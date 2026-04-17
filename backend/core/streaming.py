"""
Streaming JSON helper for long-running LLM endpoints.

Usage (in a FastAPI route handler):

    async def work() -> dict:
        ...  # slow LLM calls
        return SomeResponse(...).model_dump()

    return await stream_json(work())

While the coroutine is pending the response body is flushed with a
`~\\n` heartbeat every `heartbeat_interval` seconds. This keeps the TCP
connection alive even when the LLM backend takes 10–30 s to respond,
preventing browser / Docker-network idle-connection resets that surface as
"NetworkError when attempting to fetch resource".

The frontend reads lines from the stream:
  - `~`          → heartbeat, ignore
  - `{"__error__": "..."}` → server-side exception, raise
  - anything else → the JSON-encoded result dict
"""

import asyncio
import json
from typing import Any, Awaitable

from fastapi.responses import StreamingResponse


async def stream_json(
    coro: Awaitable[Any],
    heartbeat_interval: float = 3.0,
) -> StreamingResponse:
    result: list[Any] = [None]
    exc: list[BaseException | None] = [None]
    done = asyncio.Event()

    async def worker() -> None:
        try:
            result[0] = await coro
        except Exception as e:  # noqa: BLE001
            exc[0] = e
        finally:
            done.set()

    asyncio.create_task(worker())

    async def body():
        while not done.is_set():
            try:
                await asyncio.wait_for(done.wait(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield b"~\n"  # heartbeat — keeps the TCP connection alive
        if exc[0] is not None:
            yield json.dumps({"__error__": str(exc[0])}).encode() + b"\n"
        else:
            yield json.dumps(result[0]).encode() + b"\n"

    return StreamingResponse(body(), media_type="application/x-ndjson")
