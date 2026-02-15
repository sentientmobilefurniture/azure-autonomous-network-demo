"""
Router: /api/config — runtime agent + data source configuration.

POST /api/config/apply   — apply data source + prompt bindings (re-provisions agents)
GET  /api/config/current  — return current active configuration
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
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
                    "detail": f"All 5 agents re-provisioned. Orchestrator: {result['orchestrator']['id']}",
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
