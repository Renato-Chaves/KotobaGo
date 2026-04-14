import os
from typing import Literal

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Source = Literal["local", "anthropic", "openai"]
TaskType = Literal["story", "error_analysis", "context_compression", "coach_note", "lesson"]
Message = dict  # {"role": "user" | "assistant", "content": str}


# ---------------------------------------------------------------------------
# LLMClient — knows HOW to talk to one provider
# ---------------------------------------------------------------------------

class LLMClient:
    def __init__(self, source: Source, model: str | None = None):
        self.source = source
        self.model = model or _default_model(source)

    async def chat(self, system: str, messages: list[Message], temperature: float | None = None) -> str:
        if self.source == "local":
            return await self._ollama(system, messages, temperature)
        elif self.source == "anthropic":
            return await self._claude(system, messages, temperature)
        elif self.source == "openai":
            return await self._openai(system, messages, temperature)
        raise ValueError(f"Unknown LLM source: {self.source}")

    # --- Ollama ---

    async def _ollama(self, system: str, messages: list[Message], temperature: float | None = None) -> str:
        url = f"{os.getenv('OLLAMA_BASE_URL', 'http://ollama:11434')}/api/chat"
        payload: dict = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        if temperature is not None:
            payload["options"] = {"temperature": temperature}
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            return res.json()["message"]["content"]

    # --- Anthropic / Claude ---

    async def _claude(self, system: str, messages: list[Message], temperature: float | None = None) -> str:
        client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        kwargs: dict = dict(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        if temperature is not None:
            kwargs["temperature"] = max(0.0, min(1.0, temperature))  # Anthropic clamps to 0–1
        response = await client.messages.create(**kwargs)
        return response.content[0].text

    # --- OpenAI ---

    async def _openai(self, system: str, messages: list[Message], temperature: float | None = None) -> str:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        kwargs: dict = dict(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
        )
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = await client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


def _default_model(source: Source) -> str:
    defaults: dict[Source, str] = {
        "local": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4o-mini",
    }
    return defaults[source]


# ---------------------------------------------------------------------------
# LLMRouter — knows WHICH provider to use for each task type
# ---------------------------------------------------------------------------

class LLMRouter:
    """
    Routes each task to the appropriate LLM source.

    Most tasks run locally. Coach notes optionally use the API for
    better prose quality — controlled by COACH_NOTE_SOURCE env var.
    """

    def __init__(self):
        self._local = LLMClient("local")
        self._primary_source: Source = os.getenv("LLM_SOURCE", "local")  # type: ignore
        self._primary = LLMClient(self._primary_source)

    async def route(
        self,
        task: TaskType,
        system: str,
        messages: list[Message],
        model_override: str | None = None,
        temperature: float | None = None,
    ) -> str:
        client = self._client_for(task, model_override=model_override)
        return await client.chat(system, messages, temperature=temperature)

    def _client_for(self, task: TaskType, model_override: str | None = None) -> LLMClient:
        # If a per-call model override is given and the source is local, create a
        # lightweight temp client with that model. LLMClient has no persistent
        # state so this is safe to do per-call.
        if model_override and self._primary_source == "local":
            return LLMClient("local", model=model_override)
        # Coach notes can be routed to a cloud API for better prose.
        # Everything else runs locally regardless of LLM_SOURCE.
        if task == "coach_note":
            coach_source: Source = os.getenv("COACH_NOTE_SOURCE", "local")  # type: ignore
            return LLMClient(coach_source)
        return self._local


# Singleton — imported and reused across routes
router = LLMRouter()
