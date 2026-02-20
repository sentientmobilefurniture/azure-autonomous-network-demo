"""
Router: Interaction History — save, list, get, and delete investigation records.

Interactions are stored in a dedicated Cosmos NoSQL database: interactions / interactions.
Each document tracks a completed investigation's query, steps, diagnosis, and metadata.
The database and container are pre-created by Bicep (infra/modules/cosmos-nosql.bicep — NoSQL metadata store).

Endpoints:
  GET    /query/interactions                  — list past interactions (optionally by scenario)
  POST   /query/interactions                  — save a completed interaction
  GET    /query/interactions/{interaction_id}  — get a specific interaction
  DELETE /query/interactions/{interaction_id}  — delete a specific interaction
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from stores import get_document_store, DocumentStore
from models import InteractionSaveRequest

logger = logging.getLogger("graph-query-api.interactions")

router = APIRouter(prefix="/query", tags=["interactions"])

INTERACTIONS_DATABASE = "interactions"
INTERACTIONS_CONTAINER = "interactions"

# ---------------------------------------------------------------------------
# DocumentStore helper
# ---------------------------------------------------------------------------


def _get_store() -> DocumentStore:
    """Get the DocumentStore for interaction records."""
    return get_document_store(
        INTERACTIONS_DATABASE, INTERACTIONS_CONTAINER, "/scenario",
        ensure_created=True,
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
    store = _get_store()

    query = "SELECT * FROM c"
    params: list[dict] = []
    if scenario:
        query += " WHERE c.scenario = @scenario"
        params.append({"name": "@scenario", "value": scenario})
    query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
    params.append({"name": "@limit", "value": limit})

    items = await store.list(
        query=query,
        parameters=params,
        partition_key=scenario,  # scoped when filtering, None → cross-partition
    )
    return {"interactions": items}


@router.post("/interactions", summary="Save an interaction")
async def save_interaction(req: InteractionSaveRequest):
    """Save a completed investigation as an interaction record."""
    store = _get_store()
    doc = {
        "id": str(uuid.uuid4()),
        "scenario": req.scenario,
        "query": req.query,
        "steps": [s.model_dump() for s in req.steps],
        "diagnosis": req.diagnosis,
        "run_meta": req.run_meta.model_dump() if req.run_meta else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await store.upsert(doc)
    return doc


@router.get("/interactions/{interaction_id}", summary="Get a specific interaction")
async def get_interaction(interaction_id: str, scenario: str = Query(...)):
    """Get a specific interaction by ID. Requires scenario for partition key routing."""
    store = _get_store()
    try:
        return await store.get(interaction_id, partition_key=scenario)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Interaction not found")
    except Exception as e:
        logger.exception("Failed to get interaction %s", interaction_id)
        raise HTTPException(status_code=500, detail=f"Internal error: {type(e).__name__}")


@router.delete("/interactions/{interaction_id}", summary="Delete an interaction")
async def delete_interaction(interaction_id: str, scenario: str = Query(...)):
    """Delete a specific interaction."""
    store = _get_store()
    try:
        await store.delete(interaction_id, partition_key=scenario)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Interaction not found")
    except Exception as e:
        logger.exception("Failed to delete interaction %s", interaction_id)
        raise HTTPException(status_code=500, detail=f"Internal error: {type(e).__name__}")
    return {"deleted": interaction_id}
