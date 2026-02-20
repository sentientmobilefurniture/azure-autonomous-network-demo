# Optimize Session Persistence

## Problem

A single investigation session document can be extremely large:

| Field | Content | Size estimate |
|-------|---------|---------------|
| `alert_text` | Raw alert (15 lines) | ~1 KB |
| `steps[]` | 8–13 step objects, each with `query`, `response`, `visualizations` (graph/table JSON with full result sets) | 200 KB – 1.5 MB |
| `event_log[]` | Every SSE event emitted during the run — `run_start`, `step_thinking`, `step_start`, `step_complete` (duplicates all of `steps`), `message`, `run_complete` | 300 KB – 2 MB |
| `diagnosis` | Final markdown summary | 2–10 KB |

**Total**: 500 KB – 3.5 MB per session. Cosmos DB has a **2 MB document limit**. Multi-turn sessions (2+ turns) compound the problem since `event_log` accumulates across turns.

### Why `event_log` is necessary

The frontend's `loadSessionMessages()` reconstructs the full conversation from `event_log` — it processes `user_message`, `run_start`, `step_complete`, `message`, `run_complete`, and `error` events to rebuild the chat thread with correct turn boundaries. Without `event_log`, session replay would only show a flat list of steps with no conversational structure.

The `steps[]` array is a flattened aggregate — it loses turn boundaries and doesn't include user messages, orchestrator reasoning timing, or error recovery sequences.

### Redundancy

`event_log` and `steps` overlap significantly. Every `step_complete` event in `event_log` contains the same data as the corresponding entry in `steps[]`. The `diagnosis` field duplicates the `message` event's text. This roughly **doubles** the storage for the heaviest content.


## Design: Chunked Session Storage

Split each session into a lightweight **header** document and one or more **chunk** documents. All live in the same Cosmos container (`interactions`) with the same partition key (`/scenario`) for transactional consistency.

### Document Types

```
┌─────────────────────────────────────┐
│ Header Document                      │
│                                      │
│  id: "abc-123"                       │
│  type: "session"                     │
│  scenario: "telecom-playground"      │
│  alert_text: "..."                   │
│  status: "completed"                 │
│  created_at / updated_at             │
│  diagnosis: "..."                    │
│  run_meta: { steps, tokens, time }   │
│  error_detail: ""                    │
│  thread_id: "thread_..."             │
│  turn_count: 2                       │
│  chunk_count: 3                      │
│  step_count: 13                      │
│                                      │
│  (NO event_log, NO steps)            │
│  Size: ~15 KB                        │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ Chunk Document (1 of N)              │
│                                      │
│  id: "abc-123__chunk_0"              │
│  type: "session_chunk"               │
│  session_id: "abc-123"               │
│  scenario: "telecom-playground"      │
│  chunk_index: 0                      │
│  events: [ ... first N events ... ]  │
│                                      │
│  Size: ≤ 1.5 MB                      │
└─────────────────────────────────────┘
```

### Naming Convention

- Header: `id` = session UUID (unchanged)
- Chunk: `id` = `{session_id}__chunk_{index}`
- Both share `scenario` as partition key → same logical partition → point reads and deletes are efficient

### Chunk Sizing Strategy

Target: **max 1.5 MB per chunk** (well under the 2 MB Cosmos limit, with headroom for Cosmos metadata overhead).

Chunking algorithm:
```python
MAX_CHUNK_BYTES = 1_400_000  # Conservative limit — leaves ~600 KB headroom
                              # for chunk document wrapper + Cosmos metadata

def chunk_events(
    event_log: list[dict],
    max_bytes: int = MAX_CHUNK_BYTES,
) -> list[list[dict]]:
    """Split event_log into chunks that fit within Cosmos document size limit.

    Raises ValueError if a single event exceeds max_bytes (indicates a
    visualization payload that needs truncation upstream).
    """
    chunks = []
    current_chunk = []
    current_size = 0

    for event in event_log:
        event_size = len(json.dumps(event).encode("utf-8"))

        # Guard: a single event that exceeds the budget can never fit
        if event_size > max_bytes:
            logger.warning(
                "Single event exceeds chunk limit (%d > %d): event=%s step=%s",
                event_size, max_bytes,
                event.get("event"), event.get("data", {}).get("step", "?"),
            )
            raise ValueError(
                f"Single event too large for chunking ({event_size:,} bytes). "
                f"Truncate visualization payloads before persisting."
            )

        if current_size + event_size > max_bytes and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0
        current_chunk.append(event)
        current_size += event_size

    if current_chunk:
        chunks.append(current_chunk)
    return chunks
```

