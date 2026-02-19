"""
Fabric-specific configuration.

Provides Fabric API constants and workspace name conventions.
Resource IDs (graph model, eventhouse, KQL DB) are discovered at
runtime by fabric_discovery.py — not read from env vars here.

Imported by backends/fabric.py for API URL and scope constants.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Fabric REST API
# ---------------------------------------------------------------------------

FABRIC_API_URL = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")

# ---------------------------------------------------------------------------
# Workspace ID — the only required env var for Fabric
# ---------------------------------------------------------------------------

FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")

# ---------------------------------------------------------------------------
# Provisioning defaults (used by provision scripts, not at runtime)
# ---------------------------------------------------------------------------

FABRIC_WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "telco-autonomous-network")
FABRIC_LAKEHOUSE_NAME = os.getenv("FABRIC_LAKEHOUSE_NAME", "NetworkTopologyLH")
FABRIC_EVENTHOUSE_NAME = os.getenv("FABRIC_EVENTHOUSE_NAME", "NetworkTelemetryEH")
FABRIC_ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "NetworkTopologyOntology")
FABRIC_CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID", "")
