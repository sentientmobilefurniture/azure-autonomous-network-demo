"""
Fabric GQL graph backend.

Executes GQL (ISO Graph Query Language) queries against Microsoft Fabric
Graph Models via the REST API. Response format is normalised to the standard
{columns, data} / {nodes, edges} shapes.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Callable

import httpx
from fastapi import HTTPException

from app.gq_config import get_credential
from app.adapters.fabric_config import (
    FABRIC_API_URL,
    FABRIC_SCOPE,
)
from backends.fabric_throttle import get_fabric_gate

logger = logging.getLogger("graph-query-api.fabric")

# Retry limits by error type (see documentation/fabric_control.md Fix 2)
_MAX_429_RETRIES = 2
_MAX_COLDSTART_RETRIES = 5
_MAX_CONTINUATION_RETRIES = 5
_DEFAULT_429_WAIT = 30  # seconds
_TOKEN_STALE_THRESHOLD = 3000  # seconds (~50 min) before re-acquiring


def _parse_retry_after(response: httpx.Response, default: int = 30) -> int:
    """Parse Retry-After header from a 429 response."""
    raw = response.headers.get("Retry-After", "")
    try:
        val = int(raw)
        return val if 0 < val <= 120 else default
    except (ValueError, TypeError):
        return default


async def acquire_fabric_token() -> str:
    """Acquire a Fabric API token via DefaultAzureCredential (standalone helper)."""
    credential = get_credential()
    token = await asyncio.to_thread(credential.get_token, FABRIC_SCOPE)
    return token.token


class FabricGQLBackend:
    """GraphBackend implementation for Fabric GQL.

    Executes GQL (ISO GQL, NOT GraphQL) queries against a Fabric Graph
    Model via the REST API.  Results are normalised to the same shapes
