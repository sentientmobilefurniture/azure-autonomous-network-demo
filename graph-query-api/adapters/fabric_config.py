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
# Provisioning defaults (re-added for Phase B provision pipeline)
# ---------------------------------------------------------------------------

FABRIC_WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "AutonomousNetworkDemo")
FABRIC_LAKEHOUSE_NAME = os.getenv("FABRIC_LAKEHOUSE_NAME", "NetworkTopologyLH")
FABRIC_EVENTHOUSE_NAME = os.getenv("FABRIC_EVENTHOUSE_NAME", "NetworkTelemetryEH")
FABRIC_ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "NetworkTopologyOntology")
FABRIC_CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID", "")

# ---------------------------------------------------------------------------
# Readiness checks (two-stage lifecycle)
# ---------------------------------------------------------------------------

# Stage 1: workspace reachable — enough for discovery endpoints
FABRIC_WORKSPACE_CONNECTED = bool(os.getenv("FABRIC_WORKSPACE_ID"))

# Stage 2: graph queries ready — workspace + graph model both set
FABRIC_QUERY_READY = bool(
    os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_GRAPH_MODEL_ID")
)

# Backward compat alias — existing code that imports FABRIC_CONFIGURED is unaffected
FABRIC_CONFIGURED = FABRIC_QUERY_READY
