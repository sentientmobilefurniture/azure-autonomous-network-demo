"""
Router: /api/config — runtime agent + data source configuration.

POST /api/config/apply      — apply data source + prompt bindings (re-provisions agents)
GET  /api/config/current     — return current active configuration
GET  /api/config/resources   — resource graph (agents, tools, data sources, infra)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("api.config")

router = APIRouter(prefix="/api/config", tags=["configuration"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Add scripts/ to path for agent_provisioner import
# In container: /app/api/app/routers/config.py → PROJECT_ROOT = /app/api
# Scripts are at /app/scripts/, so we check both locations
for scripts_path in [PROJECT_ROOT / "scripts", PROJECT_ROOT.parent / "scripts"]:
    if scripts_path.exists() and str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))
        break

# ---------------------------------------------------------------------------
# In-memory config state
# ---------------------------------------------------------------------------

_config_lock = threading.Lock()
_current_config: dict | None = None


def _load_current_config() -> dict:
    """Load current config from agent_ids.json + defaults."""
    global _current_config
    if _current_config is not None:
        return _current_config

    agent_ids_path = Path(os.getenv(
        "AGENT_IDS_PATH",
        str(PROJECT_ROOT / "scripts" / "agent_ids.json"),
    ))

    _current_config = {
        "graph": os.getenv("COSMOS_GREMLIN_GRAPH", "topology"),
        "runbooks_index": os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index"),
        "tickets_index": os.getenv("TICKETS_INDEX_NAME", "tickets-index"),
        "agents": None,
    }

    if agent_ids_path.exists():
        try:
            _current_config["agents"] = json.loads(agent_ids_path.read_text())
        except Exception:
            pass

    return _current_config


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ConfigApplyRequest(BaseModel):
    """Request to apply new agent configuration."""
    graph: str = "topology"
    runbooks_index: str = "runbooks-index"
    tickets_index: str = "tickets-index"
    prompt_scenario: str | None = None     # scenario name to load prompts from Cosmos
    prompts: dict[str, str] | None = None  # agent_name → prompt content (overrides prompt_scenario)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/current", summary="Get current configuration")
async def get_current_config():
    """Return the current active data source bindings and agent IDs."""
    return _load_current_config()


@router.post("/apply", summary="Apply configuration changes")
async def apply_config(req: ConfigApplyRequest):
    """Apply new data source + prompt bindings.

    This re-provisions the AI Foundry agents with the new settings.
    Returns an SSE stream with progress events (~30s total).
    """
    # Check if we can provision (need Foundry credentials)
    project_endpoint_base = os.getenv("PROJECT_ENDPOINT", "")
    project_name = os.getenv("AI_FOUNDRY_PROJECT_NAME", "")
    model = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4.1")

    if not project_endpoint_base or not project_name:
        raise HTTPException(
            503,
            "Cannot re-provision agents: PROJECT_ENDPOINT and AI_FOUNDRY_PROJECT_NAME not set",
        )

    project_endpoint = f"{project_endpoint_base.rstrip('/')}/api/projects/{project_name}"

    async def event_generator():
        progress: asyncio.Queue = asyncio.Queue()

        async def run_provisioning():
            try:
                from agent_provisioner import AgentProvisioner

                def on_progress(step: str, detail: str):
                    progress.put_nowait({"step": step, "detail": detail})

                provisioner = AgentProvisioner(
                    project_endpoint=project_endpoint,
                )

                # Resolve prompts — fetch from Cosmos if available
                prompts = req.prompts or {}
                if not prompts:
                    # Determine which scenario's prompts to use
                    scenario_prefix = req.prompt_scenario or (
                        req.graph.rsplit("-", 1)[0] if "-" in req.graph else "telco-noc"
                    )
                    on_progress("prompts", f"Fetching prompts for '{scenario_prefix}' from Cosmos...")
                    try:
                        import urllib.request
                        import urllib.parse
                        import json as _json
                        # Single request with content — avoids N+1 round-trips
                        prompts_url = (
                            f"http://127.0.0.1:8100/query/prompts"
                            f"?scenario={urllib.parse.quote(scenario_prefix)}"
                            f"&include_content=true"
                        )
                        prompts_req = urllib.request.Request(prompts_url)
                        with urllib.request.urlopen(prompts_req, timeout=30) as resp:
                            prompts_data = _json.loads(resp.read())

                        # Substitute placeholders — scenario prompts stored in
                        # Cosmos may still contain {graph_name} / {scenario_prefix}
                        # if they originated from template files.
                        _graph_name = req.graph  # e.g. "telco-noc-topology"
                        _scenario_pfx = _graph_name.rsplit("-", 1)[0] if "-" in _graph_name else _graph_name

                        for p in prompts_data.get("prompts", []):
                            if p.get("is_active") and p.get("content"):
                                agent_name = p.get("agent", "")
                                if agent_name and agent_name not in prompts:
                                    content = p["content"]
                                    content = content.replace("{graph_name}", _graph_name)
                                    content = content.replace("{scenario_prefix}", _scenario_pfx)
                                    prompts[agent_name] = content
                                    on_progress("prompts", f"Loaded {agent_name} prompt ({len(content)} chars)")

                    except Exception as e:
                        on_progress("prompts", f"Could not fetch from Cosmos: {e}")

                # Ensure placeholder substitution for directly-passed prompts too
                _gn = req.graph
                _sp = _gn.rsplit("-", 1)[0] if "-" in _gn else _gn
                prompts = {
                    k: v.replace("{graph_name}", _gn).replace("{scenario_prefix}", _sp)
                    for k, v in prompts.items()
                }

                # Fall back to minimal defaults for any missing agents
                defaults = {
                    "orchestrator": "You are an investigation orchestrator.",
                    "graph_explorer": "You are a graph explorer agent.",
                    "telemetry": "You are a telemetry analysis agent.",
                    "runbook": "You are a runbook knowledge base agent.",
                    "ticket": "You are a historical ticket search agent.",
                }
                for agent, default_prompt in defaults.items():
                    if agent not in prompts:
                        prompts[agent] = default_prompt
                        on_progress("prompts", f"Using default prompt for {agent} (no Cosmos prompt found)")

                # Build search connection ID
                sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
                rg = os.getenv("AZURE_RESOURCE_GROUP", "")
                foundry = os.getenv("AI_FOUNDRY_NAME", "")
                graph_query_uri = os.getenv("GRAPH_QUERY_API_URI", "")
                if not graph_query_uri:
                    _hostname = os.getenv("CONTAINER_APP_HOSTNAME", "")
                    if _hostname:
                        graph_query_uri = f"https://{_hostname}"
                graph_backend = os.getenv("GRAPH_BACKEND", "cosmosdb")

                search_conn_id = (
                    f"/subscriptions/{sub_id}/resourceGroups/{rg}"
                    f"/providers/Microsoft.CognitiveServices"
                    f"/accounts/{foundry}/projects/{project_name}"
                    f"/connections/aisearch-connection"
                )

                on_progress("provisioning", "Starting agent provisioning...")

                # Try config-driven provisioning first (Phase 8)
                scenario_config = None
                try:
                    import urllib.request as _ur2
                    import json as _j2
                    _cfg_url = (
                        f"http://127.0.0.1:8100/query/scenario/config"
                        f"?scenario={urllib.parse.quote(scenario_prefix)}"
                    )
                    with _ur2.urlopen(_ur2.Request(_cfg_url), timeout=10) as _resp:
                        _cfg_data = _j2.loads(_resp.read())
                        if _cfg_data.get("config", {}).get("agents"):
                            scenario_config = _cfg_data["config"]
                            on_progress("provisioning", "Using config-driven provisioning")
                except Exception:
                    pass  # No config stored — use legacy path

                if scenario_config and scenario_config.get("agents"):
                    # Config-driven: provision N agents from scenario.yaml
                    result = provisioner.provision_from_config(
                        config=scenario_config,
                        graph_query_api_uri=graph_query_uri,
                        search_connection_id=search_conn_id,
                        graph_name=req.graph,
                        prompts=prompts,
                        force=True,
                        on_progress=on_progress,
                    )
                    n_agents = len(scenario_config["agents"])
                else:
                    # Legacy: provision hardcoded 5 agents
                    result = provisioner.provision_all(
                        model=model,
                        prompts=prompts,
                        graph_query_api_uri=graph_query_uri,
                        graph_backend=graph_backend,
                        graph_name=req.graph,
                        runbooks_index=req.runbooks_index,
                        tickets_index=req.tickets_index,
                        search_connection_id=search_conn_id,
                        force=True,
                        on_progress=on_progress,
                    )
                    n_agents = 5

                # Update in-memory config
                with _config_lock:
                    global _current_config
                    _current_config = {
                        "graph": req.graph,
                        "runbooks_index": req.runbooks_index,
                        "tickets_index": req.tickets_index,
                        "agents": result,
                    }

                progress.put_nowait({
                    "step": "done",
                    "detail": f"All {n_agents} agents re-provisioned. Orchestrator: {result['orchestrator']['id']}",
                    "result": result,
                })

            except Exception as e:
                logger.exception("Agent provisioning failed")
                progress.put_nowait({"step": "error", "detail": str(e)})
            finally:
                await asyncio.sleep(0)  # yield to event loop
                progress.put_nowait(None)  # sentinel

        task = asyncio.create_task(run_provisioning())

        while True:
            event = await progress.get()
            if event is None:
                break
            step = event.get("step", "")
            if step == "error":
                yield {"event": "error", "data": json.dumps(event)}
            elif step == "done":
                yield {"event": "complete", "data": json.dumps(event)}
            else:
                yield {"event": "progress", "data": json.dumps(event)}

        await task

    return EventSourceResponse(event_generator())


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
        if ag.get("instructions_file"):
            meta["instructions"] = ag["instructions_file"]
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
            "cosmosdb_gremlin": "datasource",
            "cosmosdb_nosql": "datasource",
            "azure_ai_search": "search-index",
            "blob_storage": "blob-container",
        }
        nt = node_type_map.get(ds_type, "datasource")
        ds_label = ds_def.get("label", ds_key)
        if ds_type == "cosmosdb_gremlin":
            ds_meta["database"] = ds_def.get("database", "")
            ds_meta["graph"] = ds_def.get("graph", "")
        elif ds_type == "cosmosdb_nosql":
            ds_meta["database"] = ds_def.get("database", "")
            ds_meta["container"] = ds_def.get("container", "")
        elif ds_type == "azure_ai_search":
            ds_meta["index"] = ds_def.get("index", "")
        elif ds_type == "blob_storage":
            ds_meta["container"] = ds_def.get("container", "")
        nodes.append({"id": f"ds-{ds_key}", "label": ds_label, "type": nt, "meta": ds_meta})

    # ── Infrastructure layer (from env vars) ─────────────────────────────
    infra_nodes = [
        ("infra-foundry", "AI Foundry", "foundry",
         {"resource": os.getenv("AI_FOUNDRY_NAME", ""), "project": os.getenv("AI_FOUNDRY_PROJECT_NAME", "")}),
        ("infra-cosmos-g", "Cosmos DB (Gremlin)", "cosmos-account",
         {"resource": os.getenv("COSMOS_GREMLIN_ENDPOINT", ""), "api": "Gremlin"}),
        ("infra-cosmos-n", "Cosmos DB (NoSQL)", "cosmos-account",
         {"resource": os.getenv("COSMOS_NOSQL_ENDPOINT", ""), "api": "NoSQL"}),
        ("infra-storage", "Storage Account", "storage",
         {"resource": os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "")}),
        ("infra-search", "AI Search", "search-service",
         {"resource": os.getenv("AZURE_SEARCH_ENDPOINT", "")}),
    ]
    for nid, label, ntype, meta in infra_nodes:
        nodes.append({"id": nid, "label": label, "type": ntype, "meta": meta})

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
        if ds_type == "cosmosdb_gremlin":
            edges.append({"source": f"ds-{ds_key}", "target": "infra-cosmos-g", "type": "contains", "label": ""})
        elif ds_type == "cosmosdb_nosql":
            edges.append({"source": f"ds-{ds_key}", "target": "infra-cosmos-n", "type": "contains", "label": ""})
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
        {"id": "infra-cosmos-g", "label": "Cosmos DB (Gremlin)", "type": "cosmos-account",
         "meta": {"resource": os.getenv("COSMOS_GREMLIN_ENDPOINT", ""), "api": "Gremlin"}},
        {"id": "infra-cosmos-n", "label": "Cosmos DB (NoSQL)", "type": "cosmos-account",
         "meta": {"resource": os.getenv("COSMOS_NOSQL_ENDPOINT", ""), "api": "NoSQL"}},
        {"id": "infra-storage", "label": "Storage Account", "type": "storage",
         "meta": {"resource": os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "")}},
        {"id": "infra-search", "label": "AI Search", "type": "search-service",
         "meta": {"resource": os.getenv("AZURE_SEARCH_ENDPOINT", "")}},
    ]


@router.get("/resources", summary="Get resource graph for visualization")
async def get_resource_graph(request: Request):
    """Build and return the nodes+edges resource graph from the active scenario config."""
    import urllib.request
    import urllib.parse

    # Determine active scenario — prefer X-Scenario header, fall back to graph-name derivation
    cfg = _load_current_config()
    graph = cfg.get("graph", "topology")
    scenario_name = (
        request.headers.get("X-Scenario")
        or (graph.rsplit("-", 1)[0] if "-" in graph else graph)
    )

    if not scenario_name or scenario_name == "topology":
        return {"nodes": _infra_nodes_only(), "edges": [], "scenario": scenario_name,
                "error": "No active scenario detected"}

    try:
        cfg_url = (
            f"http://127.0.0.1:8100/query/scenario/config"
            f"?scenario={urllib.parse.quote(scenario_name)}"
        )
        with urllib.request.urlopen(urllib.request.Request(cfg_url), timeout=10) as resp:
            cfg_data = json.loads(resp.read())
            config = cfg_data.get("config", {})

        if config.get("agents") or config.get("data_sources"):
            return _build_resource_graph(config, scenario_name)
    except Exception as e:
        logger.warning("Failed to fetch scenario config for '%s': %s", scenario_name, e)
        return {"nodes": _infra_nodes_only(), "edges": [], "scenario": scenario_name,
                "error": f"Could not load config for '{scenario_name}': {e}"}

    # Config exists but has no agents/data_sources
    return {"nodes": _infra_nodes_only(), "edges": [], "scenario": scenario_name,
            "error": f"Scenario '{scenario_name}' has no agents or data sources configured"}
