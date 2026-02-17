"""
Router: POST /query/graph — dispatches to the configured graph backend.

Supports per-request graph selection via the X-Graph header (ScenarioContext).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Depends

from backends import get_backend_for_context, close_all_backends, GraphBackend
from config import GRAPH_BACKEND, ScenarioContext, get_scenario_context
from models import GraphQueryRequest, GraphQueryResponse

logger = logging.getLogger("graph-query-api")

router = APIRouter()


async def close_graph_backend() -> None:
    """Shut down all cached backends (called during app lifespan shutdown)."""
    await close_all_backends()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/query/graph",
    response_model=GraphQueryResponse,
    summary="Execute a graph query",
    description=(
        "Dispatches to the configured graph backend "
        "(Cosmos DB Gremlin or mock) and returns columns + data. "
        "Use the X-Graph header to target a specific scenario's graph. "
        "If the query has a syntax error, the response will contain an "
        "'error' field with the details — read it, fix your query, and retry."
    ),
)
async def query_graph(
    req: GraphQueryRequest,
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    backend = get_backend_for_context(ctx)
    logger.info(
        "POST /query/graph — backend=%s graph=%s  query=%.200s",
        ctx.backend_type, ctx.graph_name, req.query,
    )
    try:
        result = await backend.execute_query(
            req.query,
        )
    except NotImplementedError as e:
        logger.warning("Graph backend not implemented (returning 200 with error body): %s", e)
        return GraphQueryResponse(
            error=f"Backend not implemented: {e}. This backend is not yet available.",
        )
    except HTTPException as e:
        logger.warning("Graph query HTTP error (returning 200 with error body): %s %s", e.status_code, e.detail)
        return GraphQueryResponse(
            error=f"Graph query error (HTTP {e.status_code}): {e.detail}. Read the error, fix the query, and retry.",
        )
    except Exception as e:
        logger.exception("Graph query error (returning 200 with error body)")
        return GraphQueryResponse(
            error=f"Graph query error: {type(e).__name__}: {e}. Read the error, fix the query, and retry.",
        )
    return GraphQueryResponse(
        columns=result.get("columns", []),
        data=result.get("data", []),
    )
