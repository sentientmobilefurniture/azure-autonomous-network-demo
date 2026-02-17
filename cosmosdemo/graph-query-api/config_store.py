"""
Config Store — persist and retrieve scenario configurations.

Stores the full parsed scenario.yaml (including agents section) in Cosmos
so that POST /api/config/apply can provision agents from config at runtime.

Usage:
    from config_store import fetch_scenario_config, save_scenario_config

    config = await fetch_scenario_config("telco-noc")
    await save_scenario_config("telco-noc", manifest_dict)
"""

from __future__ import annotations

from datetime import datetime, timezone

from stores import get_document_store

# Lazily initialized — avoids import-time Cosmos calls
_config_store = None


def _get_store():
    global _config_store
    if _config_store is None:
        _config_store = get_document_store(
            "scenarios", "configs", "/id", ensure_created=True,
        )
    return _config_store


async def fetch_scenario_config(scenario_name: str) -> dict:
    """Fetch the full scenario configuration from Cosmos.

    Returns the parsed scenario.yaml content stored during upload.
    Raises ValueError if no config exists for the scenario.
    """
    store = _get_store()
    try:
        doc = await store.get(scenario_name, partition_key=scenario_name)
        return doc.get("config", {})
    except Exception:
        raise ValueError(
            f"No scenario config found for '{scenario_name}'. "
            f"Upload the scenario with a scenario.yaml that includes "
            f"an 'agents' section."
        )


async def save_scenario_config(scenario_name: str, config: dict) -> None:
    """Persist the full scenario YAML as a Cosmos document.

    Called during POST /query/scenario/upload after parsing the tarball.
    """
    store = _get_store()
    await store.upsert({
        "id": scenario_name,
        "scenario_name": scenario_name,
        "config": config,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
