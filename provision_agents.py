"""
provision_agents.py — Create Foundry Agents for the Autonomous Network NOC Demo.

Uses the Azure AI Agents SDK to programmatically create all 5 agents:
  1. GraphExplorerAgent   — FabricTool (ontology graph via Fabric Data Agent)
  2. TelemetryAgent       — FabricTool (Eventhouse via Fabric Data Agent)
  3. RunbookKBAgent       — AzureAISearchTool (runbooks-index)
  4. HistoricalTicketAgent — AzureAISearchTool (tickets-index)
  5. Orchestrator          — ConnectedAgentTool (wired to all 4 above)

Prerequisites:
  - 'azd up' completed (infra deployed, azure_config.env populated)
  - Fabric Data Agent created in Fabric portal
  - Fabric connection added to AI Foundry project (Connected Resources)
  - Search indexes created (create_runbook_indexer.py, create_tickets_indexer.py)

Usage:
  uv run python provision_agents.py [--force]

Options:
  --force   Delete any existing agents with matching names before creating new ones
"""

import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    AzureAISearchTool,
    AzureAISearchQueryType,
    ConnectedAgentTool,
    FabricTool,
)


# ── Paths ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = PROJECT_ROOT / "data" / "prompts"
CONFIG_FILE = PROJECT_ROOT / "azure_config.env"
AGENT_IDS_FILE = PROJECT_ROOT / "agent_ids.json"


# ── Config ──────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load azure_config.env and return as dict."""
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

    # Support both new (per-agent) and legacy (shared) Fabric connection names
    graph_conn = os.environ.get("GRAPH_FABRIC_CONNECTION_NAME", "") or os.environ.get("FABRIC_CONNECTION_NAME", "")
    telemetry_conn = os.environ.get("TELEMETRY_FABRIC_CONNECTION_NAME", "") or os.environ.get("FABRIC_CONNECTION_NAME", "")

    # Compute project-scoped endpoint
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
        "graph_fabric_connection_name": graph_conn,
        "telemetry_fabric_connection_name": telemetry_conn,
    }


def load_prompt(filename: str) -> tuple[str, str]:
    """Load a prompt file and extract the instructions and description.

    Returns (instructions, description) where description is the last
    paragraph after '## Foundry Agent Description'.
    """
    path = PROMPTS_DIR / filename
    text = path.read_text(encoding="utf-8").strip()

    # Extract description (last line after "## Foundry Agent Description")
    description = ""
    if "## Foundry Agent Description" in text:
        desc_section = text.split("## Foundry Agent Description")[-1].strip()
        # Description is the text between > markers
        for line in desc_section.splitlines():
            line = line.strip()
            if line.startswith(">"):
                description += line.lstrip("> ").strip() + " "
        description = description.strip()

    return text, description


# ── Interactive pause ───────────────────────────────────────────────

