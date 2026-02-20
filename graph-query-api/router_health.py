"""
Health-check router — probes each data source for the active scenario.

GET /query/health/sources?scenario=<name>

Returns per-source health status including the exact query used,
latency, and error details. Consumed by the frontend DataSourceBar.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from config import DATA_SOURCES, SCENARIO_NAME, DEFAULT_GRAPH
from backends import get_backend_for_graph

logger = logging.getLogger("graph-query-api.health")

router = APIRouter(prefix="/query")


@router.get("/health")
async def query_health():
    """Simple liveness probe for the graph-query-api behind /query/ nginx prefix."""
    return {"status": "ok", "service": "graph-query-api"}


# AI Search env vars
AI_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "")
AI_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY", "")
AI_SEARCH_API_VERSION = "2024-07-01"


async def _ping_graph_backend(connector: str, config: dict, graph_name: str) -> dict:
    """Ping a graph backend by connector type."""
    backend_type = {
        "fabric-gql": "fabric-gql",
        "mock": "mock",
    }.get(connector, connector)

    try:
        backend = get_backend_for_graph(graph_name, backend_type)
        return await backend.ping()
    except Exception as e:
        return {"ok": False, "query": "(failed to create backend)", "detail": str(e), "latency_ms": 0}


async def _ping_telemetry_backend(connector: str, config: dict) -> dict:
    """Ping a telemetry backend by connector type."""
    if connector == "fabric-kql":
        try:
            from backends.fabric_kql import FabricKQLBackend
            backend = FabricKQLBackend()
            return await backend.ping()
        except Exception as e:
            return {"ok": False, "query": "(failed to create backend)", "detail": str(e), "latency_ms": 0}

    return {"ok": False, "query": "(unknown telemetry connector)", "detail": f"Unknown connector: {connector}", "latency_ms": 0}


async def _ping_search_index(index_name: str) -> dict:
    """Check AI Search index existence via REST API."""
    query = f"GET /indexes/{index_name}"
    if not AI_SEARCH_ENDPOINT:
        return {"ok": False, "query": query, "detail": "AZURE_SEARCH_ENDPOINT not configured", "latency_ms": 0}

    import httpx
    t0 = time.time()
    try:
        url = f"{AI_SEARCH_ENDPOINT}/indexes/{index_name}?api-version={AI_SEARCH_API_VERSION}"
        headers: dict[str, str] = {}
        if AI_SEARCH_KEY:
            headers["api-key"] = AI_SEARCH_KEY
        else:
            # Use DefaultAzureCredential
            from config import get_credential
            import asyncio
            cred = get_credential()
            token = await asyncio.to_thread(
                cred.get_token, "https://search.azure.com/.default"
            )
            headers["Authorization"] = f"Bearer {token.token}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
        latency = int((time.time() - t0) * 1000)
        if resp.status_code == 200:
            doc_count = resp.json().get("documentCount", "?")
            return {"ok": True, "query": query, "detail": f"index exists (docs: {doc_count})", "latency_ms": latency}
        else:
            return {"ok": False, "query": query, "detail": f"HTTP {resp.status_code}", "latency_ms": latency}
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return {"ok": False, "query": query, "detail": str(e), "latency_ms": latency}


@router.get("/health/sources")
async def health_check_sources(scenario: str = Query(default=SCENARIO_NAME, description="Scenario name")):
    """Probe each data source and return health status."""
    results = []

    # Graph source
    graph_def = DATA_SOURCES.get("graph", {})
    if graph_def:
        connector = graph_def.get("connector", "fabric-gql")
        graph_name = graph_def.get("resource_name", DEFAULT_GRAPH)
        ping_result = await _ping_graph_backend(connector, {}, graph_name)
        results.append({
            "source_type": "graph",
            "connector": connector,
            "resource_name": graph_name,
            **ping_result,
        })

    # Telemetry source
    telemetry_def = DATA_SOURCES.get("telemetry", {})
    if telemetry_def:
        connector = telemetry_def.get("connector", "fabric-kql")
        resource_name = telemetry_def.get("resource_name", "telemetry")
        ping_result = await _ping_telemetry_backend(connector, {})
        results.append({
            "source_type": "telemetry",
            "connector": connector,
            "resource_name": resource_name,
            **ping_result,
        })

    # Search indexes
    search_indexes = DATA_SOURCES.get("search_indexes", {})
    for idx_name, idx_def in search_indexes.items():
        index_name = idx_def.get("index_name", f"{scenario}-{idx_name}")
        ping_result = await _ping_search_index(index_name)
        results.append({
            "source_type": f"search_indexes.{idx_name}",
            "connector": "azure-ai-search",
            "resource_name": index_name,
            **ping_result,
        })

    return {"sources": results, "checked_at": datetime.now(timezone.utc).isoformat()}


@router.post("/health/rediscover")
async def rediscover_fabric():
    """Invalidate Fabric discovery cache and re-discover workspace items."""
    from fabric_discovery import invalidate_cache, get_fabric_config, is_fabric_ready, is_kql_ready

    invalidate_cache()
    cfg = get_fabric_config()   # triggers re-discovery

    return {
        "ok": True,
        "source": cfg.source,
        "workspace_id": cfg.workspace_id or None,
        "graph_model_id": cfg.graph_model_id or None,
        "eventhouse_query_uri": cfg.eventhouse_query_uri or None,
        "kql_db_name": cfg.kql_db_name or None,
        "fabric_ready": is_fabric_ready(),
        "kql_ready": is_kql_ready(),
        "workspace_items": cfg.workspace_items or [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