> **Note on `max_bytes`**: The default of 1.4 MB is deliberately conservative.
> The `event_size` sum counts only the serialized events, not the chunk
> document wrapper (`id`, `type`, `session_id`, `scenario`, `chunk_index`)
> or Cosmos system properties (`_rid`, `_self`, `_etag`, `_ts`). The 600 KB
> headroom under the 2 MB limit absorbs this overhead.

**Typical chunking**: A 13-step investigation with graph/table visualizations would produce 2–3 chunks.

### Eliminating `steps[]` Redundancy

**Drop `steps[]` from persistence entirely.** The header stores `step_count` for sidebar display. Full step data is reconstructed from `event_log` chunks (the `step_complete` events) during replay. This eliminates the single largest source of redundancy.


## Design: User-Initiated Save

### Current Behavior (Automatic)

`_finalize_turn()` in `session_manager.py` automatically calls `_persist_to_cosmos()` as a fire-and-forget task whenever a turn completes or the idle timeout fires. The user has no control over when or whether a session is persisted.

### New Behavior (Manual Save Button)

Persistence becomes **user-initiated**. A green **Save Session** button appears next to the message input. Clicking it:

1. Triggers a `POST /api/sessions/{id}/save` request.
2. **Immediately starts a new blank session** in the UI (the user can keep working).
3. The saved session appears in the sidebar with a **yellow "Saving" indicator** and is **non-interactive** — clicking it is disabled and sending queries to it is blocked.
4. Once the API returns a successful response confirming Cosmos persistence, the sidebar entry transitions to its normal completed state (green ✓) and becomes clickable again.
5. If the save fails, the sidebar entry shows a red "Save failed" indicator with a retry option.

### Why Manual Save

- Avoids the cost of persisting every completed turn automatically (most sessions are throwaway explorations).
- Prevents the 2 MB document limit from silently dropping data on large sessions — the user gets explicit feedback.
- Gives the user control: only sessions worth keeping are saved to Cosmos.

### UX Flow

```
┌──────────────────────────────────────────────────────┐
│  Chat Input Area                                      │
│                                                        │
│  ┌────────────────────────────────────┐  ┌──────────┐ │
│  │  Type a message…                   │  │  Send ➤  │ │
│  └────────────────────────────────────┘  └──────────┘ │
│                                          ┌──────────┐ │
│                                          │ 💾 Save  │ │  ← green, only visible when
│                                          └──────────┘ │    session exists & not running
└──────────────────────────────────────────────────────┘

Click "Save" →

┌────────────────────────────────────────┐
│  Sidebar                               │
│                                        │
│  ┌──────────────────────────────────┐  │
│  │  ● Saving…          2 min ago   │  │  ← yellow indicator, greyed out,
│  │  "BGP peer down on router-7"    │  │    cursor: not-allowed
│  │  13 steps                       │  │
│  └──────────────────────────────────┘  │
│                                        │
│  ┌──────────────────────────────────┐  │
│  │  ✓ Completed        5 min ago   │  │  ← normal, clickable
│  │  "OSPF adjacency flap"         │  │
│  └──────────────────────────────────┘  │
└────────────────────────────────────────┘
```

### Session Status Lifecycle (Updated)

```
PENDING → IN_PROGRESS → COMPLETED → (user clicks Save) → SAVING → SAVED
                                   ↘ (user starts new session without saving) → discarded from memory on idle timeout
```

Add two new statuses to `SessionStatus`:

