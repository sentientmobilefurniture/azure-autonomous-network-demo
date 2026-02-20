"""
Router: Session Persistence — CRUD for investigation session records.

Sessions are stored in the same Cosmos NoSQL container as interactions:
    database = "interactions", container = "interactions", pk = "/scenario".

These endpoints are called by the API service (session_manager.py) via httpx
to persist and retrieve session state across container restarts.

Endpoints:
  GET    /query/sessions                  — list sessions (optionally by scenario)
  GET    /query/sessions/{session_id}     — get a specific session (cross-partition)
  PUT    /query/sessions                  — upsert a session document
  DELETE /query/sessions/{session_id}     — delete a session
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from stores import get_document_store, DocumentStore

logger = logging.getLogger("graph-query-api.sessions")

router = APIRouter(prefix="/query", tags=["sessions"])

SESSIONS_DATABASE = "interactions"
SESSIONS_CONTAINER = "interactions"


def _get_store() -> DocumentStore:
    return get_document_store(
        SESSIONS_DATABASE, SESSIONS_CONTAINER, "/scenario",
        ensure_created=True,
    )


@router.get("/sessions", summary="List sessions from Cosmos DB")
async def list_sessions(
    scenario: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List sessions, optionally filtered by scenario. Newest first."""
    store = _get_store()

    query = "SELECT * FROM c"
    params: list[dict] = []
    if scenario:
        query += " WHERE c.scenario = @scenario"
        params.append({"name": "@scenario", "value": scenario})
    query += f" ORDER BY c.created_at DESC OFFSET 0 LIMIT {int(limit)}"

    items = await store.list(
        query=query,
        parameters=params or None,
        partition_key=scenario,
    )
    return {"sessions": items}


@router.get("/sessions/{session_id}", summary="Get a session by ID")
async def get_session(session_id: str):
    """Get a specific session by ID (cross-partition query)."""
    store = _get_store()
    items = await store.list(
        query="SELECT * FROM c WHERE c.id = @id",
        parameters=[{"name": "@id", "value": session_id}],
    )
    if not items:
        raise HTTPException(404, "Session not found in Cosmos")
    return items[0]


@router.put("/sessions", summary="Upsert a session document")
async def upsert_session(request: Request):
    """Upsert a raw session dict into Cosmos. No schema validation."""
    body = await request.json()
    if "id" not in body or "scenario" not in body:
        raise HTTPException(400, "Session document must have 'id' and 'scenario'")
    store = _get_store()
    await store.upsert(body)
    return {"ok": True, "id": body["id"]}


@router.delete("/sessions/{session_id}", summary="Delete a session")
async def delete_session(
    session_id: str,
    scenario: str = Query(default=""),
):
    """Delete a session by ID. Requires scenario for partition key routing."""
    store = _get_store()
    try:
        pk = scenario or None
        if pk:
            await store.delete(session_id, partition_key=pk)
        else:
            # Cross-partition: find the session first to get its scenario
            items = await store.list(
                query="SELECT c.id, c.scenario FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": session_id}],
            )
            if items:
                await store.delete(session_id, partition_key=items[0].get("scenario", ""))
    except (KeyError, ValueError):
        pass  # Not found — idempotent delete
    except Exception as e:
        logger.exception("Failed to delete session %s", session_id)
        raise HTTPException(500, f"Delete failed: {type(e).__name__}")
    return {"deleted": session_id}