used by other backends so routers don't need changes.

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
            POST /workspaces/{id}/GraphModels/{model_id}/executeQuery?beta=true

        Response shape (Fabric):
            {"status": {...}, "result": {"columns": [...], "data": [...]}}

        We return the normalised: {"columns": [...], "data": [...]}

        Concurrency is bounded by the shared FabricThrottleGate (semaphore +
        circuit breaker). Retry strategy is differentiated by error type —
        see documentation/fabric_control.md Fix 2.
        """
        from app.fabric_discovery import get_fabric_config, is_fabric_ready

        if not is_fabric_ready():
            raise HTTPException(
                status_code=503,
                detail="Fabric backend not configured. Set FABRIC_WORKSPACE_ID "
                       "(graph model is discovered automatically).",
            )

        cfg = get_fabric_config()
        workspace_id = kwargs.get("workspace_id") or cfg.workspace_id
        graph_model_id = kwargs.get("graph_model_id") or cfg.graph_model_id

        url = (
            f"{FABRIC_API_URL}/workspaces/{workspace_id}"
            f"/GraphModels/{graph_model_id}/executeQuery?beta=true"
        )

        gate = get_fabric_gate()
        await gate.acquire()

        try:
            return await self._execute_query_inner(
                query, url, gate, **kwargs
            )
        finally:
            gate.release()

    async def _execute_query_inner(
        self, query: str, url: str, gate, **kwargs
    ) -> dict:
        """Inner retry loop — runs with semaphore held."""
        client = self._get_client()
        token = await self._get_token()
        token_acquired_at = time.monotonic()

        max_attempts = max(
            _MAX_429_RETRIES, _MAX_COLDSTART_RETRIES, _MAX_CONTINUATION_RETRIES
        )
        retries_429 = 0
        retries_coldstart = 0
        retries_continuation = 0
        continuation_token: str | None = None

        for attempt in range(max_attempts):
            payload: dict = {"query": query}
            if continuation_token:
                payload["continuationToken"] = continuation_token

            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )

            # --- HTTP 429: capacity throttled ---
            if response.status_code == 429:
                retries_429 += 1
                await gate.record_429()
                if retries_429 > _MAX_429_RETRIES:
                    raise HTTPException(
                        status_code=429,
                        detail="Fabric capacity exhausted — too many 429s.",
                    )
                wait = _parse_retry_after(response, _DEFAULT_429_WAIT)
                wait *= random.uniform(0.75, 1.25)
                logger.warning(
                    "Fabric API 429 — retrying in %.0fs (429 retry %d/%d)",
                    wait, retries_429, _MAX_429_RETRIES,
                )
                await asyncio.sleep(wait)
                continue

            # --- HTTP 500: check for ColdStartTimeout ---
            if response.status_code == 500:
                body = (
                    response.json()
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
                if body.get("errorCode") == "ColdStartTimeout":
                    retries_coldstart += 1
                    if retries_coldstart > _MAX_COLDSTART_RETRIES:
                        raise HTTPException(
                            status_code=503,
                            detail="Fabric GQL engine cold start — retries exhausted. "
                                   "The graph model is warming up. Please try again in a minute.",
                        )
                    wait = min(10 * (2 ** (retries_coldstart - 1)), 60)
                    wait *= random.uniform(0.75, 1.25)
                    logger.warning(
                        "Fabric GQL ColdStartTimeout — retrying in %.0fs "
                        "(attempt %d/%d)",
                        wait, retries_coldstart, _MAX_COLDSTART_RETRIES,
                    )
                    continuation_token = None
                    await asyncio.sleep(wait)
                    # Re-acquire token only if stale
                    if time.monotonic() - token_acquired_at > _TOKEN_STALE_THRESHOLD:
                        token = await self._get_token()
                        token_acquired_at = time.monotonic()
                    continue

                # Non-ColdStartTimeout 5xx — fail immediately
                await gate.record_server_error()
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Fabric GQL query failed: {response.text[:500]}",
                )

            # --- Any other non-200 — fail immediately ---
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Fabric GQL query failed: {response.text[:500]}",
                )

            # --- 200 OK: parse body ---
            body = response.json()
            status_code = body.get("status", {}).get("code", "")
            result = body.get("result", body)

            # Status 02000 = cold-start continuation — data still loading
            if status_code == "02000" and result.get("nextPage"):
                retries_continuation += 1
                if retries_continuation > _MAX_CONTINUATION_RETRIES:
                    raise HTTPException(
                        status_code=503,
                        detail="Fabric GQL continuation retries exhausted.",
                    )
                continuation_token = result["nextPage"]
                wait = 10
                logger.info(
                    "Fabric GQL cold start (status 02000) — retrying with "
                    "continuation token in %ds (attempt %d/%d)",
                    wait, retries_continuation, _MAX_CONTINUATION_RETRIES,
                )
                await asyncio.sleep(wait)
                continue

            # Success
            await gate.record_success()
            return {
                "columns": result.get("columns", []),
                "data": result.get("data", []),
            }

        raise HTTPException(
            status_code=503,
            detail="Fabric GQL retries exhausted. Please try again shortly.",
        )

    # ------------------------------------------------------------------
    # GraphBackend Protocol — get_topology
    # ------------------------------------------------------------------

    # Schema definition for building topology queries.
    # Each relationship defines source→target entity types,
    # their ID properties, and other key properties to return.
    _TOPOLOGY_SCHEMA: list[dict] = [
        {"rel": "connects_to",   "source": "TransportLink", "target": "CoreRouter",
         "s_id": "LinkId", "t_id": "RouterId",
         "s_props": ["LinkType", "CapacityGbps", "SourceRouterId", "TargetRouterId"],
         "t_props": ["City", "Region", "Vendor"]},
        {"rel": "aggregates_to", "source": "AggSwitch",     "target": "CoreRouter",
         "s_id": "SwitchId", "t_id": "RouterId",
         "s_props": ["City", "UplinkRouterId"], "t_props": ["City", "Region"]},
        {"rel": "backhauls_via", "source": "BaseStation",   "target": "AggSwitch",
         "s_id": "StationId", "t_id": "SwitchId",
         "s_props": ["StationType", "City"], "t_props": ["City"]},
        {"rel": "peers_over",    "source": "BGPSession",    "target": "CoreRouter",
         "s_id": "SessionId", "t_id": "RouterId",
         "s_props": ["PeerARouterId", "PeerBRouterId"], "t_props": ["City"]},
        {"rel": "governed_by",   "source": "SLAPolicy",     "target": "Service",
         "s_id": "SLAPolicyId", "t_id": "ServiceId",
         "s_props": ["AvailabilityPct", "Tier"], "t_props": ["ServiceType", "CustomerName"]},
        {"rel": "depends_on",    "source": "Service",       "target": "MPLSPath",
         "s_id": "ServiceId", "t_id": "PathId",
         "s_props": ["ServiceType"], "t_props": ["PathType"]},
        {"rel": "routes_via",    "source": "MPLSPath",      "target": "TransportLink",
         "s_id": "PathId", "t_id": "LinkId",
         "s_props": ["PathType"], "t_props": ["LinkType"]},
    ]

    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Fetch graph topology for visualisation.

        Issues separate GQL queries per relationship type (avoids the
        7-way cartesian join that causes GraphEngineFailure in Fabric).
        Uses explicit property projections (s.*, t.* wildcards fail in
        Fabric's managed identity context).
        """
        if query is not None and query != "__MULTI_QUERY__":
            result = await self.execute_query(query)
            return self._parse_topology_result(result, vertex_labels)

        schema = self._TOPOLOGY_SCHEMA
        if vertex_labels:
            labels_set = set(vertex_labels)
            schema = [
                r for r in schema
                if r["source"] in labels_set or r["target"] in labels_set
            ]

        nodes_by_id: dict[str, dict] = {}
        edges_seen: set[str] = set()
        edge_list: list[dict] = []

        for r in schema:
            src_type = r["source"]
            tgt_type = r["target"]
            rel_name = r["rel"]
            s_id = r["s_id"]
            t_id = r["t_id"]
            s_props = r.get("s_props", [])
            t_props = r.get("t_props", [])

            # Build RETURN clause with explicit properties
            ret_cols = [f"s.`{s_id}` AS `s_{s_id}`"]
            for p in s_props:
                ret_cols.append(f"s.`{p}` AS `s_{p}`")
            ret_cols.append(f"t.`{t_id}` AS `t_{t_id}`")
            for p in t_props:
                ret_cols.append(f"t.`{p}` AS `t_{p}`")

            q = (
                f"MATCH (s:`{src_type}`)-[e:`{rel_name}`]->(t:`{tgt_type}`) "
                f"RETURN {', '.join(ret_cols)} LIMIT 500"
            )
            try:
                result = await self.execute_query(q)
            except Exception as exc:
                logger.warning("Topology query failed for %s: %s", rel_name, exc)
                continue

            for row in result.get("data", []):
                # Build source node
                s_id_val = row.get(f"s_{s_id}", "")
                s_node_id = f"{src_type}:{s_id_val}"
                if s_node_id not in nodes_by_id:
                    s_node_props = {s_id: s_id_val}
                    for p in s_props:
                        v = row.get(f"s_{p}")
                        if v is not None:
                            s_node_props[p] = v
                    nodes_by_id[s_node_id] = {"id": s_node_id, "label": src_type, "properties": s_node_props}

                # Build target node
                t_id_val = row.get(f"t_{t_id}", "")
                t_node_id = f"{tgt_type}:{t_id_val}"
                if t_node_id not in nodes_by_id:
                    t_node_props = {t_id: t_id_val}
                    for p in t_props:
                        v = row.get(f"t_{p}")
                        if v is not None:
                            t_node_props[p] = v
                    nodes_by_id[t_node_id] = {"id": t_node_id, "label": tgt_type, "properties": t_node_props}

                # Build edge
                edge_id = f"{rel_name}:{s_node_id}->{t_node_id}"
                if edge_id not in edges_seen:
                    edges_seen.add(edge_id)
                    edge_list.append({
                        "id": edge_id,
                        "source": s_node_id,
                        "target": t_node_id,
                        "label": rel_name,
                        "properties": {},
                    })

        return {
            "nodes": list(nodes_by_id.values()),
            "edges": edge_list,
        }

    def _parse_topology_result(self, result: dict, vertex_labels: list[str] | None) -> dict:
        """Parse a custom query result into nodes/edges (best-effort)."""
        import json as _json
        nodes_by_id: dict[str, dict] = {}
        edges_seen: set[str] = set()
        edge_list: list[dict] = []

        for row in result.get("data", []):
            for col_name, value in row.items():
                if value is None:
                    continue
                parsed = value
                if isinstance(value, str):
                    try:
                        parsed = _json.loads(value)
                    except (ValueError, TypeError):
                        continue
                if not isinstance(parsed, dict):
                    continue

                oid = parsed.get("oid", "")
                labels = parsed.get("labels", [])
                props = parsed.get("properties", {})
                ends = parsed.get("ends")

                if ends is not None:
                    if oid and oid not in edges_seen:
                        src = ends[0].get("oid", "") if len(ends) >= 2 else ""
                        tgt = ends[1].get("oid", "") if len(ends) >= 2 else ""
                        edges_seen.add(oid)
                        edge_list.append({
                            "id": oid, "source": src, "target": tgt,
                            "label": labels[0] if labels else col_name,
                            "properties": props,
                        })
                else:
                    if oid and oid not in nodes_by_id:
                        label = labels[0] if labels else col_name
                        if vertex_labels and label not in vertex_labels:
                            continue
                        nodes_by_id[oid] = {"id": oid, "label": label, "properties": props}

        return {"nodes": list(nodes_by_id.values()), "edges": edge_list}

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
                if not loop.is_closing():
                    loop.create_task(self._client.aclose())
                # If loop is closing, the client will be GC'd
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


