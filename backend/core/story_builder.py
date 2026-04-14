"""
Story prompt construction and vocab budget validation.

The system prompt is the main lever for keeping the LLM within the user's
vocabulary level. This module builds that prompt and validates the output.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from core.tokenizer import Token, tokenize
from db.models import User, UserVocab, Vocab


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class StorySegment:
    """A validated, annotated story segment ready to send to the frontend."""
    story_text: str
    choices: list[str]
    tokens: list[Token]
    new_word_count: int
    total_content_words: int


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

# How many recent messages to pass to the LLM — older turns are archived in DB
# but dropped from the context window to preserve quality. 8 messages = 4 turns.
_MAX_HISTORY_MESSAGES = 8


_STORY_LENGTH_MAP = {
    "tiny":   "1–2 sentences",
    "short":  "3–5 sentences",
    "medium": "5–8 sentences",
    "long":   "8–12 sentences",
}


def build_system_prompt(
    user: User,
    confident_vocab: set[str],
    fragile_vocab: set[str],
    new_word_pct: int,
    story_brief: dict | None = None,
    due_vocab: list[str] | None = None,
    story_length: str = "medium",
) -> str:
    """
    Build the system prompt for story generation.

    Args:
        user:            The User ORM object (has language, level, ai_context).
        confident_vocab: Words the user has practiced/mastered — use freely.
        fragile_vocab:   Words introduced but not yet rated — use sparingly.
        new_word_pct:    Target percentage of new words (0–100).
        story_brief:     Optional narrative anchor dict generated at story start.
        due_vocab:       Words due for SM-2 review — include at least one naturally.
        story_length:    Segment length: "short" (3–5), "medium" (5–8), "long" (8–12).
    """
    # Cap each tier to keep token cost manageable
    confident_block = ", ".join(list(confident_vocab)[:150]) if confident_vocab else "none yet"
    fragile_block = ", ".join(list(fragile_vocab)[:80]) if fragile_vocab else "none"

    brief_block = ""
    if story_brief:
        brief_block = (
            "STORY CONTEXT (keep consistent throughout):\n"
            + json.dumps(story_brief, ensure_ascii=False)
            + "\n\n"
        )

    review_block = ""
    if due_vocab:
        review_block = (
            f"\nREVIEW: Naturally include at least one of these words in this segment "
            f"(they are due for spaced repetition): {', '.join(due_vocab)}\n"
            f"Do not introduce them as new — use them as if the learner already knows them.\n"
        )

    ai_context_text = user.ai_context or f"Japanese learner at {user.jlpt_goal} level."
    length_str = _STORY_LENGTH_MAP.get(story_length, _STORY_LENGTH_MAP["medium"])

    return f"""LANGUAGE: Write ALL story content and ALL choices in Japanese only. No English. No romaji. No mixed language.
OUTPUT: Respond ONLY with a JSON object — no text before or after it.

{brief_block}You are an interactive Japanese story tutor. Generate engaging segments calibrated to the learner's level.

LEARNER: {ai_context_text} | Native: {user.native_language} | Level: {user.jlpt_goal}
Draw settings and characters from the learner's stated interests to make the story feel personal.

VOCAB:
- Confident words (learner knows these well — use freely): {confident_block}
- Fragile words (seen once, not yet rated — use at most once per segment, treat as known not new): {fragile_block}
- Introduce ~{new_word_pct}% words from outside both lists above; make them guessable from context.
- No furigana — added separately.
{review_block}
STORY RULES:
- Second person: あなた is always the protagonist.
- Each continuation: advance the story to the NEXT beat — never repeat or restate what already happened.
- End each segment at the exact moment of decision — someone waiting for your reply, a choice in the next breath.
- {length_str}. Develop the scene before the decision point.
- Choices: specific Japanese dialogue phrases (「...」). Not action descriptions.
- Choices differ in register, strategy, or character — not just politeness.
- Use emotional expressions naturally (ドキドキ、ほっとした…). Stay in the story world; never explain grammar.
- Supporting characters: Japanese names only (さくら、たろう…).

