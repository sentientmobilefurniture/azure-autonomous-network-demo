"""
Fabric Query API — Micro-service for GQL and KQL queries.

Exposes two POST endpoints:
  POST /query/graph      — Execute a GQL query against the Fabric GraphModel
  POST /query/telemetry  — Execute a KQL query against the Fabric Eventhouse

Auth:
  Uses DefaultAzureCredential (managed identity in production, az login locally).
  Callers do NOT need to authenticate to this API — it runs inside the VNet
  and is called by Foundry's OpenApiTool on behalf of agents.

Env vars (all required):
  FABRIC_API_URL          — Fabric REST API base URL (default: https://api.fabric.microsoft.com/v1)
  FABRIC_SCOPE            — OAuth scope for Fabric (default: https://api.fabric.microsoft.com/.default)
  FABRIC_WORKSPACE_ID     — Fabric workspace GUID
  FABRIC_GRAPH_MODEL_ID   — GraphModel item GUID
  EVENTHOUSE_QUERY_URI    — Kusto query URI for the Eventhouse
  FABRIC_KQL_DB_NAME      — KQL database name

Run locally:
  cd fabric-query-api && uv run uvicorn main:app --reload --port 8100
"""

from __future__ import annotations

import asyncio
import json
import os
import logging
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

logger = logging.getLogger("fabric-query-api")
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

