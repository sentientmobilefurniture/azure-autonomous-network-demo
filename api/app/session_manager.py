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
from app.agent_loader import get_agent
from app.streaming import stream_agent_to_sse
from agent_framework import AgentSession

# After merge, graph-query-api routes run in-process at the same port
_GQ_BASE = os.getenv("GRAPH_QUERY_API_URI", "http://localhost:8000")

logger = logging.getLogger(__name__)

MAX_ACTIVE_SESSIONS = int(os.getenv("MAX_ACTIVE_SESSIONS", "8"))
MAX_RECENT_SESSIONS = 100  # in-memory cache of completed sessions


def _parse_data(event: dict) -> dict:
    """Extract the parsed data payload from an SSE event dict."""
    raw = event.get("data", "{}")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Malformed JSON in event data: %s", raw[:200])
            return {}
    return raw


class SessionManager:
    """Registry of active and recently-completed sessions."""

    def __init__(self):
        self._active: dict[str, Session] = {}
        self._recent: OrderedDict[str, Session] = OrderedDict()

    async def recover_from_cosmos(self):
        """On startup, mark any in_progress sessions in Cosmos as failed.

        Called once from the FastAPI lifespan hook. Does not re-hydrate
        sessions into _active (the orchestrator threads are dead).
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{_GQ_BASE}/query/sessions",
                    params={"limit": 200},
                )
                resp.raise_for_status()
            # Guard against empty response body (graph-query-api may return
            # 200 with no body if Cosmos is not yet initialised).
            body = resp.text.strip()
            if not body:
                logger.info("Session recovery: empty response from graph-query-api (no sessions)")
                return
            sessions = resp.json().get("sessions", [])
            for s in sessions:
                if s.get("status") == "in_progress":
                    s["status"] = "failed"
                    s["error_detail"] = (
                        "Session was in progress when the server restarted. "
                        "The investigation cannot be resumed."
                    )
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            await client.put(
                                f"{_GQ_BASE}/query/sessions",
                                json=s,
                            )
                        logger.info(
                            "Recovered session %s: marked as failed", s["id"]
                        )
                    except Exception:
                        logger.warning(
                            "Failed to recover session %s", s.get("id")
                        )
        except Exception:
            logger.exception("Startup session recovery failed")

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
        elif session.error_detail:
            # Error takes precedence — even if a partial diagnosis exists,
            # the investigation did not complete successfully.
            session.status = SessionStatus.FAILED
            self._move_to_recent(session)
        else:
            session.status = SessionStatus.COMPLETED
            # Do NOT auto-persist — user must explicitly save.
            # Keep idle timeout as safety net: persist after 10 min if not saved.
            self._schedule_idle_timeout(session)

    async def save_session(self, session_id: str) -> bool:
        """Explicitly persist a session to Cosmos DB (user-triggered)."""
        session = self.get(session_id)
        if not session:
            return False
        await self._persist_to_cosmos(session)
        return True

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
        """Launch the agent for this session in a background task."""
        # Push initial user message to event_log so the first turn is
        # structurally consistent with follow-up turns (H-MODEL-01).
        session.push_event({
            "event": "user_message",
            "turn": 0,
            "data": json.dumps({"text": session.alert_text}),
        })
        session.status = SessionStatus.IN_PROGRESS

        async def _run():
            try:
                agent = get_agent()
                async for event in stream_agent_to_sse(
                    agent, session.alert_text
                ):
                    session.push_event(event)

                    # Track structured data as events arrive
                    ev_type = event.get("event")
                    if ev_type == "tool_call.complete":
                        data = _parse_data(event)
                        session.steps.append(data)
                    elif ev_type == "message.complete":
                        data = _parse_data(event)
                        session.diagnosis = data.get("text", "")
                    elif ev_type == "run.complete":
                        data = _parse_data(event)
                        session.run_meta = data
                    elif ev_type == "error":
                        data = _parse_data(event)
                        session.error_detail = data.get("message", "")
                    elif ev_type == "session.created":
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

        Re-uses the AgentSession for context continuity.
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
                agent = get_agent()
                # Restore AgentSession from thread_id for multi-turn continuity
                agent_session = None
                if session.thread_id:
                    agent_session = AgentSession(
                        session_id=session.thread_id,
                    )

                async for event in stream_agent_to_sse(
                    agent, follow_up_text, session=agent_session
                ):
                    # Tag events with turn number
                    event["turn"] = session.turn_count
                    session.push_event(event)

                    ev_type = event.get("event")
                    if ev_type == "tool_call.complete":
                        data = _parse_data(event)
                        session.steps.append(data)
                    elif ev_type == "message.complete":
                        data = _parse_data(event)
                        session.diagnosis = data.get("text", "")
                    elif ev_type == "run.complete":
                        data = _parse_data(event)
                        session.run_meta = data
                    elif ev_type == "error":
                        data = _parse_data(event)
                        session.error_detail = data.get("message", "")
                    elif ev_type == "session.created":
                        data = _parse_data(event)
                        new_tid = data.get("thread_id")
                        if new_tid and new_tid != session.thread_id:
                            logger.info(
                                "Session %s thread_id updated: %s → %s",
                                session.id, session.thread_id, new_tid,
                            )
                            session.thread_id = new_tid

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
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.put(
                        f"{_GQ_BASE}/query/sessions",
                        json=session.to_dict(),
                    )
                    resp.raise_for_status()
                logger.info("Persisted session %s to Cosmos", session.id)
                return
            except Exception:
                if attempt < max_attempts:
                    delay = 2 ** attempt  # 2s, 4s
                    logger.warning(
                        "Persist attempt %d/%d failed for session %s, retrying in %ds",
                        attempt, max_attempts, session.id, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.exception(
                        "All %d persist attempts failed for session %s — "
                        "session remains in memory until next finalize or restart",
                        max_attempts, session.id,
                    )


# Module-level singleton
session_manager = SessionManager()
