"""
provision_agents.py — Create Foundry Agents for the Autonomous Network NOC Demo.

Uses the Azure AI Agents SDK to programmatically create all 5 agents:
  1. GraphExplorerAgent   — OpenApiTool (GQL via fabric-query-api)
  2. TelemetryAgent       — OpenApiTool (KQL via fabric-query-api)
  3. RunbookKBAgent       — AzureAISearchTool (runbooks-index)
  4. HistoricalTicketAgent — AzureAISearchTool (tickets-index)
  5. Orchestrator          — ConnectedAgentTool (wired to all 4 above)

Prerequisites:
  - 'azd up' completed (infra deployed, azure_config.env populated)
  - fabric-query-api deployed and healthy (FABRIC_QUERY_API_URI set)
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

import yaml
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    AzureAISearchTool,
    AzureAISearchQueryType,
    ConnectedAgentTool,
    OpenApiTool,
    OpenApiAnonymousAuthDetails,
)


# ── Paths ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_ROOT / "data" / "prompts"
CONFIG_FILE = PROJECT_ROOT / "azure_config.env"
AGENT_IDS_FILE = PROJECT_ROOT / "scripts" / "agent_ids.json"
OPENAPI_SPEC_FILE = PROJECT_ROOT / "fabric-query-api" / "openapi.yaml"


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

    fabric_query_api_uri = os.environ.get("FABRIC_QUERY_API_URI", "")
    if not fabric_query_api_uri:
        print("WARNING: FABRIC_QUERY_API_URI not set. GraphExplorer and Telemetry agents")
        print("         will be created WITHOUT tools. Deploy fabric-query-api first.")

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
        "fabric_query_api_uri": fabric_query_api_uri,
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


# ── OpenAPI tool helpers ────────────────────────────────────────────

def _load_openapi_spec(config: dict, *, keep_path: str | None = None) -> dict:
    """Load the OpenAPI spec from disk and substitute all placeholders.

    Placeholders replaced:
      {base_url}              — fabric-query-api Container App URI
      {workspace_id}          — Fabric workspace GUID
      {graph_model_id}        — GraphModel item GUID
      {eventhouse_query_uri}  — Kusto query URI
      {kql_db_name}           — KQL database name

    If *keep_path* is given (e.g. "/query/graph"), all other paths are
    removed from the spec so the agent only sees its own endpoint.
    """
    raw = OPENAPI_SPEC_FILE.read_text(encoding="utf-8")
    replacements = {
        "{base_url}": config["fabric_query_api_uri"].rstrip("/"),
        "{workspace_id}": os.environ.get("FABRIC_WORKSPACE_ID", ""),
        "{graph_model_id}": os.environ.get("FABRIC_GRAPH_MODEL_ID", ""),
        "{eventhouse_query_uri}": os.environ.get("EVENTHOUSE_QUERY_URI", ""),
        "{kql_db_name}": os.environ.get("FABRIC_KQL_DB_NAME", ""),
    }
    for placeholder, value in replacements.items():
        raw = raw.replace(placeholder, value)
    spec = yaml.safe_load(raw)

    # Filter to a single endpoint when requested
    if keep_path and "paths" in spec:
        spec["paths"] = {k: v for k, v in spec["paths"].items() if k == keep_path}

    return spec


def _make_graph_openapi_tool(config: dict) -> OpenApiTool:
    """Build an OpenApiTool for the /query/graph endpoint only."""
    spec = _load_openapi_spec(config, keep_path="/query/graph")
    return OpenApiTool(
        name="query_graph",
        spec=spec,
        description="Execute a GQL query against the Fabric GraphModel to explore network topology and relationships.",
        auth=OpenApiAnonymousAuthDetails(),
    )


def _make_telemetry_openapi_tool(config: dict) -> OpenApiTool:
    """Build an OpenApiTool for the /query/telemetry endpoint only."""
    spec = _load_openapi_spec(config, keep_path="/query/telemetry")
    return OpenApiTool(
        name="query_telemetry",
        spec=spec,
        description="Execute a KQL query against the Fabric Eventhouse to retrieve alert and link telemetry data.",
        auth=OpenApiAnonymousAuthDetails(),
    )


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
    """
    return (
        f"/subscriptions/{config['subscription_id']}"
        f"/resourceGroups/{config['resource_group']}"
        f"/providers/Microsoft.CognitiveServices"
        f"/accounts/{config['foundry_name']}"
        f"/projects/{config['project_name']}"
        f"/connections/{connection_name}"
    )


