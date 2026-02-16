"""Telemetry data upload endpoint (Cosmos NoSQL)."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, File, Query, UploadFile

from adapters.cosmos_config import COSMOS_NOSQL_ENDPOINT
from cosmos_helpers import get_cosmos_client
from sse_helpers import SSEProgress, sse_upload_response

from .arm_helpers import _ensure_nosql_containers
from .manifest import _extract_tar, _normalize_manifest, _read_csv, _validate_upload

logger = logging.getLogger("graph-query-api.ingest")

router = APIRouter()


@router.post("/upload/telemetry", summary="Upload telemetry data only")
async def upload_telemetry(
    file: UploadFile = File(...),
    scenario_name: str | None = Query(
        default=None, description="Override scenario name from scenario.yaml"
    ),
):
    """Upload a tarball containing scenario.yaml + data/telemetry/*.csv.
    Loads into Cosmos NoSQL. Runs entirely in a background thread.
    If scenario_name is provided, it overrides the name from scenario.yaml."""
    content = await _validate_upload(file)

    async def work(progress: SSEProgress):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            scenario_dir = _extract_tar(content, tmppath)

            manifest = yaml.safe_load((scenario_dir / "scenario.yaml").read_text())
            manifest = _normalize_manifest(manifest)
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

            telemetry_cfg = manifest.get("data_sources", {}).get("telemetry", {}).get("config", {})

            nosql_db = telemetry_cfg.get("database", "telemetry")
            containers_config = telemetry_cfg.get("containers", [])
            telemetry_dir = scenario_dir / manifest.get(
                "paths", {},
            ).get("telemetry", "data/telemetry")

            if not COSMOS_NOSQL_ENDPOINT:
                progress.error("COSMOS_NOSQL_ENDPOINT not configured")
                return

            progress.emit(
                "telemetry",
                f"Loading into shared database '{nosql_db}' (scenario prefix '{sc_name}')...",
                10,
            )

            for cdef in containers_config:
                cdef["original_name"] = cdef["name"]
                cdef["name"] = f"{sc_name}-{cdef['name']}"

            await asyncio.to_thread(
                _ensure_nosql_containers, nosql_db, containers_config, progress.emit,
            )

            def _load():
                cosmos = get_cosmos_client()
                db = cosmos.get_database_client(nosql_db)
                for ci, cdef in enumerate(containers_config):
                    cname = cdef["name"]
                    original_name = cdef.get("original_name", cname)
                    csv_file = cdef.get("csv_file", f"{original_name}.csv")
                    csv_path = telemetry_dir / csv_file
                    if not csv_path.exists():
                        progress.emit("telemetry", f"⚠ {csv_file} not found — skipping", 20)
                        continue
                    pct = 20 + int(70 * ci / max(len(containers_config), 1))
                    progress.emit("telemetry", f"Loading {cname}...", pct)
                    container = db.get_container_client(cname)
                    rows = _read_csv(csv_path)
                    progress.emit("telemetry", f"Upserting {len(rows)} docs into {cname}...", pct + 10)
                    for row in rows:
                        for nf in cdef.get("numeric_fields", []):
                            if nf in row and row[nf]:
                                try:
                                    row[nf] = float(row[nf])
                                except (ValueError, TypeError):
                                    pass
                        id_field = cdef.get("id_field")
                        if id_field and id_field in row:
                            row["id"] = row[id_field]
                        elif "id" not in row:
                            keys = list(row.keys())
                            row["id"] = f"{row.get(keys[0], '')}-{row.get(keys[1], '')}"
                        container.upsert_item(row)
                    progress.emit("telemetry", f"✓ {cname}: {len(rows)} docs", pct + 20)
                return len(containers_config)

            count = await asyncio.to_thread(_load)
            progress.emit("done", f"Telemetry loaded: {count} containers → {nosql_db}", 100)
            progress.complete({
                "scenario": sc_name, "database": nosql_db, "containers": count,
            })

    return sse_upload_response(work, error_label="telemetry upload")
