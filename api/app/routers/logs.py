"""
Log streaming router — GET /api/logs

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

