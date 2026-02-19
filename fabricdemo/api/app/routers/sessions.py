"""
Sessions router — REST/SSE endpoints for persistent investigation sessions.

Endpoints:
  POST  /api/sessions              — Create a new session and start orchestrator
  GET   /api/sessions              — List all sessions (active + recent)
  GET   /api/sessions/{id}         — Get full session state + events
  GET   /api/sessions/{id}/stream  — SSE: replay past events + live tail
  POST  /api/sessions/{id}/cancel  — Cancel a running session
  POST  /api/sessions/{id}/message — Send a follow-up message (multi-turn)

See documentation/persistent.md §3.3 for the full design.
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.sessions import SessionStatus
from app.session_manager import session_manager


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    scenario: str
    alert_text: str


@router.post("")
async def create_session(req: CreateSessionRequest):
    """Create a new investigation session and start the orchestrator."""
    session = session_manager.create(req.scenario, req.alert_text)
    await session_manager.start(session)
    return {"session_id": session.id, "status": session.status.value}


@router.get("")
async def list_sessions(scenario: str = Query(default=None)):
    """List all sessions (active + recent)."""
    return {"sessions": session_manager.list_all(scenario)}


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get full session state including all events."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.to_dict()


@router.get("/{session_id}/stream")
async def stream_session(session_id: str):
    """SSE stream: replays all past events then tails live events.

    Safe to call multiple times — each call gets the full history
    plus any new events. Closes when session completes.
    """
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    async def _generate():
        history, live_queue = session.subscribe()
        try:
            # Phase 1: replay all buffered events
            for event in history:
                yield event

            # Phase 2: tail live events until session ends
            if session.status == SessionStatus.IN_PROGRESS:
                while True:
                    try:
                        event = await asyncio.wait_for(
                            live_queue.get(), timeout=120
                        )
                        yield event
                    except asyncio.TimeoutError:
                        # Session might be stuck — emit heartbeat
                        yield {"event": "heartbeat", "data": "{}"}
                        if session.status != SessionStatus.IN_PROGRESS:
                            break
                    if session.status != SessionStatus.IN_PROGRESS:
                        # Drain remaining events
                        while not live_queue.empty():
                            yield live_queue.get_nowait()
                        break
        finally:
            session.unsubscribe(live_queue)

    return EventSourceResponse(_generate())


@router.post("/{session_id}/cancel")
async def cancel_session(session_id: str):
    """Request cancellation of a running session."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status != SessionStatus.IN_PROGRESS:
        return {"status": session.status.value, "message": "Not running"}
    session._cancel_event.set()
    # Push a status event so SSE clients see immediate feedback
    session.push_event({
        "event": "status_change",
        "data": json.dumps({
            "status": "cancelling",
            "message": "Cancellation requested — waiting for current agent call to finish.",
        }),
    })
    return {"status": "cancelling"}


class FollowUpRequest(BaseModel):
    text: str


@router.post("/{session_id}/message")
async def send_follow_up(session_id: str, req: FollowUpRequest):
    """Send a follow-up message within an existing session."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status == SessionStatus.IN_PROGRESS:
        raise HTTPException(409, "Session is already processing a turn")
    if not session.thread_id:
        raise HTTPException(400, "Session has no Foundry thread (cannot follow up)")

    # Record the user message as an event
    session.turn_count += 1
    session.push_event({
        "event": "user_message",
        "turn": session.turn_count,
        "data": json.dumps({"text": req.text}),
    })

    await session_manager.continue_session(session, req.text)
    return {"status": "processing", "turn": session.turn_count}


@router.delete("/{session_id}")
async def delete_session(session_id: str, scenario: str = Query(default="")):
    """Delete a session from in-memory cache and Cosmos DB."""
    session = session_manager.get(session_id)
    if session:
        # Cancel if running
        if session.status == SessionStatus.IN_PROGRESS:
            session._cancel_event.set()
        # Remove from in-memory caches
        session_manager._active.pop(session_id, None)
        session_manager._recent.pop(session_id, None)

    # Also delete from Cosmos DB
    try:
        from stores import get_document_store
        store = get_document_store(
            "interactions", "interactions", "/scenario",
            ensure_created=True,
        )
        await store.delete(session_id, partition_key=scenario or None)
    except Exception:
        pass  # Best effort — may not exist in Cosmos yet

    return {"deleted": session_id}
