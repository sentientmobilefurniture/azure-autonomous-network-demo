"""
Router: POST /query/telemetry — SQL queries against Cosmos DB NoSQL containers.

Telemetry data (AlertStream, LinkTelemetry) is stored in a Cosmos DB NoSQL
database.  The agent writes Cosmos SQL queries (SELECT / FROM / WHERE / etc.)
which are forwarded to the appropriate container.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError
from fastapi import APIRouter

from config import (
    COSMOS_NOSQL_ENDPOINT,
    COSMOS_NOSQL_DATABASE,
    get_credential,
)
from models import TelemetryQueryRequest, TelemetryQueryResponse

logger = logging.getLogger("graph-query-api")

router = APIRouter()

# ---------------------------------------------------------------------------
# Valid container names (agents may only query these)
# ---------------------------------------------------------------------------

VALID_CONTAINERS = {"AlertStream", "LinkTelemetry"}

# ---------------------------------------------------------------------------
# Cosmos NoSQL helpers
# ---------------------------------------------------------------------------

_cosmos_lock = threading.Lock()
_cosmos_client: CosmosClient | None = None
_cosmos_endpoint: str = ""


def _get_cosmos_client(endpoint: str) -> CosmosClient:
    """Return a cached CosmosClient, creating a new one if endpoint changes."""
    global _cosmos_client, _cosmos_endpoint
    with _cosmos_lock:
        if _cosmos_client is None or endpoint != _cosmos_endpoint:
            # Close the old client if endpoint changed to avoid resource leak
            if _cosmos_client is not None:
                try:
                    _cosmos_client.close()
                except Exception:
                    pass
            _cosmos_client = CosmosClient(url=endpoint, credential=get_credential())
            _cosmos_endpoint = endpoint
        return _cosmos_client


def close_telemetry_backend() -> None:
    """Close the cached CosmosClient (called during app lifespan shutdown)."""
    global _cosmos_client
    with _cosmos_lock:
        if _cosmos_client is not None:
            try:
                _cosmos_client.close()
            except Exception:
                pass
            _cosmos_client = None


def _execute_cosmos_sql(
    query: str,
    container_name: str,
    cosmos_endpoint: str = "",
    cosmos_database: str = "",
) -> dict:
    """Execute a Cosmos SQL query against a named container and return structured results."""
    import time as _time  # TODO: move to module level when convenient

    endpoint = cosmos_endpoint or COSMOS_NOSQL_ENDPOINT
    db_name = cosmos_database or COSMOS_NOSQL_DATABASE

    logger.info("Cosmos SQL request: db=%s  container=%s  endpoint=%s", db_name, container_name, endpoint)
    logger.debug("Cosmos SQL query:\n%s", query)

    client = _get_cosmos_client(endpoint)
    database = client.get_database_client(db_name)
    container = database.get_container_client(container_name)

    t0 = _time.time()
    items = list(container.query_items(
        query=query,
        enable_cross_partition_query=True,
    ))
    elapsed_ms = (_time.time() - t0) * 1000

    if not items:
        logger.info("Cosmos SQL returned 0 rows (%.0fms)", elapsed_ms)
        return {"columns": [], "rows": []}

    # Derive column metadata from first row (Cosmos returns JSON docs)
    first = items[0]
    # Exclude Cosmos system properties
    system_keys = {"_rid", "_self", "_etag", "_attachments", "_ts"}
    columns = [
        {"name": k, "type": type(v).__name__}
        for k, v in first.items()
        if k not in system_keys
    ]
    col_names = {c["name"] for c in columns}

    rows = [
        {k: v for k, v in item.items() if k in col_names}
        for item in items
    ]

    logger.info("Cosmos SQL success: %d columns, %d rows (%.0fms)", len(columns), len(rows), elapsed_ms)
    return {"columns": columns, "rows": rows}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/query/telemetry",
    response_model=TelemetryQueryResponse,
    summary="Execute a SQL query against telemetry data in Cosmos DB",
    description=(
        "Submits a Cosmos SQL query to a telemetry container (AlertStream or "
        "LinkTelemetry) in Azure Cosmos DB NoSQL. Returns columns and rows. "
        "If the query has a syntax error, the response will contain an "
        "'error' field with the details — read it, fix your query, and retry."
    ),
)
async def query_telemetry(req: TelemetryQueryRequest):
    logger.info(
        "POST /query/telemetry — container=%s  query=%.200s",
        req.container_name, req.query,
    )
    endpoint = COSMOS_NOSQL_ENDPOINT
    db = COSMOS_NOSQL_DATABASE
    if not endpoint or not db:
        return TelemetryQueryResponse(
            columns=[],
            rows=[],
            error="Cosmos NoSQL endpoint and database name are required (set COSMOS_NOSQL_ENDPOINT and COSMOS_NOSQL_DATABASE env vars)",
        )
    if req.container_name not in VALID_CONTAINERS:
        return TelemetryQueryResponse(
            columns=[],
            rows=[],
            error=f"Invalid container_name '{req.container_name}'. Must be one of: {', '.join(sorted(VALID_CONTAINERS))}",
        )
    try:
        result = await asyncio.to_thread(
            _execute_cosmos_sql,
            req.query,
            container_name=req.container_name,
            cosmos_endpoint=endpoint,
            cosmos_database=db,
        )
    except CosmosHttpResponseError as e:
        logger.warning("Cosmos SQL query error (returning 200 with error body): %s", e)
        return TelemetryQueryResponse(
            columns=[],
            rows=[],
            error=f"Cosmos SQL query error: {e.message}. Read the error, fix the query syntax, and retry.",
        )
    except Exception as e:
        logger.exception("Cosmos SQL backend error (returning 200 with error body)")
        return TelemetryQueryResponse(
            columns=[],
            rows=[],
            error=f"Cosmos SQL backend error: {type(e).__name__}: {e}. Try simplifying the query and retry.",
        )
    return TelemetryQueryResponse(columns=result["columns"], rows=result["rows"])
