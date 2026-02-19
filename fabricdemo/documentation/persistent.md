# Persistent Async Conversations — Design Plan

> **Problem:** When the UI shows an investigation as "interrupted" (e.g., 2-minute timeout, client-side abort, or browser navigation), the backend orchestrator thread and its Foundry API calls continue running to completion. The SSE connection is severed, so steps and the final diagnosis are silently lost. The user sees an error, but the backend may actually succeed minutes later with a valid result.

> **Goal:** Decouple investigation lifecycle from the SSE connection. Every investigation runs as a server-side session that persists independently of the frontend. The UI can reconnect, poll, or browse investigations — similar to how GitHub Copilot tracks in-progress agent sessions and lets you revisit them.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                        │
│                                                                 │
│  ChatInput ──▶ POST /api/sessions ──▶ { session_id }           │
│                                                                 │
│  SessionSidebar ◀── GET /api/sessions (all sessions)           │
│    • Shows: in_progress ⏳ | completed ✓ | failed ✗            │
│    • Click to view any session (live or finished)               │
│                                                                 │
│  ChatPanel ◀── GET /api/sessions/{id}/stream (SSE)             │
│    • Reconnectable — replays buffered events + live tail        │
│    • Live dot indicator for in_progress sessions                │
│    • Diagnosis rendered inline within orchestrator bubble       │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Server (FastAPI)                        │
│                                                                 │
│  SessionManager (in-memory registry of active sessions)         │
│    • sessions: dict[session_id, Session]                        │
│    • Session holds: asyncio.Queue, event_log[], status, meta    │
│                                                                 │
│  POST /api/sessions         — create session, start background  │
│  GET  /api/sessions         — list all (active + recent)        │
│  GET  /api/sessions/{id}    — get session state + full events   │
│  GET  /api/sessions/{id}/stream — SSE: replay + live tail       │
│  POST /api/sessions/{id}/cancel — cancel a running session      │
│                                                                 │
│  Orchestrator thread runs to completion regardless of SSE       │
│  connection. Events are buffered in Session.event_log[].        │
│  On completion, session is persisted to Cosmos DB.              │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│               Cosmos DB (interactions container)                 │
│                                                                 │
│  Same schema as current Interaction documents, extended with:   │
│    • status: "in_progress" | "completed" | "failed" | "cancelled"│
│    • events: full event log (step_start, step_complete, etc.)   │
│    • updated_at: last event timestamp                           │
│    • error_detail: if failed                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Why This Matters (Current Failure Mode)

**Today's flow:**

1. `POST /api/alert` → opens SSE stream → `EventSourceResponse(run_orchestrator(alert))`
2. `run_orchestrator()` spawns a **daemon thread** running the Foundry SDK
3. The thread pushes events to an `asyncio.Queue`
4. The SSE generator reads from the queue and yields to the client
5. If the client disconnects (timeout, abort, navigation), the SSE generator stops reading from the queue
6. **But the daemon thread keeps running** — it's holding an open Foundry `stream.until_done()` call
7. The Foundry API calls continue (visible in the Graph API logs as you observed)
8. Completed results are never delivered to any client

**With persistent sessions:**

- The daemon thread writes to `Session.event_log[]` (not just a transient queue)
- SSE clients subscribe to the session and can reconnect at any time
- The sidebar shows real-time status of all sessions
- Past sessions (completed or failed) are browsable from Cosmos DB

---

## 3. Detailed Design

### 3.1 Backend: Session Model

```python
# api/app/sessions.py

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import asyncio
import uuid
import threading


class SessionStatus(str, Enum):
    PENDING = "pending"              # Created but orchestrator not yet started
    IN_PROGRESS = "in_progress"      # Orchestrator thread is running
    COMPLETED = "completed"          # Final message received
    FAILED = "failed"                # Error or timeout
    CANCELLED = "cancelled"          # User-initiated cancellation


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario: str = ""
    alert_text: str = ""
    status: SessionStatus = SessionStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Accumulated event log — survives client disconnects
    event_log: list[dict] = field(default_factory=list)

    # Extracted final data (populated on completion)
    steps: list[dict] = field(default_factory=list)
    diagnosis: str = ""
    run_meta: Optional[dict] = None
    error_detail: str = ""

    # Multi-turn support (see §13)
    thread_id: Optional[str] = None        # Foundry thread ID — persists across turns
    turn_count: int = 0                     # Each user→orchestrator exchange = 1 turn

    # Runtime (not persisted)
    _subscribers: list[asyncio.Queue] = field(
        default_factory=list, repr=False
    )
    _thread: Optional[threading.Thread] = field(default=None, repr=False)
    _cancel_event: threading.Event = field(
        default_factory=threading.Event, repr=False
    )
    _idle_task: Optional[asyncio.Task] = field(default=None, repr=False)

    # Threading lock — protects _subscribers and event_log against
    # concurrent access from the orchestrator thread and asyncio loop.
    # Mirrors the LogBroadcaster pattern (log_broadcaster.py).
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # The asyncio event loop — needed for thread-safe queue delivery.
    _loop: Optional[asyncio.AbstractEventLoop] = field(default=None, repr=False)

    def push_event(self, event: dict):
        """Append to log and fan out to all live SSE subscribers.

        Thread-safe: called from the orchestrator's background thread.
        Uses loop.call_soon_threadsafe() to safely enqueue to asyncio.Queues,
        matching the pattern in LogBroadcaster.broadcast().
        """
        with self._lock:
            self.event_log.append(event)
            self.updated_at = datetime.now(timezone.utc).isoformat()
            snapshot = list(self._subscribers)
        dead: list[asyncio.Queue] = []
        for q in snapshot:
            try:
                if self._loop is not None and self._loop.is_running():
                    self._loop.call_soon_threadsafe(q.put_nowait, event)
                else:
                    q.put_nowait(event)
            except (asyncio.QueueFull, RuntimeError):
                dead.append(q)
        if dead:
            with self._lock:
                for q in dead:
                    try:
                        self._subscribers.remove(q)
                    except ValueError:
                        pass

    def subscribe(self) -> tuple[list[dict], asyncio.Queue]:
        """Return (existing_events, live_queue) for SSE replay + tail.

        Atomic: snapshot and subscriber registration happen under the same
        lock, so no event can fall between the snapshot and the queue.
        """
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            if self._loop is None:
                self._loop = loop
            snapshot = list(self.event_log)
            self._subscribers.append(q)
        return snapshot, q

    def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def to_dict(self) -> dict:
        """Serialise for API response / Cosmos persistence."""
        return {
            "id": self.id,
            "scenario": self.scenario,
            "alert_text": self.alert_text,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "event_log": self.event_log,
            "steps": self.steps,
            "diagnosis": self.diagnosis,
            "run_meta": self.run_meta,
            "error_detail": self.error_detail,
            "thread_id": self.thread_id,
            "turn_count": self.turn_count,
        }
```

### 3.2 Backend: SessionManager

```python
# api/app/session_manager.py

import asyncio
import logging
from collections import OrderedDict
from typing import Optional

import json

from app.sessions import Session, SessionStatus
from app.orchestrator import run_orchestrator_session

logger = logging.getLogger(__name__)

MAX_ACTIVE_SESSIONS = 20   # prevent runaway resource usage
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

    def _finalize_turn(self, session: Session):
        """Called after each orchestrator turn completes.

        Marks the session as IDLE (awaiting follow-up) rather than
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
        """Persist a finalized session to Cosmos DB."""
        try:
            # Uses the same DocumentStore as router_interactions
            from stores import get_document_store
            store = get_document_store(
                "interactions", "interactions", "/scenario",
                ensure_created=True,
            )
            await store.upsert(session.to_dict())
            logger.info("Persisted session %s to Cosmos", session.id)
        except Exception:
            logger.exception("Failed to persist session %s", session.id)


# Module-level singleton
session_manager = SessionManager()
```

### 3.3 Backend: New API Routes

```python
# api/app/routers/sessions.py

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
        "data": json.dumps({"status": "cancelling",
                            "message": "Cancellation requested — waiting for current agent call to finish."}),
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
```

### 3.4 Orchestrator Changes

