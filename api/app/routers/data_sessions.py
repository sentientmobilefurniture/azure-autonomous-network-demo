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

from app.stores import get_document_store, DocumentStore

logger = logging.getLogger("graph-query-api.sessions")

router = APIRouter(prefix="/query", tags=["sessions"])

SESSIONS_DATABASE = "interactions"
SESSIONS_CONTAINER = "interactions"


def _get_store() -> DocumentStore:
    return get_document_store(
        SESSIONS_DATABASE, SESSIONS_CONTAINER, "/scenario",
        ensure_created=False,
    )


@router.get("/sessions", summary="List sessions from Cosmos DB")
async def list_sessions(
    scenario: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List sessions, optionally filtered by scenario. Newest first."""
    store = _get_store()

    query = "SELECT * FROM c WHERE (c._docType = 'session' OR NOT IS_DEFINED(c._docType))"
    params: list[dict] = []
    if scenario:
        query += " AND c.scenario = @scenario"
        params.append({"name": "@scenario", "value": scenario})
    query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
    params.append({"name": "@limit", "value": int(limit)})

    items = await store.list(
        query=query,
        parameters=params or None,
        partition_key=scenario,
    )
    return {"sessions": items}


@router.get("/sessions/{session_id}", summary="Get a session by ID")
async def get_session(session_id: str):
    """Get a specific session by ID. Reconstructs event_log from chunks."""
    store = _get_store()
    # Load manifest
    manifests = await store.list(
        query="SELECT * FROM c WHERE c.id = @id AND (c._docType = 'session' OR NOT IS_DEFINED(c._docType))",
        parameters=[{"name": "@id", "value": session_id}],
    )
    if not manifests:
        raise HTTPException(404, "Session not found in Cosmos")
    manifest = manifests[0]

    # Load chunks
    chunk_count = manifest.get("chunk_count", 0)
    if chunk_count > 0:
        chunks = await store.list(
            query="SELECT * FROM c WHERE c.session_id = @sid AND c._docType = 'session_chunk' ORDER BY c.chunk_index",
            parameters=[{"name": "@sid", "value": session_id}],
            partition_key=manifest.get("scenario"),
        )
        event_log = []
        for chunk in sorted(chunks, key=lambda c: c.get("chunk_index", 0)):
            event_log.extend(chunk.get("events", []))
        manifest["event_log"] = event_log
        if len(chunks) < chunk_count:
            manifest["partial"] = True
    elif "event_log" not in manifest:
        manifest["event_log"] = []

    return manifest


CHUNK_SIZE = 100  # events per chunk


@router.put("/sessions", summary="Upsert a session document")
async def upsert_session(request: Request):
    """Upsert a session with chunked event_log persistence."""
    body = await request.json()
    if "id" not in body or "scenario" not in body:
        raise HTTPException(400, "Session document must have 'id' and 'scenario'")
    store = _get_store()

    event_log = body.pop("event_log", [])
    steps = body.pop("steps", [])

    # Split event_log into chunks
    chunks = [event_log[i:i + CHUNK_SIZE] for i in range(0, len(event_log), CHUNK_SIZE)] if event_log else [[]]

    chunk_ids = []
    for idx, chunk_events in enumerate(chunks):
        chunk_id = f"{body['id']}:chunk-{idx}"
        chunk_ids.append(chunk_id)
        await store.upsert({
            "id": chunk_id,
            "_docType": "session_chunk",
            "session_id": body["id"],
            "scenario": body["scenario"],
            "chunk_index": idx,
            "events": chunk_events,
        })

    # Delete any orphaned chunks from prior saves with more chunks
    old_chunks = await store.list(
        query="SELECT c.id, c.chunk_index FROM c WHERE c.session_id = @sid AND c._docType = 'session_chunk' AND c.chunk_index >= @max_idx",
        parameters=[
            {"name": "@sid", "value": body["id"]},
            {"name": "@max_idx", "value": len(chunks)},
        ],
        partition_key=body["scenario"],
    )
    for oc in old_chunks:
        try:
            await store.delete(oc["id"], partition_key=body["scenario"])
        except Exception:
            pass

    # Upsert manifest (without event_log)
    body["_docType"] = "session"
    body["chunk_count"] = len(chunks)
    body["chunk_ids"] = chunk_ids
    body["steps"] = steps  # keep steps on manifest (small)
    await store.upsert(body)
    return {"ok": True, "id": body["id"], "chunks": len(chunks)}


@router.delete("/sessions/{session_id}", summary="Delete a session")
async def delete_session(
    session_id: str,
    scenario: str = Query(default=""),
):
    """Delete a session and all its chunks by ID."""
    store = _get_store()
    try:
        pk = scenario or None
        if not pk:
            # Cross-partition: find the session first to get its scenario
            items = await store.list(
                query="SELECT c.id, c.scenario FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": session_id}],
            )
            if items:
                pk = items[0].get("scenario", "")

        # Delete chunks first
        if pk:
            chunks = await store.list(
                query="SELECT c.id FROM c WHERE c.session_id = @sid AND c._docType = 'session_chunk'",
                parameters=[{"name": "@sid", "value": session_id}],
                partition_key=pk,
            )
            for chunk in chunks:
                try:
                    await store.delete(chunk["id"], partition_key=pk)
                except Exception:
                    pass

        # Delete manifest
        if pk:
            await store.delete(session_id, partition_key=pk)
    except (KeyError, ValueError):
        pass  # Not found — idempotent delete
    except Exception as e:
        logger.exception("Failed to delete session %s", session_id)
        raise HTTPException(500, f"Delete failed: {type(e).__name__}")
    return {"deleted": session_id}
