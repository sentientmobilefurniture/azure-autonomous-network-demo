"""
Azure Cosmos DB for Apache Gremlin backend.

Set GRAPH_BACKEND=cosmosdb to select this backend.
Uses the gremlinpython SDK (sync client wrapped via asyncio.to_thread)
with GraphSON v2 serializer over WSS.

Auth: Primary key based (Gremlin wire protocol does NOT support
DefaultAzureCredential — unlike the Cosmos DB NoSQL API).

Supports multiple graph targets via the graph_name constructor parameter.
Each CosmosDBGremlinBackend instance manages its own Gremlin client
targeting a specific /dbs/{db}/colls/{graph} path.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from gremlin_python.driver import client, serializer
from gremlin_python.driver.protocol import GremlinServerError
from aiohttp import WSServerHandshakeError

from config import (
    COSMOS_GREMLIN_ENDPOINT,
    COSMOS_GREMLIN_PRIMARY_KEY,
    COSMOS_GREMLIN_DATABASE,
    COSMOS_GREMLIN_GRAPH,
)

logger = logging.getLogger("graph-query-api")


# ---------------------------------------------------------------------------
# Result normalisation helpers
# ---------------------------------------------------------------------------


def _flatten_valuemap(entry: dict) -> dict:
    """Flatten a Gremlin valueMap(true) result into a simple dict.

    valueMap(true) returns {T.id: '...', T.label: '...', 'Prop': ['val']}.
    We flatten single-element lists and translate T.id/T.label.
    """
    flat: dict = {}
    for k, v in entry.items():
        # Handle T.id and T.label enum keys
        key = str(k)
        if key.startswith("T."):
            key = key[2:]  # T.id -> id, T.label -> label
        # Flatten single-element lists produced by valueMap
        if isinstance(v, list) and len(v) == 1:
            flat[key] = v[0]
        else:
            flat[key] = v
    return flat


def _normalise_results(raw_results: list) -> dict:
    """Convert Gremlin results to {columns, data} matching GraphQueryResponse.

    Handles these common Gremlin return shapes:
      - list of dicts  (from valueMap, project, elementMap)
      - list of scalars (from count, values, id)
      - list of paths   (from path())
      - single scalar   (from count())
    """
    if not raw_results:
        return {"columns": [], "data": []}

    first = raw_results[0]

    # --- dict results (valueMap / project / elementMap) ---
    if isinstance(first, dict):
        rows = [_flatten_valuemap(r) if isinstance(r, dict) else {"value": r}
                for r in raw_results]
        # Derive columns from the union of all keys
        all_keys: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    all_keys.append(k)
                    seen.add(k)
        columns = [{"name": k, "type": "String"} for k in all_keys]
        return {"columns": columns, "data": rows}

    # --- scalar results (count / values) ---
    if isinstance(first, (int, float, str, bool)):
        return {
            "columns": [{"name": "value", "type": type(first).__name__}],
            "data": [{"value": r} for r in raw_results],
        }

    # --- fallback: stringify ---
    return {
        "columns": [{"name": "result", "type": "String"}],
        "data": [{"result": str(r)} for r in raw_results],
    }


# ---------------------------------------------------------------------------
# Backend class
# ---------------------------------------------------------------------------


class CosmosDBGremlinBackend:
    """Graph backend using Azure Cosmos DB for Apache Gremlin.

    Each instance targets a specific graph via its own Gremlin client.
    Supports parameterized graph_name for multi-scenario routing.
    """

    def __init__(self, graph_name: str | None = None):
        self._graph_name = graph_name or COSMOS_GREMLIN_GRAPH
        self._lock = threading.Lock()
        self._client: client.Client | None = None
        logger.info("CosmosDBGremlinBackend created for graph '%s'", self._graph_name)

    def _get_client(self) -> client.Client:
        """Get or create the Gremlin client for this backend's graph (thread-safe)."""
        with self._lock:
            if self._client is None:
                if not COSMOS_GREMLIN_ENDPOINT or not COSMOS_GREMLIN_PRIMARY_KEY:
                    raise RuntimeError(
                        "COSMOS_GREMLIN_ENDPOINT and COSMOS_GREMLIN_PRIMARY_KEY must be set "
                        "when GRAPH_BACKEND=cosmosdb"
                    )
                url = f"wss://{COSMOS_GREMLIN_ENDPOINT}:443/"
                username = f"/dbs/{COSMOS_GREMLIN_DATABASE}/colls/{self._graph_name}"
                logger.info("Connecting to Cosmos DB Gremlin: %s (db=%s, graph=%s)",
                            COSMOS_GREMLIN_ENDPOINT, COSMOS_GREMLIN_DATABASE, self._graph_name)
                self._client = client.Client(
                    url=url,
                    traversal_source="g",
                    username=username,
                    password=COSMOS_GREMLIN_PRIMARY_KEY,
                    message_serializer=serializer.GraphSONSerializersV2d0(),
                )
        return self._client

    def _submit_query(self, query: str, max_retries: int = 3) -> list:
        """Submit a Gremlin query with retry on 429 / transient / connection errors."""
        for attempt in range(1, max_retries + 1):
            gremlin_client = self._get_client()
            t0 = time.time()
            try:
                callback = gremlin_client.submit(message=query, bindings={})
                results = callback.all().result()
                elapsed_ms = (time.time() - t0) * 1000
                logger.info(
                    "Gremlin OK [%s]: %d results in %.0fms (attempt %d/%d)  query=%.200s",
                    self._graph_name, len(results), elapsed_ms, attempt, max_retries, query,
                )
                return results
            except WSServerHandshakeError as e:
                elapsed_ms = (time.time() - t0) * 1000
                logger.error(
                    "Gremlin auth failure (401) [%s] in %.0fms: %s",
                    self._graph_name, elapsed_ms, e,
                )
                raise RuntimeError(
                    f"Cosmos DB Gremlin authentication failed: {e}. "
                    "Verify COSMOS_GREMLIN_ENDPOINT and COSMOS_GREMLIN_PRIMARY_KEY."
                ) from e
            except GremlinServerError as e:
                elapsed_ms = (time.time() - t0) * 1000
                status = getattr(e, "status_code", 0)
                logger.warning(
                    "GremlinServerError %s [%s] in %.0fms (attempt %d/%d): %s",
                    status, self._graph_name, elapsed_ms, attempt, max_retries, e,
                )
                if status in (429, 408) and attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.info("Retrying in %ds...", backoff)
                    time.sleep(backoff)
                    continue
                raise
            except Exception as e:
                elapsed_ms = (time.time() - t0) * 1000
                logger.warning(
                    "Gremlin connection error [%s] in %.0fms (attempt %d/%d): %s: %s",
                    self._graph_name, elapsed_ms, attempt, max_retries, type(e).__name__, e,
                )
                with self._lock:
                    if self._client is gremlin_client:
                        try:
                            gremlin_client.close()
                        except Exception:
                            pass
                        self._client = None
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.info("Reconnecting in %ds...", backoff)
                    time.sleep(backoff)
                    continue
                raise
        raise RuntimeError("Exhausted retries for Gremlin query")

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a Gremlin query against Cosmos DB.

        The gremlinpython client is synchronous so we run it in a thread
        to avoid blocking the FastAPI event loop.

        Returns:
            dict with "columns" and "data" matching GraphQueryResponse.
        """
        raw_results = await asyncio.to_thread(self._submit_query, query)
        return _normalise_results(raw_results)

    # ----- topology endpoint support -----------------------------------

    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Return nodes + edges for the graph topology viewer.

        Uses two Gremlin queries:
          1) g.V()… → vertex id, label, properties
          2) g.E()… → edge id, label, source/target ids, properties

        Supports optional *vertex_labels* filtering via hasLabel().
        The *query* parameter is reserved for future free-form Gremlin but
        is currently unsupported for safety — callers should use
        vertex_labels instead.
        """
        if query:
            raise ValueError(
                "Free-form topology queries are not yet supported. "
                "Use vertex_labels to filter."
            )

        # Build vertex / edge traversals, optionally filtered by label
        if vertex_labels:
            label_csv = ", ".join(f"'{lbl}'" for lbl in vertex_labels)
            v_query = (
                f"g.V().hasLabel({label_csv})"
                ".project('id','label','properties')"
                ".by(id).by(label).by(valueMap())"
            )
            # Edges: both endpoints must be in the filtered label set
            e_query = (
                f"g.V().hasLabel({label_csv}).bothE()"
                ".where(otherV().hasLabel({label_csv}))"
                ".project('id','label','source','target','properties')"
                ".by(id).by(label).by(outV().id()).by(inV().id()).by(valueMap())"
            )
        else:
            v_query = (
                "g.V()"
                ".project('id','label','properties')"
                ".by(id).by(label).by(valueMap())"
            )
            e_query = (
                "g.E()"
                ".project('id','label','source','target','properties')"
                ".by(id).by(label).by(outV().id()).by(inV().id()).by(valueMap())"
            )

        raw_vertices, raw_edges = await asyncio.gather(
            asyncio.to_thread(self._submit_query, v_query),
            asyncio.to_thread(self._submit_query, e_query),
        )

        # Flatten Gremlin valueMap lists inside properties
        nodes = []
        for v in raw_vertices:
            props = v.get("properties", {})
            nodes.append({
                "id": str(v["id"]),
                "label": v["label"],
                "properties": _flatten_valuemap(props) if isinstance(props, dict) else {},
            })

        edges = []
        for e in raw_edges:
            props = e.get("properties", {})
            edges.append({
                "id": str(e["id"]),
                "source": str(e["source"]),
                "target": str(e["target"]),
                "label": e["label"],
                "properties": _flatten_valuemap(props) if isinstance(props, dict) else {},
            })

        return {"nodes": nodes, "edges": edges}

    def close(self) -> None:
        """Close this backend's Gremlin client (thread-safe)."""
        with self._lock:
            if self._client is not None:
                logger.info("Closing Cosmos DB Gremlin client for graph '%s'", self._graph_name)
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
