"""
SessionManager — registry of active and recently-completed sessions.

Owns the lifecycle of investigation sessions:
  - Create sessions and launch orchestrator tasks
  - Track active sessions in memory
  - Move completed sessions to a recent cache
  - Persist finalized sessions to Cosmos DB
  - Support multi-turn follow-up messages

See documentation/persistent.md §3.2 for the full design.
"""

import asyncio
import json
import logging
import os
from collections import OrderedDict
from typing import Optional

import httpx

from app.sessions import Session, SessionStatus
from app.orchestrator import run_orchestrator_session

# graph-query-api runs alongside the API in the same container (supervisord)
_GQ_BASE = os.getenv("GRAPH_QUERY_API_URI", "http://localhost:8100")

logger = logging.getLogger(__name__)

MAX_ACTIVE_SESSIONS = int(os.getenv("MAX_ACTIVE_SESSIONS", "8"))
MAX_RECENT_SESSIONS = 100  # in-memory cache of completed sessions


def _parse_data(event: dict) -> dict:
    """Extract the parsed data payload from an SSE event dict."""
    raw = event.get("data", "{}")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


class SessionManager:
    """Registry of active and recently-completed sessions."""

    def __init__(self):
        self._active: dict[str, Session] = {}
        self._recent: OrderedDict[str, Session] = OrderedDict()

    def create(self, scenario: str, alert_text: str) -> Session:
        if len(self._active) >= MAX_ACTIVE_SESSIONS:
            raise RuntimeError("Too many concurrent sessions")

        session = Session(scenario=scenario, alert_text=alert_text)
        self._active[session.id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._active.get(session_id) or self._recent.get(session_id)

    def list_all(self, scenario: str = None) -> list[dict]:
        """Return summary of all sessions (active first, then recent)."""
        results = []
        for s in self._active.values():
            if scenario and s.scenario != scenario:
                continue
            results.append({
                "id": s.id,
                "scenario": s.scenario,
                "alert_text": s.alert_text[:100],
                "status": s.status.value,
                "step_count": len(s.steps),
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            })
        for s in reversed(self._recent.values()):
            if scenario and s.scenario != scenario:
                continue
            results.append({
                "id": s.id,
                "scenario": s.scenario,
                "alert_text": s.alert_text[:100],
                "status": s.status.value,
                "step_count": len(s.steps),
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            })
        return results

    async def list_all_with_history(self, scenario: str = None, limit: int = 50) -> list[dict]:
        """Return sessions from in-memory cache + Cosmos DB (for history)."""
        # In-memory first (active + recent)
        mem_sessions = self.list_all(scenario)
        mem_ids = {s["id"] for s in mem_sessions}

        # Backfill from Cosmos DB via graph-query-api
        try:
            params = {"limit": limit}
            if scenario:
                params["scenario"] = scenario
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{_GQ_BASE}/query/sessions", params=params,
                )
                resp.raise_for_status()
            cosmos_items = resp.json().get("sessions", [])
            for item in cosmos_items:
                if item.get("id") not in mem_ids:
                    mem_sessions.append({
                        "id": item["id"],
                        "scenario": item.get("scenario", ""),
                        "alert_text": (item.get("alert_text", "") or "")[:100],
                        "status": item.get("status", "completed"),
                        "step_count": len(item.get("steps", [])),
                        "created_at": item.get("created_at", ""),
                        "updated_at": item.get("updated_at", ""),
                    })
        except Exception:
            logger.exception("Failed to load historical sessions from Cosmos")

        return mem_sessions

    def _finalize_turn(self, session: Session):
        """Called after each orchestrator turn completes.

        Marks the session as COMPLETED (awaiting follow-up) rather than
        moving it out of _active. The session stays active between
        turns so that send_follow_up can re-use it.

        Sessions are only moved to _recent when explicitly closed
        or when the idle timeout fires.
        """
        if session._cancel_event.is_set():
            session.status = SessionStatus.CANCELLED
            self._move_to_recent(session)
        elif session.error_detail and not session.diagnosis:
            session.status = SessionStatus.FAILED
            self._move_to_recent(session)
        else:
            session.status = SessionStatus.COMPLETED
            # Persist immediately so session survives container restarts
            asyncio.create_task(self._persist_to_cosmos(session))
            # Start idle timeout — if no follow-up within 10 minutes,
            # finalize and persist.
            self._schedule_idle_timeout(session)

    def _move_to_recent(self, session: Session):
        """Move session from active to recent cache + persist to Cosmos."""
        self._active.pop(session.id, None)
        self._recent[session.id] = session
        if len(self._recent) > MAX_RECENT_SESSIONS:
            self._recent.popitem(last=False)
        # Persist to Cosmos (fire and forget)
        asyncio.create_task(self._persist_to_cosmos(session))

    def _schedule_idle_timeout(self, session: Session, timeout: float = 600):
        """Auto-finalize session if no follow-up arrives within timeout seconds."""
        async def _idle_watch():
            await asyncio.sleep(timeout)
            # Only finalize if still in COMPLETED (idle) state — not if
            # a follow-up moved it back to IN_PROGRESS.
            if session.id in self._active and session.status == SessionStatus.COMPLETED:
                logger.info("Session %s idle for %ds, finalizing", session.id, timeout)
                self._move_to_recent(session)
        # Cancel any existing idle task
        if hasattr(session, '_idle_task') and session._idle_task:
            session._idle_task.cancel()
        session._idle_task = asyncio.create_task(_idle_watch())

    async def start(self, session: Session):
        """Launch the orchestrator for this session in a background task."""
        session.status = SessionStatus.IN_PROGRESS

        async def _run():
            try:
                async for event in run_orchestrator_session(
                    session.alert_text, session._cancel_event
                ):
                    session.push_event(event)

                    # Track structured data as events arrive
                    ev_type = event.get("event")
                    if ev_type == "step_complete":
                        data = _parse_data(event)
                        session.steps.append(data)
                    elif ev_type == "message":
                        data = _parse_data(event)
                        session.diagnosis = data.get("text", "")
                    elif ev_type == "run_complete":
                        data = _parse_data(event)
                        session.run_meta = data
                    elif ev_type == "error":
                        data = _parse_data(event)
                        session.error_detail = data.get("message", "")
                    elif ev_type == "thread_created":
                        data = _parse_data(event)
                        session.thread_id = data.get("thread_id")

            except Exception as e:
                logger.exception("Session %s failed", session.id)
                session.status = SessionStatus.FAILED
                session.error_detail = str(e)
                session.push_event({
                    "event": "error",
                    "data": json.dumps({"message": str(e)})
                })
            finally:
                self._finalize_turn(session)

        asyncio.create_task(_run())

    async def continue_session(self, session: Session, follow_up_text: str):
        """Send a follow-up message to an existing session.

        Re-uses the Foundry thread for context continuity.
        Cancels any pending idle timeout.
        """
        if hasattr(session, '_idle_task') and session._idle_task:
            session._idle_task.cancel()

        # Reset cancel flag from any prior turn so the new run isn't
        # immediately aborted.
        session._cancel_event.clear()

        session.status = SessionStatus.IN_PROGRESS
        session.error_detail = ""  # Reset per-turn error

        async def _run():
            try:
                async for event in run_orchestrator_session(
                    follow_up_text,
                    session._cancel_event,
                    existing_thread_id=session.thread_id,
                ):
                    # Tag events with turn number
                    event["turn"] = session.turn_count
                    session.push_event(event)

                    ev_type = event.get("event")
                    if ev_type == "step_complete":
                        data = _parse_data(event)
                        session.steps.append(data)
                    elif ev_type == "message":
                        data = _parse_data(event)
                        session.diagnosis = data.get("text", "")
                    elif ev_type == "run_complete":
                        data = _parse_data(event)
                        session.run_meta = data
                    elif ev_type == "error":
                        data = _parse_data(event)
                        session.error_detail = data.get("message", "")

            except Exception as e:
                logger.exception("Session %s turn %d failed", session.id, session.turn_count)
                session.status = SessionStatus.FAILED
                session.error_detail = str(e)
                session.push_event({
                    "event": "error",
                    "data": json.dumps({"message": str(e)})
                })
            finally:
                self._finalize_turn(session)

        asyncio.create_task(_run())

    async def _persist_to_cosmos(self, session: Session):
        """Persist a finalized session to Cosmos DB via graph-query-api."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.put(
                    f"{_GQ_BASE}/query/sessions",
                    json=session.to_dict(),
                )
                resp.raise_for_status()
            logger.info("Persisted session %s to Cosmos", session.id)
        except Exception:
            logger.exception("Failed to persist session %s", session.id)


# Module-level singleton
session_manager = SessionManager()
