# Task 03: Hardening Implementation — Execution Log

> Strategy: [task_03_hardening_implementation.md](../strategy/task_03_hardening_implementation.md)

**Status**: complete  
**Date**: 2025-02-20

---

## Phase Ordering Rationale

6 phases, ordered by:

1. **Frontend fetch guards first** (Phase 1) — zero-risk, high impact, no
   backend dependency. Fixes the most user-visible crashes immediately.
2. **Backend crash prevention** (Phase 2) — fixes that prevent session loss
   on malformed data and server errors. Must land before Phase 3 because
   startup recovery assumes sessions are correctly finalized.
3. **Session lifecycle robustness** (Phase 3) — startup recovery, persist
   retry, max-sessions error handling. Depends on Phase 2 (correct finalize
   logic).
4. **Data integrity** (Phase 4) — `_docType` discriminator and `event_log`
   cap. Independent of Phases 1–3 but lower risk if sessions already
   finalize correctly.
5. **SSE transport hardening** (Phase 5) — drain race fix and `status_change`
   handler. Depends on correct session status (Phase 2/3).
6. **Conversation model completeness** (Phase 6) — initial `user_message`
   event, legacy endpoint removal. Structural improvements that benefit from
   all prior phases being stable.

The orchestrator deduplication (H-INEFF-01/02) is **excluded** — it is a
refactor, not a bug fix, and carries significant regression risk. It deserves
its own dedicated task.

---

## Phase 1: Frontend Fetch Error Guards

### Issues Resolved

`H-ERR-01`, `H-ERR-02`, `H-ERR-03`, `H-ERR-04`, `H-STATE-04`

### Files Touched

- `frontend/src/hooks/useSession.ts` — `createSession`, `sendFollowUp`,
  `viewSession`, `cancelSession`

### Changes

#### 1a. `createSession` — guard after POST (H-ERR-02)

**Location**: `useSession.ts` L153–L154, after `const res = await fetch(...)`

Insert before `const { session_id } = await res.json();`:

```typescript
if (!res.ok) {
  const err = await res.json().catch(() => ({ detail: 'Session creation failed' }));
  // Update the optimistic user message to show error
  setMessages(prev => prev.length > 0 ? [...prev, {
    id: crypto.randomUUID(), role: 'orchestrator' as const,
    timestamp: new Date().toISOString(), steps: [],
    status: 'error' as const,
    errorMessage: err.detail ?? err.message ?? `Server error (${res.status})`,
  }] : prev);
  return;
}
```

#### 1b. `sendFollowUp` — guard after POST (H-ERR-03)

**Location**: `useSession.ts` L199–L200, after `const res = await fetch(...)`

Insert before `const { event_offset = 0 } = await res.json();`:

```typescript
if (!res.ok) {
  const err = await res.json().catch(() => ({ detail: 'Follow-up failed' }));
  // Update the placeholder orchestrator message to show error
  setMessages(prev => prev.map(msg =>
    msg.id === orchMsgId
      ? { ...msg, status: 'error' as const, errorMessage: err.detail ?? `Server error (${res.status})` }
      : msg
  ));
  return;
}
```

#### 1c. `viewSession` — guard after GET + loading state (H-ERR-01, H-STATE-04)

**Location**: `useSession.ts` L301–L308

Replace the current body with:

```typescript
const viewSession = useCallback(async (sessionId: string) => {
  abortRef.current?.abort();
  setRunning(false);
  setThinking(null);
  setMessages([]);  // Clear immediately → shows empty state as loading signal (H-STATE-04)

  const res = await fetch(`/api/sessions/${sessionId}`);
  if (!res.ok) {
    // Session not found or server error — stay on empty state
    console.warn('Failed to load session:', res.status);
    setActiveSessionId(null);
    return;
  }

  const session: SessionDetail = await res.json();
  setActiveSessionId(sessionId);
  const reconstructed = loadSessionMessages(session);
  setMessages(reconstructed);

  if (session.status === 'in_progress') {
    const lastOrch = [...reconstructed].reverse().find((m: ChatMessage) => m.role === 'orchestrator');
    if (lastOrch) connectToStream(sessionId, lastOrch.id);
  }
}, [loadSessionMessages, connectToStream]);
```

