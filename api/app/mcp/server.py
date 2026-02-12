"""
MCP Server — Stub tools for NOC operations.

Exposes tools via FastMCP for consumption by Foundry agents or Copilot clients.
Currently hello-world stubs. Real implementations will query Cosmos DB, AI Search, etc.

Usage (standalone test):
  cd api && uv run mcp dev app/mcp/server.py
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("network_noc_mcp")


@mcp.tool(name="query_telemetry")
async def query_telemetry(sql_query: str) -> str:
    """Run a SQL query against the Cosmos DB telemetry database. Returns query results as text."""
    return f"[STUB] Would execute SQL: {sql_query}"


@mcp.tool(name="search_tickets")
async def search_tickets(query: str, top: int = 5) -> str:
    """Search historical incident tickets using hybrid search. Returns matching tickets."""
    return f"[STUB] Would search tickets for: {query} (top {top})"


@mcp.tool(name="create_incident")
async def create_incident(title: str, severity: str, description: str) -> str:
    """Create a new incident ticket. Returns the created ticket ID."""
    return f"[STUB] Would create incident: {title} (severity: {severity})"