```python
class SessionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SAVING = "saving"          # NEW — persistence in flight
    SAVED = "saved"            # NEW — confirmed persisted to Cosmos
    FAILED = "failed"
    CANCELLED = "cancelled"
```

### Backend Changes

#### Remove automatic persistence

In `session_manager.py`, `_finalize_turn()` currently calls `asyncio.create_task(self._persist_to_cosmos(session))`. Remove this — turns complete without persisting. The idle timeout still moves sessions to `_recent` (freeing memory) but does **not** persist.

```python
def _finalize_turn(self, session: Session):
    if session._cancel_event.is_set():
        session.status = SessionStatus.CANCELLED
        self._move_to_recent(session)
    elif session.error_detail and not session.diagnosis:
        session.status = SessionStatus.FAILED
        self._move_to_recent(session)
    else:
        session.status = SessionStatus.COMPLETED
        # NO auto-persist — user must click Save
        self._schedule_idle_timeout(session)

def _move_to_recent(self, session: Session):
    """Move session from active to recent cache. NO auto-persist."""
    self._active.pop(session.id, None)
    self._recent[session.id] = session
    if len(self._recent) > MAX_RECENT_SESSIONS:
        self._recent.popitem(last=False)
```

#### New endpoint: `POST /api/sessions/{id}/save`

```python
@router.post("/{session_id}/save")
async def save_session(session_id: str):
    """User-initiated save — persist session to Cosmos DB."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found (may have expired from memory)")
    if session.status == SessionStatus.SAVING:
        raise HTTPException(409, "Save already in progress")
    if session.status == SessionStatus.SAVED:
        return {"ok": True, "id": session_id, "status": "already_saved"}

    session.status = SessionStatus.SAVING
    try:
        await session_manager._persist_to_cosmos(session)
        session.status = SessionStatus.SAVED
        session_manager._move_to_recent(session)
        return {"ok": True, "id": session_id, "status": "saved"}
    except Exception as e:
        session.status = SessionStatus.COMPLETED  # Revert — user can retry
        raise HTTPException(502, f"Failed to persist session: {e}")
```

Key properties:
- **Synchronous** (awaits persistence, doesn't fire-and-forget) — the frontend waits for the response to transition the sidebar state.
- **Idempotent** — re-saving an already-saved session returns `already_saved`.
- **Revertible** — on failure, status reverts to `COMPLETED` so the user can retry.
- The session is moved to `_recent` only after successful persistence, not before.

#### `list_all()` changes

Include the new statuses in the summary so the sidebar can render them:

```python
results.append({
    ...
    "status": s.status.value,   # now includes "saving" / "saved"
    ...
})
```

No code change needed — `status` is already serialized as `s.status.value`.

### Frontend Changes

#### `ChatInput.tsx` — Add Save button

Add a green "Save Session" button. Visible when: `activeSessionId` exists AND `!running` AND session status is not `saving`/`saved`.

```tsx
interface ChatInputProps {
  onSubmit: (text: string) => void;
  onCancel: () => void;
  onSave: () => void;               // NEW
  running: boolean;
  canSave: boolean;                  // NEW — true when session exists, completed, not already saved
  saving: boolean;                   // NEW — true while save in flight
  exampleQuestions?: string[];
}

// Inside the button row, next to Send:
{canSave && (
  <button
    onClick={onSave}
    disabled={saving}
    className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
      saving
        ? 'bg-yellow-600/20 text-yellow-400 cursor-wait'
        : 'bg-green-600/20 text-green-400 hover:bg-green-600/30 border border-green-500/30'
    }`}
    title="Save this session to Cosmos DB"
  >
    {saving ? '⏳ Saving…' : '💾 Save'}
  </button>
)}
```

#### `useSession.ts` — Add `saveSession` action

```typescript
const [savingSessionId, setSavingSessionId] = useState<string | null>(null);

