"""
Graph Query API — Micro-service for graph and telemetry queries.

Exposes two POST endpoints:
  POST /query/graph      — Execute a graph query (GQL, Gremlin, or mock via GRAPH_BACKEND)
  POST /query/telemetry  — Execute a SQL query against Cosmos DB NoSQL telemetry containers

The graph backend is selected by the GRAPH_BACKEND env var:
  fabric   → GQL queries against Fabric GraphModel REST API (default)
  cosmosdb → Gremlin queries against Azure Cosmos DB
  mock     → static topology data for offline demos

Auth:
  Uses DefaultAzureCredential (managed identity in production, az login locally).
  Callers do NOT need to authenticate to this API — it runs inside the VNet
  and is called by Foundry's OpenApiTool on behalf of agents.

Run locally:
  cd graph-query-api && uv run uvicorn main:app --reload --port 8100
"""

from __future__ import annotations

import asyncio
import json
import os
import logging
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from config import GRAPH_BACKEND, GraphBackendType, BACKEND_REQUIRED_VARS, TELEMETRY_REQUIRED_VARS
from models import GraphQueryRequest
from router_graph import router as graph_router, close_graph_backend
from router_telemetry import router as telemetry_router, close_telemetry_backend

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("graph-query-api")
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Validate config at startup; clean up backend on shutdown."""
    required = BACKEND_REQUIRED_VARS.get(GRAPH_BACKEND, ())
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        logger.warning(
            "Missing env vars for %s backend (will rely on request body values): %s",
            GRAPH_BACKEND.value, ", ".join(missing),
        )
    # Check optional telemetry vars separately
    missing_telemetry = [v for v in TELEMETRY_REQUIRED_VARS if not os.getenv(v)]
    if missing_telemetry:
        logger.warning(
            "Missing telemetry env vars — /query/telemetry will not work: %s",
            ", ".join(missing_telemetry),
        )
    logger.info("Starting with GRAPH_BACKEND=%s", GRAPH_BACKEND.value)
    yield
    await close_graph_backend()
    close_telemetry_backend()


app = FastAPI(
    title="Graph Query API",
    version="0.5.0",
    description=f"Graph ({GRAPH_BACKEND.value}) and telemetry queries for Foundry agents.",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request with timing and full error details."""
    import time as _time
    body = b""
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        logger.info(
            "▶ %s %s  body=%s",
            request.method, request.url.path, body[:1000].decode(errors="replace"),
        )
    else:
        logger.info("▶ %s %s", request.method, request.url.path)
    t0 = _time.time()
    response = await call_next(request)
    elapsed_ms = (_time.time() - t0) * 1000
    if response.status_code >= 400:
        logger.warning(
            "◀ %s %s → %d  (%.0fms)",
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
    else:
        logger.info(
            "◀ %s %s → %d  (%.0fms)",
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
    return response


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(graph_router)
app.include_router(telemetry_router)


# ---------------------------------------------------------------------------
# Log streaming SSE
# ---------------------------------------------------------------------------

_log_subscribers: set[asyncio.Queue] = set()
_log_buffer: deque[dict] = deque(maxlen=100)


def _broadcast_log(record: dict) -> None:
    _log_buffer.append(record)
    dead: list[asyncio.Queue] = []
    for q in _log_subscribers:
        try:
            q.put_nowait(record)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _log_subscribers.discard(q)


class _SSELogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3],
                "level": record.levelname,
                "name": record.name,
                "msg": self.format(record),
            }
            _broadcast_log(entry)
        except Exception:
            self.handleError(record)


_sse_handler = _SSELogHandler()
_sse_handler.setLevel(logging.DEBUG)
_sse_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_sse_handler.addFilter(lambda r: r.name.startswith(("graph-query-api",)))
logging.getLogger().addHandler(_sse_handler)


async def _log_sse_generator():
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _log_subscribers.add(q)
    try:
        for rec in list(_log_buffer):
            yield f"event: log\ndata: {json.dumps(rec)}\n\n"
        while True:
            rec = await q.get()
            yield f"event: log\ndata: {json.dumps(rec)}\n\n"
    finally:
        _log_subscribers.discard(q)


@app.get("/api/logs", summary="Stream logs via SSE")
async def stream_logs():
    return StreamingResponse(
        _log_sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Health & Debug
# ---------------------------------------------------------------------------


@app.get("/health", summary="Health check")
async def health():
    return {
        "status": "ok",
        "service": "graph-query-api",
        "version": app.version,
        "graph_backend": GRAPH_BACKEND.value,
    }


if os.getenv("DEBUG_ENDPOINTS") == "1" and GRAPH_BACKEND == GraphBackendType.FABRIC:
    from backends.fabric import _execute_gql
    from config import WORKSPACE_ID, GRAPH_MODEL_ID

    @app.post("/debug/raw-gql", summary="Debug: raw GQL response")
    async def debug_raw_gql(req: GraphQueryRequest):
        """Return the raw Fabric API response for debugging."""
        ws = req.workspace_id or WORKSPACE_ID
        gm = req.graph_model_id or GRAPH_MODEL_ID
        if not ws or not gm:
            raise HTTPException(status_code=400, detail="workspace_id and graph_model_id required")
        result = await _execute_gql(req.query, workspace_id=ws, graph_model_id=gm)
        return result
