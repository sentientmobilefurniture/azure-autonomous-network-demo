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

from config_store import fetch_scenario_config
from backends import get_backend_for_graph

logger = logging.getLogger("graph-query-api.health")

router = APIRouter(prefix="/query")

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


def _derive_resource_name(source_type: str, source_def: dict) -> str:
    """Derive a display name for a data source."""
    cfg = source_def.get("config", {})
    if source_type == "graph":
        return cfg.get("graph_name", cfg.get("ontology_name", source_type))
    if source_type == "telemetry":
        return cfg.get("eventhouse_name", cfg.get("container_prefix", source_type))
    # search indexes
    return cfg.get("index_name", source_type)


@router.get("/health/sources")
async def health_check_sources(scenario: str = Query(..., description="Scenario name")):
    """Probe each data source defined in the scenario config and return health status."""
    try:
        config = await fetch_scenario_config(scenario)
    except ValueError:
        return {"sources": [], "checked_at": datetime.now(timezone.utc).isoformat(), "error": f"No config for '{scenario}'"}

    data_sources = config.get("data_sources", {})
    results = []

    # Graph source
    graph_def = data_sources.get("graph", {})
    if graph_def:
        connector = graph_def.get("connector", "fabric-gql")
        graph_cfg = graph_def.get("config", {})
        graph_name = graph_cfg.get("graph_name", f"{scenario}-topology")
        resource_name = _derive_resource_name("graph", graph_def)
        ping_result = await _ping_graph_backend(connector, graph_cfg, graph_name)
        results.append({
            "source_type": "graph",
            "connector": connector,
            "resource_name": resource_name,
            **ping_result,
        })

    # Telemetry source
    telemetry_def = data_sources.get("telemetry", {})
    if telemetry_def:
        connector = telemetry_def.get("connector", "fabric-kql")
        resource_name = _derive_resource_name("telemetry", telemetry_def)
        ping_result = await _ping_telemetry_backend(connector, telemetry_def.get("config", {}))
        results.append({
            "source_type": "telemetry",
            "connector": connector,
            "resource_name": resource_name,
            **ping_result,
        })

    # Search indexes
    search_indexes = data_sources.get("search_indexes", {})
    for idx_name, idx_def in search_indexes.items():
        index_name = idx_def.get("config", {}).get("index_name", f"{scenario}-{idx_name}")
        ping_result = await _ping_search_index(index_name)
        results.append({
            "source_type": f"search_indexes.{idx_name}",
            "connector": "azure-ai-search",
            "resource_name": index_name,
            **ping_result,
        })

    return {"sources": results, "checked_at": datetime.now(timezone.utc).isoformat()}
