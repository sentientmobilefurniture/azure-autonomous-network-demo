"""
Agents router — GET /api/agents, POST /api/agents/rediscover

Returns the list of provisioned Foundry agents.
Discovered from AI Foundry at runtime (cached with TTL).
"""

from fastapi import APIRouter

from app.agent_ids import get_agent_list, invalidate_cache, load_agent_ids

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/agents")
async def list_agents():
    """List provisioned agents discovered from AI Foundry."""
    agents = get_agent_list()
    if agents:
        return {"agents": agents, "source": "foundry-discovery"}
    return {"agents": [], "source": "none"}


@router.post("/agents/rediscover")
async def rediscover_agents():
    """Invalidate agent cache and re-discover from AI Foundry."""
    invalidate_cache()
    data = load_agent_ids()  # triggers re-discovery
    agents = get_agent_list()
    return {
        "ok": bool(data),
        "agents": agents,
        "count": len(agents),
        "source": "foundry-discovery" if agents else "none",
    }
