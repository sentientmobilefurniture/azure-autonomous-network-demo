"""
Shared configuration for all provisioning/management scripts.

Centralises Fabric API constants and common env-loading so they aren't
repeated in every script. Import like:

    from _config import FABRIC_API, FABRIC_SCOPE, get_fabric_headers, PROJECT_ROOT
"""

import os
from pathlib import Path

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = str(PROJECT_ROOT / "azure_config.env")
DATA_DIR = PROJECT_ROOT / "data"

# Load env once on import
load_dotenv(ENV_FILE)

# ---------------------------------------------------------------------------
# Fabric API constants (defined once, used by all scripts)
# ---------------------------------------------------------------------------
FABRIC_API: str = os.getenv(
    "FABRIC_API_URL", "https://api.fabric.microsoft.com/v1"
)
FABRIC_SCOPE: str = os.getenv(
    "FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default"
)

# ---------------------------------------------------------------------------
# Common resource names (read from env with sensible defaults)
# ---------------------------------------------------------------------------
WORKSPACE_ID: str = os.getenv("FABRIC_WORKSPACE_ID", "")
WORKSPACE_NAME: str = os.getenv("FABRIC_WORKSPACE_NAME", "telco-autonomous-network")
CAPACITY_ID: str = os.getenv("FABRIC_CAPACITY_ID", "")
LAKEHOUSE_NAME: str = os.getenv("FABRIC_LAKEHOUSE_NAME", "NetworkTopologyLH")
EVENTHOUSE_NAME: str = os.getenv("FABRIC_EVENTHOUSE_NAME", "NetworkTelemetryEH")
KQL_DB_NAME: str = os.getenv("FABRIC_KQL_DB_NAME", "")
ONTOLOGY_NAME: str = os.getenv("FABRIC_ONTOLOGY_NAME", "NetworkTopologyOntology")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_fabric_headers() -> dict[str, str]:
    """Return authorisation headers for Fabric REST API calls."""
    credential = DefaultAzureCredential()
    token = credential.get_token(FABRIC_SCOPE).token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