const saveSession = useCallback(async () => {
  if (!activeSessionId || running) return;
  const sessionIdToSave = activeSessionId;
  setSavingSessionId(sessionIdToSave);

  // Immediately start a new session (clears chat, nulls activeSessionId)
  handleNewSession();

  try {
    const res = await fetch(`/api/sessions/${sessionIdToSave}/save`, { method: 'POST' });
    if (!res.ok) throw new Error(`Save failed: ${res.status}`);
    // Success — sidebar will pick up "saved" status on next refetch
  } catch (err) {
    console.error('Save failed:', err);
    // Sidebar shows "Save failed" — user can click to retry
  } finally {
    setSavingSessionId(null);
  }
}, [activeSessionId, running, handleNewSession]);
```

Return `saveSession`, `savingSessionId` from the hook.

#### `SessionSidebar.tsx` — Saving / Save Failed states

Extend `StatusBadge` and `SessionCard`:

```tsx
// New status entries in StatusBadge config:
saving: { icon: '⏳', color: 'text-yellow-400 animate-pulse', label: 'Saving' },
saved:  { icon: '✓', color: 'text-green-400', label: 'Saved' },

// In SessionCard — disable interaction while saving:
<div
  onClick={session.status === 'saving' ? undefined : onClick}
  className={`group rounded-lg border p-2.5 transition-colors ${
    session.status === 'saving'
      ? 'border-yellow-500/20 bg-yellow-500/5 opacity-60 cursor-not-allowed'
      : isActive
        ? 'border-brand/40 bg-brand/10 cursor-pointer'
        : 'border-border-subtle bg-neutral-bg3 hover:border-border-strong hover:bg-neutral-bg4 cursor-pointer'
  }`}
>
```

#### `types/index.ts` — Add new statuses

```typescript
export interface SessionSummary {
  id: string;
  scenario: string;
  alert_text: string;
  status: 'pending' | 'in_progress' | 'completed' | 'saving' | 'saved' | 'failed' | 'cancelled';
  step_count: number;
  created_at: string;
  updated_at: string;
}
```

#### `App.tsx` — Wire up Save button

```tsx
const {
  messages, thinking, running, activeSessionId,
  createSession, sendFollowUp, viewSession, cancelSession,
  handleNewSession, deleteSession,
  saveSession, savingSessionId,     // NEW
} = useSession();

// Determine if save button should be enabled
const canSave = !!activeSessionId && !running;
const saving = savingSessionId !== null;

// Pass to ChatInput:
<ChatInput
  onSubmit={handleSubmit}
  onCancel={cancelSession}
  onSave={saveSession}
  running={running}
  canSave={canSave}
  saving={saving}
  exampleQuestions={SCENARIO.exampleQuestions}
/>
```

### Edge Cases

| Scenario | Handling |
|----------|----------|
| User clicks Save while a turn is still running | Button is disabled (`canSave = false` when `running`). |
| User clicks Save, then immediately views another session | Allowed — the save continues in the background. The old session remains "Saving" in the sidebar until the API responds. |
| Save fails (network error, Cosmos 413, etc.) | Status reverts to `COMPLETED` server-side. Sidebar shows the session as completed — user can view it and retry Save. The `saveSession` catch block can trigger a toast notification. |
| Session expires from memory before user saves | `POST /save` returns 404. Frontend shows a toast: "Session expired — start a new investigation." The unsaved data is lost. This is acceptable since the user chose not to save. |
| Double-click Save | Second request returns `409` (save in progress) — no duplicate writes. |
| User navigates away during save | Save completes server-side regardless. Next session list refresh picks up the "saved" status. |
| Container restart before save | Session is lost from memory. Same as today — but now the user was warned (no false expectation of auto-persistence). |


## API Changes

### graph-query-api (`router_sessions.py`)

#### Write Path: `PUT /query/sessions`

Current: single `upsert(body)`.

New:
```python
@router.put("/sessions", summary="Upsert a session (chunked)")
async def upsert_session(request: Request):
    body = await request.json()
    session_id = body["id"]
    scenario = body["scenario"]
    store = _get_store()

    # 1. Extract event_log, chunk it; compute step_count from steps before dropping
    event_log = body.pop("event_log", [])
    steps = body.pop("steps", [])  # Drop redundant steps array
    body["step_count"] = body.get("step_count") or len(steps)
    chunks = chunk_events(event_log)
    body["chunk_count"] = len(chunks)
    body["type"] = "session"

    # 2. Identify existing chunks that will be orphaned after this write
    existing = await store.list(
        query="SELECT c.id FROM c WHERE c.session_id = @sid AND c.type = 'session_chunk'",
        parameters=[{"name": "@sid", "value": session_id}],
        partition_key=scenario,
    )
    old_chunk_ids = [c["id"] for c in existing]

    # 3. Write new chunks FIRST (crash here → stale header still points
    #    to old chunks which are still valid — no data loss)
    for i, events in enumerate(chunks):
        await store.upsert({
            "id": f"{session_id}__chunk_{i}",
            "type": "session_chunk",
            "session_id": session_id,
            "scenario": scenario,
            "chunk_index": i,
            "events": events,
        })

    # 4. Write header — this atomically makes the new chunks "live"
    #    because chunk_count now matches the new chunk set
    await store.upsert(body)

    # 5. Delete orphaned old chunks (safe: header already points to new set)
    for old_id in old_chunk_ids:
        try:
            await store.delete(old_id, partition_key=scenario)
        except Exception:
            logger.warning("Failed to delete orphaned chunk %s", old_id)

    return {"ok": True, "id": session_id, "chunks": len(chunks)}
