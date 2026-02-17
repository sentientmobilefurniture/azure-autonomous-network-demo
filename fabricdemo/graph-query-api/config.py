"""
Configuration — environment variable loading and shared resources.

Centralises all env var reads so other modules import from here
instead of calling os.getenv() directly.

Provides ScenarioContext — a fixed hardcoded context for the telco-noc
demo. No dynamic routing, no X-Graph header parsing, no config store.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from azure.identity import DefaultAzureCredential


# ---------------------------------------------------------------------------
# Graph backend selector
# ---------------------------------------------------------------------------

GRAPH_BACKEND: str = os.getenv("GRAPH_BACKEND", "fabric-gql").lower()


# ---------------------------------------------------------------------------
# AI Search settings (used by /query/health)
# ---------------------------------------------------------------------------

AI_SEARCH_NAME = os.getenv("AI_SEARCH_NAME", "")

# ---------------------------------------------------------------------------
# Fabric resource IDs (set by provisioning scripts → azure_config.env)
# ---------------------------------------------------------------------------

FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
FABRIC_GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")
EVENTHOUSE_QUERY_URI = os.getenv("EVENTHOUSE_QUERY_URI", "")
FABRIC_KQL_DB_NAME = os.getenv("FABRIC_KQL_DB_NAME", "")

# ---------------------------------------------------------------------------
# Hardcoded scenario defaults
# ---------------------------------------------------------------------------

DEFAULT_GRAPH = "telco-noc-topology"

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
# Scenario context — hardcoded for telco-noc
# ---------------------------------------------------------------------------

@dataclass
class ScenarioContext:
    """Fixed routing context for the telco-noc demo.

    No dynamic resolution — returns the same hardcoded context for every
    request. Graph queries route to Fabric GQL via env var resource IDs.
    """
    graph_name: str = DEFAULT_GRAPH
    backend_type: str = GRAPH_BACKEND
    fabric_workspace_id: str = FABRIC_WORKSPACE_ID
    fabric_graph_model_id: str = FABRIC_GRAPH_MODEL_ID


def get_scenario_context() -> ScenarioContext:
    """Return a fixed ScenarioContext. No X-Graph header, no config store."""
    return ScenarioContext()


# ---------------------------------------------------------------------------
# Hardcoded data source definitions (used by router_health.py)
# ---------------------------------------------------------------------------

DATA_SOURCES = {
    "graph": {"connector": "fabric-gql", "resource_name": DEFAULT_GRAPH},
    "telemetry": {"connector": "fabric-kql", "resource_name": "NetworkTelemetryEH"},
    "search_indexes": {
        "runbooks": {"index_name": "runbooks-index"},
        "tickets": {"index_name": "tickets-index"},
    },
}

# ---------------------------------------------------------------------------
# Required env vars per backend (used by lifespan health check)
# ---------------------------------------------------------------------------

BACKEND_REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "fabric-gql": ("FABRIC_WORKSPACE_ID", "FABRIC_GRAPH_MODEL_ID"),
    "mock": (),
}
