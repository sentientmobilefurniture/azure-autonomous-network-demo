"""
Graph Query API — Micro-service for graph and telemetry queries.

Exposes two POST endpoints:
  POST /query/graph      — Execute a graph query (GQL via Fabric or mock)
  POST /query/telemetry  — Execute a KQL query against Fabric Eventhouse

The graph backend is selected by the GRAPH_BACKEND env var:
  fabric-gql → GQL queries against Microsoft Fabric (default)
  mock       → static topology data for offline demos

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
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from config import GRAPH_BACKEND, BACKEND_REQUIRED_VARS
from router_graph import router as graph_router, close_graph_backend
from router_telemetry import router as telemetry_router
from router_topology import router as topology_router
from router_interactions import router as interactions_router
from router_health import router as health_router

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
    """Validate config at startup; pre-warm backends; clean up on shutdown."""
    required = BACKEND_REQUIRED_VARS.get(GRAPH_BACKEND, ())
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        logger.warning(
            "Missing env vars for %s backend (will rely on request body values): %s",
            GRAPH_BACKEND, ", ".join(missing),
        )

    logger.info("Starting with GRAPH_BACKEND=%s", GRAPH_BACKEND)
    yield

    await close_graph_backend()


app = FastAPI(
    title="Graph Query API",
    version="0.5.0",
    description=f"Graph ({GRAPH_BACKEND}) and telemetry queries for Foundry agents.",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request with timing and full error details."""
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
app.include_router(topology_router)
app.include_router(interactions_router)
app.include_router(health_router)


# ---------------------------------------------------------------------------
# Log streaming SSE (uses shared LogBroadcaster)
# ---------------------------------------------------------------------------

from log_broadcaster import LogBroadcaster

_log_broadcaster = LogBroadcaster(max_buffer=100, max_queue=500)

_sse_handler = _log_broadcaster.get_handler(level=logging.DEBUG)
_sse_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_sse_handler.addFilter(lambda r: r.name.startswith(("graph-query-api",)))
logging.getLogger().addHandler(_sse_handler)

# Data-ops only: ingest, cosmos, indexer, blob
_data_ops_broadcaster = LogBroadcaster(max_buffer=200, max_queue=500)
_data_ops_handler = _data_ops_broadcaster.get_handler(level=logging.DEBUG)
_data_ops_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_data_ops_handler.addFilter(
    lambda r: r.name.startswith((
        "graph-query-api.ingest",
        "graph-query-api.cosmos",
        "graph-query-api.indexer",
        "graph-query-api.blob",
    ))
)
logging.getLogger().addHandler(_data_ops_handler)


@app.get("/query/logs", summary="Stream graph-query-api logs via SSE")
async def stream_logs():
    """Stream graph-query-api logs via SSE."""
    return StreamingResponse(
        _log_broadcaster.subscribe(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/query/logs/data-ops", summary="Stream data-operation logs via SSE")
async def stream_data_ops_logs():
    """Stream only data-operation logs (ingest, cosmos, indexer, blob)."""
    return StreamingResponse(
        _data_ops_broadcaster.subscribe(),
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
        "graph_backend": GRAPH_BACKEND,
    }



