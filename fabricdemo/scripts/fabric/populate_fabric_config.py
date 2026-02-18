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
  - FABRIC_CONNECTION_NAME  (from AI Foundry project connections)

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

    # --- AI Foundry — find the Fabric connection name ---
    project_endpoint = os.getenv("PROJECT_ENDPOINT", "").rstrip("/")
    fabric_conn_name = ""
    if project_endpoint:
        # Ensure endpoint uses services.ai.azure.com and has /api/projects/ path
        if "/api/projects/" not in project_endpoint:
            project_name = os.getenv("AI_FOUNDRY_PROJECT_NAME", "")
            project_endpoint = project_endpoint.replace(
                "cognitiveservices.azure.com", "services.ai.azure.com"
            )
            if project_name:
                project_endpoint = f"{project_endpoint}/api/projects/{project_name}"
        print(f"\nLooking up Fabric connection in AI Foundry project...")
        try:
            from azure.ai.projects import AIProjectClient

            project_client = AIProjectClient(
                endpoint=project_endpoint,
                credential=DefaultAzureCredential(),
            )
            # List all connections and find ones that look like Fabric
            connections = project_client.connections.list()
            for conn in connections:
                # Fabric connections have category "MicrosoftFabric" or contain "fabric" in name
                conn_props = conn.properties if hasattr(conn, "properties") else {}
                category = getattr(conn_props, "category", "") if conn_props else ""
                conn_name = conn.name if hasattr(conn, "name") else ""

                if "fabric" in category.lower() or "fabric" in conn_name.lower():
                    fabric_conn_name = conn_name
                    print(f"  ✓ FABRIC_CONNECTION_NAME = {fabric_conn_name}  (category: {category})")
                    break

            if not fabric_conn_name:
                # Print all connections so the user can identify the right one
                print("  ⚠ No Fabric connection found. Available connections:")
                connections = project_client.connections.list()
                for conn in connections:
                    conn_props = conn.properties if hasattr(conn, "properties") else {}
                    category = getattr(conn_props, "category", "?") if conn_props else "?"
                    conn_name = conn.name if hasattr(conn, "name") else "?"
                    print(f"    - {conn_name}  (category: {category})")
        except Exception as e:
            print(f"  ⚠ Could not query AI Foundry connections: {e}")
            print("    You may need to install: pip install azure-ai-projects")
    else:
        print("\n  ⚠ PROJECT_ENDPOINT not set — skipping AI Foundry connection lookup")

    if fabric_conn_name:
        updates["FABRIC_CONNECTION_NAME"] = fabric_conn_name

    # Only write non-empty values
    updates = {k: v for k, v in updates.items() if v}

    if updates:
        update_env_file(updates)
        print(f"\n✓ Updated {len(updates)} values in azure_config.env")
    else:
        print("\n⚠ Nothing to update")


if __name__ == "__main__":
    main()
