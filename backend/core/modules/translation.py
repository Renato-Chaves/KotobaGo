"""
Translation module — strict-match translation drill.

Walks a deterministic pool of authored items (examples + sentences, deduped,
capped at POOL_CAP) and alternates direction per item: JP→NL on even indices,
NL→JP on odd indices.

DESIGN: This module deliberately does NOT call the LLM. Both the "ask" (present
the prompt) and "grade" (judge the answer) phases are pure templates / pure
Python comparisons. On a local qwen2.5:7b backend, LLM grading is unreliable
and LLM Japanese generation hallucinates readings — so we lean on authored
content for everything.

The only LLM path for this module is the explicit user-triggered tiebreak
endpoint in routes/lessons.py, which handles the "I think mine is also right"
button.

State shape:
  {
    "completed_ids": [],     # items that have been graded
    "turns": 0,
    "current_index": 0,      # index into the pool
    "phase": "ask",          # "ask" | "grade"
    "last_grade_result": None,  # "accept" | "close" | "wrong" — for the most recent grade
    "last_item_id": None,    # id of the most recently graded item
  }
"""

import re
from difflib import SequenceMatcher

from core.romaji import convert_to_japanese, is_romaji_heavy
from db.models import Lesson, User

POOL_CAP = 6

_LANG_NAMES = {"pt": "Portuguese", "en": "English", "es": "Spanish", "fr": "French"}

# ---------------------------------------------------------------------------
# Localised UI strings
# ---------------------------------------------------------------------------

# Kept tiny on purpose — extend as needed. Fall back to English.
_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "translate_to_jp": "Translate to Japanese:",
        "translate_to_nl": "Translate to English:",
        "accept":          "✓ Correct!",
        "close":           "Close — the expected answer was:",
        "wrong":           "Not quite. The answer is:",
        "stage_complete":  "🎉 Translation drill complete! You can move on, or revisit any stage.",
        "next_prompt":     "Next:",
    },
    "pt": {
        "translate_to_jp": "Traduza para o japonês:",
        "translate_to_nl": "Traduza para o português:",
        "accept":          "✓ Correto!",
        "close":           "Quase — a resposta esperada era:",
        "wrong":           "Não é bem isso. A resposta é:",
        "stage_complete":  "🎉 Treino de tradução completo! Você pode seguir em frente ou revisitar qualquer etapa.",
        "next_prompt":     "Próxima:",
    },
}


def _s(lang: str, key: str) -> str:
    return _STRINGS.get(lang, _STRINGS["en"]).get(key, _STRINGS["en"][key])


# ---------------------------------------------------------------------------
# Pool building + direction
# ---------------------------------------------------------------------------

def build_pool(lesson: Lesson) -> list[dict]:
    """
    Deterministic pool: examples first, then sentences, deduped by Japanese
    surface, capped at POOL_CAP. Order is stable across calls for the same
    lesson, so direction_for_index() stays consistent.
    """
    content = lesson.content_json or {}
    examples = content.get("examples", []) or []
    sentences = content.get("sentences", []) or []

    seen: set[str] = set()
    pool: list[dict] = []
    for item in [*examples, *sentences]:
        jp = (item.get("japanese") or "").strip()
        if not jp or jp in seen:
            continue
        seen.add(jp)
        pool.append(item)
        if len(pool) >= POOL_CAP:
            break
    return pool


def direction_for_index(idx: int) -> str:
    """Even indices → JP→NL, odd → NL→JP. First item is always JP→NL (easier)."""
    return "jp_to_nl" if idx % 2 == 0 else "nl_to_jp"


# ---------------------------------------------------------------------------
# Normalisation + scoring
# ---------------------------------------------------------------------------

_NL_PUNCT_RE = re.compile(r"[.,!?;:\"'()\[\]…—–-]")
_NL_ARTICLES_RE = re.compile(r"\b(the|a|an|os|as|um|uma|uns|umas)\b", re.IGNORECASE)
_JP_PUNCT_RE = re.compile(r"[。、！？\s.,!?…・「」『』（）]")


def _expand_contractions(text: str) -> str:
    # Minimal: just the common ones so "I'm" matches "I am" after normalisation.
    return (text
        .replace("I'm", "I am").replace("i'm", "i am")
        .replace("you're", "you are").replace("You're", "you are")
        .replace("it's", "it is").replace("It's", "it is")
        .replace("don't", "do not").replace("Don't", "do not")
        .replace("isn't", "is not").replace("Isn't", "is not"))


def normalise_nl(text: str) -> str:
    text = _expand_contractions(text).lower().strip()
    text = _NL_PUNCT_RE.sub(" ", text)
    text = _NL_ARTICLES_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalise_jp(text: str) -> str:
    return _JP_PUNCT_RE.sub("", text.strip())


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


