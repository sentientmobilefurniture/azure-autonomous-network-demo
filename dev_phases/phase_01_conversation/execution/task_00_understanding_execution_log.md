# Task 00: Understanding Current Conversation Handling — Execution Log

> Strategy: [task_00_understanding.md](../strategy/task_00_understanding.md)

**Status**: complete  
**Date**: 2025-02-20

---

## 1. Conversation Data Model

The system uses **two distinct model layers** — one in the API service (Python dataclasses) and one in the frontend (TypeScript interfaces).

### 1.1 Backend: `Session` dataclass

**File**: `api/app/sessions.py` L29–L68

```python
@dataclass
class Session:
    id: str                              # UUID
    scenario: str                        # scenario name (partition key in Cosmos)
    alert_text: str                      # original user alert / prompt
    status: SessionStatus                # enum: pending | in_progress | completed | failed | cancelled
    created_at: str                      # ISO 8601
    updated_at: str                      # ISO 8601
    event_log: list[dict]                # accumulated SSE events (survives disconnects)
    steps: list[dict]                    # extracted step data (populated from step_complete events)
    diagnosis: str                       # final LLM response text
    run_meta: dict | None                # {steps, tokens, time}
    error_detail: str                    # error text if failed
    thread_id: str | None                # Foundry thread ID (persists across turns)
    turn_count: int                      # each user→orchestrator exchange = 1 turn
```

**Runtime-only fields** (not persisted):
- `_subscribers: list[asyncio.Queue]` — live SSE subscriber queues
- `_cancel_event: threading.Event` — cancellation signal
- `_idle_task: asyncio.Task | None` — idle timeout watcher
- `_lock: threading.Lock` — thread-safety for subscribers/event_log
- `_loop: asyncio.AbstractEventLoop | None` — for thread-safe queue delivery

**`SessionStatus` enum** (`api/app/sessions.py` L19–L25):
`PENDING` → `IN_PROGRESS` → `COMPLETED` / `FAILED` / `CANCELLED`

### 1.2 Backend: `InteractionSaveRequest` (legacy)

**File**: `graph-query-api/models.py` L85–L103

Separate from sessions — used by `POST /query/interactions` to save completed investigations. Fields: `scenario`, `query`, `steps: list[InteractionStep]`, `diagnosis`, `run_meta`.

`InteractionStep` (`L83`): `step`, `agent`, `duration`, `query`, `response`, `error`, `visualization`, `reasoning`.

### 1.3 Frontend: TypeScript types

**File**: `frontend/src/types/index.ts`

| Type | Lines | Purpose |
|------|-------|---------|
| `ChatMessage` | L191–L207 | Union of user and orchestrator messages |
| `ChatRole` | L189 | `'user' \| 'orchestrator'` |
| `StepEvent` | L82–L97 | Individual agent step (query, response, viz, action) |
| `ThinkingState` | L99–L102 | Live thinking indicator state |
| `RunMeta` | L104–L107 | Run completion metadata |
| `SessionSummary` | L209–L218 | Sidebar list item |
| `SessionDetail` | L220–L234 | Full session payload from API |
| `VisualizationData` | L52–L54 | Union: graph \| table \| documents |
| `ActionData` | L60–L78 | Dispatch action payload |

Key design: `ChatMessage` is a **union type** — user messages carry `text`, orchestrator messages carry `steps[]`, `diagnosis`, `runMeta`, `status`, `errorMessage`.

---

## 2. API Surface

### 2.1 API service (port 8000)

**Router file**: `api/app/routers/sessions.py`

| Method | Route | Handler | Purpose |
|--------|-------|---------|---------|
| POST | `/api/sessions` | `create_session` | Create session + launch orchestrator |
| GET | `/api/sessions` | `list_sessions` | List all (in-memory + Cosmos backfill) |
| GET | `/api/sessions/{id}` | `get_session` | Full session state (memory → Cosmos fallback) |
| GET | `/api/sessions/{id}/stream` | `stream_session` | SSE: replay + live tail (supports `since` param) |
| POST | `/api/sessions/{id}/cancel` | `cancel_session` | Request cancellation of running session |
| POST | `/api/sessions/{id}/message` | `send_follow_up` | Multi-turn follow-up (reuses Foundry thread) |
| DELETE | `/api/sessions/{id}` | `delete_session` | Remove from memory + Cosmos |

**Router file**: `api/app/routers/alert.py`

