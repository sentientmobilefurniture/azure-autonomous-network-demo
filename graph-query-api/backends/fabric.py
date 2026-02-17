"""
Fabric GQL graph backend.

Executes GQL (ISO Graph Query Language) queries against Microsoft Fabric
Graph Models via the REST API. Response format is normalised to the same
{columns, data} / {nodes, edges} shapes as CosmosDBGremlinBackend.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import httpx
from fastapi import HTTPException

from config import get_credential
from adapters.fabric_config import (
    FABRIC_API_URL,
    FABRIC_SCOPE,
    FABRIC_WORKSPACE_ID,
    FABRIC_GRAPH_MODEL_ID,
    FABRIC_CONFIGURED,
)

logger = logging.getLogger("graph-query-api.fabric")


async def acquire_fabric_token() -> str:
    """Acquire a Fabric API token via DefaultAzureCredential (standalone helper)."""
    credential = get_credential()
    token = await asyncio.to_thread(credential.get_token, FABRIC_SCOPE)
    return token.token


class FabricGQLBackend:
    """GraphBackend implementation for Fabric GQL.

    Executes GQL (ISO GQL, NOT GraphQL) queries against a Fabric Graph
    Model via the REST API.  Results are normalised to the same shapes
    used by CosmosDBGremlinBackend so routers don't need changes.

    GQL uses MATCH/RETURN syntax:
        MATCH (r:CoreRouter) RETURN r.RouterId, r.Hostname
        MATCH (a)-[r:connects_to]->(b) RETURN a, r, b
    """

    def __init__(self, graph_name: str = "__default__"):
        self._graph_name = graph_name
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP client (lazy, reusable)
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    # ------------------------------------------------------------------
    # Token acquisition
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        return await acquire_fabric_token()

    # ------------------------------------------------------------------
    # GraphBackend Protocol — execute_query
    # ------------------------------------------------------------------

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a GQL query against Fabric Graph Model REST API.

        GQL uses MATCH/RETURN syntax (ISO GQL), NOT GraphQL.
        Example: MATCH (r:CoreRouter) RETURN r.RouterId, r.Hostname

        Endpoint:
            POST /workspaces/{id}/GraphModels/{model_id}/executeQuery?beta=True

        Response shape (Fabric):
            {"status": {...}, "result": {"columns": [...], "data": [...]}}

        We return the normalised: {"columns": [...], "data": [...]}
        """
        if not FABRIC_CONFIGURED:
            raise HTTPException(
                status_code=503,
                detail="Fabric backend not configured. Set FABRIC_WORKSPACE_ID "
                       "and FABRIC_GRAPH_MODEL_ID environment variables.",
            )

        workspace_id = kwargs.get("workspace_id") or FABRIC_WORKSPACE_ID
        graph_model_id = kwargs.get("graph_model_id") or FABRIC_GRAPH_MODEL_ID

        url = (
            f"{FABRIC_API_URL}/workspaces/{workspace_id}"
            f"/GraphModels/{graph_model_id}/executeQuery?beta=True"
        )
        token = await self._get_token()
        client = self._get_client()

        # Retry with exponential backoff for 429s
        max_retries = 5
        for attempt in range(max_retries):
            response = await client.post(
                url,
                json={"query": query},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 429:
                wait = 15 * (attempt + 1)
                logger.warning(
                    "Fabric API 429 — retrying in %ds (attempt %d/%d)",
                    wait, attempt + 1, max_retries,
                )
                await asyncio.sleep(wait)
                # Re-acquire token in case it expired during wait
                token = await self._get_token()
                continue

            if response.status_code != 200:
                detail = response.text[:500]
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Fabric GQL query failed: {detail}",
                )

            body = response.json()
            result = body.get("result", body)
            return {
                "columns": result.get("columns", []),
                "data": result.get("data", []),
            }

        raise HTTPException(
            status_code=429,
            detail="Fabric API rate limit — retries exhausted",
        )

    # ------------------------------------------------------------------
    # GraphBackend Protocol — get_topology
    # ------------------------------------------------------------------

    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Fetch graph topology for visualisation.

        Default GQL query fetches all nodes and edges.
        Returns normalised {nodes, edges} format.
        """
        if query is None:
            query = "MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m"

        result = await self.execute_query(query)

        # Parse GQL tabular results into nodes/edges topology format
        nodes_by_id: dict[str, dict] = {}
        edges: list[dict] = []

        for row in result.get("data", []):
            # GQL returns columns like n, r, m — each is a graph element
            for col_name, value in row.items():
                if value is None:
                    continue
                if isinstance(value, dict):
                    elem_type = value.get("_type", "node")
                    if (
                        elem_type == "relationship"
                        or "_source" in value
                        or "_target" in value
                    ):
                        edge = {
                            "id": value.get("_id", f"e-{len(edges)}"),
                            "source": value.get("_source", ""),
                            "target": value.get("_target", ""),
                            "label": value.get("_label", ""),
                            "properties": {
                                k: v
                                for k, v in value.items()
                                if not k.startswith("_")
                            },
                        }
                        edges.append(edge)
                    else:
                        node_id = value.get("_id", str(id(value)))
                        if node_id not in nodes_by_id:
                            label = value.get(
                                "_label",
                                (
                                    value.get("_labels", ["Unknown"])[0]
                                    if isinstance(value.get("_labels"), list)
                                    else "Unknown"
                                ),
                            )
                            # Apply vertex_labels filter
                            if vertex_labels and label not in vertex_labels:
                                continue
                            nodes_by_id[node_id] = {
                                "id": node_id,
                                "label": label,
                                "properties": {
                                    k: v
                                    for k, v in value.items()
                                    if not k.startswith("_")
                                },
                            }

        return {
            "nodes": list(nodes_by_id.values()),
            "edges": edges,
        }

    # ------------------------------------------------------------------
    # GraphBackend Protocol — ingest
    # ------------------------------------------------------------------

    async def ingest(
        self,
        vertices: list[dict],
        edges: list[dict],
        *,
        graph_name: str,
        graph_database: str,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> dict:
        """Fabric graph data is loaded via Lakehouse + Ontology, not direct ingest.

        Raises NotImplementedError — data loading for Fabric uses the
        provisioning scripts (Lakehouse CSV upload + Ontology creation).
        """
        raise NotImplementedError(
            "Fabric graphs are populated via Lakehouse + Ontology provisioning, "
            "not direct ingest. Use the Fabric provisioning pipeline."
        )

    # ------------------------------------------------------------------
    # GraphBackend Protocol — close / aclose
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Sync cleanup — V10's close_all_backends() calls this and
        checks inspect.isawaitable(result) for async backends."""
        if self._client and not self._client.is_closed:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._client.aclose())
            except RuntimeError:
                # No event loop — shouldn't happen in prod
                pass
            self._client = None

    async def ping(self) -> dict:
        """Health check — run a minimal GQL query against Fabric Ontology."""
        query = "MATCH (n) RETURN n LIMIT 1"
        import time
        t0 = time.time()
        try:
            result = await self.execute_query(query)
            latency = int((time.time() - t0) * 1000)
            count = len(result.get("data", []))
            return {"ok": True, "query": query, "detail": f"{count} row(s)", "latency_ms": latency}
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            return {"ok": False, "query": query, "detail": str(e), "latency_ms": latency}