def prompt_fabric_connections(config: dict) -> tuple[str, str]:
    """Prompt user to set up Fabric connections if not configured.

    Returns (graph_connection_name, telemetry_connection_name).
    Each may be empty if the user skips.
    """
    graph_conn = config["graph_fabric_connection_name"]
    telemetry_conn = config["telemetry_fabric_connection_name"]

    if graph_conn and telemetry_conn:
        print(f"  Graph Fabric connection:     {graph_conn}")
        print(f"  Telemetry Fabric connection: {telemetry_conn}")
        return graph_conn, telemetry_conn

    print()
    print("=" * 72)
    print("  MANUAL STEP REQUIRED: Connect Fabric Data Agents to AI Foundry")
    print("=" * 72)
    print()
    print("  Each Fabric Data Agent must be connected to your AI Foundry project")
    print("  as a 'Connected Resource' before agents can use the FabricTool.")
    print()
    print("  You need TWO Fabric connections — one per Data Agent:")
    print("    • Graph/Ontology Data Agent  (Lakehouse)  → GraphExplorerAgent")
    print("    • Telemetry Data Agent       (Eventhouse)  → TelemetryAgent")
    print()
    print(f"  Workspace ID:            {os.environ.get('FABRIC_WORKSPACE_ID', '(not set)')}")
    print(f"  Graph Data Agent ID:     {os.environ.get('GRAPH_DATA_AGENT_ID', '(not set)')}")
    print(f"  Telemetry Data Agent ID: {os.environ.get('TELEMETRY_DATA_AGENT_ID', '(not set)')}")
    print()
    print("  Steps:")
    print("    1. In the AI Foundry portal, go to your project's 'Connected Resources':")
    print(f"       Project: {os.environ.get('AI_FOUNDRY_PROJECT_NAME', '(not set)')}")
    print(f"       Endpoint: {config['project_endpoint']}")
    print("    2. Click '+ New Connection' → 'Microsoft Fabric'.")
    print("    3. Select the Graph/Ontology Data Agent's workspace and complete.")
    print("    4. Repeat for the Telemetry Data Agent.")
    print("    5. Note both connection names.")
    print()
    print("-" * 72)

    if not graph_conn:
        while True:
            name = input("  Graph/Ontology Fabric connection name (or 'skip'): ").strip()
            if name:
                break
            print("  Please enter a name or 'skip'.")
        if name.lower() != "skip":
            graph_conn = name
            _update_config_env("GRAPH_FABRIC_CONNECTION_NAME", name)
            print(f"  Saved GRAPH_FABRIC_CONNECTION_NAME={name}")
        else:
            print("  Skipping Graph Fabric connection.")

    if not telemetry_conn:
        while True:
            name = input("  Telemetry Fabric connection name (or 'skip'): ").strip()
            if name:
                break
            print("  Please enter a name or 'skip'.")
        if name.lower() != "skip":
            telemetry_conn = name
            _update_config_env("TELEMETRY_FABRIC_CONNECTION_NAME", name)
            print(f"  Saved TELEMETRY_FABRIC_CONNECTION_NAME={name}")
        else:
            print("  Skipping Telemetry Fabric connection.")

    return graph_conn, telemetry_conn


def _update_config_env(key: str, value: str):
    """Update a key in azure_config.env in-place."""
    lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    CONFIG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Agent cleanup ───────────────────────────────────────────────────

AGENT_NAMES = [
    "GraphExplorerAgent",
    "TelemetryAgent",
    "RunbookKBAgent",
    "HistoricalTicketAgent",
    "Orchestrator",
]


def cleanup_existing_agents(agents_client, force: bool):
    """Delete existing agents with known names if --force is set."""
    if not force:
        return

    print("\n  Cleaning up existing agents (--force)...")
    existing = agents_client.list_agents()
    for agent in existing:
        if agent.name in AGENT_NAMES:
            print(f"    Deleting {agent.name} ({agent.id})...")
            agents_client.delete_agent(agent.id)
    print("    Done.")


# ── Connection ID helpers ───────────────────────────────────────────

AI_SEARCH_CONNECTION_NAME = "aisearch-connection"  # from infra/modules/ai-foundry.bicep


def _build_connection_id(config: dict, connection_name: str) -> str:
    """Build a project-scoped connection ID from config values.

    Format: /subscriptions/{sub}/resourceGroups/{rg}/providers/
            Microsoft.CognitiveServices/accounts/{foundry}/
            projects/{project}/connections/{name}

    FabricTool requires this project-scoped format.
    """
    return (
        f"/subscriptions/{config['subscription_id']}"
        f"/resourceGroups/{config['resource_group']}"
        f"/providers/Microsoft.CognitiveServices"
        f"/accounts/{config['foundry_name']}"
        f"/projects/{config['project_name']}"
        f"/connections/{connection_name}"
    )


def get_fabric_connection_id(config: dict, fabric_conn_name: str, label: str = "") -> str | None:
    """Build the full connection ID for a Fabric connection."""
    if not fabric_conn_name:
        return None
    prefix = f"  [{label}] " if label else "  "
    conn_id = _build_connection_id(config, fabric_conn_name)
    print(f"{prefix}Fabric connection ID: {conn_id}")
    return conn_id


def get_search_connection_id(config: dict) -> str:
    """Build the full connection ID for the AI Search connection."""
    conn_id = _build_connection_id(config, AI_SEARCH_CONNECTION_NAME)
    print(f"  AI Search connection ID: {conn_id}")
    return conn_id


