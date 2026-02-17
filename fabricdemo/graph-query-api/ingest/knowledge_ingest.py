"""Knowledge-file upload endpoints: runbooks (.md) and tickets (.txt)."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile

from sse_helpers import SSEProgress, sse_upload_response

from .manifest import _extract_tar, _resolve_scenario_name, _validate_upload

logger = logging.getLogger("graph-query-api.ingest")

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared knowledge-file upload logic (runbooks + tickets)
# ---------------------------------------------------------------------------


async def _upload_knowledge_files(
    content: bytes,
    scenario_default: str,
    scenario_override: str | None,
    file_ext: str,
    type_label: str,
    progress: SSEProgress,
) -> None:
    """Shared logic for runbooks (.md) and tickets (.txt) upload to blob + AI Search."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        _extract_tar(content, tmppath)  # reuse shared extraction

        sc_name = _resolve_scenario_name(tmppath, scenario_override, scenario_default)

        matched_files = list(tmppath.rglob(f"*{file_ext}"))
        if not matched_files:
            progress.error(f"No {file_ext} files found in archive")
            return

        progress.emit(type_label, f"Found {len(matched_files)} {type_label} files", 10)

        storage_account = os.getenv("STORAGE_ACCOUNT_NAME", "")
        ai_search = os.getenv("AI_SEARCH_NAME", "")
        if not storage_account:
            progress.error("STORAGE_ACCOUNT_NAME not configured")
            return

        container_name = f"{sc_name}-{type_label}"
        index_name = f"{sc_name}-{type_label}-index"

        def _upload_and_index():
            from services.blob_uploader import upload_files_to_blob

            upload_files_to_blob(
                container_name,
                matched_files,
                on_progress=lambda msg: progress.emit(type_label, msg, 50),
            )

            if ai_search:
                progress.emit(type_label, f"Creating search index '{index_name}'...", 60)
                from search_indexer import create_search_index

                result = create_search_index(
                    index_name=index_name,
                    container_name=container_name,
                    on_progress=lambda msg: progress.emit(type_label, msg, 80),
                )
                return result
            return {"index_name": index_name, "status": "blob_only"}

        result = await asyncio.to_thread(_upload_and_index)
        progress.emit("done", f"{type_label.title()} indexed: {index_name}", 100)
        progress.complete({"scenario": sc_name, "index": index_name, **result})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload/runbooks", summary="Upload runbooks only")
async def upload_runbooks(
    file: UploadFile = File(...),
    scenario: str = "default",
    scenario_name: str | None = Query(
        default=None,
        description="Override scenario name (takes priority over scenario.yaml and scenario param)",
    ),
):
    """Upload a tarball of .md runbook files. Uploads to blob + creates AI Search index.
    If scenario_name is provided, it overrides both the scenario param and scenario.yaml."""
    content = await _validate_upload(file)

    async def work(progress: SSEProgress):
        await _upload_knowledge_files(
            content, scenario, scenario_name,
            file_ext=".md", type_label="runbooks", progress=progress,
        )

    return sse_upload_response(work, error_label="runbooks upload")


@router.post("/upload/tickets", summary="Upload tickets only")
async def upload_tickets(
    file: UploadFile = File(...),
    scenario: str = "default",
    scenario_name: str | None = Query(
        default=None,
        description="Override scenario name (takes priority over scenario.yaml and scenario param)",
    ),
):
    """Upload a tarball of .txt ticket files. Uploads to blob + creates AI Search index.
    If scenario_name is provided, it overrides both the scenario param and scenario.yaml."""
    content = await _validate_upload(file)

    async def work(progress: SSEProgress):
        await _upload_knowledge_files(
            content, scenario, scenario_name,
            file_ext=".txt", type_label="tickets", progress=progress,
        )

    return sse_upload_response(work, error_label="tickets upload")
