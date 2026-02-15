"""
Graph backend abstraction layer.

Defines the GraphBackend protocol and the get_backend() factory that
dispatches based on the GRAPH_BACKEND environment variable.

get_backend_for_context() supports per-request graph selection via
ScenarioContext (X-Graph header).
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

from config import GRAPH_BACKEND, GraphBackendType, ScenarioContext


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
    """Factory: return the correct backend based on GRAPH_BACKEND env var.

    Uses the default graph from env vars. For per-request graph selection,
    use get_backend_for_context() instead.
    """
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


# ---------------------------------------------------------------------------
# Per-graph backend cache (for multi-scenario support)
# ---------------------------------------------------------------------------

_backend_cache: dict[str, GraphBackend] = {}
_backend_lock = threading.Lock()


def get_backend_for_context(ctx: ScenarioContext) -> GraphBackend:
    """Return a backend for the given scenario context.

    For mock backends, returns a shared singleton (graph name irrelevant).
    For cosmosdb, returns a per-graph-name cached backend.
    """
    if ctx.backend_type == GraphBackendType.MOCK:
        return get_backend_for_graph("__mock__", ctx.backend_type)

    return get_backend_for_graph(ctx.graph_name, ctx.backend_type)


def get_backend_for_graph(
    graph_name: str,
    backend_type: GraphBackendType | None = None,
) -> GraphBackend:
    """Return a cached backend for a specific graph name."""
    bt = backend_type or GRAPH_BACKEND
    cache_key = f"{bt.value}:{graph_name}"

    with _backend_lock:
        if cache_key not in _backend_cache:
            if bt == GraphBackendType.COSMOSDB:
                from .cosmosdb import CosmosDBGremlinBackend
                _backend_cache[cache_key] = CosmosDBGremlinBackend(graph_name=graph_name)
            elif bt == GraphBackendType.MOCK:
                from .mock import MockGraphBackend
                _backend_cache[cache_key] = MockGraphBackend()
            else:
                raise ValueError(f"Unknown backend type: {bt}")
        return _backend_cache[cache_key]


async def close_all_backends() -> None:
    """Close all cached backends (called during app lifespan shutdown)."""
    import inspect
    with _backend_lock:
        for backend in _backend_cache.values():
            result = backend.close()
            if inspect.isawaitable(result):
                await result
        _backend_cache.clear()
