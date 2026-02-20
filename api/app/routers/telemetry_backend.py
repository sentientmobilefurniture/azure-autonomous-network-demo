"""
Router: POST /query/telemetry — KQL queries against Fabric Eventhouse.

Telemetry data is queried via Fabric Eventhouse KQL.
Uses hardcoded ScenarioContext (no X-Graph header routing).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.gq_config import (
    get_scenario_context,
)
from app.data_models import TelemetryQueryRequest, TelemetryQueryResponse

logger = logging.getLogger("graph-query-api")

router = APIRouter()

# Module-level singleton to preserve KustoClient cache across requests
from app.backends.fabric_kql import FabricKQLBackend  # noqa: E402
_kql_backend = FabricKQLBackend()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/query/telemetry",
    response_model=TelemetryQueryResponse,
    summary="Execute a KQL query against Fabric Eventhouse telemetry",
    description=(
        "Submits a KQL query to Fabric Eventhouse for telemetry data. "
        "Returns columns and rows. If the query has a syntax error, the "
        "response will contain an 'error' field — read it, fix your query, and retry."
    ),
)
async def query_telemetry(
    req: TelemetryQueryRequest,
):
    ctx = get_scenario_context()
    return await _query_fabric_kql(req)


async def _query_fabric_kql(
    req: TelemetryQueryRequest,
) -> TelemetryQueryResponse:
    """Route telemetry queries to Fabric Eventhouse via KQL."""
    logger.info(
        "POST /query/telemetry [KQL] — query=%.200s",
        req.query,
    )
    try:
        result = await _kql_backend.execute_query(req.query)
        if "error" in result:
            return TelemetryQueryResponse(
                columns=[], rows=[],
                error=result.get("detail", "KQL query failed"),
            )
        return TelemetryQueryResponse(
            columns=result.get("columns", []),
            rows=result.get("rows", []),
        )
    except Exception as e:
        logger.exception("KQL backend error")
        return TelemetryQueryResponse(
            columns=[], rows=[],
            error=f"KQL backend error: {type(e).__name__}: {e}",
        )