```

#### Read Path: `GET /query/sessions/{session_id}`

Current: returns the single document.

New: fetches header + all chunks, reassembles `event_log`:
```python
@router.get("/sessions/{session_id}", summary="Get full session (reassembled)")
async def get_session(session_id: str):
    store = _get_store()

    # Fetch header
    headers = await store.list(
        query="SELECT * FROM c WHERE c.id = @id AND (c.type = 'session' OR NOT IS_DEFINED(c.type))",
        parameters=[{"name": "@id", "value": session_id}],
    )
    if not headers:
        raise HTTPException(404, "Session not found")
    header = headers[0]

    # Fetch chunks (ordered by chunk_index)
    chunk_count = header.get("chunk_count", 0)
    if chunk_count > 0:
        chunks = await store.list(
            query=(
                "SELECT * FROM c WHERE c.session_id = @sid AND c.type = 'session_chunk' "
                "ORDER BY c.chunk_index ASC"
            ),
            parameters=[{"name": "@sid", "value": session_id}],
            partition_key=header.get("scenario"),
        )
        # Reassemble event_log
        event_log = []
        for chunk in sorted(chunks, key=lambda c: c.get("chunk_index", 0)):
            event_log.extend(chunk.get("events", []))
        header["event_log"] = event_log

        # Reconstruct steps from event_log (for backward compat)
        header["steps"] = [
            (json.loads(e["data"]) if isinstance(e.get("data"), str) else e.get("data", {}))
            for e in event_log
            if e.get("event") == "step_complete"
        ]
    elif "event_log" not in header:
        # Legacy document with no chunks and no event_log
        header["event_log"] = []

    return header
```

#### List Path: `GET /query/sessions` — Filter out chunks

The list endpoint returns session summaries (`SELECT * FROM c`). With the split, it naturally returns only headers (chunks have `type = 'session_chunk'` and no `alert_text`/`status` fields). Add a `WHERE` filter for safety — use `IS_DEFINED(c.alert_text)` as a secondary discriminator to avoid surfacing any non-session documents that also lack a `type` field:

```python
query = (
    "SELECT * FROM c "
    "WHERE (c.type = 'session' OR (NOT IS_DEFINED(c.type) AND IS_DEFINED(c.alert_text)))"
)
```

#### Delete Path: `DELETE /query/sessions/{session_id}` — Delete chunks too

The current endpoint accepts `scenario` as an optional query param. When empty, it does a cross-partition lookup to find the session first. The chunk deletion must use the resolved `scenario` value — not the raw query param which may be empty:

```python
# Resolve scenario: use query param if provided, otherwise look up from header
pk = scenario or None
if not pk:
    items = await store.list(
        query="SELECT c.id, c.scenario FROM c WHERE c.id = @id",
        parameters=[{"name": "@id", "value": session_id}],
    )
    if items:
        pk = items[0].get("scenario", "")

