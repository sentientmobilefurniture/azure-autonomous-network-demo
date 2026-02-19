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
# Resource names (must be set in azure_config.env — no defaults)
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    """Return env var value or raise with a clear message."""
    val = os.getenv(name)
    if not val:
        raise EnvironmentError(
            f"{name} is not set. Set it in azure_config.env before running."
        )
    return val

FABRIC_WORKSPACE_NAME = _require_env("FABRIC_WORKSPACE_NAME")
FABRIC_LAKEHOUSE_NAME = _require_env("FABRIC_LAKEHOUSE_NAME")
FABRIC_EVENTHOUSE_NAME = _require_env("FABRIC_EVENTHOUSE_NAME")
FABRIC_ONTOLOGY_NAME = _require_env("FABRIC_ONTOLOGY_NAME")
FABRIC_CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID", "")
