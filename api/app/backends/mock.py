"""
Mock graph backend — static responses for offline/disconnected demos.

Set GRAPH_BACKEND=mock to select this backend. Returns canned topology
data without any external dependency.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("graph-query-api")

# ---------------------------------------------------------------------------
# Load canned topology data from JSON fixture
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mock_topology.json"
try:
    _fixture = json.loads(_FIXTURE_PATH.read_text())
    _CORE_ROUTERS = _fixture["core_routers"]
    _CORE_ROUTER_COLUMNS = _fixture["core_router_columns"]
    _TOPOLOGY_NODES: list[dict] = _fixture["topology_nodes"]
    _TOPOLOGY_EDGES: list[dict] = _fixture["topology_edges"]
except (FileNotFoundError, json.JSONDecodeError, KeyError) as _e:
    import logging as _log
    _log.getLogger("graph-query-api").warning("Mock fixture not found or invalid: %s", _e)
    _CORE_ROUTERS = []
    _CORE_ROUTER_COLUMNS = []
    _TOPOLOGY_NODES = []
    _TOPOLOGY_EDGES = []


class MockGraphBackend:
    """Graph backend returning static topology data for offline demos."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Return static topology data for any query.

        Pattern-matches a few common queries; returns a generic info
        row for anything unrecognised.
        """
        q_lower = query.lower()
        logger.info("Mock backend received query: %.200s", query)

        # Simple pattern matching for common demo queries
        if "corerouter" in q_lower or "core router" in q_lower or "all routers" in q_lower:
            return {"columns": _CORE_ROUTER_COLUMNS, "data": _CORE_ROUTERS}

        # Default: echo the query back
        return {
            "columns": [{"name": "info", "type": "string"}],
            "data": [{"info": f"Mock backend received query: {query[:200]}"}],
        }

    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Return full or filtered static topology data."""
        logger.info("Mock get_topology — vertex_labels=%s", vertex_labels)
        nodes = _TOPOLOGY_NODES
        edges = _TOPOLOGY_EDGES

        if vertex_labels:
            label_set = set(vertex_labels)
            nodes = [n for n in nodes if n["label"] in label_set]
            node_ids = {n["id"] for n in nodes}
            edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

        return {"nodes": nodes, "edges": edges}

    async def ingest(self, vertices, edges, **kwargs):
        """Mock ingest — just return counts without storing."""
        return {"vertices_loaded": len(vertices), "edges_loaded": len(edges), "errors": []}

    async def ping(self) -> dict:
        """Mock ping — always succeeds."""
        return {"ok": True, "query": "(mock)", "detail": "Mock backend always healthy", "latency_ms": 0}

    def close(self) -> None:
        pass
