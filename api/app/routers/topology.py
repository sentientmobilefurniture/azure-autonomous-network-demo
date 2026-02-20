"""
Router: POST /query/topology — returns graph topology for the frontend viewer.

Returns {nodes, edges, meta} instead of the tabular {columns, data} shape
used by /query/graph (which is designed for agent consumption).

Supports two modes via TOPOLOGY_SOURCE env var:
  - "static" (default): reads pre-built topology.json — instant, no Fabric dependency
  - "live": queries Fabric Graph (GQL) at runtime — slower, cold-start prone
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter

from app.backends import get_backend_for_context
from app.gq_config import TOPOLOGY_SOURCE, get_scenario_context
from app.data_models import TopologyRequest, TopologyResponse, TopologyMeta

logger = logging.getLogger("graph-query-api")

router = APIRouter()

# ---------------------------------------------------------------------------
# Static topology — loaded once at startup from pre-built JSON
# ---------------------------------------------------------------------------
_STATIC_TOPO_PATH = Path(__file__).parent.parent / "backends" / "fixtures" / "topology.json"
_static_topo: dict | None = None


def _load_static_topology() -> dict | None:
    """Load pre-built topology JSON file. Returns None if missing."""
    if _STATIC_TOPO_PATH.exists():
        data = json.loads(_STATIC_TOPO_PATH.read_text())
        nodes = data.get("topology_nodes", [])
        edges = data.get("topology_edges", [])
        logger.info(
            "Loaded static topology: %d nodes, %d edges from %s",
            len(nodes), len(edges), _STATIC_TOPO_PATH,
        )
        return {"nodes": nodes, "edges": edges}
    logger.warning("Static topology file not found: %s", _STATIC_TOPO_PATH)
    return None


# Load at import time (module startup)
if TOPOLOGY_SOURCE == "static":
    _static_topo = _load_static_topology()
    if _static_topo:
        logger.info("TOPOLOGY_SOURCE=static — serving pre-built topology")
    else:
        logger.warning(
            "TOPOLOGY_SOURCE=static but topology.json not found — "
            "will fall back to live backend queries"
        )
else:
    logger.info("TOPOLOGY_SOURCE=live — topology will be queried from graph backend")

# ---------------------------------------------------------------------------
# TTL cache — keyed by "graph_name:label1,label2,..."
# Only used when TOPOLOGY_SOURCE=live
# Values: (expires_at, original_query_ms, response_dict)
# ---------------------------------------------------------------------------
_topo_cache: dict[str, tuple[float, float, dict]] = {}
_topo_lock = asyncio.Lock()
TOPO_TTL = 30  # seconds


def _serve_static(req: TopologyRequest) -> TopologyResponse:
    """Return topology from the pre-built JSON file, with optional label filtering."""
    assert _static_topo is not None
    nodes = _static_topo["nodes"]
    edges = _static_topo["edges"]

    if req.vertex_labels:
        label_set = set(req.vertex_labels)
        nodes = [n for n in nodes if n["label"] in label_set]
        node_ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    sorted_labels = sorted({n["label"] for n in nodes})
    return TopologyResponse(
        nodes=nodes,
        edges=edges,
        meta=TopologyMeta(
            node_count=len(nodes),
            edge_count=len(edges),
            query_time_ms=0,
            labels=sorted_labels,
            cached=True,
        ),
    )


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
    # ── Static path: serve from pre-built JSON (default) ──────────
    if TOPOLOGY_SOURCE == "static" and _static_topo is not None:
        logger.debug("POST /query/topology — serving from static topology.json")
        return _serve_static(req)

    # ── Live path: query graph backend (Fabric GQL / mock) ────────
    ctx = get_scenario_context()
    backend = get_backend_for_context(ctx)

    # Normalise cache key: None and [] both mean "all vertices" → same key
    labels = sorted(req.vertex_labels) if req.vertex_labels else []
    cache_key = f"{ctx.graph_name}:{','.join(labels)}"

    # Check cache
    async with _topo_lock:
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
        async with _topo_lock:
            _topo_cache[cache_key] = (
                time.time() + TOPO_TTL,
                round(elapsed, 1),
                response.model_dump(),
            )
        return response
    except Exception as exc:
        logger.exception("Topology query failed: %s", exc)
        return TopologyResponse(error=str(exc))