The current `run_orchestrator()` function needs a minimal refactor to support cancellation awareness:

```python
# Changes to api/app/orchestrator.py

async def run_orchestrator_session(
    alert_text: str,
    cancel_event: threading.Event = None,
) -> AsyncGenerator[dict, None]:
    """Same as run_orchestrator() but with:
    1. cancel_event support — checked between steps
    2. No timeout-based abort (session manager handles lifecycle)
    """
    # ... same queue/thread bridge pattern ...
    
    def _thread_target():
        # Before each run attempt, check cancellation
        if cancel_event and cancel_event.is_set():
            _put("error", {"message": "Investigation cancelled by user."})
            return
        
        # ... existing orchestrator logic ...
        # Add cancel checks between retry attempts:
        if cancel_event and cancel_event.is_set():
            _put("error", {"message": "Investigation cancelled by user."})
            break
    
    # ... yield from queue (no EVENT_TIMEOUT — session manager owns lifecycle) ...
```

### 3.5 Frontend Types & Hook

> **Note:** The flat-state hook (`steps`, `finalMessage`, etc.) from the original
> Part 1 design is **superseded** by the chat-oriented `useSession` hook in §14.
> Types and hook are defined there. This section is kept for reference only —
> see §10.1 for `ChatMessage`, `SessionSummary`, `SessionDetail` types, and
> §14 for the authoritative `useSession` hook implementation.

### 3.6 Frontend: Updated SessionSidebar

The sidebar evolves to show both **live sessions** and **completed history**:

```
┌─────────────────────┐
│      SESSIONS        │
│ ┌─────────────────┐ │
│ │ ⏳ IN PROGRESS   │ │  ← green pulsing dot
│ │ VPN-ACME-CORP   │ │
│ │ 4 steps · 45s   │ │
│ └─────────────────┘ │
│ ┌─────────────────┐ │
│ │ ✓ COMPLETED     │ │
│ │ BGP flap on PE3 │ │
│ │ 9 steps · 139s  │ │
│ └─────────────────┘ │
│ ┌─────────────────┐ │
│ │ ✗ FAILED        │ │
│ │ MPLS path down  │ │
│ │ 3 steps · 60s   │ │
│ └─────────────────┘ │
└─────────────────────┘
```

Key changes:
- **Status badges** replace the simple timestamp header
- **Live sessions** show a pulsing indicator and real-time step count
- Clicking a live session reconnects the SSE stream and shows current progress
- **Cancelled/failed** sessions are still viewable with partial results
- Sessions list is **auto-refreshed** via polling (every 5s)

---

## 4. Implementation Phases

### Phase 1: Backend Session Infrastructure (Core)
**Files:**
- `api/app/sessions.py` — Session dataclass
- `api/app/session_manager.py` — SessionManager singleton
- `api/app/routers/sessions.py` — New REST/SSE endpoints
- `api/app/orchestrator.py` — Add `run_orchestrator_session()` with cancel support
- `api/app/main.py` — Mount new router

**Key behaviors:**
- Sessions persist in memory even when no SSE clients are connected
- Orchestrator thread writes to `Session.event_log[]` instead of a transient queue
- Multiple clients can subscribe to the same session simultaneously
- Completed sessions are auto-persisted to Cosmos DB

### ~~Phase 2: Frontend Session Management~~ → Merged into Part 2 Phases 3–5

> This phase is superseded by the chat UI redesign (Part 2). The chat UI
> phases build the frontend session management directly into the chat components
> and `useSession` hook. Implementing a flat-state `useSession` hook here
> would be throwaway work replaced immediately by the chat-oriented version.
> See Part 2, Phases 3–5.

### Phase 3: Cosmos DB Persistence & Recovery
**Files:**
- `graph-query-api/router_interactions.py` — Extend schema for session fields
- `api/app/session_manager.py` — Load recent sessions from Cosmos on startup

**Key behaviors:**
- Completed sessions write to Cosmos with full event log
- On API restart, recent sessions are loaded from Cosmos into the `_recent` cache
- The `list_sessions` endpoint merges in-memory active + Cosmos history
- Backward compatible with existing `Interaction` documents

### Phase 4: Polish & Edge Cases
- **Heartbeat SSE events** — keep connection alive, detect stuck sessions
- **Session TTL** — auto-expire in-memory sessions after 1 hour
- **Concurrent session limit** — cap at 5 per scenario to prevent abuse
- **Graceful shutdown** — on SIGTERM, mark active sessions as failed and persist
- **Duplicate prevention** — debounce rapid re-submissions of the same alert

---

## 5. Migration Strategy

The transition can be **non-breaking** and incremental:

1. **Phase 1** adds the new `/api/sessions/*` endpoints alongside the existing `/api/alert` endpoint
2. **Phase 2** switches the frontend from `/api/alert` to `/api/sessions` 
3. The old `/api/alert` endpoint and `useInvestigation` hook remain functional during migration
4. Once validated, the old endpoint can be deprecated (or kept as a simpler alternative)
5. Existing Cosmos interactions remain readable — the new session schema is a superset

---

## 6. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Session storage | In-memory (active) + Cosmos (completed) | Active sessions need sub-second event delivery; Cosmos is too slow for real-time fan-out |
| Event replay | Full log stored per session | Enables reconnection at any point; events are small (~1KB each) |
| Cancellation | `threading.Event` checked between steps | Foundry SDK `stream.until_done()` is blocking; can't interrupt mid-call, but can skip retries |
| Multiple subscribers | Fan-out via `asyncio.Queue` per client | Same pattern as current `LogBroadcaster`; proven in this codebase |
| Polling vs WebSocket for session list | HTTP polling every 5s | Simpler than WebSocket; session list changes are infrequent; adequate for demo scale |
| Backward compatibility | New endpoints alongside old | Zero-risk migration; can roll back by reverting frontend only |

---

## 7. Data Flow: Before vs After

### Before (Current)
```
Browser ──SSE──▶ /api/alert ──queue──▶ OrchestratorThread
   │                                        │
   │ (disconnect)                           │ (keeps running)
   ✗ lost                                   │
                                            ▼
                                     Results discarded
```

### After (Sessions)
```
Browser ──POST──▶ /api/sessions ──▶ SessionManager.create()
   │                                     │
   │◀── { session_id } ─────────────────┘
   │
   │──SSE──▶ /api/sessions/{id}/stream
   │              │
   │ (disconnect) │  Session.event_log[] keeps accumulating
   │              │
   │──SSE──▶ /api/sessions/{id}/stream  (reconnect)
   │              │
   │◀── replay all past events + live tail
   │
   ▼
   Full investigation visible regardless of connection stability
```

---

## 8. Estimated Effort (Part 1 Only)

> **Note:** Part 1's frontend phases (Phase 2) are superseded by the chat UI
> redesign in Part 2. See §17 for the unified phase table.

| Phase | Scope | Estimate |
|---|---|---|
| Phase 1 | Backend session infra (sessions.py, session_manager.py, routers/sessions.py, orchestrator.py) | ~350 lines new Python |
| Phase 3 | Cosmos persistence + recovery | ~80 lines new Python |
| Phase 4 | Polish & edge cases | ~100 lines across backend + frontend |

All phases can be implemented incrementally with the old system running in parallel.

---
---

# Part 2: Chat-Style Conversational UI Redesign

> **Problem:** The current UI is a rigid two-panel layout (Investigation steps on the left, Diagnosis on the right). This doesn't support multi-turn conversations — the user submits one alert, gets one diagnosis, and that's it. There's no way to ask follow-up questions like "What about the BGP sessions on PE-03?" or "Can you check the SLA impact?" without starting a completely new investigation from scratch.

> **Goal:** Replace the split Investigation+Diagnosis layout with a unified **chat thread** UI — similar to GitHub Copilot's agent mode — where each turn displays the agent's work as expandable step groups, and the user can continue the conversation with follow-up prompts. The orchestrator reasoning, sub-agent calls, and final diagnosis all render inline as rich, collapsible blocks within the chat flow.

---

## 9. Current Layout vs Proposed Layout

