"""
Cosmos DB configuration — all Cosmos-specific env vars.

Extracted from config.py so the main config module stays
backend-agnostic.  Other files that need Cosmos connection
details import from here instead of config.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Cosmos DB NoSQL settings
# ---------------------------------------------------------------------------

COSMOS_NOSQL_ENDPOINT = os.getenv("COSMOS_NOSQL_ENDPOINT", "")
COSMOS_NOSQL_DATABASE = os.getenv("COSMOS_NOSQL_DATABASE", "telemetry")

# ---------------------------------------------------------------------------
# Cosmos DB Gremlin settings
# ---------------------------------------------------------------------------

COSMOS_GREMLIN_ENDPOINT = os.getenv("COSMOS_GREMLIN_ENDPOINT", "")
COSMOS_GREMLIN_PRIMARY_KEY = os.getenv("COSMOS_GREMLIN_PRIMARY_KEY", "")
COSMOS_GREMLIN_DATABASE = os.getenv("COSMOS_GREMLIN_DATABASE", "networkgraph")
COSMOS_GREMLIN_GRAPH = os.getenv("COSMOS_GREMLIN_GRAPH", "topology")

# ---------------------------------------------------------------------------
# Required-var tuples (used by lifespan health checks)
# ---------------------------------------------------------------------------

TELEMETRY_REQUIRED_VARS: tuple[str, ...] = (
    "COSMOS_NOSQL_ENDPOINT", "COSMOS_NOSQL_DATABASE",
)

COSMOS_REQUIRED_VARS: tuple[str, ...] = (
    "COSMOS_GREMLIN_ENDPOINT", "COSMOS_GREMLIN_PRIMARY_KEY",
)
