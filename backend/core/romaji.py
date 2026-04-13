"""
Romaji detection and conversion to Japanese.

When a user doesn't have a Japanese IME available, they may type in romaji
(e.g. "watashi wa gakusei desu"). This module detects such input and converts
it to natural Japanese so the rest of the pipeline (error analysis, story
continuation) can work correctly.
"""

import re

from core.llm import router as llm_router

_LATIN_RE = re.compile(r"[a-zA-Z]")
_JP_RE = re.compile(r"[\u3040-\u9fff]")
_JP_CHAR_RE = re.compile(r"[\u3040-\u9fff]")


def is_romaji_heavy(text: str) -> bool:
    """
    True when the input is mostly Latin characters with little/no Japanese.
    Threshold: >50% of combined Latin+Japanese chars are Latin.
    """
    latin = len(_LATIN_RE.findall(text))
    jp = len(_JP_RE.findall(text))
    total = latin + jp
    return total > 0 and latin / total > 0.5


async def convert_to_japanese(text: str, model_override: str | None = None) -> str:
    """
    Use the LLM to convert a romaji sentence to natural Japanese script.

    Preserves the learner's intended grammar/vocabulary — the goal is
    transliteration + kanji conversion, not correction. Errors in the
    original romaji should survive so the error analyzer can still catch them.

    Returns the original text unchanged if conversion fails or produces garbage.
    """
    system = (
        "Romaji to Japanese converter. Rules:\n"
        "1. Convert ONLY the romaji I give you to Japanese (hiragana/katakana/kanji).\n"
        "2. Do NOT add, remove, or correct anything — preserve mistakes.\n"
        "3. Output ONLY the Japanese characters. Stop immediately after the last character.\n"
        "4. No explanations. No extra sentences. No English. Just the Japanese."
    )
    messages = [{"role": "user", "content": f"Convert this romaji to Japanese: {text}"}]

    try:
        result = await llm_router.route("error_analysis", system, messages, model_override=model_override)
        converted = result.strip()

        # Strip trailing ASCII/Latin garbage the model may hallucinate after the Japanese
        # Find the index of the last Japanese character and truncate there
        last_jp_idx = -1
        for i, ch in enumerate(converted):
            if _JP_CHAR_RE.match(ch):
                last_jp_idx = i
        if last_jp_idx >= 0:
            converted = converted[: last_jp_idx + 1].strip()

        # Reject if result contains no Japanese at all
        if not converted or not _JP_RE.search(converted):
            return text

        return converted
    except Exception:
        pass

    return text  # fall back to original if conversion fails