#### 1d. `cancelSession` — try/catch (H-ERR-04)

**Location**: `useSession.ts` L240–L246

Wrap in try/catch:

```typescript
const cancelSession = useCallback(async () => {
  if (!activeSessionId) {
    abortRef.current?.abort();
    return;
  }
  try {
    await fetch(`/api/sessions/${activeSessionId}/cancel`, { method: 'POST' });
  } catch (err) {
    console.warn('Cancel request failed:', err);
  }
}, [activeSessionId]);
```

### Verification

1. Start a session normally → happy path should work identically.
2. Manually trigger `POST /api/sessions` with a bad payload → verify the
   chat panel shows an error message instead of crashing.
3. Click a deleted session in the sidebar → verify chat panel shows empty
   state, no console crash.
4. Click a session card → verify previous messages clear immediately
   (loading signal).

### Risk Assessment

- **Low risk**: Only adds early-return guards. The happy path (where `res.ok`
  is true) is unchanged.
- **Rollback**: Revert the file to its prior state.

---

## Phase 2: Backend Crash Prevention & Finalize Logic

### Issues Resolved

`H-BUG-01`, `H-BUG-05`, `H-FRAG-05`

### Files Touched

- `api/app/session_manager.py` — `_parse_data`, `_finalize_turn`
- `api/app/routers/sessions.py` — `create_session`

### Changes

#### 2a. `_parse_data` — catch malformed JSON (H-BUG-01)

**Location**: `session_manager.py` L35–L40

Replace:

```python
def _parse_data(event: dict) -> dict:
    """Extract the parsed data payload from an SSE event dict."""
    raw = event.get("data", "{}")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw
```

With:

```python
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
```

#### 2b. `_finalize_turn` — prioritize error over diagnosis (H-BUG-05)

**Location**: `session_manager.py` L122–L140

Replace the condition block:

```python
        if session._cancel_event.is_set():
            session.status = SessionStatus.CANCELLED
            self._move_to_recent(session)
        elif session.error_detail and not session.diagnosis:
            session.status = SessionStatus.FAILED
            self._move_to_recent(session)
        else:
            session.status = SessionStatus.COMPLETED
```

With:

```python
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
```

**Note**: This changes behavior — sessions with both `error_detail` and
`diagnosis` are now FAILED instead of COMPLETED. This is correct: a partial
diagnosis from attempt 1 followed by a fatal error on attempt 2 is not a
successful investigation.

#### 2c. `create_session` — catch max sessions error (H-FRAG-05)

**Location**: `routers/sessions.py` L38–L43

Replace:

```python
@router.post("")
async def create_session(req: CreateSessionRequest):
    """Create a new investigation session and start the orchestrator."""
    session = session_manager.create(req.scenario, req.alert_text)
    await session_manager.start(session)
    return {"session_id": session.id, "status": session.status.value}
```

With:

```python
@router.post("")
async def create_session(req: CreateSessionRequest):
    """Create a new investigation session and start the orchestrator."""
    try:
        session = session_manager.create(req.scenario, req.alert_text)
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    await session_manager.start(session)
    return {"session_id": session.id, "status": session.status.value}
```

### Verification

1. Inject a malformed JSON string into an event dict (e.g., modify
   orchestrator to emit `{"event": "step_complete", "data": "not-json"}`)
   → verify the session survives and logs a warning instead of crashing.
2. Trigger an orchestrator run that partially succeeds then errors →
   verify the session status is FAILED, not COMPLETED.
3. Set `MAX_ACTIVE_SESSIONS=1`, create one session, then try to create
   another → verify HTTP 429 with "Too many concurrent sessions" message.

### Risk Assessment

