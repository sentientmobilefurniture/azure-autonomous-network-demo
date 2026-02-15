"""
Router: Interaction History — save, list, get, and delete investigation records.

Interactions are stored in a dedicated Cosmos NoSQL database: interactions / interactions.
Each document tracks a completed investigation's query, steps, diagnosis, and metadata.
The database and container are pre-created by Bicep (infra/modules/cosmos-gremlin.bicep).

Endpoints:
  GET    /query/interactions                  — list past interactions (optionally by scenario)
  POST   /query/interactions                  — save a completed interaction
  GET    /query/interactions/{interaction_id}  — get a specific interaction
  DELETE /query/interactions/{interaction_id}  — delete a specific interaction
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from config import COSMOS_NOSQL_ENDPOINT
from cosmos_helpers import get_or_create_container
from models import InteractionSaveRequest

logger = logging.getLogger("graph-query-api.interactions")

router = APIRouter(prefix="/query", tags=["interactions"])

INTERACTIONS_DATABASE = "interactions"
INTERACTIONS_CONTAINER = "interactions"

# ---------------------------------------------------------------------------
# Cosmos helpers (delegated to cosmos_helpers)
# ---------------------------------------------------------------------------


def _get_interactions_container(*, ensure_created: bool = True):
    """Get the Cosmos container for interaction records.

    Database: interactions (pre-created by Bicep)
    Container: interactions
    Partition key: /scenario
    """
    return get_or_create_container(
        INTERACTIONS_DATABASE, INTERACTIONS_CONTAINER, "/scenario",
        ensure_created=ensure_created,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/interactions", summary="List past interactions")
async def list_interactions(
    scenario: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List interactions, optionally filtered by scenario.
    Returns newest first (ORDER BY c.created_at DESC).
    """
    container = _get_interactions_container(ensure_created=False)

    def _list():
        query = "SELECT * FROM c"
        params: list[dict] = []
        if scenario:
            query += " WHERE c.scenario = @scenario"
            params.append({"name": "@scenario", "value": scenario})
        query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
        params.append({"name": "@limit", "value": limit})

        if scenario:
            return list(
                container.query_items(
                    query=query,
                    parameters=params,
                    partition_key=scenario,
                )
            )
        else:
            return list(
                container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=True,
                )
            )

    items = await asyncio.to_thread(_list)
    return {"interactions": items}


@router.post("/interactions", summary="Save an interaction")
async def save_interaction(req: InteractionSaveRequest):
    """Save a completed investigation as an interaction record."""
    container = _get_interactions_container()
    doc = {
        "id": str(uuid.uuid4()),
        "scenario": req.scenario,
        "query": req.query,
        "steps": [s.model_dump() for s in req.steps],
        "diagnosis": req.diagnosis,
        "run_meta": req.run_meta.model_dump() if req.run_meta else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    def _save():
        return container.upsert_item(doc)

    await asyncio.to_thread(_save)
    return doc


@router.get("/interactions/{interaction_id}", summary="Get a specific interaction")
async def get_interaction(interaction_id: str, scenario: str = Query(...)):
    """Get a specific interaction by ID. Requires scenario for partition key routing."""
    container = _get_interactions_container(ensure_created=False)

    def _get():
        try:
            return container.read_item(item=interaction_id, partition_key=scenario)
        except CosmosResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Interaction not found")

    return await asyncio.to_thread(_get)


@router.delete("/interactions/{interaction_id}", summary="Delete an interaction")
async def delete_interaction(interaction_id: str, scenario: str = Query(...)):
    """Delete a specific interaction."""
    container = _get_interactions_container(ensure_created=False)

    def _delete():
        try:
            container.delete_item(item=interaction_id, partition_key=scenario)
        except CosmosResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Interaction not found")

    await asyncio.to_thread(_delete)
    return {"deleted": interaction_id}
