"""
Provision (find or create) a Fabric workspace and write its ID to azure_config.env.

This script is the FIRST Fabric step — it ensures the workspace exists
before any downstream provisioning (lakehouse, eventhouse, ontology, RBAC).

Flow:
  1. Search for workspace by FABRIC_WORKSPACE_NAME
  2. If not found → create it and attach to FABRIC_CAPACITY_ID
  3. Poll until the workspace ID is confirmed accessible via API (retry)
  4. Write FABRIC_WORKSPACE_ID to azure_config.env

Usage:
  source azure_config.env && uv run python scripts/fabric/provision_workspace.py
"""

import os
import re
import sys
import time

import requests
from azure.identity import DefaultAzureCredential

from _config import (
    FABRIC_API,
    WORKSPACE_NAME,
    CAPACITY_ID,
    ENV_FILE,
    get_fabric_headers,
)


def find_workspace(headers: dict, name: str) -> dict | None:
    """Find workspace by display name."""
    r = requests.get(f"{FABRIC_API}/workspaces", headers=headers)
    r.raise_for_status()
    for ws in r.json().get("value", []):
        if ws["displayName"] == name:
            return ws
    return None


def create_workspace(headers: dict, name: str, capacity_id: str = "") -> dict:
    """Create a Fabric workspace, optionally attach to capacity."""
    body = {"displayName": name}
    if capacity_id:
        body["capacityId"] = capacity_id
    r = requests.post(f"{FABRIC_API}/workspaces", headers=headers, json=body)
    if r.status_code == 201:
        return r.json()
    # Handle name conflict (workspace exists but wasn't found — eventual consistency)
    if r.status_code == 409:
        print(f"  ⚠ Workspace '{name}' already exists (409 conflict) — searching again...")
        return None
    r.raise_for_status()
    return r.json()


def assign_capacity(headers: dict, workspace_id: str, capacity_id: str):
    """Assign capacity to an existing workspace."""
    r = requests.post(
        f"{FABRIC_API}/workspaces/{workspace_id}/assignToCapacity",
        headers=headers,
        json={"capacityId": capacity_id},
    )
    if r.status_code in (200, 202):
        print(f"  ✓ Capacity assigned: {capacity_id}")
    elif r.status_code == 409:
        print(f"  ✓ Capacity already assigned")
    else:
        print(f"  ⚠ Assign capacity: {r.status_code} — {r.text}")


def wait_for_workspace(headers: dict, name: str, max_retries: int = 10, retry_delay: int = 10) -> dict:
    """Poll until workspace is discoverable via the Fabric API."""
    for attempt in range(1, max_retries + 1):
        ws = find_workspace(headers, name)
        if ws:
            return ws
        print(f"  ⏳ Workspace not yet visible (attempt {attempt}/{max_retries}), retrying in {retry_delay}s...")
        time.sleep(retry_delay)
    print(f"  ✗ Workspace '{name}' not found after {max_retries} attempts")
    sys.exit(1)


def update_env_file(key: str, value: str):
    """Update or append a key=value in azure_config.env."""
    if not os.path.exists(ENV_FILE):
        with open(ENV_FILE, "w") as f:
            f.write(f"{key}={value}\n")
        return

    with open(ENV_FILE, "r") as f:
        content = f.read()

    pattern = rf"^({re.escape(key)}=)(.*)$"
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, rf"\g<1>{value}", content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{key}={value}\n"

    with open(ENV_FILE, "w") as f:
        f.write(content)


def main():
    headers = get_fabric_headers()

    print("=" * 60)
    print(f"Provisioning Fabric workspace: {WORKSPACE_NAME}")
    print("=" * 60)

    # 1. Look for existing workspace
    print(f"  Looking for workspace '{WORKSPACE_NAME}'...")
    ws = find_workspace(headers, WORKSPACE_NAME)

    if ws:
        print(f"  ✓ Workspace already exists: {ws['id']}")
    else:
        # 2. Create workspace
        print(f"  Workspace not found — creating...")
        ws = create_workspace(headers, WORKSPACE_NAME, CAPACITY_ID)

        if ws is None:
            # 409 conflict — retry finding it
            ws = wait_for_workspace(headers, WORKSPACE_NAME)
            print(f"  ✓ Found workspace after conflict: {ws['id']}")
        else:
            print(f"  ✓ Workspace created: {ws['id']}")
            # Wait for it to be fully accessible
            print(f"  Waiting for workspace to be fully accessible...")
            ws = wait_for_workspace(headers, WORKSPACE_NAME)

    workspace_id = ws["id"]

    # 3. Ensure capacity is assigned
    if CAPACITY_ID and not ws.get("capacityId"):
        print(f"  Assigning capacity...")
        assign_capacity(headers, workspace_id, CAPACITY_ID)

    # 4. Write to azure_config.env
    update_env_file("FABRIC_WORKSPACE_ID", workspace_id)
    print(f"\n  ✓ FABRIC_WORKSPACE_ID={workspace_id} written to azure_config.env")

    print("=" * 60)
    print(f"✅ Workspace ready: {WORKSPACE_NAME} ({workspace_id})")
    print("=" * 60)


if __name__ == "__main__":
    main()
