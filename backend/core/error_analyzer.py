"""
Error analysis for learner-produced Japanese text.

Sends the text to the LLM and parses a structured JSON response with:
  - errors: list of {error_text, correction, type, explanation}
  - overall_feedback: one encouraging sentence

Error types:
  critical   — spelling, wrong kanji, unintelligible
  grammar    — wrong particle, conjugation, sentence structure
  politeness — wrong speech level (keigo vs plain)
  unnatural  — grammatically fine but no native speaker would say it
  stylistic  — optional style improvements (not wrong, just improvable)
"""
import json
import re

from core.llm import router as llm_router

# ---------------------------------------------------------------------------
# Types (plain dicts — converted to Pydantic on the route layer)
# ---------------------------------------------------------------------------

ErrorType = str  # "critical" | "grammar" | "politeness" | "unnatural" | "stylistic"


def _system_prompt(native_lang: str) -> str:
    lang_name = {"pt": "Portuguese", "en": "English"}.get(native_lang, "English")
    return f"""You are a strict but encouraging Japanese language teacher.
A learner has written a Japanese sentence or short passage.
Identify any errors and return ONLY a JSON object in exactly this format (no markdown, no extra text):

{{
  "errors": [
    {{
      "error_text": "the exact wrong text from the input",
      "correction": "the correct form",
      "type": "critical|grammar|politeness|unnatural|stylistic",
      "explanation": "brief explanation in {lang_name}"
    }}
  ],
  "overall_feedback": "one encouraging sentence in {lang_name} summarising their performance"
}}

Error type definitions:
- critical: spelling mistakes, wrong kanji, text a Japanese person cannot understand
- grammar: incorrect particles, verb conjugation, te-form, sentence structure
- politeness: wrong speech register (mixing keigo with casual, など)
- unnatural: grammatically correct but a native speaker would never say it this way
- stylistic: optional improvements — not wrong, just could be more natural

Rules:
- Only report ACTUAL errors, not stylistic preferences unless clearly unnatural.
- If there are no errors, return {{"errors": [], "overall_feedback": "..."}}
- error_text must be a verbatim substring of the input.
- Output only the JSON object."""


async def analyze_errors(
    text: str,
    native_lang: str = "en",
) -> dict:
    """
    Returns {"errors": [...], "overall_feedback": "..."}.
    On LLM or parse failure returns an empty-error result rather than crashing.
    """
    system = _system_prompt(native_lang)
    messages = [{"role": "user", "content": text}]

    try:
        raw = await llm_router.route("error_analysis", system, messages)
        return _parse_response(raw)
    except Exception:
        return {"errors": [], "overall_feedback": "Could not analyse text at this time."}


def _parse_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON from LLM output."""
    cleaned = raw.strip()
    # Remove ```json ... ``` or ``` ... ``` wrappers
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    data = json.loads(cleaned)

    errors = []
    for item in data.get("errors", []):
        errors.append({
            "error_text": str(item.get("error_text", "")),
            "correction": str(item.get("correction", "")),
            "type": str(item.get("type", "grammar")),
            "explanation": str(item.get("explanation", "")),
        })

    return {
        "errors": errors,
        "overall_feedback": str(data.get("overall_feedback", "")),
    }
