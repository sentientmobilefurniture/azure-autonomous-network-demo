"""
Router: Prompts CRUD — store and manage agent prompts in Cosmos DB.

Prompts are stored in per-scenario Cosmos containers within the shared "prompts"
database. Each document represents a versioned prompt for a specific agent.

Endpoints:
  GET    /query/prompts              — list prompts (filter by agent, scenario)
  GET    /query/prompts/{id}         — get a specific prompt
  POST   /query/prompts              — create a new prompt (or new version)
  PUT    /query/prompts/{id}         — update metadata (tags, is_active)
  DELETE /query/prompts/{id}         — soft-delete a prompt version
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from adapters.cosmos_config import COSMOS_NOSQL_ENDPOINT
from cosmos_helpers import get_mgmt_client
from stores import get_document_store, DocumentStore

logger = logging.getLogger("graph-query-api.prompts")

router = APIRouter(prefix="/query", tags=["prompts"])

PROMPTS_DATABASE = "prompts"  # shared DB — pre-created by Bicep

# ---------------------------------------------------------------------------
# DocumentStore helper
# ---------------------------------------------------------------------------


def _get_prompts_store(scenario: str, *, ensure_created: bool = False) -> DocumentStore:
    """Get the DocumentStore for a scenario's prompts.

    Database: prompts (shared, pre-created by Bicep)
    Container: {scenario} (per-scenario, created on demand)
    Partition key: /agent
    """
    return get_document_store(
        PROMPTS_DATABASE, scenario, "/agent", ensure_created=ensure_created,
    )


def _list_prompt_scenarios() -> list[str]:
    """List all per-scenario containers in the shared 'prompts' database.

    Returns list of scenario names (each container name IS the scenario name).
    This is infrastructure introspection via ARM — not a DocumentStore operation.
    """
    if not COSMOS_NOSQL_ENDPOINT:
        return []
    account_name = COSMOS_NOSQL_ENDPOINT.replace("https://", "").split(".")[0]
    rg = os.getenv("AZURE_RESOURCE_GROUP", "")
    if not rg:
        return []
    try:
        mgmt = get_mgmt_client()
        containers = mgmt.sql_resources.list_sql_containers(rg, account_name, PROMPTS_DATABASE)
        return sorted(c.name for c in containers if c.name)
    except Exception as e:
        logger.warning("Failed to list prompt containers: %s", e)
        return []


def _parse_scenario_from_id(prompt_id: str) -> str:
    """Extract scenario name from a prompt ID like 'telco-noc__orchestrator__v1'."""
    parts = prompt_id.split("__")
    if len(parts) >= 2:
        return parts[0]
    raise HTTPException(400, f"Invalid prompt ID format: {prompt_id}")


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
    include_content: bool = Query(default=False, description="Include prompt content in response"),
):
    """List all prompts, optionally filtered by agent and/or scenario."""
    conditions = ["c.deleted != true"]
    params = []
    if agent:
        conditions.append("c.agent = @agent")
        params.append({"name": "@agent", "value": agent})

    fields = "c.id, c.agent, c.scenario, c.name, c.version, c.description, c.is_active, c.tags, c.created_at"
    if include_content:
        fields += ", c.content"
    where = " AND ".join(conditions)
    query = f"SELECT {fields} FROM c WHERE {where}"

    async def _query_scenario(sc: str) -> list:
        try:
            store = _get_prompts_store(sc)
            results = await store.list(query=query, parameters=params or None)
            # Sort in Python: by agent, then scenario, then version descending
            results.sort(key=lambda x: (x.get("agent", ""), x.get("scenario", ""), -(x.get("version", 0))))
            return results
        except Exception as e:
            logger.warning("Failed to query prompts for scenario %s: %s", sc, e)
            return []

    if scenario:
        items = await _query_scenario(scenario)
    else:
        all_items = []
        for sc in await asyncio.to_thread(_list_prompt_scenarios):
            all_items.extend(await _query_scenario(sc))
        items = all_items

    return {"prompts": items}


@router.get("/prompts/scenarios", summary="List available prompt sets")
async def list_prompt_scenarios():
    """List distinct scenario names that have prompts stored in Cosmos."""
    try:
        scenarios = await asyncio.to_thread(_list_prompt_scenarios)
        result = []
        for sc in scenarios:
            try:
                store = _get_prompts_store(sc)
                count_q = "SELECT VALUE COUNT(1) FROM c WHERE c.is_active = true AND c.deleted != true"
                counts = await store.list(query=count_q)
                result.append({"scenario": sc, "prompt_count": counts[0] if counts else 0})
            except Exception as e:
                logger.warning("Failed to count prompts for %s: %s", sc, e)
                result.append({"scenario": sc, "prompt_count": 0})
        return {"prompt_scenarios": result}
    except Exception as e:
        logger.warning("Failed to list prompt scenarios: %s", e)
        return {"prompt_scenarios": [], "error": str(e)}


@router.get("/prompts/{prompt_id}", summary="Get a prompt")
async def get_prompt(prompt_id: str, agent: str = Query(description="Agent name (partition key)")):
    """Get a specific prompt by ID (includes content)."""
    scenario = _parse_scenario_from_id(prompt_id)
    store = _get_prompts_store(scenario)
    try:
        return await store.get(prompt_id, partition_key=agent)
    except Exception:
        raise HTTPException(404, f"Prompt not found: {prompt_id}")


@router.post("/prompts", summary="Create a prompt")
async def create_prompt(prompt: PromptCreate):
    """Create a new prompt or a new version of an existing one.

    Auto-increments version number if a prompt with the same
    (scenario, name, agent) already exists.
    """
    store = _get_prompts_store(prompt.scenario, ensure_created=True)

    # Find existing versions to determine next version number
    query = (
        "SELECT c.version FROM c "
        "WHERE c.agent = @agent AND c.scenario = @scenario AND c.name = @name "
        "ORDER BY c.version DESC"
    )
    existing = await store.list(
        query=query,
        parameters=[
            {"name": "@agent", "value": prompt.agent},
            {"name": "@scenario", "value": prompt.scenario},
            {"name": "@name", "value": prompt.name},
        ],
        partition_key=prompt.agent,
    )
    next_version = (existing[0]["version"] + 1) if existing else 1

    doc_id = f"{prompt.scenario}__{prompt.name}__v{next_version}"
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
                existing_doc = await store.get(
                    f"{prompt.scenario}__{prompt.name}__v{prev['version']}",
                    partition_key=prompt.agent,
                )
                existing_doc["is_active"] = False
                await store.upsert(existing_doc)
            except Exception:
                pass

    await store.upsert(doc)
    logger.info("Created prompt: %s (v%d)", doc_id, next_version)
    return {"id": doc_id, "version": next_version, "status": "created"}


@router.put("/prompts/{prompt_id}", summary="Update prompt metadata")
async def update_prompt(
    prompt_id: str,
    update: PromptUpdate,
    agent: str = Query(description="Agent name (partition key)"),
):
    """Update prompt metadata (description, tags, is_active). Content is immutable per version."""
    scenario = _parse_scenario_from_id(prompt_id)
    store = _get_prompts_store(scenario)
    try:
        doc = await store.get(prompt_id, partition_key=agent)
    except Exception:
        raise HTTPException(404, f"Prompt not found: {prompt_id}")

    if update.description is not None:
        doc["description"] = update.description
    if update.tags is not None:
        doc["tags"] = update.tags
    if update.is_active is not None:
        doc["is_active"] = update.is_active

    await store.upsert(doc)
    return {"id": prompt_id, "status": "updated"}


@router.delete("/prompts/{prompt_id}", summary="Soft-delete a prompt")
async def delete_prompt(
    prompt_id: str,
    agent: str = Query(description="Agent name (partition key)"),
):
    """Soft-delete a prompt version (marks deleted=true, not actually removed)."""
    scenario = _parse_scenario_from_id(prompt_id)
    store = _get_prompts_store(scenario)
    try:
        doc = await store.get(prompt_id, partition_key=agent)
    except Exception:
        raise HTTPException(404, f"Prompt not found: {prompt_id}")

    doc["deleted"] = True
    doc["is_active"] = False
    await store.upsert(doc)
    return {"id": prompt_id, "status": "deleted"}
