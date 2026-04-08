from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

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
from db.models import Story, StorySession, UserVocab, Vocab, get_db

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

    # Update session history
    updated_history = [
        *session.content_json,
        {"role": "user", "content": req.user_input},
        {"role": "assistant", "content": story_text},
    ]
    context_tokens = _estimate_tokens(adjusted_system, updated_history)

    session.content_json = updated_history
    session.context_tokens_used = context_tokens

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
