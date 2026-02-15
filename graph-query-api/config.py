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
from enum import Enum

from fastapi import Header
from azure.identity import DefaultAzureCredential


# ---------------------------------------------------------------------------
# Graph backend selector
# ---------------------------------------------------------------------------

class GraphBackendType(str, Enum):
    """Supported graph backends, controlled by GRAPH_BACKEND env var."""
    COSMOSDB = "cosmosdb"
    MOCK = "mock"


GRAPH_BACKEND = GraphBackendType(os.getenv("GRAPH_BACKEND", "cosmosdb").lower())


# ---------------------------------------------------------------------------
# Cosmos DB NoSQL settings (used by /query/telemetry)
# ---------------------------------------------------------------------------

COSMOS_NOSQL_ENDPOINT = os.getenv("COSMOS_NOSQL_ENDPOINT", "")
COSMOS_NOSQL_DATABASE = os.getenv("COSMOS_NOSQL_DATABASE", "telemetry")

# ---------------------------------------------------------------------------
# Cosmos DB Gremlin settings (used by GRAPH_BACKEND=cosmosdb)
# ---------------------------------------------------------------------------

COSMOS_GREMLIN_ENDPOINT = os.getenv("COSMOS_GREMLIN_ENDPOINT", "")
COSMOS_GREMLIN_PRIMARY_KEY = os.getenv("COSMOS_GREMLIN_PRIMARY_KEY", "")
COSMOS_GREMLIN_DATABASE = os.getenv("COSMOS_GREMLIN_DATABASE", "networkgraph")
COSMOS_GREMLIN_GRAPH = os.getenv("COSMOS_GREMLIN_GRAPH", "topology")

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

    Determines which Gremlin graph and which NoSQL telemetry database
    each request targets. If no header is provided, falls back to the
    default graph from env vars.
    """
    graph_name: str              # e.g. "cloud-outage-topology"
    gremlin_database: str        # e.g. "networkgraph" (shared across scenarios)
    telemetry_database: str      # e.g. "cloud-outage-telemetry" (derived)
    backend_type: GraphBackendType


def get_scenario_context(
    x_graph: str | None = Header(default=None, alias="X-Graph"),
) -> ScenarioContext:
    """FastAPI dependency — resolve scenario context from X-Graph header.

    If the header is absent, falls back to COSMOS_GREMLIN_GRAPH env var.

    Telemetry database is derived from the graph name:
      "cloud-outage-topology" → prefix "cloud-outage" → "cloud-outage-telemetry"
    Falls back to COSMOS_NOSQL_DATABASE if no prefix can be derived.
    """
    graph_name = x_graph or COSMOS_GREMLIN_GRAPH

    if "-" in graph_name:
        prefix = graph_name.rsplit("-", 1)[0]
        telemetry_db = f"{prefix}-telemetry"
    else:
        telemetry_db = COSMOS_NOSQL_DATABASE

    return ScenarioContext(
        graph_name=graph_name,
        gremlin_database=COSMOS_GREMLIN_DATABASE,
        telemetry_database=telemetry_db,
        backend_type=GRAPH_BACKEND,
    )

# ---------------------------------------------------------------------------
# Required env vars per backend (used by lifespan health check)
# ---------------------------------------------------------------------------

BACKEND_REQUIRED_VARS: dict[GraphBackendType, tuple[str, ...]] = {
    GraphBackendType.COSMOSDB: (
        "COSMOS_GREMLIN_ENDPOINT",
        "COSMOS_GREMLIN_PRIMARY_KEY",
    ),
    GraphBackendType.MOCK: (),
}

# Telemetry (Cosmos NoSQL) vars — optional; /query/telemetry fails gracefully without them
TELEMETRY_REQUIRED_VARS: tuple[str, ...] = (
    "COSMOS_NOSQL_ENDPOINT", "COSMOS_NOSQL_DATABASE",
)