- **2a**: Zero risk — adds a try/except around an existing call.
- **2b**: **Medium risk** — changes finalize behavior. Sessions that
  previously showed as COMPLETED will now show as FAILED. This is the
  correct behavior but may surprise users who were accustomed to seeing
  "Completed" for partial results. **Rollback**: restore the
  `and not session.diagnosis` condition.
- **2c**: Low risk — adds a try/except in the router. The happy path
  (< MAX_ACTIVE_SESSIONS) is unchanged.

---

## Phase 3: Session Lifecycle Robustness

### Issues Resolved

`H-FRAG-01`, `H-FRAG-02`

### Files Touched

- `api/app/session_manager.py` — `__init__`, `_persist_to_cosmos`,
  new method `_recover_from_cosmos`

### Changes

#### 3a. Startup recovery from Cosmos (H-FRAG-01)

**Location**: `session_manager.py` — add new method after `__init__`

Add method to `SessionManager`:

```python
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
```

**Location**: `api/app/main.py` — add lifespan hook

Replace the `app = FastAPI(...)` block to add a lifespan:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: recover orphaned sessions
    from app.session_manager import session_manager
    await session_manager.recover_from_cosmos()
    yield
    # Shutdown: no cleanup needed (sessions persist to Cosmos on finalize)

app = FastAPI(
    title="Autonomous Network NOC API",
    version="0.1.0",
    description="Backend API for the Autonomous Network NOC Demo",
    lifespan=lifespan,
)
```

#### 3b. `_persist_to_cosmos` retry with backoff (H-FRAG-02)

**Location**: `session_manager.py` L267–L278

Replace the method:

```python
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
```

### Verification

1. Deploy, create and complete a session, then restart the container.
   Verify: the session appears in the sidebar as "Failed" with the
   recovery message, not "In Progress".
2. Temporarily block the graph-query-api (e.g., stop the process),
   complete a session → verify log shows retry attempts (2s, 4s delays)
   and the session remains in `_recent` after all retries fail.
3. Restore graph-query-api → next session finalize should persist normally.

### Risk Assessment

- **3a**: **Medium risk** — the lifespan hook runs on every startup. If the
  Cosmos query fails (timeout, auth), the startup continues (exception is
  caught). If it incorrectly marks sessions as failed, users lose
  investigations. Mitigation: only marks `in_progress` sessions, which by
  definition cannot be resumed after a restart anyway.
- **3b**: Low risk — adds retries to an existing fire-and-forget persist.
  The worst case is the same as today (persist fails silently) but now
  with 3 attempts instead of 1.

---

## Phase 4: Data Integrity

### Issues Resolved

`H-DATA-01`, `H-DATA-02`, `H-MODEL-01`

### Files Touched

- `api/app/sessions.py` — `to_dict`
- `api/app/session_manager.py` — `start` (push initial user_message)
- `graph-query-api/router_sessions.py` — `list_sessions`, `upsert_session`
- `graph-query-api/router_interactions.py` — `save_interaction`,
  `list_interactions`

### Changes

#### 4a. Add `_docType` discriminator (H-DATA-01)

**`api/app/sessions.py`** — `to_dict()` method

Add `"_docType": "session"` to the returned dict:

```python
def to_dict(self) -> dict:
    return {
        "_docType": "session",
        "id": self.id,
        # ... rest unchanged
    }
```

**`graph-query-api/router_sessions.py`** — `list_sessions`

Change the base query from `SELECT * FROM c` to:

```python
query = "SELECT * FROM c WHERE c._docType = 'session'"
```

And when `scenario` is also provided:

```python
if scenario:
    query += " AND c.scenario = @scenario"
```

**`graph-query-api/router_interactions.py`** — `save_interaction`

Add `"_docType": "interaction"` to the document dict at L86:

```python
doc = {
    "_docType": "interaction",
    "id": str(uuid.uuid4()),
    # ... rest unchanged
}
```

**`graph-query-api/router_interactions.py`** — `list_interactions`

Change the base query to:

```python
query = "SELECT * FROM c WHERE c._docType = 'interaction'"
```

And when `scenario` is also provided:

```python
if scenario:
    query += " AND c.scenario = @scenario"