### Current (Split Panel)
```
┌──────────────────────┬──────────────────────┬──────────┐
│    SUBMIT ALERT      │     DIAGNOSIS        │ HISTORY  │
│  ┌────────────────┐  │                      │          │
│  │ textarea       │  │  # Incident Summary  │  card 1  │
│  │ [Investigate]  │  │  At 14:31 UTC, a ... │  card 2  │
│  └────────────────┘  │  ...                 │  card 3  │
│                      │                      │          │
│  INVESTIGATION       │                      │          │
│  ◇ Orch Thoughts     │                      │          │
│  ● GraphExplorer 3.2s│                      │          │
│  ● TelemetryAgent 2s │                      │          │
│  ● RunbookKBAgent 1s │                      │          │
│  ● HistoricalTicket  │                      │          │
│  Run complete — 9    │                      │          │
└──────────────────────┴──────────────────────┴──────────┘
```

### Proposed (Chat Thread)
```
┌─────────────────────────────────────────────┬──────────┐
│                  CHAT THREAD                │ SESSIONS │
│                                             │          │
│  ┌─ YOU ──────────────────────────────────┐ │  ⏳ live │
│  │ 14:31:14.259 CRITICAL VPN-ACME-CORP   │ │  ✓ done  │
│  │ SERVICE_DEGRADATION VPN tunnel ...     │ │  ✓ done  │
│  └────────────────────────────────────────┘ │          │
│                                             │          │
│  ┌─ ORCHESTRATOR ─────────────────────────┐ │          │
│  │                                        │ │          │
│  │  ▸ Orchestrator Thoughts          [▾]  │ │          │
│  │    "To diagnose the service..."        │ │          │
│  │                                        │ │          │
│  │  ▸ GraphExplorerAgent            3.2s  │ │          │
│  │  ▸ TelemetryAgent                2.1s  │ │          │
│  │  ▸ RunbookKBAgent                1.4s  │ │          │
│  │  ▸ HistoricalTicketAgent         2.8s  │ │          │
│  │                                        │ │          │
│  │  ▾ Diagnosis                     [▾]   │ │          │
│  │  ┌──────────────────────────────────┐  │ │          │
│  │  │ # Incident Summary              │  │ │          │
│  │  │ At 14:31 UTC, a CRITICAL ...    │  │ │          │
│  │  │ ...                             │  │ │          │
│  │  └──────────────────────────────────┘  │ │          │
│  │                                        │ │          │
│  │  9 steps · 150s                  Copy  │ │          │
│  └────────────────────────────────────────┘ │          │
│                                             │          │
│  ┌─ YOU ──────────────────────────────────┐ │          │
│  │ What about the SLA impact on BIGBANK?  │ │          │
│  └────────────────────────────────────────┘ │          │
│                                             │          │
│  ┌─ ORCHESTRATOR ─────────────────────────┐ │          │
│  │  ▸ GraphExplorerAgent (SLA query) 2.5s │ │          │
│  │                                        │ │          │
│  │  ▾ Diagnosis                           │ │          │
│  │  ┌──────────────────────────────────┐  │ │          │
│  │  │ The SLA for VPN-BIGBANK is ...   │  │ │          │
│  │  └──────────────────────────────────┘  │ │          │
│  └────────────────────────────────────────┘ │          │
│                                             │          │
│  ┌──────────────────────────────────────────┤          │
│  │ Ask a follow-up...          [Send] [⏹]  │          │
│  └──────────────────────────────────────────┘          │
└─────────────────────────────────────────────┴──────────┘
```

Key differences:
- **Single column** replaces the horizontal Investigation/Diagnosis split
- User messages and orchestrator responses alternate in a **chat thread**
- Agent steps are **collapsed by default** within each orchestrator turn
- Diagnosis is rendered **inline** as an expandable section (auto-expanded on completion)
- **Input bar pinned to the bottom** (like Copilot) instead of top-of-panel
- Follow-up messages re-use the **same Foundry thread** for context continuity

---

## 10. Chat Message Model

### 10.1 Types

```typescript
// types/index.ts — additions for chat UI

export type ChatRole = 'user' | 'orchestrator';

export interface ChatMessage {
  id: string;                          // unique per message
  role: ChatRole;
  timestamp: string;                   // ISO 8601

  // User messages
  text?: string;                       // the user's input

  // Orchestrator messages
  steps?: StepEvent[];                 // sub-agent calls (expandable)
  thinking?: string[];                 // orchestrator reasoning snippets
  diagnosis?: string;                  // final markdown response
  runMeta?: RunMeta;                   // step count + elapsed
  status?: 'thinking' | 'investigating' | 'complete' | 'error';
  errorMessage?: string;
}

// A session's conversation is just an ordered list of messages
export interface SessionConversation {
  sessionId: string;
  messages: ChatMessage[];
}
```

### 10.2 How Events Map to Chat Messages

Each orchestrator "turn" (from the user hitting Send to `run_complete` / `error`) produces one `ChatMessage` with `role: 'orchestrator'`. Events accumulate into that message:

| SSE Event | ChatMessage Field |
|---|---|
| `step_thinking` | Append to `thinking[]`, set `status: 'thinking'` |
| `step_start` | Set `status: 'investigating'` |
| `step_complete` | Append to `steps[]` |
| `message` | Set `diagnosis` |
| `run_complete` | Set `runMeta`, `status: 'complete'` |
| `error` | Set `errorMessage`, `status: 'error'` |

---

## 11. Chat Thread Component Hierarchy

```
ChatPanel (replaces InvestigationPanel + DiagnosisPanel)
├── ChatThread (scrollable message list)
│   ├── UserBubble              — user's alert / follow-up
│   │   └── text content
│   ├── OrchestratorBubble      — one per orchestrator turn
│   │   ├── ThinkingIndicator   — pulsing dots while thinking
│   │   ├── StepGroup           — collapsible group of agent steps
│   │   │   ├── OrchestratorThoughts  (existing, reused)
│   │   │   └── StepCard[]            (existing, reused)
│   │   ├── DiagnosisBlock      — collapsible markdown diagnosis
│   │   │   └── ReactMarkdown
│   │   └── RunMetaFooter       — "9 steps · 150s  Copy"
│   └── ... (alternating user/orchestrator bubbles)
│
├── ScrollAnchor (auto-scroll to bottom on new messages)
│
└── ChatInput (pinned to bottom)
    ├── textarea (auto-resize)
    ├── SendButton
    └── CancelButton (visible during active run)
```

### Component Reuse

The key insight is that most existing components **stay as-is** — they just get re-parented:

| Existing Component | Fate |
|---|---|
| `StepCard` | **Reused verbatim** inside `StepGroup` |
| `OrchestratorThoughts` | **Reused verbatim** inside `StepGroup` |
| `ThinkingDots` | **Reused** as `ThinkingIndicator` |
| `AgentTimeline` | **Replaced** by `StepGroup` (simpler — no header/footer) |
| `AlertInput` | **Replaced** by `ChatInput` (bottom-pinned, no card wrapper) |
| `DiagnosisPanel` | **Replaced** by `DiagnosisBlock` (inline, collapsible) |
| `InvestigationPanel` | **Replaced** by `ChatPanel` |
| `ErrorBanner` | **Absorbed** into `OrchestratorBubble` (inline error state) |

---

## 12. Detailed Component Designs

### 12.1 ChatPanel

```tsx
// components/ChatPanel.tsx

interface ChatPanelProps {
  messages: ChatMessage[];
  currentThinking: ThinkingState | null;
  running: boolean;
  onSubmit: (text: string) => void;
  onCancel: () => void;
  exampleQuestions?: string[];
}

export function ChatPanel({
  messages, currentThinking, running, onSubmit, onCancel, exampleQuestions,
}: ChatPanelProps) {
  // Auto-scroll uses window.scrollTo (page-level scroll, not panel scroll).
  // See §22.1 useAutoScroll() hook for the full implementation.

  return (
    <div className="flex flex-col">
      {/* Chat thread — participates in page scroll (no overflow-y-auto).
          See Part 3 §21.4. */}
      <div className="p-4 space-y-4">
        {messages.length === 0 && (
          <EmptyState exampleQuestions={exampleQuestions} onSelect={onSubmit} />
        )}

        {messages.map((msg) =>
          msg.role === 'user'
            ? <UserBubble key={msg.id} message={msg} />
            : <OrchestratorBubble key={msg.id} message={msg} />
        )}

        {/* Live thinking indicator (not yet part of a message) */}
        {currentThinking && (
          <ThinkingIndicator agent={currentThinking.agent} status={currentThinking.status} />
        )}
      </div>

      {/* Bottom-pinned input — sticky to viewport bottom.
          See Part 3 §21.3. */}
      <ChatInput
        onSubmit={onSubmit}
        onCancel={onCancel}
        running={running}
      />
    </div>
  );
}
```

