"""
Log streaming router — GET /api/logs

Streams backend log output to the frontend as SSE events for real-time
observability. Uses the shared LogBroadcaster for fan-out to multiple
concurrent SSE clients.
"""

import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.log_broadcaster import LogBroadcaster

router = APIRouter(prefix="/api", tags=["logs"])

# ---------------------------------------------------------------------------
# Shared broadcaster instance
# ---------------------------------------------------------------------------

_broadcaster = LogBroadcaster(max_buffer=100, max_queue=500)

# Install handler on the root logger
_handler = _broadcaster.get_handler(level=logging.INFO)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_handler.addFilter(lambda r: r.name.startswith(("app", "azure", "uvicorn")))
logging.getLogger().addHandler(_handler)


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------

@router.get("/logs")
async def stream_logs():
    """SSE endpoint that streams backend log lines."""
    return EventSourceResponse(
        _broadcaster.subscribe(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

