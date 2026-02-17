#!/usr/bin/env python3
"""
Provision Cosmos DB NoSQL containers — async bulk load.

Generalized Cosmos DB provisioner that creates databases, containers,
and bulk-loads CSV data. For the telco-noc demo, loads AlertStream
and LinkTelemetry into Cosmos NoSQL.

Data source options:
  (default)       Read CSVs from local data/scenarios/telco-noc/data/telemetry/
  --from-blob     Read CSVs from Azure Blob Storage ('telemetry-data' container)

Usage:
    source azure_config.env
    uv run python scripts/provision_cosmos.py

    # Read from blob storage instead of local files
    uv run python scripts/provision_cosmos.py --from-blob

    # Keep existing data
    uv run python scripts/provision_cosmos.py --no-clear

Requires: azure-cosmos, azure-identity, (optional) azure-storage-blob for --from-blob
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import os
import sys
import time
from pathlib import Path

from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError
from azure.identity.aio import DefaultAzureCredential

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "scenarios" / "telco-noc" / "data" / "telemetry"

ENDPOINT = os.environ.get("COSMOS_NOSQL_ENDPOINT", "")
DATABASE = os.environ.get("COSMOS_NOSQL_DATABASE", "telemetrydb")

STORAGE_ACCOUNT = os.environ.get("STORAGE_ACCOUNT_NAME", "")
BLOB_CONTAINER = "telemetry-data"

# Concurrency — how many upserts run in parallel.
# Cosmos DB NoSQL allows up to 100 concurrent operations per partition;
# 50 is conservative and avoids 429 rate-limit storms.
CONCURRENCY = 50

# Container definitions: name → config
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
    doc: dict = {}
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


def _load_csv_local(csv_path: Path) -> list[dict]:
    """Load a CSV from the local filesystem."""
    if not csv_path.exists():
        print(f"  ✗ CSV file not found: {csv_path}")
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def _load_csv_blob(credential: DefaultAzureCredential, csv_file: str) -> list[dict]:
    """Download a CSV from Azure Blob Storage and parse it."""
    from azure.storage.blob.aio import BlobServiceClient

    blob_url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net"
    async with BlobServiceClient(blob_url, credential=credential) as bsc:
        blob = bsc.get_blob_client(BLOB_CONTAINER, csv_file)
        stream = await blob.download_blob()
        content = await stream.readall()
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        return list(reader)


async def _clear_container(container) -> int:
    """Delete all items from a Cosmos DB container (async)."""
    items = []
    async for item in container.query_items(
        query="SELECT c.id, c.SourceNodeType, c.LinkId FROM c",
    ):
        items.append(item)

    if not items:
        return 0

    sem = asyncio.Semaphore(CONCURRENCY)
    deleted = 0

    async def _delete_one(item: dict):
        nonlocal deleted
        pk = item.get("SourceNodeType") or item.get("LinkId") or ""
        async with sem:
            try:
                await container.delete_item(item=item["id"], partition_key=pk)
                deleted += 1
            except CosmosHttpResponseError:
                pass

    await asyncio.gather(*[_delete_one(item) for item in items])
    return deleted


async def _bulk_upsert(container, docs: list[dict], container_name: str) -> tuple[int, int]:
    """Upsert documents concurrently with semaphore-controlled parallelism.

    Returns (loaded_count, error_count).
    """
    sem = asyncio.Semaphore(CONCURRENCY)
    loaded = 0
    errors = 0
    total = len(docs)

    async def _upsert_one(doc: dict):
        nonlocal loaded, errors
        async with sem:
            try:
                await container.upsert_item(body=doc)
                loaded += 1
            except CosmosHttpResponseError as e:
                errors += 1
                if errors <= 3:
                    print(f"    ✗ {e.message[:200]}")

    # Process in batches to show progress
    BATCH = 500
    for i in range(0, total, BATCH):
        batch = docs[i : i + BATCH]
        await asyncio.gather(*[_upsert_one(d) for d in batch])
        done = min(i + BATCH, total)
        print(f"    ... {done}/{total} ({done * 100 // total}%)")

    return loaded, errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> None:
    print("=" * 72)
    print("  Cosmos DB NoSQL — Bulk Loader (async)")
    print("=" * 72)

    if not ENDPOINT:
        print("\n  ✗ COSMOS_NOSQL_ENDPOINT is not set.")
        print("    Set it in azure_config.env or export it before running.")
        sys.exit(1)

    from_blob = args.from_blob
    if from_blob and not STORAGE_ACCOUNT:
        print("\n  ✗ --from-blob requires STORAGE_ACCOUNT_NAME to be set.")
        sys.exit(1)

    source_label = f"blob ({STORAGE_ACCOUNT}/{BLOB_CONTAINER})" if from_blob else str(DATA_DIR)
    print(f"\n  Endpoint:    {ENDPOINT}")
    print(f"  Database:    {DATABASE}")
    print(f"  Data source: {source_label}")
    print(f"  Concurrency: {CONCURRENCY} parallel upserts")

    credential = DefaultAzureCredential()

    async with CosmosClient(url=ENDPOINT, credential=credential) as client:

        # Ensure database exists
        print(f"\n[1/3] Ensuring database '{DATABASE}' exists...")
        try:
            database = await client.create_database_if_not_exists(id=DATABASE)
            print(f"  ✓ Database: {DATABASE}")
        except CosmosHttpResponseError as e:
            print(f"  ✗ Failed to access database: {e.message}")
            sys.exit(1)

        # Load each container
        print(f"\n[2/3] Loading data...")
        total_docs = 0
        t_all = time.time()

        for container_name, config in CONTAINERS.items():
            print(f"\n  ── {container_name} ──")

            # Ensure container exists
            try:
                container = await database.create_container_if_not_exists(
                    id=container_name,
                    partition_key=PartitionKey(path=config["partition_key"]),
                )
                print(f"  ✓ Container: {container_name} (pk: {config['partition_key']})")
            except CosmosHttpResponseError as e:
                print(f"  ✗ Failed to create container: {e.message}")
                continue

            # Clear existing data
            if not args.no_clear:
                print("  Clearing existing data...")
                deleted = await _clear_container(container)
                if deleted:
                    print(f"  Deleted {deleted} existing documents")

            # Load CSV data
            if from_blob:
                print(f"  Reading {config['csv_file']} from blob storage...")
                rows = await _load_csv_blob(credential, config["csv_file"])
            else:
                csv_path = DATA_DIR / config["csv_file"]
                rows = _load_csv_local(csv_path)

            if not rows:
                print(f"  ✗ No data to load for {container_name}")
                continue

            # Coerce rows to Cosmos DB documents
            docs = [
                _coerce_row(row, config["numeric_fields"], config["id_field"])
                for row in rows
            ]

            print(f"  Bulk-upserting {len(docs)} documents ({CONCURRENCY} concurrent)...")
            t0 = time.time()
            loaded, errors = await _bulk_upsert(container, docs, container_name)
            elapsed = time.time() - t0
            total_docs += loaded

            rate = loaded / elapsed if elapsed > 0 else 0
            print(f"  ✓ {loaded}/{len(docs)} loaded in {elapsed:.1f}s ({rate:.0f} docs/s)")
            if errors:
                print(f"    ({errors} errors)")

        total_elapsed = time.time() - t_all

        # Summary
        print(f"\n[3/3] Summary")
        print("=" * 72)
        print(f"  ✅ {total_docs} total documents loaded in {total_elapsed:.1f}s")
        print("=" * 72)
        print()

    # Close credential
    await credential.close()


def main():
    parser = argparse.ArgumentParser(
        description="Bulk-load CSV data into Cosmos DB NoSQL (async)",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Don't clear containers before loading",
    )
    parser.add_argument(
        "--from-blob",
        action="store_true",
        help=(
            "Read CSVs from Azure Blob Storage instead of local files. "
            "Requires STORAGE_ACCOUNT_NAME and data uploaded to 'telemetry-data' container."
        ),
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