```

#### 4b. Cap `event_log` size (H-DATA-02)

**`api/app/sessions.py`** — `push_event` method

Add a size cap at the top of `push_event`:

```python
MAX_EVENT_LOG_SIZE = 500

def push_event(self, event: dict):
    with self._lock:
        self.event_log.append(event)
        # Cap event_log to prevent Cosmos 2MB document limit breach.
        # Oldest events are dropped; the frontend reconstructs from
        # the tail anyway (follow-up turns use `since` offset).
        if len(self.event_log) > MAX_EVENT_LOG_SIZE:
            self.event_log = self.event_log[-MAX_EVENT_LOG_SIZE:]
        self.updated_at = datetime.now(timezone.utc).isoformat()
        snapshot = list(self._subscribers)
    # ... rest unchanged
```

#### 4c. Push initial `user_message` event (H-MODEL-01)

**`api/app/session_manager.py`** — `start` method

Add before `session.status = SessionStatus.IN_PROGRESS`:

```python
async def start(self, session: Session):
    """Launch the orchestrator for this session in a background task."""
    # Push initial user message to event_log so the first turn is
    # structurally consistent with follow-up turns (H-MODEL-01).
    session.push_event({
        "event": "user_message",
        "turn": 0,
        "data": json.dumps({"text": session.alert_text}),
    })
    session.status = SessionStatus.IN_PROGRESS
    # ... rest unchanged
```

### Verification

1. Create a session → verify Cosmos document has `"_docType": "session"`.
2. Save an interaction → verify Cosmos document has `"_docType": "interaction"`.
3. Call `GET /query/sessions` → verify only session documents are returned
   (no interaction documents mixed in).
4. Create a session and inspect its `event_log` → verify the first event
   is `user_message` with the alert text.
5. Create a session with many steps (or simulate by appending 600 events)
   → verify `event_log` is capped at 500.

### Risk Assessment

- **4a**: **Medium risk** — existing documents in Cosmos lack `_docType`.
  The `WHERE c._docType = 'session'` filter will **exclude** all existing
  documents from list queries until they are re-persisted. **Mitigation**:
  Change the filter to `WHERE (c._docType = 'session' OR NOT IS_DEFINED(c._docType))`
  for backward compatibility. This is recommended.
- **4b**: Low risk — only affects sessions with >500 events, which are
  extreme outliers. The frontend only replays from `since` offset anyway.
- **4c**: Low risk — adds one event at session start. The frontend's
  `loadSessionMessages` already handles `user_message` events. The
  synthesized fallback (`L289–L294`) still works (the check is
  `msgs[0].role !== 'user'` — now the first message IS `user`, so the
  fallback is skipped, which is correct).

---

## Phase 5: SSE Transport Hardening

### Issues Resolved

`H-SSE-03`, `H-MODEL-04`

### Files Touched

- `api/app/routers/sessions.py` — `stream_session` SSE generator
- `frontend/src/hooks/useSession.ts` — `updateOrchestratorMessage` switch

### Changes

#### 5a. Fix final event drain race (H-SSE-03)

**Location**: `routers/sessions.py` L95–L112

After the `while True` loop breaks (line `if session.status != SessionStatus.IN_PROGRESS: break`),
replace the immediate drain:

```python
                    if session.status != SessionStatus.IN_PROGRESS:
                        # Drain remaining events
                        while not live_queue.empty():
                            yield live_queue.get_nowait()
                        break
```

With a short yield to let `call_soon_threadsafe` callbacks complete:

```python
                    if session.status != SessionStatus.IN_PROGRESS:
                        # Allow in-flight call_soon_threadsafe callbacks
                        # to land before draining the queue.
                        await asyncio.sleep(0.05)
                        while not live_queue.empty():
                            yield live_queue.get_nowait()
                        break
