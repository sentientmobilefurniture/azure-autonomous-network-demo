"""
Quick diagnostic — checks the state of all Fabric items and their data.

Usage:
  uv run check_status.py
"""

import os
import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv("azure_config.env")

FABRIC_API = "https://api.fabric.microsoft.com/v1"
WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")


def get_headers():
    credential = DefaultAzureCredential()
    token = credential.get_token("https://api.fabric.microsoft.com/.default").token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def main():
    headers = get_headers()

    if not WORKSPACE_ID:
        print("✗ FABRIC_WORKSPACE_ID not set in azure_config.env")
        return

    # ------------------------------------------------------------------
    # 1. List all items in workspace
    # ------------------------------------------------------------------
    print("=" * 70)
    print(f"Workspace: {WORKSPACE_ID}")
    print("=" * 70)

    r = requests.get(f"{FABRIC_API}/workspaces/{WORKSPACE_ID}/items", headers=headers)
    if r.status_code != 200:
        print(f"✗ Failed to list items: {r.status_code} — {r.text}")
        return

    items = r.json().get("value", [])
    print(f"\n{'Type':<25} {'Name':<50} {'ID'}")
    print("-" * 110)
    for item in sorted(items, key=lambda x: x.get("type", "")):
        print(f"{item.get('type', '?'):<25} {item['displayName']:<50} {item['id']}")

    print(f"\nTotal: {len(items)} items")

    # ------------------------------------------------------------------
    # 2. Lakehouse — check tables
    # ------------------------------------------------------------------
    lakehouses = [i for i in items if i.get("type") == "Lakehouse"]
    for lh in lakehouses:
        print(f"\n--- Lakehouse: {lh['displayName']} ---")
        r = requests.get(
            f"{FABRIC_API}/workspaces/{WORKSPACE_ID}/lakehouses/{lh['id']}/tables",
            headers=headers,
        )
        if r.status_code == 200:
            tables = r.json().get("data", [])
            if tables:
                for t in tables:
                    fmt = t.get("format", "?")
                    loc = t.get("location", "?")
                    print(f"  ✓ {t['name']:<30} ({fmt})")
            else:
                print("  ⚠ No tables found")
        else:
            print(f"  ✗ Could not list tables: {r.status_code} — {r.text}")

    # ------------------------------------------------------------------
    # 3. Eventhouse / KQL DB — check tables
    # ------------------------------------------------------------------
    kql_dbs = [i for i in items if i.get("type") == "KQLDatabase"]
    for db in kql_dbs:
        print(f"\n--- KQL Database: {db['displayName']} ---")
        r = requests.get(
            f"{FABRIC_API}/workspaces/{WORKSPACE_ID}/kqlDatabases/{db['id']}",
            headers=headers,
        )
        if r.status_code == 200:
            props = r.json().get("properties", {})
            uri = props.get("queryServiceUri", "N/A")
            db_name = props.get("databaseName", "N/A")
            print(f"  Query URI: {uri}")
            print(f"  DB name:   {db_name}")
        else:
            print(f"  ✗ Could not get details: {r.status_code}")

    # ------------------------------------------------------------------
    # 4. Ontology — check existence
    # ------------------------------------------------------------------
    ontologies = [i for i in items if i.get("type") == "Ontology"]
    for ont in ontologies:
        print(f"\n--- Ontology: {ont['displayName']} ({ont['id']}) ---")
        print(f"  ✓ Exists")

    # ------------------------------------------------------------------
    # 5. Graph — check job instances (most recent)
    # ------------------------------------------------------------------
    graphs = [i for i in items if i.get("type") in ("GraphModel", "Graph")]
    for g in graphs:
        print(f"\n--- Graph: {g['displayName']} ({g['id']}) ---")
        r = requests.get(
            f"{FABRIC_API}/workspaces/{WORKSPACE_ID}/items/{g['id']}/jobs/instances",
            headers=headers,
        )
        if r.status_code == 200:
            jobs = r.json().get("value", [])
            if jobs:
                print(f"  Job instances ({len(jobs)}):")
                for j in jobs[:5]:  # Show last 5
                    status = j.get("status", "?")
                    jtype = j.get("jobType", "?")
                    start = j.get("startTimeUtc", "?")
                    end = j.get("endTimeUtc", "")
                    invoke = j.get("invokeType", "?")
                    icon = "✓" if status == "Completed" else "⚡" if status == "InProgress" else "✗"
                    print(f"  {icon} {jtype:<20} {status:<15} {invoke:<10} {start} → {end or '...'}")
                    if j.get("failureReason"):
                        reason = j["failureReason"]
                        if isinstance(reason, dict):
                            print(f"    Error: {reason.get('message', reason)}")
                        else:
                            print(f"    Error: {reason}")
            else:
                print("  ⚠ No job instances — graph has never been refreshed")
                print("    → This is why the Data Agent can't query anything")
                print("    → Manually refresh: Workspace → graph item → ... → Schedule → Refresh now")
        else:
            print(f"  ✗ Could not list jobs: {r.status_code} — {r.text}")

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  Lakehouses:  {len(lakehouses)} {'✓' if lakehouses else '✗ MISSING'}")
    print(f"  KQL DBs:     {len(kql_dbs)} {'✓' if kql_dbs else '✗ MISSING'}")
    print(f"  Ontologies:  {len(ontologies)} {'✓' if ontologies else '✗ MISSING'}")
    print(f"  Graphs:      {len(graphs)} {'✓' if graphs else '✗ MISSING'}")

    if not graphs:
        print("\n  ⚠ No graph items found — the ontology may not have created one yet")
    elif all(
        r.status_code == 200
        and not r.json().get("value", [])
        for g in graphs
        for r in [requests.get(f"{FABRIC_API}/workspaces/{WORKSPACE_ID}/items/{g['id']}/jobs/instances", headers=headers)]
    ):
        print("\n  ⚠ Graph exists but has never been refreshed — trigger a refresh!")
    print("=" * 70)


if __name__ == "__main__":
    main()
