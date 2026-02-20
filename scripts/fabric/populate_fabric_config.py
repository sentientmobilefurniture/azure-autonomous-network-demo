"""
Populate Fabric IDs in azure_config.env by looking up items via Fabric REST API
and the Fabric connection name from AI Foundry.

Finds the workspace by FABRIC_WORKSPACE_NAME, then discovers:
  - FABRIC_WORKSPACE_ID
  - FABRIC_LAKEHOUSE_ID
  - FABRIC_EVENTHOUSE_ID
  - FABRIC_KQL_DB_ID
  - FABRIC_KQL_DB_NAME
  - EVENTHOUSE_QUERY_URI
Usage:
  uv run populate_fabric_config.py
"""

import os
import re
import sys

import requests
from azure.identity import DefaultAzureCredential

from _config import FABRIC_API, ENV_FILE, WORKSPACE_NAME, get_fabric_headers


def find_workspace(headers: dict, name: str) -> dict | None:
    r = requests.get(f"{FABRIC_API}/workspaces", headers=headers)
    r.raise_for_status()
    for ws in r.json().get("value", []):
        if ws["displayName"] == name:
            return ws
    return None


def find_items_by_type(headers: dict, workspace_id: str, item_type: str) -> list[dict]:
    r = requests.get(f"{FABRIC_API}/workspaces/{workspace_id}/items", headers=headers)
    r.raise_for_status()
    return [i for i in r.json().get("value", []) if i.get("type") == item_type]


def get_kql_db_details(headers: dict, workspace_id: str, db_id: str) -> dict:
    r = requests.get(
        f"{FABRIC_API}/workspaces/{workspace_id}/kqlDatabases/{db_id}",
        headers=headers,
    )
    r.raise_for_status()
    return r.json()


def update_env_file(updates: dict[str, str]):
    """Update key=value pairs in azure_config.env, preserving structure."""
    with open(ENV_FILE, "r") as f:
        content = f.read()

    for key, value in updates.items():
        # Match KEY= or KEY=existing_value (rest of line)
        pattern = rf"^({re.escape(key)}=)(.*)$"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, rf"\g<1>{value}", content, flags=re.MULTILINE)
        else:
            # Key doesn't exist — append
            content = content.rstrip("\n") + f"\n{key}={value}\n"

    with open(ENV_FILE, "w") as f:
        f.write(content)


def main():
    headers = get_fabric_headers()

    # --- Workspace ---
    print(f"Looking up workspace: {WORKSPACE_NAME}")
    ws = find_workspace(headers, WORKSPACE_NAME)
    if not ws:
        print(f"✗ Workspace '{WORKSPACE_NAME}' not found")
        sys.exit(1)
    workspace_id = ws["id"]
    print(f"  ✓ FABRIC_WORKSPACE_ID = {workspace_id}")

    # --- List all items ---
    r = requests.get(f"{FABRIC_API}/workspaces/{workspace_id}/items", headers=headers)
    r.raise_for_status()
    items = r.json().get("value", [])

    # --- Lakehouse ---
    lakehouses = [i for i in items if i.get("type") == "Lakehouse"]
    lakehouse_id = ""
    if lakehouses:
        lh = lakehouses[0]  # Take the first one
        lakehouse_id = lh["id"]
        print(f"  ✓ FABRIC_LAKEHOUSE_ID = {lakehouse_id}  ({lh['displayName']})")
    else:
        print("  ⚠ No Lakehouse found")

    # --- Eventhouse ---
    eventhouses = [i for i in items if i.get("type") == "Eventhouse"]
    eventhouse_id = ""
    if eventhouses:
        eh = eventhouses[0]
        eventhouse_id = eh["id"]
        print(f"  ✓ FABRIC_EVENTHOUSE_ID = {eventhouse_id}  ({eh['displayName']})")
    else:
        print("  ⚠ No Eventhouse found")

    # --- KQL Database ---
    kql_dbs = [i for i in items if i.get("type") == "KQLDatabase"]
    kql_db_id = ""
    kql_db_name = ""
    query_uri = ""
    if kql_dbs:
        db = kql_dbs[0]
        kql_db_id = db["id"]
        print(f"  ✓ FABRIC_KQL_DB_ID = {kql_db_id}  ({db['displayName']})")

        # Get query URI and database name from properties
        details = get_kql_db_details(headers, workspace_id, kql_db_id)
        props = details.get("properties", {})
        query_uri = props.get("queryServiceUri", "")
        kql_db_name = props.get("databaseName", db["displayName"])
        print(f"  ✓ FABRIC_KQL_DB_NAME = {kql_db_name}")
        print(f"  ✓ EVENTHOUSE_QUERY_URI = {query_uri}")
    else:
        print("  ⚠ No KQL Database found")

    # --- Write to azure_config.env ---
    updates = {
        "FABRIC_WORKSPACE_ID": workspace_id,
        "FABRIC_LAKEHOUSE_ID": lakehouse_id,
        "FABRIC_EVENTHOUSE_ID": eventhouse_id,
        "FABRIC_KQL_DB_ID": kql_db_id,
        "FABRIC_KQL_DB_NAME": kql_db_name,
        "EVENTHOUSE_QUERY_URI": query_uri,
    }

    # Only write non-empty values
    updates = {k: v for k, v in updates.items() if v}

    if updates:
        update_env_file(updates)
        print(f"\n✓ Updated {len(updates)} values in azure_config.env")
    else:
        print("\n⚠ Nothing to update")


if __name__ == "__main__":
    main()
