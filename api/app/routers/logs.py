"""
Log streaming router — GET /api/logs

Streams backend log output to the frontend as SSE events for real-time
observability.  A custom logging.Handler pushes formatted records into an
asyncio.Queue consumed by the SSE generator.

Multiple concurrent SSE clients are supported — each gets its own queue
and a copy of every log record.
"""

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api", tags=["logs"])

# ---------------------------------------------------------------------------
# Broadcast hub — fan-out log records to all connected SSE clients
# ---------------------------------------------------------------------------

_subscribers: set[asyncio.Queue] = set()
_log_buffer: deque[dict] = deque(maxlen=100)  # last 100 lines for new connects


def _broadcast(record: dict) -> None:
    """Push a log record dict to every connected subscriber queue."""
    _log_buffer.append(record)
    dead: list[asyncio.Queue] = []
    for q in _subscribers:
        try:
            q.put_nowait(record)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.discard(q)


# ---------------------------------------------------------------------------
# Custom logging handler → queue bridge
# ---------------------------------------------------------------------------

class _SSELogHandler(logging.Handler):
    """Logging handler that serialises records and broadcasts them."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3],
                "level": record.levelname,
                "name": record.name,
                "msg": self.format(record),
            }
            _broadcast(entry)
        except Exception:
            self.handleError(record)


# Install handler on the root logger so we capture everything interesting
_handler = _SSELogHandler()
_handler.setLevel(logging.INFO)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
# Filter to only app.* and azure.* loggers to avoid noise
_handler.addFilter(lambda r: r.name.startswith(("app", "azure", "uvicorn")))

logging.getLogger().addHandler(_handler)


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------

async def _log_event_generator() -> AsyncGenerator:
    """Yields SSE events for each log record."""
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.add(q)

    try:
        # Send buffered history first so the panel isn't empty on connect
        for rec in list(_log_buffer):
            yield {"event": "log", "data": json.dumps(rec)}

        # Then stream live
        while True:
            rec = await q.get()
            yield {"event": "log", "data": json.dumps(rec)}
    finally:
        _subscribers.discard(q)


@router.get("/logs")
async def stream_logs():
    """SSE endpoint that streams backend log lines."""
    return EventSourceResponse(
        _log_event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
