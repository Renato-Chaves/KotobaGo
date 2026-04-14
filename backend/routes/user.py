import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.models import User, get_db

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    id: int
    native_language: str
    target_language: str
    jlpt_goal: str
    ai_context: str | None
    error_analysis_mode: str   # "on_call" | "auto"
    furigana_mode: str         # "full" | "known_only" | "none"
    dark_mode: bool
    model_settings: dict | None  # per-task Ollama model overrides
    story_config: dict | None    # story prompt tuning: temperature, story_length, new_word_pct


class UpdateProfileRequest(BaseModel):
    native_language: str | None = None
    jlpt_goal: str | None = None
    ai_context: str | None = None
    error_analysis_mode: str | None = None
    furigana_mode: str | None = None
    model_settings: dict | None = None  # merged into existing, not replaced wholesale
    story_config: dict | None = None    # merged into existing


class AvailableModelsResponse(BaseModel):
    models: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserProfile)
async def get_profile(user_id: int = 1, db: Session = Depends(get_db)):
    """Return the current user's profile and preferences."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_profile(user)


@router.patch("/me", response_model=UserProfile)
async def update_profile(
    req: UpdateProfileRequest,
    user_id: int = 1,
    db: Session = Depends(get_db),
):
    """Update user preferences. Only provided fields are changed."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _JLPT_LEVELS = {"N5", "N4", "N3", "N2", "N1"}
    _LANGUAGES = {"pt", "en", "es", "fr", "de", "zh", "ko"}
    _ERROR_MODES = {"on_call", "auto"}
    _FURIGANA_MODES = {"full", "known_only", "none"}
    _VALID_TASKS = {"story", "error_analysis", "coach_note"}

    if req.native_language is not None:
        if req.native_language not in _LANGUAGES:
            raise HTTPException(status_code=422, detail=f"Unsupported language: {req.native_language}")
        user.native_language = req.native_language

    if req.jlpt_goal is not None:
        if req.jlpt_goal not in _JLPT_LEVELS:
            raise HTTPException(status_code=422, detail=f"Invalid JLPT level: {req.jlpt_goal}")
        user.jlpt_goal = req.jlpt_goal

    if req.ai_context is not None:
        user.ai_context = req.ai_context.strip() or None

    if req.error_analysis_mode is not None:
        if req.error_analysis_mode not in _ERROR_MODES:
            raise HTTPException(status_code=422, detail=f"Invalid mode: {req.error_analysis_mode}")
        user.error_analysis_mode = req.error_analysis_mode

    if req.furigana_mode is not None:
        if req.furigana_mode not in _FURIGANA_MODES:
            raise HTTPException(status_code=422, detail=f"Invalid mode: {req.furigana_mode}")
        user.furigana_mode = req.furigana_mode

    if req.model_settings is not None:
        # Merge: only update keys explicitly sent; ignore unknown task keys
        current = dict(user.model_settings or {})
        for task, model in req.model_settings.items():
            if task in _VALID_TASKS:
                current[task] = model or None  # empty string → null
        user.model_settings = current
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, "model_settings")

    if req.story_config is not None:
        _VALID_STORY_LENGTHS = {"tiny", "short", "medium", "long"}
        current_sc = dict(user.story_config or {})
        if "temperature" in req.story_config:
            t = float(req.story_config["temperature"])
            current_sc["temperature"] = max(0.0, min(2.0, t))
        if "story_length" in req.story_config:
            sl = req.story_config["story_length"]
            if sl in _VALID_STORY_LENGTHS:
                current_sc["story_length"] = sl
        if "new_word_pct" in req.story_config:
            pct = int(req.story_config["new_word_pct"])
            current_sc["new_word_pct"] = max(0, min(50, pct))
        user.story_config = current_sc
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, "story_config")

    db.commit()
    db.refresh(user)
    return _to_profile(user)


@router.get("/models", response_model=AvailableModelsResponse)
async def get_available_models():
    """
    Return the list of Ollama models currently installed on the local instance.
    Calls Ollama's /api/tags endpoint. Returns empty list if Ollama is unreachable.
    """
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{ollama_base}/api/tags")
            res.raise_for_status()
            data = res.json()
            model_names = [m["name"] for m in data.get("models", [])]
            return AvailableModelsResponse(models=model_names)
    except Exception:
        return AvailableModelsResponse(models=[])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        native_language=user.native_language,
        target_language=user.target_language,
        jlpt_goal=user.jlpt_goal,
        ai_context=user.ai_context,
        error_analysis_mode=user.error_analysis_mode,
        furigana_mode=user.furigana_mode,
        dark_mode=user.dark_mode,
        model_settings=user.model_settings,
        story_config=user.story_config,
    )
