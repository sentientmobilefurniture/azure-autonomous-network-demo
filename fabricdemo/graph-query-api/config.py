"""
Configuration — environment variable loading and shared resources.

Centralises all env var reads so other modules import from here
instead of calling os.getenv() directly.

Provides ScenarioContext — a per-request dataclass resolved from the
X-Graph request header, enabling multi-graph routing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from fastapi import Header
from azure.identity import DefaultAzureCredential




# ---------------------------------------------------------------------------
# Graph backend selector
# ---------------------------------------------------------------------------

GRAPH_BACKEND: str = os.getenv("GRAPH_BACKEND", "fabric-gql").lower()


# ---------------------------------------------------------------------------
# AI Search settings (used by /query/indexes)
# ---------------------------------------------------------------------------

AI_SEARCH_NAME = os.getenv("AI_SEARCH_NAME", "")

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
# Per-request scenario context (resolved from X-Graph header)
# ---------------------------------------------------------------------------

@dataclass
class ScenarioContext:
    """Per-request routing context derived from the X-Graph header.

    Determines which graph and prompts database each request targets.
    If no header is provided, falls back to the DEFAULT_SCENARIO env var.

    Graph queries route to Fabric GQL. Telemetry queries route to Fabric KQL.
    Prompts use a shared Cosmos NoSQL database (pre-created by Bicep).
    """
    graph_name: str                  # e.g. "cloud-outage-topology"
    prompts_database: str            # "prompts" (shared DB, pre-created by Bicep)
    prompts_container: str           # "cloud-outage" (per-scenario container name)
    backend_type: str
    # Per-scenario Fabric routing (populated from config store's fabric_resources)
    fabric_workspace_id: str = ""
    fabric_graph_model_id: str = ""
    fabric_eventhouse_id: str = ""


# ---------------------------------------------------------------------------
# Connector → backend key mapping
# ---------------------------------------------------------------------------

CONNECTOR_TO_BACKEND: dict[str, str] = {
    "fabric-gql": "fabric-gql",
    "mock": "mock",
}


async def get_scenario_context(
    x_graph: str | None = Header(default=None, alias="X-Graph"),
) -> ScenarioContext:
    """FastAPI dependency — resolve scenario context from X-Graph header.

    If the header is absent, falls back to DEFAULT_SCENARIO env var.

    The scenario prefix is derived from the graph name:
      "cloud-outage-topology" → "cloud-outage"
    If no hyphen exists, the full graph_name is used as the prefix.

    Backend type resolution:
      1. Try to read the scenario's config from the config store
         (requires V10 DocumentStore infrastructure)
      2. Falls back to the GRAPH_BACKEND env var default
    """
    graph_name = x_graph or os.getenv("DEFAULT_SCENARIO", "telco-noc")

    # Derive scenario prefix: "cloud-outage-topology" → "cloud-outage"
    prefix = graph_name.rsplit("-", 1)[0] if "-" in graph_name else graph_name

    # Per-scenario backend resolution: check config store for connector type
    backend_type = GRAPH_BACKEND  # default
    # Fabric per-scenario resource IDs (populated by provisioning pipeline)
    fabric_workspace_id = ""
    fabric_graph_model_id = ""
    fabric_eventhouse_id = ""

    try:
        from config_store import fetch_scenario_config
        config = await fetch_scenario_config(prefix)
        connector = (
            config.get("data_sources", {})
                  .get("graph", {})
                  .get("connector", "")
        )
        if connector:
            backend_type = CONNECTOR_TO_BACKEND.get(connector, connector)

        # Extract per-scenario Fabric resource IDs
        fabric_resources = config.get("fabric_resources", {})
        if fabric_resources:
            from adapters.fabric_config import FABRIC_WORKSPACE_ID as _FW, FABRIC_GRAPH_MODEL_ID as _FG
            fabric_workspace_id = fabric_resources.get("workspace_id", _FW)
            fabric_graph_model_id = fabric_resources.get("graph_model_id", _FG)
            fabric_eventhouse_id = fabric_resources.get("eventhouse_id", "")
    except Exception:
        logger.warning(
            "Config store lookup failed for prefix=%s, backend_type=%s — using env defaults",
            prefix, backend_type,
            exc_info=True,
        )

    return ScenarioContext(
        graph_name=graph_name,
        prompts_database="prompts",                # shared DB
        prompts_container=prefix,                  # scenario container name
        backend_type=backend_type,
        fabric_workspace_id=fabric_workspace_id,
        fabric_graph_model_id=fabric_graph_model_id,
        fabric_eventhouse_id=fabric_eventhouse_id,
    )

# ---------------------------------------------------------------------------
# Required env vars per backend (used by lifespan health check)
# ---------------------------------------------------------------------------

BACKEND_REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "fabric-gql": ("FABRIC_WORKSPACE_ID", "FABRIC_GRAPH_MODEL_ID"),
    "mock": (),
}
