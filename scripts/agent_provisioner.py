"""
AgentProvisioner — importable agent creation logic.

Extracted from provision_agents.py for use by both:
  - CLI (provision_agents.py --force)
  - API (POST /api/config/apply)

Prompts are passed as strings (not read from disk), enabling Cosmos-backed
prompt management and runtime reconfiguration.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable

import yaml
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    AzureAISearchTool,
    AzureAISearchQueryType,
    ConnectedAgentTool,
    OpenApiTool,
    OpenApiAnonymousAuthDetails,
)

logger = logging.getLogger("agent-provisioner")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_DIR = PROJECT_ROOT / "graph-query-api" / "openapi"
AGENT_IDS_FILE = PROJECT_ROOT / "scripts" / "agent_ids.json"

AI_SEARCH_CONNECTION_NAME = "aisearch-connection"

OPENAPI_SPEC_MAP = {
    "cosmosdb": OPENAPI_DIR / "cosmosdb.yaml",
    "mock": OPENAPI_DIR / "mock.yaml",
}

OPENAPI_TEMPLATE_DIR = OPENAPI_DIR / "templates"

# Connector-specific variable expansions for OpenAPI template placeholders.
# Used by _load_openapi_spec() when rendering templates.
CONNECTOR_OPENAPI_VARS: dict[str, dict[str, str]] = {
    "cosmosdb": {
        "query_language_description": (
            "Submits a Gremlin traversal query to Azure Cosmos DB for Apache Gremlin. "
            "Send Gremlin queries as plain text strings (no bytecode, no lambdas). "
            "Cosmos DB only supports string-based Gremlin."
        ),
        "telemetry_query_language_description": (
            "Submits a Cosmos SQL query to a telemetry container in Azure Cosmos DB NoSQL. "
            "Use standard SQL syntax: SELECT, FROM c, WHERE, ORDER BY, TOP, GROUP BY. "
            "Always use FROM c as the alias."
        ),
    },
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
            "Submits a KQL query against telemetry data stored in "
            "Microsoft Fabric Eventhouse."
        ),
    },
}

GRAPH_TOOL_DESCRIPTIONS = {
    "cosmosdb": "Execute a Gremlin query against Azure Cosmos DB to explore topology and relationships.",
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
    graph_backend: str = "cosmosdb",
    keep_path: str | None = None,
    graph_name: str = "topology",
    *,
    spec_template: str | None = None,
) -> dict:
    """Load and expand an OpenAPI spec with connector-specific descriptions.

    If spec_template is provided (e.g. "graph", "telemetry"), loads from
    openapi/templates/{spec_template}.yaml and injects connector-specific
    descriptions. Otherwise falls back to the per-backend spec files
    (openapi/cosmosdb.yaml, openapi/mock.yaml) for backward compatibility.
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
            spec_file = OPENAPI_SPEC_MAP.get(graph_backend, OPENAPI_DIR / "cosmosdb.yaml")
            raw = spec_file.read_text(encoding="utf-8")
    else:
        spec_file = OPENAPI_SPEC_MAP.get(graph_backend, OPENAPI_DIR / "cosmosdb.yaml")
        raw = spec_file.read_text(encoding="utf-8")

    raw = raw.replace("{base_url}", graph_query_api_uri.rstrip("/"))
    raw = raw.replace("{graph_name}", graph_name)
    spec = yaml.safe_load(raw)
    if keep_path and "paths" in spec:
        # Prefix match: "/query/graph" matches "/query/graph/telco-noc-topology"
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
        for agent in agents_client.list_agents():
            if agent.name in AGENT_NAMES:
                logger.info("Deleting %s (%s)", agent.name, agent.id)
                agents_client.delete_agent(agent.id)
                deleted += 1
        return deleted

    def provision_all(
        self,
        model: str,
        prompts: dict[str, str],
        graph_query_api_uri: str,
        graph_backend: str,
        graph_name: str,
        runbooks_index: str,
        tickets_index: str,
        search_connection_id: str,
        force: bool = True,
        on_progress: callable | None = None,
    ) -> dict:
        """Provision all 5 agents and return agent_ids structure.

        Args:
            model: Model deployment name (e.g. "gpt-4.1")
            prompts: {agent_name: prompt_content} for all 5 agents
              Keys: "orchestrator", "graph_explorer", "telemetry", "runbook", "ticket"
            graph_query_api_uri: Base URL for OpenAPI tools
            graph_backend: "cosmosdb" or "mock"
            graph_name: Graph name for X-Graph header (e.g. "telco-noc-topology")
            runbooks_index: AI Search index name for RunbookKB
            tickets_index: AI Search index name for HistoricalTicket
            search_connection_id: Foundry connection ID for AI Search
            force: Delete existing agents before creating
            on_progress: Optional callback(step: str, detail: str)

        Returns:
            Dict matching agent_ids.json structure
        """
        def emit(step: str, detail: str):
            logger.info("[%s] %s", step, detail)
            if on_progress:
                on_progress(step, detail)

        client = self._get_client()
        agents_client = client.agents

        if force:
            emit("cleanup", "Deleting existing agents...")
            self.cleanup_existing()

        # Create sub-agents
        sub_agents = []

        # 1. GraphExplorer
        emit("graph_explorer", "Creating GraphExplorerAgent...")
        ge_tools = []
        if graph_query_api_uri:
            spec = _load_openapi_spec(graph_query_api_uri, graph_backend, "/query/graph", graph_name=graph_name)
            tool = OpenApiTool(
                name="query_graph",
                spec=spec,
                description=GRAPH_TOOL_DESCRIPTIONS.get(graph_backend, GRAPH_TOOL_DESCRIPTIONS["cosmosdb"]),
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
            spec = _load_openapi_spec(graph_query_api_uri, graph_backend, "/query/telemetry", graph_name=graph_name)
            tool = OpenApiTool(
                name="query_telemetry",
                spec=spec,
                description="Execute a Cosmos SQL query against telemetry data.",
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

        orch = agents_client.create_agent(
            model=model,
            name="Orchestrator",
            instructions=prompts.get("orchestrator", "You are an orchestrator agent."),
            tools=connected_tools,
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

        # Save to file as well (for backwards compat)
        try:
            AGENT_IDS_FILE.write_text(json.dumps(result, indent=2) + "\n")
            emit("save", f"Agent IDs saved to {AGENT_IDS_FILE.name}")
        except Exception as e:
            logger.warning("Failed to save agent_ids.json: %s", e)

        return result

    # ------------------------------------------------------------------
    # Config-driven provisioning (Phase 8)
    # ------------------------------------------------------------------

    def cleanup_by_names(self, names: list[str]) -> int:
        """Delete agents whose name is in *names*. Returns count deleted."""
        client = self._get_client()
        agents_client = client.agents
        deleted = 0
        name_set = set(names)
        for agent in agents_client.list_agents():
            if agent.name in name_set:
                logger.info("Deleting %s (%s)", agent.name, agent.id)
                agents_client.delete_agent(agent.id)
                deleted += 1
        return deleted

    def provision_from_config(
        self,
        config: dict,
        graph_query_api_uri: str,
        search_connection_id: str,
        graph_name: str,
        *,
        prompts: dict[str, str] | None = None,
        force: bool = True,
        on_progress: Callable[[str, str], None] | None = None,
    ) -> dict:
        """Provision N agents from scenario config (config-driven).

        Args:
            config: Parsed scenario.yaml dict (must have 'agents' key).
            graph_query_api_uri: Base URL for OpenAPI tools.
            search_connection_id: Foundry connection ID for AI Search.
            graph_name: Graph name for X-Graph header.
            prompts: Optional pre-loaded prompts keyed by agent role.
                     If not provided, uses instructions_file default text.
            force: Delete existing agents before creating.
            on_progress: Optional callback(step, detail).

        Returns:
            Dict matching agent_ids.json structure.
        """
        def emit(step: str, detail: str):
            logger.info("[%s] %s", step, detail)
            if on_progress:
                on_progress(step, detail)

        client = self._get_client()
        agents_client = client.agents
        agent_defs = config["agents"]
        prompts = prompts or {}

        if force:
            agent_names = [a["name"] for a in agent_defs]
            emit("cleanup", f"Deleting existing agents: {agent_names}")
            self.cleanup_by_names(agent_names)

        created_agents: dict[str, str] = {}  # name → agent_id
        sub_agents: list[dict] = []

        # Phase 1: Create sub-agents (non-orchestrators)
        for agent_def in agent_defs:
            if agent_def.get("is_orchestrator"):
                continue
            name = agent_def["name"]
            role = agent_def.get("role", name)
            emit(role, f"Creating {name}...")

            tools, tool_resources = self._build_tools_from_config(
                agent_def, config, graph_query_api_uri,
                search_connection_id, graph_name,
            )
            prompt = prompts.get(role, agent_def.get(
                "default_instructions", f"You are a {role} agent.",
            ))

            create_kwargs = dict(
                model=agent_def["model"],
                name=name,
                instructions=prompt,
                tools=tools,
            )
            if tool_resources:
                create_kwargs["tool_resources"] = tool_resources

            agent = agents_client.create_agent(**create_kwargs)
            created_agents[name] = agent.id
            description = agent_def.get("display_name", name)
            sub_agents.append({
                "id": agent.id,
                "name": name,
                "description": description,
            })
            emit(role, f"Created: {agent.id}")

        # Phase 2: Create orchestrators with ConnectedAgentTool
        for agent_def in agent_defs:
            if not agent_def.get("is_orchestrator"):
                continue
            name = agent_def["name"]
            role = agent_def.get("role", "orchestrator")
            emit(role, f"Creating {name}...")

            connected_tools = []
            for ref_name in agent_def.get("connected_agents", []):
                if ref_name not in created_agents:
                    emit(role, f"Warning: connected agent '{ref_name}' not found, skipping")
                    continue
                ct = ConnectedAgentTool(
                    id=created_agents[ref_name],
                    name=ref_name,
                    description=f"Delegate to {ref_name}",
                )
                connected_tools.extend(ct.definitions)

            prompt = prompts.get(role, agent_def.get(
                "default_instructions", "You are an orchestrator agent.",
            ))
            agent = agents_client.create_agent(
                model=agent_def["model"],
                name=name,
                instructions=prompt,
                tools=connected_tools,
            )
            created_agents[name] = agent.id
            emit(role, f"Created: {agent.id}")

        # Build result structure
        orchestrator_names = {
            a["name"] for a in agent_defs if a.get("is_orchestrator")
        }
        orch_name = next(iter(orchestrator_names), None)
        agent_def_map = {a["name"]: a for a in agent_defs}
        result = {
            "orchestrator": {
                "id": created_agents.get(orch_name, ""),
                "name": orch_name or "",
                "model": agent_def_map.get(orch_name, {}).get("model", ""),
                "is_orchestrator": True,
                "tools": agent_def_map.get(orch_name, {}).get("tools", []),
                "connected_agents": agent_def_map.get(orch_name, {}).get("connected_agents", []),
            },
            "sub_agents": {
                a["name"]: {
                    "id": created_agents.get(a["name"], ""),
                    "name": a["name"],
                    "model": a.get("model", ""),
                    "is_orchestrator": False,
                    "tools": a.get("tools", []),
                    "connected_agents": a.get("connected_agents", []),
                }
                for a in agent_defs if not a.get("is_orchestrator")
            },
        }

        try:
            AGENT_IDS_FILE.write_text(json.dumps(result, indent=2) + "\n")
            emit("save", f"Agent IDs saved to {AGENT_IDS_FILE.name}")
        except Exception as e:
            logger.warning("Failed to save agent_ids.json: %s", e)

        return result

    def _build_tools_from_config(
        self,
        agent_def: dict,
        config: dict,
        api_uri: str,
        search_conn_id: str,
        graph_name: str,
    ) -> tuple[list, object | None]:
        """Build tool definitions + resources for an agent from config.

        Returns:
            (tool_definitions, tool_resources)
        """
        tool_definitions = []
        tool_resources = None
        graph_backend = config.get("data_sources", {}).get(
            "graph", {},
        ).get("connector", "cosmosdb").split("-")[0]  # "cosmosdb-gremlin" → "cosmosdb"

        for tool_def in agent_def.get("tools", []):
            if tool_def["type"] == "openapi":
                template = tool_def.get("spec_template", "graph")
                keep_path = tool_def.get("keep_path")
                # Default keep_path from template name
                if not keep_path:
                    keep_path = f"/query/{template}"
                spec = _load_openapi_spec(
                    api_uri, graph_backend,
                    keep_path=keep_path, graph_name=graph_name,
                    spec_template=template,
                )
                description = tool_def.get(
                    "description",
                    GRAPH_TOOL_DESCRIPTIONS.get(graph_backend, "Query the API."),
                )
                tool = OpenApiTool(
                    name=f"{template}_query",
                    spec=spec,
                    description=description,
                    auth=OpenApiAnonymousAuthDetails(),
                )
                tool_definitions.extend(tool.definitions)

            elif tool_def["type"] == "azure_ai_search":
                index_key = tool_def["index_key"]
                # Resolve index name from config data_sources
                ds = config.get("data_sources", {})
                search_indexes = ds.get("search_indexes", {})
                index_cfg = search_indexes.get(index_key, {})
                index_name = index_cfg.get("index_name", f"{index_key}-index")

                search_tool = AzureAISearchTool(
                    index_connection_id=search_conn_id,
                    index_name=index_name,
                    query_type=AzureAISearchQueryType.SEMANTIC,
                    top_k=5,
                )
                tool_definitions.extend(search_tool.definitions)
                tool_resources = search_tool.resources

        return tool_definitions, tool_resources