| Method | Route | Handler | Purpose |
|--------|-------|---------|---------|
| POST | `/api/alert` | `submit_alert` | Legacy: one-shot SSE stream (no session persistence) |

**Other conversation-adjacent routes**:

| Method | Route | File | Purpose |
|--------|-------|------|---------|
| GET | `/api/logs` | `routers/logs.py` | SSE stream of backend log lines |
| GET | `/api/agents` | `routers/agents.py` | List provisioned Foundry agents |
| POST | `/api/agents/rediscover` | `routers/agents.py` | Force re-discovery from Foundry |
| GET | `/api/config/scenario` | `routers/config.py` | Scenario configuration (graph styles, examples, etc.) |

### 2.2 Graph Query API (port 8100)

**Router file**: `graph-query-api/router_sessions.py`

| Method | Route | Handler | Purpose |
|--------|-------|---------|---------|
| GET | `/query/sessions` | `list_sessions` | List sessions from Cosmos (optionally by scenario) |
| GET | `/query/sessions/{id}` | `get_session` | Get a session by ID (cross-partition) |
| PUT | `/query/sessions` | `upsert_session` | Upsert raw session dict into Cosmos |
| DELETE | `/query/sessions/{id}` | `delete_session` | Delete session from Cosmos |

**Router file**: `graph-query-api/router_interactions.py`

| Method | Route | Handler | Purpose |
|--------|-------|---------|---------|
| GET | `/query/interactions` | `list_interactions` | List past interactions (legacy) |
| POST | `/query/interactions` | `save_interaction` | Save completed interaction (legacy) |
| GET | `/query/interactions/{id}` | `get_interaction` | Get specific interaction |
| DELETE | `/query/interactions/{id}` | `delete_interaction` | Delete interaction |

---

## 3. Storage Layer

### 3.1 Cosmos DB NoSQL

**Database**: `interactions`  
**Container**: `interactions`  
**Partition key**: `/scenario`

Both sessions and interactions are stored in the **same container**. There is no type discriminator field — sessions have `thread_id`, `turn_count`, `event_log` fields that interactions lack. Schema-free storage.

**Access path**:
1. `api/app/session_manager.py` → `httpx` calls to graph-query-api at `http://localhost:8100`
2. `graph-query-api/router_sessions.py` → `stores.get_document_store("interactions", "interactions", "/scenario")`
3. `graph-query-api/stores/__init__.py` → factory returns `CosmosDocumentStore`
4. `graph-query-api/stores/cosmos_nosql.py` → wraps `cosmos_helpers.get_or_create_container()` + async via `asyncio.to_thread()`
5. `graph-query-api/cosmos_helpers.py` → singleton `CosmosClient`, ARM-based container creation

**Container creation**: `ensure_created=True` triggers ARM (`CosmosDBManagementClient`) to idempotently create the container if missing (`cosmos_helpers.py` L90–L135).

**Indexing**: Default Cosmos indexing (no custom index policy observed in code).

**TTL**: None configured in code. Sessions accumulate indefinitely.

### 3.2 In-Memory Storage

**File**: `api/app/session_manager.py` L46–L49

```python
self._active: dict[str, Session] = {}       # currently running sessions
self._recent: OrderedDict[str, Session] = OrderedDict()  # completed, evicted on overflow
```

- `MAX_ACTIVE_SESSIONS = 8` (env-configurable)
- `MAX_RECENT_SESSIONS = 100` (hardcoded)
- Recent cache is FIFO — oldest evicted first

### 3.3 Persistence Timing

- Persisted to Cosmos on **every turn completion** (`_finalize_turn` → `_persist_to_cosmos`, `session_manager.py` L126)
- Also persisted when moved to `_recent` (`_move_to_recent`, L135)
- Persistence is **fire-and-forget** via `asyncio.create_task`

---

## 4. Session / Thread Management

### 4.1 Session Lifecycle

**File**: `api/app/session_manager.py`

```
CREATE (L51)
  → Session(scenario, alert_text)
  → added to _active dict
  
START (L157)
  → status = IN_PROGRESS
  → asyncio.create_task(_run)
  → _run iterates over run_orchestrator_session() async generator
  → events pushed via session.push_event()
  → structured data extracted: step_complete → steps[], message → diagnosis, etc.
  
FINALIZE (L118)
  → if cancelled: status=CANCELLED, move to _recent
  → if error + no diagnosis: status=FAILED, move to _recent
  → else: status=COMPLETED, persist to Cosmos, start idle timeout
  
IDLE TIMEOUT (L141, 600s = 10 min)
  → if still COMPLETED after 10 min, move to _recent
  → cancelled if follow-up arrives
  
FOLLOW-UP (L213)
  → cancel idle timeout
  → reset cancel_event, reset error_detail
  → status = IN_PROGRESS
  → increment turn_count
  → push user_message event to event_log
  → call run_orchestrator_session with existing_thread_id
  → events tagged with turn number
```

