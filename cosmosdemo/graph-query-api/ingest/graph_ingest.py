"""Graph data upload endpoint + CSV→vertex/edge helpers."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, File, Query, UploadFile

from adapters.cosmos_config import COSMOS_GREMLIN_DATABASE
from sse_helpers import SSEProgress, sse_upload_response

from .manifest import _extract_tar, _normalize_manifest, _read_csv, _validate_upload

logger = logging.getLogger("graph-query-api.ingest")

router = APIRouter()


# ---------------------------------------------------------------------------
# Schema → vertex / edge helpers
# ---------------------------------------------------------------------------


def _prepare_vertices_from_schema(schema: dict, data_dir: Path) -> list[dict]:
    """Convert graph_schema.yaml vertex definitions + CSV data → flat dicts."""
    vertices = []
    for vdef in schema.get("vertices", []):
        csv_path = data_dir / vdef["csv_file"]
        if not csv_path.exists():
            continue
        rows = _read_csv(csv_path)
        for row in rows:
            props = {}
            for p in vdef.get("properties", []):
                if p in row:
                    props[p] = row[p]
            vertices.append({
                "label": vdef["label"],
                "id": row[vdef["id_column"]],
                "partition_key": vdef["partition_key"],
                "properties": props,
            })
    return vertices


def _prepare_edges_from_schema(schema: dict, data_dir: Path) -> list[dict]:
    """Convert graph_schema.yaml edge definitions + CSV data → flat dicts."""
    edges = []
    for edef in schema.get("edges", []):
        csv_path = data_dir / edef["csv_file"]
        if not csv_path.exists():
            continue
        rows = _read_csv(csv_path)
        # Apply optional filter
        rf = edef.get("filter")
        if rf:
            negate = rf.get("negate", False)
            rows = [
                r for r in rows
                if (r.get(rf["column"]) != rf["value"]) == negate
            ]
        src, tgt = edef["source"], edef["target"]
        for row in rows:
            props = {}
            for ep in edef.get("properties", []):
                if "column" in ep:
                    props[ep["name"]] = row[ep["column"]]
                elif "value" in ep:
                    props[ep["name"]] = ep["value"]
            edges.append({
                "label": edef["label"],
                "source": {
                    "label": src["label"],
                    "property": src["property"],
                    "value": row[src["column"]],
                },
                "target": {
                    "label": tgt["label"],
                    "property": tgt["property"],
                    "value": row[tgt["column"]],
                },
                "properties": props,
            })
    return edges


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/upload/graph", summary="Upload graph data only")
async def upload_graph(
    file: UploadFile = File(...),
    scenario_name: str | None = Query(
        default=None, description="Override scenario name from scenario.yaml"
    ),
):
    """Upload a tarball containing scenario.yaml + graph_schema.yaml + data/entities/*.csv.
    Loads vertices and edges into Cosmos Gremlin. Returns SSE progress.
    If scenario_name is provided, it overrides the name from scenario.yaml."""
    content = await _validate_upload(file)

    async def work(progress: SSEProgress):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            scenario_dir = _extract_tar(content, tmppath)

            manifest = yaml.safe_load((scenario_dir / "scenario.yaml").read_text())
            manifest = _normalize_manifest(manifest)
            sc_name = manifest["name"]

            schema = yaml.safe_load((scenario_dir / "graph_schema.yaml").read_text())
            sc_name = manifest["name"]

            # scenario_name parameter is accepted for API compat but ignored
            if scenario_name and scenario_name != manifest.get("name"):
                logger.info(
                    "Ignoring scenario_name override '%s' — using manifest name '%s'",
                    scenario_name, sc_name,
                )

            # Persist full config if agents section present (Phase 8)
            if "agents" in manifest:
                from config_store import save_scenario_config
                await save_scenario_config(sc_name, manifest)
                progress.emit("config", f"Saved scenario config for '{sc_name}'", 12)

            # Extract metadata for frontend passthrough
            scenario_metadata = {
                "display_name": manifest.get("display_name"),
                "description": manifest.get("description"),
                "use_cases": manifest.get("use_cases"),
                "example_questions": manifest.get("example_questions"),
                "graph_styles": manifest.get("graph_styles"),
                "domain": manifest.get("domain"),
            }

            graph_cfg = manifest.get("data_sources", {}).get("graph", {}).get("config", {})
            gremlin_graph = graph_cfg.get("graph", f"{sc_name}-topology")
            data_dir = scenario_dir / schema.get("data_dir", "data/entities")

            progress.emit("graph", "Preparing graph data from schema...", 15)

            # Transform schema + CSV → generic dicts
            vertices = _prepare_vertices_from_schema(schema, data_dir)
            edges = _prepare_edges_from_schema(schema, data_dir)

            progress.emit(
                "graph",
                f"Prepared {len(vertices)} vertices, {len(edges)} edges",
                20,
            )

            # Use GraphBackend.ingest() instead of raw Gremlin calls
            from backends import get_backend_for_graph

            backend = get_backend_for_graph(gremlin_graph)

            def progress_adapter(message: str, current: int, total: int):
                pct = 20 + int(current / max(total, 1) * 75)
                progress.emit("graph", message, pct)

            try:
                result = await backend.ingest(
                    vertices, edges,
                    graph_name=gremlin_graph,
                    graph_database=COSMOS_GREMLIN_DATABASE,
                    on_progress=progress_adapter,
                )
            except NotImplementedError:
                raise ValueError(
                    "This backend does not support direct graph ingest. "
                    "Use the provisioning pipeline instead."
                )

            total_v = result["vertices_loaded"]
            total_e = result["edges_loaded"]
            progress.emit(
                "done",
                f"Graph loaded: {total_v} vertices, {total_e} edges → {gremlin_graph}",
                100,
            )
            # Invalidate topology cache for this graph
            from router_topology import invalidate_topology_cache
            invalidate_topology_cache(gremlin_graph)

            progress.complete({
                "scenario": sc_name,
                "graph": gremlin_graph,
                "vertices": total_v,
                "edges": total_e,
                "errors": result.get("errors", []),
                "scenario_metadata": scenario_metadata,
            })

    return sse_upload_response(work, error_label="graph upload")
