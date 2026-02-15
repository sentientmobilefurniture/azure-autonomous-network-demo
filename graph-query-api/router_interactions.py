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
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from config import COSMOS_NOSQL_ENDPOINT, get_credential
from models import InteractionSaveRequest

logger = logging.getLogger("graph-query-api.interactions")

router = APIRouter(prefix="/query", tags=["interactions"])

INTERACTIONS_DATABASE = "interactions"
INTERACTIONS_CONTAINER = "interactions"

# ---------------------------------------------------------------------------
# Cosmos helpers (lazy init)
# ---------------------------------------------------------------------------

_interactions_container = None


def _get_interactions_container(*, ensure_created: bool = True):
    """Get the Cosmos container for interaction records.

    Database: interactions (pre-created by Bicep)
    Container: interactions
    Partition key: /scenario

    Database creation is skipped — the shared 'interactions' DB pre-exists
    from Bicep. Only the container is created via ARM if needed.
    """
    global _interactions_container
    if _interactions_container is not None:
        return _interactions_container

    if not COSMOS_NOSQL_ENDPOINT:
        raise HTTPException(503, "COSMOS_NOSQL_ENDPOINT not configured")

    if ensure_created:
        account_name = COSMOS_NOSQL_ENDPOINT.replace("https://", "").split(".")[0]
        sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
        rg = os.getenv("AZURE_RESOURCE_GROUP", "")

        if sub_id and rg:
            try:
                from azure.mgmt.cosmosdb import CosmosDBManagementClient
                from azure.identity import DefaultAzureCredential as _DC

                mgmt = CosmosDBManagementClient(_DC(), sub_id)

                # Database "interactions" pre-exists from Bicep — skip creation
                # Only create container if needed
                try:
                    mgmt.sql_resources.begin_create_update_sql_container(
                        rg,
                        account_name,
                        INTERACTIONS_DATABASE,
                        INTERACTIONS_CONTAINER,
                        {
                            "resource": {
                                "id": INTERACTIONS_CONTAINER,
                                "partitionKey": {
                                    "paths": ["/scenario"],
                                    "kind": "Hash",
                                },
                            }
                        },
                    ).result()
                except Exception:
                    pass  # already exists
            except Exception as e:
                logger.warning("ARM interactions container creation failed: %s", e)

    # Data-plane client
    from azure.cosmos import CosmosClient

    client = CosmosClient(url=COSMOS_NOSQL_ENDPOINT, credential=get_credential())
    db = client.get_database_client(INTERACTIONS_DATABASE)
    container = db.get_container_client(INTERACTIONS_CONTAINER)
    _interactions_container = container
    return container


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
