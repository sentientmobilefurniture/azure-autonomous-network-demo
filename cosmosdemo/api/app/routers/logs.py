"""
Log streaming router — GET /api/logs, GET /api/logs/data-ops

Streams backend log output to the frontend as SSE events for real-time
observability. Uses the shared LogBroadcaster for fan-out to multiple
concurrent SSE clients.
"""

import logging

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from app.log_broadcaster import LogBroadcaster

router = APIRouter(prefix="/api", tags=["logs"])

# ---------------------------------------------------------------------------
# All logs broadcaster (API + orchestrator + azure)
# ---------------------------------------------------------------------------

_broadcaster = LogBroadcaster(max_buffer=100, max_queue=500)

_handler = _broadcaster.get_handler(level=logging.INFO)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_handler.addFilter(lambda r: r.name.startswith(("app", "api", "azure", "uvicorn")))
logging.getLogger().addHandler(_handler)


# ---------------------------------------------------------------------------
# Data-ops broadcaster (agent config only)
# ---------------------------------------------------------------------------

_data_ops_broadcaster = LogBroadcaster(max_buffer=200, max_queue=500)

_data_ops_handler = _data_ops_broadcaster.get_handler(level=logging.DEBUG)
_data_ops_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_data_ops_handler.addFilter(
    lambda r: r.name.startswith(("api.config",))
)
logging.getLogger().addHandler(_data_ops_handler)


# ---------------------------------------------------------------------------
# SSE endpoints
# ---------------------------------------------------------------------------

def _sse_response(broadcaster: LogBroadcaster) -> StreamingResponse:
    return StreamingResponse(
        broadcaster.subscribe(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/logs")
async def stream_logs():
    """SSE endpoint that streams all backend log lines."""
    return _sse_response(_broadcaster)


@router.get("/logs/data-ops")
async def stream_data_ops_logs():
    """SSE endpoint that streams only data-operation logs (config)."""
    return _sse_response(_data_ops_broadcaster)

