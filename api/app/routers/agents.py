"""
Agents router — GET /api/agents

Returns the list of provisioned Foundry agents.
Currently a hello-world stub.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/agents")
async def list_agents():
    """List provisioned agents. Stub returns hardcoded names."""
    return {
        "agents": [
            {"name": "Orchestrator", "id": "stub-orchestrator", "status": "active"},
            {"name": "GraphExplorerAgent", "id": "stub-graph", "status": "active"},
            {"name": "TelemetryAgent", "id": "stub-telemetry", "status": "active"},
            {"name": "RunbookKBAgent", "id": "stub-runbook", "status": "active"},
            {"name": "HistoricalTicketAgent", "id": "stub-ticket", "status": "active"},
        ]
    }
