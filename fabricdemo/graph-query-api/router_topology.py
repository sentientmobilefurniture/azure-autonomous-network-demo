"""
Router: POST /query/topology — returns graph topology for the frontend viewer.

Returns {nodes, edges, meta} instead of the tabular {columns, data} shape
used by /query/graph (which is designed for agent consumption).

Uses hardcoded ScenarioContext (no X-Graph header routing).
"""

from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter

from backends import get_backend_for_context
from config import ScenarioContext, get_scenario_context
from models import TopologyRequest, TopologyResponse, TopologyMeta

logger = logging.getLogger("graph-query-api")

router = APIRouter()

# ---------------------------------------------------------------------------
# TTL cache — keyed by "graph_name:label1,label2,..."
# Values: (expires_at, original_query_ms, response_dict)
# ---------------------------------------------------------------------------
_topo_cache: dict[str, tuple[float, float, dict]] = {}
_topo_lock = threading.Lock()
TOPO_TTL = 30  # seconds


def invalidate_topology_cache(graph_name: str | None = None) -> None:
    """Clear topology cache entries.  Called by ingest after graph mutations.

    If *graph_name* is provided only entries for that graph are removed.
    If ``None`` the entire cache is cleared.
    """
    with _topo_lock:
        if graph_name is None:
            _topo_cache.clear()
        else:
            to_delete = [k for k in _topo_cache if k.startswith(f"{graph_name}:")]
            for k in to_delete:
                del _topo_cache[k]
    logger.info("Topology cache invalidated (graph=%s)", graph_name)


@router.post(
    "/query/topology",
    response_model=TopologyResponse,
    summary="Get graph topology for visualization",
    description=(
        "Returns the graph topology as separate nodes and edges arrays, "
        "suitable for graph rendering libraries. Optionally filter by vertex labels."
    ),
)
async def topology(
    req: TopologyRequest,
) -> TopologyResponse:
    ctx = get_scenario_context()
    backend = get_backend_for_context(ctx)

    # Normalise cache key: None and [] both mean "all vertices" → same key
    labels = sorted(req.vertex_labels) if req.vertex_labels else []
    cache_key = f"{ctx.graph_name}:{','.join(labels)}"

    # Check cache
    with _topo_lock:
        hit = _topo_cache.get(cache_key)
        if hit:
            exp, orig_ms, cached_dict = hit
            if time.time() < exp:
                logger.debug("Topology cache HIT  key=%s", cache_key)
                meta = {**cached_dict["meta"], "cached": True}
                return TopologyResponse(**{**cached_dict, "meta": meta})

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
        sorted_labels = sorted({n["label"] for n in nodes})
        response = TopologyResponse(
            nodes=nodes,
            edges=edges,
            meta=TopologyMeta(
                node_count=len(nodes),
                edge_count=len(edges),
                query_time_ms=round(elapsed, 1),
                labels=sorted_labels,
                cached=False,
            ),
        )

        # Cache the DICT (not the Pydantic object) to avoid shared mutation
        with _topo_lock:
            _topo_cache[cache_key] = (
                time.time() + TOPO_TTL,
                round(elapsed, 1),
                response.model_dump(),
            )
        return response
    except Exception as exc:
        logger.exception("Topology query failed: %s", exc)
        return TopologyResponse(error=str(exc))
