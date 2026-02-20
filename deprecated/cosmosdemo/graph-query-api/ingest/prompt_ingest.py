"""Prompt upload endpoint — stores .md prompts in Cosmos platform-config."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile

from adapters.cosmos_config import COSMOS_NOSQL_ENDPOINT
from sse_helpers import SSEProgress, sse_upload_response

from .manifest import _extract_tar, _resolve_scenario_name, _validate_upload

logger = logging.getLogger("graph-query-api.ingest")

router = APIRouter()


# ---------------------------------------------------------------------------
# Prompt ↔ agent mapping
# ---------------------------------------------------------------------------

# Legacy hardcoded prompt-to-agent mapping (backward compatibility).
# Config-driven scenarios use the agents[].instructions_file field instead.
PROMPT_AGENT_MAP = {
    "foundry_orchestrator_agent.md": "orchestrator",
    "orchestrator.md": "orchestrator",
    "foundry_telemetry_agent_v2.md": "telemetry",
    "telemetry_agent.md": "telemetry",
    "foundry_runbook_kb_agent.md": "runbook",
    "runbook_agent.md": "runbook",
    "foundry_historical_ticket_agent.md": "ticket",
    "ticket_agent.md": "ticket",
    "alert_storm.md": "default_alert",
    "default_alert.md": "default_alert",
}


def _build_prompt_agent_map_from_config(config: dict) -> dict[str, str]:
    """Build filename → agent_role mapping from scenario config agents section.

    For each agent in config['agents'], maps its instructions_file basename
    to the agent's role. Handles both single files and directories
    (compose_with_connector).

    Returns:
        Dict mapping prompt filename → agent role string.
    """
    mapping: dict[str, str] = {}
    for agent_def in config.get("agents", []):
        role = agent_def.get("role", agent_def["name"])
        instr = agent_def.get("instructions_file", "")
        if not instr:
            continue
        # Directory reference (ends with /) → store directory name as key
        if instr.endswith("/"):
            dir_name = instr.rstrip("/").split("/")[-1]
            mapping[f"__dir__{dir_name}"] = role
        else:
            # Single file → map basename
            fname = instr.split("/")[-1]
            mapping[fname] = role
    return mapping


def _get_composed_agents_from_config(config: dict) -> dict[str, dict]:
    """Extract agents that use compose_with_connector from config.

    Returns:
        Dict mapping directory name → agent config dict.
    """
    result: dict[str, dict] = {}
    for agent_def in config.get("agents", []):
        if agent_def.get("compose_with_connector"):
            instr = agent_def.get("instructions_file", "")
            if instr.endswith("/"):
                dir_name = instr.rstrip("/").split("/")[-1]
                result[dir_name] = agent_def
    return result


def _resolve_connector_for_agent(agent_def: dict, config: dict) -> str:
    """Determine which data source connector an agent uses.

    Looks at the agent's tools to find the first tool that references a
    data source, then returns that data source's connector type.
    """
    ds = config.get("data_sources", {})
    for tool_def in agent_def.get("tools", []):
        if tool_def.get("type") == "openapi":
            template = tool_def.get("spec_template", "")
            if template == "graph" and "graph" in ds:
                return ds["graph"].get("connector", "cosmosdb-gremlin")
            if template == "telemetry" and "telemetry" in ds:
                return ds["telemetry"].get("connector", "cosmosdb-nosql")
    return "cosmosdb-gremlin"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/upload/prompts", summary="Upload prompts to Cosmos DB")
async def upload_prompts(
    file: UploadFile = File(...),
    scenario_name: str | None = Query(
        default=None, description="Override scenario name from scenario.yaml"
    ),
):
    """Upload a tarball of .md prompt files. Stores in Cosmos platform-config.prompts.
    If scenario_name is provided, it overrides the name from scenario.yaml."""
    content = await _validate_upload(file)

    async def work(progress: SSEProgress):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            _extract_tar(content, tmppath)  # reuse shared extraction

            sc_name = _resolve_scenario_name(tmppath, scenario_name)

            all_md = list(tmppath.rglob("*.md"))
            if not all_md:
                progress.error("No .md prompt files found in archive")
                return

            progress.emit("prompts", f"Found {len(all_md)} .md files for scenario '{sc_name}'", 10)

            if not COSMOS_NOSQL_ENDPOINT:
                progress.error("COSMOS_NOSQL_ENDPOINT not configured")
                return

            # Try to load scenario config for config-driven prompt mapping
            scenario_config: dict | None = None
            try:
                from config_store import fetch_scenario_config
                scenario_config = await fetch_scenario_config(sc_name)
                progress.emit("prompts", "Using config-driven prompt mapping", 12)
            except Exception:
                progress.emit("prompts", "No scenario config — using legacy prompt mapping", 12)

            # Build prompt-to-agent mapping
            if scenario_config and scenario_config.get("agents"):
                config_prompt_map = _build_prompt_agent_map_from_config(scenario_config)
                composed_agents = _get_composed_agents_from_config(scenario_config)
            else:
                config_prompt_map = {}
                composed_agents = {}

            def _store():
                from cosmos_helpers import get_or_create_container
                from prompt_helpers import get_next_version

                container = get_or_create_container(
                    "prompts", sc_name, "/agent", ensure_created=True,
                )
                stored = []

                # Derive graph name for placeholder substitution
                graph_name = f"{sc_name}-topology"

                def _sub(text: str) -> str:
                    """Replace {graph_name} and {scenario_prefix} placeholders."""
                    return text.replace("{graph_name}", graph_name).replace("{scenario_prefix}", sc_name)

                # Find prompts dir (parent of graph_explorer/ or where prompt .md files live)
                prompts_dir = None
                for md in all_md:
                    if md.name in PROMPT_AGENT_MAP or md.name in config_prompt_map:
                        prompts_dir = md.parent
                        break
                if not prompts_dir:
                    prompts_dir = all_md[0].parent

                # Determine which directories are composed (from config or legacy)
                composed_dir_names = set(composed_agents.keys()) if composed_agents else {"graph_explorer"}

                # Store individual prompts
                for md_file in all_md:
                    # Skip files in composed directories — handled separately
                    if md_file.parent.name in composed_dir_names:
                        continue

                    # Resolve agent role: config-driven first, then legacy fallback
                    agent = config_prompt_map.get(md_file.name) or PROMPT_AGENT_MAP.get(md_file.name)
                    if not agent:
                        continue

                    txt = _sub(md_file.read_text())
                    nv = get_next_version(container, sc_name, agent, md_file.stem)
                    did = f"{sc_name}__{md_file.stem}__v{nv}"
                    container.upsert_item({
                        "id": did, "agent": agent, "scenario": sc_name,
                        "name": md_file.stem, "version": nv, "content": txt,
                        "description": f"Uploaded from {sc_name}-prompts.tar.gz",
                        "tags": [sc_name, agent], "is_active": True, "deleted": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "created_by": "ui-upload",
                    })
                    stored.append(did)
                    progress.emit(
                        "prompts",
                        f"Stored {agent}: {md_file.name} (v{nv})",
                        20 + len(stored) * 8,
                    )

                # Compose prompts from subdirectories
                for dir_name in composed_dir_names:
                    comp_dir = prompts_dir / dir_name
                    if not comp_dir.exists():
                        for d in tmppath.rglob(dir_name):
                            if d.is_dir():
                                comp_dir = d
                                break
                    if not comp_dir.exists():
                        continue

                    # Determine agent role for this directory
                    agent_role = config_prompt_map.get(f"__dir__{dir_name}", dir_name)

                    # Determine which language file to use
                    if dir_name in composed_agents and scenario_config:
                        agent_def = composed_agents[dir_name]
                        connector = _resolve_connector_for_agent(agent_def, scenario_config)
                        language_suffix = connector.split("-")[-1]  # "gremlin", "nosql", "kusto"
                        language_file = f"language_{language_suffix}.md"
                    else:
                        # Legacy: always use gremlin
                        language_file = "language_gremlin.md"

                    # Collect all .md files, skip non-matching language files
                    parts = []
                    for pf in sorted(comp_dir.glob("*.md")):
                        if pf.name.startswith("language_") and pf.name != language_file:
                            continue
                        parts.append(pf.read_text())

                    if parts:
                        composed = _sub("\n\n---\n\n".join(parts))
                        nv = get_next_version(container, sc_name, agent_role, dir_name)
                        did = f"{sc_name}__{dir_name}__v{nv}"
                        container.upsert_item({
                            "id": did, "agent": agent_role, "scenario": sc_name,
                            "name": dir_name, "version": nv, "content": composed,
                            "description": f"Composed from {dir_name}/ ({sc_name})",
                            "tags": [sc_name, agent_role, "composed"],
                            "is_active": True, "deleted": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "created_by": "ui-upload",
                        })
                        stored.append(did)
                        progress.emit("prompts", f"Stored {agent_role} (composed from {dir_name}/, v{nv})", 90)

                return stored

            stored = await asyncio.to_thread(_store)
            progress.emit("done", f"Stored {len(stored)} prompts for '{sc_name}'", 100)
            progress.complete({
                "scenario": sc_name,
                "prompts_stored": len(stored),
                "ids": stored,
            })

    return sse_upload_response(work, error_label="prompts upload")
