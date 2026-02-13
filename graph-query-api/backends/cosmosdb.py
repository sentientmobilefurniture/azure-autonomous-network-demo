"""
Azure Cosmos DB for Apache Gremlin backend.

Set GRAPH_BACKEND=cosmosdb to select this backend.
Uses the gremlinpython SDK (sync client wrapped via asyncio.to_thread)
with GraphSON v2 serializer over WSS.

Auth: Primary key based (Gremlin wire protocol does NOT support
DefaultAzureCredential — unlike the Cosmos DB NoSQL API).
"""

from __future__ import annotations

import asyncio
import logging
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
# Singleton Gremlin client (thread-safe lazy init)
# ---------------------------------------------------------------------------

import threading

_gremlin_lock = threading.Lock()
_gremlin_client: client.Client | None = None


def _get_client() -> client.Client:
    """Get or create the singleton Gremlin client for Cosmos DB (thread-safe)."""
    global _gremlin_client
    with _gremlin_lock:
        if _gremlin_client is None:
            if not COSMOS_GREMLIN_ENDPOINT or not COSMOS_GREMLIN_PRIMARY_KEY:
                raise RuntimeError(
                    "COSMOS_GREMLIN_ENDPOINT and COSMOS_GREMLIN_PRIMARY_KEY must be set "
                    "when GRAPH_BACKEND=cosmosdb"
                )
            url = f"wss://{COSMOS_GREMLIN_ENDPOINT}:443/"
            username = f"/dbs/{COSMOS_GREMLIN_DATABASE}/colls/{COSMOS_GREMLIN_GRAPH}"
            logger.info("Connecting to Cosmos DB Gremlin: %s (db=%s, graph=%s)",
                         COSMOS_GREMLIN_ENDPOINT, COSMOS_GREMLIN_DATABASE, COSMOS_GREMLIN_GRAPH)
            _gremlin_client = client.Client(
                url=url,
                traversal_source="g",
                username=username,
                password=COSMOS_GREMLIN_PRIMARY_KEY,
                message_serializer=serializer.GraphSONSerializersV2d0(),
            )
    return _gremlin_client


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
# Sync query execution (called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _submit_query(query: str, max_retries: int = 3) -> list:
    """Submit a Gremlin query with retry on 429 / transient / connection errors.

    If the WebSocket connection drops (idle timeout, DNS change, etc.) the
    singleton client is discarded and a fresh connection is established on
    the next attempt.
    """
    global _gremlin_client
    for attempt in range(1, max_retries + 1):
        gremlin_client = _get_client()           # may create a fresh client
        t0 = time.time()
        try:
            callback = gremlin_client.submit(message=query, bindings={})
            results = callback.all().result()
            elapsed_ms = (time.time() - t0) * 1000
            logger.info(
                "Gremlin OK: %d results in %.0fms (attempt %d/%d)  query=%.200s",
                len(results), elapsed_ms, attempt, max_retries, query,
            )
            return results
        except WSServerHandshakeError as e:
            # 401 — auth failure (bad key / endpoint / username path)
            elapsed_ms = (time.time() - t0) * 1000
            logger.error(
                "Gremlin auth failure (401) in %.0fms: %s  — check "
                "COSMOS_GREMLIN_ENDPOINT, COSMOS_GREMLIN_PRIMARY_KEY, "
                "and /dbs/{db}/colls/{graph} username path",
                elapsed_ms, e,
            )
            raise RuntimeError(
                f"Cosmos DB Gremlin authentication failed: {e}. "
                "Verify COSMOS_GREMLIN_ENDPOINT and COSMOS_GREMLIN_PRIMARY_KEY."
            ) from e
        except GremlinServerError as e:
            elapsed_ms = (time.time() - t0) * 1000
            status = getattr(e, "status_code", 0)
            logger.warning(
                "GremlinServerError %s in %.0fms (attempt %d/%d): %s",
                status, elapsed_ms, attempt, max_retries, e,
            )
            # 429 rate-limit or 408 timeout — retry with backoff
            if status in (429, 408) and attempt < max_retries:
                backoff = 2 ** attempt
                logger.info("Retrying in %ds...", backoff)
                time.sleep(backoff)
                continue
            raise  # non-retryable or final attempt
        except Exception as e:
            # Connection/transport error (WebSocket dropped, DNS failure, etc.)
            # Discard the dead client so the next attempt opens a fresh connection.
            elapsed_ms = (time.time() - t0) * 1000
            logger.warning(
                "Gremlin connection error in %.0fms (attempt %d/%d): %s: %s",
                elapsed_ms, attempt, max_retries, type(e).__name__, e,
            )
            with _gremlin_lock:
                if _gremlin_client is gremlin_client:   # guard against races
                    try:
                        gremlin_client.close()
                    except Exception:
                        pass
                    _gremlin_client = None
            if attempt < max_retries:
                backoff = 2 ** attempt
                logger.info("Reconnecting in %ds...", backoff)
                time.sleep(backoff)
                continue
            raise
    # Should not reach here
    raise RuntimeError("Exhausted retries for Gremlin query")


# ---------------------------------------------------------------------------
# Backend class
# ---------------------------------------------------------------------------


class CosmosDBGremlinBackend:
    """Graph backend using Azure Cosmos DB for Apache Gremlin."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a Gremlin query against Cosmos DB.

        The gremlinpython client is synchronous so we run it in a thread
        to avoid blocking the FastAPI event loop.

        Returns:
            dict with "columns" and "data" matching GraphQueryResponse.
        """
        raw_results = await asyncio.to_thread(_submit_query, query)
        return _normalise_results(raw_results)

    def close(self) -> None:
        """Close the singleton Gremlin client (thread-safe)."""
        global _gremlin_client
        with _gremlin_lock:
            if _gremlin_client is not None:
                logger.info("Closing Cosmos DB Gremlin client")
                try:
                    _gremlin_client.close()
                except Exception:
                    pass
                _gremlin_client = None
