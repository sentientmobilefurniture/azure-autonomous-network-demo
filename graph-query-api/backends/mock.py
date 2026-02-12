"""
Mock graph backend — static responses for offline/disconnected demos.

Set GRAPH_BACKEND=mock to select this backend. Returns canned topology
data without any external dependency.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("graph-query-api")

# ---------------------------------------------------------------------------
# Canned topology data (subset of the full ontology)
# ---------------------------------------------------------------------------

_CORE_ROUTERS = [
    {"RouterId": "CORE-SYD-01", "City": "Sydney", "Region": "NSW", "Vendor": "Cisco", "Model": "ASR-9922"},
    {"RouterId": "CORE-MEL-01", "City": "Melbourne", "Region": "VIC", "Vendor": "Cisco", "Model": "ASR-9922"},
    {"RouterId": "CORE-BNE-01", "City": "Brisbane", "Region": "QLD", "Vendor": "Juniper", "Model": "MX10008"},
]

_CORE_ROUTER_COLUMNS = [
    {"name": "RouterId", "type": "string"},
    {"name": "City", "type": "string"},
    {"name": "Region", "type": "string"},
    {"name": "Vendor", "type": "string"},
    {"name": "Model", "type": "string"},
]


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

    def close(self) -> None:
        pass
