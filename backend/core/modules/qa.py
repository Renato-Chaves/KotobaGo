"""
QA module — handles meta-questions about the grammar point or Japanese in general.

The learner can ask a question at any time. The QA module answers it and then
returns to whatever module was active before (qa_return_module).

This module has no persistent state — qa_return_module in session_meta is
the only state needed, and it's owned by the route layer.

State shape:
  { "turns": 0 }
"""

from db.models import Lesson, User

_LANG_NAMES = {"pt": "Portuguese", "en": "English", "es": "Spanish", "fr": "French"}


def build_system_prompt(lesson: Lesson, user: User, module_state: dict) -> str:
    lang = user.native_language or "en"
    lang_name = _LANG_NAMES.get(lang, "English")
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or lesson.title
    explanation_notes = content.get("explanation", "")

    return (
        f"LANGUAGE: Answer in {lang_name}. Use Japanese only for example sentences.\n\n"
        f"You are a knowledgeable Japanese language tutor. "
        f"The learner is currently studying the grammar point: {grammar_point}.\n\n"
        f"Context about this grammar point: {explanation_notes}\n\n"
        f"RULES:\n"
        f"- Answer the learner's question clearly and concisely in {lang_name}.\n"
        f"- Use Japanese examples only when they directly illustrate your answer.\n"
        f"- After answering, let the learner know they can ask another question "
        f"or say 'back' / 'continue' to return to the lesson.\n"
        f"- Keep answers to 3–5 sentences.\n"
        f"- Output only your answer — no headers."
    )


def build_opening(lesson: Lesson, user: User) -> str:
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or lesson.title
    return (
        f"[System: QA mode activated for '{grammar_point}'. "
        f"Answer the learner's question, then return to the lesson.]"
    )


def initial_state() -> dict:
    return {"turns": 0}


def should_advance(module_state: dict) -> bool:
    return False  # QA module never auto-advances; route handles return explicitly
