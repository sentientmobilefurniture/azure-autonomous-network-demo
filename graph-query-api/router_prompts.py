"""
Router: Prompts CRUD — store and manage agent prompts in Cosmos DB.

Prompts are stored in the platform-config / prompts container.
Each document represents a versioned prompt for a specific agent.

Endpoints:
  GET    /query/prompts              — list prompts (filter by agent, scenario)
  GET    /query/prompts/{id}         — get a specific prompt
  POST   /query/prompts              — create a new prompt (or new version)
  PUT    /query/prompts/{id}         — update metadata (tags, is_active)
  DELETE /query/prompts/{id}         — soft-delete a prompt version
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config import COSMOS_NOSQL_ENDPOINT, get_credential

logger = logging.getLogger("graph-query-api.prompts")

router = APIRouter(prefix="/query", tags=["prompts"])

PLATFORM_DB = os.getenv("AGENT_CONFIG_DATABASE", "platform-config")
PROMPTS_CONTAINER = "prompts"

# ---------------------------------------------------------------------------
# Cosmos helpers (lazy init)
# ---------------------------------------------------------------------------

_container = None


def _get_prompts_container():
    global _container
    if _container is not None:
        return _container

    if not COSMOS_NOSQL_ENDPOINT:
        raise HTTPException(503, "COSMOS_NOSQL_ENDPOINT not configured")

    client = CosmosClient(url=COSMOS_NOSQL_ENDPOINT, credential=get_credential())
    db = client.create_database_if_not_exists(PLATFORM_DB)
    _container = db.create_container_if_not_exists(
        id=PROMPTS_CONTAINER,
        partition_key=PartitionKey(path="/agent"),
    )
    logger.info("Prompts container ready: %s/%s", PLATFORM_DB, PROMPTS_CONTAINER)
    return _container


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PromptCreate(BaseModel):
    agent: str               # orchestrator, graph_explorer, telemetry, runbook, ticket
    scenario: str            # scenario name or "shared"
    name: str                # prompt name (e.g. "orchestrator", "graph_explorer")
    content: str             # markdown prompt content
    description: str = ""
    tags: list[str] = []


class PromptUpdate(BaseModel):
    description: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/prompts", summary="List prompts")
async def list_prompts(
    agent: str | None = Query(default=None, description="Filter by agent name"),
    scenario: str | None = Query(default=None, description="Filter by scenario"),
):
    """List all prompts, optionally filtered by agent and/or scenario."""
    container = _get_prompts_container()

    conditions = ["c.deleted != true"]
    params = []
    if agent:
        conditions.append("c.agent = @agent")
        params.append({"name": "@agent", "value": agent})
    if scenario:
        conditions.append("c.scenario = @scenario")
        params.append({"name": "@scenario", "value": scenario})

    where = " AND ".join(conditions)
    query = f"SELECT c.id, c.agent, c.scenario, c.name, c.version, c.description, c.is_active, c.tags, c.created_at FROM c WHERE {where} ORDER BY c.agent, c.scenario, c.version DESC"

    items = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
    return {"prompts": items}


@router.get("/prompts/{prompt_id}", summary="Get a prompt")
async def get_prompt(prompt_id: str, agent: str = Query(description="Agent name (partition key)")):
    """Get a specific prompt by ID (includes content)."""
    container = _get_prompts_container()
    try:
        item = container.read_item(item=prompt_id, partition_key=agent)
        return item
    except CosmosResourceNotFoundError:
        raise HTTPException(404, f"Prompt not found: {prompt_id}")


@router.post("/prompts", summary="Create a prompt")
async def create_prompt(prompt: PromptCreate):
    """Create a new prompt or a new version of an existing one.

    Auto-increments version number if a prompt with the same
    (scenario, name, agent) already exists.
    """
    container = _get_prompts_container()

    # Find existing versions to determine next version number
    query = (
        "SELECT c.version FROM c "
        "WHERE c.agent = @agent AND c.scenario = @scenario AND c.name = @name "
        "ORDER BY c.version DESC"
    )
    existing = list(container.query_items(
        query=query,
        parameters=[
            {"name": "@agent", "value": prompt.agent},
            {"name": "@scenario", "value": prompt.scenario},
            {"name": "@name", "value": prompt.name},
        ],
        enable_cross_partition_query=False,
    ))
    next_version = (existing[0]["version"] + 1) if existing else 1

    doc_id = f"{prompt.scenario}/{prompt.name}/v{next_version}"
    doc = {
        "id": doc_id,
        "agent": prompt.agent,
        "scenario": prompt.scenario,
        "name": prompt.name,
        "version": next_version,
        "content": prompt.content,
        "description": prompt.description,
        "tags": prompt.tags,
        "is_active": True,
        "deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "ui",
    }

    # Deactivate previous versions
    for prev in existing:
        if prev.get("is_active"):
            try:
                existing_doc = container.read_item(
                    item=f"{prompt.scenario}/{prompt.name}/v{prev['version']}",
                    partition_key=prompt.agent,
                )
                existing_doc["is_active"] = False
                container.upsert_item(existing_doc)
            except Exception:
                pass

    container.upsert_item(doc)
    logger.info("Created prompt: %s (v%d)", doc_id, next_version)
    return {"id": doc_id, "version": next_version, "status": "created"}


@router.put("/prompts/{prompt_id}", summary="Update prompt metadata")
async def update_prompt(
    prompt_id: str,
    update: PromptUpdate,
    agent: str = Query(description="Agent name (partition key)"),
):
    """Update prompt metadata (description, tags, is_active). Content is immutable per version."""
    container = _get_prompts_container()
    try:
        doc = container.read_item(item=prompt_id, partition_key=agent)
    except CosmosResourceNotFoundError:
        raise HTTPException(404, f"Prompt not found: {prompt_id}")

    if update.description is not None:
        doc["description"] = update.description
    if update.tags is not None:
        doc["tags"] = update.tags
    if update.is_active is not None:
        doc["is_active"] = update.is_active

    container.upsert_item(doc)
    return {"id": prompt_id, "status": "updated"}


@router.delete("/prompts/{prompt_id}", summary="Soft-delete a prompt")
async def delete_prompt(
    prompt_id: str,
    agent: str = Query(description="Agent name (partition key)"),
):
    """Soft-delete a prompt version (marks deleted=true, not actually removed)."""
    container = _get_prompts_container()
    try:
        doc = container.read_item(item=prompt_id, partition_key=agent)
    except CosmosResourceNotFoundError:
        raise HTTPException(404, f"Prompt not found: {prompt_id}")

    doc["deleted"] = True
    doc["is_active"] = False
    container.upsert_item(doc)
    return {"id": prompt_id, "status": "deleted"}