def _make_fabric_tool(connection_id: str) -> list:
    """Build a FabricTool definitions list for create_agent.

    Returns the .definitions list from FabricTool, suitable for passing
    directly to the 'tools' parameter of create_agent().
    """
    fabric = FabricTool(connection_id=connection_id)
    return fabric.definitions


def create_graph_explorer_agent(agents_client, model: str, fabric_conn_id: str | None) -> dict:
    """Create the GraphExplorerAgent with FabricTool."""
    instructions, description = load_prompt("foundry_graph_explorer_agent.md")

    tools = _make_fabric_tool(fabric_conn_id) if fabric_conn_id else []

    agent = agents_client.create_agent(
        model=model,
        name="GraphExplorerAgent",
        instructions=instructions,
        tools=tools,
    )
    print(f"  Created GraphExplorerAgent: {agent.id}")
    return {"id": agent.id, "name": agent.name, "description": description}


def create_telemetry_agent(agents_client, model: str, fabric_conn_id: str | None) -> dict:
    """Create the TelemetryAgent with FabricTool."""
    instructions, description = load_prompt("foundry_telemetry_agent.md")

    tools = _make_fabric_tool(fabric_conn_id) if fabric_conn_id else []

    agent = agents_client.create_agent(
        model=model,
        name="TelemetryAgent",
        instructions=instructions,
        tools=tools,
    )
    print(f"  Created TelemetryAgent: {agent.id}")
    return {"id": agent.id, "name": agent.name, "description": description}


def create_runbook_kb_agent(agents_client, model: str, search_conn_id: str, index_name: str) -> dict:
    """Create the RunbookKBAgent with AzureAISearchTool."""
    instructions, description = load_prompt("foundry_runbook_kb_agent.md")

    ai_search = AzureAISearchTool(
        index_connection_id=search_conn_id,
        index_name=index_name,
        query_type=AzureAISearchQueryType.SEMANTIC,
        top_k=5,
    )

    agent = agents_client.create_agent(
        model=model,
        name="RunbookKBAgent",
        instructions=instructions,
        tools=ai_search.definitions,
        tool_resources=ai_search.resources,
    )
    print(f"  Created RunbookKBAgent: {agent.id}")
    return {"id": agent.id, "name": agent.name, "description": description}


def create_historical_ticket_agent(agents_client, model: str, search_conn_id: str, index_name: str) -> dict:
    """Create the HistoricalTicketAgent with AzureAISearchTool."""
    instructions, description = load_prompt("foundry_historical_ticket_agent.md")

    ai_search = AzureAISearchTool(
        index_connection_id=search_conn_id,
        index_name=index_name,
        query_type=AzureAISearchQueryType.SEMANTIC,
        top_k=5,
    )

    agent = agents_client.create_agent(
        model=model,
        name="HistoricalTicketAgent",
        instructions=instructions,
        tools=ai_search.definitions,
        tool_resources=ai_search.resources,
    )
    print(f"  Created HistoricalTicketAgent: {agent.id}")
    return {"id": agent.id, "name": agent.name, "description": description}


def create_orchestrator(agents_client, model: str, sub_agents: list[dict]) -> dict:
    """Create the Orchestrator wired to all sub-agents via ConnectedAgentTool."""
    instructions, description = load_prompt("foundry_orchestrator_agent.md")

    # Wire each sub-agent as a ConnectedAgentTool
    connected_tools = []
    for sa in sub_agents:
        ct = ConnectedAgentTool(
            id=sa["id"],
            name=sa["name"],
            description=sa["description"],
        )
        connected_tools.extend(ct.definitions)

    agent = agents_client.create_agent(
        model=model,
        name="Orchestrator",
        instructions=instructions,
        tools=connected_tools,
    )
    print(f"  Created Orchestrator: {agent.id}")
    return {"id": agent.id, "name": agent.name, "description": description}


# ── Save results ────────────────────────────────────────────────────

