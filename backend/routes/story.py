from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.error_analyzer import analyze_errors as _run_error_analysis
from core.llm import router as llm_router
from core.romaji import convert_to_japanese, is_romaji_heavy
from core.streaming import stream_json
from core.story_builder import (
    build_continuation_prompt,
    build_system_prompt,
    generate_story_brief,
    get_due_vocab,
    get_user_or_404,
    get_vocab_tiers,
    parse_llm_response,
    validate_vocab_budget,
)
from core.tokenizer import Token, tokenize
from db.models import SessionSummary, Story, StorySession, UserVocab, Vocab, get_db
from routes.vocab import _annotate_with_vocab_status

router = APIRouter(prefix="/story", tags=["story"])

_MAX_RETRIES = 3
_DEFAULT_NEW_WORD_PCT = 15
_CONTEXT_LIMIT_TOKENS = 4096  # conservative default; overridden per model later


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StartStoryRequest(BaseModel):
    user_id: int = 1
    theme: str | None = None
    grammar_focus: str | None = None
    new_word_pct: int = Field(default=_DEFAULT_NEW_WORD_PCT, ge=0, le=50)


class ContinueStoryRequest(BaseModel):
    user_input: str
    user_id: int = 1
    difficulty_hint: str | None = None   # "too_hard" | "too_easy"


class TokenOut(BaseModel):
    surface: str
    reading: str
    pos: str
    is_content: bool
    status: str
    vocab_id: int | None


class StoryResponse(BaseModel):
    session_id: int
    story_id: int
    tokens: list[TokenOut]
    choices: list[str]
    context_usage_pct: float
    new_word_count: int
    total_content_words: int
    converted_input: str | None = None  # set when user typed romaji and it was converted


class TranslateRequest(BaseModel):
    text: str
    user_id: int = 1


class TranslateResponse(BaseModel):
    translation: str


class AnalyzeErrorsRequest(BaseModel):
    session_id: int
    user_input: str
    user_id: int = 1


class ErrorItem(BaseModel):
    error_text: str
    correction: str
    type: str          # "critical" | "grammar" | "politeness" | "unnatural" | "stylistic"
    explanation: str


class ErrorAnalysisResponse(BaseModel):
    session_id: int
    errors: list[ErrorItem]
    overall_feedback: str
    converted_input: str | None = None  # present when romaji was converted before analysis


class SessionStatsOut(BaseModel):
    turns: int
    new_words_total: int
    content_words_total: int
    errors_by_type: dict[str, int]


class SummaryRequest(BaseModel):
    user_id: int = 1


class WordEntry(BaseModel):
    vocab_id: int
    word: str
    reading: str
    meaning: str


class SummaryResponse(BaseModel):
    session_id: int
    story_id: int
    stats: SessionStatsOut
    coach_note: str
    new_words: list[WordEntry] = []
    known_words: list[WordEntry] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/start")