### 12.2 UserBubble

```tsx
// Minimal — just the user's text in a distinct visual style

function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] glass-card p-3 bg-brand/8 border-brand/20">
        <span className="text-[10px] uppercase text-brand/60 block mb-1">You</span>
        <p className="text-sm text-text-primary whitespace-pre-wrap">{message.text}</p>
        <span className="text-[10px] text-text-muted mt-1 block">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
}
```

### 12.3 OrchestratorBubble

This is the richest component — it houses the expandable steps and diagnosis:

```tsx
function OrchestratorBubble({ message }: { message: ChatMessage }) {
  const [stepsExpanded, setStepsExpanded] = useState(false);
  const [diagnosisExpanded, setDiagnosisExpanded] = useState(true); // auto-expand diagnosis
  const steps = message.steps ?? [];
  const isLive = message.status === 'thinking' || message.status === 'investigating';

  return (
    <div className="flex justify-start">
      <div className="glass-card p-3 w-full">
        <span className="text-[10px] uppercase text-text-muted block mb-2">
          <span className="text-brand">◇</span> Orchestrator
          {isLive && <span className="ml-2 animate-pulse text-brand">●</span>}
        </span>

        {/* Orchestrator reasoning (if any) */}
        {message.thinking?.map((t, i) => (
          <OrchestratorThoughts key={i} reasoning={t} />
        ))}

        {/* Collapsible step group */}
        {steps.length > 0 && (
          <StepGroup
            steps={steps}
            expanded={stepsExpanded}
            onToggle={() => setStepsExpanded(v => !v)}
          />
        )}

        {/* Live thinking indicator within this bubble */}
        {isLive && !message.diagnosis && (
          <ThinkingDots agent="Orchestrator" status={message.status} />
        )}

        {/* Error */}
        {message.errorMessage && (
          <div className="mt-2 p-2 rounded bg-status-error/10 border border-status-error/30
                          text-xs text-status-error">
            ⚠ {message.errorMessage}
          </div>
        )}

        {/* Collapsible diagnosis */}
        {message.diagnosis && (
          <DiagnosisBlock
            text={message.diagnosis}
            expanded={diagnosisExpanded}
            onToggle={() => setDiagnosisExpanded(v => !v)}
          />
        )}

        {/* Footer */}
        {message.runMeta && (
          <div className="flex items-center justify-between text-[10px] text-text-muted
                          border-t border-border-subtle pt-2 mt-3">
            <span>
              {message.runMeta.steps} step{message.runMeta.steps !== 1 ? 's' : ''} · {message.runMeta.time}
            </span>
            <button
              onClick={() => navigator.clipboard.writeText(message.diagnosis ?? '')}
              className="hover:text-text-primary transition-colors"
            >
              Copy
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

### 12.4 StepGroup (Copilot-style collapsible)

The step group shows a summary line when collapsed (like Copilot's "Used 5 references") and expands to reveal the individual `StepCard` components:

```tsx
function StepGroup({ steps, expanded, onToggle }: {
  steps: StepEvent[];
  expanded: boolean;
  onToggle: () => void;
}) {
  const failedCount = steps.filter(s => s.error).length;

  return (
    <div className="my-2">
      {/* Summary header (always visible, clickable) */}
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-xs text-text-secondary
                   hover:text-text-primary transition-colors w-full text-left
                   py-1.5 px-2 rounded hover:bg-neutral-bg3"
      >
        <span className="text-[10px]">{expanded ? '▾' : '▸'}</span>
        <span>
          Investigated with {steps.length} agent{steps.length !== 1 ? 's' : ''}
          {failedCount > 0 && (
            <span className="text-status-error ml-1">
              ({failedCount} failed)
            </span>
          )}
        </span>
        <span className="text-text-muted ml-auto">
          {steps.map(s => s.agent).join(', ')}
        </span>
      </button>

      {/* Expanded: individual step cards */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden pl-4 border-l-2 border-brand/20 mt-1 space-y-2"
          >
            {steps.map((s) => (
              <StepCard key={s.step} step={s} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

### 12.5 DiagnosisBlock (Inline, Collapsible)

```tsx
function DiagnosisBlock({ text, expanded, onToggle }: {
  text: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="mt-3">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-xs font-medium text-text-muted
                   hover:text-text-primary transition-colors mb-1"
      >
        <span>{expanded ? '▾' : '▸'}</span>
        <span>Diagnosis</span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="prose prose-sm max-w-none bg-neutral-bg3 rounded-lg p-3">
              <ReactMarkdown>{text}</ReactMarkdown>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

### 12.6 ChatInput (Bottom-Pinned)

```tsx
function ChatInput({ onSubmit, onCancel, running, exampleQuestions }: {
  onSubmit: (text: string) => void;
  onCancel: () => void;
  running: boolean;
  exampleQuestions?: string[];
}) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    if (!text.trim() || running) return;
    onSubmit(text.trim());
    setText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
  }, [text]);

  return (
    <div className="sticky bottom-0 z-40 border-t border-border p-3 bg-neutral-bg2">
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={running ? 'Investigation in progress...' : 'Ask a follow-up or paste a new alert...'}
          disabled={running}
          rows={1}
          className="flex-1 glass-input rounded-lg p-2.5 text-sm text-text-primary
                     placeholder-text-muted resize-none min-h-[2.5rem] max-h-[7.5rem]
                     focus:outline-none disabled:opacity-50"
        />

        {running ? (
          <button
            onClick={onCancel}
            className="px-3 py-2 text-sm rounded-lg bg-status-error/20 text-status-error
                       hover:bg-status-error/30 transition-colors"
            title="Cancel investigation"
          >
            ⏹
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!text.trim()}
            className="px-3 py-2 text-sm rounded-lg bg-brand text-white
                       hover:bg-brand-hover disabled:opacity-30
                       transition-colors"
            title="Send (Ctrl+Enter)"
          >
            ↑
          </button>
        )}
      </div>
    </div>
  );
}
```

---

## 13. Multi-Turn Backend Support

For follow-up questions to work, the backend must re-use the **same Foundry thread** across turns within a session. This is the key architectural change.

### 13.1 Session Model Changes

The `Session` dataclass in §3.1 already includes these fields (added during the
reconciliation pass):

```python
    # Foundry thread ID — persists across turns (set from "thread_created" event)
    thread_id: str | None = None
    
    # Turn counter (each user message → orchestrator response = 1 turn)
    turn_count: int = 0
    
    # Idle timeout task handle (for auto-finalization between turns)
    _idle_task: Optional[asyncio.Task] = field(default=None, repr=False)
```

### 13.2 API Endpoint & SessionManager Method: Follow-Up

The `/message` endpoint is defined in §3.3 (`routers/sessions.py`).
`SessionManager.continue_session()` is defined in §3.2.
Both were added during the reconciliation pass to ensure the multi-turn
lifecycle is fully implemented in the authoritative code sections.

### 13.3 Orchestrator Thread Reuse

```python
# orchestrator.py — modified to support thread reuse

async def run_orchestrator_session(
    alert_text: str,
    cancel_event: threading.Event = None,
    existing_thread_id: str = None,     # NEW: reuse thread for follow-ups
) -> AsyncGenerator[dict, None]:
    """
    If existing_thread_id is provided, posts the message to that thread
    instead of creating a new one. The orchestrator sees the full prior
    conversation and can use context from previous turns.
    """
    def _thread_target():
        client = _get_project_client()
        with client:
            agents_client = client.agents
            
            if existing_thread_id:
                thread_id = existing_thread_id
            else:
                thread = agents_client.threads.create()
                thread_id = thread.id
            
            # Send the new message to the thread
            agents_client.messages.create(
                thread_id=thread_id,
                role="user",
                content=alert_text,
            )
            
            # Emit thread_id so SessionManager can store it
            _put("thread_created", {"thread_id": thread_id})
            
            # Run orchestrator (same as before)
            with agents_client.runs.stream(
                thread_id=thread_id,
                agent_id=orchestrator_id,
                event_handler=handler,
            ) as stream:
                stream.until_done()
```

This means:
- **Turn 1:** "VPN-ACME-CORP SERVICE_DEGRADATION..." → creates new Foundry thread, runs full investigation
- **Turn 2:** "What about the SLA impact on BIGBANK?" → re-uses same thread, orchestrator sees Turn 1's context
- **Turn 3:** "Can you recommend remediation steps?" → same thread, full context

The Foundry orchestrator agent naturally handles this because Foundry threads are persistent conversation histories — the agent sees all previous messages, tool calls, and responses.

---

## 14. Frontend Conversation State (useSession Hook Update)

```typescript
// hooks/useSession.ts — extended for multi-turn chat

export function useSession() {
  // ... existing fields ...
  
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const createSession = async (scenario: string, alertText: string) => {
    // Add user message immediately (optimistic)
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      text: alertText,
      timestamp: new Date().toISOString(),
    };
    setMessages([userMsg]);

    // Create session + start orchestrator
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario, alert_text: alertText }),
    });
    const { session_id } = await res.json();
    setActiveSessionId(session_id);

    // Add placeholder orchestrator message
    const orchMsgId = crypto.randomUUID();
    const orchMsg: ChatMessage = {
      id: orchMsgId,
      role: 'orchestrator',
      timestamp: new Date().toISOString(),
      steps: [],
      status: 'thinking',
    };
    setMessages(prev => [...prev, orchMsg]);

    // Connect SSE — events update the orchestrator message by ID
    connectToStream(session_id, orchMsgId);
  };

  const sendFollowUp = async (text: string) => {
    if (!activeSessionId) return;

    // Add user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      text,
      timestamp: new Date().toISOString(),
    };
    const orchMsgId = crypto.randomUUID();
    const orchMsg: ChatMessage = {
      id: orchMsgId,
      role: 'orchestrator',
      timestamp: new Date().toISOString(),
      steps: [],
      status: 'thinking',
    };
    setMessages(prev => [...prev, userMsg, orchMsg]);

    // POST follow-up to existing session
    await fetch(`/api/sessions/${activeSessionId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });

    // Reconnect SSE for new events (will replay + tail)
    connectToStream(activeSessionId, orchMsgId);
  };

  const connectToStream = (sessionId: string, targetMsgId: string) => {
    // Abort any existing SSE connection
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRunning(true);

    // Note: does NOT reset messages — follow-ups preserve history.
    fetchEventSource(`/api/sessions/${sessionId}/stream`, {
      signal: ctrl.signal,
      onmessage: (ev) => {
        if (!ev.event || !ev.data) return;
        const data = JSON.parse(ev.data);
        updateOrchestratorMessage(targetMsgId, ev.event, data);
      },
      onerror: () => { /* SSE dropped — session continues server-side */ },
      openWhenHidden: true,
    }).finally(() => setRunning(false));
  };

  // Immutable state update targeting a specific orchestrator message by ID
  const updateOrchestratorMessage = (
    msgId: string, eventType: string, data: any
  ) => {
    setMessages(prev => prev.map(msg => {
      if (msg.id !== msgId) return msg;
      // Clone the message object for immutability
      const updated = { ...msg };
      switch (eventType) {
        case 'step_thinking':
          updated.thinking = [...(updated.thinking ?? []), data.status];
          updated.status = 'thinking';
          break;
        case 'step_complete':
          updated.steps = [...(updated.steps ?? []), data];
          updated.status = 'investigating';
          break;
        case 'message':
          updated.diagnosis = data.text;
          updated.status = 'complete';
          break;
        case 'run_complete':
          updated.runMeta = data;
          updated.status = 'complete';
          break;
        case 'error':
          updated.errorMessage = data.message;
          updated.status = 'error';
          break;
      }
      return updated;
    }));
  };

  // Reconstruct ChatMessage[] from a session's event_log (for loading past sessions)
  const loadSessionMessages = (session: SessionDetail): ChatMessage[] => {
    const msgs: ChatMessage[] = [];
    let currentOrch: ChatMessage | null = null;

    for (const event of session.event_log) {
      const evType = event.event;
      const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;

      if (evType === 'user_message') {
        // Flush any pending orchestrator message
        if (currentOrch) { msgs.push(currentOrch); currentOrch = null; }
        msgs.push({
          id: crypto.randomUUID(), role: 'user',
          text: data.text, timestamp: event.timestamp ?? session.created_at,
        });
      } else if (evType === 'run_start') {
        // Start a new orchestrator message
        if (currentOrch) msgs.push(currentOrch);
        currentOrch = {
          id: crypto.randomUUID(), role: 'orchestrator',
          timestamp: data.timestamp ?? session.created_at,
          steps: [], thinking: [], status: 'complete',
        };
      } else if (currentOrch) {
        if (evType === 'step_complete') currentOrch.steps = [...(currentOrch.steps ?? []), data];
        else if (evType === 'step_thinking') currentOrch.thinking = [...(currentOrch.thinking ?? []), data.status];
        else if (evType === 'message') currentOrch.diagnosis = data.text;
        else if (evType === 'run_complete') currentOrch.runMeta = data;
        else if (evType === 'error') { currentOrch.errorMessage = data.message; currentOrch.status = 'error'; }
      }
    }
    if (currentOrch) msgs.push(currentOrch);

    // If no user_message events (single-turn session), synthesise one
    if (msgs.length > 0 && msgs[0].role !== 'user') {
      msgs.unshift({
        id: crypto.randomUUID(), role: 'user',
        text: session.alert_text, timestamp: session.created_at,
      });
    }
    return msgs;
  };

  const viewSession = async (sessionId: string) => {
    const res = await fetch(`/api/sessions/${sessionId}`);
    const session: SessionDetail = await res.json();
    setActiveSessionId(sessionId);
    setMessages(loadSessionMessages(session));

    // If still running, connect to live stream targeting the last orch message
    if (session.status === 'in_progress') {
      const lastOrch = messages.findLast(m => m.role === 'orchestrator');
      if (lastOrch) connectToStream(sessionId, lastOrch.id);
    }
  };

  return {
    messages, running, activeSessionId,
    createSession, sendFollowUp, viewSession, cancelSession,
  };
}
```

---

## 15. App.tsx Layout Changes

The split `InvestigationPanel + DiagnosisPanel` horizontal split is replaced by a single `ChatPanel`:

```tsx
// Before:
<PanelGroup orientation="horizontal" id="investigation-diagnosis-layout">
  <Panel><InvestigationPanel ... /></Panel>
  <PanelResizeHandle />
  <Panel><DiagnosisPanel ... /></Panel>
</PanelGroup>

// After:
<ChatPanel
  messages={messages}
  currentThinking={thinking}
  running={running}
  onSubmit={(text) => {
    if (activeSessionId) sendFollowUp(text);
    else createSession(SCENARIO.name, text);
  }}
  onCancel={cancelSession}
  exampleQuestions={SCENARIO.exampleQuestions}
/>
```

This eliminates:
- The `investigation-diagnosis-layout` PanelGroup (no more horizontal split)
- The `InvestigationPanel` component
- The `DiagnosisPanel` component
- The `viewingInteraction` state (replaced by loading a session's messages)

---

## 16. Empty State / Welcome Screen

When no session is active and no messages exist, the `ChatPanel` shows a welcome screen:

```
┌─────────────────────────────────────────────┐
│                                             │
│              ◇                              │
│                                             │
│     Submit an alert to begin                │
│     investigation                           │
│                                             │
│     ┌────────────────────────────────┐      │
│     │ 💡 VPN-ACME-CORP SERVICE_...  │      │
│     │ 💡 BGP session flapping on... │      │
│     │ 💡 Fibre cut on SYD-MEL...   │      │
│     └────────────────────────────────┘      │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │ Paste a NOC alert...       [Send]   │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

Example questions are shown **only in the empty state** (welcome screen). Once a conversation
starts, the empty state disappears. The `ChatInput` at the bottom does NOT have its own
example dropdown — the two are mutually exclusive, not shown simultaneously.

---

## 17. Implementation Phases (Unified)

> The phases below are the **authoritative** implementation order. Part 1's
> Phases 2–4 and Part 3's layout changes are merged in.

| Phase | Scope | What Changes |
|---|---|---|
| **Phase 1** | Backend session infra | `sessions.py`, `session_manager.py`, `routers/sessions.py` — as described in §3.1–3.3. Includes `_parse_data()`, `_persist_to_cosmos()`, `continue_session()`, and the `/message` endpoint. |
| **Phase 2** | Multi-turn backend | `run_orchestrator_session()` gains `existing_thread_id` param. `thread_created` event emitted. Cancel-between-steps logic. (§3.4, §13.3) |
| **Phase 3** | Chat UI components + scrollable layout | New: `ChatPanel`, `UserBubble`, `OrchestratorBubble`, `StepGroup`, `DiagnosisBlock`, `ChatInput`. Reuse: `StepCard`, `OrchestratorThoughts`, `ThinkingDots`. Root `h-screen` → `min-h-screen`. Remove PanelGroup nesting. Sticky header/input/sidebar. (§12, §20–21) |
| **Phase 4** | Hook + wiring | `useSession` hook (§14) replaces `useInvestigation`. `useAutoScroll` hook (§22). Update `App.tsx` layout. Remove split panel + old hook. |
| **Phase 5** | Session sidebar | Update `InteractionSidebar` → `SessionSidebar`. Show live status (⏳/✓/✗). Loading a session calls `loadSessionMessages()` to reconstruct `ChatMessage[]`. |
| **Phase 6** | Cosmos persistence & recovery | Persist full session (multi-turn) to Cosmos on finalization. Load recent sessions into `_recent` cache on API startup. Merge in-memory + Cosmos in `list_sessions`. |
| **Phase 7** | Polish & edge cases | Auto-scroll FAB, keyboard shortcuts, idle timeout UX, cancellation "Cancelling..." feedback, heartbeat events, session TTL, graceful shutdown. |

### Estimated Effort (Revised)

| Phase | Estimate |
|---|---|
| Phase 1 (session infra + multi-turn manager) | ~350 lines Python |
| Phase 2 (orchestrator changes) | ~80 lines Python |
| Phase 3 (chat components + layout) | ~400 lines TSX |
| Phase 4 (hook + wiring) | ~250 lines TS |
| Phase 5 (sidebar update) | ~80 lines TSX modified |
| Phase 6 (Cosmos) | ~80 lines Python |
| Phase 7 (polish) | ~120 lines mixed |
| **Total** | **~1,360 lines** |

---

## 18. Key Design Decisions (Chat UI)

| Decision | Choice | Rationale |
|---|---|---|
| Chat vs split panel | Single chat thread | Matches user expectation for conversational AI; supports multi-turn naturally; reduces cognitive split |
| Diagnosis placement | Inline within orchestrator bubble, auto-expanded | The diagnosis is the **answer** — it should be front and center, not hidden in a separate panel |
| Steps default state | Collapsed (summary line) | Most users care about the diagnosis, not the 9 intermediate steps. Power users can expand. Mirrors Copilot's "Used N references" pattern |
| Input placement | Bottom-pinned | Standard chat convention; keeps latest content near the input for follow-ups |
| Thread reuse | Same Foundry thread across turns | Foundry threads are built for this — the orchestrator sees full history, enabling contextual follow-ups without re-explaining the incident |
| User bubbles alignment | Right-aligned | Visual distinction from orchestrator (left-aligned), standard chat UX convention |
| Follow-up while running | Disabled (queue or block) | Foundry can only have one active run per thread at a time; serialize turns |

---
---

# Part 3: Full-Page Scrollable Layout

> **Problem:** The current layout locks every zone into the viewport via a chain of `h-screen → flex-col → h-full → PanelGroup → h-full → overflow-y-auto`. Each sub-panel (Investigation, Diagnosis, Sidebar, Terminal, Metrics) scrolls independently within its own fixed-height box. The **page itself** never scrolls. This creates several UX issues:
>
> 1. **Content is trapped** — a long diagnosis with 9 agent steps requires scrolling inside a ~300px panel, even though there's plenty of screen real estate below
> 2. **Resizing is mandatory** — users must drag panel dividers just to read content, not to customize layout
> 3. **No natural reading flow** — you can't scroll top-to-bottom through an investigation; you have to interact with 3 separate scroll containers
> 4. **Mobile/small screens are broken** — panels collapse to unusable sizes rather than flowing vertically

> **Goal:** Replace the viewport-locked `PanelGroup` grid with a vertically scrollable page where content sections stack naturally and grow to their intrinsic height. The whole page scrolls, not individual boxes.

---

## 19. Current Layout Model

```
┌─ h-screen ─────────────────────────────────────────┐
│ Header (h-12, shrink-0)                            │
│ TabBar (shrink-0)                                  │
│ ┌─ PanelGroup vertical (flex-1 min-h-0) ─────────┐│
│ │ ┌─ Panel 75% ─────────────────────────────────┐ ││
│ │ │ ┌─ PanelGroup horizontal ──────────────────┐│ ││
│ │ │ │ ┌─ Panel 80% ─────────────────────────┐  ││ ││
│ │ │ │ │ ┌─ PanelGroup vertical ────────────┐│  ││ ││
│ │ │ │ │ │  MetricsBar (Panel 30%, h-full)  ││  ││ ││
│ │ │ │ │ │──────────────────────────────────││  ││ ││
│ │ │ │ │ │  ┌─ PanelGroup horizontal ─────┐ ││  ││ ││
│ │ │ │ │ │  │ Investigation │ Diagnosis   │ ││  ││ ││
│ │ │ │ │ │  │ overflow-y    │ overflow-y   │ ││  ││ ││
│ │ │ │ │ │  └─────────────────────────────┘ ││  ││ ││
│ │ │ │ │ └──────────────────────────────────┘│  ││ ││
│ │ │ │ └─────────────────────────────────────┘  ││ ││
│ │ │ │ Sidebar (Panel 20%, overflow-y)          ││ ││
│ │ │ └─────────────────────────────────────────┘│ ││
│ │ └─────────────────────────────────────────────┘ ││
│ │ Terminal (Panel 25%, overflow-y)                 ││
│ └─────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────┘

4 nested PanelGroups. 5 independent scroll containers.
Nothing ever escapes the viewport.
```

**The chain that prevents page scroll:**
1. `<motion.div className="h-screen flex flex-col">` — root is exactly viewport height
2. `<PanelGroup className="flex-1 min-h-0">` — fills remaining space, never exceeds it
3. Every `<Panel>` gets a calculated `height` from the PanelGroup — content must scroll internally
4. Each content component uses `overflow-y-auto` to create its own scroll container

---

## 20. Proposed Layout Model

The chat UI redesign (Part 2) is the natural moment to break out of the viewport-locked model. With the Investigation+Diagnosis split replaced by a single chat thread, we can simplify dramatically:

```
┌─ min-h-screen (scrollable page) ──────────────────────────────┐
│                                                                │
│ Header (sticky top-0)                                          │
│ TabBar (sticky, below header)                                  │
│                                                                │
│ ┌─ Main Content ──────────────────────────┬─ Sidebar ─────────┐│
│ │                                         │ ◀── drag handle   ││
│ │  Graph Topology                         │                   ││
│ │  (user-resizable, drag bottom edge)     │  Sessions list    ││
│ │  ═══════════════════════════════════    │  (sticky within   ││
│ │                                         │   viewport,       ││
│ │  Chat Thread                            │   overflow-y-auto ││
│ │  (grows with content, page scrolls)     │   internally)     ││
│ │                                         │                   ││
│ │  ┌─ User Bubble ─────────────────────┐  │                   ││
│ │  └───────────────────────────────────┘  │                   ││
│ │  ┌─ Orchestrator Bubble ─────────────┐  │                   ││
│ │  │  ▸ Steps (collapsed)              │  │                   ││
│ │  │  ▾ Diagnosis (expanded, inline)   │  │                   ││
│ │  └───────────────────────────────────┘  │                   ││
│ │  ...                                    │                   ││
│ └─────────────────────────────────────────┴───────────────────┘│
│                                                                │
│ ┌─ Terminal (drag top edge to resize) ────────────────────────┐│
│ │  fixed bottom, overlay/drawer                               ││
│ └─────────────────────────────────────────────────────────────┘│
│                                                                │
│ ┌─ Chat Input (sticky bottom-0, above terminal if open) ─────┐│
│ │  Ask a follow-up...                              [Send]     ││
│ └─────────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────────┘

0 nested PanelGroups. 1 page scroll. 3 lightweight resize handles.
```

---

## 21. Key Layout Changes

### 21.1 Root Container: `h-screen` → `min-h-screen`

```tsx
// Before:
<motion.div className="h-screen flex flex-col bg-neutral-bg1">

// After:
<motion.div className="min-h-screen flex flex-col bg-neutral-bg1">
```

This single change unlocks page scrolling. `h-screen` means "exactly viewport height" (content is trapped). `min-h-screen` means "at least viewport height" (content can push the page taller).

### 21.2 Remove PanelGroup Nesting (for chat tab)

The current layout has 4 nested `PanelGroup` instances:
1. `app-terminal-layout` (vertical: content/terminal)
2. `content-sidebar-layout` (horizontal: main/sidebar)
3. `metrics-content-layout` (vertical: metrics/investigation)
4. `investigation-diagnosis-layout` (horizontal: investigation/diagnosis)

With the chat UI, #3 and #4 are eliminated entirely. #1 changes behavior (terminal becomes a sticky/collapsible footer rather than a resizable panel). Only #2 (content + sidebar) may survive, but as a simpler CSS Grid/Flexbox rather than a PanelGroup.

```tsx
// After — Investigate tab layout (no PanelGroups, 3 resize handles):
{activeTab === 'investigate' && (
  <div className="flex-1 flex">
    {/* Main scrollable content */}
    <main className="flex-1 min-w-0 flex flex-col">
      {/* Graph topology — resizable from bottom edge */}
      <ResizableGraph>
        <MetricsBar />
      </ResizableGraph>

      {/* Chat thread — grows with content, page scrolls */}
      <ChatPanel
        messages={messages}
        currentThinking={thinking}
        running={running}
        onSubmit={handleSubmit}
        onCancel={cancelSession}
        exampleQuestions={SCENARIO.exampleQuestions}
      />
    </main>

    {/* Session sidebar — resizable from left edge, sticky */}
    <ResizableSidebar>
      <SessionSidebar ... />
    </ResizableSidebar>
  </div>
)}

{/* Terminal — resizable from top edge, fixed-bottom drawer */}
<ResizableTerminal visible={terminalVisible}>
  <TerminalPanel />
</ResizableTerminal>
```

### 21.3 Sticky Elements

Three things should stay fixed while the page scrolls:

| Element | Behavior |
|---|---|
| **Header** | `sticky top-0 z-50` — always visible |
| **Chat Input** | `sticky bottom-0 z-40` — always accessible at bottom of viewport |
| **Session Sidebar** | `sticky top-12 h-[calc(100vh-3rem)]` — scrolls internally but stays in viewport |

The **Terminal panel** is a collapsible bottom drawer (overlay), toggled via the tab bar. See §21.6.

### 21.4 Resizable Peripheral Panels

Three panels get lightweight drag-to-resize handles. Critically, none of these
touch the chat thread — they're all **outside** the document flow that produces
page scroll. The chat thread simply fills whatever space remains between the
graph and the bottom of the page.

#### Why this doesn't break conversation flow

The old `PanelGroup` layout broke page scroll because it forced *every* element
(including the chat content) into a fixed-height slot. The new approach is
different: only the **peripheral panels** (graph, sidebar, terminal) have
controlled dimensions. The chat thread has **no height constraint** — it grows
with content and participates in normal page scroll. Resizing a peripheral
panel doesn't trap the chat content; it just shifts how much viewport space the
chat area occupies.

```
                 ┌──────────────────────────────────────┐
  Graph          │  d3 canvas                           │
  (resizable)    │                                      │
                 ├══════════╤═══════════════════════════╡ ← drag handle (bottom edge)
                 │          │                           │
  Chat Thread    │  bubbles │   Sidebar (resizable)     │
  (no height     │  ...     │◀─ drag handle (left edge) │
   constraint,   │  ...     │                           │
   page scrolls) │  ...     │   SessionCard             │
                 │  ...     │   SessionCard             │
                 │          │   SessionCard             │
                 ├──────────┴───────────────────────────┤
  Terminal       │  logs                                │
  (resizable)    ├══════════════════════════════════════╡ ← drag handle (top edge)
                 │                                      │
                 └──────────────────────────────────────┘
```

#### 21.4.1 Graph Topology — Bottom-Edge Resize

The graph viewer has a fixed initial height (e.g. 280px). A drag handle on its
bottom edge lets the user expand/collapse it. The chat thread below simply
reflows.

```tsx
function ResizableGraph({ children }: { children: React.ReactNode }) {
  const [height, setHeight] = useState(280);
  const dragging = useRef(false);
  const startY = useRef(0);
  const startH = useRef(0);

  const onPointerDown = (e: React.PointerEvent) => {
    dragging.current = true;
    startY.current = e.clientY;
    startH.current = height;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging.current) return;
    const delta = e.clientY - startY.current;
    setHeight(Math.max(100, Math.min(600, startH.current + delta)));
  };

  const onPointerUp = () => {
    dragging.current = false;
    // Persist to localStorage
    localStorage.setItem('graph-height', String(height));
  };

  return (
    <div style={{ height }} className="border-b border-border relative">
      {children}
      {/* Drag handle — bottom edge */}
      <div
        className="absolute bottom-0 left-0 right-0 h-1.5 cursor-row-resize
                   hover:bg-brand/20 active:bg-brand/40 transition-colors z-10"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
    </div>
  );
}
```

**Key point:** This does NOT use a `PanelGroup`. It's a simple `div` with a
controlled `height` state and pointer events on a 6px handle. The chat content
below is not constrained — it flows after the graph and pushes down
into page scroll.

#### 21.4.2 Session Sidebar — Left-Edge Resize

The sidebar is `sticky` and positioned to fill the viewport height. A drag
handle on its left edge lets the user widen or narrow it. The main content
area uses `flex-1` and automatically absorbs the width change.

```tsx
function ResizableSidebar({ children }: { children: React.ReactNode }) {
  const [width, setWidth] = useState(288); // 18rem default
  const dragging = useRef(false);
  const startX = useRef(0);
  const startW = useRef(0);

  const onPointerDown = (e: React.PointerEvent) => {
    dragging.current = true;
    startX.current = e.clientX;
    startW.current = width;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging.current) return;
    // Moving left = wider sidebar (negative delta = grow)
    const delta = startX.current - e.clientX;
    setWidth(Math.max(200, Math.min(500, startW.current + delta)));
  };

  const onPointerUp = () => {
    dragging.current = false;
    localStorage.setItem('sidebar-width', String(width));
  };

  return (
    <aside
      style={{ width }}
      className="shrink-0 border-l border-border sticky top-12
                 h-[calc(100vh-3rem)] overflow-y-auto relative"
    >
      {/* Drag handle — left edge */}
      <div
        className="absolute top-0 left-0 bottom-0 w-1.5 cursor-col-resize
                   hover:bg-brand/20 active:bg-brand/40 transition-colors z-10"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
      <div className="pl-2">{children}</div>
    </aside>
  );
}
```

**Why this doesn't affect scroll:** The sidebar is `sticky` with its own
`overflow-y-auto`. It doesn't contribute to document height. Changing its
width just adjusts how much horizontal space the `flex-1` chat area gets.

#### 21.4.3 Terminal Panel — Top-Edge Resize

The terminal is a `position: fixed` bottom drawer. A drag handle on its top
edge lets the user pull it taller or shorter. Since it's an overlay (fixed
position), it doesn't participate in document flow at all.

```tsx
function ResizableTerminal({ children, visible }: {
  children: React.ReactNode;
  visible: boolean;
}) {
  const [height, setHeight] = useState(200);
  const dragging = useRef(false);
  const startY = useRef(0);
  const startH = useRef(0);

  const onPointerDown = (e: React.PointerEvent) => {
    dragging.current = true;
    startY.current = e.clientY;
    startH.current = height;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging.current) return;
    // Moving up = taller terminal (negative delta = grow)
    const delta = startY.current - e.clientY;
    setHeight(Math.max(100, Math.min(500, startH.current + delta)));
  };

  const onPointerUp = () => {
    dragging.current = false;
    localStorage.setItem('terminal-height', String(height));
  };

  if (!visible) return null;

  return (
    <div
      style={{ height }}
      className="fixed bottom-0 left-0 right-0 z-30
                 bg-neutral-bg2 border-t border-border shadow-lg"
    >
      {/* Drag handle — top edge */}
      <div
        className="absolute top-0 left-0 right-0 h-1.5 cursor-row-resize
                   hover:bg-brand/20 active:bg-brand/40 transition-colors"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
      <div className="h-full pt-1.5 overflow-hidden">
        {children}
      </div>
    </div>
  );
}
```

**Interaction with Chat Input:** When the terminal drawer is open, the Chat
Input needs to sit just above it:

```tsx
<div
  className="sticky z-40 border-t border-border p-3 bg-neutral-bg2"
  style={{ bottom: terminalVisible ? terminalHeight : 0 }}
