"""
Configuration — environment variable loading and shared resources.

Centralises all env var reads so other modules import from here
instead of calling os.getenv() directly.
"""

from __future__ import annotations

import os
from enum import Enum

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
COSMOS_NOSQL_DATABASE = os.getenv("COSMOS_NOSQL_DATABASE", "telemetrydb")

# ---------------------------------------------------------------------------
# Cosmos DB Gremlin settings (used by GRAPH_BACKEND=cosmosdb)
# ---------------------------------------------------------------------------

COSMOS_GREMLIN_ENDPOINT = os.getenv("COSMOS_GREMLIN_ENDPOINT", "")
COSMOS_GREMLIN_PRIMARY_KEY = os.getenv("COSMOS_GREMLIN_PRIMARY_KEY", "")
COSMOS_GREMLIN_DATABASE = os.getenv("COSMOS_GREMLIN_DATABASE", "networkgraph")
COSMOS_GREMLIN_GRAPH = os.getenv("COSMOS_GREMLIN_GRAPH", "topology")

# ---------------------------------------------------------------------------
# Shared credential (used by Cosmos DB AAD auth)
# ---------------------------------------------------------------------------

credential = DefaultAzureCredential()

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
