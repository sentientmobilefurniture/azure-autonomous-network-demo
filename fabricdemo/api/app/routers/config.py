"""
Router: /api/config — runtime configuration and resource graph.

GET  /api/config/current     — return current active configuration
GET  /api/config/resources   — resource graph (agents, tools, data sources, infra)
GET  /api/config/scenario    — active scenario metadata
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from fastapi import APIRouter, Request

from app.paths import PROJECT_ROOT
from app.agent_ids import load_agent_ids

logger = logging.getLogger("app.config")

router = APIRouter(prefix="/api/config", tags=["configuration"])


# ---------------------------------------------------------------------------
# Scenario YAML loader
# ---------------------------------------------------------------------------

SCENARIO_NAME = os.getenv("DEFAULT_SCENARIO", "")

# Container path: /app/data/scenarios/<name>/scenario.yaml
_SCENARIO_YAML_CANDIDATES = [
    Path("/app/data/scenarios") / SCENARIO_NAME / "scenario.yaml",
    PROJECT_ROOT / "data" / "scenarios" / SCENARIO_NAME / "scenario.yaml",
]

def _load_scenario_yaml() -> dict:
    if not SCENARIO_NAME:
        logger.warning("DEFAULT_SCENARIO not set — resource graph will be empty")
        return {}
    for p in _SCENARIO_YAML_CANDIDATES:
        if p.exists():
            with open(p) as f:
                return yaml.safe_load(f)
    logger.warning("scenario.yaml not found — resource graph will be empty")
    return {}


# ---------------------------------------------------------------------------
# Build SCENARIO_CONFIG from YAML (replaces hardcoded dict)
# ---------------------------------------------------------------------------

def _build_scenario_config(manifest: dict) -> dict:
    """Convert scenario.yaml into the internal SCENARIO_CONFIG format."""
    agents = []
    for ag in manifest.get("agents", []):
        tools = []
        for t in ag.get("tools", []):
            tool_entry = {"type": t["type"]}
            if t["type"] == "openapi":
                tool_entry["spec_template"] = t.get("spec_template", "")
                tool_entry["data_source"] = t.get("spec_template", "")  # graph/telemetry
            elif t["type"] == "azure_ai_search":
                # Resolve index key to actual index name from scenario.yaml
                idx_key = t.get("index_key", "")
                idx_name = manifest.get("data_sources", {}).get("search_indexes", {}).get(idx_key, {}).get("index_name", f"{idx_key}-index")
                tool_entry["index"] = idx_name
                tool_entry["data_source"] = idx_key
            tools.append(tool_entry)

        agents.append({
            "name": ag["name"],
            "model": ag.get("model", "gpt-4.1"),
            "is_orchestrator": ag.get("is_orchestrator", False),
            "tools": tools,
            "connected_agents": ag.get("connected_agents", []),
        })

    ds = manifest.get("data_sources", {})
    graph_cfg = ds.get("graph", {}).get("config", {})
    graph_name = graph_cfg.get("graph", "")
    search = ds.get("search_indexes", {})
    runbooks_idx = search.get("runbooks", {}).get("index_name", "runbooks-index")
    tickets_idx = search.get("tickets", {}).get("index_name", "tickets-index")

    data_sources = {
        "graph": {
            "type": ds.get("graph", {}).get("connector", "fabric-gql") if ds else "fabric_gql",
            "label": f"Fabric GQL ({graph_name})",
            "workspace": os.getenv("FABRIC_WORKSPACE_ID", ""),
            "graph_model": "(auto-discovered at runtime)",
        },
        "telemetry": {
            "type": ds.get("telemetry", {}).get("connector", "fabric-kql") if ds else "fabric_kql",
            "label": "Fabric KQL (NetworkTelemetryEH)",
            "eventhouse": "(auto-discovered at runtime)",
        },
        "runbooks": {
            "type": "azure_ai_search",
            "label": f"AI Search ({runbooks_idx})",
            "index": runbooks_idx,
        },
        "tickets": {
            "type": "azure_ai_search",
            "label": f"AI Search ({tickets_idx})",
            "index": tickets_idx,
        },
    }

    return {"agents": agents, "data_sources": data_sources}


_manifest = _load_scenario_yaml()
SCENARIO_CONFIG = _build_scenario_config(_manifest) if _manifest else {"agents": [], "data_sources": {}}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_current_config() -> dict:
    """Load current config from Foundry agent discovery + env-var defaults."""
    _runbooks_default = (
        _manifest.get("data_sources", {}).get("search_indexes", {}).get("runbooks", {}).get("index_name", "runbooks-index")
        if _manifest else "runbooks-index"
    )
    _tickets_default = (
        _manifest.get("data_sources", {}).get("search_indexes", {}).get("tickets", {}).get("index_name", "tickets-index")
        if _manifest else "tickets-index"
    )
    config = {
        "graph": SCENARIO_NAME,
        "runbooks_index": os.getenv("RUNBOOKS_INDEX_NAME", _runbooks_default),
        "tickets_index": os.getenv("TICKETS_INDEX_NAME", _tickets_default),
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
    """Build and return the nodes+edges resource graph from active scenario."""
    return _build_resource_graph(SCENARIO_CONFIG, SCENARIO_NAME)


@router.get("/scenario", summary="Active scenario metadata")
async def get_scenario():
    """Return scenario-level metadata loaded from scenario.yaml.

    The frontend uses this to populate titles, graph styles,
    example questions, and data-source labels without hardcoding.

    Keys are camelCase to match the frontend ScenarioConfig interface.
    graph_styles.node_types is transformed into flat nodeColors/nodeSizes/nodeIcons maps.
    """
    if not _manifest:
        return {
            "name": SCENARIO_NAME,
            "displayName": SCENARIO_NAME,
            "description": "",
            "graph": "",
            "runbooksIndex": "",
            "ticketsIndex": "",
            "graphStyles": {"nodeColors": {}, "nodeSizes": {}, "nodeIcons": {}},
            "exampleQuestions": [],
            "useCases": [],
            "demoFlows": [],
        }

    ds = _manifest.get("data_sources", {})
    search = ds.get("search_indexes", {})
    graph_cfg = ds.get("graph", {}).get("config", {})

    # Transform graph_styles.node_types into flat maps for the frontend
    node_types = _manifest.get("graph_styles", {}).get("node_types", {})
    node_colors: dict[str, str] = {}
    node_sizes: dict[str, int] = {}
    node_icons: dict[str, str] = {}
    for node_type, style in node_types.items():
        if "color" in style:
            node_colors[node_type] = style["color"]
        if "size" in style:
            node_sizes[node_type] = style["size"]
        if "icon" in style:
            node_icons[node_type] = style["icon"]

    return {
        "name": SCENARIO_NAME,
        "displayName": _manifest.get("display_name", SCENARIO_NAME),
        "description": _manifest.get("description", ""),
        "graph": graph_cfg.get("graph", ""),
        "runbooksIndex": search.get("runbooks", {}).get("index_name", "runbooks-index"),
        "ticketsIndex": search.get("tickets", {}).get("index_name", "tickets-index"),
        "graphStyles": {
            "nodeColors": node_colors,
            "nodeSizes": node_sizes,
            "nodeIcons": node_icons,
        },
        "exampleQuestions": _manifest.get("example_questions", []),
        "useCases": _manifest.get("use_cases", []),
        "demoFlows": _manifest.get("demo_flows", []),
    }
