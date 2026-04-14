"""
Presentation module — explains a grammar point conversationally in the user's native language.

The stored lesson explanation is used as author notes / context only; the AI
rewrites it in a natural, conversational tone. Japanese examples are included
inline to illustrate the point.

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
    examples = content.get("examples", [])

    examples_block = ""
    if examples:
        lines = [
            f"  • {ex['japanese']} — {ex.get('translation', '')}"
            for ex in examples[:3]
        ]
        examples_block = "\nInclude these example phrases naturally in your explanation:\n" + "\n".join(lines)

    return (
        f"LANGUAGE: Explain entirely in {lang_name}. Japanese phrases and sentences are fine as examples, "
        f"but all explanations and commentary must be in {lang_name}.\n\n"
        f"You are a friendly, conversational Japanese grammar teacher. "
        f"You are currently teaching the grammar point: {grammar_point}.\n\n"
        f"Author notes (use as context — do NOT copy verbatim): {explanation_notes}\n"
        f"{examples_block}\n\n"
        f"RULES:\n"
        f"- Explain the grammar in a warm, memorable way — use analogies if helpful.\n"
        f"- Show Japanese examples with readings and translations.\n"
        f"- Invite the learner to ask questions or say 'ready' when they want to see more examples.\n"
        f"- Keep each turn to 3–5 sentences. Do not dump all the information at once.\n"
        f"- Output only your explanation — no headers, no bullet points unless formatting examples."
    )


def build_opening(lesson: Lesson, user: User) -> str:
    lang = user.native_language or "en"
    lang_name = _LANG_NAMES.get(lang, "English")
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or lesson.title
    return (
        f"[System: Starting Presentation module for '{grammar_point}'. "
        f"Explain the grammar point in {lang_name}.]"
    )


def initial_state() -> dict:
    return {"turns": 0}


def should_advance(module_state: dict) -> bool:
    """Suggest moving on after 3+ turns — but never force it."""
    return module_state.get("turns", 0) >= 3