# Delete header
if pk:
    await store.delete(session_id, partition_key=pk)

    # Delete associated chunks
    chunks = await store.list(
        query="SELECT c.id FROM c WHERE c.session_id = @sid AND c.type = 'session_chunk'",
        parameters=[{"name": "@sid", "value": session_id}],
        partition_key=pk,
    )
    for chunk in chunks:
        await store.delete(chunk["id"], partition_key=pk)
```

### api service (`session_manager.py`)

**One change required.** `_persist_to_cosmos` sends `session.to_dict()` as the PUT body — no chunking awareness needed. However, `list_all_with_history()` currently derives `step_count` from the `steps` array when backfilling from Cosmos:

```python
# BEFORE (broken after chunking — header has no steps array):
"step_count": len(item.get("steps", []))

# AFTER (falls back to steps for legacy docs):
"step_count": item.get("step_count", len(item.get("steps", [])))
```

This backfill line (currently at line 114) must be updated or historical sessions will show **0 steps** in the sidebar.

### `Session.to_dict()` — Optional cleanup

Could drop `steps` from serialization since graph-query-api now ignores it:
```python
def to_dict(self) -> dict:
    return {
        "id": self.id,
        "scenario": self.scenario,
        "alert_text": self.alert_text,
        "status": self.status.value,
        "created_at": self.created_at,
        "updated_at": self.updated_at,
        "event_log": self.event_log,
        # "steps" omitted — reconstructed from event_log on read
        "step_count": len(self.steps),    # lightweight count for sidebar
        "diagnosis": self.diagnosis,
        "run_meta": self.run_meta,
        "error_detail": self.error_detail,
        "thread_id": self.thread_id,
        "turn_count": self.turn_count,
    }
