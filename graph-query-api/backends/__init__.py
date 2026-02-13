"""
Graph backend abstraction layer.

Defines the GraphBackend protocol and the get_backend() factory that
dispatches based on the GRAPH_BACKEND environment variable.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from config import GRAPH_BACKEND, GraphBackendType


@runtime_checkable
class GraphBackend(Protocol):
    """Interface that all graph backends must implement."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a graph query and return {columns: [...], data: [...]}.

        The query language depends on the backend:
        - cosmosdb:  Gremlin (string-based, no bytecode)
        - mock:      natural language or predefined keys

        Returns:
            dict with "columns" (list of {name, type}) and "data" (list of dicts)
        """
        ...

    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Return full or filtered graph topology as {nodes: [...], edges: [...]}.

        Each node: {id, label, properties}
        Each edge: {id, source, target, label, properties}
        """
        ...

    def close(self) -> None:
        """Clean up resources (connections, clients)."""
        ...


def get_backend() -> GraphBackend:
    """Factory: return the correct backend based on GRAPH_BACKEND env var."""
    if GRAPH_BACKEND == GraphBackendType.COSMOSDB:
        from .cosmosdb import CosmosDBGremlinBackend
        return CosmosDBGremlinBackend()
    elif GRAPH_BACKEND == GraphBackendType.MOCK:
        from .mock import MockGraphBackend
        return MockGraphBackend()
    else:
        raise ValueError(
            f"Unknown GRAPH_BACKEND: {GRAPH_BACKEND!r}. "
            f"Valid options: cosmosdb, mock"
        )
