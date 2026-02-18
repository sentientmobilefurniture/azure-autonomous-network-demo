"""
Configuration — environment variable loading and shared resources.

Centralises all env var reads so other modules import from here
instead of calling os.getenv() directly.

Provides ScenarioContext — a routing context for the active scenario,
derived from scenario.yaml when available, with env var fallbacks.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

from azure.identity import DefaultAzureCredential


# ---------------------------------------------------------------------------
# Graph backend selector
# ---------------------------------------------------------------------------

GRAPH_BACKEND: str = os.getenv("GRAPH_BACKEND", "fabric-gql").lower()

# ---------------------------------------------------------------------------
# Topology source: "static" (default) reads pre-built JSON file,
# "live" queries the graph backend (Fabric GQL / mock).
# ---------------------------------------------------------------------------

TOPOLOGY_SOURCE: str = os.getenv("TOPOLOGY_SOURCE", "static").lower()


# ---------------------------------------------------------------------------
# AI Search settings (used by /query/health)
# ---------------------------------------------------------------------------

AI_SEARCH_NAME = os.getenv("AI_SEARCH_NAME", "")

# ---------------------------------------------------------------------------
# Fabric resource IDs — discovered at runtime via fabric_discovery.py
# Env var overrides are still honoured if set explicitly.
# ---------------------------------------------------------------------------

FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
# FABRIC_GRAPH_MODEL_ID, EVENTHOUSE_QUERY_URI, FABRIC_KQL_DB_NAME are
# resolved lazily via fabric_discovery.get_fabric_config(). Do NOT
# read them from os.getenv() at module level — use the discovery module.

# ---------------------------------------------------------------------------
# Scenario config — loaded from scenario.yaml with env var fallbacks
# ---------------------------------------------------------------------------

SCENARIO_NAME = os.getenv("DEFAULT_SCENARIO", "")

# Try to load scenario.yaml from container path, then local dev path
_SCENARIO_YAML_CANDIDATES = [
    Path("/app/data/scenarios") / SCENARIO_NAME / "scenario.yaml",
    Path(__file__).resolve().parent.parent / "data" / "scenarios" / SCENARIO_NAME / "scenario.yaml",
]

def _load_scenario_config() -> dict:
    if not SCENARIO_NAME:
        logger.warning("DEFAULT_SCENARIO not set — using env var defaults")
        return {}
    for p in _SCENARIO_YAML_CANDIDATES:
        if p.exists():
            with open(p) as f:
                return yaml.safe_load(f)
    logger.warning("scenario.yaml not found — using env var defaults")
    return {}

_SCENARIO = _load_scenario_config()

# Derived from scenario.yaml instead of hardcoded
DEFAULT_GRAPH = (
    _SCENARIO.get("data_sources", {}).get("graph", {}).get("config", {}).get("graph", f"{SCENARIO_NAME}-topology")
    if _SCENARIO else os.getenv("DEFAULT_GRAPH", "")
)

# ---------------------------------------------------------------------------
# Data source definitions (derived from scenario.yaml)
# ---------------------------------------------------------------------------

DATA_SOURCES = {
    "graph": {
        "connector": _SCENARIO.get("data_sources", {}).get("graph", {}).get("connector", "fabric-gql") if _SCENARIO else "fabric-gql",
        "resource_name": DEFAULT_GRAPH,
    },
    "telemetry": {
        "connector": _SCENARIO.get("data_sources", {}).get("telemetry", {}).get("connector", "fabric-kql") if _SCENARIO else "fabric-kql",
        "resource_name": "NetworkTelemetryEH",
    },
    "search_indexes": {
        "runbooks": {
            "index_name": (
                _SCENARIO.get("data_sources", {}).get("search_indexes", {}).get("runbooks", {}).get("index_name", "")
                if _SCENARIO else os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index")
            ) or os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index"),
        },
        "tickets": {
            "index_name": (
                _SCENARIO.get("data_sources", {}).get("search_indexes", {}).get("tickets", {}).get("index_name", "")
                if _SCENARIO else os.getenv("TICKETS_INDEX_NAME", "tickets-index")
            ) or os.getenv("TICKETS_INDEX_NAME", "tickets-index"),
        },
    },
}

# ---------------------------------------------------------------------------
# Shared credential (lazy-initialised to avoid probing at import time)
# ---------------------------------------------------------------------------

_credential = None

def get_credential():
    """Return a cached DefaultAzureCredential (lazy-initialised)."""
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential

# ---------------------------------------------------------------------------
# Scenario context — derived from active scenario
# ---------------------------------------------------------------------------

@dataclass
class ScenarioContext:
    """Routing context for the active scenario.

    No dynamic resolution — returns the same context for every
    request. Graph queries route to Fabric GQL via runtime-discovered IDs.
    """
    graph_name: str = DEFAULT_GRAPH
    backend_type: str = GRAPH_BACKEND
    fabric_workspace_id: str = ""
    fabric_graph_model_id: str = ""


def get_scenario_context() -> ScenarioContext:
    """Return a ScenarioContext with runtime-discovered Fabric IDs."""
    from fabric_discovery import get_fabric_config
    cfg = get_fabric_config()
    return ScenarioContext(
        fabric_workspace_id=cfg.workspace_id,
        fabric_graph_model_id=cfg.graph_model_id,
    )


# ---------------------------------------------------------------------------
# Required env vars per backend (used by lifespan health check)
# ---------------------------------------------------------------------------

BACKEND_REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "fabric-gql": ("FABRIC_WORKSPACE_ID",),  # graph_model_id is discovered at runtime
    "mock": (),
}
