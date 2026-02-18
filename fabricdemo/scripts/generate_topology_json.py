#!/usr/bin/env python3
"""
Generate topology.json from graph_schema.yaml + entity CSVs.

Reads the declarative schema and CSV data, then produces a JSON file
with the exact {topology_nodes, topology_edges} structure that
router_topology.py / MockGraphBackend expects.

Usage:
    python scripts/generate_topology_json.py [--scenario telco-noc] [--output path]

Default output: graph-query-api/backends/fixtures/topology.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import yaml


def load_schema(schema_path: Path) -> dict:
    """Load and return the graph_schema.yaml."""
    with open(schema_path) as f:
        return yaml.safe_load(f)


def load_csv(csv_path: Path) -> list[dict]:
    """Load a CSV file and return rows as list of dicts."""
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def build_nodes(
    schema: dict, data_dir: Path
) -> tuple[list[dict], dict[str, dict]]:
    """Build topology nodes from vertex definitions.

    Returns:
        (nodes_list, nodes_by_id) — nodes_by_id maps node id → node dict
        for fast lookup during edge resolution.
    """
    nodes: list[dict] = []
    nodes_by_id: dict[str, dict] = {}  # id → node

    for vertex in schema["vertices"]:
        label = vertex["label"]
        csv_file = vertex["csv_file"]
        id_column = vertex["id_column"]
        properties = vertex.get("properties", [])

        rows = load_csv(data_dir / csv_file)
        for row in rows:
            node_id = row[id_column]
            props = {col: row[col] for col in properties if col in row}
            node = {
                "id": node_id,
                "label": label,
                "properties": props,
            }
            nodes.append(node)
            # Index by both bare ID and label:ID for flexible lookup
            nodes_by_id[node_id] = node
            nodes_by_id[f"{label}:{node_id}"] = node

    return nodes, nodes_by_id


def build_edges(
    schema: dict, data_dir: Path, nodes_by_id: dict[str, dict]
) -> list[dict]:
    """Build topology edges from edge definitions in the schema."""
    edges: list[dict] = []
    edge_counter: dict[str, int] = {}  # for generating unique IDs

    for edge_def in schema["edges"]:
        label = edge_def["label"]
        csv_file = edge_def["csv_file"]
        source_def = edge_def["source"]
        target_def = edge_def["target"]
        edge_props_defs = edge_def.get("properties", [])
        filter_def = edge_def.get("filter")

        rows = load_csv(data_dir / csv_file)

        for row in rows:
            # Apply filter if defined
            if filter_def:
                filter_col = filter_def["column"]
                filter_val = filter_def["value"]
                if row.get(filter_col) != filter_val:
                    continue

            # Resolve source node
            source_label = source_def["label"]
            source_col = source_def["column"]
            source_id = row.get(source_col)
            if not source_id:
                continue

            # Resolve target node
            target_label = target_def["label"]
            target_col = target_def["column"]
            target_id = row.get(target_col)
            if not target_id:
                continue

            # Verify both nodes exist
            source_node = nodes_by_id.get(source_id) or nodes_by_id.get(
                f"{source_label}:{source_id}"
            )
            target_node = nodes_by_id.get(target_id) or nodes_by_id.get(
                f"{target_label}:{target_id}"
            )

            if not source_node or not target_node:
                print(
                    f"  WARN: Skipping edge {label} — "
                    f"source={source_id} (found={source_node is not None}), "
                    f"target={target_id} (found={target_node is not None})",
                    file=sys.stderr,
                )
                continue

            # Build edge properties
            props: dict = {}
            for prop_def in edge_props_defs:
                name = prop_def["name"]
                if "value" in prop_def:
                    props[name] = prop_def["value"]
                elif "column" in prop_def:
                    props[name] = row.get(prop_def["column"], "")

            # Generate a unique edge ID
            # Format: {label}:{source_id}→{target_id}
            edge_id = f"{label}:{source_node['id']}→{target_node['id']}"
            # Handle duplicate edge IDs (e.g., multiple hops on same path)
            if edge_id in edge_counter:
                edge_counter[edge_id] += 1
                edge_id = f"{edge_id}#{edge_counter[edge_id]}"
            else:
                edge_counter[edge_id] = 0

            edge = {
                "id": edge_id,
                "source": source_node["id"],
                "target": target_node["id"],
                "label": label,
                "properties": props,
            }
            edges.append(edge)

    return edges


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate topology.json from graph schema + CSVs"
    )
    parser.add_argument(
        "--scenario",
        default="telco-noc",
        help="Scenario name (subfolder under data/scenarios/)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: graph-query-api/backends/fixtures/topology.json)",
    )
    args = parser.parse_args()

    # Resolve paths relative to project root
    project_root = Path(__file__).resolve().parent.parent
    scenario_dir = project_root / "data" / "scenarios" / args.scenario
    schema_path = scenario_dir / "graph_schema.yaml"

    if not schema_path.exists():
        print(f"ERROR: Schema not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(
        args.output
        or project_root
        / "graph-query-api"
        / "backends"
        / "fixtures"
        / "topology.json"
    )

    print(f"Schema:   {schema_path}")
    print(f"Output:   {output_path}")

    schema = load_schema(schema_path)
    data_dir = scenario_dir / schema.get("data_dir", "data/entities")

    print(f"Data dir: {data_dir}")
    print()

    # Build nodes
    nodes, nodes_by_id = build_nodes(schema, data_dir)
    labels = sorted({n["label"] for n in nodes})
    label_counts = {l: sum(1 for n in nodes if n["label"] == l) for l in labels}
    print(f"Nodes: {len(nodes)} ({', '.join(f'{l}:{label_counts[l]}' for l in labels)})")

    # Build edges
    edges = build_edges(schema, data_dir, nodes_by_id)
    edge_labels = sorted({e["label"] for e in edges})
    edge_counts = {l: sum(1 for e in edges if e["label"] == l) for l in edge_labels}
    print(f"Edges: {len(edges)} ({', '.join(f'{l}:{edge_counts[l]}' for l in edge_labels)})")

    # Assemble output (same structure as mock_topology.json)
    output = {
        "topology_nodes": nodes,
        "topology_edges": edges,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWritten {output_path} ({output_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
