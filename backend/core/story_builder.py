"""
Story prompt construction and vocab budget validation.

The system prompt is the main lever for keeping the LLM within the user's
vocabulary level. This module builds that prompt and validates the output.
"""

import json
import re
from dataclasses import dataclass

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

def build_system_prompt(user: User, session_vocab: list[str], new_word_pct: int) -> str:
    """
    Build the system prompt for story generation.

    Args:
        user:          The User ORM object (has language, level, ai_context).
        session_vocab: List of known word surfaces to pass to the LLM.
        new_word_pct:  Target percentage of new words (0–100).
    """
    vocab_block = ", ".join(session_vocab[:500]) if session_vocab else "none yet"

    return f"""You are an interactive Japanese language tutor. Generate engaging story segments calibrated to the learner's exact level.

LEARNER PROFILE:
{user.ai_context or f"Japanese learner at {user.jlpt_goal} level."}
Native language: {user.native_language}
JLPT level: {user.jlpt_goal}

VOCABULARY RULES:
- The learner knows these words: {vocab_block}
- Introduce approximately {new_word_pct}% new words (words not in the list above)
- New words should be guessable from context — never leave the reader completely lost
- Do NOT include furigana — it is added separately by the tokenizer

STORY RULES:
- Write 3–6 sentences of story text per segment
- End each segment with exactly 2–3 choices for the learner
- Make choices consequential — different grammar forms or politeness levels when appropriate
- Never break the narrative to explain grammar or translate — stay in the story world
- Do not correct the learner's input in-line
- Use Japanese names for all characters (e.g. さくら、たろう) — never English names or placeholders

OUTPUT FORMAT — respond ONLY with valid JSON, no markdown, no extra text:
{{
  "story_text": "story segment in Japanese",
  "choices": ["choice 1 in Japanese", "choice 2 in Japanese", "choice 3 in Japanese (optional)"]
}}"""


def build_continuation_prompt(
    system_prompt: str,
    history: list[dict],
    user_input: str,
    difficulty_hint: str | None = None,
) -> tuple[str, list[dict]]:
    """
    Prepare the system prompt and message history for a story continuation.

    difficulty_hint is injected when the user taps Too Hard / Too Easy,
    appending a one-time instruction to the system prompt for this turn only.
    """
    adjusted_system = system_prompt
    if difficulty_hint:
        adjusted_system += f"\n\nDIFFICULTY ADJUSTMENT FOR THIS TURN: {difficulty_hint}"

    messages = [*history, {"role": "user", "content": user_input}]
    return adjusted_system, messages


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
    # Strip markdown code fences if present (```json ... ```)
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

    return story_text, choices


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_known_surfaces(user_id: int, db: Session) -> set[str]:
    """Return the set of word surfaces the user has encountered (any status)."""
    rows = (
        db.query(Vocab.word)
        .join(UserVocab, UserVocab.vocab_id == Vocab.id)
        .filter(UserVocab.user_id == user_id)
        .all()
    )
    return {row.word for row in rows}


def get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user
