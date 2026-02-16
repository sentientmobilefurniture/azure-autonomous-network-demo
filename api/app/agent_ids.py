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
    """Return {agent_id: agent_name} mapping from agent_ids.json."""
    data = _read_agent_ids()
    names: dict[str, str] = {}
    for key, val in data.items():
        if isinstance(val, dict) and "id" in val:
            names[val["id"]] = val.get("name", key)
    return names


def get_agent_list() -> list[dict]:
    """Return list of agent stubs for the /agents endpoint."""
    data = _read_agent_ids()
    if not data:
        return []
    agents = []
    for key, val in data.items():
        if isinstance(val, dict) and "id" in val:
            agents.append({
                "id": val["id"],
                "name": val.get("name", key),
                "role": key,
                "model": val.get("model", ""),
                "status": "provisioned",
            })
    return agents
