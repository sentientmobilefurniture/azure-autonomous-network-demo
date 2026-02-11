"""
Test KQL queries against the Fabric Eventhouse (NetworkDB).

Uses the azure-kusto-data SDK with DefaultAzureCredential to query
the AlertStream and LinkTelemetry tables.

Prerequisites:
  - Eventhouse provisioned (provision_eventhouse.py)
  - EVENTHOUSE_QUERY_URI and FABRIC_KQL_DB_NAME set in azure_config.env
  - azure-kusto-data + azure-identity installed (already in project deps)

Usage:
  cd /home/hanchoong/projects/autonomous-network-demo
  uv run scripts/test_kql_query.py                              # runs sample queries
  uv run scripts/test_kql_query.py "AlertStream | take 5"       # custom KQL
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(str(PROJECT_ROOT / "azure_config.env"))

EVENTHOUSE_QUERY_URI = os.getenv("EVENTHOUSE_QUERY_URI", "")
KQL_DB_NAME = os.getenv("FABRIC_KQL_DB_NAME", "")

# ---------------------------------------------------------------------------
# KQL Client
# ---------------------------------------------------------------------------
_kusto_client: KustoClient | None = None


def get_kusto_client() -> KustoClient:
    """Lazy-init a KustoClient with DefaultAzureCredential."""
    global _kusto_client
    if _kusto_client is None:
        credential = DefaultAzureCredential()
        kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
            EVENTHOUSE_QUERY_URI, credential
        )
        _kusto_client = KustoClient(kcsb)
    return _kusto_client


# ---------------------------------------------------------------------------
# Execute KQL
# ---------------------------------------------------------------------------
def execute_kql(query: str, database: str | None = None) -> dict:
    """Submit a KQL query and return results as a dict.

    Returns:
        {
            "columns": [{"name": "...", "type": "..."}],
            "rows": [{"col1": val1, "col2": val2, ...}, ...]
        }
    On error:
        {
            "error": True,
            "detail": "..."
        }
    """
    db = database or KQL_DB_NAME
    try:
        client = get_kusto_client()
        response = client.execute(db, query)
        primary = response.primary_results[0] if response.primary_results else None
        if primary is None:
            return {"columns": [], "rows": []}

        columns = [
            {"name": col.column_name, "type": col.column_type}
            for col in primary.columns
        ]
        rows = []
        for row in primary:
            row_dict = {}
            for col in primary.columns:
                val = row[col.column_name]
                # Convert non-serializable types to string
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                row_dict[col.column_name] = val
            rows.append(row_dict)

        return {"columns": columns, "rows": rows}

    except Exception as e:
        return {"error": True, "detail": str(e)}


# ---------------------------------------------------------------------------
# Pretty print
# ---------------------------------------------------------------------------
def print_results(response: dict, query: str) -> None:
    print(f"\n{'─' * 70}")
    print(f"KQL:  {query}")
    print(f"{'─' * 70}")

    if "error" in response:
        print(f"  ✗ Error: {response['detail'][:500]}")
        return

    columns = response.get("columns", [])
    rows = response.get("rows", [])

    col_names = [c["name"] for c in columns]
    print(f"  Columns: {', '.join(col_names)}")
    print(f"  Rows: {len(rows)}")
    print()

    for i, row in enumerate(rows[:10]):  # limit display
        print(f"  [{i + 1}]", json.dumps(row, indent=6, ensure_ascii=False, default=str))

    if len(rows) > 10:
        print(f"  ... ({len(rows) - 10} more rows)")


# ---------------------------------------------------------------------------
# Sample queries
# ---------------------------------------------------------------------------
SAMPLE_QUERIES = [
    # Recent critical alerts
    "AlertStream | where Severity == 'CRITICAL' | top 5 by Timestamp desc | project AlertId, Timestamp, SourceNodeId, AlertType, Severity",
    # Link telemetry summary
    "LinkTelemetry | summarize avg(UtilizationPct), avg(LatencyMs), max(BitErrorRate) by LinkId | order by LinkId asc",
    # Count alerts by type
    "AlertStream | summarize cnt=count() by AlertType | order by cnt desc",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not EVENTHOUSE_QUERY_URI:
        print("✗ EVENTHOUSE_QUERY_URI not set in azure_config.env")
        sys.exit(1)
    if not KQL_DB_NAME:
        print("✗ FABRIC_KQL_DB_NAME not set in azure_config.env")
        sys.exit(1)

    print("Authenticating with DefaultAzureCredential...")
    print(f"Eventhouse: {EVENTHOUSE_QUERY_URI}")
    print(f"Database:   {KQL_DB_NAME}")

    # Determine which queries to run
    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]
    else:
        queries = SAMPLE_QUERIES

    for q in queries:
        result = execute_kql(q)
        print_results(result, q)

    print(f"\n{'═' * 70}")
    print("Done.")


if __name__ == "__main__":
    main()
