#!/usr/bin/env python3
"""
Provision Cosmos DB Gremlin graph — generic, manifest-driven data loader.

Reads a YAML graph schema manifest (vertices + edges) and loads CSV data
into an Azure Cosmos DB for Apache Gremlin graph.

Usage:
    # Default manifest (data/graph_schema.yaml)
    source azure_config.env
    uv run python scripts/cosmos/provision_cosmos_gremlin.py

    # Custom manifest
    uv run python scripts/cosmos/provision_cosmos_gremlin.py --schema path/to/schema.yaml

    # Skip verification
    uv run python scripts/cosmos/provision_cosmos_gremlin.py --no-verify

    # Keep existing data (don't drop graph first)
    uv run python scripts/cosmos/provision_cosmos_gremlin.py --no-clear

Requires: gremlinpython>=3.7.0, pyyaml
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import yaml
from gremlin_python.driver import client, serializer
from gremlin_python.driver.protocol import GremlinServerError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SCHEMA = PROJECT_ROOT / "data" / "graph_schema.yaml"

ENDPOINT = os.environ.get("COSMOS_GREMLIN_ENDPOINT", "")
PRIMARY_KEY = os.environ.get("COSMOS_GREMLIN_PRIMARY_KEY", "")
DATABASE = os.environ.get("COSMOS_GREMLIN_DATABASE", "networkgraph")
GRAPH = os.environ.get("COSMOS_GREMLIN_GRAPH", "topology")


# ---------------------------------------------------------------------------
# Gremlin client helpers
# ---------------------------------------------------------------------------


def get_client() -> client.Client:
    """Create a Gremlin client with key-based auth over WSS."""
    if not ENDPOINT or not PRIMARY_KEY:
        print("ERROR: Set COSMOS_GREMLIN_ENDPOINT and COSMOS_GREMLIN_PRIMARY_KEY")
        sys.exit(1)
    return client.Client(
        url=f"wss://{ENDPOINT}:443/",
        traversal_source="g",
        username=f"/dbs/{DATABASE}/colls/{GRAPH}",
        password=PRIMARY_KEY,
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )


def submit(
    c: client.Client,
    query: str,
    bindings: dict | None = None,
    retries: int = 3,
):
    """Submit a Gremlin query with exponential-backoff retry on 429/408."""
    for attempt in range(1, retries + 1):
        try:
            return c.submit(message=query, bindings=bindings or {}).all().result()
        except GremlinServerError as e:
            status = getattr(e, "status_code", 0)
            if status in (429, 408) and attempt < retries:
                wait = 2**attempt
                print(f"    \u23f3 {status} — retrying in {wait}s (attempt {attempt}/{retries})")
                time.sleep(wait)
                continue
            raise


def read_csv_file(path: Path) -> list[dict]:
    """Read a CSV file and return a list of dicts (one per row)."""
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------


def load_schema(schema_path: Path) -> dict:
    """Load and validate a YAML graph schema manifest."""
    if not schema_path.exists():
        print(f"ERROR: Schema file not found: {schema_path}")
        sys.exit(1)

    with open(schema_path) as f:
        schema = yaml.safe_load(f)

    # Basic validation
    if not isinstance(schema.get("vertices"), list) or not schema["vertices"]:
        print("ERROR: Schema must have a non-empty 'vertices' list")
        sys.exit(1)

    if "data_dir" not in schema:
        print("ERROR: Schema must specify 'data_dir'")
        sys.exit(1)

    return schema


# ---------------------------------------------------------------------------
# Generic vertex loader
# ---------------------------------------------------------------------------


def load_vertices(c: client.Client, vertex_def: dict, data_dir: Path) -> int:
    """Load vertices from a CSV file according to the vertex definition.

    Returns the number of vertices loaded.
    """
    label = vertex_def["label"]
    csv_file = data_dir / vertex_def["csv_file"]
    id_column = vertex_def["id_column"]
    pk_value = vertex_def["partition_key"]
    properties = vertex_def.get("properties", [])

    if not csv_file.exists():
        print(f"  \u26a0 CSV not found: {csv_file} — skipping {label}")
        return 0

    rows = read_csv_file(csv_file)
    print(f"Loading {label} ({len(rows)} rows from {vertex_def['csv_file']})...")

    for row in rows:
        vertex_id = row[id_column]

        # Build property chain dynamically
        prop_parts = [
            ".property('id', id_val)",
            ".property('partitionKey', pk_val)",
        ]
        bindings: dict = {"label_val": label, "id_val": vertex_id, "pk_val": pk_value}

        for i, prop_name in enumerate(properties):
            if prop_name in row:
                param = f"p{i}"
                prop_parts.append(f".property('{prop_name}', {param})")
                bindings[param] = row[prop_name]

        query = "g.addV(label_val)" + "".join(prop_parts)
        submit(c, query, bindings)
        print(f"  \u2713 {label} {vertex_id}")

    return len(rows)


# ---------------------------------------------------------------------------
# Generic edge loader
# ---------------------------------------------------------------------------


def load_edges(c: client.Client, edge_def: dict, data_dir: Path) -> int:
    """Load edges from a CSV file according to the edge definition.

    Returns the number of edges loaded.
    """
    label = edge_def["label"]
    csv_file = data_dir / edge_def["csv_file"]
    source = edge_def["source"]
    target = edge_def["target"]
    edge_props = edge_def.get("properties", [])
    row_filter = edge_def.get("filter")

    if not csv_file.exists():
        print(f"  \u26a0 CSV not found: {csv_file} — skipping {label}")
        return 0

    rows = read_csv_file(csv_file)

    # Apply row filter if specified
    if row_filter:
        filter_col = row_filter["column"]
        filter_val = row_filter["value"]
        rows = [r for r in rows if r.get(filter_col) == filter_val]
        print(f"Loading {label} edges ({len(rows)} filtered rows from {edge_def['csv_file']})...")
    else:
        print(f"Loading {label} edges ({len(rows)} rows from {edge_def['csv_file']})...")

    count = 0
    for row in rows:
        src_val = row[source["column"]]
        tgt_val = row[target["column"]]

        # Build parameterised edge query
        bindings: dict = {
            "src_val": src_val,
            "tgt_val": tgt_val,
        }

        query = (
            f"g.V().has('{source['label']}', '{source['property']}', src_val)"
            f".addE('{label}')"
            f".to(g.V().has('{target['label']}', '{target['property']}', tgt_val))"
        )

        # Add edge properties
        for i, prop in enumerate(edge_props):
            param = f"ep{i}"
            if "column" in prop:
                bindings[param] = row[prop["column"]]
            elif "value" in prop:
                bindings[param] = prop["value"]
            else:
                continue
            query += f".property('{prop['name']}', {param})"

        submit(c, query, bindings)
        print(f"  \u2713 {src_val} —[{label}]\u2192 {tgt_val}")
        count += 1

    return count


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(c: client.Client) -> None:
    """Print vertex/edge counts and a sample traversal."""
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    vertex_counts = submit(c, "g.V().groupCount().by(label)")
    print(f"  Vertices by label: {vertex_counts}")

    edge_counts = submit(c, "g.E().groupCount().by(label)")
    print(f"  Edges by label:    {edge_counts}")

    total_v = submit(c, "g.V().count()")
    total_e = submit(c, "g.E().count()")
    print(f"  Total: {total_v[0]} vertices, {total_e[0]} edges")

    # Orphan check: vertices with no edges at all
    orphans = submit(c, "g.V().not(__.bothE()).project('label','id').by(label).by(id)")
    if orphans:
        print(f"  \u26a0 Orphan vertices (no edges): {orphans}")
    else:
        print("  \u2713 All vertices have at least one edge")

    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Load CSV data into Cosmos DB Gremlin graph from a YAML schema manifest.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help=f"Path to graph schema YAML (default: {DEFAULT_SCHEMA.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-load verification queries",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Don't drop existing graph data before loading",
    )
    args = parser.parse_args()

    # Load schema
    schema_path = args.schema if args.schema.is_absolute() else PROJECT_ROOT / args.schema
    schema = load_schema(schema_path)
    data_dir = PROJECT_ROOT / schema["data_dir"]

    print(f"Cosmos DB Gremlin: {ENDPOINT} / {DATABASE} / {GRAPH}")
    print(f"Schema: {schema_path.relative_to(PROJECT_ROOT)}")
    print(f"Data dir: {data_dir}")
    print(f"Vertices: {len(schema['vertices'])} types")
    print(f"Edges: {len(schema.get('edges', []))} definitions")
    print()

    c = get_client()

    try:
        # 1. Clear existing data (unless --no-clear)
        if not args.no_clear:
            print("Clearing existing graph data...")
            submit(c, "g.V().drop()")
            print("  \u2713 Graph cleared\n")

        # 2. Load all vertices
        t0 = time.time()
        total_vertices = 0
        for vertex_def in schema["vertices"]:
            total_vertices += load_vertices(c, vertex_def, data_dir)
        vertex_time = time.time() - t0
        print(f"\n  {total_vertices} vertices loaded in {vertex_time:.1f}s\n")

        # 3. Load all edges
        t1 = time.time()
        total_edges = 0
        for edge_def in schema.get("edges", []):
            total_edges += load_edges(c, edge_def, data_dir)
        edge_time = time.time() - t1
        print(f"\n  {total_edges} edges loaded in {edge_time:.1f}s\n")

        # 4. Verify
        if not args.no_verify:
            verify(c)

        total = time.time() - t0
        print(f"\nDone — {total_vertices} vertices, {total_edges} edges in {total:.1f}s")

    finally:
        c.close()


if __name__ == "__main__":
    main()
