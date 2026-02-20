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
import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import httpx

from app.sessions import SessionStatus
from app.session_manager import session_manager

_GQ_BASE = os.getenv("GRAPH_QUERY_API_URI", "http://localhost:8000")


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    scenario: str
    alert_text: str


@router.post("")
async def create_session(req: CreateSessionRequest):
    """Create a new investigation session and start the orchestrator."""
    try:
        session = session_manager.create(req.scenario, req.alert_text)
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    await session_manager.start(session)
    return {"session_id": session.id, "status": session.status.value}


@router.get("")
async def list_sessions(scenario: str = Query(default=None)):
    """List all sessions (active + recent + Cosmos DB history)."""
    sessions = await session_manager.list_all_with_history(scenario)
    return {"sessions": sessions}


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get full session state — checks memory first, then Cosmos DB."""
    session = session_manager.get(session_id)
    if session:
        return session.to_dict()

    # Fallback: load from Cosmos DB via graph-query-api
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{_GQ_BASE}/query/sessions/{session_id}")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass

    raise HTTPException(404, "Session not found")


@router.get("/{session_id}/stream")
async def stream_session(session_id: str, since: int = Query(default=0, ge=0)):
    """SSE stream: replays past events then tails live events.

    Query params:
        since — event index to start from (skip earlier events).
               Used by follow-up turns so only new-turn events are
               replayed, avoiding the prior diagnosis being echoed.

    Safe to call multiple times — each call gets the history
    (from ``since``) plus any new events. Closes when session completes.
    """
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    async def _generate():
        history, live_queue = session.subscribe(since_index=since)
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
                        # Allow in-flight call_soon_threadsafe callbacks
                        # to land before draining the queue.
                        await asyncio.sleep(0.05)
                        while not live_queue.empty():
                            yield live_queue.get_nowait()
                        break

            # Signal the client that this turn is done — prevents
            # fetchEventSource from treating the TCP close as an error
            # and retrying in a loop.
            yield {"event": "done", "data": json.dumps({"status": session.status.value})}
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
        "event": "status",
        "data": json.dumps({
            "status": "cancelling",
            "message": "Cancellation requested — waiting for current agent call to finish.",
        }),
    })
    return {"status": "cancelling"}


@router.post("/{session_id}/save")
async def save_session(session_id: str):
    """Explicitly persist a session to Cosmos DB (user-triggered)."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    ok = await session_manager.save_session(session_id)
    if not ok:
        raise HTTPException(500, "Save failed")
    return {"saved": session_id}


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

    # Capture the event log length *before* adding user message + starting
    # the new turn.  The frontend passes this as ``since`` to the SSE
    # stream so it only receives events from the new turn.
    event_offset = session.event_count

    # Record the user message as an event
    session.turn_count += 1
    session.push_event({
        "event": "user_message",
        "turn": session.turn_count,
        "data": json.dumps({"text": req.text}),
    })

    await session_manager.continue_session(session, req.text)
    return {
        "status": "processing",
        "turn": session.turn_count,
        "event_offset": event_offset,
    }


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

    # Also delete from Cosmos DB via graph-query-api
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.delete(
                f"{_GQ_BASE}/query/sessions/{session_id}",
                params={"scenario": scenario} if scenario else {},
            )
    except Exception:
        pass  # Best effort — may not exist in Cosmos yet

    return {"deleted": session_id}
