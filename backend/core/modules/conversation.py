"""
Conversation module — mini-story constrained to use the target grammar point.

Wraps story_builder-style logic but with a hard grammar constraint injected
into the system prompt. The story is self-contained in the lesson session —
no Story/StorySession DB records are created here.

Export to a real StorySession is handled separately by the export-to-story route.

State shape:
  { "turns": 0, "exported": false }
"""

from db.models import Lesson, User

_LANG_NAMES = {"pt": "Portuguese", "en": "English", "es": "Spanish", "fr": "French"}


def build_system_prompt(lesson: Lesson, user: User, module_state: dict) -> str:
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or lesson.title
    ai_context = user.ai_context or f"Japanese learner at {user.jlpt_goal} level."
    level = user.jlpt_goal or "N5"

    return (
        f"LANGUAGE: Write ALL story content and ALL choices in Japanese only. No English. No romaji.\n"
        f"OUTPUT: Respond ONLY with a JSON object — no text before or after it.\n\n"
        f"You are an interactive Japanese story tutor. "
        f"Generate a short story that naturally and repeatedly uses the grammar point: {grammar_point}.\n\n"
        f"HARD CONSTRAINT: Every assistant turn MUST include at least one natural example of '{grammar_point}'. "
        f"This is the core learning objective — do not skip it.\n\n"
        f"LEARNER: {ai_context} | Level: {level}\n"
        f"Draw settings from the learner's interests.\n\n"
        f"VOCABULARY CONSTRAINT — CRITICAL:\n"
        f"- The learner is at {level} level. ALL Japanese MUST use ONLY {level}-appropriate vocabulary and grammar.\n"
        f"- Use hiragana or very common beginner kanji only (食べ物, 本, 学校, etc.).\n"
        f"- NEVER use advanced kanji or vocab above {level}.\n"
        f"- Keep sentences short: 1–2 short sentences per line.\n"
        f"- Prefer kana over kanji when in doubt.\n\n"
        f"STORY RULES:\n"
        f"- Second person: あなた is always the protagonist.\n"
        f"- Keep each segment to 1–2 short sentences.\n"
        f"- End each turn at a moment of choice or dialogue.\n"
        f"- Choices: specific Japanese dialogue phrases in 「」. At least 2 choices.\n"
        f"- No furigana — added separately.\n\n"
        f"JSON FORMAT:\n"
        f'{{\"story_text\": \"3-5 sentences in Japanese using {grammar_point}\", '
        f'\"choices\": [\"「...」\", \"「...」\"]}}'
    )


def build_opening(lesson: Lesson, user: User) -> str:
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or lesson.title
    return (
        f"[System: Starting Conversation module. "
        f"Generate a mini-story that uses '{grammar_point}' naturally throughout. "
        f"Begin the story now.]"
    )


def initial_state() -> dict:
    return {"turns": 0, "exported": False}


def should_advance(module_state: dict) -> bool:
    return module_state.get("turns", 0) >= 4