### 4.2 Foundry Thread Management

**File**: `api/app/orchestrator.py` L1285–L1292

- **New session**: `agents_client.threads.create()` → new Foundry thread
- `thread_created` event emitted → `SessionManager` captures `thread_id` on session
- **Follow-up**: `existing_thread_id` parameter reuses the same Foundry thread
- Thread ID stored on `Session.thread_id` and persisted to Cosmos

**Multi-turn flow**:
1. Frontend calls `POST /api/sessions/{id}/message` with follow-up text
2. API validates: session exists, not already IN_PROGRESS, has a `thread_id`
3. Returns `event_offset` = current event_log length
4. Frontend reconnects SSE with `?since=event_offset` to only get new-turn events
5. Orchestrator posts the follow-up text as a user message to the existing Foundry thread
6. New run streams against the same thread — agent has full conversation context

### 4.3 Cancellation

**File**: `api/app/routers/sessions.py` L127–L141

- Sets `session._cancel_event` (a `threading.Event`)
- Pushes `status_change` event for immediate SSE feedback
- Orchestrator thread checks `cancel_event.is_set()` between retry attempts (`orchestrator.py` L1245, L1303)
- **Limitation**: cancellation is cooperative — a long-running agent call cannot be interrupted mid-stream

---

## 5. Agent Interaction Flow

### 5.1 Architecture Overview

```
Frontend → POST /api/sessions → API service (port 8000)
  → SessionManager.create() + start()
  → run_orchestrator_session() (async generator)
    → background thread: SSEEventHandler + Foundry Agent SDK
      → agents_client.runs.stream(thread_id, orchestrator_id, handler)
      → handler callbacks → asyncio.Queue → async generator yields SSE events
    → SSE events → session.push_event() → fan out to subscriber queues
  → EventSourceResponse → frontend
```

### 5.2 Two Orchestrator Paths

**File**: `api/app/orchestrator.py`

1. **`run_orchestrator()`** (L100–L772): Legacy one-shot, used by `POST /api/alert`. Has EVENT_TIMEOUT (120s). No cancel support, no thread reuse.

2. **`run_orchestrator_session()`** (L780–L1432): Session-aware. Cancel support, thread reuse, no EVENT_TIMEOUT (session manager owns lifecycle).

Both contain **fully duplicated** `SSEEventHandler` classes (~400 lines each) with identical logic.

### 5.3 SSE Event Types

All emitted by `SSEEventHandler` callbacks, consumed by frontend `useSession` hook:

| Event | Data | Source |
|-------|------|--------|
| `run_start` | `{run_id, alert, timestamp}` | Thread target start |
| `thread_created` | `{thread_id}` | After thread creation (session path only) |
| `step_thinking` | `{agent, status}` | `on_run_step` fallback |
| `step_started` | `{step, agent, query, reasoning?, timestamp}` | `on_run_step` in_progress with tool calls |
| `step_response` | `{step, agent, duration, query, response, visualizations?, reasoning?, is_action?, action?}` | `on_run_step` completed |
| `step_complete` | Same as step_response | `on_run_step` completed (emitted right after step_response) |
| `message` | `{text}` | Final orchestrator response |
| `run_complete` | `{steps, tokens, time}` | Successful completion |
| `error` | `{message}` | Failure |
| `user_message` | `{text}` | Follow-up (added by session_manager, not orchestrator) |
| `status_change` | `{status, message}` | Cancel request |
| `done` | `{status}` | SSE stream termination signal |
| `action_executed` | `{step, action_name, action_data, timestamp}` | FunctionTool executed |
| `heartbeat` | `{}` | Keep-alive during long waits |

### 5.4 Agent Response Parsing

**File**: `api/app/orchestrator.py` — `_parse_structured_output()` method (L248–L337, duplicated at L955–L1020)

Sub-agents use delimited output format:
```
---QUERY---
<gremlin query or KQL query>
---RESULTS---
<JSON results>
---ANALYSIS---
<natural language analysis>
```

