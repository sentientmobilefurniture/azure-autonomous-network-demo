"""
Router: /api/config — runtime configuration and resource graph.

GET  /api/config/current     — return current active configuration
GET  /api/config/resources   — resource graph (agents, tools, data sources, infra)
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request

from app.paths import PROJECT_ROOT
from app.agent_ids import load_agent_ids

logger = logging.getLogger("app.config")

router = APIRouter(prefix="/api/config", tags=["configuration"])


# ---------------------------------------------------------------------------
# Hardcoded scenario config for telco-noc (used by _build_resource_graph)
# ---------------------------------------------------------------------------

SCENARIO_CONFIG = {
    "agents": [
        {
            "name": "GraphExplorerAgent",
            "model": "gpt-4.1",
            "is_orchestrator": False,
            "tools": [{"type": "openapi", "spec_template": "graph", "data_source": "graph"}],
            "connected_agents": [],
        },
        {
            "name": "TelemetryAgent",
            "model": "gpt-4.1",
            "is_orchestrator": False,
            "tools": [{"type": "openapi", "spec_template": "telemetry", "data_source": "telemetry"}],
            "connected_agents": [],
        },
        {
            "name": "RunbookKBAgent",
            "model": "gpt-4.1",
            "is_orchestrator": False,
            "tools": [{"type": "azure_ai_search", "index": "runbooks-index", "data_source": "runbooks"}],
            "connected_agents": [],
        },
        {
            "name": "HistoricalTicketAgent",
            "model": "gpt-4.1",
            "is_orchestrator": False,
            "tools": [{"type": "azure_ai_search", "index": "tickets-index", "data_source": "tickets"}],
            "connected_agents": [],
        },
        {
            "name": "Orchestrator",
            "model": "gpt-4.1",
            "is_orchestrator": True,
            "tools": [],
            "connected_agents": ["GraphExplorerAgent", "TelemetryAgent", "RunbookKBAgent", "HistoricalTicketAgent"],
        },
    ],
    "data_sources": {
        "graph": {
            "type": "fabric_gql",
            "label": "Fabric GQL (telco-noc-topology)",
            "workspace": os.getenv("FABRIC_WORKSPACE_ID", ""),
            "graph_model": "(auto-discovered at runtime)",
        },
        "telemetry": {
            "type": "fabric_kql",
            "label": "Fabric KQL (NetworkTelemetryEH)",
            "eventhouse": "(auto-discovered at runtime)",
        },
        "runbooks": {
            "type": "azure_ai_search",
            "label": "AI Search (runbooks-index)",
            "index": "runbooks-index",
        },
        "tickets": {
            "type": "azure_ai_search",
            "label": "AI Search (tickets-index)",
            "index": "tickets-index",
        },
    },
}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_current_config() -> dict:
    """Load current config from Foundry agent discovery + env-var defaults."""
    config = {
        "graph": "telco-noc",
        "runbooks_index": os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index"),
        "tickets_index": os.getenv("TICKETS_INDEX_NAME", "tickets-index"),
        "agents": None,
    }

    try:
        data = load_agent_ids()
        if data:
            config["agents"] = data
    except Exception:
        pass

    return config


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/current", summary="Get current configuration")
async def get_current_config():
    """Return the current active data source bindings and agent IDs."""
    return _load_current_config()


# ---------------------------------------------------------------------------
# Resource graph endpoint
# ---------------------------------------------------------------------------


def _build_resource_graph(config: dict, scenario_name: str) -> dict:
    """Build a nodes+edges graph from scenario config for the Resources tab.

    Layers: agents → tools → data sources → infrastructure.
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    agents = config.get("agents", [])
    data_sources = config.get("data_sources", {})

    # ── Agent + tool layer ───────────────────────────────────────────────
    for ag in agents:
        name = ag["name"]
        is_orch = ag.get("is_orchestrator", False)
        node_type = "orchestrator" if is_orch else "agent"
        meta = {"model": ag.get("model", "gpt-4.1")}
        nodes.append({"id": f"agent-{name}", "label": name, "type": node_type, "meta": meta})

        # Connected agents (orchestrator → sub-agents)
        for ca in ag.get("connected_agents", []):
            edges.append({
                "source": f"agent-{name}",
                "target": f"agent-{ca}",
                "type": "delegates_to",
                "label": "delegates",
            })

        # Tools
        for tool in ag.get("tools", []):
            tool_type = tool.get("type", "unknown")
            tool_id = f"tool-{name}-{tool_type}"
            ds_name = tool.get("data_source", "")
            tool_meta: dict = {"tool_type": tool_type}

            if tool_type == "openapi":
                spec = tool.get("spec_template", tool.get("spec", ""))
                tool_meta["spec"] = spec
                nodes.append({"id": tool_id, "label": f"OpenAPI: {spec}", "type": "tool", "meta": tool_meta})
            elif tool_type == "azure_ai_search":
                index = tool.get("index", "")
                tool_meta["index"] = index
                nodes.append({"id": tool_id, "label": f"AzureAISearch: {index}", "type": "tool", "meta": tool_meta})
            else:
                nodes.append({"id": tool_id, "label": tool_type, "type": "tool", "meta": tool_meta})

            edges.append({
                "source": f"agent-{name}",
                "target": tool_id,
                "type": "uses_tool",
                "label": "uses",
            })

            # Tool → data source
            if ds_name and ds_name in data_sources:
                edges.append({
                    "source": tool_id,
                    "target": f"ds-{ds_name}",
                    "type": "queries",
                    "label": "queries",
                })

    # ── Data source layer ────────────────────────────────────────────────
    for ds_key, ds_def in data_sources.items():
        ds_type = ds_def.get("type", "unknown")
        ds_meta = {"type": ds_type}
        node_type_map = {
            "fabric_gql": "datasource",
            "fabric_kql": "datasource",
            "azure_ai_search": "search-index",
            "blob_storage": "blob-container",
        }
        nt = node_type_map.get(ds_type, "datasource")
        ds_label = ds_def.get("label", ds_key)
        if ds_type == "fabric_gql":
            ds_meta["workspace"] = ds_def.get("workspace", "")
            ds_meta["graph_model"] = ds_def.get("graph_model", "")
        elif ds_type == "fabric_kql":
            ds_meta["eventhouse"] = ds_def.get("eventhouse", "")
        elif ds_type == "azure_ai_search":
            ds_meta["index"] = ds_def.get("index", "")
        elif ds_type == "blob_storage":
            ds_meta["container"] = ds_def.get("container", "")
        nodes.append({"id": f"ds-{ds_key}", "label": ds_label, "type": nt, "meta": ds_meta})

    # ── Infrastructure layer (from env vars) ─────────────────────────────
    nodes.extend(_infra_nodes_only())

    # Agents → Foundry
    for ag in agents:
        edges.append({
            "source": f"agent-{ag['name']}",
            "target": "infra-foundry",
            "type": "runs_on",
            "label": "",
        })

    # Data sources → infra (best-effort mapping)
    for ds_key, ds_def in data_sources.items():
        ds_type = ds_def.get("type", "")
        if ds_type == "fabric_gql":
            edges.append({"source": f"ds-{ds_key}", "target": "infra-foundry", "type": "hosted_on", "label": "hosted on"})
        elif ds_type == "fabric_kql":
            edges.append({"source": f"ds-{ds_key}", "target": "infra-foundry", "type": "hosted_on", "label": "hosted on"})
        elif ds_type == "azure_ai_search":
            edges.append({"source": f"ds-{ds_key}", "target": "infra-search", "type": "hosted_on", "label": "hosted on"})
        elif ds_type == "blob_storage":
            edges.append({"source": f"ds-{ds_key}", "target": "infra-storage", "type": "contains", "label": ""})

    # Validate edges — drop any whose source or target doesn't match a node ID
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    return {"nodes": nodes, "edges": edges, "scenario": scenario_name}


def _infra_nodes_only() -> list[dict]:
    """Return only infrastructure nodes (for partial-failure responses)."""
    return [
        {"id": "infra-foundry", "label": "AI Foundry", "type": "foundry",
         "meta": {"resource": os.getenv("AI_FOUNDRY_NAME", ""), "project": os.getenv("AI_FOUNDRY_PROJECT_NAME", "")}},
        {"id": "infra-cosmos-n", "label": "Cosmos DB (Interactions)", "type": "datasource",
         "meta": {"resource": os.getenv("COSMOS_NOSQL_ENDPOINT", ""), "api": "NoSQL"}},
        {"id": "infra-storage", "label": "Storage Account", "type": "storage",
         "meta": {"resource": os.getenv("STORAGE_ACCOUNT_NAME", "")}},
        {"id": "infra-search", "label": "AI Search", "type": "search-service",
         "meta": {"resource": os.getenv("AZURE_SEARCH_ENDPOINT", "")}},
    ]


@router.get("/resources", summary="Get resource graph for visualization")
async def get_resource_graph(request: Request):
    """Build and return the nodes+edges resource graph from hardcoded config."""
    return _build_resource_graph(SCENARIO_CONFIG, "telco-noc")
