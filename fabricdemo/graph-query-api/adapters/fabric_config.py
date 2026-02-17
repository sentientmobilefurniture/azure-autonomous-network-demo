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

FABRIC_WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "AutonomousNetworkDemo")
FABRIC_LAKEHOUSE_NAME = os.getenv("FABRIC_LAKEHOUSE_NAME", "NetworkTopologyLH")
FABRIC_EVENTHOUSE_NAME = os.getenv("FABRIC_EVENTHOUSE_NAME", "NetworkTelemetryEH")
FABRIC_ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "NetworkTopologyOntology")
FABRIC_CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID", "")

# ---------------------------------------------------------------------------
# Readiness checks — use fabric_discovery for runtime checks
# ---------------------------------------------------------------------------

# Stage 1: workspace reachable — enough for discovery endpoints
FABRIC_WORKSPACE_CONNECTED = bool(os.getenv("FABRIC_WORKSPACE_ID"))


def is_fabric_configured() -> bool:
    """Check if Fabric is configured (workspace set, graph model discoverable)."""
    from fabric_discovery import is_fabric_ready
    return is_fabric_ready()


# Backward compat alias
FABRIC_CONFIGURED = FABRIC_WORKSPACE_CONNECTED  # lazy check; full check via is_fabric_configured()
FABRIC_QUERY_READY = FABRIC_WORKSPACE_CONNECTED


# ---------------------------------------------------------------------------
# Per-scenario Fabric asset name derivation
# ---------------------------------------------------------------------------

def fabric_asset_names(scenario_name: str) -> dict:
    """Derive per-scenario Fabric asset names.

    Falls back to global env var defaults when no scenario_name is provided.
    """
    if not scenario_name:
        return {
            "lakehouse_name": FABRIC_LAKEHOUSE_NAME,
            "eventhouse_name": FABRIC_EVENTHOUSE_NAME,
            "ontology_name": FABRIC_ONTOLOGY_NAME,
        }
    return {
        "lakehouse_name": f"{scenario_name}-lakehouse",
        "eventhouse_name": f"{scenario_name}-eventhouse",
        "ontology_name": f"{scenario_name}-ontology",
    }