```

### Frontend — See "Design: User-Initiated Save" section above

Changes to `useSession.ts`, `ChatInput.tsx`, `SessionSidebar.tsx`, `App.tsx`, and `types/index.ts` are detailed under "Design: User-Initiated Save → Frontend Changes".

`loadSessionMessages()` and `viewSession` require no changes — the graph-query-api still reassembles the full document with `event_log` and `steps` before returning.


## Backward Compatibility

| Scenario | Handling |
|----------|----------|
| Old sessions (pre-chunking) in Cosmos | No `type` field, no `chunk_count`. The read path checks `NOT IS_DEFINED(c.type)` and returns them as-is. `loadSessionMessages` works unchanged. |
| New sessions read by old code | Old code does `SELECT * FROM c WHERE c.id = @id` — gets only the header (no `event_log`). Would break replay. **Mitigation**: deploy graph-query-api before api service. |
| Session with 0 events | `chunk_count = 0`, no chunks written, header has empty `event_log`. |


## Size Analysis

A 13-step, 2-turn session (the heaviest observed):

| | Before (single doc) | After (header + chunks) |
|---|---|---|
| Header | — | ~15 KB (metadata + diagnosis) |
| Chunk 0 | — | ~800 KB (turn 1: run_start, 8× step_complete, message, run_complete) |
| Chunk 1 | — | ~500 KB (turn 2: user_message, run_start, 5× step_complete, message, run_complete) |
| **Total Cosmos storage** | 2.5 MB (**EXCEEDS 2 MB LIMIT**) | 1.3 MB (split across 3 docs, each under limit) |

The ~50% reduction comes from dropping the redundant `steps[]` array.


## Execution Order

1. **graph-query-api** — Update `router_sessions.py`: chunked write (with crash-safe ordering), reassembled read, cascaded delete. Add `chunk_events()` helper.
2. **api service** — Three changes:
   - `Session.to_dict()` (`api/app/sessions.py`): replace `steps` with `step_count`. Add `SAVING`/`SAVED` to `SessionStatus`.
   - `list_all_with_history()` (`api/app/session_manager.py`): read `step_count` from header, fall back to `len(steps)` for legacy docs.
   - `_finalize_turn()` / `_move_to_recent()` (`api/app/session_manager.py`): remove auto-persist.
   - New endpoint `POST /api/sessions/{id}/save` (`api/app/routers/sessions.py`): synchronous user-initiated persist.
3. **Frontend** — Four changes:
   - `useSession.ts`: add `saveSession` action + `savingSessionId` state.
   - `ChatInput.tsx`: add green Save button (props: `onSave`, `canSave`, `saving`).
   - `App.tsx`: wire `saveSession` / `canSave` / `saving` from hook to `ChatInput`.
   - `SessionSidebar.tsx`: add `saving`/`saved` status badge variants; disable click while saving.
   - `types/index.ts`: add `'saving' | 'saved'` to `SessionSummary.status` union.
4. **Test** — Run an investigation, click Save, verify:
   - Session persists to Cosmos (chunked).
   - Sidebar transitions: Saving → Saved.
   - New blank session starts immediately.
   - Replay works after save completes.
   - Failed save reverts to Completed (retryable).
5. **Backfill** (optional) — One-time script to re-chunk any oversized legacy documents.

## Files to Touch

| File | Change |
|------|--------|
| `graph-query-api/router_sessions.py` | Chunked write/read/delete logic, `chunk_events()` helper |
| `api/app/sessions.py` | `to_dict()`: replace `steps` with `step_count`. Add `SAVING`/`SAVED` to `SessionStatus`. |
| `api/app/session_manager.py` | Remove auto-persist from `_finalize_turn()` and `_move_to_recent()`. Fix `list_all_with_history()` `step_count`. |
| `api/app/routers/sessions.py` | New `POST /{id}/save` endpoint (synchronous persist). |
| `frontend/src/hooks/useSession.ts` | `saveSession` action, `savingSessionId` state. |
| `frontend/src/components/ChatInput.tsx` | Green Save button (`onSave`, `canSave`, `saving` props). |
| `frontend/src/components/SessionSidebar.tsx` | `saving`/`saved` status badges; disable click while saving. |
| `frontend/src/App.tsx` | Wire `saveSession` / `canSave` / `saving` to `ChatInput`. |
| `frontend/src/types/index.ts` | Add `'saving' | 'saved'` to `SessionSummary.status`. |

## Risks

- **Read cost**: Reassembling a session requires 1 header query + 1 chunk query (2 queries vs. current 1). The header query is cross-partition (no `partition_key` param — the caller doesn't know the scenario yet), costing 3–10 RU. The chunk query targets a single partition (~3 RU). Total: **6–13 RU** vs. ~3 RU today. Acceptable for a detail-view endpoint.
- **Write cost**: 1 header upsert + N chunk upserts + old chunk deletes. Slightly more than the current single upsert, but avoids the catastrophic failure of a >2 MB document being silently rejected.
- **Consistency**: Write ordering is crash-safe: new chunks are written first, header is updated second (atomically switching `chunk_count` to the new set), orphaned old chunks are deleted last. If the process crashes:
  - After writing chunks but before header update → stale header still points to old (valid) chunks. No data loss.
  - After header update but before orphan cleanup → orphaned chunks waste storage but don't affect reads (header's `chunk_count` controls which chunks are loaded).
  - A concurrent `GET` during the write may see a briefly inconsistent state. For stronger guarantees, use Cosmos transactional batch (same partition key requirement is already satisfied).
- **Oversized events**: A single `step_complete` event with very large visualization payloads could exceed the per-chunk limit. The `chunk_events()` helper raises `ValueError` in this case. Upstream code should truncate or compress large visualization payloads before persisting.
- **Unsaved sessions lost on restart**: With auto-persist removed, container restarts discard all unsaved sessions. This is by design — the user chose not to save. Consider a toast warning ("You have unsaved sessions") on `beforeunload` if any in-memory sessions have `status = COMPLETED` (not `SAVED`).
- **Memory pressure**: Without auto-persist, long-lived sessions stay in memory longer (until idle timeout + `_move_to_recent` eviction). The existing `MAX_RECENT_SESSIONS` cap and 10-minute idle timeout mitigate this.
