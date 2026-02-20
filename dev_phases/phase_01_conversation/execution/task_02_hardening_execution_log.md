# Task 02: Conversation Hardening — Execution Log

> Strategy: [task_02_hardening.md](../strategy/task_02_hardening.md)

**Status**: complete  
**Date**: 2025-02-20

---

## Issue Inventory

Issues already documented in task_01 §10 (UX Friction Points) are referenced
by their §10.N number but not re-described. This document adds new findings
and technical depth.

---

### 1. Backend Bugs

#### H-BUG-01 — `_parse_data` crashes on malformed JSON in event_log

- **Severity**: high
- **Location**: `api/app/session_manager.py` L36–L40
- **Description**: `_parse_data()` calls `json.loads(raw)` with no try/except; a malformed `data` string in an event dict will raise `json.JSONDecodeError`, crashing the `_run()` task and marking the session as FAILED.
- **Impact**: A single malformed event from the orchestrator (e.g., truncated JSON) kills the entire session.
- **Evidence**: `_parse_data` is called on every event in `start()` L176–L191 and `continue_session()` L231–L246. The exception propagates to the `except Exception` handler which sets `FAILED`.
- **Suggested Fix**: Wrap `json.loads` in try/except, log a warning, and return `{}` on failure so the session survives.

#### H-BUG-02 — Steps accumulate across turns without reset