Parser extracts query/results pairs into typed visualization payloads (`graph`, `table`, `documents`). Falls back to `documents` type if parsing fails or agent doesn't follow format.

### 5.5 FunctionTool Support (Actions)

**File**: `api/app/dispatch.py` — `dispatch_field_engineer()` function

- Registered as a `FunctionTool` with `agents_client.enable_auto_function_calls()`
- Auto-executed by the SDK when the orchestrator calls it
- Output cached in `_fn_output_cache` dict, referenced during `on_run_step` completed
- Emits `action_executed` event with parsed action data

### 5.6 Retry Logic

**File**: `api/app/orchestrator.py` L569–L717 (session path: L1300–L1405)

- `MAX_RUN_ATTEMPTS = 2` (initial + 1 retry)
- On failure: posts a `[SYSTEM]` recovery message to the thread instructing retry
- **Skips retry for Fabric capacity errors** (429, 503, circuit breaker) to avoid doubling load
- If final response text is empty: falls back to `agents_client.messages.list()` to scrape the last assistant message

---

## 6. Frontend Integration

### 6.1 Component Hierarchy

```
App.tsx
├── Header
├── TabBar (investigate | resources | scenario | ontology)
├── ResizableGraph → MetricsBar
├── ChatPanel
│   ├── UserMessage (per user turn)
│   ├── OrchestratorThoughts (per step.reasoning)
│   ├── StepCard / ActionCard (per step)
│   ├── ThinkingDots (live indicator)
│   ├── DiagnosisBlock (final response)
│   └── RunMeta footer
├── ChatInput (textarea + examples dropdown + submit/cancel)
├── ResizableTerminal → TerminalPanel
└── ResizableSidebar → SessionSidebar
    └── SessionCard (per session)
```

### 6.2 Key Hooks

**`useSession`** (`frontend/src/hooks/useSession.ts`, 327 lines)

Core state machine for conversation management. Exposes:
- `messages: ChatMessage[]` — the full conversation thread
- `thinking: ThinkingState | null` — live agent activity indicator
- `running: boolean` — is an investigation in progress
- `activeSessionId: string | null` — currently viewed session
- `createSession(scenario, alertText)` — POST → SSE connect
- `sendFollowUp(text)` — POST follow-up → SSE reconnect with `since` offset
- `viewSession(sessionId)` — fetch full session, reconstruct messages from event_log
- `cancelSession()` — POST cancel
- `handleNewSession()` — clear UI, park current session
- `deleteSession(sessionId)` — DELETE session

**Key patterns**:
- **Optimistic UI**: User message added to state immediately before API call (L138–L144)
- **SSE via `@microsoft/fetch-event-source`**: Handles reconnect gracefully, throws on error to prevent auto-retry loop (L126–L131)
- **Event replay**: `loadSessionMessages()` (L253–L297) reconstructs `ChatMessage[]` from a session's `event_log` array — handles single-turn sessions (no `user_message` event) by synthesising one from `alert_text`
- **Turn isolation**: `sendFollowUp` captures `event_offset` and passes as `since` param so SSE stream only replays new-turn events

**`useSessions`** (`frontend/src/hooks/useSessions.ts`, 36 lines)

Simple list fetcher: `GET /api/sessions` on mount, exposes `refetch()`. Auto-refetches when `running` transitions true→false (wired in `App.tsx` L50–L55).

### 6.3 Data Flow: Submit → Render

1. User types in `ChatInput`, presses Ctrl+Enter
2. `App.handleSubmit()` — routes to `createSession()` (new) or `sendFollowUp()` (existing)
3. `createSession`:
   - Adds user `ChatMessage` to `messages` state
   - `POST /api/sessions` → gets `session_id`
   - Adds placeholder orchestrator `ChatMessage` (status=`thinking`, empty steps)
   - Calls `connectToStream(session_id, orchMsgId)`
4. `connectToStream`:
   - Opens SSE to `/api/sessions/{id}/stream`
   - Each SSE event calls `updateOrchestratorMessage(msgId, eventType, data)`
   - `updateOrchestratorMessage` is a pure state updater (L14–L80): maps over messages, finds the target orchestrator message by ID, applies event-specific mutations
5. `ChatPanel` re-renders on each state change:
   - `StepCard`s appear incrementally (step_started → pending, step_complete → filled)
   - `ThinkingDots` shows between steps
   - `DiagnosisBlock` appears on `message` event
   - `RunMeta` footer on `run_complete`

### 6.4 Proxy Configuration

**File**: `frontend/vite.config.ts`

