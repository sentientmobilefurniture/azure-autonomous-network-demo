"""
scenario_loader.py — Parse scenario.yaml and return a resolved config dict.

Usage:
    from scenario_loader import load_scenario

    sc = load_scenario()             # uses DEFAULT_SCENARIO env var
    sc = load_scenario("my-scenario")  # explicit name
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_scenario(name: str | None = None) -> dict:
    """Load and validate scenario.yaml, returning a resolved config dict.

    Args:
        name: Scenario folder name. Defaults to DEFAULT_SCENARIO env var.

    Returns:
        Dict with keys:
          name, display_name, description, version, domain,
          scenario_dir (Path), paths (resolved to absolute),
          data_sources, agents, graph_styles, ...

    Raises:
        SystemExit if scenario not found or invalid.
    """
    if name is None:
        name = os.environ.get("DEFAULT_SCENARIO", "")
    if not name:
        print("ERROR: No scenario specified. Set DEFAULT_SCENARIO or pass name explicitly.")
        sys.exit(1)

    scenario_dir = PROJECT_ROOT / "data" / "scenarios" / name
    manifest = scenario_dir / "scenario.yaml"

    if not manifest.exists():
        print(f"ERROR: Scenario manifest not found: {manifest}")
        sys.exit(1)

    with open(manifest) as f:
        cfg = yaml.safe_load(f)

    # Resolve relative paths to absolute
    raw_paths = cfg.get("paths", {})
    resolved_paths = {}
    for key, rel in raw_paths.items():
        resolved_paths[key] = scenario_dir / rel

    cfg["scenario_dir"] = scenario_dir
    cfg["paths"] = resolved_paths

    # Convenience shortcuts for the most common lookups
    ds = cfg.get("data_sources", {})
    graph_cfg = ds.get("graph", {}).get("config", {})
    cfg["graph_name"] = graph_cfg.get("graph", name + "-topology")
    cfg["container_prefix"] = ds.get("telemetry", {}).get("config", {}).get("container_prefix", name)

    search_idx = ds.get("search_indexes", {})
    cfg["runbooks_index_name"] = search_idx.get("runbooks", {}).get("index_name", f"{name}-runbooks-index")
    cfg["tickets_index_name"] = search_idx.get("tickets", {}).get("index_name", f"{name}-tickets-index")
    cfg["runbooks_blob_container"] = search_idx.get("runbooks", {}).get("blob_container", "runbooks")
    cfg["tickets_blob_container"] = search_idx.get("tickets", {}).get("blob_container", "tickets")

    return cfg
