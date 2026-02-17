"""
Agents router — GET /api/agents

Returns the list of provisioned Foundry agents.
Discovered from AI Foundry at runtime (cached with TTL).
"""

from fastapi import APIRouter

from app.agent_ids import get_agent_list

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/agents")
async def list_agents():
    """List provisioned agents discovered from AI Foundry."""
    agents = get_agent_list()
    if agents:
        return {"agents": agents, "source": "foundry-discovery"}
    return {"agents": [], "source": "none"}
