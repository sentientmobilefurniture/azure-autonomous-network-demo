"""Manifest normalization, validation, and archive extraction helpers."""

from __future__ import annotations

import csv
import io
import logging
import os
import tarfile
from pathlib import Path

import yaml
from fastapi import HTTPException, UploadFile

logger = logging.getLogger("graph-query-api.ingest")


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Manifest normalization (backward compat: v1.0 → v2.0 schema)
# ---------------------------------------------------------------------------


def _normalize_manifest(manifest: dict) -> dict:
    """Normalize old-format manifest to the v2.0 data_sources format.

    Supports both old (cosmos: / search_indexes:) and new (data_sources:)
    formats. If data_sources already exists, returns as-is.
    """
    if "data_sources" in manifest:
        return manifest  # already new format

    ds: dict = {}
    cosmos = manifest.get("cosmos", {})
    sc_name = manifest.get("name", "")

    if cosmos.get("gremlin"):
        gremlin_cfg = cosmos["gremlin"]
        graph_name = gremlin_cfg.get("graph", "topology")
        # Old format used unprefixed names — add scenario prefix
        if sc_name and not graph_name.startswith(sc_name):
            graph_name = f"{sc_name}-{graph_name}"
        ds["graph"] = {
            "connector": "cosmosdb-gremlin",
            "config": {
                "database": gremlin_cfg.get("database", "networkgraph"),
                "graph": graph_name,
                "partition_key": "/partitionKey",
            },
            "schema_file": "graph_schema.yaml",
        }

    if cosmos.get("nosql"):
        nosql_cfg = cosmos["nosql"]
        ds["telemetry"] = {
            "connector": "cosmosdb-nosql",
            "config": {
                "database": nosql_cfg.get("database", "telemetry"),
                "container_prefix": sc_name,
                "containers": nosql_cfg.get("containers", []),
            },
        }

    old_indexes = manifest.get("search_indexes", [])
    if old_indexes:
        si: dict = {}
        for idx in old_indexes:
            key = idx.get("container", idx["name"].split("-")[0])
            si[key] = {
                "index_name": f"{sc_name}-{idx['name']}" if sc_name and not idx["name"].startswith(sc_name) else idx["name"],
                "source": idx.get("source", ""),
                "blob_container": idx.get("container", key),
            }
        ds["search_indexes"] = si

    manifest["data_sources"] = ds
    return manifest


def _rewrite_manifest_prefix(manifest: dict, new_name: str) -> dict:
    """Rewrite all resource names in the manifest to use *new_name*.

    Called when the user overrides the scenario name so that graph, telemetry,
    and search resources all share a consistent prefix.
    """
    old_name = manifest.get("name", "")
    manifest["name"] = new_name

    ds = manifest.get("data_sources", {})

    # ── graph ──
    graph_cfg = ds.get("graph", {}).get("config", {})
    old_graph = graph_cfg.get("graph", "")
    if old_graph:
        if old_name and old_graph.startswith(old_name):
            graph_cfg["graph"] = f"{new_name}{old_graph[len(old_name):]}"
        else:
            graph_cfg["graph"] = f"{new_name}-topology"

    # ── telemetry ──
    tel_cfg = ds.get("telemetry", {}).get("config", {})
    if "container_prefix" in tel_cfg:
        tel_cfg["container_prefix"] = new_name

    # ── search indexes ──
    for _key, idx_cfg in ds.get("search_indexes", {}).items():
        old_idx = idx_cfg.get("index_name", "")
        if old_name and old_idx.startswith(old_name):
            idx_cfg["index_name"] = f"{new_name}{old_idx[len(old_name):]}"

    return manifest


# ---------------------------------------------------------------------------
# Archive extraction
# ---------------------------------------------------------------------------


def _extract_tar(content: bytes, tmppath: Path) -> Path:
    """Extract a tar.gz and return the scenario root directory."""
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
        tar.extractall(tmppath, filter="data")
    # Find scenario root (may be one level down)
    scenario_dir = tmppath
    if not (scenario_dir / "scenario.yaml").exists():
        for sd in tmppath.iterdir():
            if sd.is_dir() and (sd / "scenario.yaml").exists():
                return sd
    return scenario_dir


def _resolve_scenario_name(
    tmppath: Path, override: str | None, fallback: str = "default",
) -> str:
    """Resolve scenario name from scenario.yaml, ignoring override.

    The override parameter is accepted for API compatibility but is ignored.
    Name always comes from scenario.yaml embedded in the tarball.
    """
    for root, _dirs, files in os.walk(tmppath):
        if "scenario.yaml" in files:
            m = yaml.safe_load(Path(root, "scenario.yaml").read_text())
            return m.get("name", fallback)
    return fallback


async def _validate_upload(file: UploadFile) -> bytes:
    """Validate tarball filename and read content. Raises HTTPException on invalid."""
    if not file.filename or not (
        file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")
    ):
        raise HTTPException(400, "File must be a .tar.gz archive")
    content = await file.read()
    logger.info("Received %s (%d bytes)", file.filename, len(content))
    return content
