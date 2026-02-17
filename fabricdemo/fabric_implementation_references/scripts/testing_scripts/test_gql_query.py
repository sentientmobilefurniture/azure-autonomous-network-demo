"""
Test GQL (Graph Query Language) queries against a Microsoft Fabric Graph Model.

Uses the Fabric REST API's Execute Query (beta) endpoint:
  POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/GraphModels/{graphModelId}/executeQuery?beta=True

Prerequisites:
  - Graph Model item exists in the Fabric workspace (created by provision_ontology.py)
  - Caller has at least *viewer* workspace role
  - azure-identity + requests installed (already in project deps)

Usage:
  cd /home/hanchoong/projects/autonomous-network-demo
  uv run scripts/test_gql_query.py                                  # runs default sample queries
  uv run scripts/test_gql_query.py "MATCH (r:CoreRouter) RETURN r.RouterId, r.City LIMIT 5"
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(str(PROJECT_ROOT / "azure_config.env"))

FABRIC_API = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")
WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "NetworkTopologyOntology")
GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
credential = DefaultAzureCredential()


def get_headers() -> dict[str, str]:
    token = credential.get_token(FABRIC_SCOPE).token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Discover Graph Model ID
# ---------------------------------------------------------------------------
def find_graph_model_id(workspace_id: str) -> str | None:
    """Find the GraphModel item in the workspace (auto-created by ontology)."""
    headers = get_headers()

    # Try listing GraphModel items directly
    r = requests.get(
        f"{FABRIC_API}/workspaces/{workspace_id}/GraphModels",
        headers=headers,
    )
    if r.status_code == 200:
        models = r.json().get("value", [])
        if models:
            # Prefer one whose name matches the ontology
            for m in models:
                if ONTOLOGY_NAME.lower() in m.get("displayName", "").lower():
                    return m["id"]
            return models[0]["id"]

    # Fallback: list all items and filter by type
    r = requests.get(
        f"{FABRIC_API}/workspaces/{workspace_id}/items",
        headers=headers,
    )
    r.raise_for_status()
    for item in r.json().get("value", []):
        if item.get("type") in ("GraphModel", "Graph"):
            if ONTOLOGY_NAME.lower() in item["displayName"].lower():
                return item["id"]
    # Last resort — first graph-ish item
    for item in r.json().get("value", []):
        if item.get("type") in ("GraphModel", "Graph"):
            return item["id"]
    return None


# ---------------------------------------------------------------------------
# Execute GQL Query
# ---------------------------------------------------------------------------
def execute_gql(workspace_id: str, graph_model_id: str, query: str, max_retries: int = 5) -> dict:
    """Submit a GQL query to the Fabric GraphModel Execute Query (beta) API.

    Automatically retries on 429 (rate-limited / RequestBlocked) with backoff.
    """
    url = (
        f"{FABRIC_API}/workspaces/{workspace_id}"
        f"/GraphModels/{graph_model_id}/executeQuery"
    )
    body = {"query": query}

    for attempt in range(1, max_retries + 1):
        headers = get_headers()
        r = requests.post(url, headers=headers, json=body, params={"beta": "True"})

        if r.status_code == 200:
            return r.json()

        if r.status_code == 429:
            # Parse Retry-After header or blocked-until timestamp from body
            retry_after = int(r.headers.get("Retry-After", "0"))
            if not retry_after:
                # Try to extract from the error message timestamp
                try:
                    msg = r.json().get("message", "")
                    # e.g. "...until: 2/11/2026 12:54:06 PM (UTC)"
                    if "until:" in msg:
                        ts_str = msg.split("until:")[1].strip().rstrip(")")
                        ts_str = ts_str.replace("(UTC", "").strip()
                        blocked_until = datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")
                        blocked_until = blocked_until.replace(tzinfo=timezone.utc)
                        wait = (blocked_until - datetime.now(timezone.utc)).total_seconds()
                        retry_after = max(int(wait) + 1, 3)
                except Exception:
                    pass
            retry_after = max(retry_after, 15 * attempt)  # at least 15s × attempt (F4 cold start)

            if attempt < max_retries:
                print(f"  ⏳ Rate-limited (429). Waiting {retry_after}s before retry {attempt}/{max_retries}...")
                time.sleep(retry_after)
                continue

        return {
            "error": True,
            "status_code": r.status_code,
            "detail": r.text,
        }

    return {"error": True, "status_code": 429, "detail": "Max retries exceeded"}


def print_results(response: dict, query: str) -> None:
    """Pretty-print GQL query results."""
    print(f"\n{'─' * 70}")
    print(f"GQL:  {query}")
    print(f"{'─' * 70}")

    if "error" in response:
        print(f"  ✗ HTTP {response['status_code']}")
        print(f"    {response['detail'][:500]}")
        return

    status = response.get("status", {})
    code = status.get("code", "?")
    desc = status.get("description", "")
    print(f"  Status: {code} — {desc}")

    result = response.get("result", {})
    columns = result.get("columns", [])
    data = result.get("data", [])

    if not data:
        print("  (no rows)")
        return

    # Print column headers
    col_names = [c["name"] for c in columns]
    print(f"  Columns: {', '.join(col_names)}")
    print(f"  Rows: {len(data)}")
    print()

    # Print rows (pretty)
    for i, row in enumerate(data):
        print(f"  [{i + 1}]", json.dumps(row, indent=6, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Sample queries for the Network Topology ontology
# ---------------------------------------------------------------------------
SAMPLE_QUERIES = [
    # Count all node types
    "MATCH (n) RETURN LABELS(n) AS type, count(n) AS cnt GROUP BY type ORDER BY cnt DESC",
    # List core routers
    "MATCH (r:CoreRouter) RETURN r.RouterId AS router, r.City AS city, r.Region AS region LIMIT 10",
    # Find what each router connects to
    "MATCH (l:TransportLink)-[:connects_to]->(r:CoreRouter) RETURN r.RouterId AS router, l.LinkId AS link, l.LinkType AS type LIMIT 10",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not WORKSPACE_ID:
        print("✗ FABRIC_WORKSPACE_ID not set in azure_config.env")
        sys.exit(1)

    print("Authenticating with DefaultAzureCredential...")
    print(f"Workspace: {WORKSPACE_ID}")

    # Discover graph model (use env var if available, else auto-discover)
    graph_model_id = GRAPH_MODEL_ID
    if graph_model_id:
        print(f"Using FABRIC_GRAPH_MODEL_ID from env: {graph_model_id}")
    else:
        print("Looking for GraphModel item in workspace...")
        graph_model_id = find_graph_model_id(WORKSPACE_ID)
    if not graph_model_id:
        print("✗ No GraphModel found in workspace.")
        print("  Make sure provision_ontology.py has been run successfully.")
        sys.exit(1)
    print(f"  ✓ GraphModel ID: {graph_model_id}")

    # Determine which queries to run
    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]
    else:
        queries = SAMPLE_QUERIES

    # Execute queries (with delay between to avoid rate-limiting)
    for i, q in enumerate(queries):
        if i > 0:
            time.sleep(10)  # pause between queries to avoid F4 throttling
        result = execute_gql(WORKSPACE_ID, graph_model_id, q)
        print_results(result, q)

    print(f"\n{'═' * 70}")
    print("Done.")


if __name__ == "__main__":
    main()
