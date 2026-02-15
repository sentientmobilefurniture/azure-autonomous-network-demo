"""
SSE upload lifecycle helper — reusable SSE streaming scaffold.

Provides SSEProgress (thin asyncio.Queue wrapper) and sse_upload_response()
which encapsulates the common pattern used by all upload endpoints:
  Queue + emit/complete/error/done → create_task → while-loop → EventSourceResponse

Used by: router_ingest.py (5 upload endpoints)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("graph-query-api.sse")


class SSEProgress:
    """Thin wrapper around asyncio.Queue for SSE upload progress."""

    def __init__(self) -> None:
        self._q: asyncio.Queue[dict | None] = asyncio.Queue()

    def emit(self, step: str, detail: str, pct: int) -> None:
        self._q.put_nowait({"step": step, "detail": detail, "pct": pct})

    def complete(self, result: dict) -> None:
        self._q.put_nowait({"_result": result})

    def error(self, msg: str) -> None:
        self._q.put_nowait({"step": "error", "detail": msg, "pct": -1})

    def done(self) -> None:
        self._q.put_nowait(None)

    async def get(self) -> dict | None:
        return await self._q.get()


def sse_upload_response(
    work_fn: Callable[[SSEProgress], Coroutine[Any, Any, None]],
    error_label: str = "upload",
) -> EventSourceResponse:
    """Standard SSE lifecycle: run work_fn, stream progress/complete/error.

    The work_fn receives an SSEProgress instance and should call:
      progress.emit(step, detail, pct)  — for progress updates
      progress.complete(result_dict)    — for the final result
      progress.error(msg)              — on failure (also called by wrapper)
    The wrapper ensures progress.done() is always called in finally.

    Returns an EventSourceResponse suitable as a FastAPI endpoint return value.
    """

    async def stream():
        progress = SSEProgress()

        async def run():
            try:
                await work_fn(progress)
            except Exception as e:
                logger.exception("%s failed", error_label)
                progress.error(str(e))
            finally:
                progress.done()

        task = asyncio.create_task(run())
        while True:
            ev = await progress.get()
            if ev is None:
                break
            if "_result" in ev:
                yield {"event": "complete", "data": json.dumps(ev["_result"])}
            elif ev.get("step") == "error":
                yield {"event": "error", "data": json.dumps({"error": ev["detail"]})}
            else:
                yield {"event": "progress", "data": json.dumps(ev)}
        await task

    return EventSourceResponse(stream())
