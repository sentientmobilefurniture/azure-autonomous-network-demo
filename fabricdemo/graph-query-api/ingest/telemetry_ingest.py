"""Telemetry data upload endpoint — Fabric Eventhouse (stub).

Telemetry ingest to Cosmos NoSQL has been removed. Upload telemetry data
via the Fabric Lakehouse pipeline or implement Eventhouse streaming ingest.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Query, UploadFile

from sse_helpers import SSEProgress, sse_upload_response
from .manifest import _validate_upload

logger = logging.getLogger("graph-query-api.ingest")

router = APIRouter()


@router.post("/upload/telemetry", summary="Upload telemetry data (Fabric Eventhouse)")
async def upload_telemetry(
    file: UploadFile = File(...),
    scenario_name: str | None = Query(
        default=None, description="Override scenario name from scenario.yaml"
    ),
):
    """Upload telemetry data. Currently a stub — Cosmos NoSQL ingest has been removed.

    Telemetry data should be ingested via the Fabric Lakehouse pipeline or
    Eventhouse streaming ingestion. This endpoint will be updated to support
    direct Eventhouse ingest in a future release.
    """
    await _validate_upload(file)

    async def work(progress: SSEProgress):
        progress.error(
            "Telemetry ingest requires Fabric Eventhouse — "
            "upload via Lakehouse pipeline. "
            "Direct Eventhouse ingest will be available in a future release."
        )

    return sse_upload_response(work, error_label="telemetry upload")