async def grade(user_input: str, item: dict, direction: str) -> tuple[str, str]:
    """
    Compare the learner's answer to the authored answer.

    Returns (result, authored_answer) where:
      - result ∈ {"accept", "close", "wrong"}
      - authored_answer is the canonical answer string to show alongside feedback

    For NL→JP direction, romaji input is converted to Japanese before comparison
    (using the same convert_to_japanese helper the recognition/conversation
    modules already use).
    """
    if direction == "jp_to_nl":
        authored = item.get("translation", "")
        norm_user = normalise_nl(user_input)
        norm_authored = normalise_nl(authored)
    else:  # nl_to_jp
        authored = item.get("japanese", "")
        user_text = user_input
        if is_romaji_heavy(user_text):
            user_text = await convert_to_japanese(user_text)
        norm_user = normalise_jp(user_text)
        norm_authored = normalise_jp(authored)

    if not norm_user:
        return "wrong", authored

    if norm_user == norm_authored:
        return "accept", authored

    ratio = _similarity(norm_user, norm_authored)
    if ratio >= 0.85:
        return "accept", authored
    if ratio >= 0.6:
        return "close", authored
    return "wrong", authored


# ---------------------------------------------------------------------------
# Templated message builders (no LLM)
# ---------------------------------------------------------------------------

def _format_ask(item: dict, direction: str, lang: str) -> str:
    if direction == "jp_to_nl":
        return f"{_s(lang, 'translate_to_nl')}\n\n  {item.get('japanese', '')}"
    else:
        return f"{_s(lang, 'translate_to_jp')}\n\n  {item.get('translation', '')}"


def _format_feedback(result: str, authored: str, lang: str) -> str:
    if result == "accept":
        return f"{_s(lang, 'accept')}  {authored}"
    label = _s(lang, "close") if result == "close" else _s(lang, "wrong")
    return f"{label}\n  {authored}"


def build_opening_text(lesson: Lesson, user: User, module_state: dict) -> str:
    """
    Generate the first 'ask' message when the user enters the translation
    module via switch-module. Mutates module_state to set phase="grade" so the
    next continue call grades the learner's reply.
    """
    lang = user.native_language or "en"
    pool = build_pool(lesson)
    if not pool:
        return _s(lang, "stage_complete")

    idx = module_state.get("current_index", 0)
    if idx >= len(pool):
        return _s(lang, "stage_complete")

    item = pool[idx]
    direction = direction_for_index(idx)
    module_state["phase"] = "grade"
    return _format_ask(item, direction, lang)


async def handle_continue(
    lesson: Lesson,
    user: User,
    module_state: dict,
    user_input: str,
) -> str:
    """
    Handle one translation continue() turn. No LLM call.

    Grades the user's reply against the current item, advances state, and
    appends the next ask (or completion message) into the same response.
    Mutates module_state in place.
    """
    lang = user.native_language or "en"
    pool = build_pool(lesson)
    if not pool:
        return _s(lang, "stage_complete")

    phase = module_state.get("phase", "ask")
    idx = module_state.get("current_index", 0)

    # If we're not in grade phase (e.g. user typed something after stage complete),
    # just present the current ask again.
    if phase != "grade" or idx >= len(pool):
        if idx >= len(pool):
            return _s(lang, "stage_complete")
        item = pool[idx]
        direction = direction_for_index(idx)
        module_state["phase"] = "grade"
        return _format_ask(item, direction, lang)

    # Grade phase: judge the current item
    item = pool[idx]
    direction = direction_for_index(idx)
    result, authored = await grade(user_input, item, direction)

    # Record the grade and advance state
    completed = module_state.setdefault("completed_ids", [])
    if item["id"] not in completed:
        completed.append(item["id"])
    module_state["last_grade_result"] = result
    module_state["last_item_id"] = item["id"]
    module_state["current_index"] = idx + 1
    module_state["phase"] = "ask"

    feedback = _format_feedback(result, authored, lang)

    # If pool exhausted, end the drill
    next_idx = idx + 1
    if next_idx >= len(pool):
        module_state["phase"] = "done"
        return f"{feedback}\n\n{_s(lang, 'stage_complete')}"

    # Otherwise present the next ask in the same response
    next_item = pool[next_idx]
    next_direction = direction_for_index(next_idx)
    module_state["phase"] = "grade"  # ready for the next reply
    next_ask = _format_ask(next_item, next_direction, lang)
    return f"{feedback}\n\n{_s(lang, 'next_prompt')}\n{next_ask}"


# ---------------------------------------------------------------------------
# Module interface (matching other modules)
# ---------------------------------------------------------------------------

def build_system_prompt(lesson: Lesson, user: User, module_state: dict) -> str:
    """
    Unused — the translation module is fully templated and bypasses the LLM
    in the continue/switch routes. Returned here only to satisfy the module
    interface that the router calls into; the result is never sent to a model.
    """
    return ""


def build_opening(lesson: Lesson, user: User) -> str:
    """Unused — see build_system_prompt. Route uses build_opening_text directly."""
    return ""


def initial_state() -> dict:
    return {
        "completed_ids": [],
        "turns": 0,
        "current_index": 0,
        "phase": "ask",
        "last_grade_result": None,
        "last_item_id": None,
    }


def should_advance(module_state: dict) -> bool:
    """True once every pool item has been graded."""
    return module_state.get("phase") == "done"
