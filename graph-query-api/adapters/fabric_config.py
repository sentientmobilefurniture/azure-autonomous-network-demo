"""
Fabric-specific environment variable reads.

Follows the same adapter pattern as cosmos_config.py.
Imported only by backends/fabric.py — no pollution of shared config.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Fabric REST API
# ---------------------------------------------------------------------------

FABRIC_API_URL = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")

# ---------------------------------------------------------------------------
# Workspace & Graph Model (required for graph queries)
# ---------------------------------------------------------------------------

FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
FABRIC_GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")

# ---------------------------------------------------------------------------
# Readiness check
# ---------------------------------------------------------------------------

FABRIC_CONFIGURED = bool(
    os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_GRAPH_MODEL_ID")
)
