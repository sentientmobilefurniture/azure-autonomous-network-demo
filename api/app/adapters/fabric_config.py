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
