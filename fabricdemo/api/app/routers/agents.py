"""
Agents router — GET /api/agents

Returns the list of provisioned Foundry agents.
Reads from agent_ids.json when available, otherwise returns an empty list.
Agent names come from the scenario config — no hardcoded stubs.
"""

from fastapi import APIRouter

from app.agent_ids import get_agent_list

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/agents")
async def list_agents():
    """List provisioned agents from agent_ids.json."""
    agents = get_agent_list()
    if agents:
        return {"agents": agents, "source": "agent_ids.json"}
    return {"agents": [], "source": "none"}
