"""
Lesson routes — structured grammar lesson sessions.

Session flow:
  POST /lessons/{id}/start               — create LessonSession, enter Presentation
  POST /lessons/session/{id}/continue    — send user turn to active module
  POST /lessons/session/{id}/switch-module — jump to a specific module
  POST /lessons/session/{id}/analyze-errors — error analysis (reuses error_analyzer.py)
  POST /lessons/session/{id}/summary    — generate coach note, finalize session
  POST /lessons/session/{id}/export-to-story — export conversation turns to StorySession
  GET  /lessons                          — list all lessons
"""

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.error_analyzer import analyze_errors as _run_error_analysis
from core.llm import router as llm_router
from core.modules import conversation, examples, presentation, qa, recognition
from core.story_builder import get_user_or_404
from core.tokenizer import tokenize
from db.models import (
    Lesson,
    LessonSession,
    LessonSessionSummary,
    Story,
    StorySession,
    User,
    UserVocab,
    Vocab,
    get_db,
)
from routes.vocab import _annotate_with_vocab_status

router = APIRouter(prefix="/lessons", tags=["lessons"])

# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------

_MODULES = {
    "presentation": presentation,
    "examples":     examples,
    "recognition":  recognition,
    "conversation": conversation,
    "qa":           qa,
}

_INITIAL_MODULE = "presentation"

