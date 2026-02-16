"""
Router: Fabric resource discovery.

Lists ontologies, graph models, and eventhouses in the configured
Fabric workspace. Used by the frontend Settings modal for resource
selection.

All endpoints are under /query/fabric/* and are proxied through
the existing /query/* nginx location block — no nginx changes needed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_credential
from adapters.fabric_config import (
    FABRIC_API_URL,
    FABRIC_SCOPE,
    FABRIC_WORKSPACE_ID,
    FABRIC_CONFIGURED,
    FABRIC_WORKSPACE_CONNECTED,
    FABRIC_QUERY_READY,
)
from backends.fabric import acquire_fabric_token

logger = logging.getLogger("graph-query-api.fabric-discovery")

router = APIRouter(prefix="/query/fabric", tags=["fabric-discovery"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class FabricItem(BaseModel):
    """A Fabric workspace item (ontology, graph model, eventhouse, etc.)."""
    id: str
    display_name: str
    type: str
    description: str = ""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _get_token() -> str:
    """Acquire a Fabric API token via DefaultAzureCredential."""
    return await acquire_fabric_token()


async def _fabric_get(path: str, params: dict[str, str] | None = None) -> Any:
    """Execute a GET request against the Fabric REST API.

    Args:
        path: Relative path appended to FABRIC_API_URL
              (e.g. "/workspaces/{id}/ontologies").
        params: Optional query parameters.

    Returns:
        Parsed JSON response body.
    """
    if not FABRIC_WORKSPACE_CONNECTED:
        raise HTTPException(
            status_code=503,
            detail="Fabric workspace not configured. Set FABRIC_WORKSPACE_ID "
                   "environment variable.",
        )

    token = await _get_token()
    url = f"{FABRIC_API_URL}{path}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    if resp.status_code != 200:
        detail = resp.text[:500]
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Fabric API error: {detail}",
        )

    return resp.json()


def _items_to_fabric_items(
    items: list[dict], expected_type: str | None = None,
) -> list[FabricItem]:
    """Convert raw Fabric API item dicts to FabricItem models.

    Optionally filters by item type.
    """
    result = []
    for item in items:
        item_type = item.get("type", "")
        if expected_type and item_type != expected_type:
            continue
        result.append(
            FabricItem(
                id=item.get("id", ""),
                display_name=item.get("displayName", ""),
                type=item_type,
                description=item.get("description", ""),
            )
        )
    return result


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------


@router.get("/ontologies", response_model=list[FabricItem])
async def list_ontologies(workspace_id: str | None = None) -> list[FabricItem]:
    """List ontologies in the Fabric workspace.

    Uses the dedicated /ontologies endpoint first, falls back to
    workspace items filtered by type.
    """
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    try:
        body = await _fabric_get(f"/workspaces/{ws_id}/ontologies")
        items = body.get("value", body if isinstance(body, list) else [])
        return _items_to_fabric_items(items)
    except HTTPException:
        # Fallback: use workspace items API with type filter
        body = await _fabric_get(f"/workspaces/{ws_id}/items")
        items = body.get("value", body if isinstance(body, list) else [])
        return _items_to_fabric_items(items, expected_type="Ontology")


@router.get(
    "/ontologies/{ontology_id}/models",
    response_model=list[FabricItem],
)
async def list_graph_models(
    ontology_id: str,
    workspace_id: str | None = None,
) -> list[FabricItem]:
    """List graph models in the workspace.

    Fabric graph models are workspace-level items (not nested under
    ontologies), so we list workspace items filtered by type.
    """
    ws_id = workspace_id or FABRIC_WORKSPACE_ID

    # Try type-filtered items first
    try:
        body = await _fabric_get(
            f"/workspaces/{ws_id}/items", params={"type": "GraphModel"},
        )
        items = body.get("value", body if isinstance(body, list) else [])
        if items:
            return _items_to_fabric_items(items)
    except HTTPException:
        pass

    # Fallback: list all items and filter client-side
    body = await _fabric_get(f"/workspaces/{ws_id}/items")
    items = body.get("value", body if isinstance(body, list) else [])
    return _items_to_fabric_items(items, expected_type="GraphModel")


@router.get("/eventhouses", response_model=list[FabricItem])
async def list_eventhouses(workspace_id: str | None = None) -> list[FabricItem]:
    """List eventhouses in the Fabric workspace."""
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    body = await _fabric_get(f"/workspaces/{ws_id}/items")
    items = body.get("value", body if isinstance(body, list) else [])
    return _items_to_fabric_items(items, expected_type="Eventhouse")


@router.get("/kql-databases", response_model=list[FabricItem])
async def list_kql_databases(workspace_id: str | None = None) -> list[FabricItem]:
    """List KQL databases in the Fabric workspace."""
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    try:
        body = await _fabric_get(f"/workspaces/{ws_id}/kqlDatabases")
        items = body.get("value", body if isinstance(body, list) else [])
        return _items_to_fabric_items(items)
    except HTTPException:
        # Fallback to items API
        body = await _fabric_get(f"/workspaces/{ws_id}/items")
        items = body.get("value", body if isinstance(body, list) else [])
        return _items_to_fabric_items(items, expected_type="KQLDatabase")


@router.get("/lakehouses", response_model=list[FabricItem])
async def list_lakehouses(workspace_id: str | None = None) -> list[FabricItem]:
    """List lakehouses in the Fabric workspace."""
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    body = await _fabric_get(f"/workspaces/{ws_id}/items")
    items = body.get("value", body if isinstance(body, list) else [])
    return _items_to_fabric_items(items, expected_type="Lakehouse")


@router.get("/health")
async def fabric_health() -> dict:
    """Check Fabric backend readiness."""
    return {
        "configured": FABRIC_CONFIGURED,
        "workspace_id": FABRIC_WORKSPACE_ID,
    }
