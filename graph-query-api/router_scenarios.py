"""
Router: Scenario CRUD — save, list, and delete scenario metadata in Cosmos DB.

Scenarios are stored in a dedicated Cosmos NoSQL database: scenarios / scenarios.
Each document tracks the name, display name, description, and resource bindings
for a complete scenario (graph + telemetry + runbooks + tickets + prompts).

Endpoints:
  GET    /query/scenarios/saved       — list all saved scenario records
  POST   /query/scenarios/save        — upsert a scenario record
  DELETE /query/scenarios/saved/{name} — delete a scenario record
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from config import COSMOS_NOSQL_ENDPOINT
from cosmos_helpers import get_or_create_container

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
# Cosmos helpers (delegated to cosmos_helpers)
# ---------------------------------------------------------------------------


def _get_scenarios_container(*, ensure_created: bool = True):
    """Get the Cosmos container for scenario metadata.

    Database: scenarios (pre-created by Bicep)
    Container: scenarios
    Partition key: /id
    """
    return get_or_create_container(
        SCENARIOS_DATABASE, SCENARIOS_CONTAINER, "/id",
        ensure_created=ensure_created,
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ScenarioSaveRequest(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    upload_results: dict = {}

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
        container = _get_scenarios_container()

        def _list():
            items = list(
                container.query_items(
                    query="SELECT * FROM c ORDER BY c.updated_at DESC",
                    enable_cross_partition_query=True,
                )
            )
            return items

        scenarios = await asyncio.to_thread(_list)
        return {"scenarios": scenarios}
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

    container = _get_scenarios_container(ensure_created=True)

    now = datetime.now(timezone.utc).isoformat()

    # Auto-derive display name if not provided
    display_name = req.display_name or name.replace("-", " ").title()

    # Build resource bindings from the scenario name
    doc = {
        "id": name,
        "display_name": display_name,
        "description": req.description,
        "created_at": now,
        "updated_at": now,
        "created_by": "ui",
        "resources": {
            "graph": f"{name}-topology",
            "telemetry_database": "telemetry",
            "telemetry_container_prefix": name,
            "runbooks_index": f"{name}-runbooks-index",
            "tickets_index": f"{name}-tickets-index",
            "prompts_database": "prompts",
            "prompts_container": name,
        },
        "upload_status": req.upload_results,
    }

    # Check if existing document has a created_at we should preserve
    try:

        def _read_existing():
            try:
                existing = container.read_item(item=name, partition_key=name)
                return existing
            except Exception:
                return None

        existing = await asyncio.to_thread(_read_existing)
        if existing:
            doc["created_at"] = existing.get("created_at", now)
    except Exception:
        pass

    def _upsert():
        container.upsert_item(doc)
        return doc

    result = await asyncio.to_thread(_upsert)
    logger.info("Saved scenario: %s", name)
    return {"scenario": result, "status": "saved"}


@router.delete("/scenarios/saved/{name}", summary="Delete a saved scenario record")
async def delete_saved_scenario(name: str):
    """Delete a scenario metadata record.

    This removes only the metadata document, NOT the underlying Azure resources
    (graph data, search indexes, telemetry databases). Those are left intact.
    """
    _validate_scenario_name(name)
    container = _get_scenarios_container()

    def _delete():
        try:
            container.delete_item(item=name, partition_key=name)
            return True
        except Exception as e:
            if "NotFound" in str(e):
                return False
            raise

    deleted = await asyncio.to_thread(_delete)
    if not deleted:
        raise HTTPException(404, f"Scenario '{name}' not found")

    logger.info("Deleted scenario record: %s", name)
    return {"name": name, "status": "deleted"}
