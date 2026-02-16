"""
Router: Scenario CRUD — save, list, and delete scenario metadata in Cosmos DB.

Scenarios are stored in a dedicated Cosmos NoSQL database: scenarios / scenarios.
Each document tracks the name, display name, description, and resource bindings
for a complete scenario (graph + telemetry + search indexes + prompts).

Endpoints:
  GET    /query/scenarios/saved       — list all saved scenario records
  POST   /query/scenarios/save        — upsert a scenario record
  DELETE /query/scenarios/saved/{name} — delete a scenario record
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from stores import get_document_store, DocumentStore

logger = logging.getLogger("graph-query-api.scenarios")

router = APIRouter(prefix="/query", tags=["scenarios"])

SCENARIOS_DATABASE = "scenarios"
SCENARIOS_CONTAINER = "scenarios"

# Scenario name validation: lowercase alphanum + hyphens, no consecutive hyphens,
# 2-50 chars, must not end with reserved suffixes.
_NAME_RE = re.compile(r"^[a-z0-9](?!.*--)[a-z0-9-]{0,48}[a-z0-9]$")
_RESERVED_SUFFIXES = ("-topology", "-telemetry", "-prompts", "-runbooks", "-tickets")


def _validate_scenario_name(name: str) -> str:
    """Validate and return a cleaned scenario name, or raise HTTPException."""
    if not _NAME_RE.match(name):
        raise HTTPException(
            400,
            "Scenario name must be 2-50 chars, lowercase alphanumeric + hyphens, "
            "no consecutive hyphens, and must start/end with alphanumeric.",
        )
    for suffix in _RESERVED_SUFFIXES:
        if name.endswith(suffix):
            raise HTTPException(
                400,
                f"Scenario name must not end with reserved suffix '{suffix}'.",
            )
    return name


# ---------------------------------------------------------------------------
# DocumentStore helper
# ---------------------------------------------------------------------------


def _get_store() -> DocumentStore:
    """Get the DocumentStore for scenario metadata."""
    return get_document_store(
        SCENARIOS_DATABASE, SCENARIOS_CONTAINER, "/id",
        ensure_created=True,
    )


# ---------------------------------------------------------------------------
# Resource derivation (config-driven with convention fallback)
# ---------------------------------------------------------------------------


def _derive_resources(name: str, config: dict | None = None) -> dict:
    """Build resource bindings from config, falling back to conventions."""
    ds = (config or {}).get("data_sources", {})
    graph_cfg = ds.get("graph", {}).get("config", {})
    search_cfg = ds.get("search_indexes", {})
    return {
        "graph": graph_cfg.get("graph", f"{name}-topology"),
        "telemetry_database": ds.get("telemetry", {}).get("config", {}).get("database", "telemetry"),
        "telemetry_container_prefix": name,
        "runbooks_index": search_cfg.get("runbooks", {}).get("index_name", f"{name}-runbooks-index"),
        "tickets_index": search_cfg.get("tickets", {}).get("index_name", f"{name}-tickets-index"),
        "prompts_database": "prompts",
        "prompts_container": name,
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ScenarioSaveRequest(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    use_cases: list[str] | None = None
    example_questions: list[str] | None = None
    graph_styles: dict | None = None
    domain: str | None = None
    upload_results: dict = {}
    config: dict | None = None  # full scenario config (data_sources, agents, etc.)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip().lower()
        if not _NAME_RE.match(v):
            raise ValueError(
                "Scenario name must be 2-50 chars, lowercase alphanumeric + hyphens, "
                "no consecutive hyphens."
            )
        for suffix in _RESERVED_SUFFIXES:
            if v.endswith(suffix):
                raise ValueError(f"Scenario name must not end with reserved suffix '{suffix}'.")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/scenarios/saved", summary="List saved scenarios")
async def list_saved_scenarios():
    """Return all saved scenario documents from the scenarios database."""
    try:
        store = _get_store()
        items = await store.list(
            query="SELECT * FROM c ORDER BY c.updated_at DESC",
        )
        return {"scenarios": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to list saved scenarios: %s", e)
        return {"scenarios": [], "error": str(e)}


@router.post("/scenarios/save", summary="Save scenario metadata")
async def save_scenario(req: ScenarioSaveRequest):
    """Upsert a scenario metadata document after uploads complete."""
    name = req.name
    _validate_scenario_name(name)

    store = _get_store()

    now = datetime.now(timezone.utc).isoformat()

    # Auto-derive display name if not provided
    display_name = req.display_name or name.replace("-", " ").title()

    # Build resource bindings from config (or convention fallback)
    resources = _derive_resources(name, req.config)

    doc = {
        "id": name,
        "display_name": display_name,
        "description": req.description,
        "created_at": now,
        "updated_at": now,
        "created_by": "ui",
        "resources": resources,
        "upload_status": req.upload_results,
        "use_cases": req.use_cases or [],
        "example_questions": req.example_questions or [],
        "graph_styles": req.graph_styles or {},
        "domain": req.domain or "",
    }

    # Check if existing document has a created_at we should preserve
    try:
        existing = await store.get(name, partition_key=name)
        if existing:
            doc["created_at"] = existing.get("created_at", now)
    except Exception:
        pass

    result = await store.upsert(doc)
    logger.info("Saved scenario: %s", name)
    return {"scenario": result, "status": "saved"}


@router.delete("/scenarios/saved/{name}", summary="Delete a saved scenario record")
async def delete_saved_scenario(name: str):
    """Delete a scenario metadata record.

    This removes only the metadata document, NOT the underlying Azure resources
    (graph data, search indexes, telemetry databases). Those are left intact.
    """
    _validate_scenario_name(name)
    store = _get_store()

    try:
        await store.delete(name, partition_key=name)
    except Exception as e:
        if "NotFound" in str(e):
            raise HTTPException(404, f"Scenario '{name}' not found")
        raise

    logger.info("Deleted scenario record: %s", name)
    return {"name": name, "status": "deleted"}


# ---------------------------------------------------------------------------
# Scenario Config (Phase 8 — config-driven provisioning support)
# ---------------------------------------------------------------------------


@router.get("/scenario/config", summary="Get scenario config for provisioning")
async def get_scenario_config(
    scenario: str = Query(..., description="Scenario name"),
):
    """Return the full scenario config (parsed scenario.yaml) stored during upload.

    Used by POST /api/config/apply to drive config-driven agent provisioning.
    Returns {"config": {...}} or {"config": {}, "error": "..."} if not found.
    """
    try:
        from config_store import fetch_scenario_config
        config = await fetch_scenario_config(scenario)
        return {"config": config, "scenario": scenario}
    except ValueError as e:
        return {"config": {}, "scenario": scenario, "error": str(e)}
