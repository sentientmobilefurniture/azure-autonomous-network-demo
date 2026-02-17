"""
Assign Fabric workspace Contributor role to the graph-query-api managed identity.

The graph-query-api Container App uses a system-assigned managed identity to
authenticate to Fabric (GQL and KQL).  That identity must be a workspace member
before it can execute queries.

This script:
  1. Reads FABRIC_WORKSPACE_ID and GRAPH_QUERY_API_PRINCIPAL_ID from azure_config.env.
  2. Checks existing role assignments — skips if the principal already has access.
  3. Adds the principal as Contributor via the Fabric REST API.

Run after both `azd up` (creates the Container App + identity) and
`provision_lakehouse.py` (creates the Fabric workspace).

Usage:
    uv run python scripts/assign_fabric_role.py
"""

from __future__ import annotations

import os
import sys

import requests

from _config import FABRIC_API, WORKSPACE_ID, get_fabric_headers, load_dotenv, ENV_FILE

# Re-load to pick up latest values
load_dotenv(ENV_FILE, override=True)


def _get_required_env(name: str, fallback: str = "") -> str:
    val = os.getenv(name, fallback)
    if not val:
        print(f"✗ {name} is not set in azure_config.env")
        sys.exit(1)
    return val


def list_role_assignments(workspace_id: str) -> list[dict]:
    """Return current workspace role assignments."""
    url = f"{FABRIC_API}/workspaces/{workspace_id}/roleAssignments"
    r = requests.get(url, headers=get_fabric_headers())
    r.raise_for_status()
    return r.json().get("value", [])


def principal_has_role(workspace_id: str, principal_id: str) -> str | None:
    """Return the existing role name if the principal already has one, else None."""
    for ra in list_role_assignments(workspace_id):
        pid = ra.get("principal", {}).get("id", "")
        if pid.lower() == principal_id.lower():
            return ra.get("role", "Unknown")
    return None


def assign_contributor_role(workspace_id: str, principal_id: str) -> None:
    """Add the principal as Contributor on the Fabric workspace."""
    url = f"{FABRIC_API}/workspaces/{workspace_id}/roleAssignments"
    body = {
        "principal": {
            "id": principal_id,
            "type": "ServicePrincipal",
        },
        "role": "Contributor",
    }
    r = requests.post(url, headers=get_fabric_headers(), json=body)
    if r.status_code in (200, 201):
        print(f"  ✓ Assigned Contributor role to {principal_id}")
    elif r.status_code == 409:
        print(f"  ✓ Principal {principal_id} already has a role assignment (409 conflict)")
    else:
        print(f"  ✗ Failed ({r.status_code}): {r.text[:300]}")
        r.raise_for_status()


def main() -> None:
    workspace_id = _get_required_env("FABRIC_WORKSPACE_ID", WORKSPACE_ID)
    principal_id = _get_required_env("APP_PRINCIPAL_ID")

    print("Fabric workspace role assignment")
    print(f"  Workspace : {workspace_id}")
    print(f"  Principal : {principal_id}")

    existing = principal_has_role(workspace_id, principal_id)
    if existing:
        print(f"  ✓ Already has role: {existing} — nothing to do")
        return

    assign_contributor_role(workspace_id, principal_id)
    print("Done.")


if __name__ == "__main__":
    main()
