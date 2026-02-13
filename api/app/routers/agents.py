"""
Agents router — GET /api/agents

Returns the list of provisioned Foundry agents.
Reads from agent_ids.json when available, otherwise returns stub data.
"""

from fastapi import APIRouter

from app.orchestrator import load_agents_from_file

router = APIRouter(prefix="/api", tags=["agents"])

_STUB_AGENTS = [
    {"name": "Orchestrator", "id": "stub-orchestrator", "status": "stub"},
    {"name": "GraphExplorerAgent", "id": "stub-graph", "status": "stub"},
    {"name": "TelemetryAgent", "id": "stub-telemetry", "status": "stub"},
    {"name": "RunbookKBAgent", "id": "stub-runbook", "status": "stub"},
    {"name": "HistoricalTicketAgent", "id": "stub-ticket", "status": "stub"},
]


@router.get("/agents")
async def list_agents():
    """List provisioned agents from agent_ids.json or stub data."""
    agents = load_agents_from_file()
    if agents:
        return {"agents": agents, "source": "agent_ids.json"}
    return {"agents": _STUB_AGENTS, "source": "stub"}
