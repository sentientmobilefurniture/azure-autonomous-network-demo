"""
Runtime agent discovery via AI Foundry.

Queries the Foundry project's agent listing API to discover provisioned
agents by their known names, replacing the old agent_ids.json file
dependency.  Results are cached with a configurable TTL.

All modules that need agent IDs, names, or agent lists should import
from here instead of independently querying Foundry.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known agent names — must match what agent_provisioner.py creates
# ---------------------------------------------------------------------------

AGENT_NAMES = {
    "GraphExplorerAgent",
    "TelemetryAgent",
    "RunbookKBAgent",
    "HistoricalTicketAgent",
    "Orchestrator",
}

# ---------------------------------------------------------------------------
# TTL-based cache (thread-safe)
# ---------------------------------------------------------------------------

_cache: dict | None = None
_cache_time: float = 0.0
_cache_lock = threading.Lock()
_refresh_in_progress = False
_CACHE_TTL = float(os.getenv("AGENT_DISCOVERY_TTL", "300"))  # 5 min default

# Cached credential singleton
_credential = None


def _get_credential():
    global _credential
    if _credential is None:
        from azure.identity import DefaultAzureCredential
        _credential = DefaultAzureCredential()
    return _credential


def _get_project_client():
    """Create an AIProjectClient for the current project."""
    from azure.ai.projects import AIProjectClient

    endpoint = os.environ.get("PROJECT_ENDPOINT", "").rstrip("/")
    project_name = os.environ.get("AI_FOUNDRY_PROJECT_NAME", "")
    if not endpoint or not project_name:
        return None
    # Ensure endpoint uses services.ai.azure.com and has /api/projects/ path
    if "/api/projects/" not in endpoint:
        endpoint = endpoint.replace("cognitiveservices.azure.com", "services.ai.azure.com")
        endpoint = f"{endpoint}/api/projects/{project_name}"
    return AIProjectClient(endpoint=endpoint, credential=_get_credential())


def _discover_agents() -> dict:
    """Query AI Foundry and return an agent_ids-compatible dict.

    Returns the same structure that agent_ids.json used to provide::

        {
            "orchestrator": {"id": "...", "name": "Orchestrator", ...},
            "sub_agents": {
                "GraphExplorerAgent": {"id": "...", ...},
                ...
            }
        }

    If duplicates exist, picks the newest by created_at.
    """
    client = _get_project_client()
    if client is None:
        logger.warning(
            "Cannot discover agents: PROJECT_ENDPOINT or "
            "AI_FOUNDRY_PROJECT_NAME not set"
        )
        return {}

    try:
        all_agents = list(client.agents.list_agents(limit=100))
    except Exception as e:
        logger.error("Failed to list agents from Foundry: %s", e)
        return {}

    # Filter to known names; if duplicates, keep the newest
    by_name: dict = {}
    for agent in all_agents:
        if agent.name in AGENT_NAMES:
            if (
                agent.name not in by_name
                or agent.created_at > by_name[agent.name].created_at
            ):
                by_name[agent.name] = agent

    # Build agent_ids-compatible structure
    sub_agents: dict = {}
    for name in (
        "GraphExplorerAgent",
        "TelemetryAgent",
        "RunbookKBAgent",
        "HistoricalTicketAgent",
    ):
        if name in by_name:
            a = by_name[name]
            sub_agents[name] = {
                "id": a.id,
                "name": a.name,
                "model": a.model,
                "is_orchestrator": False,
                "tools": [],
                "connected_agents": [],
            }

    result: dict = {}
    orchestrator = by_name.get("Orchestrator")
    if orchestrator:
        result["orchestrator"] = {
            "id": orchestrator.id,
            "name": orchestrator.name,
            "model": orchestrator.model,
            "is_orchestrator": True,
            "tools": [],
            "connected_agents": list(sub_agents.keys()),
        }
    result["sub_agents"] = sub_agents
    return result


def _get_cached() -> dict:
    """Return cached discovery result, refreshing if TTL expired."""
    global _cache, _cache_time, _refresh_in_progress
    with _cache_lock:
        now = time.time()
        if _cache is not None and (now - _cache_time) < _CACHE_TTL:
            return _cache
        # Prevent thundering herd: if another thread is refreshing, return stale
        if _refresh_in_progress and _cache is not None:
            return _cache
        _refresh_in_progress = True
    # Refresh outside the lock (network call)
    try:
        result = _discover_agents()
        with _cache_lock:
            _cache = result
            _cache_time = time.time()
    finally:
        with _cache_lock:
            _refresh_in_progress = False
    return result


def invalidate_cache() -> None:
    """Force the next call to re-query Foundry."""
    global _cache, _cache_time
    with _cache_lock:
        _cache = None
        _cache_time = 0.0


# ---------------------------------------------------------------------------
# Public API — same signatures as the old file-based implementation
# ---------------------------------------------------------------------------


def load_agent_ids() -> dict:
    """Return the full agent discovery dict (cached with TTL)."""
    return _get_cached()


def get_agent_names() -> dict[str, str]:
    """Return {agent_id: agent_name} mapping.

    Handles both flat and nested (sub_agents) structures.
    """
    data = _get_cached()
    names: dict[str, str] = {}
    for key, val in data.items():
        if isinstance(val, dict) and "id" in val:
            names[val["id"]] = val.get("name", key)
        elif isinstance(val, dict):
            for sub_key, sub_val in val.items():
                if isinstance(sub_val, dict) and "id" in sub_val:
                    names[sub_val["id"]] = sub_val.get("name", sub_key)
    return names


def _make_agent_stub(role: str, entry: dict) -> dict:
    """Build a single agent stub from a discovery entry."""
    agent = {
        "id": entry["id"],
        "name": entry.get("name", role),
        "role": role,
        "model": entry.get("model", ""),
        "status": "provisioned",
    }
    if entry.get("tools"):
        agent["tools"] = entry["tools"]
    if entry.get("is_orchestrator"):
        agent["is_orchestrator"] = True
    if entry.get("connected_agents"):
        agent["connected_agents"] = entry["connected_agents"]
    return agent


def get_agent_list() -> list[dict]:
    """Return list of agent stubs for the /agents endpoint.

    Handles both flat and nested (sub_agents) structures.
    """
    data = _get_cached()
    if not data:
        return []
    agents = []
    for key, val in data.items():
        if isinstance(val, dict) and "id" in val:
            agents.append(_make_agent_stub(key, val))
        elif isinstance(val, dict):
            for sub_key, sub_val in val.items():
                if isinstance(sub_val, dict) and "id" in sub_val:
                    agents.append(_make_agent_stub(sub_key, sub_val))
    return agents
