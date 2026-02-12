#!/usr/bin/env python3
"""
Provision Cosmos DB NoSQL telemetry containers — load CSV data.

Loads AlertStream.csv and LinkTelemetry.csv from data/telemetry/ into
Azure Cosmos DB NoSQL containers in the telemetrydb database.

Usage:
    source azure_config.env
    uv run python scripts/cosmos/provision_cosmos_telemetry.py

    # Keep existing data (don't clear containers first)
    uv run python scripts/cosmos/provision_cosmos_telemetry.py --no-clear

Requires: azure-cosmos, azure-identity
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceExistsError
from azure.identity import DefaultAzureCredential

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "telemetry"

ENDPOINT = os.environ.get("COSMOS_NOSQL_ENDPOINT", "")
DATABASE = os.environ.get("COSMOS_NOSQL_DATABASE", "telemetrydb")

# Container definitions: name → (partition_key_path, csv_file, id_field)
CONTAINERS = {
    "AlertStream": {
        "partition_key": "/SourceNodeType",
        "csv_file": "AlertStream.csv",
        "id_field": "AlertId",
        "numeric_fields": {"OpticalPowerDbm", "BitErrorRate", "CPUUtilPct", "PacketLossPct"},
    },
    "LinkTelemetry": {
        "partition_key": "/LinkId",
        "csv_file": "LinkTelemetry.csv",
        "id_field": None,  # composite: LinkId + Timestamp
        "numeric_fields": {"UtilizationPct", "OpticalPowerDbm", "BitErrorRate", "LatencyMs"},
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_row(row: dict, numeric_fields: set[str], id_field: str | None) -> dict:
    """Convert CSV string values to appropriate types and add 'id' field."""
    doc = {}
    for key, value in row.items():
        if key in numeric_fields:
            try:
                doc[key] = float(value) if value else 0.0
            except ValueError:
                doc[key] = 0.0
        else:
            doc[key] = value

    # Cosmos DB requires an 'id' field
    if id_field and id_field in doc:
        doc["id"] = doc[id_field]
    else:
        # Composite key for LinkTelemetry
        link_id = doc.get("LinkId", "unknown")
        timestamp = doc.get("Timestamp", "unknown")
        doc["id"] = f"{link_id}_{timestamp}"

    return doc


def _load_csv(csv_path: Path) -> list[dict]:
    """Load a CSV file and return list of dicts."""
    if not csv_path.exists():
        print(f"  ✗ CSV file not found: {csv_path}")
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _clear_container(container) -> int:
    """Delete all items from a container. Returns count deleted."""
    items = list(container.query_items(
        query="SELECT c.id, c.SourceNodeType, c.LinkId FROM c",
        enable_cross_partition_query=True,
    ))
    count = 0
    for item in items:
        # Determine partition key value
        pk = item.get("SourceNodeType") or item.get("LinkId") or ""
        try:
            container.delete_item(item=item["id"], partition_key=pk)
            count += 1
        except CosmosHttpResponseError:
            pass
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Load telemetry CSV data into Cosmos DB NoSQL")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear containers before loading")
    args = parser.parse_args()

    print("=" * 72)
    print("  Cosmos DB NoSQL — Telemetry Data Loader")
    print("=" * 72)

    if not ENDPOINT:
        print("\n  ✗ COSMOS_NOSQL_ENDPOINT is not set.")
        print("    Set it in azure_config.env or export it before running.")
        sys.exit(1)

    print(f"\n  Endpoint:  {ENDPOINT}")
    print(f"  Database:  {DATABASE}")
    print(f"  Data dir:  {DATA_DIR}")

    # Connect using DefaultAzureCredential
    print("\n[1/3] Connecting to Cosmos DB...")
    credential = DefaultAzureCredential()
    client = CosmosClient(url=ENDPOINT, credential=credential)

    # Ensure database exists (it should have been created by Bicep)
    print(f"\n[2/3] Ensuring database '{DATABASE}' exists...")
    try:
        database = client.create_database_if_not_exists(id=DATABASE)
        print(f"  ✓ Database: {DATABASE}")
    except CosmosHttpResponseError as e:
        print(f"  ✗ Failed to access database: {e.message}")
        sys.exit(1)

    # Load each container
    print(f"\n[3/3] Loading telemetry data...")
    total_docs = 0

    for container_name, config in CONTAINERS.items():
        csv_path = DATA_DIR / config["csv_file"]
        print(f"\n  ── {container_name} ──")

        # Ensure container exists
        try:
            container = database.create_container_if_not_exists(
                id=container_name,
                partition_key=PartitionKey(path=config["partition_key"]),
            )
            print(f"  ✓ Container: {container_name} (pk: {config['partition_key']})")
        except CosmosHttpResponseError as e:
            print(f"  ✗ Failed to create container: {e.message}")
            continue

        # Clear existing data if requested
        if not args.no_clear:
            print("  Clearing existing data...")
            deleted = _clear_container(container)
            if deleted:
                print(f"  Deleted {deleted} existing documents")

        # Load CSV data
        rows = _load_csv(csv_path)
        if not rows:
            print(f"  ✗ No data to load from {csv_path.name}")
            continue

        print(f"  Loading {len(rows)} documents from {csv_path.name}...")
        t0 = time.time()
        loaded = 0
        errors = 0

        for i, row in enumerate(rows):
            doc = _coerce_row(row, config["numeric_fields"], config["id_field"])
            try:
                container.upsert_item(body=doc)
                loaded += 1
            except CosmosHttpResponseError as e:
                errors += 1
                if errors <= 3:
                    print(f"    ✗ Error on row {i}: {e.message}")

            # Progress indicator every 500 rows
            if (i + 1) % 500 == 0:
                print(f"    ... {i + 1}/{len(rows)}")

        elapsed = time.time() - t0
        total_docs += loaded
        print(f"  ✓ Loaded {loaded}/{len(rows)} documents in {elapsed:.1f}s")
        if errors:
            print(f"    ({errors} errors)")

    # Summary
    print("\n" + "=" * 72)
    print(f"  Done! Loaded {total_docs} total documents.")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
