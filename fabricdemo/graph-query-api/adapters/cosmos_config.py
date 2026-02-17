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


