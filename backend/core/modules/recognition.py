"""
Recognition module — fill-in-blank and is-this-correct exercises.

IMPORTANT: Exercises are generated EXCLUSIVELY from the lesson's authored sentences —
no AI invention. This prevents hallucination on learning material.

Exercise types: fill-in-blank, is-this-correct (pick the valid option).

State shape:
  { "scored_ids": [], "turns": 0 }
"""

import random

from db.models import Lesson, User

_LANG_NAMES = {"pt": "Portuguese", "en": "English", "es": "Spanish", "fr": "French"}


def build_system_prompt(lesson: Lesson, user: User, module_state: dict) -> str:
    lang = user.native_language or "en"
    lang_name = _LANG_NAMES.get(lang, "English")
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or lesson.title
    sentences = content.get("sentences", [])
    scored_ids = set(module_state.get("scored_ids", []))

    unscored = [s for s in sentences if s["id"] not in scored_ids]

    if not unscored:
        # All sentences done — offer a review round
        sentences_block = (
            "All sentences have been practiced! Choose any sentence from the list below "
            "for a review exercise:\n"
            + "\n".join(f"  • {s['japanese']}" for s in sentences)
        )
    else:
        # Pick the next unscored sentence
        target = unscored[0]
        exercise_type = "fill-in-blank" if module_state.get("turns", 0) % 2 == 0 else "is-this-correct"

        if exercise_type == "fill-in-blank":
            sentences_block = (
                f"Create a fill-in-blank exercise from this sentence:\n"
                f"  {target['japanese']}\n"
                f"  Translation: {target.get('translation', '')}\n\n"
                f"Replace the の particle (or the key grammar element) with ___. "
                f"Ask the learner to fill in the blank. "
                f"After they answer, confirm or correct them and show the full sentence."
            )
        else:
            sentences_block = (
                f"Create an is-this-correct exercise from this sentence:\n"
                f"  {target['japanese']}\n"
                f"  Translation: {target.get('translation', '')}\n\n"
                f"Either present it as-is (correct) OR swap の for は or が to make it wrong. "
                f"Ask the learner: 'Is this correct? If not, fix it.' "
                f"After they answer, confirm or correct them."
            )

    return (
        f"LANGUAGE: Use {lang_name} for instructions and feedback. "
        f"Use Japanese for the exercise sentences.\n\n"
        f"You are running a recognition exercise for the grammar point: {grammar_point}.\n\n"
        f"CRITICAL RULE: Only use sentences from the lesson's authored material — "
        f"do NOT invent new sentences. Use ONLY what is provided below.\n\n"
        f"{sentences_block}\n\n"
        f"ROMAJI HANDLING: The learner may answer in romaji (e.g. 'no' instead of 'の'). "
        f"Accept romaji answers and evaluate them as if they were written in kana.\n\n"
        f"RULES:\n"
        f"- Present one exercise at a time.\n"
        f"- Be concise — question, then wait for the answer.\n"
        f"- After the learner answers, give brief feedback in {lang_name} and ask if they want another.\n"
        f"- Never reveal the answer before the learner responds.\n"
        f"- Output only the exercise prompt — no headers."
    )


def build_opening(lesson: Lesson, user: User) -> str:
    content = lesson.content_json or {}
    grammar_point = content.get("grammar_point") or lesson.grammar_point or lesson.title
    return (
        f"[System: Starting Recognition module for '{grammar_point}'. "
        f"Generate the first exercise from the authored sentences.]"
    )


def initial_state() -> dict:
    return {"scored_ids": [], "turns": 0}


def should_advance(module_state: dict) -> bool:
    return module_state.get("turns", 0) >= 4
