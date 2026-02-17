"""
Router: POST /query/telemetry — SQL queries against Cosmos DB NoSQL containers.

Telemetry data is stored in scenario-prefixed Cosmos DB NoSQL databases.
The target database is derived from the X-Graph header via ScenarioContext.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from config import (
    ScenarioContext,
    get_scenario_context,
)
from adapters.cosmos_config import (
    COSMOS_NOSQL_ENDPOINT,
)
from stores import get_document_store
from models import TelemetryQueryRequest, TelemetryQueryResponse

logger = logging.getLogger("graph-query-api")

router = APIRouter()


def close_telemetry_backend() -> None:
    """Close the cached CosmosClient (called during app lifespan shutdown)."""
    from cosmos_helpers import close_cosmos_client
    close_cosmos_client()


# ---------------------------------------------------------------------------
# Post-processing (stays in router — the store returns raw documents)
# ---------------------------------------------------------------------------

_SYSTEM_KEYS = {"_rid", "_self", "_etag", "_attachments", "_ts"}


def _transform_telemetry_results(items: list[dict]) -> dict:
    """Transform raw documents into {columns, rows} for the API response.

    Derives column metadata from first row and excludes Cosmos system keys.
    """
    if not items:
        return {"columns": [], "rows": []}

    first = items[0]
    columns = [
        {"name": k, "type": type(v).__name__}
        for k, v in first.items()
        if k not in _SYSTEM_KEYS
    ]
    col_names = {c["name"] for c in columns}

    rows = [
        {k: v for k, v in item.items() if k in col_names}
        for item in items
    ]
    return {"columns": columns, "rows": rows}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/query/telemetry",
    response_model=TelemetryQueryResponse,
    summary="Execute a SQL query against telemetry",
    description=(
        "Submits a Cosmos SQL query to a telemetry container in Azure Cosmos "
        "DB NoSQL. The target database is derived from the X-Graph header. "
        "Returns columns and rows. If the query has a syntax error, the "
        "response will contain an 'error' field — read it, fix your query, and retry."
    ),
)
async def query_telemetry(
    req: TelemetryQueryRequest,
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    # Default: Cosmos NoSQL path
    # Prefix container name with scenario prefix for shared DB isolation
    container_name = (
        f"{ctx.telemetry_container_prefix}-{req.container_name}"
        if ctx.telemetry_container_prefix
        else req.container_name
    )
    logger.info(
        "POST /query/telemetry — db=%s  container=%s  query=%.200s",
        ctx.telemetry_database, container_name, req.query,
    )
    endpoint = COSMOS_NOSQL_ENDPOINT
    if not endpoint:
        return TelemetryQueryResponse(
            columns=[],
            rows=[],
            error="Cosmos NoSQL endpoint not configured (set COSMOS_NOSQL_ENDPOINT env var)",
        )
    try:
        store = get_document_store(
            ctx.telemetry_database, container_name, "/id",
        )
        t0 = time.time()
        items = await store.list(query=req.query)
        elapsed_ms = (time.time() - t0) * 1000
        logger.info(
            "Telemetry query: %d items (%.0fms)",
            len(items), elapsed_ms,
        )
        result = _transform_telemetry_results(items)
    except Exception as e:
        logger.exception("Cosmos SQL backend error (returning 200 with error body)")
        return TelemetryQueryResponse(
            columns=[],
            rows=[],
            error=f"Cosmos SQL backend error: {type(e).__name__}: {e}. Try simplifying the query and retry.",
        )
    return TelemetryQueryResponse(columns=result["columns"], rows=result["rows"])

