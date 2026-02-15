"""
Agents router — GET /api/agents

Returns the list of provisioned Foundry agents.
Reads from agent_ids.json when available, otherwise returns an empty list.
Agent names come from the scenario config — no hardcoded stubs.
"""

import json
from pathlib import Path

from fastapi import APIRouter

from app.orchestrator import load_agents_from_file

router = APIRouter(prefix="/api", tags=["agents"])

_AGENT_IDS_FILE = Path(__file__).resolve().parent.parent.parent / "scripts" / "agent_ids.json"


def _load_dynamic_stubs() -> list[dict]:
    """Build stub agent list from agent_ids.json.

    Returns agents with 'provisioned' status if the file exists,
    or an empty list if no provisioning has occurred yet.
    """
    if not _AGENT_IDS_FILE.exists():
        return []
    try:
        with open(_AGENT_IDS_FILE) as f:
            ids = json.load(f)
        agents = []
        # Orchestrator
        orch = ids.get("orchestrator", {})
        if orch.get("id"):
            agents.append({"name": orch["name"], "id": orch["id"], "status": "provisioned"})
        # Sub-agents
        for name, info in ids.get("sub_agents", {}).items():
            agents.append({"name": name, "id": info["id"], "status": "provisioned"})
        return agents
    except Exception:
        return []


@router.get("/agents")
async def list_agents():
    """List provisioned agents from agent_ids.json or dynamic stubs."""
    agents = load_agents_from_file()
    if agents:
        return {"agents": agents, "source": "agent_ids.json"}
    stubs = _load_dynamic_stubs()
    if stubs:
        return {"agents": stubs, "source": "agent_ids.json"}
    return {"agents": [], "source": "none"}