```

#### 5b. Handle `status_change` event in frontend (H-MODEL-04)

**Location**: `useSession.ts` L22–L79, inside the `updateOrchestratorMessage`
switch statement

Add after the `case 'error':` block:

```typescript
case 'status_change':
  // Server-side status feedback (e.g., "cancelling")
  updated.statusMessage = data.message as string | undefined;
  break;
```

And add `statusMessage?: string` to the `ChatMessage` type in
`frontend/src/types/index.ts` L191–L207.

**Location**: `frontend/src/components/ChatPanel.tsx` — render the status
message

After the ThinkingDots block (`L95–L97`), add:

```tsx
{msg.statusMessage && (
  <div className="glass-card p-2 border-brand/20 bg-brand/5">
    <span className="text-xs text-brand">ℹ {msg.statusMessage}</span>
  </div>
)}
```

Also handle in the SSE `connectToStream` thinking state block
(`useSession.ts` L103–L115`):

```typescript
} else if (ev.event === 'status_change') {
  setThinking({ agent: 'System', status: data.message ?? 'Status update' });
}
```

### Verification

1. Start an investigation, cancel it → verify the chat panel shows
   "ℹ Cancellation requested — waiting for current agent call to finish."
   instead of silently ignoring the cancel.
2. Complete a multi-step investigation → verify the final `message` and
   `run_complete` events are not missed (check that DiagnosisBlock and
   RunMeta footer appear correctly).

### Risk Assessment

- **5a**: Low risk — adds a 50ms yield. Worst case: 50ms added latency
  on session completion.
- **5b**: Low risk — adds a new case to the switch. Existing events are
  unaffected. The `statusMessage` field is optional and only rendered
  when present.

---

## Phase 6: Cleanup & Model Completeness

### Issues Resolved

`H-MODEL-02`, `H-BUG-04`, `H-DATA-04`

### Files Touched

- `api/app/main.py` — remove `alert.router` mount
- `api/app/session_manager.py` — `continue_session` event handler
- `graph-query-api/router_sessions.py` — parameterize `limit`

### Changes

#### 6a. Remove legacy alert endpoint (H-MODEL-02)

**Location**: `api/app/main.py` L45

Remove or comment out:

```python
# app.include_router(alert.router)  # Deprecated: use /api/sessions
```

Also remove the import at the top of the file:

```python
from app.routers import agents, logs, config, sessions  # noqa: E402
# (remove alert from the import)
```

#### 6b. Handle `thread_created` in `continue_session` (H-BUG-04)

**Location**: `session_manager.py` — `continue_session._run()` event handler
(~L231–L246)

Add after the `elif ev_type == "error":` block:

```python
                    elif ev_type == "thread_created":
                        data = _parse_data(event)
                        new_tid = data.get("thread_id")
                        if new_tid and new_tid != session.thread_id:
                            logger.info(
                                "Session %s thread_id updated: %s → %s",
                                session.id, session.thread_id, new_tid,
                            )
                            session.thread_id = new_tid
```

#### 6c. Parameterize `limit` in `list_sessions` query (H-DATA-04)

**Location**: `graph-query-api/router_sessions.py` L53–L55

Replace:

```python
    query += f" ORDER BY c.created_at DESC OFFSET 0 LIMIT {int(limit)}"
```

With:

```python
    query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
    params.append({"name": "@limit", "value": int(limit)})
```

### Verification

1. Attempt `POST /api/alert` → verify 404 (endpoint removed).
2. Send a follow-up message → verify no warnings about unhandled
   `thread_created` events in logs.
3. Call `GET /query/sessions?limit=5` → verify only 5 results returned
   (parameterized query works correctly).

### Risk Assessment

- **6a**: **Medium risk** — if any external client still calls
  `/api/alert`, it will break. Mitigation: confirm no external consumers
  exist. The frontend does not use this endpoint.
- **6b**: Low risk — adds an event handler case. Only fires if the
  orchestrator changes the thread_id (which it currently does not).
