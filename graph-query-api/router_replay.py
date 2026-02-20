"""
Router: Query Replay — re-execute a GQL or KQL query for visualization.

This is a fallback mechanism for interactions saved before the prompt
instrumentation (Phase 1D) was deployed. For post-migration interactions,
the frontend reads visualization data directly from the persisted StepEvent.

Endpoints:
  POST /query/replay  — replay a graph or telemetry query

The agent name determines which backend to call:
  GraphExplorerAgent  → POST /query/graph  (GQL)
  TelemetryAgent      → POST /query/telemetry (KQL)
  Others              → 400 (not replayable)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from models import ReplayRequest, GraphQueryRequest, TelemetryQueryRequest
from router_graph import query_graph
from router_telemetry import query_telemetry

logger = logging.getLogger("graph-query-api.replay")

router = APIRouter(prefix="/query", tags=["replay"])

# Map agent names to their query backend type
_AGENT_BACKEND = {
    "GraphExplorerAgent": "graph",
    "TelemetryAgent": "telemetry",
}


@router.post("/replay", summary="Replay a graph or telemetry query for visualization")
async def replay_query(req: ReplayRequest):
    backend = _AGENT_BACKEND.get(req.agent)
    if not backend:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{req.agent}' is not replayable. "
            f"Only {list(_AGENT_BACKEND.keys())} support query replay.",
        )

    if not req.query or not req.query.strip():
        raise HTTPException(
            status_code=400,
            detail="Query string is empty. Cannot replay.",
        )

    logger.info("Replaying %s query for agent=%s: %s", backend, req.agent, req.query[:200])

    try:
        if backend == "graph":
            result = await query_graph(GraphQueryRequest(query=req.query))
            # Check for error-in-200 pattern (BUG 5)
            if hasattr(result, "error") and result.error:
                return {"type": "graph", "error": result.error}
            # result is a GraphQueryResponse Pydantic model
            columns = result.columns if hasattr(result, "columns") else result.get("columns", [])
            data = result.data if hasattr(result, "data") else result.get("data", [])
            error = result.error if hasattr(result, "error") else result.get("error")
            if error:
                return {"type": "graph", "error": error}
            return {
                "type": "graph",
                "columns": columns,
                "data": data,
                "query": req.query,
            }
        else:  # telemetry
            result = await query_telemetry(TelemetryQueryRequest(query=req.query))
            rows = result.rows if hasattr(result, "rows") else result.get("rows", [])
            columns = result.columns if hasattr(result, "columns") else result.get("columns", [])
            error = result.error if hasattr(result, "error") else result.get("error")
            if error:
                return {"type": "table", "error": error}
            return {
                "type": "table",
                "columns": columns,
                "rows": rows,
                "query": req.query,
            }
    except Exception as e:
        logger.exception("Replay failed for agent=%s", req.agent)
        raise HTTPException(status_code=500, detail=f"Replay failed: {type(e).__name__}: {e}")
