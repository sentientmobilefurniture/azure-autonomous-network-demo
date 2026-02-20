"""
AgentProvisioner — importable agent creation logic.

Extracted from provision_agents.py for use by both:
  - CLI (provision_agents.py --force)
  - API (POST /api/config/apply)

Prompts are passed as strings (not read from disk), enabling store-backed
prompt management and runtime reconfiguration.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import yaml
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    AzureAISearchTool,
    AzureAISearchQueryType,
    ConnectedAgentTool,
    OpenApiTool,
    OpenApiAnonymousAuthDetails,
    FunctionToolDefinition,
    FunctionDefinition,
)

logger = logging.getLogger("agent-provisioner")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_DIR = PROJECT_ROOT / "graph-query-api" / "openapi"

AI_SEARCH_CONNECTION_NAME = "aisearch-connection"

OPENAPI_SPEC_MAP = {
    "mock": OPENAPI_DIR / "mock.yaml",
}

OPENAPI_TEMPLATE_DIR = OPENAPI_DIR / "templates"

# Connector-specific variable expansions for OpenAPI template placeholders.
# Used by _load_openapi_spec() when rendering templates.
CONNECTOR_OPENAPI_VARS: dict[str, dict[str, str]] = {
    "mock": {
        "query_language_description": (
            "Sends a query to the mock graph backend, which returns static network "
            "topology data for offline demonstrations and testing. "
            "Send any query string — natural language or formal syntax."
        ),
        "telemetry_query_language_description": (
            "Submits a SQL query to the mock telemetry backend. "
            "Returns sample telemetry data for offline demonstrations."
        ),
    },
    "fabric": {
        "query_language_description": (
            "GQL (ISO Graph Query Language). Uses MATCH/RETURN syntax. "
            "Example: MATCH (r:CoreRouter) RETURN r.RouterId, r.Hostname. "
            "Do NOT use GraphQL syntax \u2014 GQL is a different language. "
            "Relationships use arrow syntax: MATCH (a)-[r:connects_to]->(b). "
            "Filter with WHERE: MATCH (r:CoreRouter) WHERE r.Region = 'Sydney' "
            "RETURN r.RouterId."
        ),
        "telemetry_query_language_description": (
            "KQL (Kusto Query Language). Queries start with the table name "
            "followed by pipe operators. Example: AlertStream | where "
            "Severity == 'CRITICAL' | top 10 by Timestamp desc | project "
            "AlertId, Timestamp, SourceNodeId, AlertType. Available tables: "
            "AlertStream (network alerts) and LinkTelemetry (link metrics). "
            "Do NOT use SQL syntax (SELECT, FROM, GROUP BY). Use KQL: "
            "project (select columns), summarize (aggregation), top (order+limit), "
            "take (limit), where (filter)."
        ),
    },
}

GRAPH_TOOL_DESCRIPTIONS = {
    "mock": "Query the topology graph (offline mock mode).",
    "fabric": "Execute a GQL query against Microsoft Fabric Graph Model to explore topology and relationships.",
}

AGENT_NAMES = [
    "GraphExplorerAgent",
    "TelemetryAgent",
    "RunbookKBAgent",
    "HistoricalTicketAgent",
    "Orchestrator",
]


def _build_connection_id(
    subscription_id: str,
    resource_group: str,
    foundry_name: str,
    project_name: str,
    connection_name: str,
) -> str:
    return (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices"
        f"/accounts/{foundry_name}"
        f"/projects/{project_name}"
        f"/connections/{connection_name}"
    )


def _load_openapi_spec(
    graph_query_api_uri: str,
    graph_backend: str = "fabric",
    keep_path: str | None = None,
    *,
    spec_template: str | None = None,
) -> dict:
    """Load and expand an OpenAPI spec with connector-specific descriptions.

    If spec_template is provided (e.g. "graph", "telemetry"), loads from
    openapi/templates/{spec_template}.yaml and injects connector-specific
    descriptions. Otherwise falls back to the per-backend spec files
    (openapi/mock.yaml) for backward compatibility.
    """
    if spec_template:
        template_file = OPENAPI_TEMPLATE_DIR / f"{spec_template}.yaml"
        if template_file.exists():
            raw = template_file.read_text(encoding="utf-8")
            # Inject connector-specific descriptions
            connector_vars = CONNECTOR_OPENAPI_VARS.get(graph_backend, {})
            # For telemetry template, use telemetry-specific description
            if spec_template == "telemetry":
                desc = connector_vars.get(
                    "telemetry_query_language_description",
                    connector_vars.get("query_language_description", ""),
                )
            else:
                desc = connector_vars.get("query_language_description", "")
            raw = raw.replace("{query_language_description}", desc)
        else:
            # Template not found — fall through to legacy
            spec_file = OPENAPI_SPEC_MAP.get(graph_backend, OPENAPI_DIR / "mock.yaml")
            raw = spec_file.read_text(encoding="utf-8")
    else:
        spec_file = OPENAPI_SPEC_MAP.get(graph_backend, OPENAPI_DIR / "mock.yaml")
        raw = spec_file.read_text(encoding="utf-8")

    raw = raw.replace("{base_url}", graph_query_api_uri.rstrip("/"))
    spec = yaml.safe_load(raw)
    if keep_path and "paths" in spec:
        # Prefix match: "/query/graph" matches "/query/graph/<scenario>-topology"
        spec["paths"] = {k: v for k, v in spec["paths"].items() if k.startswith(keep_path)}
    return spec


class AgentProvisioner:
    """Runtime agent provisioning — importable from CLI or API."""

    def __init__(
        self,
        project_endpoint: str,
        credential: DefaultAzureCredential | None = None,
    ):
        self.project_endpoint = project_endpoint
        self.credential = credential or DefaultAzureCredential()
        self._project_client: AIProjectClient | None = None

    def _get_client(self) -> AIProjectClient:
        if self._project_client is None:
            self._project_client = AIProjectClient(
                endpoint=self.project_endpoint,
                credential=self.credential,
            )
        return self._project_client

    def cleanup_existing(self) -> int:
        """Delete all agents with known names. Returns count deleted."""
        client = self._get_client()
        agents_client = client.agents
        deleted = 0
        try:
            for agent in agents_client.list_agents(limit=100):
                if agent.name in AGENT_NAMES:
                    logger.info("Deleting %s (%s)", agent.name, agent.id)
                    try:
                        agents_client.delete_agent(agent.id)
                        deleted += 1
                    except Exception as exc:
                        logger.warning("Could not delete %s: %s", agent.id, exc)
        except ResourceNotFoundError as exc:
            # Stale agent references can cause list pagination to fail;
            # log and continue — we'll create fresh agents anyway.
            logger.warning("list_agents hit a stale reference, continuing: %s", exc)
        return deleted

    def provision_all(
        self,
        model: str,
        prompts: dict[str, str],
        graph_query_api_uri: str,
        graph_backend: str,
        runbooks_index: str,
        tickets_index: str,
        search_connection_id: str,
        on_progress: callable | None = None,
    ) -> dict:
        """Provision all 5 agents and return agent_ids structure.

        Always cleans up existing agents with matching names first
        to guarantee idempotent provisioning (no duplicates).

        Args:
            model: Model deployment name (e.g. "gpt-4.1")
            prompts: {agent_name: prompt_content} for all 5 agents
              Keys: "orchestrator", "graph_explorer", "telemetry", "runbook", "ticket"
            graph_query_api_uri: Base URL for OpenAPI tools
            graph_backend: "fabric" or "mock"
            runbooks_index: AI Search index name for RunbookKB
            tickets_index: AI Search index name for HistoricalTicket
            search_connection_id: Foundry connection ID for AI Search
            on_progress: Optional callback(step: str, detail: str)

        Returns:
            Dict matching agent_ids structure
        """
        def emit(step: str, detail: str):
            logger.info("[%s] %s", step, detail)
            if on_progress:
                on_progress(step, detail)

        client = self._get_client()
        agents_client = client.agents

        emit("cleanup", "Deleting existing agents with matching names...")
        deleted = self.cleanup_existing()
        if deleted:
            emit("cleanup", f"Deleted {deleted} existing agent(s)")

        # Create sub-agents
        sub_agents = []

        # 1. GraphExplorer
        emit("graph_explorer", "Creating GraphExplorerAgent...")
        ge_tools = []
        if graph_query_api_uri:
            spec = _load_openapi_spec(graph_query_api_uri, graph_backend, "/query/graph", spec_template="graph")
            tool = OpenApiTool(
                name="query_graph",
                spec=spec,
                description=GRAPH_TOOL_DESCRIPTIONS.get(graph_backend, GRAPH_TOOL_DESCRIPTIONS["fabric"]),
                auth=OpenApiAnonymousAuthDetails(),
            )
            ge_tools = tool.definitions

        ge = agents_client.create_agent(
            model=model,
            name="GraphExplorerAgent",
            instructions=prompts.get("graph_explorer", "You are a graph explorer agent."),
            tools=ge_tools,
        )
        sub_agents.append({"id": ge.id, "name": ge.name, "description": "Graph topology explorer"})
        emit("graph_explorer", f"Created: {ge.id}")

        # 2. Telemetry
        emit("telemetry", "Creating TelemetryAgent...")
        tel_tools = []
        if graph_query_api_uri:
            spec = _load_openapi_spec(graph_query_api_uri, graph_backend, "/query/telemetry", spec_template="telemetry")
            tool = OpenApiTool(
                name="query_telemetry",
                spec=spec,
                description="Execute a KQL query against telemetry data.",
                auth=OpenApiAnonymousAuthDetails(),
            )
            tel_tools = tool.definitions

        tel = agents_client.create_agent(
            model=model,
            name="TelemetryAgent",
            instructions=prompts.get("telemetry", "You are a telemetry agent."),
            tools=tel_tools,
        )
        sub_agents.append({"id": tel.id, "name": tel.name, "description": "Telemetry and alert analyst"})
        emit("telemetry", f"Created: {tel.id}")

        # 3. RunbookKB
        emit("runbook", "Creating RunbookKBAgent...")
        search_tool = AzureAISearchTool(
            index_connection_id=search_connection_id,
            index_name=runbooks_index,
            query_type=AzureAISearchQueryType.SEMANTIC,
            top_k=5,
        )
        rb = agents_client.create_agent(
            model=model,
            name="RunbookKBAgent",
            instructions=prompts.get("runbook", "You are a runbook knowledge base agent."),
            tools=search_tool.definitions,
            tool_resources=search_tool.resources,
        )
        sub_agents.append({"id": rb.id, "name": rb.name, "description": "Operational runbook searcher"})
        emit("runbook", f"Created: {rb.id}")

        # 4. HistoricalTicket
        emit("ticket", "Creating HistoricalTicketAgent...")
        ticket_search = AzureAISearchTool(
            index_connection_id=search_connection_id,
            index_name=tickets_index,
            query_type=AzureAISearchQueryType.SEMANTIC,
            top_k=5,
        )
        tk = agents_client.create_agent(
            model=model,
            name="HistoricalTicketAgent",
            instructions=prompts.get("ticket", "You are a historical ticket agent."),
            tools=ticket_search.definitions,
            tool_resources=ticket_search.resources,
        )
        sub_agents.append({"id": tk.id, "name": tk.name, "description": "Historical incident searcher"})
        emit("ticket", f"Created: {tk.id}")

        # 5. Orchestrator
        emit("orchestrator", "Creating Orchestrator...")
        connected_tools = []
        for sa in sub_agents:
            ct = ConnectedAgentTool(
                id=sa["id"], name=sa["name"], description=sa["description"],
            )
            connected_tools.extend(ct.definitions)

        # FunctionTool definition for dispatch_field_engineer.
        # Uses FunctionToolDefinition with a raw JSON schema — no Python
        # callable needed at provisioning time.  The actual callable is
        # loaded at runtime in orchestrator.py via enable_auto_function_calls.
        dispatch_tool_def = FunctionToolDefinition(
            function=FunctionDefinition(
                name="dispatch_field_engineer",
                description=(
                    "Dispatch a field engineer to a physical site to investigate a "
                    "network incident. Composes a dispatch notification with incident "
                    "details, exact GPS coordinates, and inspection checklist. Call "
                    "this after identifying a physical root cause, locating the fault "
                    "via sensors, and finding the nearest on-duty engineer from the "
                    "duty roster."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "engineer_name": {
                            "type": "string",
                            "description": "Full name from duty roster",
                        },
                        "engineer_email": {
                            "type": "string",
                            "description": "Email address from duty roster",
                        },
                        "engineer_phone": {
                            "type": "string",
                            "description": "Phone number from duty roster",
                        },
                        "incident_summary": {
                            "type": "string",
                            "description": "Brief incident summary",
                        },
                        "destination_description": {
                            "type": "string",
                            "description": "Human-readable location description",
                        },
                        "destination_latitude": {
                            "type": "number",
                            "description": "GPS latitude (WGS84)",
                        },
                        "destination_longitude": {
                            "type": "number",
                            "description": "GPS longitude (WGS84)",
                        },
                        "physical_signs_to_inspect": {
                            "type": "string",
                            "description": "Inspection checklist for what to look for on arrival",
                        },
                        "sensor_ids": {
                            "type": "string",
                            "description": "Comma-separated triggering sensor IDs",
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["CRITICAL", "HIGH", "STANDARD"],
                            "description": "Urgency level",
                        },
                    },
                    "required": [
                        "engineer_name", "engineer_email", "engineer_phone",
                        "incident_summary", "destination_description",
                        "destination_latitude", "destination_longitude",
                        "physical_signs_to_inspect", "sensor_ids",
                    ],
                },
            )
        )

        all_tools = connected_tools + [dispatch_tool_def]

        orch = agents_client.create_agent(
            model=model,
            name="Orchestrator",
            instructions=prompts.get("orchestrator", "You are an orchestrator agent."),
            tools=all_tools,
        )
        emit("orchestrator", f"Created: {orch.id}")

        result = {
            "orchestrator": {
                "id": orch.id,
                "name": orch.name,
                "model": model,
                "is_orchestrator": True,
                "tools": [],
                "connected_agents": [sa["name"] for sa in sub_agents],
            },
            "sub_agents": {
                sa["name"]: {
                    "id": sa["id"],
                    "name": sa["name"],
                    "model": model,
                    "is_orchestrator": False,
                    "tools": [],
                    "connected_agents": [],
                }
                for sa in sub_agents
            },
        }

        return result


