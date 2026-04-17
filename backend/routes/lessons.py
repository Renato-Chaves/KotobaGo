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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.error_analyzer import analyze_errors as _run_error_analysis
from core.llm import router as llm_router
from core.streaming import stream_json
from core.modules import conversation, examples, presentation, qa, recognition
from core.romaji import convert_to_japanese, is_romaji_heavy
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
    progress_status: str = "available"       # completed | active | available | locked
    active_session_id: int | None = None


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
async def list_lessons(
    user_id: int = Query(default=1),
    db: Session = Depends(get_db),
):
    """List all lessons ordered by stage and position within stage, with per-user progress."""
    lessons = db.query(Lesson).order_by(Lesson.stage, Lesson.order).all()

    # Fetch all sessions for this user to compute per-lesson progress
    sessions = (
        db.query(LessonSession)
        .filter(LessonSession.user_id == user_id)
        .all()
    )
    # Group sessions by lesson_id
    sessions_by_lesson: dict[int, list[LessonSession]] = {}
    for s in sessions:
        sessions_by_lesson.setdefault(s.lesson_id, []).append(s)

    # Track which lessons have been completed to determine locked/available
    completed_ids: set[int] = set()
    for lid, sess_list in sessions_by_lesson.items():
        if any(s.status == "completed" for s in sess_list):
            completed_ids.add(lid)

    result: list[LessonOut] = []
    prev_available = True  # first lesson is always available

    for l in lessons:
        sess_list = sessions_by_lesson.get(l.id, [])
        has_completed = any(s.status == "completed" for s in sess_list)
        active_sessions = [s for s in sess_list if s.status == "active"]

        if has_completed:
            status = "completed"
        elif active_sessions:
            status = "active"
        elif prev_available:
            status = "available"
        else:
            status = "locked"

        # Most recent active session id (for "Continue" button)
        active_sid = max((s.id for s in active_sessions), default=None) if active_sessions else None

        # A lesson is "available" for the next one if it's completed or available
        prev_available = status in ("completed", "available", "active")

        result.append(LessonOut(
            id=l.id,
            title=l.title,
            jlpt_level=l.jlpt_level,
            grammar_point=l.grammar_point,
            category=getattr(l, "category", "grammar") or "grammar",
            stage=l.stage,
            order=l.order,
            content_json=l.content_json,
            progress_status=status,
            active_session_id=active_sid,
        ))

    return result


# ---------------------------------------------------------------------------
# POST /lessons/import-url — extract lesson structure from a URL or pasted text
# ---------------------------------------------------------------------------

class ImportRequest(BaseModel):
    url: str | None = None
    text: str | None = None    # raw pasted text (used when url is None)


class ImportedExample(BaseModel):
    id: str
    japanese: str
    reading: str
    translation: str


class ImportedSentence(BaseModel):
    id: str
    japanese: str
    reading: str
    translation: str


class ImportPreview(BaseModel):
    title: str
    grammar_point: str
    jlpt_level: str
    category: str
    source_language: str
    explanation: str
    examples: list[ImportedExample]
    sentences: list[ImportedSentence]


