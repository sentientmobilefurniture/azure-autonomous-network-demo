"""
Configuration — environment variable loading and shared resources.

Centralises all env var reads so other modules import from here
instead of calling os.getenv() directly.

Provides ScenarioContext — a per-request dataclass resolved from the
X-Graph request header, enabling multi-graph routing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header
from azure.identity import DefaultAzureCredential

# Cosmos-specific env vars live in adapters.cosmos_config.
# Re-export COSMOS_GREMLIN_GRAPH only for get_scenario_context() fallback.
from adapters.cosmos_config import COSMOS_GREMLIN_DATABASE, COSMOS_GREMLIN_GRAPH


# ---------------------------------------------------------------------------
# Graph backend selector
# ---------------------------------------------------------------------------

GRAPH_BACKEND: str = os.getenv("GRAPH_BACKEND", "cosmosdb").lower()


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

    Determines which graph, NoSQL telemetry database, and prompts
    database each request targets. If no header is provided, falls back
    to the default graph from env vars.

    Telemetry and prompts use **shared databases** (pre-created by Bicep).
    Per-scenario data is isolated via container-level prefixing:
      - Telemetry containers: "{prefix}-AlertStream", "{prefix}-PerformanceMetrics"
      - Prompts container: "{prefix}" within the shared "prompts" DB
    """
    graph_name: str                  # e.g. "cloud-outage-topology"
    graph_database: str              # e.g. "networkgraph" (shared across scenarios)
    telemetry_database: str          # "telemetry" (shared DB, pre-created by Bicep)
    telemetry_container_prefix: str  # "cloud-outage" (used to prefix container names)
    prompts_database: str            # "prompts" (shared DB, pre-created by Bicep)
    prompts_container: str           # "cloud-outage" (per-scenario container name)
    backend_type: str


def get_scenario_context(
    x_graph: str | None = Header(default=None, alias="X-Graph"),
) -> ScenarioContext:
    """FastAPI dependency — resolve scenario context from X-Graph header.

    If the header is absent, falls back to COSMOS_GREMLIN_GRAPH env var.

    The scenario prefix is derived from the graph name:
      "cloud-outage-topology" → "cloud-outage"
    If no hyphen exists, the full graph_name is used as the prefix.
    """
    graph_name = x_graph or COSMOS_GREMLIN_GRAPH

    # Derive scenario prefix: "cloud-outage-topology" → "cloud-outage"
    prefix = graph_name.rsplit("-", 1)[0] if "-" in graph_name else graph_name

    return ScenarioContext(
        graph_name=graph_name,
        graph_database=COSMOS_GREMLIN_DATABASE,
        telemetry_database="telemetry",           # shared DB
        telemetry_container_prefix=prefix,         # scenario prefix for container lookup
        prompts_database="prompts",                # shared DB
        prompts_container=prefix,                  # scenario container name
        backend_type=GRAPH_BACKEND,
    )

# ---------------------------------------------------------------------------
# Required env vars per backend (used by lifespan health check)
# ---------------------------------------------------------------------------

BACKEND_REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "cosmosdb": (
        "COSMOS_GREMLIN_ENDPOINT",
        "COSMOS_GREMLIN_PRIMARY_KEY",
    ),
    "mock": (),
}

# Telemetry (Cosmos NoSQL) vars — optional; /query/telemetry fails gracefully without them
TELEMETRY_REQUIRED_VARS: tuple[str, ...] = (
    "COSMOS_NOSQL_ENDPOINT", "COSMOS_NOSQL_DATABASE",
)