- `/api/*` → `http://localhost:8000` (API service)
- `/query/*` → `http://localhost:8100` (graph-query-api)
- SSE routes (`/api/alert`, `/api/logs`) have explicit proxy config to disable buffering

---

## 7. Gaps & Pain Points

### 7.1 Massive Code Duplication in Orchestrator

`api/app/orchestrator.py` is **1,432 lines** with two nearly identical implementations:
- `run_orchestrator()` (L100–L772): legacy one-shot
- `run_orchestrator_session()` (L780–L1432): session-aware

`SSEEventHandler` is **fully duplicated** (~400 lines each). The second copy has trivial additions (cancel_event checks, thread_created event). Any bug fix or feature must be applied twice.

### 7.2 No Persistent User Messages in Single-Turn Sessions

When a session is first created, the user's alert text is stored on `Session.alert_text` but **not** pushed as a `user_message` event into `event_log`. Only follow-up turns generate `user_message` events (`session_manager.py` L244–L248). The frontend works around this in `loadSessionMessages()` by synthesising a fake user message from `alert_text` (L291–L296).

### 7.3 Sessions and Interactions Share a Container

`router_sessions.py` L31–L32 and `router_interactions.py` L30–L31 both target `database="interactions", container="interactions"`. There is no `type` discriminator field. A query for sessions could return interaction documents and vice versa, though in practice the field differences (sessions have `thread_id`, interactions have `query`) prevent confusion. This is fragile.

### 7.4 No Chat Message Persistence

Individual messages are **not** stored as first-class entities. The conversation is reconstructed from the `event_log` array on the session document. This means:
- No direct message lookup by ID
- No editing or deleting individual messages
- The entire event_log must be replayed to reconstruct the conversation
- Event logs grow unbounded with multi-turn sessions (every SSE event is appended)

### 7.5 Limited Conversation Model

The system does not support true conversational flow:
- **No message threading**: Messages are flat — no parent/child relationships
- **No message roles beyond user/orchestrator**: No system messages visible to the user
- **No message streaming**: The orchestrator response is delivered as a single `message` event at the end. Steps stream incrementally, but the final diagnosis appears atomically.
- **No conversation branching**: Cannot fork a conversation from a prior turn

### 7.6 In-Memory Session Loss

Active and recent sessions are stored **in-memory only** on the API service. If the container restarts:
- All active sessions are lost (orchestrator threads die)
- Recent sessions are lost (only the last-persisted snapshot exists in Cosmos)
- Running sessions cannot be resumed — the Foundry agent run is gone

Mitigation: `_finalize_turn` persists to Cosmos on each turn completion, so completed sessions survive. But in-progress sessions are unrecoverable.

### 7.7 Legacy Alert Endpoint Still Active

`POST /api/alert` (`routers/alert.py`) returns a one-shot SSE stream with no session creation, no persistence, no multi-turn. The frontend no longer uses it (all paths go through `/api/sessions`), but it remains in the codebase and is mounted in `main.py`.

### 7.8 Cooperative Cancellation Only

Cancellation (`Session._cancel_event`) is checked only between retry attempts in the orchestrator thread. A long-running Foundry agent call (which can take 30–60s) **cannot be interrupted**. The user sees "cancelling" but must wait for the current agent call to complete.

### 7.9 No Typing Indicators or Partial Streaming

The final diagnosis (`message` event) arrives as a complete text blob. There is no token-by-token streaming to the frontend. `on_message_delta` accumulates text internally but only emits it after the run completes. This means the user sees nothing until the entire orchestrator response is ready.

### 7.10 Idle Timeout is Single-Instance

The idle timeout (`_schedule_idle_timeout`, 600s) is an `asyncio.Task` — it only works within a single process. In a multi-instance deployment (e.g., multiple container replicas), idle timeouts would not fire on replicas that don't own the session.

---

## Summary

The conversation system is a **session-based, SSE-streamed orchestrator bridge** that:
1. Creates persistent `Session` objects tracked in-memory and Cosmos DB
2. Bridges synchronous Foundry Agent SDK callbacks to async SSE via background threads + `asyncio.Queue`
3. Supports multi-turn via Foundry thread reuse and `event_offset`-based SSE replay
4. Renders incrementally in the frontend via the `useSession` hook's `updateOrchestratorMessage` state machine

The primary architectural debt is the 1,432-line orchestrator with duplicated handler classes, the lack of first-class message persistence, and the fragile in-memory session lifecycle.