>
  <ChatInput ... />
</div>
```

#### 21.4.4 Extracted Hook: `useResizable`

All three panels share the same pointer-drag pattern. This can be a reusable hook:

```tsx
function useResizable(axis: 'x' | 'y', {
  initial, min, max, storageKey, invert = false,
}: {
  initial: number; min: number; max: number;
  storageKey: string; invert?: boolean;
}) {
  const [size, setSize] = useState(() => {
    const saved = localStorage.getItem(storageKey);
    return saved ? Number(saved) : initial;
  });
  const dragging = useRef(false);
  const startPos = useRef(0);
  const startSize = useRef(0);

  const handleProps = {
    onPointerDown: (e: React.PointerEvent) => {
      dragging.current = true;
      startPos.current = axis === 'x' ? e.clientX : e.clientY;
      startSize.current = size;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    onPointerMove: (e: React.PointerEvent) => {
      if (!dragging.current) return;
      const pos = axis === 'x' ? e.clientX : e.clientY;
      const delta = invert
        ? startPos.current - pos    // sidebar (left edge), terminal (top edge)
        : pos - startPos.current;   // graph (bottom edge)
      setSize(Math.max(min, Math.min(max, startSize.current + delta)));
    },
    onPointerUp: () => {
      dragging.current = false;
      localStorage.setItem(storageKey, String(size));
    },
  };

  return { size, handleProps };
}

// Usage:
const graph = useResizable('y', { initial: 280, min: 100, max: 600, storageKey: 'graph-h' });
const sidebar = useResizable('x', { initial: 288, min: 200, max: 500, storageKey: 'sidebar-w', invert: true });
const terminal = useResizable('y', { initial: 200, min: 100, max: 500, storageKey: 'terminal-h', invert: true });
```

### 21.5 ChatPanel Becomes Non-Scrolling

Critical change: the chat thread has **no height constraint and no overflow**. It participates in page scroll — the chat thread **participates in the page scroll** instead of creating its own scroll container:

```tsx
// Part 2 (scroll within panel):
<div className="flex-1 overflow-y-auto p-4 space-y-4">
  {messages.map(...)}
</div>

// Part 3 (participates in page scroll):
<div className="p-4 space-y-4">
  {messages.map(...)}
</div>
```

The `flex-1 overflow-y-auto` is what traps content. Removing it lets bubbles push the page height and scroll naturally.

### 21.6 MetricsBar / Graph Topology

The graph topology viewer is wrapped in `ResizableGraph` (§21.4.1) with a
user-controllable height (default 280px, range 100–600px). The d3 canvas
resizes to fit via `ResizeObserver` or by reading the container dimensions
on each render — this is already how the current `GraphTopologyViewer`
works (it reads its parent's `clientWidth`/`clientHeight`).

---

## 22. Scroll Behavior Details

### 22.1 Auto-Scroll on New Messages

When a new orchestrator step arrives or diagnosis streams in, the page should auto-scroll to keep the latest content visible:

```typescript
const scrollToBottom = () => {
  window.scrollTo({
    top: document.documentElement.scrollHeight,
    behavior: 'smooth',
  });
};

// Auto-scroll when new messages arrive (unless user has scrolled up)
useEffect(() => {
  if (isNearBottom) {
    scrollToBottom();
  }
}, [messages, currentThinking]);

// Track if user is near the bottom
const [isNearBottom, setIsNearBottom] = useState(true);
useEffect(() => {
  const handleScroll = () => {
    const threshold = 200; // px from bottom
    const scrollBottom = window.innerHeight + window.scrollY;
    const docHeight = document.documentElement.scrollHeight;
    setIsNearBottom(docHeight - scrollBottom < threshold);
  };
  window.addEventListener('scroll', handleScroll, { passive: true });
  return () => window.removeEventListener('scroll', handleScroll);
}, []);
```

### 22.2 "Scroll to Bottom" FAB

When the user has scrolled up and new content arrives below, show a floating action button:

```
                    ┌──────────────┐
                    │ ↓ New steps  │
                    └──────────────┘
┌──────────────────────────────────────────┐
│ Ask a follow-up...              [Send]   │
└──────────────────────────────────────────┘
```

This mirrors Copilot / ChatGPT / Slack behavior — you're never lost, and you can jump back to the latest content with one click.

### 22.3 Viewing Past Sessions

When clicking a completed session in the sidebar, the page scrolls to top and the chat thread is populated with that session's messages. The page will be as tall as the content. No panel-scroll gymnastics needed.

---

## 23. What This Eliminates

| Current | After |
|---|---|
| `react-resizable-panels` PanelGroup (for chat tab) | Plain CSS Flexbox + `useResizable` hook |
| 4 layout persistence keys in localStorage | 3 lightweight keys (graph-h, sidebar-w, terminal-h) |
| `useDefaultLayout` hook calls | Removed |
| `PanelResizeHandle` dividers | Lightweight pointer-event handles (6px) |
| `panelRef` / `isCollapsed` sidebar logic | CSS `sticky` + controlled width |
| Per-panel `overflow-y-auto` | Single page scroll (sidebar/terminal keep internal scroll) |
| `min-h-0` hack on every flex container | Not needed — content isn't trapped |

**Note:** The Resources and Scenario tabs can keep their current PanelGroup layouts if needed — those are data-visualization screens where viewport-locking makes sense (d3 canvases, tables). The scrollable layout only applies to the Investigate/chat tab.

---

## 24. Updated Implementation (Merged with Part 2)

This layout change is best done **simultaneously with the chat UI** (Part 2, Phase 3–4) since both are restructuring the same `App.tsx` layout. The components are:

| Item | Change |
|---|---|
| `App.tsx` root | `h-screen` → `min-h-screen` |
| `App.tsx` investigate tab | Remove `PanelGroup` nesting, use flexbox |
| `ChatPanel` | Remove `overflow-y-auto` from thread container |
| `ChatInput` | `sticky bottom-0` |
| `Header` | `sticky top-0 z-50` |
| `SessionSidebar` | `sticky top-12`, `h-[calc(100vh-3rem)]`, internal `overflow-y-auto` |
| `MetricsBar` wrapper | `ResizableGraph` — bottom-edge drag, default 280px (§21.4.1) |
| `SessionSidebar` | `ResizableSidebar` — left-edge drag, default 288px (§21.4.2) |
| `TerminalPanel` | `ResizableTerminal` — top-edge drag, fixed-bottom drawer (§21.4.3) |
| `useResizable` hook | New: shared pointer-drag logic + localStorage persistence (§21.4.4) |
| Auto-scroll hook | New: `useAutoScroll()` — tracks page position, scrolls on new content |
| Scroll-to-bottom FAB | New floating button when user scrolled up |
