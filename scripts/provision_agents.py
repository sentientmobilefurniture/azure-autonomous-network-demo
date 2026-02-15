"""
provision_agents.py — CLI wrapper for agent provisioning.

Thin CLI that loads config + prompts from disk and delegates to
AgentProvisioner (agent_provisioner.py) for all Foundry API calls.

Usage:
    uv run python provision_agents.py [--force]

Options:
    --force   Delete any existing agents with matching names before creating
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_provisioner import (
    AgentProvisioner,
    AGENT_IDS_FILE,
    _build_connection_id,
    AI_SEARCH_CONNECTION_NAME,
)

# ── Paths ─────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_ROOT / "data" / "prompts"
CONFIG_FILE = PROJECT_ROOT / "azure_config.env"

LANGUAGE_FILE_MAP = {
    "cosmosdb": "language_gremlin.md",
    "mock": "language_mock.md",
}


# ── Config helpers ────────────────────────────────────────────────


def _load_config() -> dict:
    """Load azure_config.env and return validated config dict."""
    load_dotenv(CONFIG_FILE, override=True)

    required = [
        "PROJECT_ENDPOINT",
        "MODEL_DEPLOYMENT_NAME",
        "RUNBOOKS_INDEX_NAME",
        "TICKETS_INDEX_NAME",
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_RESOURCE_GROUP",
        "AI_FOUNDRY_NAME",
        "AI_FOUNDRY_PROJECT_NAME",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing required config in {CONFIG_FILE}: {', '.join(missing)}")
        sys.exit(1)

    graph_query_api_uri = os.environ.get("GRAPH_QUERY_API_URI", "")
    if not graph_query_api_uri:
        print("WARNING: GRAPH_QUERY_API_URI not set. GraphExplorer and Telemetry agents")
        print("         will be created WITHOUT tools.")

    base_endpoint = os.environ["PROJECT_ENDPOINT"].rstrip("/")
    project_name = os.environ["AI_FOUNDRY_PROJECT_NAME"]
    project_endpoint = f"{base_endpoint}/api/projects/{project_name}"

    return {
        "project_endpoint": project_endpoint,
        "model": os.environ["MODEL_DEPLOYMENT_NAME"],
        "runbooks_index": os.environ["RUNBOOKS_INDEX_NAME"],
        "tickets_index": os.environ["TICKETS_INDEX_NAME"],
        "subscription_id": os.environ["AZURE_SUBSCRIPTION_ID"],
        "resource_group": os.environ["AZURE_RESOURCE_GROUP"],
        "foundry_name": os.environ["AI_FOUNDRY_NAME"],
        "project_name": project_name,
        "graph_query_api_uri": graph_query_api_uri,
        "graph_backend": os.environ.get("GRAPH_BACKEND", "cosmosdb").lower(),
        "graph_name": os.environ.get("COSMOS_GREMLIN_GRAPH", "topology"),
    }


# ── Prompt loaders ────────────────────────────────────────────────


def _substitute_placeholders(text: str, graph_name: str) -> str:
    """Replace {graph_name} and {scenario_prefix} in prompt text."""
    scenario_prefix = graph_name.rsplit("-", 1)[0] if "-" in graph_name else graph_name
    return text.replace("{graph_name}", graph_name).replace("{scenario_prefix}", scenario_prefix)


def _load_prompt(filename: str, graph_name: str) -> str:
    """Load a prompt file from disk, with placeholder substitution."""
    path = PROMPTS_DIR / filename
    return _substitute_placeholders(path.read_text(encoding="utf-8").strip(), graph_name)


def _load_graph_explorer_prompt(backend: str, graph_name: str) -> str:
    """Compose the GraphExplorer prompt from parts."""
    base = PROMPTS_DIR / "graph_explorer"
    language_file = LANGUAGE_FILE_MAP.get(backend, "language_gremlin.md")
    instructions = "\n\n---\n\n".join([
        (base / "core_instructions.md").read_text(encoding="utf-8").strip(),
        (base / "core_schema.md").read_text(encoding="utf-8").strip(),
        (base / language_file).read_text(encoding="utf-8").strip(),
    ])
    return _substitute_placeholders(instructions, graph_name)


def _load_all_prompts(config: dict) -> dict[str, str]:
    """Load all 5 agent prompts from disk."""
    gn = config["graph_name"]
    return {
        "orchestrator": _load_prompt("foundry_orchestrator_agent.md", gn),
        "graph_explorer": _load_graph_explorer_prompt(config["graph_backend"], gn),
        "telemetry": _load_prompt("foundry_telemetry_agent_v2.md", gn),
        "runbook": _load_prompt("foundry_runbook_kb_agent.md", gn),
        "ticket": _load_prompt("foundry_historical_ticket_agent.md", gn),
    }


# ── Main ──────────────────────────────────────────────────────────


def main():
    force = "--force" in sys.argv

    print("=" * 72)
    print("  Autonomous Network NOC Demo — Agent Provisioning")
    print("=" * 72)

    config = _load_config()
    print(f"\n  Project endpoint: {config['project_endpoint']}")
    print(f"  Model: {config['model']}")
    print(f"  Graph backend: {config['graph_backend']}")
    if config["graph_query_api_uri"]:
        print(f"  Graph Query API: {config['graph_query_api_uri']}")

    prompts = _load_all_prompts(config)

    search_conn_id = _build_connection_id(
        config["subscription_id"],
        config["resource_group"],
        config["foundry_name"],
        config["project_name"],
        AI_SEARCH_CONNECTION_NAME,
    )
    print(f"  AI Search connection: {search_conn_id}")

    provisioner = AgentProvisioner(config["project_endpoint"])
    result = provisioner.provision_all(
        model=config["model"],
        prompts=prompts,
        graph_query_api_uri=config["graph_query_api_uri"],
        graph_backend=config["graph_backend"],
        graph_name=config["graph_name"],
        runbooks_index=config["runbooks_index"],
        tickets_index=config["tickets_index"],
        search_connection_id=search_conn_id,
        force=force,
        on_progress=lambda step, detail: print(f"  [{step}] {detail}"),
    )

    print("\n" + "=" * 72)
    print("  Provisioning complete!")
    print("=" * 72)
    print(f"\n  Orchestrator ID: {result['orchestrator']['id']}")
    print(f"  Agent IDs saved to: {AGENT_IDS_FILE}")
    print(f"\n  To test: uv run python test_orchestrator.py")
    print()


if __name__ == "__main__":
    main()
