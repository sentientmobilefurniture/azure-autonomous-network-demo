"""
Router: Prompts CRUD — store and manage agent prompts in Cosmos DB.

Prompts are stored in per-scenario Cosmos databases: {scenario}-prompts / prompts.
Each document represents a versioned prompt for a specific agent.

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

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config import COSMOS_NOSQL_ENDPOINT, get_credential

logger = logging.getLogger("graph-query-api.prompts")

router = APIRouter(prefix="/query", tags=["prompts"])

PROMPTS_DATABASE = "prompts"  # shared DB — pre-created by Bicep

# ---------------------------------------------------------------------------
# Cosmos helpers (lazy init, per-scenario cache)
# ---------------------------------------------------------------------------

_containers: dict[str, object] = {}


def _get_prompts_container(scenario: str, *, ensure_created: bool = False):
    """Get the Cosmos container for a scenario's prompts.

    Database: prompts (shared, pre-created by Bicep)
    Container: {scenario} (per-scenario, created on demand)
    Partition key: /agent

    Args:
        scenario: Scenario name (e.g. "telco-noc")
        ensure_created: If True, create the container via ARM first.
            Database creation is skipped — the shared "prompts" DB
            pre-exists from Bicep. Only needed for write operations.
    """
    if scenario in _containers:
        return _containers[scenario]

    if not COSMOS_NOSQL_ENDPOINT:
        raise HTTPException(503, "COSMOS_NOSQL_ENDPOINT not configured")

    if ensure_created:
        # Create container via ARM (management plane)
        # Database "prompts" already exists (Bicep) — skip DB creation
        account_name = COSMOS_NOSQL_ENDPOINT.replace("https://", "").split(".")[0]
        sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
        rg = os.getenv("AZURE_RESOURCE_GROUP", "")

        if sub_id and rg:
            try:
                from azure.mgmt.cosmosdb import CosmosDBManagementClient
                from azure.identity import DefaultAzureCredential as _DC
                mgmt = CosmosDBManagementClient(_DC(), sub_id)
                try:
                    mgmt.sql_resources.begin_create_update_sql_container(
                        rg, account_name, PROMPTS_DATABASE, scenario,
                        {"resource": {"id": scenario, "partitionKey": {"paths": ["/agent"], "kind": "Hash"}}},
                    ).result()
                except Exception:
                    pass  # already exists
            except Exception as e:
                logger.warning("ARM prompts container creation failed: %s", e)

    # Data-plane client for reads/writes
    client = CosmosClient(url=COSMOS_NOSQL_ENDPOINT, credential=get_credential())
    db = client.get_database_client(PROMPTS_DATABASE)
    container = db.get_container_client(scenario)
    _containers[scenario] = container
    logger.info("Prompts container ready: %s/%s", PROMPTS_DATABASE, scenario)
    return container


def _list_prompt_scenarios() -> list[str]:
    """List all per-scenario containers in the shared 'prompts' database.

    Returns list of scenario names (each container name IS the scenario name).
    """
    if not COSMOS_NOSQL_ENDPOINT:
        return []
    account_name = COSMOS_NOSQL_ENDPOINT.replace("https://", "").split(".")[0]
    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
    rg = os.getenv("AZURE_RESOURCE_GROUP", "")
    if not sub_id or not rg:
        return []
    try:
        from azure.mgmt.cosmosdb import CosmosDBManagementClient
        from azure.identity import DefaultAzureCredential as _DC
        mgmt = CosmosDBManagementClient(_DC(), sub_id)
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
    # NOTE: No ORDER BY — Cosmos NoSQL requires a composite index for multi-field
    # ORDER BY, and the container is created without one. Sorting is done in Python.
    query = f"SELECT {fields} FROM c WHERE {where}"

    def _query_scenario(sc: str) -> list:
        try:
            c = _get_prompts_container(sc)  # read-only, no ARM
            results = list(c.query_items(query=query, parameters=params, enable_cross_partition_query=True))
            # Sort in Python: by agent, then scenario, then version descending
            results.sort(key=lambda x: (x.get("agent", ""), x.get("scenario", ""), -(x.get("version", 0))))
            return results
        except Exception as e:
            logger.warning("Failed to query prompts for scenario %s: %s", sc, e)
            return []

    if scenario:
        items = await asyncio.to_thread(_query_scenario, scenario)
    else:
        def _scan_all():
            all_items = []
            for sc in _list_prompt_scenarios():
                all_items.extend(_query_scenario(sc))
            return all_items
        items = await asyncio.to_thread(_scan_all)

    return {"prompts": items}


@router.get("/prompts/scenarios", summary="List available prompt sets")
async def list_prompt_scenarios():
    """List distinct scenario names that have prompts stored in Cosmos."""
    try:
        def _list():
            scenarios = _list_prompt_scenarios()
            result = []
            for sc in scenarios:
                try:
                    container = _get_prompts_container(sc)
                    count_q = "SELECT VALUE COUNT(1) FROM c WHERE c.is_active = true AND c.deleted != true"
                    counts = list(container.query_items(query=count_q, enable_cross_partition_query=True))
                    result.append({"scenario": sc, "prompt_count": counts[0] if counts else 0})
                except Exception as e:
                    logger.warning("Failed to count prompts for %s: %s", sc, e)
                    result.append({"scenario": sc, "prompt_count": 0})
            return result

        scenarios = await asyncio.to_thread(_list)
        return {"prompt_scenarios": scenarios}
    except Exception as e:
        logger.warning("Failed to list prompt scenarios: %s", e)
        return {"prompt_scenarios": [], "error": str(e)}


@router.get("/prompts/{prompt_id}", summary="Get a prompt")
async def get_prompt(prompt_id: str, agent: str = Query(description="Agent name (partition key)")):
    """Get a specific prompt by ID (includes content)."""
    scenario = _parse_scenario_from_id(prompt_id)
    container = _get_prompts_container(scenario)
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
    container = _get_prompts_container(prompt.scenario, ensure_created=True)

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
                existing_doc = container.read_item(
                    item=f"{prompt.scenario}__{prompt.name}__v{prev['version']}",
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
    scenario = _parse_scenario_from_id(prompt_id)
    container = _get_prompts_container(scenario)
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
    scenario = _parse_scenario_from_id(prompt_id)
    container = _get_prompts_container(scenario)
    try:
        doc = container.read_item(item=prompt_id, partition_key=agent)
    except CosmosResourceNotFoundError:
        raise HTTPException(404, f"Prompt not found: {prompt_id}")

    doc["deleted"] = True
    doc["is_active"] = False
    container.upsert_item(doc)
    return {"id": prompt_id, "status": "deleted"}