JSON FORMAT:
{{"story_text": "{length_str} in Japanese", "choices": ["「...」", "「...」", "「...」"]}}"""


async def build_continuation_prompt(
    system_prompt: str,
    history: list[dict],
    user_input: str,
    difficulty_hint: str | None = None,
    existing_summary: str | None = None,
    model_override: str | None = None,
) -> tuple[str, list[dict], str | None]:
    """
    Prepare the system prompt and message history for a story continuation.

    When history exceeds _MAX_HISTORY_MESSAGES, the oldest turns are compressed
    into a narrative summary before being dropped, so long sessions stay coherent.

    Returns:
        (adjusted_system, messages, new_summary_or_none)
        new_summary_or_none is set when a new compression was performed — caller
        should persist it to session_meta["story_summary"].
    """
    adjusted_system = system_prompt
    if difficulty_hint:
        adjusted_system += f"\nDIFFICULTY FOR THIS TURN: {difficulty_hint}"

    new_summary: str | None = None

    if len(history) > _MAX_HISTORY_MESSAGES:
        # Turns to be dropped from the live window
        to_drop = history[:-_MAX_HISTORY_MESSAGES]
        recent = history[-_MAX_HISTORY_MESSAGES:]

        # Compress: combine existing summary with newly dropped turns
        summary = await _compress_turns(
            to_drop=to_drop,
            existing_summary=existing_summary,
            model_override=model_override,
        )
        new_summary = summary

        # Inject compressed summary as the first message in the window
        summary_msg = {"role": "assistant", "content": f"[これまでのストーリー: {summary}]"}
        messages = [summary_msg, *recent, {"role": "user", "content": user_input}]
    else:
        messages = [*history, {"role": "user", "content": user_input}]

    return adjusted_system, messages, new_summary


async def _compress_turns(
    to_drop: list[dict],
    existing_summary: str | None,
    model_override: str | None = None,
) -> str:
    """
    Summarise dropped story turns (plus any prior summary) into 1–2 sentences
    of plain Japanese narrative. Cached result avoids re-compressing old turns.
    """
    from core.llm import router as llm_router

    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in to_drop)

    if existing_summary:
        content = (
            f"Previous summary: {existing_summary}\n\n"
            f"New story turns to add to the summary:\n{history_text}"
        )
    else:
        content = history_text

    system = (
        "You are a story summariser. Summarise the following Japanese story excerpt in 1–2 sentences "
        "of plain Japanese narrative (no dialogue, no choices). "
        "Focus on: where the protagonist is, what just happened, and who they met. "
        "Output only the summary — no extra text."
    )
    messages = [{"role": "user", "content": content}]

    try:
        result = await llm_router.route(
            "context_compression", system, messages, model_override=model_override
        )
        return result.strip() or (existing_summary or "")
    except Exception:
        return existing_summary or ""


async def generate_story_brief(
    theme: str | None,
    user: User,
    model_override: str | None = None,
) -> dict:
    """
    Generate a short narrative anchor JSON at story start.
    The brief is prepended to every system prompt to keep the LLM coherent across turns.
    """
    from core.llm import router as llm_router

    ai_context_text = user.ai_context or "Japanese learner interested in everyday life."
    theme_hint = f"Story theme: {theme}." if theme else "No specific theme — pick something interesting."

    system = (
        "You are a creative writing assistant. Generate a brief JSON narrative anchor for an interactive Japanese story. "
        "Output ONLY valid JSON with these exact keys: setting, protagonist_situation, atmosphere, key_characters (array of 1-3 SUPPORTING character names only — never name the protagonist), arc. "
        "CRITICAL: The protagonist is always the reader ('you'/'あなた'). Never name them. "
        "protagonist_situation must use second person: 'You are...' not 'Ryosuke is...'. "
        "No markdown, no extra text. Keep each value to one sentence."
    )
    prompt = (
        f"Learner interests: {ai_context_text}\n"
        f"{theme_hint}\n\n"
        "Create a story brief that reflects the learner's interests and makes the story feel personally relevant. "
        "The protagonist_situation should describe what YOU (the reader) are doing, in second person."
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        raw = await llm_router.route("story", system, messages, model_override=model_override)
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        brief = json.loads(cleaned)
        return brief
    except Exception:
        return {
            "setting": theme or "Everyday life in Japan",
            "protagonist_situation": "You are about to begin an adventure",
            "atmosphere": "Warm and inviting",
            "key_characters": [],
            "arc": "Small choices that reveal who you are",
        }


# ---------------------------------------------------------------------------
# Vocab budget validation
# ---------------------------------------------------------------------------

def validate_vocab_budget(
    story_text: str,
    known_surfaces: set[str],
    target_pct: int,
) -> tuple[bool, list[Token], int, int]:
    """
    Check whether the generated story respects the vocabulary budget.

    known_surfaces should be the union of confident + fragile vocab — both
    tiers count as "known" for budget purposes.

    Returns:
        (within_budget, tokens, new_word_count, total_content_words)
    """
    tokens = tokenize(story_text)
    content_tokens = [t for t in tokens if t.is_content]
    total = len(content_tokens)

    if total == 0:
        return True, tokens, 0, 0

    new_words = [t for t in content_tokens if t.surface not in known_surfaces]
    new_count = len(new_words)
    actual_pct = (new_count / total) * 100

    within_budget = actual_pct <= target_pct * 1.5  # 50% tolerance before retry
    return within_budget, tokens, new_count, total


def parse_llm_response(raw: str) -> tuple[str, list[str]]:
    """
    Extract story_text and choices from the LLM's JSON response.

    Handles cases where the LLM wraps the JSON in markdown code fences.
    Raises ValueError if the response cannot be parsed.
    """
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response is not valid JSON: {e}\nRaw: {raw[:200]}")

    story_text = data.get("story_text", "").strip()
    choices = data.get("choices", [])

    if not story_text:
        raise ValueError("LLM response missing 'story_text'")
    if not choices or len(choices) < 2:
        raise ValueError("LLM response must include at least 2 choices")

    # Ensure every choice contains at least one Japanese character
    _jp_re = re.compile(r"[\u3040-\u9fff]")
    sanitized = []
    for choice in choices:
        sanitized.append(choice if _jp_re.search(choice) else "「はい、わかりました。」")

    return story_text, sanitized


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_vocab_tiers(user_id: int, db: Session) -> tuple[set[str], set[str]]:
    """
    Return (confident, fragile) word surface sets.

    confident: practiced + mastered — LLM should use these freely.
    fragile:   introduced (seen once, not yet rated) — LLM should use sparingly.

    Both tiers are treated as "known" for vocab budget validation.
    """
    rows = (
        db.query(Vocab.word, UserVocab.status)
        .join(UserVocab, UserVocab.vocab_id == Vocab.id)
        .filter(UserVocab.user_id == user_id)
        .all()
    )
    confident: set[str] = set()
    fragile: set[str] = set()
    for word, status in rows:
        if status in ("practiced", "mastered"):
            confident.add(word)
        else:
            fragile.add(word)
    return confident, fragile


def get_due_vocab(user_id: int, db: Session, limit: int = 3) -> list[str]:
    """
    Return surfaces of words due for SM-2 review (next_review <= now, not mastered).
    Limited to `limit` words to avoid overloading the story with review targets.
    """
    rows = (
        db.query(Vocab.word)
        .join(UserVocab, UserVocab.vocab_id == Vocab.id)
        .filter(
            UserVocab.user_id == user_id,
            UserVocab.next_review <= datetime.utcnow(),
            UserVocab.status != "mastered",
        )
        .limit(limit)
        .all()
    )
    return [r.word for r in rows]


def get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user
