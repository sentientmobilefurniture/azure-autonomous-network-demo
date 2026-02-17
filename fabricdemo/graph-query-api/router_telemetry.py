"""
Router: POST /query/telemetry — KQL queries against Fabric Eventhouse.

Telemetry data is queried via Fabric Eventhouse KQL.
The target scenario is derived from the X-Graph header via ScenarioContext.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from config import (
    ScenarioContext,
    get_scenario_context,
)
from models import TelemetryQueryRequest, TelemetryQueryResponse

logger = logging.getLogger("graph-query-api")

router = APIRouter()


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
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    return await _query_fabric_kql(req, ctx)


async def _query_fabric_kql(
    req: TelemetryQueryRequest,
    ctx: ScenarioContext,
) -> TelemetryQueryResponse:
    """Route telemetry queries to Fabric Eventhouse via KQL."""
    from backends.fabric_kql import FabricKQLBackend

    logger.info(
        "POST /query/telemetry [KQL] — query=%.200s",
        req.query,
    )
    try:
        backend = FabricKQLBackend()
        result = await backend.execute_query(req.query)
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