async def start_story(req: StartStoryRequest, db: Session = Depends(get_db)):
    """
    Start a new story session. Generates the opening segment calibrated
    to the user's vocabulary level and creates DB records.
    Streams heartbeat newlines while the LLM is working to keep the
    TCP connection alive for slow local models.
    """
    async def work() -> dict:
        user = get_user_or_404(req.user_id, db)
        model_settings = user.model_settings or {}
        story_model: str | None = model_settings.get("story") or None
        sc = user.story_config or {}
        story_temperature: float | None = sc.get("temperature") or None
        story_length: str = sc.get("story_length") or "medium"
        # new_word_pct: request value wins; fall back to user's saved default
        new_word_pct = req.new_word_pct if req.new_word_pct != _DEFAULT_NEW_WORD_PCT else int(sc.get("new_word_pct", req.new_word_pct))

        confident_vocab, fragile_vocab = get_vocab_tiers(req.user_id, db)
        known_surfaces = confident_vocab | fragile_vocab  # union for budget validation

        # Generate narrative anchor — keeps LLM coherent across all turns
        brief = await generate_story_brief(req.theme, user, model_override=story_model)

        # Build the opening user message — sets scene and theme
        opening = _build_opening_message(req.theme, req.grammar_focus)
        messages = [{"role": "user", "content": opening}]

        system_prompt = build_system_prompt(
            user, confident_vocab, fragile_vocab, new_word_pct,
            story_brief=brief, story_length=story_length,
        )

        story_text, choices, tokens, new_count, total = await _generate_with_retry(
            system_prompt=system_prompt,
            messages=messages,
            known_surfaces=known_surfaces,
            target_pct=new_word_pct,
            model_override=story_model,
            temperature=story_temperature,
        )
        tokens = _annotate_with_vocab_status(tokens, req.user_id, db)

        # Persist story + session
        story = Story(
            theme=req.theme,
            grammar_focus=req.grammar_focus,
            brief=brief,
            status="active",
        )
        db.add(story)
        db.flush()  # get story.id without full commit

        # Store only the story_text as the assistant turn — not the raw JSON.
        # If the model sees its own JSON in history it tries to continue the JSON
        # format rather than the narrative, producing garbled output.
        history = [
            {"role": "user", "content": opening},
            {"role": "assistant", "content": story_text},
        ]
        context_tokens = _estimate_tokens(system_prompt, history)

        # Collect known vocab_ids seen in this turn
        known_ids = [t.vocab_id for t in tokens if t.is_content and t.status == "known" and t.vocab_id]

        session = StorySession(
            story_id=story.id,
            content_json=history,
            context_tokens_used=context_tokens,
            session_meta={
                "new_words_total": new_count,
                "content_words_total": total,
                "turn_count": 0,  # user turns only
                "errors": [],
                "session_words": {"new_tokens": [], "known": list(set(known_ids))},
            },
        )
        db.add(session)
        db.flush()  # get session.id so _introduce_new_words can reference it

        # Mark new words as "introduced" in user_vocab; track their ids in session_words
        await _introduce_new_words(req.user_id, tokens, known_surfaces, db, session=session)

        db.commit()
        db.refresh(session)

        return StoryResponse(
            session_id=session.id,
            story_id=story.id,
            tokens=_tokens_to_out(tokens),
            choices=choices,
            context_usage_pct=round(context_tokens / _CONTEXT_LIMIT_TOKENS * 100, 1),
            new_word_count=new_count,
            total_content_words=total,
        ).model_dump()

    return await stream_json(work())