def get_search_connection_id(config: dict) -> str:
    """Build the full connection ID for the AI Search connection."""
    conn_id = _build_connection_id(config, AI_SEARCH_CONNECTION_NAME)
    print(f"  AI Search connection ID: {conn_id}")
    return conn_id


def create_graph_explorer_agent(agents_client, model: str, config: dict) -> dict:
    """Create the GraphExplorerAgent with OpenApiTool (GQL via fabric-query-api)."""
    instructions, description = load_prompt("foundry_graph_explorer_agent_v2.md")

    tools = []
    if config["fabric_query_api_uri"]:
        openapi_tool = _make_graph_openapi_tool(config)
        tools = openapi_tool.definitions

    agent = agents_client.create_agent(
        model=model,
        name="GraphExplorerAgent",
        instructions=instructions,
        tools=tools,
    )
    print(f"  Created GraphExplorerAgent: {agent.id}")
    return {"id": agent.id, "name": agent.name, "description": description}


def create_telemetry_agent(agents_client, model: str, config: dict) -> dict:
    """Create the TelemetryAgent with OpenApiTool (KQL via fabric-query-api)."""
    instructions, description = load_prompt("foundry_telemetry_agent_v2.md")

    tools = []
    if config["fabric_query_api_uri"]:
        openapi_tool = _make_telemetry_openapi_tool(config)
        tools = openapi_tool.definitions

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
    print("\n[1/5] Loading configuration...")
    config = load_config()
    print(f"  Project endpoint: {config['project_endpoint']}")
    print(f"  Model: {config['model']}")
    api_uri = config["fabric_query_api_uri"]
    if api_uri:
        print(f"  Fabric Query API: {api_uri}")

    # 2. Connect to Foundry
    print("\n[2/5] Connecting to AI Foundry...")
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
        print("\n[3/5] Resolving connections...")
        search_conn_id = get_search_connection_id(config)

        # 3. Create sub-agents
        print("\n[4/5] Creating specialist agents...")
        graph_agent = create_graph_explorer_agent(
            agents_client, config["model"], config,
        )
        telemetry_agent = create_telemetry_agent(
            agents_client, config["model"], config,
        )
        runbook_agent = create_runbook_kb_agent(
            agents_client, config["model"], search_conn_id, config["runbooks_index"],
        )
        ticket_agent = create_historical_ticket_agent(
            agents_client, config["model"], search_conn_id, config["tickets_index"],
        )

        sub_agents = [graph_agent, telemetry_agent, runbook_agent, ticket_agent]

        # 4. Create orchestrator wired to sub-agents
        print("\n[5/5] Creating orchestrator...")
        orchestrator = create_orchestrator(
            agents_client, config["model"], sub_agents,
        )

    # 5. Save results
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
        if sa["name"] in ("GraphExplorerAgent", "TelemetryAgent"):
            has_tool = "OpenApiTool" if api_uri else "(no tool)"
        elif sa["name"] in ("RunbookKBAgent", "HistoricalTicketAgent"):
            has_tool = "AzureAISearchTool"
        else:
            has_tool = "(unknown)"
        print(f"    {sa['name']:30s} {sa['id']}  [{has_tool}]")

    if not api_uri:
        print("\n  WARNING: GraphExplorerAgent and TelemetryAgent were created WITHOUT tools.")
        print("  To fix: deploy fabric-query-api, set FABRIC_QUERY_API_URI, re-run with --force")

    print(f"\n  To test: uv run python test_orchestrator.py")
    print()


if __name__ == "__main__":
    main()
