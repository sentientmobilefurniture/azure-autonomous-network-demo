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
# Common resource names (must be set in azure_config.env — no defaults)
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    """Return env var value or raise with a clear message."""
    val = os.getenv(name)
    if not val:
        raise EnvironmentError(
            f"{name} is not set. Set it in azure_config.env before running."
        )
    return val

WORKSPACE_ID: str = os.getenv("FABRIC_WORKSPACE_ID", "")
WORKSPACE_NAME: str = _require_env("FABRIC_WORKSPACE_NAME")
CAPACITY_ID: str = os.getenv("FABRIC_CAPACITY_ID", "")
LAKEHOUSE_NAME: str = _require_env("FABRIC_LAKEHOUSE_NAME")
EVENTHOUSE_NAME: str = _require_env("FABRIC_EVENTHOUSE_NAME")
KQL_DB_NAME: str = os.getenv("FABRIC_KQL_DB_NAME", "")
ONTOLOGY_NAME: str = _require_env("FABRIC_ONTOLOGY_NAME")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_fabric_headers() -> dict[str, str]:
    """Return authorisation headers for Fabric REST API calls."""
    credential = DefaultAzureCredential()
    token = credential.get_token(FABRIC_SCOPE).token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
