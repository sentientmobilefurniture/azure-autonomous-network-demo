"""
Cosmos container helper — shared Cosmos DB client and container init logic.

Consolidates the repeated ARM boilerplate for creating NoSQL databases and
containers found in router_prompts.py, router_scenarios.py, and
router_interactions.py. Also provides a singleton CosmosClient and
CosmosDBManagementClient.

Used by: router_prompts, router_scenarios, router_interactions, router_ingest,
         router_telemetry
"""

from __future__ import annotations

import logging
import os

from azure.cosmos import CosmosClient, ContainerProxy

from config import get_credential
from adapters.cosmos_config import COSMOS_NOSQL_ENDPOINT

logger = logging.getLogger("graph-query-api.cosmos")

# ---------------------------------------------------------------------------
# Singleton clients (manual pattern matching config.py convention)
# ---------------------------------------------------------------------------

_cosmos_client: CosmosClient | None = None


def get_cosmos_client() -> CosmosClient:
    """Cached data-plane CosmosClient singleton.
    
    Raises RuntimeError instead of HTTPException so this can be safely
    called during module init without crashing the entire app.
    """
    global _cosmos_client
    if _cosmos_client is None:
        if not COSMOS_NOSQL_ENDPOINT:
            raise RuntimeError("COSMOS_NOSQL_ENDPOINT not configured")
        _cosmos_client = CosmosClient(url=COSMOS_NOSQL_ENDPOINT, credential=get_credential())
    return _cosmos_client


def close_cosmos_client() -> None:
    """Close the cached CosmosClient (for shutdown cleanup)."""
    global _cosmos_client
    if _cosmos_client is not None:
        try:
            _cosmos_client.close()
        except Exception:
            pass
        _cosmos_client = None


_mgmt_client = None


def get_mgmt_client():
    """Cached ARM CosmosDBManagementClient singleton."""
    global _mgmt_client
    if _mgmt_client is None:
        from azure.mgmt.cosmosdb import CosmosDBManagementClient
        sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
        if not sub_id:
            raise RuntimeError("AZURE_SUBSCRIPTION_ID not set")
        _mgmt_client = CosmosDBManagementClient(get_credential(), sub_id)
    return _mgmt_client


# ---------------------------------------------------------------------------
# Container cache + idempotent creation
# ---------------------------------------------------------------------------

_container_cache: dict[tuple[str, str], ContainerProxy] = {}


def get_or_create_container(
    db_name: str,
    container_name: str,
    partition_key_path: str,
    *,
    ensure_created: bool = False,
) -> ContainerProxy:
    """Get a Cosmos container, optionally creating DB + container via ARM.

    Args:
        db_name: Database name (e.g. "prompts", "scenarios", "interactions")
        container_name: Container name (may be dynamic, e.g. scenario name)
        partition_key_path: Partition key path (e.g. "/agent", "/id")
        ensure_created: If True, create the container via ARM first.
            Database is assumed to pre-exist (created by Bicep).

    Returns:
        ContainerProxy for the requested container.
    """
    cache_key = (db_name, container_name)
    if cache_key in _container_cache:
        return _container_cache[cache_key]

    if not COSMOS_NOSQL_ENDPOINT:
        from fastapi import HTTPException
        raise HTTPException(503, "COSMOS_NOSQL_ENDPOINT not configured")

    if ensure_created:
        _arm_ensure_container(db_name, container_name, partition_key_path)

    client = get_cosmos_client()
    container = client.get_database_client(db_name).get_container_client(container_name)
    _container_cache[cache_key] = container
    return container


def _arm_ensure_container(db_name: str, container_name: str, pk_path: str) -> None:
    """Idempotent ARM creation of a SQL container (catches 'already exists')."""
    account_name = COSMOS_NOSQL_ENDPOINT.replace("https://", "").split(".")[0]
    rg = os.environ.get("AZURE_RESOURCE_GROUP", "")
    if not rg:
        logger.warning("AZURE_RESOURCE_GROUP not set — cannot create container via ARM")
        return

    try:
        mgmt = get_mgmt_client()
        # Check existence first — partition keys are immutable so update would
        # fail with BadRequest if the PK path doesn't match.
        try:
            mgmt.sql_resources.get_sql_container(rg, account_name, db_name, container_name)
            logger.debug("Container %s/%s already exists — skipping ARM creation", db_name, container_name)
            return
        except Exception:
            pass  # doesn't exist yet — create below

        mgmt.sql_resources.begin_create_update_sql_container(
            rg, account_name, db_name, container_name,
            {
                "resource": {
                    "id": container_name,
                    "partitionKey": {"paths": [pk_path], "kind": "Hash", "version": 2},
                }
            },
        ).result()
        logger.info("Created container %s/%s (pk=%s)", db_name, container_name, pk_path)
    except Exception as e:
        if "Conflict" not in str(e):
            logger.warning("ARM container creation failed: %s", e)
