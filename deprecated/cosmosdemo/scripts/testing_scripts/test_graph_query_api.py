"""
Test the deployed graph-query-api Container App.

Sends test Gremlin and SQL queries to verify both endpoints are working
after deployment (azd deploy --service graph-query-api).

Usage:
  # Auto-discover URL from azure_config.env
  uv run scripts/test_graph_query_api.py

  # Or pass explicitly
  uv run scripts/test_graph_query_api.py https://ca-graphquery-xxx.region.azurecontainerapps.io
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(str(PROJECT_ROOT / "azure_config.env"))


def get_base_url() -> str:
    """Get the base URL, from CLI arg, env var, or default to localhost."""
    if len(sys.argv) > 1:
        return sys.argv[1].rstrip("/")
    url = os.getenv("GRAPH_QUERY_API_URI", "")
    if url:
        return url.rstrip("/")
    return "http://localhost:8100"


def test_health(base: str) -> bool:
    print(f"\n{'─' * 60}")
    print(f"GET {base}/health")
    try:
        r = requests.get(f"{base}/health", timeout=10)
        print(f"  Status: {r.status_code}")
        print(f"  Body:   {r.json()}")
        return r.status_code == 200
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def test_graph(base: str) -> bool:
    print(f"\n{'─' * 60}")
    query = "MATCH (r:CoreRouter) RETURN r.RouterId, r.City LIMIT 3"
    print(f"POST {base}/query/graph")
    print(f"  Query: {query}")
    try:
        r = requests.post(
            f"{base}/query/graph",
            json={"query": query},
            timeout=30,
        )
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            body = r.json()
            print(f"  Columns: {[c['name'] for c in body.get('columns', [])]}")
            print(f"  Rows:    {len(body.get('data', []))}")
            for row in body.get("data", []):
                print(f"    {json.dumps(row, ensure_ascii=False)}")
            return len(body.get("data", [])) > 0
        else:
            print(f"  ✗ Error: {r.text[:300]}")
            return False
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def test_telemetry(base: str) -> bool:
    print(f"\n{'─' * 60}")
    query = "AlertStream | summarize cnt=count() by AlertType | top 3 by cnt desc"
    print(f"POST {base}/query/telemetry")
    print(f"  Query: {query}")
    try:
        r = requests.post(
            f"{base}/query/telemetry",
            json={"query": query},
            timeout=30,
        )
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            body = r.json()
            print(f"  Columns: {[c['name'] for c in body.get('columns', [])]}")
            print(f"  Rows:    {len(body.get('rows', []))}")
            for row in body.get("rows", []):
                print(f"    {json.dumps(row, ensure_ascii=False)}")
            return len(body.get("rows", [])) > 0
        else:
            print(f"  ✗ Error: {r.text[:300]}")
            return False
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def main():
    base = get_base_url()
    print("=" * 60)
    print(f"  Graph Query API — Deployment Verification")
    print(f"  Target: {base}")
    print("=" * 60)

    results = {
        "health": test_health(base),
        "graph (Gremlin)": test_graph(base),
        "telemetry (SQL)": test_telemetry(base),
    }

    print(f"\n{'═' * 60}")
    print("  Results:")
    all_pass = True
    for name, ok in results.items():
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"    {name:20s} {status}")
        if not ok:
            all_pass = False

    print(f"{'═' * 60}")
    if all_pass:
        print("  All tests passed!")
    else:
        print("  Some tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
