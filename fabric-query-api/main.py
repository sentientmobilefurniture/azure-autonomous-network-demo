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

import os
import logging
import time
from datetime import datetime, timezone

import requests as http_requests
from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fabric Query API",
    version="0.3.0",
    description="Runs GQL and KQL queries against Microsoft Fabric for Foundry agents.",
)

logger = logging.getLogger("fabric-query-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request and catch validation errors."""
    body = b""
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        logger.info(f"Incoming {request.method} {request.url.path} — body={body[:500]}")
    response = await call_next(request)
    if response.status_code >= 400:
        logger.warning(f"Response {response.status_code} for {request.method} {request.url.path}")
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


def _execute_gql(
    query: str,
    workspace_id: str = "",
    graph_model_id: str = "",
    max_retries: int = 3,
) -> dict:
    """Execute a GQL query with retry on 429."""
    ws = workspace_id or WORKSPACE_ID
    gm = graph_model_id or GRAPH_MODEL_ID
    url = (
        f"{FABRIC_API}/workspaces/{ws}"
        f"/GraphModels/{gm}/executeQuery"
    )
    body = {"query": query}

    for attempt in range(1, max_retries + 1):
        headers = _fabric_headers()
        r = http_requests.post(url, headers=headers, json=body, params={"beta": "True"})

        if r.status_code == 200:
            payload = r.json()
            # Fabric returns HTTP 200 even for GQL errors — check body status
            status_code = payload.get("status", {}).get("code", "")
            if status_code and not status_code.startswith("0"):
                cause = payload.get("status", {}).get("cause", {})
                err_desc = cause.get("description", payload["status"].get("description", "unknown GQL error"))
                raise HTTPException(status_code=400, detail=f"GQL error ({status_code}): {err_desc}")
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
                    pass
            retry_after = max(retry_after, 10 * attempt)
            time.sleep(retry_after)
            continue

        # Non-retryable error
        raise HTTPException(
            status_code=r.status_code,
            detail=f"Fabric GraphModel API error: {r.text[:500]}",
        )

    raise HTTPException(status_code=429, detail="Rate-limited after max retries")


# ---------------------------------------------------------------------------
# KQL helpers
# ---------------------------------------------------------------------------

_kusto_client: KustoClient | None = None


def _make_kusto_client(uri: str) -> KustoClient:
    """Create a fresh KustoClient for the given URI."""
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(uri, credential)
    return KustoClient(kcsb)


def _get_kusto_client() -> KustoClient:
    global _kusto_client
    if _kusto_client is None and EVENTHOUSE_QUERY_URI:
        _kusto_client = _make_kusto_client(EVENTHOUSE_QUERY_URI)
    return _kusto_client


def _execute_kql(
    query: str,
    eventhouse_query_uri: str = "",
    kql_db_name: str = "",
) -> dict:
    """Execute a KQL query and return structured results."""
    uri = eventhouse_query_uri or EVENTHOUSE_QUERY_URI
    db = kql_db_name or KQL_DB_NAME
    client = _get_kusto_client() if not eventhouse_query_uri else _make_kusto_client(uri)
    response = client.execute(db, query)
    primary = response.primary_results[0] if response.primary_results else None
    if primary is None:
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
    logger.info(f"POST /query/graph — query={req.query[:100]!r} ws={req.workspace_id!r} gm={req.graph_model_id!r}")
    ws = req.workspace_id or WORKSPACE_ID
    gm = req.graph_model_id or GRAPH_MODEL_ID
    if not ws or not gm:
        raise HTTPException(status_code=400, detail="workspace_id and graph_model_id are required (via request body or env vars)")
    result = _execute_gql(req.query, workspace_id=ws, graph_model_id=gm)

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
    logger.info(f"POST /query/telemetry — query={req.query[:100]!r} uri={req.eventhouse_query_uri!r} db={req.kql_db_name!r}")
    uri = req.eventhouse_query_uri or EVENTHOUSE_QUERY_URI
    db = req.kql_db_name or KQL_DB_NAME
    if not uri or not db:
        raise HTTPException(status_code=400, detail="eventhouse_query_uri and kql_db_name are required (via request body or env vars)")
    try:
        result = _execute_kql(req.query, eventhouse_query_uri=uri, kql_db_name=db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"KQL query error: {str(e)}")
    return TelemetryQueryResponse(columns=result["columns"], rows=result["rows"])


@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "service": "fabric-query-api", "version": "0.2.0"}


@app.post("/debug/raw-gql", summary="Debug: raw GQL response")
async def debug_raw_gql(req: GraphQueryRequest):
    """Return the raw Fabric API response for debugging."""
    ws = req.workspace_id or WORKSPACE_ID
    gm = req.graph_model_id or GRAPH_MODEL_ID
    if not ws or not gm:
        raise HTTPException(status_code=400, detail="workspace_id and graph_model_id required")
    result = _execute_gql(req.query, workspace_id=ws, graph_model_id=gm)
    return result
