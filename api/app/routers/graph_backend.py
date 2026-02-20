"""
Router: POST /query/graph — dispatches to the configured graph backend.

Uses a fixed hardcoded ScenarioContext (no X-Graph header routing).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.backends import get_backend_for_context, close_all_backends
from app.gq_config import get_scenario_context
from app.data_models import GraphQueryRequest, GraphQueryResponse

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
        "(Fabric GQL or mock) and returns columns + data. "
        "If the query has a syntax error, the response will contain an "
        "'error' field with the details — read it, fix your query, and retry."
    ),
)
async def query_graph(
    req: GraphQueryRequest,
):
    ctx = get_scenario_context()
    backend = get_backend_for_context(ctx)
    logger.info(
        "POST /query/graph — backend=%s graph=%s  query=%.200s",
        ctx.backend_type, ctx.graph_name, req.query,
    )
    try:
        result = await backend.execute_query(
            req.query,
            workspace_id=ctx.fabric_workspace_id or None,
            graph_model_id=ctx.fabric_graph_model_id or None,
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
