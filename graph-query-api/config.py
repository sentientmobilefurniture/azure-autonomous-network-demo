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
    FABRIC = "fabric"
    COSMOSDB = "cosmosdb"
    MOCK = "mock"


GRAPH_BACKEND = GraphBackendType(os.getenv("GRAPH_BACKEND", "cosmosdb").lower())


# ---------------------------------------------------------------------------
# Fabric API settings (used by GRAPH_BACKEND=fabric and KQL endpoints)
# ---------------------------------------------------------------------------

FABRIC_API = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")
WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")

# ---------------------------------------------------------------------------
# Cosmos DB NoSQL settings (used by /query/telemetry, all backends)
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
# Shared credential (used by Fabric GQL, KQL, and Cosmos DB AAD auth)
# ---------------------------------------------------------------------------

credential = DefaultAzureCredential()

# ---------------------------------------------------------------------------
# Required env vars per backend (used by lifespan health check)
# ---------------------------------------------------------------------------

BACKEND_REQUIRED_VARS: dict[GraphBackendType, tuple[str, ...]] = {
    GraphBackendType.FABRIC: (
        "FABRIC_WORKSPACE_ID", "FABRIC_GRAPH_MODEL_ID",
    ),
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
