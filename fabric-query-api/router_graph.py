"""
Router: POST /query/graph — dispatches to the configured graph backend.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backends import get_backend, GraphBackend
from config import GRAPH_BACKEND
from models import GraphQueryRequest, GraphQueryResponse

logger = logging.getLogger("fabric-query-api")

router = APIRouter()

# ---------------------------------------------------------------------------
# Lazy-initialised backend singleton
# ---------------------------------------------------------------------------

_backend: GraphBackend | None = None


def get_graph_backend() -> GraphBackend:
    """Return (and cache) the graph backend for the configured GRAPH_BACKEND."""
    global _backend
    if _backend is None:
        _backend = get_backend()
        logger.info("Initialised graph backend: %s", GRAPH_BACKEND.value)
    return _backend


def close_graph_backend() -> None:
    """Shut down the cached backend (called during app lifespan shutdown)."""
    global _backend
    if _backend is not None:
        _backend.close()
        _backend = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/query/graph",
    response_model=GraphQueryResponse,
    summary="Execute a graph query",
    description=(
        "Dispatches to the configured graph backend "
        "(Fabric GQL, Cosmos DB Gremlin, or mock) and returns columns + data. "
        "If the query has a syntax error, the response will contain an "
        "'error' field with the details — read it, fix your query, and retry."
    ),
)
async def query_graph(req: GraphQueryRequest):
    backend = get_graph_backend()
    logger.info(
        "POST /query/graph — backend=%s  query=%.200s",
        GRAPH_BACKEND.value, req.query,
    )
    try:
        result = await backend.execute_query(
            req.query,
            workspace_id=req.workspace_id,
            graph_model_id=req.graph_model_id,
        )
    except NotImplementedError as e:
        logger.warning("Graph backend not implemented (returning 200 with error body): %s", e)
        return GraphQueryResponse(
            error=f"Backend not implemented: {e}. This backend is not yet available.",
        )
    except HTTPException as e:
        # Catch HTTPExceptions from backends (GQL errors, rate limits, config errors)
        # and surface them as 200 + error payload so the agent LLM can read & retry
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
