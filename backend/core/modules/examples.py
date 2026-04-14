"""
Examples module — presents authored examples one at a time and generates new ones on demand.

Authored examples are shown first (tracked in seen_ids). Once exhausted (or on
"give me more" request), the AI generates fresh examples following the same pattern.

State shape:
  { "seen_ids": [], "turns": 0 }
"""

from db.models import Lesson, User

_LANG_NAMES = {"pt": "Portuguese", "en": "English", "es": "Spanish", "fr": "French"}


def build_system_prompt(lesson: Lesson, user: User, module_state: dict) -> str:
    lang = user.native_language or "en"
    lang_name = _LANG_NAMES.get(lang, "English")
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or lesson.title
    all_examples = content.get("examples", [])
    seen_ids = set(module_state.get("seen_ids", []))

    unseen = [ex for ex in all_examples if ex["id"] not in seen_ids]
    seen = [ex for ex in all_examples if ex["id"] in seen_ids]

    ai_context = user.ai_context or ""

    if unseen:
        next_ex = unseen[0]
        examples_block = (
            f"Present this example next:\n"
            f"  Japanese: {next_ex['japanese']}\n"
            f"  Reading: {next_ex.get('reading', next_ex['japanese'])}\n"
            f"  Translation: {next_ex.get('translation', '')}\n\n"
            f"Already shown examples (do NOT repeat): "
            + ", ".join(ex["japanese"] for ex in seen)
        )
        exhausted = False
    else:
        examples_block = (
            f"All authored examples have been shown. Generate a NEW original example "
            f"following the same pattern as: {grammar_point}.\n"
            f"Learner's interests (for personalised examples): {ai_context}\n"
            f"Already shown: {', '.join(ex['japanese'] for ex in all_examples)}\n"
            f"Do NOT repeat any already-shown example."
        )
        exhausted = True

    return (
        f"LANGUAGE: Use {lang_name} for explanations and translations. "
        f"Japanese for the example itself.\n\n"
        f"You are teaching the grammar point: {grammar_point}.\n\n"
        f"{examples_block}\n\n"
        f"RULES:\n"
        f"- Present one example at a time.\n"
        f"- Show the Japanese, then the reading in hiragana (in parentheses if different), then the {lang_name} translation.\n"
        f"- Add one sentence of explanation about WHY this example illustrates the grammar point.\n"
        f"- End by asking if they want another example or are ready for practice.\n"
        + ("- Since all authored examples are shown, generate a creative new one using the learner's interests.\n" if exhausted else "")
        + "- Output only the example presentation — no headers."
    )


def build_opening(lesson: Lesson, user: User) -> str:
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or lesson.title
    return (
        f"[System: Starting Examples module for '{grammar_point}'. "
        f"Present the first example.]"
    )


def initial_state() -> dict:
    return {"seen_ids": [], "turns": 0}


def next_unseen_id(lesson: Lesson, module_state: dict) -> str | None:
    """Return the id of the next unseen example, or None if all shown."""
    content = lesson.content_json or {}
    all_examples = content.get("examples", [])
    seen_ids = set(module_state.get("seen_ids", []))
    for ex in all_examples:
        if ex["id"] not in seen_ids:
            return ex["id"]
    return None


def should_advance(module_state: dict) -> bool:
    return module_state.get("turns", 0) >= 5