@router.post("/continue/{session_id}")
async def continue_story(
    session_id: int,
    req: ContinueStoryRequest,
    db: Session = Depends(get_db),
):
    """
    Continue a story session with user input. Appends to message history
    and generates the next segment.
    Streams heartbeat newlines while the LLM is working to keep the
    TCP connection alive for slow local models.
    """
    session = db.query(StorySession).filter(StorySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    get_user_or_404(req.user_id, db)  # validate user exists before streaming starts

    async def work() -> dict:
        user = get_user_or_404(req.user_id, db)
        model_settings = user.model_settings or {}
        story_model: str | None = model_settings.get("story") or None
        error_model: str | None = model_settings.get("error_analysis") or None
        sc = user.story_config or {}
        story_temperature: float | None = sc.get("temperature") or None
        story_length: str = sc.get("story_length") or "medium"
        new_word_pct: int = int(sc.get("new_word_pct", _DEFAULT_NEW_WORD_PCT))

        confident_vocab, fragile_vocab = get_vocab_tiers(req.user_id, db)
        known_surfaces = confident_vocab | fragile_vocab

        # Convert romaji to Japanese if needed — the LLM and tokenizer need proper Japanese
        user_input = req.user_input
        converted_input: str | None = None
        if is_romaji_heavy(user_input):
            japanese = await convert_to_japanese(user_input, model_override=error_model)
            if japanese != user_input:
                converted_input = japanese
                user_input = japanese

        story = db.query(Story).filter(Story.id == session.story_id).first()
        meta = dict(session.session_meta or {})
        existing_summary: str | None = meta.get("story_summary")

        # SM-2: get words due for review to reinforce in this turn
        due_words = get_due_vocab(req.user_id, db)

        system_prompt = build_system_prompt(
            user, confident_vocab, fragile_vocab, new_word_pct,
            story_brief=story.brief if story else None,
            due_vocab=due_words or None,
            story_length=story_length,
        )

        difficulty_hint = _difficulty_hint_text(req.difficulty_hint)
        adjusted_system, messages, new_summary = await build_continuation_prompt(
            system_prompt=system_prompt,
            history=session.content_json,
            user_input=user_input,
            difficulty_hint=difficulty_hint,
            existing_summary=existing_summary,
            model_override=story_model,
        )

        story_text, choices, tokens, new_count, total = await _generate_with_retry(
            system_prompt=adjusted_system,
            messages=messages,
            known_surfaces=known_surfaces,
            target_pct=new_word_pct,
            model_override=story_model,
            temperature=story_temperature,
        )
        tokens = _annotate_with_vocab_status(tokens, req.user_id, db)

        # Update session history (store the Japanese version so history stays coherent)
        updated_history = [
            *session.content_json,
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": story_text},
        ]
        context_tokens = _estimate_tokens(adjusted_system, updated_history)

        session.content_json = updated_history
        session.context_tokens_used = context_tokens

        # Accumulate running stats for session summary
        meta["new_words_total"] = meta.get("new_words_total", 0) + new_count
        meta["content_words_total"] = meta.get("content_words_total", 0) + total
        meta["turn_count"] = meta.get("turn_count", 0) + 1
        if "errors" not in meta:
            meta["errors"] = []

        # Persist narrative compression if new turns were compressed this turn
        if new_summary:
            meta["story_summary"] = new_summary

        # Accumulate known vocab_ids seen this turn
        known_ids_this_turn = [t.vocab_id for t in tokens if t.is_content and t.status == "known" and t.vocab_id]
        session_words = meta.setdefault("session_words", {"new_tokens": [], "known": []})
        session_words["known"] = list(set(session_words.get("known", [])) | set(known_ids_this_turn))
        meta["session_words"] = session_words

        session.session_meta = meta
        flag_modified(session, "session_meta")

        await _introduce_new_words(req.user_id, tokens, known_surfaces, db, session=session)

        db.commit()

        return StoryResponse(
            session_id=session.id,
            story_id=session.story_id,
            tokens=_tokens_to_out(tokens),
            choices=choices,
            context_usage_pct=round(context_tokens / _CONTEXT_LIMIT_TOKENS * 100, 1),
            new_word_count=new_count,
            total_content_words=total,
            converted_input=converted_input,
        ).model_dump()

    return await stream_json(work())


@router.get("/session/{session_id}")
async def get_session(session_id: int, db: Session = Depends(get_db)):
    """Fetch the raw session history (for debugging and session summary)."""
    session = db.query(StorySession).filter(StorySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.id,
        "story_id": session.story_id,
        "context_tokens_used": session.context_tokens_used,
        "context_usage_pct": round(session.context_tokens_used / _CONTEXT_LIMIT_TOKENS * 100, 1),
        "history": session.content_json,
    }


@router.post("/translate", response_model=TranslateResponse)
async def translate_segment(req: TranslateRequest, db: Session = Depends(get_db)):
    """
    Translate a Japanese story segment into the user's native language.
    Called on demand — the frontend caches the result so it's fetched once.
    """
    from db.models import User
    user = db.query(User).filter(User.id == req.user_id).first()
    native = user.native_language if user else "en"
    lang_name = {"pt": "Portuguese", "en": "English"}.get(native, native)

    system = (
        f"You are a Japanese translator. Translate the following Japanese text naturally into {lang_name}. "
        "Output only the translation — no explanations, no Japanese, no extra text."
    )
    messages = [{"role": "user", "content": req.text}]
    translation = await llm_router.route("story", system, messages)
    return TranslateResponse(translation=translation.strip())


@router.post("/analyze-errors", response_model=ErrorAnalysisResponse)
async def analyze_errors_endpoint(
    req: AnalyzeErrorsRequest,
    db: Session = Depends(get_db),
):
    """
    Analyse a learner's Japanese input for errors.
    Stores the result in session_meta so the session summary can aggregate it.
    """
    session = db.query(StorySession).filter(StorySession.id == req.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from db.models import User
    user = db.query(User).filter(User.id == req.user_id).first()
    native = user.native_language if user else "en"
    error_model: str | None = (user.model_settings or {}).get("error_analysis") or None

    result = await _run_error_analysis(req.user_input, native, model_override=error_model)

    # Persist errors in session_meta for use in session summary
    meta = dict(session.session_meta or {})
    if "errors" not in meta:
        meta["errors"] = []

    # Find the current turn index (number of user turns so far)
    turn_index = meta.get("turn_count", 0)
    meta["errors"].append({
        "turn_index": turn_index,
        "user_input": req.user_input,
        "errors": result["errors"],
        "overall_feedback": result["overall_feedback"],
    })
    session.session_meta = meta
    flag_modified(session, "session_meta")
    db.commit()

    return ErrorAnalysisResponse(
        session_id=req.session_id,
        errors=[ErrorItem(**e) for e in result["errors"]],
        overall_feedback=result["overall_feedback"],
        converted_input=result.get("converted"),
    )


@router.post("/summary/{session_id}", response_model=SummaryResponse)
async def get_session_summary(
    session_id: int,
    req: SummaryRequest,
    db: Session = Depends(get_db),
):
    """
    Generate (or retrieve cached) session summary.
    Computes stats from session_meta and generates an AI coach note.
    Persists to SessionSummary for future retrieval.
    """
    session = db.query(StorySession).filter(StorySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    story = db.query(Story).filter(Story.id == session.story_id).first()

    from db.models import User
    user = db.query(User).filter(User.id == req.user_id).first()
    native_lang = user.native_language if user else "en"

    meta = session.session_meta or {}

    # Return cached summary if already generated
    if session.summary:
        cached = session.summary
        return _build_summary_response(session_id, session.story_id, cached.stats_json, cached.coach_note or "", meta, db)

    errors_log: list[dict] = meta.get("errors", [])

    # Aggregate errors by type
    errors_by_type: dict[str, int] = {
        "critical": 0, "grammar": 0, "politeness": 0, "unnatural": 0, "stylistic": 0
    }
    for entry in errors_log:
        for err in entry.get("errors", []):
            etype = err.get("type", "grammar")
            if etype in errors_by_type:
                errors_by_type[etype] += 1

    stats = SessionStatsOut(
        turns=meta.get("turn_count", 0),
        new_words_total=meta.get("new_words_total", 0),
        content_words_total=meta.get("content_words_total", 0),
        errors_by_type=errors_by_type,
    )

    # Generate AI coach note
    coach_model: str | None = (user.model_settings or {}).get("coach_note") or None
    coach_note = await _generate_coach_note(session, story, stats, errors_log, native_lang, model_override=coach_model)

    # Persist
    summary_record = SessionSummary(
        session_id=session_id,
        stats_json=stats.model_dump(),
        coach_note=coach_note,
    )
    db.add(summary_record)

    # Mark story as completed
    if story:
        story.status = "completed"

    db.commit()

    return _build_summary_response(session_id, session.story_id, stats.model_dump(), coach_note, meta, db)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_summary_response(
    session_id: int,
    story_id: int,
    stats_json: dict,
    coach_note: str,
    meta: dict,
    db: Session,
) -> SummaryResponse:
    """Resolve word lists and build a SummaryResponse."""
    session_words = meta.get("session_words", {"new_tokens": [], "known": []})
    new_token_entries: list[dict] = session_words.get("new_tokens", [])
    known_ids: list[int] = session_words.get("known", [])

    # Build vocab lookup for all ids that exist
    all_vocab_ids = [e["vocab_id"] for e in new_token_entries if e.get("vocab_id")]
    all_vocab_ids += known_ids
    vocab_map: dict[int, Vocab] = {}
    if all_vocab_ids:
        rows = db.query(Vocab).filter(Vocab.id.in_(all_vocab_ids)).all()
        vocab_map = {v.id: v for v in rows}

    # New words: show all — use DB meaning when available, blank when not (word not in seed)
    new_words: list[WordEntry] = []
    for entry in new_token_entries:
        vid = entry.get("vocab_id")
        v = vocab_map.get(vid) if vid else None
        new_words.append(WordEntry(
            vocab_id=vid or 0,
            word=entry["surface"],
            reading=entry["reading"],
            meaning=v.meaning if v else "",
        ))

    # Known words: always have ids
    known_words: list[WordEntry] = []
    seen_known: set[int] = set()
    for vid in known_ids:
        if vid in seen_known:
            continue
        seen_known.add(vid)
        v = vocab_map.get(vid)
        if v:
            known_words.append(WordEntry(vocab_id=v.id, word=v.word, reading=v.reading, meaning=v.meaning))

    return SummaryResponse(
        session_id=session_id,
        story_id=story_id,
        stats=SessionStatsOut(**stats_json),
        coach_note=coach_note,
        new_words=new_words,
        known_words=known_words,
    )


_JSON_FORMAT_REMINDER = (
    '\n\nCRITICAL FORMAT ERROR: Your last response was plain text, not JSON. '
    'You MUST respond with ONLY a JSON object — no dialogue, no narration outside the JSON. '
    'Required format:\n'
    '{"story_text": "story in Japanese", "choices": ["「...」", "「...」"]}'
)

_LANGUAGE_REMINDER = (
    '\n\nLANGUAGE ERROR: Your last response contained English or romaji words inside the Japanese text. '
    'ALL story_text and ALL choices must be written entirely in Japanese (kanji/hiragana/katakana). '
    'No English words — not even proper nouns like "Lunch", "Game", "OK".'
)

_FALLBACK_CHOICES = ["「はい、わかりました。」", "「少し待ってください。」", "「もう一度お願いします。」"]

import re as _re
_LATIN_WORD_RE = _re.compile(r'\b[a-zA-Z]{2,}\b')


async def _generate_with_retry(
    system_prompt: str,
    messages: list[dict],
    known_surfaces: set[str],
    target_pct: int,
    model_override: str | None = None,
    temperature: float | None = None,
) -> tuple[str, list[str], list[Token], int, int]:
    """
    Call the LLM, validate vocab budget, and retry up to _MAX_RETRIES times.

    On JSON parse failure: inject a strong format reminder for the next attempt.
    On final failure: rescue the raw text as story_text with fallback choices
    rather than crashing — a degraded response is better than a 500.
    """
    current_system = system_prompt
    last_raw: str = ""

    for attempt in range(_MAX_RETRIES):
        raw = await llm_router.route("story", current_system, messages, model_override=model_override, temperature=temperature)
        last_raw = raw

        try:
            story_text, choices = parse_llm_response(raw)
        except ValueError:
            if attempt == _MAX_RETRIES - 1:
                # Last chance: rescue whatever Japanese text the model produced
                story_text = raw.strip() or "続きを考えています…"
                choices = _FALLBACK_CHOICES
                tokens = tokenize(story_text)
                return story_text, choices, tokens, 0, max(len([t for t in tokens if t.is_content]), 1)
            # Inject a hard format reminder for the next attempt
            current_system = system_prompt + _JSON_FORMAT_REMINDER
            continue

        # Check for English/Latin words leaking into the story text
        if _LATIN_WORD_RE.search(story_text) and attempt < _MAX_RETRIES - 1:
            current_system = system_prompt + _LANGUAGE_REMINDER
            continue

        within_budget, tokens, new_count, total = validate_vocab_budget(
            story_text, known_surfaces, target_pct
        )

        if within_budget or attempt == _MAX_RETRIES - 1:
            return story_text, choices, tokens, new_count, total

        # Over budget — tighten the instruction for the next attempt
        actual_pct = round((new_count / max(total, 1)) * 100)
        current_system = system_prompt + (
            f"\n\nIMPORTANT: Your last response used ~{actual_pct}% new words. "
            f"The target is {target_pct}%. Please use significantly fewer new words — "
            f"stick closely to the known vocabulary list provided."
        )

    # Should never reach here, but satisfy the type checker
    raise RuntimeError("Retry loop exited without returning")


async def _introduce_new_words(
    user_id: int,
    tokens: list[Token],
    known_surfaces: set[str],
    db: Session,
    session: "StorySession | None" = None,
) -> None:
    """
    For each unseen content word in the story, look it up in the global vocab
    table and create a UserVocab row with status='introduced'.

    If a session is provided, tracks ALL new tokens (surface+reading+optional vocab_id)
    in session_meta["session_words"]["new_tokens"] — even words not in the vocab DB.
    """
    unseen_tokens = [
        t for t in tokens
        if t.is_content and t.surface not in known_surfaces
    ]
    if not unseen_tokens:
        return

    unseen_surfaces = {t.surface for t in unseen_tokens}
    vocab_rows = db.query(Vocab).filter(Vocab.word.in_(unseen_surfaces)).all()
    vocab_by_surface: dict[str, Vocab] = {v.word: v for v in vocab_rows}

    for vocab in vocab_rows:
        existing = (
            db.query(UserVocab)
            .filter(UserVocab.user_id == user_id, UserVocab.vocab_id == vocab.id)
            .first()
        )
        if not existing:
            db.add(UserVocab(
                user_id=user_id,
                vocab_id=vocab.id,
                status="introduced",
            ))

    if session:
        meta = dict(session.session_meta or {})
        session_words = meta.setdefault("session_words", {"new_tokens": [], "known": []})
        existing_surfaces = {e["surface"] for e in session_words.get("new_tokens", [])}

        for t in unseen_tokens:
            if t.surface in existing_surfaces:
                continue
            v = vocab_by_surface.get(t.surface)
            session_words.setdefault("new_tokens", []).append({
                "surface": t.surface,
                "reading": t.reading,
                "vocab_id": v.id if v else None,
            })
            existing_surfaces.add(t.surface)

        meta["session_words"] = session_words
        session.session_meta = meta
        flag_modified(session, "session_meta")


def _estimate_tokens(system_prompt: str, messages: list[dict]) -> int:
    """
    Rough token count estimate for Japanese + English mixed text.
    Japanese: ~1.5 chars per token. English: ~4 chars per token.
    This is a heuristic — good enough for the radial progress bar.
    """
    all_text = system_prompt + " ".join(m.get("content", "") for m in messages)
    return int(len(all_text) / 2)


def _tokens_to_out(tokens: list[Token]) -> list[TokenOut]:
    return [
        TokenOut(
            surface=t.surface,
            reading=t.reading,
            pos=t.pos,
            is_content=t.is_content,
            status=t.status,
            vocab_id=t.vocab_id,
        )
        for t in tokens
    ]


def _build_opening_message(theme: str | None, grammar_focus: str | None) -> str:
    parts = [
        "Please start a new interactive story where I am the protagonist.",
        "Address me directly (あなた or implied second person).",
        "Set the scene briefly, then immediately put me in a situation where I need to act or speak.",
        "End the opening segment the moment I need to respond — someone is asking me something, "
        "or I am facing a clear choice. Do not resolve the situation for me.",
    ]
    if theme:
        parts.append(f"Theme: {theme}.")
    if grammar_focus:
        parts.append(f"Naturally incorporate grammar patterns related to: {grammar_focus}.")
    return " ".join(parts)


async def _generate_coach_note(
    session: "StorySession",
    story: "Story | None",
    stats: SessionStatsOut,
    errors_log: list[dict],
    native_lang: str = "en",
    model_override: str | None = None,
) -> str:
    """Generate a personalised coach note summarising the session."""
    lang_name = {"pt": "Portuguese", "en": "English"}.get(native_lang, "English")
    total_errors = sum(stats.errors_by_type.values())
    top_error_type = (
        max(stats.errors_by_type, key=lambda k: stats.errors_by_type[k])
        if total_errors > 0 else None
    )

    error_summary = (
        f"{total_errors} error(s) found — most common type: {top_error_type}."
        if total_errors > 0 else "No errors detected."
    )

    # Include the last few story exchanges for context
    history = session.content_json or []
    recent_exchanges = history[-6:]  # last 3 turns
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in recent_exchanges
    )

    system = (
        f"LANGUAGE: Write ONLY in {lang_name}. Do NOT write in Japanese or any other language. "
        f"You are an encouraging Japanese language coach. "
        f"Write a short (2–4 sentence) personalised coach note for the learner "
        f"based on their practice session stats. Be specific, positive, and actionable. "
        f"Output only the coach note text — no headers, no bullet points."
    )
    prompt = (
        f"Session stats:\n"
        f"- Turns taken: {stats.turns}\n"
        f"- New words encountered: {stats.new_words_total}\n"
        f"- Content words in story: {stats.content_words_total}\n"
        f"- {error_summary}\n\n"
        f"Recent story excerpt:\n{history_text}"
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        note = await llm_router.route("coach_note", system, messages, model_override=model_override)
        return note.strip()
    except Exception:
        return "Great work completing this session! Keep reading and writing Japanese every day."


def _difficulty_hint_text(hint: str | None) -> str | None:
    if hint == "too_hard":
        return (
            "The learner found this too difficult. Reduce new vocabulary significantly, "
            "use shorter sentences, and choose familiar settings and topics."
        )
    if hint == "too_easy":
        return (
            "The learner found this too easy. Introduce more new vocabulary, "
            "use more complex sentence structures, and raise the stakes in the story."
        )
    return None
