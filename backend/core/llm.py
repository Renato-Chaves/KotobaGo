import os
from typing import Literal

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Source = Literal["local", "anthropic", "openai"]
TaskType = Literal["story", "error_analysis", "context_compression", "coach_note"]
Message = dict  # {"role": "user" | "assistant", "content": str}


# ---------------------------------------------------------------------------
# LLMClient — knows HOW to talk to one provider
# ---------------------------------------------------------------------------

class LLMClient:
    def __init__(self, source: Source, model: str | None = None):
        self.source = source
        self.model = model or _default_model(source)

    async def chat(self, system: str, messages: list[Message]) -> str:
        if self.source == "local":
            return await self._ollama(system, messages)
        elif self.source == "anthropic":
            return await self._claude(system, messages)
        elif self.source == "openai":
            return await self._openai(system, messages)
        raise ValueError(f"Unknown LLM source: {self.source}")

    # --- Ollama ---

    async def _ollama(self, system: str, messages: list[Message]) -> str:
        url = f"{os.getenv('OLLAMA_BASE_URL', 'http://ollama:11434')}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            return res.json()["message"]["content"]

    # --- Anthropic / Claude ---

    async def _claude(self, system: str, messages: list[Message]) -> str:
        client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    # --- OpenAI ---

    async def _openai(self, system: str, messages: list[Message]) -> str:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
        )
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

    async def route(self, task: TaskType, system: str, messages: list[Message]) -> str:
        client = self._client_for(task)
        return await client.chat(system, messages)

    def _client_for(self, task: TaskType) -> LLMClient:
        # Coach notes can be routed to a cloud API for better prose.
        # Everything else runs locally regardless of LLM_SOURCE.
        if task == "coach_note":
            coach_source: Source = os.getenv("COACH_NOTE_SOURCE", "local")  # type: ignore
            return LLMClient(coach_source)
        return self._local


# Singleton — imported and reused across routes
router = LLMRouter()