- **6c**: Zero risk — parameterization produces identical query results.

---

## Excluded Issues

| ID | Severity | Reason |
|----|----------|--------|
| H-INEFF-01 | high | SSEEventHandler deduplication is a refactor (~800 lines), not a bug fix. Requires its own task with dedicated testing to avoid regression in orchestrator event handling. |
| H-INEFF-02 | high | Same as H-INEFF-01 — `_thread_target` dedup is part of the same refactor. |
| H-INEFF-03 | low | Nested `_is_capacity_error` — trivial, folded into the H-INEFF-01/02 refactor. |
| H-INEFF-04 | low | Subscriber list copy in `push_event` — acceptable at current scale. Not a bug. |
| H-BUG-02 | medium | Steps accumulating across turns — accepted behavior. The frontend reconstructs per-turn from `event_log`. The `steps` field on the session is a convenience aggregate, not the source of truth. |
| H-BUG-03 | medium | Diagnosis overwritten per turn — accepted behavior. Same reasoning: `event_log` is the source of truth; `diagnosis` is "latest diagnosis" by design. |
| H-FRAG-03 | medium | Idle timeout single-instance — not a bug in current single-container deployment. Document the constraint; no code change. |
| H-FRAG-04 | medium | Cancel/finalize race — inherent to cooperative cancellation. The current behavior (cancel-too-late = COMPLETED) is correct. Document. |
| H-SSE-01 | high | Client-side SSE reconnection — requires UX design decisions (retry count, backoff, notification). Should be its own task. |
| H-SSE-02 | medium | Unlocked status reads — safe under CPython GIL. Not a bug. |
| H-SSE-04 | low | `since` upper bound — frontend always passes correct offset. No user impact. |
| H-ERR-05 | medium | Cross-partition get_session query — performance optimization, not a bug. Should be addressed when scale demands it. |
| H-ERR-06 | medium | No schema validation on `upsert_session` — defense-in-depth. Low priority since the only caller is the trusted API service. |
| H-STATE-01 | medium | Shallow copy / data spread — theoretical concern. No known bug triggered. |
| H-STATE-02 | low | Expand state lost on session switch — minor UX annoyance. |
| H-STATE-03 | low | Regenerated message IDs — contributes to H-STATE-02. Fix when H-STATE-02 is addressed. |
| H-DATA-03 | medium | No TTL on Cosmos docs — operational concern, not a bug. Configure TTL on the Cosmos container via Bicep/portal. |
| H-DATA-05 | low | Transition duplicate risk — handled by existing dedup logic. |
| H-MODEL-03 | medium | No diagnosis streaming — feature enhancement, not a bug fix. Requires coordinated backend + frontend changes. Own task. |
| H-MODEL-05 | low | `run_start` not handled in frontend switch — no impact. |

---

## Summary

| Phase | Issues | Files | Risk |
|-------|--------|-------|------|
| 1 — Frontend Fetch Guards | H-ERR-01/02/03/04, H-STATE-04 | `useSession.ts` | Low |
| 2 — Backend Crash Prevention | H-BUG-01, H-BUG-05, H-FRAG-05 | `session_manager.py`, `routers/sessions.py` | Low–Med |
| 3 — Session Lifecycle | H-FRAG-01, H-FRAG-02 | `session_manager.py`, `main.py` | Medium |
| 4 — Data Integrity | H-DATA-01, H-DATA-02, H-MODEL-01 | `sessions.py`, `session_manager.py`, `router_sessions.py`, `router_interactions.py` | Medium |
| 5 — SSE Transport | H-SSE-03, H-MODEL-04 | `routers/sessions.py`, `useSession.ts`, `types/index.ts`, `ChatPanel.tsx` | Low |
| 6 — Cleanup | H-MODEL-02, H-BUG-04, H-DATA-04 | `main.py`, `session_manager.py`, `router_sessions.py` | Low–Med |

**Total**: 17 issues resolved across 6 phases. 12 issues excluded with rationale.