def save_agent_ids(agents: dict):
    """Save agent IDs to agent_ids.json for use by test scripts."""
    AGENT_IDS_FILE.write_text(json.dumps(agents, indent=2) + "\n", encoding="utf-8")
    print(f"\n  Agent IDs saved to {AGENT_IDS_FILE.name}")


# ── Main ────────────────────────────────────────────────────────────

def main():
    force = "--force" in sys.argv

    print("=" * 72)
    print("  Autonomous Network NOC Demo — Agent Provisioning")
    print("=" * 72)

    # 1. Load config
    print("\n[1/6] Loading configuration...")
    config = load_config()
    print(f"  Project endpoint: {config['project_endpoint']}")
    print(f"  Model: {config['model']}")

    # 2. Prompt for Fabric connections if needed
    print("\n[2/6] Checking Fabric connections...")
    graph_conn_name, telemetry_conn_name = prompt_fabric_connections(config)

    # 3. Connect to Foundry
    print("\n[3/6] Connecting to AI Foundry...")
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(
        endpoint=config["project_endpoint"],
        credential=credential,
    )

    with project_client:
        agents_client = project_client.agents

        # Clean up if --force
        cleanup_existing_agents(agents_client, force)

        # Resolve connection IDs
        print("\n[4/6] Resolving connections...")
        graph_fabric_conn_id = get_fabric_connection_id(config, graph_conn_name, "Graph")
        telemetry_fabric_conn_id = get_fabric_connection_id(config, telemetry_conn_name, "Telemetry")
        search_conn_id = get_search_connection_id(config)

        # 4. Create sub-agents
        print("\n[5/6] Creating specialist agents...")
        graph_agent = create_graph_explorer_agent(
            agents_client, config["model"], graph_fabric_conn_id,
        )
        telemetry_agent = create_telemetry_agent(
            agents_client, config["model"], telemetry_fabric_conn_id,
        )
        runbook_agent = create_runbook_kb_agent(
            agents_client, config["model"], search_conn_id, config["runbooks_index"],
        )
        ticket_agent = create_historical_ticket_agent(
            agents_client, config["model"], search_conn_id, config["tickets_index"],
        )

        sub_agents = [graph_agent, telemetry_agent, runbook_agent, ticket_agent]

        # 5. Create orchestrator wired to sub-agents
        print("\n[6/6] Creating orchestrator...")
        orchestrator = create_orchestrator(
            agents_client, config["model"], sub_agents,
        )

    # 6. Save results
    all_agents = {
        "orchestrator": {"id": orchestrator["id"], "name": orchestrator["name"]},
        "sub_agents": {
            sa["name"]: {"id": sa["id"], "name": sa["name"]}
            for sa in sub_agents
        },
    }
    save_agent_ids(all_agents)

    # Summary
    print("\n" + "=" * 72)
    print("  Provisioning complete!")
    print("=" * 72)
    print(f"\n  Orchestrator ID: {orchestrator['id']}")
    print(f"  Sub-agents:")
    for sa in sub_agents:
        if sa["name"] == "GraphExplorerAgent":
            has_tool = "FabricTool" if graph_fabric_conn_id else "(no tool)"
        elif sa["name"] == "TelemetryAgent":
            has_tool = "FabricTool" if telemetry_fabric_conn_id else "(no tool)"
        elif sa["name"] in ("RunbookKBAgent", "HistoricalTicketAgent"):
            has_tool = "AzureAISearchTool"
        else:
            has_tool = "(no tool)"
        print(f"    {sa['name']:30s} {sa['id']}  [{has_tool}]")

    if not graph_fabric_conn_id or not telemetry_fabric_conn_id:
        print("\n  WARNING: Some agents were created WITHOUT FabricTool:")
        if not graph_fabric_conn_id:
            print("    - GraphExplorerAgent  (set GRAPH_FABRIC_CONNECTION_NAME)")
        if not telemetry_fabric_conn_id:
            print("    - TelemetryAgent      (set TELEMETRY_FABRIC_CONNECTION_NAME)")
        print("  To fix: update azure_config.env and re-run with --force")

    print(f"\n  To test: uv run python test_fabric_agent.py")
    print()


if __name__ == "__main__":
    main()