- **Severity**: medium
- **Location**: `api/app/session_manager.py` L178 (start), L233 (continue_session)
- **Description**: `session.steps.append(data)` appends to the same list across all turns. The step list grows monotonically and `session.run_meta` is overwritten on each turn, creating a mismatch between `run_meta.steps` (current turn's count) and `len(session.steps)` (all turns).
- **Impact**: When the session is persisted to Cosmos, `steps` contains all steps from all turns but `run_meta` only reflects the last turn. Sidebar shows `step_count` from the full list but `run_meta.time` from the last turn.
- **Evidence**: Compare `session_manager.py` L178 (`session.steps.append(data)`) with L183 (`session.run_meta = data` — overwrites per turn).
- **Suggested Fix**: Either reset `steps` per turn (and maintain a `all_steps` list), or structure `run_meta` to accumulate across turns.

#### H-BUG-03 — `diagnosis` is overwritten on each turn, losing prior diagnoses

- **Severity**: medium
- **Location**: `api/app/session_manager.py` L181, L239
- **Description**: `session.diagnosis = data.get("text", "")` replaces the diagnosis string on every `message` event. In a multi-turn session, only the last turn's diagnosis is preserved.
- **Impact**: When viewing a persisted multi-turn session, the `diagnosis` field contains only the final turn's response. Prior turn diagnoses exist only in the `event_log` array.
- **Evidence**: `session_manager.py` L181 and L239 — simple assignment, not append.
- **Suggested Fix**: Either append to a per-turn structure, or accept that `diagnosis` is always "latest" and ensure the frontend reconstructs all diagnoses from `event_log`.

#### H-BUG-04 — `continue_session` does not re-emit `thread_created` event

- **Severity**: low
- **Location**: `api/app/session_manager.py` L225–L247
- **Description**: On a follow-up turn, `continue_session` passes `existing_thread_id` to `run_orchestrator_session`, which re-emits a `thread_created` event with the same thread_id. The `start()` handler at L188–L190 captures this, but `continue_session` at L231–L246 does not have a `thread_created` handler.
- **Impact**: If the orchestrator ever changed the thread_id on a follow-up (unlikely but possible), the session would not track it. Low severity because the thread_id doesn't actually change.
- **Suggested Fix**: Add `thread_created` case in `continue_session`'s event handler, or filter out the redundant event.

#### H-BUG-05 — `_finalize_turn` logic: error_detail + diagnosis → COMPLETED, not FAILED

- **Severity**: medium
- **Location**: `api/app/session_manager.py` L122–L129
- **Description**: `_finalize_turn` marks a session as FAILED only if `session.error_detail and not session.diagnosis`. If a run produces both an error AND a partial diagnosis (e.g., error on retry but diagnosis from attempt 1), the session is marked COMPLETED despite having an error.
- **Impact**: Sessions that partially succeeded but ultimately errored are shown as "Completed" in the sidebar. The user sees a green checkmark but the investigation is incomplete.
- **Evidence**: `session_manager.py` L125–L126: `elif session.error_detail and not session.diagnosis`.
- **Suggested Fix**: Check `session.error_detail` independently and use a `PARTIAL` status, or prioritize error over diagnosis.

---

### 2. Code Duplication / Inefficiency

#### H-INEFF-01 — SSEEventHandler duplicated in full (≈800 lines total)

- **Severity**: high
- **Location**: `api/app/orchestrator.py` L117–L570 (first copy) and L823–L1210 (second copy)
- **Description**: The `SSEEventHandler` class is copy-pasted in its entirety between `run_orchestrator()` and `run_orchestrator_session()`. Both copies include identical methods: `on_thread_run`, `_resolve_agent_name`, `_extract_arguments`, `_parse_structured_output`, `on_run_step`, `on_message_delta`, `on_error`.
- **Impact**: Any bug fix, feature addition, or behavioral change must be applied in two places. Divergence is inevitable and has already occurred (the session copy adds cancel_event checks in `_thread_target` but the handler class itself is identical).
- **Suggested Fix**: Extract `SSEEventHandler` to a module-level class parameterized with the `_put` closure (passed via constructor). Use one class in both generators.

#### H-INEFF-02 — `_thread_target` duplicated (≈200 lines each)

- **Severity**: high
- **Location**: `api/app/orchestrator.py` L572–L771 (first) and L1230–L1425 (second)
- **Description**: The thread target function is duplicated. The session version adds cancel_event checks and thread reuse but is otherwise identical (FunctionTool setup, retry loop, message fallback, error handling).
- **Impact**: Same maintenance burden as H-INEFF-01. The two copies have diverged: the session version checks `cancel_event` in two places; the legacy version has `EVENT_TIMEOUT`. Any fix to retry logic must be applied twice.
- **Suggested Fix**: Merge into a single function parameterized with `cancel_event` (optional), `existing_thread_id` (optional), and `use_event_timeout` (bool).

#### H-INEFF-03 — `_is_capacity_error` duplicated as a nested function

- **Severity**: low
- **Location**: `api/app/orchestrator.py` L572–L581 and L1230–L1239
- **Description**: The capacity error detection function is defined twice as a nested function inside each `_thread_target`.
- **Impact**: Minor — but adds to the duplication tax.
- **Suggested Fix**: Extract to module level.

#### H-INEFF-04 — `list(self._subscribers)` snapshot on every push_event

- **Severity**: low
- **Location**: `api/app/sessions.py` L81
- **Description**: `push_event` creates a full copy of the subscribers list on every event under the lock. For high-frequency events (step_response + step_complete emitted as pairs), this is two list copies per step.
- **Impact**: Negligible for ≤10 subscribers but scales linearly. More a style issue than a performance problem at current scale.
- **Suggested Fix**: Acceptable as-is. Could optimize with a copy-on-write pattern if subscriber counts grow.

---

### 3. Session Lifecycle Fragilities

#### H-FRAG-01 — In-memory sessions lost on container restart

- **Severity**: critical
- **Location**: `api/app/session_manager.py` L48–L49
- **Description**: `_active` and `_recent` dicts are in-memory only. A container restart loses all active sessions. The orchestrator threads die, Foundry threads become orphaned, and in-progress investigations cannot be resumed.
- **Impact**: Users see "Session not found" for any session that wasn't persisted to Cosmos before the restart. In-progress sessions are unrecoverable.
- **Evidence**: `SessionManager.__init__` creates empty dicts. No startup recovery logic exists.
- **Suggested Fix**: On startup, query Cosmos for `status: in_progress` sessions and mark them as `failed` with an explanation. Optionally, re-hydrate completed sessions into `_recent`.

#### H-FRAG-02 — `_persist_to_cosmos` failure is silently swallowed

- **Severity**: high
- **Location**: `api/app/session_manager.py` L269–L278
- **Description**: `_persist_to_cosmos` logs the exception but does not retry, queue for later, or notify the user. A Cosmos timeout or transient error means the session is lost when it's eventually evicted from `_recent`.
- **Impact**: Session data is permanently lost. The user sees the session in the sidebar (from memory) but after a restart it's gone.
- **Evidence**: `except Exception: logger.exception(...)` — no retry, no fallback.
- **Suggested Fix**: Add a retry with exponential backoff (2–3 attempts). If all retries fail, keep the session in `_recent` until the next successful persist.

#### H-FRAG-03 — Idle timeout is single-instance (`asyncio.Task`)

- **Severity**: medium
- **Location**: `api/app/session_manager.py` L141–L155
- **Description**: The idle timeout is an `asyncio.Task` within a single process. In a multi-replica deployment, only the instance that owns the session's `_active` entry runs the timeout. Other replicas cannot finalize the session.
- **Impact**: In single-container deployment (current): no issue. In scaled deployment: sessions leak in `_active` indefinitely on non-owner replicas. However, since `SessionManager` is a process singleton, this only matters if load-balanced.
- **Suggested Fix**: Document the single-instance constraint. For multi-instance: use Cosmos TTL or a distributed timer.

#### H-FRAG-04 — Race condition between cancel and finalize

- **Severity**: medium
- **Location**: `api/app/session_manager.py` L118–L135, `api/app/routers/sessions.py` L127–L141
- **Description**: `cancel_session` sets `_cancel_event` and pushes a `status_change` event. Concurrently, the orchestrator thread may already be in `_finalize_turn`. If `_finalize_turn` reads `_cancel_event.is_set()` before `cancel_session` sets it (timing window), the session is marked COMPLETED instead of CANCELLED.
- **Impact**: User cancels but the session shows as "Completed". The cancel was too late — the orchestrator had already finished.
- **Evidence**: No atomic coordination between the cancel POST and `_finalize_turn`. The `_cancel_event` is checked in `_finalize_turn` (L118) but the orchestrator thread may call `_finalize_turn` before the cancel POST handler runs.
- **Suggested Fix**: This is fundamentally a race in cooperative cancellation. The current behavior (cancel-too-late results in COMPLETED) is arguably correct — document it. Alternatively, check `_cancel_event` once more after `_finalize_turn` and override to CANCELLED if set.

#### H-FRAG-05 — `create_session` raises RuntimeError for max sessions — unhandled by router

- **Severity**: medium
- **Location**: `api/app/session_manager.py` L53, `api/app/routers/sessions.py` L42
- **Description**: `session_manager.create()` raises `RuntimeError("Too many concurrent sessions")` but `create_session` in the router doesn't catch it. FastAPI converts uncaught exceptions to HTTP 500 with a generic error.
- **Impact**: User gets a confusing 500 error instead of a clear "Too many concurrent sessions" message.
- **Evidence**: `routers/sessions.py` L42: `session = session_manager.create(...)` — no try/except or HTTPException mapping.
- **Suggested Fix**: Catch `RuntimeError` in the router and return HTTP 429 or 503 with the message.

---

### 4. SSE Transport Issues

#### H-SSE-01 — No client-side reconnection on SSE disconnect

- **Severity**: high
- **Location**: `frontend/src/hooks/useSession.ts` L125–L131
- **Description**: `onerror` throws to prevent `fetchEventSource` from retrying. If the network drops temporarily or the server restarts, the SSE stream dies permanently. No reconnection attempt is made.
- **Impact**: The investigation stops updating silently. The user sees a frozen UI with no error indication. Already noted as task_01 §10.10.
- **Suggested Fix**: Implement a reconnect strategy: on error, wait 2s then call `viewSession(activeSessionId)` to re-fetch state and optionally reconnect if still in_progress.

#### H-SSE-02 — `stream_session` checks `session.status` outside the lock

- **Severity**: medium
- **Location**: `api/app/routers/sessions.py` L90, L98–L99
- **Description**: `stream_session` reads `session.status` in the SSE loop without acquiring `session._lock`. The orchestrator thread may update `session.status` concurrently (via `_finalize_turn`). On CPython this is safe due to the GIL for simple attribute reads, but it's a correctness issue in principle.
- **Impact**: Extremely unlikely to cause a bug in practice (CPython GIL protects enum assignment). But the pattern is fragile if the codebase ever moves to a GIL-free Python runtime.
- **Suggested Fix**: Acceptable as-is. If concerned, read `session.status` under `session._lock`.

#### H-SSE-03 — SSE stream can miss the final events

- **Severity**: medium
- **Location**: `api/app/routers/sessions.py` L95–L103
- **Description**: After the `while` loop breaks (because `session.status != IN_PROGRESS`), the code drains the queue with `get_nowait()`. But events pushed between the last `wait_for` wakeup and the status check may still be in transit via `call_soon_threadsafe` and not yet in the queue.
- **Impact**: The final `run_complete` or `message` event may be missed by the SSE client. The frontend would show the session as still "investigating" until a page refresh or session re-select.
- **Evidence**: `push_event` uses `loop.call_soon_threadsafe(q.put_nowait, event)` — the event is scheduled but not yet in the queue at the instant the loop checks `session.status`.
- **Suggested Fix**: After the status change, add a short `await asyncio.sleep(0.1)` before draining, or drain in a loop until the queue is empty for N consecutive iterations.

#### H-SSE-04 — No `since` upper bound validation

- **Severity**: low
- **Location**: `api/app/routers/sessions.py` L80
- **Description**: The `since` query param is validated as `ge=0` but has no upper bound. A `since` value larger than `event_log` length results in an empty history snapshot and no error. `subscribe(since_index=999999)` silently skips all events.
- **Impact**: Malformed frontend requests could miss all history. In practice, the frontend always passes the correct offset from the `/message` endpoint response.
- **Suggested Fix**: Clamp `since` to `min(since, session.event_count)` in `subscribe`.

---

### 5. Error Handling Gaps

#### H-ERR-01 — `viewSession` fetch has no `.ok` check

- **Severity**: high
- **Location**: `frontend/src/hooks/useSession.ts` L305–L308
- **Description**: `viewSession` calls `fetch(GET /api/sessions/{id})` and immediately parses the response as `SessionDetail` with no status check. A 404 or 500 response body is treated as a valid session.
- **Impact**: `loadSessionMessages` receives a malformed object (e.g., `{"detail": "Session not found"}`). `event_log` is undefined, the `for` loop crashes, and the chat panel shows a blank or broken state with a console error.
- **Evidence**: `useSession.ts` L306: `const session: SessionDetail = await res.json();` — no `if (!res.ok)` guard.
- **Suggested Fix**: Add `if (!res.ok) { setMessages([]); return; }` or show an error toast.

Already noted as task_01 §10.4.

#### H-ERR-02 — `createSession` fetch has no `.ok` check

- **Severity**: high
- **Location**: `frontend/src/hooks/useSession.ts` L149–L153
- **Description**: `createSession` calls `POST /api/sessions` and destructures `session_id` from the response. If the server returns an error (e.g., 500 from max sessions exceeded — H-FRAG-05), `session_id` is `undefined`. The code then calls `setActiveSessionId(undefined)` and `connectToStream(undefined, orchMsgId)`, which constructs the URL `/api/sessions/undefined/stream`.
- **Impact**: The SSE connection hits a 404, the `onerror` handler throws, `running` becomes false, and the user sees a blank orchestrator message with no error explanation.
- **Evidence**: `useSession.ts` L153: `const { session_id } = await res.json();` — no guard.
- **Suggested Fix**: Check `res.ok`. If not, parse the error and show it to the user.

#### H-ERR-03 — `sendFollowUp` fetch has no `.ok` check

- **Severity**: high
- **Location**: `frontend/src/hooks/useSession.ts` L186–L192
- **Description**: Same pattern as H-ERR-02. If `POST /api/sessions/{id}/message` returns 409 (already processing) or 400 (no thread_id), the code destructures `event_offset` as `undefined`, defaulting to `0`. The SSE stream replays the entire session history instead of just the new turn.
- **Impact**: All prior events replay, duplicating steps in the UI. The user sees a confusing double-render of previous steps.
- **Evidence**: `useSession.ts` L190: `const { event_offset = 0 } = await res.json();` — the `= 0` default masks the error.
- **Suggested Fix**: Check `res.ok`. On 409, show "Session is already processing". On 400, show "Cannot follow up on this session".

#### H-ERR-04 — `cancelSession` fetch has no `.ok` check and no error handling

- **Severity**: medium
- **Location**: `frontend/src/hooks/useSession.ts` L254–L259
- **Description**: `cancelSession` calls `POST /cancel` with no error handling. If the session has already completed (server returns `{status, message: "Not running"}`), the response is silently ignored.
- **Impact**: Minor — the cancel is a no-op. But a network error during cancel is also silently swallowed, which could confuse the user.
- **Suggested Fix**: Wrap in try/catch and optionally show a toast.

#### H-ERR-05 — Cosmos `get_session` cross-partition query is slow and unindexed

- **Severity**: medium
- **Location**: `graph-query-api/router_sessions.py` L66–L72
- **Description**: `get_session` does `SELECT * FROM c WHERE c.id = @id` as a cross-partition query (no partition key provided). Cross-partition queries scan all logical partitions.
- **Impact**: Latency increases linearly with the number of scenarios. For a small dataset this is negligible, but at scale it degrades. Also, the full document (including potentially large `event_log` arrays) is transferred.
- **Suggested Fix**: Require `scenario` as a query param (as `delete_session` does), or maintain a secondary lookup.

#### H-ERR-06 — `router_sessions.upsert_session` has no schema validation

- **Severity**: medium
- **Location**: `graph-query-api/router_sessions.py` L78–L83
- **Description**: `upsert_session` accepts any JSON body with `id` and `scenario` and writes it to Cosmos. Malformed data (wrong types, missing fields, extra fields) is persisted without validation.
- **Impact**: If the API service sends a corrupted session dict (e.g., `status` as an int instead of string), it's persisted and returned to the frontend which will fail to render it.
- **Suggested Fix**: Add a Pydantic model for session documents with at least type checking on critical fields.

---

### 6. Frontend State Issues

#### H-STATE-01 — `updateOrchestratorMessage` creates shallow copies that may share nested objects

- **Severity**: medium
- **Location**: `frontend/src/hooks/useSession.ts` L17–L80
- **Description**: `const updated = { ...msg }` creates a shallow copy. If `msg.steps` is mutated elsewhere (it shouldn't be, but TypeScript doesn't enforce deep immutability), the spread doesn't protect against it. More critically, the `data as any` spread in `step_complete` (`L55`) copies all properties from the SSE event data directly onto the step, including any unexpected properties from the backend.
- **Impact**: Unexpected properties from the backend bleed into the step objects. If the backend ever sends a property that conflicts with a StepEvent field (e.g., a `pending` property), it would override the frontend's intended value.
- **Suggested Fix**: Explicitly destructure known fields from `data` instead of spreading the entire object.

#### H-STATE-02 — Expand/collapse state lost on session switch

- **Severity**: low
- **Location**: `frontend/src/components/ChatPanel.tsx` L19–L21
- **Description**: `expandedSteps` and `expandedThoughts` are stored in component state. When the user switches sessions (which replaces `messages`), all expand/collapse states reset because the message IDs change (they're regenerated by `loadSessionMessages` via `crypto.randomUUID()`).
- **Impact**: If the user had expanded a specific step in a session, switching away and back collapses everything. Minor annoyance.
- **Suggested Fix**: Acceptable. To preserve, key expand state by `sessionId + step number` instead of message ID.

#### H-STATE-03 — `loadSessionMessages` generates new IDs on every call

- **Severity**: low
- **Location**: `frontend/src/hooks/useSession.ts` L263, L269, L275, L291
- **Description**: Every call to `loadSessionMessages` generates fresh `crypto.randomUUID()` for each message. This means React keys change on every re-render if `viewSession` is called multiple times, causing full component unmount/remount.
- **Impact**: Minor performance cost. More importantly, it contributes to H-STATE-02 (expand states keyed by ID are invalidated).
- **Suggested Fix**: Derive deterministic IDs from session_id + event index.

#### H-STATE-04 — No loading state during `viewSession` fetch

- **Severity**: medium
- **Location**: `frontend/src/hooks/useSession.ts` L303–L318
- **Description**: Between clicking a session card and the fetch completing, the chat panel shows the **previous** session's messages. No loading indicator or skeleton is shown.
- **Impact**: User may not realize the click registered because the UI doesn't change for 1–2 seconds. They may click again, triggering a second fetch. Already noted as task_01 §10.5.
- **Suggested Fix**: Set `setMessages([])` or a loading sentinel immediately on click, before the fetch.

---

### 7. Data Integrity

#### H-DATA-01 — Sessions and interactions share a container with no type discriminator

- **Severity**: high
- **Location**: `graph-query-api/router_sessions.py` L29–L30, `graph-query-api/router_interactions.py` L30–L31
- **Description**: Both use `database="interactions", container="interactions", pk="/scenario"`. Documents are distinguished only by their shape (sessions have `thread_id`/`turn_count`/`event_log`; interactions have `query`/`steps`/`diagnosis`). No `type` or `_docType` field exists.
- **Impact**: A `SELECT * FROM c` query returns both sessions and interactions mixed. `list_sessions` may return interaction documents (which lack `status`, `event_log`) and vice versa. The frontend would fail to render these.
- **Evidence**: `router_sessions.py` L50: `SELECT * FROM c` with optional scenario filter — no type filter.
- **Suggested Fix**: Add `"_docType": "session"` or `"_docType": "interaction"` to every document. Filter by `_docType` in all queries.

#### H-DATA-02 — Unbounded `event_log` growth

- **Severity**: high
- **Location**: `api/app/sessions.py` L78, persisted via `to_dict()` L140
- **Description**: `event_log` is a list that grows indefinitely. Each SSE event is appended. A multi-turn session with complex investigations can accumulate hundreds of events, each containing full response text and visualization data.
- **Impact**: Cosmos document size limit is 2MB. A session with many steps and large visualizations could exceed this limit and fail to persist. Even below the limit, large documents increase RU cost and network transfer time.
- **Evidence**: `sessions.py` L78: `self.event_log.append(event)` — no size check.
- **Suggested Fix**: Cap event_log at a configurable maximum (e.g., 500 events). When exceeded, truncate older events or split into a separate overflow document. Alternatively, store events in a separate collection keyed by session_id.

#### H-DATA-03 — No TTL on Cosmos documents

- **Severity**: medium
- **Location**: `graph-query-api/cosmos_helpers.py` L95–L135 (container creation)
- **Description**: Containers are created with default settings — no TTL policy. Documents accumulate indefinitely.
- **Impact**: Storage costs grow without bound. Old sessions and interactions are never cleaned up.
- **Suggested Fix**: Set a default TTL of 30–90 days on the container, or add a `_ttl` field to each document.

#### H-DATA-04 — `list_sessions` SQL injection via `limit` parameter

- **Severity**: low
- **Location**: `graph-query-api/router_sessions.py` L55
- **Description**: `query += f" ORDER BY c.created_at DESC OFFSET 0 LIMIT {int(limit)}"` — the `limit` is cast to `int` which prevents injection, but is not parameterized. The `int()` cast is correct but inconsistent with `router_interactions.py` L68 which uses `@limit` as a parameter.
- **Impact**: No actual vulnerability (the `int()` cast is safe and `Query(ge=1, le=200)` validates the range). But inconsistency between routers.
- **Suggested Fix**: Use `@limit` parameterization for consistency.

#### H-DATA-05 — `list_all_with_history` may return duplicates during transition

- **Severity**: low
- **Location**: `api/app/session_manager.py` L94–L117
- **Description**: `list_all_with_history` deduplicates by `id` using `mem_ids`. But there's a window where a session exists in both `_active` (in-memory) and Cosmos (just persisted) with different states. The in-memory version is returned (correct), but a slight timing issue could cause the Cosmos version to appear in a different position in the list.
- **Impact**: Minor — the user might see a session briefly listed twice if the dedup check races with a persist. Extremely unlikely.
- **Suggested Fix**: Acceptable as-is; the `mem_ids` set dedup handles this correctly.

---

### 8. Conversation Model Limitations

#### H-MODEL-01 — No initial `user_message` event for first turn

- **Severity**: medium
- **Location**: `api/app/session_manager.py` L157–L165 (start method)
- **Description**: The `start()` method launches the orchestrator but never pushes a `user_message` event into the event_log for the initial alert. Only follow-up turns generate `user_message` events (via `send_follow_up`, `routers/sessions.py` L170–L172). The frontend works around this in `loadSessionMessages` by synthesising a user message from `session.alert_text`.
- **Impact**: The event_log is structurally incomplete — the first user input is not an event. Any system that processes event_logs (analytics, replay, debugging) must special-case the first turn.
- **Evidence**: Compare `start()` (no `user_message` push) with `send_follow_up` in `routers/sessions.py` L169–L173 (pushes `user_message`). Frontend workaround at `useSession.ts` L289–L294.
- **Suggested Fix**: Push a `user_message` event at the start of `start()`, before launching the orchestrator.

#### H-MODEL-02 — `run_orchestrator` (legacy) is still mounted and reachable

- **Severity**: low
- **Location**: `api/app/routers/alert.py` L1–L99, `api/app/main.py` L40
- **Description**: `POST /api/alert` is still registered. It uses `run_orchestrator()` (the non-session path) which creates a one-shot SSE stream with no session, no persistence, no multi-turn capability.
- **Impact**: If any client calls `/api/alert`, the investigation runs without session tracking. The result is not persisted and doesn't appear in the sidebar. The frontend no longer uses this endpoint, but it remains accessible.
- **Suggested Fix**: Remove `alert.router` from `main.py` or deprecate with a redirect to the session-based flow.

#### H-MODEL-03 — No message-level streaming for final diagnosis

- **Severity**: medium
- **Location**: `api/app/orchestrator.py` L567 (`on_message_delta`), L696 (`_put("message", ...)`)
- **Description**: `on_message_delta` accumulates text into `handler.response_text` but never emits intermediate events. The `message` event is only emitted after `stream.until_done()` completes. The frontend receives the entire diagnosis atomically.
- **Impact**: For long diagnoses, the user waits with no indication of progress, then sees a large block of text appear instantly. Already noted as task_01 §10.3.
- **Suggested Fix**: Emit `message_delta` events during `on_message_delta` and have the frontend append text tokens incrementally.

#### H-MODEL-04 — No `status_change` handler in frontend

- **Severity**: medium
- **Location**: `frontend/src/hooks/useSession.ts` L22–L79 (`updateOrchestratorMessage` switch)
- **Description**: The server pushes `status_change` events (e.g., when cancel is requested, `routers/sessions.py` L136–L140`), but the frontend's `updateOrchestratorMessage` switch has no case for `status_change`. The event is silently ignored.
- **Impact**: The user gets no visual feedback when cancellation is acknowledged. Already noted as task_01 §10.1.
- **Suggested Fix**: Add a `case 'status_change'` that updates a `statusMessage` field on the orchestrator message, rendered as an info banner in ChatPanel.

#### H-MODEL-05 — `run_start` event not handled in `updateOrchestratorMessage`

- **Severity**: low
- **Location**: `frontend/src/hooks/useSession.ts` L22–L79
- **Description**: `run_start` events fall through the switch with no matching case. The event is ignored during live streaming (it's only used during `loadSessionMessages` for replay).
- **Impact**: None during live sessions. But if the handler were to need run-level metadata (e.g., run_id), it has no way to capture it.
- **Suggested Fix**: Add a no-op case for documentation, or capture `run_id` on the message.

---

## Summary by Severity

| Severity | Count | IDs |
|----------|-------|-----|
| **Critical** | 1 | H-FRAG-01 |
| **High** | 8 | H-BUG-01, H-INEFF-01, H-INEFF-02, H-SSE-01, H-ERR-01, H-ERR-02, H-ERR-03, H-DATA-01, H-DATA-02, H-FRAG-02 |
| **Medium** | 12 | H-BUG-02, H-BUG-03, H-BUG-05, H-FRAG-03, H-FRAG-04, H-FRAG-05, H-SSE-02, H-SSE-03, H-ERR-04, H-ERR-05, H-ERR-06, H-STATE-01, H-STATE-04, H-DATA-03, H-MODEL-01, H-MODEL-03, H-MODEL-04 |
| **Low** | 8 | H-BUG-04, H-INEFF-03, H-INEFF-04, H-SSE-04, H-STATE-02, H-STATE-03, H-DATA-04, H-DATA-05, H-MODEL-02, H-MODEL-05 |

**Total**: 29 issues across 8 categories.

### Top 5 Priorities for Immediate Action

1. **H-FRAG-01** (critical): In-memory session loss on restart — add startup recovery from Cosmos.
2. **H-INEFF-01 + H-INEFF-02** (high): 800+ lines of duplicated orchestrator code — extract shared handler and thread target.
3. **H-ERR-01/02/03** (high): Missing `.ok` checks on all frontend fetch calls — add guards across `useSession.ts`.
4. **H-DATA-01** (high): Shared container with no type discriminator — add `_docType` field.
5. **H-DATA-02** (high): Unbounded event_log growth — add size cap or split storage.
