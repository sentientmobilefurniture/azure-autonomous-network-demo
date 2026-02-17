"""
Unified agent_ids.json reader with file-mtime caching.

All modules that need agent IDs, names, or agent lists should import
from here instead of independently reading and parsing the file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.paths import AGENT_IDS_FILE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mtime-based cache
# ---------------------------------------------------------------------------

_cache: dict | None = None
_cache_mtime: float = 0.0


def _read_agent_ids() -> dict:
    """Read and parse agent_ids.json with file-mtime caching."""
    global _cache, _cache_mtime
    if not AGENT_IDS_FILE.exists():
        return {}
    mtime = AGENT_IDS_FILE.stat().st_mtime
    if _cache is not None and mtime == _cache_mtime:
        return _cache
    try:
        _cache = json.loads(AGENT_IDS_FILE.read_text())
        _cache_mtime = mtime
        return _cache
    except Exception as e:
        logger.warning("Failed to read %s: %s", AGENT_IDS_FILE, e)
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_agent_ids() -> dict:
    """Return the full parsed agent_ids.json dict (cached by mtime)."""
    return _read_agent_ids()


def get_agent_names() -> dict[str, str]:
    """Return {agent_id: agent_name} mapping from agent_ids.json.

    Handles both flat and nested (sub_agents) structures.
    """
    data = _read_agent_ids()
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
    """Build a single agent stub from an agent_ids.json entry."""
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
    data = _read_agent_ids()
    if not data:
        return []
    agents = []
    for key, val in data.items():
        if isinstance(val, dict) and "id" in val:
            # Top-level agent (e.g. "orchestrator")
            agents.append(_make_agent_stub(key, val))
        elif isinstance(val, dict):
            # Nested container (e.g. "sub_agents")
            for sub_key, sub_val in val.items():
                if isinstance(sub_val, dict) and "id" in sub_val:
                    agents.append(_make_agent_stub(sub_key, sub_val))
    return agents