@router.post("/import-url", response_model=ImportPreview)
async def import_url(req: ImportRequest):
    """
    Fetch a URL (or accept pasted text), send the content to an LLM, and
    return a structured lesson preview the user can review and edit before saving.
    """
    if not req.url and not req.text:
        raise HTTPException(status_code=400, detail="Provide a URL or pasted text")

    raw_text = req.text or ""

    if req.url:
        import httpx
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                resp = await client.get(req.url)
                resp.raise_for_status()
                raw_text = resp.text
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}")

    # Strip HTML tags for a rough plain-text extraction
    import re as _re
    plain = _re.sub(r"<[^>]+>", " ", raw_text)
    plain = _re.sub(r"\s+", " ", plain).strip()
    # Limit to ~6000 chars to fit in context
    plain = plain[:6000]

    system = (
        "You are a Japanese lesson extractor. Given raw text from a grammar resource page, "
        "extract a structured JSON lesson.\n\n"
        "OUTPUT: Respond ONLY with a single JSON object — no text before or after.\n\n"
        "JSON SCHEMA:\n"
        "{\n"
        '  "title": "short descriptive title in English",\n'
        '  "grammar_point": "grammar pattern (e.g. N1のN2, V-てform)",\n'
        '  "jlpt_level": "N5|N4|N3|N2|N1",\n'
        '  "category": "grammar|vocabulary|conversation",\n'
        '  "source_language": "en",\n'
        '  "explanation": "clear explanation of the grammar point for a beginner, 2-4 sentences",\n'
        '  "examples": [\n'
        '    {"id": "ex_1", "japanese": "...", "reading": "hiragana reading", "translation": "English translation"},\n'
        '    ... (3-5 examples)\n'
        '  ],\n'
        '  "sentences": [\n'
        '    {"id": "s_1", "japanese": "...", "reading": "hiragana reading", "translation": "English translation"},\n'
        '    ... (3-5 practice sentences)\n'
        '  ]\n'
        "}\n\n"
        "RULES:\n"
        "- Extract ONLY from the provided text. Do not invent content.\n"
        "- If the text doesn't contain enough examples, generate simple ones that match the pattern.\n"
        "- Use hiragana for readings. Use simple vocabulary appropriate to the JLPT level.\n"
        "- Each example id must be unique (ex_1, ex_2, ...). Each sentence id must be unique (s_1, s_2, ...).\n"
        "- Keep explanations beginner-friendly."
    )
    messages = [{"role": "user", "content": f"Extract a lesson from this content:\n\n{plain}"}]

    raw_response = await llm_router.route("lesson", system, messages)

    # Parse JSON from response
    try:
        cleaned = _re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_response.strip(), flags=_re.MULTILINE)
        data = json.loads(cleaned)
    except Exception:
        raise HTTPException(status_code=502, detail="LLM returned invalid JSON. Try again or paste the text manually.")

    # Validate and normalise
    try:
        return ImportPreview(
            title=data.get("title", "Untitled Lesson"),
            grammar_point=data.get("grammar_point", ""),
            jlpt_level=data.get("jlpt_level", "N5"),
            category=data.get("category", "grammar"),
            source_language=data.get("source_language", "en"),
            explanation=data.get("explanation", ""),
            examples=[ImportedExample(**ex) for ex in data.get("examples", [])],
            sentences=[ImportedSentence(**s) for s in data.get("sentences", [])],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM output didn't match expected shape: {exc}")


# ---------------------------------------------------------------------------
# POST /lessons — create a new lesson
# ---------------------------------------------------------------------------

class CreateLessonRequest(BaseModel):
    title: str
    grammar_point: str | None = None
    jlpt_level: str = "N5"
    category: str = "grammar"
    source_language: str = "en"
    explanation: str
    examples: list[ImportedExample]
    sentences: list[ImportedSentence]


class CreateLessonResponse(BaseModel):
    id: int
    title: str


@router.post("", response_model=CreateLessonResponse)
async def create_lesson(req: CreateLessonRequest, db: Session = Depends(get_db)):
    """Save a new lesson to the database."""
    # Determine stage and order: place after all existing lessons in this category
    last = (
        db.query(Lesson)
        .filter(Lesson.category == req.category)
        .order_by(Lesson.stage.desc(), Lesson.order.desc())
        .first()
    )
    if last:
        stage = last.stage
        order = last.order + 1
    else:
        stage = 1
        order = 1

    content_json = {
        "grammar_point": req.grammar_point or "",
        "source_language": req.source_language,
        "explanation": req.explanation,
        "examples": [ex.model_dump() for ex in req.examples],
        "sentences": [s.model_dump() for s in req.sentences],
    }

    lesson = Lesson(
        title=req.title,
        jlpt_level=req.jlpt_level,
        grammar_point=req.grammar_point,
        category=req.category,
        source_language=req.source_language,
        stage=stage,
        order=order,
        content_md="",
        content_json=content_json,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)

    return CreateLessonResponse(id=lesson.id, title=lesson.title)


# ---------------------------------------------------------------------------
# POST /lessons/{id}/start
# ---------------------------------------------------------------------------

@router.post("/{lesson_id}/start")
async def start_lesson(
    lesson_id: int,
    req: StartRequest,
    db: Session = Depends(get_db),
):
    """
    Start a lesson session. Creates LessonSession, enters the Presentation module,
    and returns the AI's opening explanation.
    Streams heartbeat newlines while the LLM is working to keep the
    TCP connection alive for slow local models.
    """
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    get_user_or_404(req.user_id, db)  # validate before streaming starts

    async def work() -> dict:
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

        tokens = _tokenize_lesson_text(text, req.user_id, db, lesson=lesson)

        return StartResponse(
            session_id=session.id,
            lesson_id=lesson_id,
            text=text,
            tokens=tokens,
            session_meta=SessionMetaOut(**session.session_meta),
            choices=[],
        ).model_dump()

    return await stream_json(work())


# ---------------------------------------------------------------------------
# POST /lessons/session/{id}/continue
# ---------------------------------------------------------------------------

@router.post("/session/{session_id}/continue")
async def continue_lesson(
    session_id: int,
    req: ContinueRequest,
    db: Session = Depends(get_db),
):
    """
    Continue the current lesson module with the user's input.
    Routes to the active module's system prompt, calls LLM, returns response.
    Streams heartbeat newlines while the LLM is working to keep the
    TCP connection alive for slow local models.
    """
    # Fast validation — can raise HTTPException with proper status codes
    session, lesson, user = _load_session_context(session_id, req.user_id, db)
    meta = dict(session.session_meta or {})
    active = meta.get("active_module", _INITIAL_MODULE)
    if active not in _MODULES:
        raise HTTPException(status_code=400, detail=f"Unknown module: {active}")

    async def work() -> dict:
        nonlocal meta, active
        module = _MODULES[active]
        module_state = meta["modules"].get(active, {})
        system = module.build_system_prompt(lesson, user, module_state)

        # Determine if this is a "return" signal in QA mode
        is_return = _is_return_signal(req.user_input)
        if active == "qa" and is_return and meta.get("qa_return_module"):
            return_to = meta["qa_return_module"]
            meta["qa_return_module"] = None
            meta["active_module"] = return_to
            session.session_meta = meta
            flag_modified(session, "session_meta")
            db.commit()
            result = await _do_switch(session, lesson, user, return_to, meta, db)
            d = result.model_dump()
            d.setdefault("stage_complete", False)
            return d

        # Convert romaji input to Japanese for recognition/conversation modules
        user_input = req.user_input
        if active in ("recognition", "conversation") and is_romaji_heavy(user_input):
            converted = await convert_to_japanese(user_input)
            if converted != user_input:
                user_input = converted

        # Build messages: full history + user turn
        history = list(session.content_json or [])
        messages = [*history, {"role": "user", "content": user_input}]

        # For the conversation module, parse JSON response like story builder
        turn_choices: list[str] = []
        if active == "conversation":
            text, turn_choices = await _call_conversation_module(system, messages)
        else:
            raw = await llm_router.route("lesson", system, messages)
            text = raw.strip()

        updated_history = [*history, {"role": "user", "content": user_input}, {"role": "assistant", "content": text}]
        session.content_json = updated_history

        module_state = meta["modules"].setdefault(active, {})
        module_state["turns"] = module_state.get("turns", 0) + 1

        if active == "examples":
            next_id = examples.next_unseen_id(lesson, module_state)
            if next_id:
                module_state.setdefault("seen_ids", []).append(next_id)

        stage_complete = module.should_advance(module_state)

        meta["modules"][active] = module_state
        session.session_meta = meta
        flag_modified(session, "session_meta")
        db.commit()

        tokens = _tokenize_lesson_text(text, req.user_id, db, lesson=lesson)

        return ContinueResponse(
            session_id=session.id,
            text=text,
            tokens=tokens,
            session_meta=SessionMetaOut(**session.session_meta),
            stage_complete=stage_complete,
            choices=turn_choices,
        ).model_dump()

    return await stream_json(work())


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

    tokens = _tokenize_lesson_text(text, session.user_id, db, lesson=lesson)

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


def _tokenize_lesson_text(
    text: str,
    user_id: int,
    db: Session,
    lesson: Lesson | None = None,
) -> list[TokenOut]:
    """
    Tokenize the lesson response. Non-Japanese text tokenizes as individual
    surface tokens — the frontend decides how to render them.

    When a lesson is provided, a second annotation pass marks tokens that match
    the grammar target (e.g. the の particle) as ``lesson_example``.
    """
    tokens = tokenize(text)
    annotated = _annotate_with_vocab_status(tokens, user_id, db)

    # Second pass: mark grammar target tokens as lesson_example
    if lesson:
        annotated = _annotate_lesson_targets(annotated, lesson)

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


def _annotate_lesson_targets(tokens: list, lesson: Lesson) -> list:
    """
    Mark tokens that match the lesson's grammar target as ``lesson_example``.

    For particle-based lessons (e.g. N1のN2), marks every occurrence of the
    target particle. For other grammar points, does a surface match against
    the grammar_point string.
    """
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or ""
    if not grammar_point:
        return tokens

    # Extract the core particle/token to highlight
    # Common patterns: "N1のN2" → highlight "の", "V-てform" → highlight "て"
    target_surfaces: set[str] = set()

    # For NxのNy style patterns, extract the particle
    import re as _re
    particle_match = _re.search(r"[NVA]\d?(.{1,3})[NVA]\d?", grammar_point)
    if particle_match:
        target_surfaces.add(particle_match.group(1))

    # Also try direct match against the whole grammar_point for simpler cases
    if not target_surfaces:
        target_surfaces.add(grammar_point)

    for token in tokens:
        if token.surface in target_surfaces:
            token.status = "lesson_example"

    return tokens


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