_REQUIRED_ENV_VARS = (
    "FABRIC_WORKSPACE_ID", "FABRIC_GRAPH_MODEL_ID",
    "EVENTHOUSE_QUERY_URI", "FABRIC_KQL_DB_NAME",
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Validate config at startup; warn about missing env vars."""
    missing = [v for v in _REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        logger.warning(
            "Missing env vars (will rely on request body values): %s",
            ", ".join(missing),
        )
    yield


app = FastAPI(
    title="Fabric Query API",
    version="0.4.0",
    description="Runs GQL and KQL queries against Microsoft Fabric for Foundry agents.",
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
# Config
# ---------------------------------------------------------------------------

FABRIC_API = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")
WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")
EVENTHOUSE_QUERY_URI = os.getenv("EVENTHOUSE_QUERY_URI", "")
KQL_DB_NAME = os.getenv("FABRIC_KQL_DB_NAME", "")

# ---------------------------------------------------------------------------
# Shared credential
# ---------------------------------------------------------------------------

credential = DefaultAzureCredential()

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class GraphQueryRequest(BaseModel):
    query: str
    workspace_id: str = ""
    graph_model_id: str = ""


class GraphQueryResponse(BaseModel):
    columns: list[dict]
    data: list[dict]


class TelemetryQueryRequest(BaseModel):
    query: str
    eventhouse_query_uri: str = ""
    kql_db_name: str = ""


class TelemetryQueryResponse(BaseModel):
    columns: list[dict]
    rows: list[dict]


class ErrorResponse(BaseModel):
    error: str


# ---------------------------------------------------------------------------
# GQL helpers
# ---------------------------------------------------------------------------


def _fabric_headers() -> dict[str, str]:
    token = credential.get_token(FABRIC_SCOPE).token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _execute_gql(
    query: str,
    workspace_id: str = "",
    graph_model_id: str = "",
    max_retries: int = 3,
) -> dict:
    """Execute a GQL query with retry on 429 (fully async)."""
    ws = workspace_id or WORKSPACE_ID
    gm = graph_model_id or GRAPH_MODEL_ID
    url = (
        f"{FABRIC_API}/workspaces/{ws}"
        f"/GraphModels/{gm}/executeQuery"
    )
    body = {"query": query}

    logger.info("GQL request to %s", url)
    logger.debug("GQL query:\n%s", query)

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(1, max_retries + 1):
            headers = _fabric_headers()
            import time as _time
            t0 = _time.time()
            r = await client.post(url, headers=headers, json=body, params={"beta": "True"})
            elapsed_ms = (_time.time() - t0) * 1000
            logger.info(
                "GQL response: status=%d  elapsed=%.0fms  attempt=%d/%d",
                r.status_code, elapsed_ms, attempt, max_retries,
            )

            if r.status_code == 200:
                payload = r.json()
                # Fabric returns HTTP 200 even for GQL errors — check body status
                status_code = payload.get("status", {}).get("code", "")
                if status_code and not status_code.startswith("0"):
                    cause = payload.get("status", {}).get("cause", {})
                    err_desc = cause.get("description", payload["status"].get("description", "unknown GQL error"))
                    logger.error(
                        "GQL logical error (status=%s): %s\nFull query:\n%s\nFull response body:\n%s",
                        status_code, err_desc, query, r.text[:2000],
                    )
                    raise HTTPException(status_code=400, detail=f"GQL error ({status_code}): {err_desc}")
                # Log result summary
                result_data = payload.get("result", payload)
                row_count = len(result_data.get("data", []))
                col_count = len(result_data.get("columns", []))
                logger.info("GQL success: %d columns, %d rows", col_count, row_count)
                return payload

            if r.status_code == 429 and attempt < max_retries:
                retry_after = int(r.headers.get("Retry-After", "0"))
                if not retry_after:
                    try:
                        msg = r.json().get("message", "")
                        if "until:" in msg:
                            ts_str = msg.split("until:")[1].strip().rstrip(")")
                            ts_str = ts_str.replace("(UTC", "").strip()
                            blocked_until = datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")
                            blocked_until = blocked_until.replace(tzinfo=timezone.utc)
                            wait = (blocked_until - datetime.now(timezone.utc)).total_seconds()
                            retry_after = max(int(wait) + 1, 3)
                    except Exception:
                        logger.debug("Could not parse Retry-After timestamp from 429 body, using fallback")
                retry_after = max(retry_after, 10 * attempt)
                logger.info("429 rate-limited, retrying in %ds (attempt %d/%d)", retry_after, attempt, max_retries)
                await asyncio.sleep(retry_after)
                continue

            # Non-retryable error
            logger.error(
                "GQL non-retryable error: HTTP %d\nQuery:\n%s\nResponse body:\n%s",
                r.status_code, query, r.text[:2000],
            )
            raise HTTPException(
                status_code=r.status_code,
                detail=f"Fabric GraphModel API error (HTTP {r.status_code}): {r.text[:1000]}",
            )

    raise HTTPException(status_code=429, detail="Rate-limited after max retries")


# ---------------------------------------------------------------------------
# KQL helpers
# ---------------------------------------------------------------------------

_kusto_lock = threading.Lock()
_kusto_client: KustoClient | None = None
_kusto_client_uri: str = ""


def _get_kusto_client(uri: str) -> KustoClient:
    """Return a cached KustoClient if the URI matches, otherwise create a new one (thread-safe)."""
    global _kusto_client, _kusto_client_uri
    with _kusto_lock:
        if _kusto_client is None or uri != _kusto_client_uri:
            kcsb = KustoConnectionStringBuilder.with_azure_token_credential(uri, credential)
            _kusto_client = KustoClient(kcsb)
            _kusto_client_uri = uri
        return _kusto_client


def _execute_kql(
    query: str,
    eventhouse_query_uri: str = "",
    kql_db_name: str = "",
) -> dict:
    """Execute a KQL query and return structured results."""
    import time as _time
    uri = eventhouse_query_uri or EVENTHOUSE_QUERY_URI
    db = kql_db_name or KQL_DB_NAME
    logger.info("KQL request: db=%s  uri=%s", db, uri)
    logger.debug("KQL query:\n%s", query)
    client = _get_kusto_client(uri)
    t0 = _time.time()
    response = client.execute(db, query)
    elapsed_ms = (_time.time() - t0) * 1000
    primary = response.primary_results[0] if response.primary_results else None
    if primary is None:
        logger.warning("KQL returned no primary results (%.0fms)", elapsed_ms)
        return {"columns": [], "rows": []}

    columns = [
        {"name": col.column_name, "type": col.column_type}
        for col in primary.columns
    ]
    rows = []
    for row in primary:
        row_dict = {}
        for col in primary.columns:
            val = row[col.column_name]
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            row_dict[col.column_name] = val
        rows.append(row_dict)

    logger.info("KQL success: %d columns, %d rows  (%.0fms)", len(columns), len(rows), elapsed_ms)
    return {"columns": columns, "rows": rows}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post(
    "/query/graph",
    response_model=GraphQueryResponse,
    responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    summary="Execute a GQL query against the Fabric ontology graph",
    description=(
        "Submits a GQL (Graph Query Language) query to the Fabric GraphModel Execute Query API. "
        "Returns columns and data rows. Retries automatically on 429 rate-limits."
    ),
)
async def query_graph(req: GraphQueryRequest):
    logger.info(
        "POST /query/graph — query=%.200s  ws=%s  gm=%s",
        req.query, req.workspace_id or WORKSPACE_ID, req.graph_model_id or GRAPH_MODEL_ID,
    )
    ws = req.workspace_id or WORKSPACE_ID
    gm = req.graph_model_id or GRAPH_MODEL_ID
    if not ws or not gm:
        raise HTTPException(status_code=400, detail="workspace_id and graph_model_id are required (via request body or env vars)")
    try:
        result = await _execute_gql(req.query, workspace_id=ws, graph_model_id=gm)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error in /query/graph")
        raise HTTPException(status_code=502, detail=f"Unexpected GQL error: {type(e).__name__}: {e}")

    # Normalise Fabric API response
    # The API may return {"status": "...", "result": {"columns": [...], "data": [...]}}
    # or the columns/data may be at the top level
    gql_result = result.get("result", result)
    columns = gql_result.get("columns", [])
    data = gql_result.get("data", [])
    return GraphQueryResponse(columns=columns, data=data)


@app.post(
    "/query/telemetry",
    response_model=TelemetryQueryResponse,
    responses={400: {"model": ErrorResponse}},
    summary="Execute a KQL query against the Fabric Eventhouse",
    description=(
        "Submits a KQL query to the Fabric Eventhouse (NetworkDB). "
        "Returns columns and rows of telemetry or alert data."
    ),
)
async def query_telemetry(req: TelemetryQueryRequest):
    logger.info(
        "POST /query/telemetry — query=%.200s  uri=%s  db=%s",
        req.query, req.eventhouse_query_uri or EVENTHOUSE_QUERY_URI, req.kql_db_name or KQL_DB_NAME,
    )
    uri = req.eventhouse_query_uri or EVENTHOUSE_QUERY_URI
    db = req.kql_db_name or KQL_DB_NAME
    if not uri or not db:
        raise HTTPException(status_code=400, detail="eventhouse_query_uri and kql_db_name are required (via request body or env vars)")
    try:
        result = await asyncio.to_thread(_execute_kql, req.query, eventhouse_query_uri=uri, kql_db_name=db)
    except KustoServiceError as e:
        raise HTTPException(status_code=400, detail=f"KQL query error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KQL backend error: {type(e).__name__}: {e}")
    return TelemetryQueryResponse(columns=result["columns"], rows=result["rows"])


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
_sse_handler.setLevel(logging.INFO)
_sse_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_sse_handler.addFilter(lambda r: r.name.startswith(("fabric-query-api", "azure", "uvicorn")))
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


@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "service": "fabric-query-api", "version": app.version}


if os.getenv("DEBUG_ENDPOINTS") == "1":
    @app.post("/debug/raw-gql", summary="Debug: raw GQL response")
    async def debug_raw_gql(req: GraphQueryRequest):
        """Return the raw Fabric API response for debugging."""
        ws = req.workspace_id or WORKSPACE_ID
        gm = req.graph_model_id or GRAPH_MODEL_ID
        if not ws or not gm:
            raise HTTPException(status_code=400, detail="workspace_id and graph_model_id required")
        result = await _execute_gql(req.query, workspace_id=ws, graph_model_id=gm)
        return result
