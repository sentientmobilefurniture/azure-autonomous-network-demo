"""
Graph backend abstraction layer.

Defines the GraphBackend protocol and the get_backend() factory that
dispatches based on the GRAPH_BACKEND environment variable.

get_backend_for_context() supports per-request graph selection via
ScenarioContext (X-Graph header).
"""

from __future__ import annotations

import threading
from typing import Callable, Protocol, runtime_checkable

from config import GRAPH_BACKEND, ScenarioContext


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

    async def ingest(
        self,
        vertices: list[dict],
        edges: list[dict],
        *,
        graph_name: str,
        graph_database: str,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> dict:
        """Load vertices and edges into the graph backend.

        Args:
            vertices: List of {label, id, partition_key, properties} dicts
            edges: List of {label, source_id, target_id, properties} dicts
            graph_name: Target graph name
            graph_database: Target database name
            on_progress: Callback(message, current, total) for progress reporting

        Returns:
            {vertices_loaded: int, edges_loaded: int, errors: list[str]}
        """
        ...

    def close(self) -> None:
        """Clean up resources (connections, clients)."""
        ...

    async def ping(self) -> dict:
        """Health check — returns {"ok": bool, "query": str, "detail": str, "latency_ms": int}."""
        ...


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------

_backend_registry: dict[str, type[GraphBackend]] = {}


def register_backend(name: str, cls: type[GraphBackend]) -> None:
    """Register a GraphBackend implementation by name."""
    _backend_registry[name] = cls


def get_backend() -> GraphBackend:
    """Factory: return the correct backend based on GRAPH_BACKEND env var.

    Uses the default graph from env vars. For per-request graph selection,
    use get_backend_for_context() instead.
    """
    return get_backend_for_graph("__default__")


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
    if ctx.backend_type == "mock":
        return get_backend_for_graph("__mock__", ctx.backend_type)

    return get_backend_for_graph(ctx.graph_name, ctx.backend_type)


def get_backend_for_graph(
    graph_name: str,
    backend_type: str | None = None,
) -> GraphBackend:
    """Return a cached backend for a specific graph name."""
    bt = backend_type or GRAPH_BACKEND
    cache_key = f"{bt}:{graph_name}"

    with _backend_lock:
        if cache_key not in _backend_cache:
            if bt not in _backend_registry:
                raise ValueError(
                    f"Unknown backend: {bt!r}. "
                    f"Available: {list(_backend_registry)}"
                )
            _backend_cache[cache_key] = _backend_registry[bt](graph_name=graph_name)
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


# ---------------------------------------------------------------------------
# Auto-register known backends at module load
# ---------------------------------------------------------------------------

try:
    from .cosmosdb import CosmosDBGremlinBackend
    register_backend("cosmosdb", CosmosDBGremlinBackend)
except ImportError:
    import logging
    logging.getLogger("graph-query-api").warning(
        "CosmosDBGremlinBackend not available (missing gremlin_python?)"
    )

from .mock import MockGraphBackend  # noqa: E402
register_backend("mock", MockGraphBackend)
