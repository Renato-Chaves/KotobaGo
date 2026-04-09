from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.error_analyzer import analyze_errors as _run_error_analysis
from core.llm import router as llm_router
from core.story_builder import (
    build_continuation_prompt,
    build_system_prompt,
    get_known_surfaces,
    get_user_or_404,
    parse_llm_response,
    validate_vocab_budget,
)
from core.tokenizer import Token
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


class SessionStatsOut(BaseModel):
    turns: int
    new_words_total: int
    content_words_total: int
    errors_by_type: dict[str, int]


class SummaryRequest(BaseModel):
    user_id: int = 1


class SummaryResponse(BaseModel):
    session_id: int
    story_id: int
    stats: SessionStatsOut
    coach_note: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/start", response_model=StoryResponse)
async def start_story(req: StartStoryRequest, db: Session = Depends(get_db)):
    """
    Start a new story session. Generates the opening segment calibrated
    to the user's vocabulary level and creates DB records.
    """
    user = get_user_or_404(req.user_id, db)
    known_surfaces = get_known_surfaces(req.user_id, db)

    # Build the opening user message — sets scene and theme
    opening = _build_opening_message(req.theme, req.grammar_focus)
    messages = [{"role": "user", "content": opening}]

    system_prompt = build_system_prompt(user, list(known_surfaces), req.new_word_pct)

    story_text, choices, tokens, new_count, total = await _generate_with_retry(
        system_prompt=system_prompt,
        messages=messages,
        known_surfaces=known_surfaces,
        target_pct=req.new_word_pct,
    )
    tokens = _annotate_with_vocab_status(tokens, req.user_id, db)

    # Persist story + session
    story = Story(
        theme=req.theme,
        grammar_focus=req.grammar_focus,
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

    session = StorySession(
        story_id=story.id,
        content_json=history,
        context_tokens_used=context_tokens,
        session_meta={
            "new_words_total": new_count,
            "content_words_total": total,
            "turn_count": 0,  # user turns only
            "errors": [],
        },
    )
    db.add(session)

    # Mark new words as "introduced" in user_vocab
    await _introduce_new_words(req.user_id, tokens, known_surfaces, db)

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
    )


@router.post("/continue/{session_id}", response_model=StoryResponse)
async def continue_story(
    session_id: int,
    req: ContinueStoryRequest,
    db: Session = Depends(get_db),
):
    """
    Continue a story session with user input. Appends to message history
    and generates the next segment.
    """
    session = db.query(StorySession).filter(StorySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    user = get_user_or_404(req.user_id, db)
    known_surfaces = get_known_surfaces(req.user_id, db)

    story = db.query(Story).filter(Story.id == session.story_id).first()
    system_prompt = build_system_prompt(user, list(known_surfaces), _DEFAULT_NEW_WORD_PCT)

    difficulty_hint = _difficulty_hint_text(req.difficulty_hint)
    adjusted_system, messages = build_continuation_prompt(
        system_prompt=system_prompt,
        history=session.content_json,
        user_input=req.user_input,
        difficulty_hint=difficulty_hint,
    )

    story_text, choices, tokens, new_count, total = await _generate_with_retry(
        system_prompt=adjusted_system,
        messages=messages,
        known_surfaces=known_surfaces,
        target_pct=_DEFAULT_NEW_WORD_PCT,
    )
    tokens = _annotate_with_vocab_status(tokens, req.user_id, db)

    # Update session history
    updated_history = [
        *session.content_json,
        {"role": "user", "content": req.user_input},
        {"role": "assistant", "content": story_text},
    ]
    context_tokens = _estimate_tokens(adjusted_system, updated_history)

    session.content_json = updated_history
    session.context_tokens_used = context_tokens

    # Accumulate running stats for session summary
    meta = dict(session.session_meta or {})
    meta["new_words_total"] = meta.get("new_words_total", 0) + new_count
    meta["content_words_total"] = meta.get("content_words_total", 0) + total
    meta["turn_count"] = meta.get("turn_count", 0) + 1
    if "errors" not in meta:
        meta["errors"] = []
    session.session_meta = meta
    flag_modified(session, "session_meta")

    await _introduce_new_words(req.user_id, tokens, known_surfaces, db)

    db.commit()

    return StoryResponse(
        session_id=session.id,
        story_id=session.story_id,
        tokens=_tokens_to_out(tokens),
        choices=choices,
        context_usage_pct=round(context_tokens / _CONTEXT_LIMIT_TOKENS * 100, 1),
        new_word_count=new_count,
        total_content_words=total,
    )


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

    result = await _run_error_analysis(req.user_input, native)

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

    # Return cached summary if already generated
    if session.summary:
        cached = session.summary
        return SummaryResponse(
            session_id=session_id,
            story_id=session.story_id,
            stats=SessionStatsOut(**cached.stats_json),
            coach_note=cached.coach_note or "",
        )

    meta = session.session_meta or {}
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
    coach_note = await _generate_coach_note(session, story, stats, errors_log, native_lang)

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

    return SummaryResponse(
        session_id=session_id,
        story_id=session.story_id,
        stats=stats,
        coach_note=coach_note,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _generate_with_retry(
    system_prompt: str,
    messages: list[dict],
    known_surfaces: set[str],
    target_pct: int,
) -> tuple[str, list[str], list[Token], int, int]:
    """
    Call the LLM, validate vocab budget, and retry up to _MAX_RETRIES times.
    On the last retry, return whatever the LLM produced regardless of budget.
    """
    current_system = system_prompt

    for attempt in range(_MAX_RETRIES):
        raw = await llm_router.route("story", current_system, messages)

        try:
            story_text, choices = parse_llm_response(raw)
        except ValueError:
            if attempt == _MAX_RETRIES - 1:
                raise
            continue  # retry on parse failure

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
) -> None:
    """
    For each unseen content word in the story, look it up in the global vocab
    table and create a UserVocab row with status='introduced'.

    Words not yet in the vocab table are skipped — they'll be seeded in Phase 4.
    """
    unseen_surfaces = {
        t.surface for t in tokens
        if t.is_content and t.surface not in known_surfaces
    }
    if not unseen_surfaces:
        return

    vocab_rows = db.query(Vocab).filter(Vocab.word.in_(unseen_surfaces)).all()
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
        f"You are an encouraging Japanese language coach. "
        f"Write a short (2–4 sentence) personalised coach note for the learner "
        f"based on their practice session stats. Be specific, positive, and actionable. "
        f"Write in {lang_name}. "
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
        note = await llm_router.route("coach_note", system, messages)
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
