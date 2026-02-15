"""
Router: POST /query/topology — returns graph topology for the frontend viewer.

Returns {nodes, edges, meta} instead of the tabular {columns, data} shape
used by /query/graph (which is designed for agent consumption).

Supports per-request graph selection via the X-Graph header (ScenarioContext).
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from backends import get_backend_for_context
from config import ScenarioContext, get_scenario_context
from models import TopologyRequest, TopologyResponse, TopologyMeta

logger = logging.getLogger("graph-query-api")

router = APIRouter()


@router.post(
    "/query/topology",
    response_model=TopologyResponse,
    summary="Get graph topology for visualization",
    description=(
        "Returns the graph topology as separate nodes and edges arrays, "
        "suitable for graph rendering libraries. Optionally filter by vertex labels. "
        "Use the X-Graph header to target a specific scenario's graph."
    ),
)
async def topology(
    req: TopologyRequest,
    ctx: ScenarioContext = Depends(get_scenario_context),
) -> TopologyResponse:
    backend = get_backend_for_context(ctx)
    logger.info(
        "POST /query/topology — graph=%s  vertex_labels=%s  query=%s",
        ctx.graph_name,
        req.vertex_labels,
        f"{req.query[:100]}..." if req.query else None,
    )
    t0 = time.perf_counter()
    try:
        result = await backend.get_topology(
            query=req.query,
            vertex_labels=req.vertex_labels,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
        labels = sorted({n["label"] for n in nodes})
        return TopologyResponse(
            nodes=nodes,
            edges=edges,
            meta=TopologyMeta(
                node_count=len(nodes),
                edge_count=len(edges),
                query_time_ms=round(elapsed, 1),
                labels=labels,
            ),
        )
    except Exception as exc:
        logger.exception("Topology query failed: %s", exc)
        return TopologyResponse(error=str(exc))
