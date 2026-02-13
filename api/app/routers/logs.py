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
import threading
from collections import deque
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api", tags=["logs"])

# ---------------------------------------------------------------------------
# Broadcast hub — fan-out log records to all connected SSE clients
# ---------------------------------------------------------------------------

_lock = threading.Lock()  # Protects _subscribers and _log_buffer from cross-thread access
_subscribers: set[asyncio.Queue] = set()
_log_buffer: deque[dict] = deque(maxlen=100)  # last 100 lines for new connects

# Cache the running event loop for thread-safe queue puts
_event_loop: asyncio.AbstractEventLoop | None = None


def _broadcast(record: dict) -> None:
    """Push a log record dict to every connected subscriber queue (thread-safe)."""
    with _lock:
        _log_buffer.append(record)
        dead: list[asyncio.Queue] = []
        subscribers_snapshot = list(_subscribers)
    # Enqueue outside the lock to avoid holding it during potentially slow ops
    for q in subscribers_snapshot:
        try:
            if _event_loop is not None and _event_loop.is_running():
                _event_loop.call_soon_threadsafe(q.put_nowait, record)
            else:
                q.put_nowait(record)
        except (asyncio.QueueFull, RuntimeError):
            dead.append(q)
    if dead:
        with _lock:
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
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    q: asyncio.Queue = asyncio.Queue(maxsize=500)

    # Snapshot buffer BEFORE subscribing to avoid duplicate delivery
    with _lock:
        buffered = list(_log_buffer)
        _subscribers.add(q)

    try:
        # Send buffered history first so the panel isn't empty on connect
        for rec in buffered:
            yield {"event": "log", "data": json.dumps(rec)}

        # Then stream live
        while True:
            rec = await q.get()
            yield {"event": "log", "data": json.dumps(rec)}
    finally:
        with _lock:
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