_LANG_NAMES = {"pt": "Portuguese", "en": "English", "es": "Spanish", "fr": "French"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TokenOut(BaseModel):
    surface: str
    reading: str
    pos: str
    is_content: bool
    status: str
    vocab_id: int | None


class LessonOut(BaseModel):
    id: int
    title: str
    jlpt_level: str
    grammar_point: str | None
    category: str
    stage: int
    order: int
    content_json: dict | None


class SessionMetaOut(BaseModel):
    active_module: str
    module_history: list[str]
    qa_return_module: str | None
    modules: dict


class StartRequest(BaseModel):
    user_id: int = 1


class StartResponse(BaseModel):
    session_id: int
    lesson_id: int
    text: str
    tokens: list[TokenOut]
    session_meta: SessionMetaOut
    choices: list[str] = []


class ContinueRequest(BaseModel):
    user_id: int = 1
    user_input: str


class ContinueResponse(BaseModel):
    session_id: int
    text: str
    tokens: list[TokenOut]
    session_meta: SessionMetaOut
    stage_complete: bool
    choices: list[str] = []   # non-empty for conversation module


class SwitchModuleRequest(BaseModel):
    target_module: str


class SwitchModuleResponse(BaseModel):
    session_id: int
    text: str
    tokens: list[TokenOut]
    session_meta: SessionMetaOut
    choices: list[str] = []


class AnalyzeErrorsRequest(BaseModel):
    session_id: int
    user_input: str
    user_id: int = 1


class ErrorItem(BaseModel):
    error_text: str
    correction: str
    type: str
    explanation: str


class ErrorAnalysisResponse(BaseModel):
    session_id: int
    errors: list[ErrorItem]
    overall_feedback: str
    converted_input: str | None = None


class SummaryRequest(BaseModel):
    user_id: int = 1


class SummaryResponse(BaseModel):
    session_id: int
    lesson_id: int
    stats_json: dict
    coach_note: str


class ExportRequest(BaseModel):
    user_id: int = 1


class ExportResponse(BaseModel):
    session_id: int   # new StorySession id


# ---------------------------------------------------------------------------
# GET /lessons
# ---------------------------------------------------------------------------

@router.get("", response_model=list[LessonOut])
async def list_lessons(db: Session = Depends(get_db)):
    """List all lessons ordered by stage and position within stage."""
    lessons = db.query(Lesson).order_by(Lesson.stage, Lesson.order).all()
    return [
        LessonOut(
            id=l.id,
            title=l.title,
            jlpt_level=l.jlpt_level,
            grammar_point=l.grammar_point,
            category=getattr(l, "category", "grammar") or "grammar",
            stage=l.stage,
            order=l.order,
            content_json=l.content_json,
        )
        for l in lessons
    ]


# ---------------------------------------------------------------------------
# POST /lessons/{id}/start
# ---------------------------------------------------------------------------

@router.post("/{lesson_id}/start", response_model=StartResponse)
async def start_lesson(
    lesson_id: int,
    req: StartRequest,
    db: Session = Depends(get_db),
):
    """
    Start a lesson session. Creates LessonSession, enters the Presentation module,
    and returns the AI's opening explanation.
    """
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    user = get_user_or_404(req.user_id, db)

    # Build initial session_meta
    session_meta = _make_session_meta()

    # Generate the Presentation module's opening turn
    system = presentation.build_system_prompt(lesson, user, session_meta["modules"]["presentation"])
    opening_prompt = presentation.build_opening(lesson, user)
    messages = [{"role": "user", "content": opening_prompt}]

    text = await llm_router.route("lesson", system, messages)
    text = text.strip()

    # Seed history: only the assistant reply (the opening prompt is internal)
    history = [{"role": "assistant", "content": text}]

    # Advance module turn counter
    session_meta["modules"]["presentation"]["turns"] += 1

    session = LessonSession(
        lesson_id=lesson_id,
        user_id=req.user_id,
        content_json=history,
        session_meta=session_meta,
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    tokens = _tokenize_lesson_text(text, req.user_id, db)

    return StartResponse(
        session_id=session.id,
        lesson_id=lesson_id,
        text=text,
        tokens=tokens,
        session_meta=SessionMetaOut(**session.session_meta),
        choices=[],
    )


# ---------------------------------------------------------------------------
# POST /lessons/session/{id}/continue
# ---------------------------------------------------------------------------

@router.post("/session/{session_id}/continue", response_model=ContinueResponse)
async def continue_lesson(
    session_id: int,
    req: ContinueRequest,
    db: Session = Depends(get_db),
):
    """
    Continue the current lesson module with the user's input.
    Routes to the active module's system prompt, calls LLM, returns response.
    """
    session, lesson, user = _load_session_context(session_id, req.user_id, db)

    meta = dict(session.session_meta or {})
    active = meta.get("active_module", _INITIAL_MODULE)
    module = _MODULES.get(active)
    if not module:
        raise HTTPException(status_code=400, detail=f"Unknown module: {active}")

    module_state = meta["modules"].get(active, {})
    system = module.build_system_prompt(lesson, user, module_state)

    # Determine if this is a "return" signal in QA mode
    is_return = _is_return_signal(req.user_input)
    if active == "qa" and is_return and meta.get("qa_return_module"):
        # Switch back to origin module
        return_to = meta["qa_return_module"]
        meta["qa_return_module"] = None
        meta["active_module"] = return_to
        session.session_meta = meta
        flag_modified(session, "session_meta")
        db.commit()
        # Re-enter via switch so we get a proper module intro
        return await _do_switch(session, lesson, user, return_to, meta, db)

    # Build messages: full history + user turn
    history = list(session.content_json or [])
    messages = [*history, {"role": "user", "content": req.user_input}]

    # For the conversation module, parse JSON response like story builder
    turn_choices: list[str] = []
    if active == "conversation":
        text, turn_choices = await _call_conversation_module(system, messages)
    else:
        raw = await llm_router.route("lesson", system, messages)
        text = raw.strip()

    # Update history
    updated_history = [*history, {"role": "user", "content": req.user_input}, {"role": "assistant", "content": text}]
    session.content_json = updated_history

    # Advance module turn counter
    module_state = meta["modules"].setdefault(active, {})
    module_state["turns"] = module_state.get("turns", 0) + 1

    # Track seen example ids for the examples module
    if active == "examples":
        next_id = examples.next_unseen_id(lesson, module_state)
        if next_id:
            module_state.setdefault("seen_ids", []).append(next_id)

    stage_complete = module.should_advance(module_state)

    meta["modules"][active] = module_state
    session.session_meta = meta
    flag_modified(session, "session_meta")
    db.commit()

    tokens = _tokenize_lesson_text(text, req.user_id, db)

    return ContinueResponse(
        session_id=session.id,
        text=text,
        tokens=tokens,
        session_meta=SessionMetaOut(**session.session_meta),
        stage_complete=stage_complete,
        choices=turn_choices,
    )


# ---------------------------------------------------------------------------
# POST /lessons/session/{id}/switch-module
# ---------------------------------------------------------------------------

@router.post("/session/{session_id}/switch-module", response_model=SwitchModuleResponse)
async def switch_module(
    session_id: int,
    req: SwitchModuleRequest,
    db: Session = Depends(get_db),
):
    """
    Jump to a specific lesson module. State is preserved per module.
    Can also activate QA mode — sets qa_return_module to resume later.
    """
    session, lesson, user = _load_session_context(session_id, 1, db)
    meta = dict(session.session_meta or {})

    if req.target_module not in _MODULES:
        raise HTTPException(status_code=400, detail=f"Unknown module: {req.target_module}")

    return await _do_switch(session, lesson, user, req.target_module, meta, db)


# ---------------------------------------------------------------------------
# POST /lessons/session/{id}/analyze-errors
# ---------------------------------------------------------------------------

@router.post("/session/{session_id}/analyze-errors", response_model=ErrorAnalysisResponse)
async def analyze_errors_endpoint(
    session_id: int,
    req: AnalyzeErrorsRequest,
    db: Session = Depends(get_db),
):
    """
    Analyse a learner's Japanese input for errors. Reuses error_analyzer.py.
    Stores result in session_meta for the session summary.
    """
    session = db.query(LessonSession).filter(LessonSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    user = db.query(User).filter(User.id == req.user_id).first()
    native = user.native_language if user else "en"
    error_model: str | None = (user.model_settings or {}).get("error_analysis") if user else None

    result = await _run_error_analysis(req.user_input, native, model_override=error_model)

    # Persist in session_meta
    meta = dict(session.session_meta or {})
    meta.setdefault("errors", []).append({
        "turn_index": meta.get("modules", {}).get(meta.get("active_module", ""), {}).get("turns", 0),
        "user_input": req.user_input,
        "errors": result["errors"],
        "overall_feedback": result["overall_feedback"],
    })
    session.session_meta = meta
    flag_modified(session, "session_meta")
    db.commit()

    return ErrorAnalysisResponse(
        session_id=session_id,
        errors=[ErrorItem(**e) for e in result["errors"]],
        overall_feedback=result["overall_feedback"],
        converted_input=result.get("converted"),
    )


# ---------------------------------------------------------------------------
# POST /lessons/session/{id}/summary
# ---------------------------------------------------------------------------

@router.post("/session/{session_id}/summary", response_model=SummaryResponse)
async def get_lesson_summary(
    session_id: int,
    req: SummaryRequest,
    db: Session = Depends(get_db),
):
    """
    Generate (or retrieve cached) lesson session summary with an AI coach note.
    """
    session = db.query(LessonSession).filter(LessonSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Return cached if available
    if session.summary:
        s = session.summary
        return SummaryResponse(
            session_id=session_id,
            lesson_id=session.lesson_id,
            stats_json=s.stats_json,
            coach_note=s.coach_note or "",
        )

    user = db.query(User).filter(User.id == req.user_id).first()
    native_lang = user.native_language if user else "en"
    lesson = db.query(Lesson).filter(Lesson.id == session.lesson_id).first()

    meta = session.session_meta or {}
    errors_log = meta.get("errors", [])

    # Build stats
    modules_state = meta.get("modules", {})
    total_turns = sum(m.get("turns", 0) for m in modules_state.values())
    errors_by_type: dict[str, int] = {
        "critical": 0, "grammar": 0, "politeness": 0, "unnatural": 0, "stylistic": 0
    }
    for entry in errors_log:
        for err in entry.get("errors", []):
            etype = err.get("type", "grammar")
            if etype in errors_by_type:
                errors_by_type[etype] += 1

    stats = {
        "turns": total_turns,
        "modules_completed": list(meta.get("module_history", [])),
        "errors_by_type": errors_by_type,
    }

    grammar_point = (lesson.content_json or {}).get("grammar_point") if lesson else ""
    coach_note = await _generate_lesson_coach_note(
        grammar_point=grammar_point or (lesson.title if lesson else ""),
        stats=stats,
        errors_log=errors_log,
        native_lang=native_lang,
        model_override=(user.model_settings or {}).get("coach_note") if user else None,
    )

    # Persist
    summary_record = LessonSessionSummary(
        session_id=session_id,
        stats_json=stats,
        coach_note=coach_note,
    )
    db.add(summary_record)
    session.status = "completed"
    db.commit()

    return SummaryResponse(
        session_id=session_id,
        lesson_id=session.lesson_id,
        stats_json=stats,
        coach_note=coach_note,
    )


# ---------------------------------------------------------------------------
# POST /lessons/session/{id}/export-to-story
# ---------------------------------------------------------------------------

@router.post("/session/{session_id}/export-to-story", response_model=ExportResponse)
async def export_to_story(
    session_id: int,
    req: ExportRequest,
    db: Session = Depends(get_db),
):
    """
    Export the conversation module turns to a new StorySession.

    Extracts the last N conversation turns, creates a Story + StorySession with
    a hard grammar constraint in the brief, and returns the new session id.
    """
    session = db.query(LessonSession).filter(LessonSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    lesson = db.query(Lesson).filter(Lesson.id == session.lesson_id).first()
    user = get_user_or_404(req.user_id, db)

    content = lesson.content_json or {} if lesson else {}
    grammar_point = content.get("grammar_point") or (lesson.title if lesson else "")

    # Extract recent turns — use last 8 messages (4 turns) from the lesson session
    history = list(session.content_json or [])
    initial_history = history[-8:] if len(history) > 8 else history

    # Hard grammar constraint embedded in the story brief
    brief = {
        "setting": f"Continuing from your {grammar_point} lesson",
        "protagonist_situation": "You are the protagonist, continuing your adventure",
        "atmosphere": "Warm and encouraging",
        "key_characters": [],
        "arc": f"A story that naturally uses {grammar_point} throughout",
        "grammar_constraint": f"REQUIRED: use '{grammar_point}' naturally and repeatedly throughout this story",
    }

    story = Story(
        grammar_focus=grammar_point,
        brief=brief,
        status="active",
    )
    db.add(story)
    db.flush()

    story_session = StorySession(
        story_id=story.id,
        content_json=initial_history,
        context_tokens_used=0,
        session_meta={
            "new_words_total": 0,
            "content_words_total": 0,
            "turn_count": 0,
            "errors": [],
            "session_words": {"new_tokens": [], "known": []},
            "exported_from_lesson": session_id,
        },
    )
    db.add(story_session)

    # Mark the conversation module as exported
    meta = dict(session.session_meta or {})
    meta.setdefault("modules", {}).setdefault("conversation", {})["exported"] = True
    session.session_meta = meta
    flag_modified(session, "session_meta")

    db.commit()
    db.refresh(story_session)

    return ExportResponse(session_id=story_session.id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_session_meta() -> dict:
    return {
        "active_module": _INITIAL_MODULE,
        "module_history": [_INITIAL_MODULE],
        "qa_return_module": None,
        "modules": {
            "presentation": presentation.initial_state(),
            "examples":     examples.initial_state(),
            "recognition":  recognition.initial_state(),
            "conversation": conversation.initial_state(),
            "qa":           qa.initial_state(),
        },
    }


def _load_session_context(
    session_id: int,
    user_id: int,
    db: Session,
) -> tuple[LessonSession, Lesson, User]:
    session = db.query(LessonSession).filter(LessonSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    lesson = db.query(Lesson).filter(Lesson.id == session.lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    user = get_user_or_404(user_id, db)
    return session, lesson, user


async def _do_switch(
    session: LessonSession,
    lesson: Lesson,
    user: User,
    target_module: str,
    meta: dict,
    db: Session,
) -> SwitchModuleResponse:
    """Perform the actual module switch and generate the intro message."""
    current = meta.get("active_module", _INITIAL_MODULE)

    # QA mode: remember where to return
    if target_module == "qa":
        meta["qa_return_module"] = current

    meta["active_module"] = target_module
    history = meta.get("module_history", [])
    if target_module not in history:
        history.append(target_module)
    meta["module_history"] = history

    module = _MODULES[target_module]
    module_state = meta["modules"].get(target_module, module.initial_state())

    # Generate the module's opening/intro message
    system = module.build_system_prompt(lesson, user, module_state)
    opening_prompt = module.build_opening(lesson, user)
    messages = [{"role": "user", "content": opening_prompt}]

    switch_choices: list[str] = []
    if target_module == "conversation":
        text, switch_choices = await _call_conversation_module(system, messages)
    else:
        raw = await llm_router.route("lesson", system, messages)
        text = raw.strip()

    # Append module switch marker + AI intro to history
    updated_history = list(session.content_json or [])
    updated_history.append({"role": "assistant", "content": text, "module": target_module})

    module_state["turns"] = module_state.get("turns", 0) + 1
    meta["modules"][target_module] = module_state
    session.content_json = updated_history
    session.session_meta = meta
    flag_modified(session, "session_meta")
    db.commit()

    tokens = _tokenize_lesson_text(text, session.user_id, db)

    return SwitchModuleResponse(
        session_id=session.id,
        text=text,
        tokens=tokens,
        session_meta=SessionMetaOut(**session.session_meta),
        choices=switch_choices,
    )


async def _call_conversation_module(system: str, messages: list[dict]) -> tuple[str, list[str]]:
    """
    Call LLM for conversation module. Expects JSON {story_text, choices}.
    Returns (story_text, choices). Falls back gracefully on parse failure.
    """
    raw = await llm_router.route("lesson", system, messages)
    try:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        data = json.loads(cleaned)
        story_text = data.get("story_text", "").strip()
        choices = data.get("choices", [])
        if story_text:
            return story_text, choices
    except Exception:
        pass
    return raw.strip(), []


def _tokenize_lesson_text(text: str, user_id: int, db: Session) -> list[TokenOut]:
    """
    Tokenize the lesson response. Non-Japanese text tokenizes as individual
    surface tokens — the frontend decides how to render them.
    """
    tokens = tokenize(text)
    annotated = _annotate_with_vocab_status(tokens, user_id, db)
    return [
        TokenOut(
            surface=t.surface,
            reading=t.reading,
            pos=t.pos,
            is_content=t.is_content,
            status=t.status,
            vocab_id=t.vocab_id,
        )
        for t in annotated
    ]


def _is_return_signal(text: str) -> bool:
    """Return True if the user wants to go back to their lesson after QA."""
    lower = text.strip().lower()
    return lower in {"back", "continue", "戻る", "続ける", "はい", "ok", "okay"}


async def _generate_lesson_coach_note(
    grammar_point: str,
    stats: dict,
    errors_log: list[dict],
    native_lang: str = "en",
    model_override: str | None = None,
) -> str:
    lang_name = _LANG_NAMES.get(native_lang, "English")
    total_errors = sum(stats.get("errors_by_type", {}).values())
    modules_done = stats.get("modules_completed", [])

    system = (
        f"LANGUAGE: Write ONLY in {lang_name}. You are an encouraging Japanese language coach.\n"
        f"Write a short (2–4 sentence) personalised coach note for the learner "
        f"based on their grammar lesson session. Be specific, positive, and actionable. "
        f"Output only the coach note text — no headers, no bullet points."
    )
    prompt = (
        f"Lesson: {grammar_point}\n"
        f"Modules completed: {', '.join(modules_done) if modules_done else 'none'}\n"
        f"Total turns: {stats.get('turns', 0)}\n"
        f"Errors found: {total_errors}\n"
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        note = await llm_router.route("coach_note", system, messages, model_override=model_override)
        return note.strip()
    except Exception:
        return f"Great work studying {grammar_point} today! Keep practicing and it'll become second nature."
