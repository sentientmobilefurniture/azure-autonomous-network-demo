"""
MCP Server — Custom tools for the Autonomous Network NOC Agent.

Hosted on Azure Functions using the MCP extension trigger bindings.
The Foundry Agent Service connects to this server via the MCP protocol
endpoint: https://<funcapp>.azurewebsites.net/runtime/webhooks/mcp

Tools exposed:
  1. query_eventhouse  — Run KQL queries against Fabric Eventhouse
  2. search_tickets    — Search historical incident tickets via AI Search
  3. create_incident   — Create & log a new incident ticket

These tools replace the local FunctionTool definitions in create_agents.py,
allowing the Supervisor agent to call them SERVER-SIDE via MCP rather than
requiring client-side auto_function_calls execution.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# ── Tool property helpers ───────────────────────────────────────────

class ToolProperty:
    """Describes a single input parameter for an MCP tool."""
    def __init__(self, name: str, prop_type: str, description: str):
        self.propertyName = name
        self.propertyType = prop_type
        self.description = description

    def to_dict(self):
        return {
            "propertyName": self.propertyName,
            "propertyType": self.propertyType,
            "description": self.description,
        }


def props_json(properties: list[ToolProperty]) -> str:
    return json.dumps([p.to_dict() for p in properties])


# ── Tool 1: query_eventhouse ────────────────────────────────────────

query_eventhouse_props = props_json([
    ToolProperty("kql_query", "string", "The KQL query string to execute against the Eventhouse."),
    ToolProperty("database", "string", "The KQL database name. Default: NetworkDB."),
])


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="query_eventhouse",
    description=(
        "Execute a KQL query against the Fabric Eventhouse. "
        "Database 'NetworkDB' contains tables: AlertStream (AlertId, Timestamp, "
        "SourceNodeId, SourceNodeType, AlertType, Severity, Description, "
        "OpticalPowerDbm, BitErrorRate, CPUUtilPct, PacketLossPct) and "
        "LinkTelemetry (LinkId, Timestamp, UtilizationPct, OpticalPowerDbm, "
        "BitErrorRate, LatencyMs). Returns JSON array of result rows (max 50)."
    ),
    toolProperties=query_eventhouse_props,
)
def query_eventhouse(context) -> str:
    """Execute a KQL query against the Fabric Eventhouse and return JSON results."""
    from azure.identity import DefaultAzureCredential
    from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

    content = json.loads(context)
    kql_query = content["arguments"]["kql_query"]
    database = content["arguments"].get("database", os.environ.get("FABRIC_KQL_DB_DEFAULT", "NetworkDB"))

    query_uri = os.environ["EVENTHOUSE_QUERY_URI"]
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
        query_uri, DefaultAzureCredential()
    )
    client = KustoClient(kcsb)
    response = client.execute(database, kql_query)
    rows = [
        dict(zip([c.column_name for c in response.primary_results[0].columns], row))
        for row in response.primary_results[0]
    ]
    result = json.dumps(rows[:50], default=str)
    logging.info(f"query_eventhouse: {len(rows)} rows returned for query: {kql_query[:80]}")
    return result


# ── Tool 2: search_tickets ─────────────────────────────────────────

search_tickets_props = props_json([
    ToolProperty("query_text", "string", "Natural language description of the incident to search for."),
    ToolProperty("max_results", "string", "Maximum number of results to return (default: 5)."),
])


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="search_tickets",
    description=(
        "Search historical incident tickets in AI Search for similar past incidents. "
        "Returns matching ticket summaries with resolution details. "
        "Use to check for precedent and past remediation steps."
    ),
    toolProperties=search_tickets_props,
)
def search_tickets(context) -> str:
    """Search AI Search tickets-index for historical incident matches."""
    from azure.identity import DefaultAzureCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.models import VectorizableTextQuery

    content = json.loads(context)
    query_text = content["arguments"]["query_text"]
    max_results = int(content["arguments"].get("max_results", "5"))

    search_endpoint = f"https://{os.environ['AI_SEARCH_NAME']}.search.windows.net"
    credential = DefaultAzureCredential()

    search_client = SearchClient(
        endpoint=search_endpoint,
        index_name=os.environ.get("TICKETS_INDEX_NAME", "tickets-index"),
        credential=credential,
    )
    results = search_client.search(
        search_text=query_text,
        vector_queries=[
            VectorizableTextQuery(
                text=query_text,
                k_nearest_neighbors=max_results,
                fields="vector",
            )
        ],
        top=max_results,
        select=["chunk", "title"],
    )
    items = [{"title": r["title"], "content": r["chunk"]} for r in results]
    logging.info(f"search_tickets: {len(items)} results for: {query_text[:80]}")
    return json.dumps(items, default=str)


# ── Tool 3: create_incident ────────────────────────────────────────

create_incident_props = props_json([
    ToolProperty("title", "string", "Short incident title."),
    ToolProperty("severity", "string", "Severity level: P1, P2, P3, or P4."),
    ToolProperty("root_cause", "string", "Identified root cause description."),
    ToolProperty("affected_services", "string", "Comma-separated list of affected service names."),
    ToolProperty("sla_breach_risk", "string", "SLA breach assessment (e.g. 'HIGH - 99.99% SLA at risk')."),
    ToolProperty("recommended_action", "string", "Recommended remediation action."),
    ToolProperty("timeline", "string", "Incident timeline summary."),
])


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="create_incident",
    description=(
        "Create a new incident ticket in the ticketing system. "
        "Returns the ticket ID and full ticket details as JSON. "
        "In production this would integrate with ServiceNow or similar."
    ),
    toolProperties=create_incident_props,
)
def create_incident(context) -> str:
    """Create a new incident ticket and return it as JSON."""
    content = json.loads(context)
    args = content["arguments"]

    ticket_id = f"INC-{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    ticket = {
        "ticket_id": ticket_id,
        "title": args["title"],
        "severity": args["severity"],
        "status": "Open",
        "root_cause": args["root_cause"],
        "affected_services": args["affected_services"],
        "sla_breach_risk": args["sla_breach_risk"],
        "recommended_action": args["recommended_action"],
        "timeline": args["timeline"],
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    logging.info(f"INCIDENT CREATED: {ticket_id} — {args['title']} [{args['severity']}]")
    return json.dumps({"ticket_id": ticket_id, "status": "created", "detail": ticket})
