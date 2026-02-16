"""
Router: Fabric workspace connection CRUD.

Persists workspace connections in Cosmos NoSQL so users can
add, list, select, and delete Fabric workspace connections
from the UI.

Container: fabric-connections (auto-created on first access)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from stores import get_document_store

logger = logging.getLogger("graph-query-api.fabric-connections")

router = APIRouter(prefix="/query/fabric/connections", tags=["fabric-connections"])

DB_NAME = "scenarios"  # reuse the existing scenarios database
CONTAINER_NAME = "fabric-connections"
PK_PATH = "/id"


def _get_store():
    return get_document_store(
        DB_NAME, CONTAINER_NAME, PK_PATH, ensure_created=True,
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ConnectionCreate(BaseModel):
    workspace_id: str
    workspace_name: str


class ConnectionDoc(BaseModel):
    id: str
    workspace_id: str
    workspace_name: str
    created_at: str
    last_used: str
    active: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_connections():
    """List all saved Fabric workspace connections."""
    store = _get_store()
    items = await store.list(
        query="SELECT * FROM c ORDER BY c.last_used DESC",
    )
    # Strip Cosmos system fields
    connections = [
        {k: v for k, v in item.items() if not k.startswith("_")}
        for item in items
    ]
    return {"connections": connections}


@router.post("")
async def create_connection(req: ConnectionCreate):
    """Add a new workspace connection. Upserts if workspace_id already exists."""
    store = _get_store()

    # Validate workspace is reachable
    try:
        import httpx
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        token = credential.get_token("https://api.fabric.microsoft.com/.default")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://api.fabric.microsoft.com/v1/workspaces/{req.workspace_id}",
                headers={"Authorization": f"Bearer {token.token}"},
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"Workspace not reachable: {resp.status_code} — {resp.text[:200]}",
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot validate workspace: {e}")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": req.workspace_id,
        "workspace_id": req.workspace_id,
        "workspace_name": req.workspace_name,
        "created_at": now,
        "last_used": now,
        "active": False,
    }

    result = await store.upsert(doc)
    clean = {k: v for k, v in result.items() if not k.startswith("_")}
    return clean


@router.delete("/{connection_id}")
async def delete_connection(connection_id: str):
    """Remove a saved connection."""
    store = _get_store()
    try:
        await store.delete(connection_id, connection_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Connection not found: {e}")
    return {"deleted": connection_id}


@router.post("/{connection_id}/select")
async def select_connection(connection_id: str):
    """Set a connection as the active workspace.

    Writes the active workspace config to a fabric-config document
    that both services can read at runtime.
    """
    store = _get_store()

    # Get the connection
    try:
        connection = await store.get(connection_id, connection_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Deactivate all, activate this one
    all_connections = await store.list(query="SELECT * FROM c")
    for conn in all_connections:
        was_active = conn.get("active", False)
        is_target = conn["id"] == connection_id
        if was_active or is_target:
            conn["active"] = is_target
            if is_target:
                conn["last_used"] = datetime.now(timezone.utc).isoformat()
            await store.upsert(conn)

    # Write active config to a well-known document in the same container
    config_doc = {
        "id": "__active_fabric_config__",
        "workspace_id": connection["workspace_id"],
        "workspace_name": connection["workspace_name"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await store.upsert(config_doc)

    clean = {k: v for k, v in connection.items() if not k.startswith("_")}
    clean["active"] = True
    return clean
