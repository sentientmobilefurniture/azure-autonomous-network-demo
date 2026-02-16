"""
Router: Background upload jobs.

Accepts scenario tarballs, processes them in a background asyncio task,
and persists job status to Cosmos via graph-query-api proxy calls.

Jobs survive modal close and browser refresh — the frontend polls for status.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

logger = logging.getLogger("app.upload-jobs")

router = APIRouter(prefix="/api/upload-jobs", tags=["upload-jobs"])

# In-memory job store (will be moved to Cosmos via graph-query-api proxy later)
_jobs: dict[str, dict[str, Any]] = {}
_tasks: dict[str, asyncio.Task] = {}

GRAPH_QUERY_API = os.getenv("GRAPH_QUERY_API_URL", "http://127.0.0.1:8100")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_job(scenario_name: str, step_names: list[str]) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "scenario_name": scenario_name,
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now(),
        "overall_pct": 0,
        "error": None,
        "steps": [
            {"name": name, "status": "pending", "detail": "", "pct": 0}
            for name in step_names
        ],
    }


def _update_step(job: dict, step_name: str, status: str, detail: str = "", pct: int = 0):
    for step in job["steps"]:
        if step["name"] == step_name:
            step["status"] = status
            step["detail"] = detail
            step["pct"] = pct
            break
    # Recalculate overall
    done = sum(1 for s in job["steps"] if s["status"] == "done")
    total = len(job["steps"])
    job["overall_pct"] = int(done / total * 100) if total else 0
    job["updated_at"] = _now()
    if all(s["status"] == "done" for s in job["steps"]):
        job["status"] = "done"
    elif any(s["status"] == "error" for s in job["steps"]):
        job["status"] = "error"


# ---------------------------------------------------------------------------
# Background task: process upload steps
# ---------------------------------------------------------------------------

async def _run_upload_job(job_id: str, files: dict[str, Path]):
    """Process upload steps sequentially."""
    job = _jobs.get(job_id)
    if not job:
        return

    job["status"] = "running"
    scenario_name = job["scenario_name"]

    async with httpx.AsyncClient(timeout=300) as client:
        for step in job["steps"]:
            step_name = step["name"]
            file_path = files.get(step_name)

            if not file_path or not file_path.exists():
                _update_step(job, step_name, "error", "File not found")
                continue

            _update_step(job, step_name, "running", "Uploading…")

            try:
                # Determine endpoint
                if step_name == "graph":
                    endpoint = f"{GRAPH_QUERY_API}/query/upload/graph"
                elif step_name == "telemetry":
                    endpoint = f"{GRAPH_QUERY_API}/query/upload/telemetry"
                elif step_name == "runbooks":
                    endpoint = f"{GRAPH_QUERY_API}/query/upload/runbooks"
                elif step_name == "tickets":
                    endpoint = f"{GRAPH_QUERY_API}/query/upload/tickets"
                elif step_name == "prompts":
                    endpoint = f"{GRAPH_QUERY_API}/query/upload/prompts"
                else:
                    _update_step(job, step_name, "error", f"Unknown step: {step_name}")
                    continue

                # Upload file
                with open(file_path, "rb") as f:
                    resp = await client.post(
                        endpoint,
                        files={"file": (file_path.name, f, "application/gzip")},
                        params={"scenario_name": scenario_name},
                    )

                if resp.status_code == 200:
                    # Parse SSE response for final result
                    detail = "Done"
                    for line in resp.text.split("\n"):
                        if line.startswith("data: ") and '"error"' not in line:
                            try:
                                data = json.loads(line[6:])
                                if "graph" in data or "index" in data or "prompts_stored" in data:
                                    detail = json.dumps(data)[:100]
                            except Exception:
                                pass
                    _update_step(job, step_name, "done", detail, 100)
                else:
                    error_text = resp.text[:200]
                    _update_step(job, step_name, "error", f"HTTP {resp.status_code}: {error_text}")
                    job["error"] = f"{step_name}: HTTP {resp.status_code}"

            except Exception as e:
                logger.exception("Upload step %s failed", step_name)
                _update_step(job, step_name, "error", str(e)[:200])
                job["error"] = f"{step_name}: {e}"

    # Final status
    if job["status"] == "running":
        if all(s["status"] == "done" for s in job["steps"]):
            job["status"] = "done"
            job["overall_pct"] = 100
        else:
            job["status"] = "error"
    job["updated_at"] = _now()

    # Cleanup temp files
    for f in files.values():
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def create_upload_job(
    scenario_name: str = Form(...),
    graph: UploadFile | None = File(None),
    telemetry: UploadFile | None = File(None),
    runbooks: UploadFile | None = File(None),
    tickets: UploadFile | None = File(None),
    prompts: UploadFile | None = File(None),
):
    """Create a background upload job. Returns job ID immediately."""
    # Save uploaded files to temp
    temp_dir = Path(tempfile.mkdtemp(prefix="upload-job-"))
    files: dict[str, Path] = {}
    step_names: list[str] = []

    for name, upload in [
        ("graph", graph), ("telemetry", telemetry),
        ("runbooks", runbooks), ("tickets", tickets), ("prompts", prompts),
    ]:
        if upload and upload.filename:
            dest = temp_dir / f"{name}.tar.gz"
            content = await upload.read()
            dest.write_bytes(content)
            files[name] = dest
            step_names.append(name)

    if not step_names:
        raise HTTPException(400, "No files provided")

    job = _make_job(scenario_name, step_names)
    _jobs[job["id"]] = job

    # Start background task
    task = asyncio.create_task(_run_upload_job(job["id"], files))
    _tasks[job["id"]] = task

    return {"job_id": job["id"]}


@router.get("")
async def list_jobs():
    """List all upload jobs."""
    jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return {"jobs": jobs}


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Get full job detail."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """Remove a completed/failed job."""
    if job_id in _jobs:
        del _jobs[job_id]
    if job_id in _tasks:
        task = _tasks.pop(job_id)
        if not task.done():
            task.cancel()
    return {"deleted": job_id}
