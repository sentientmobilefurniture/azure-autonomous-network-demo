# Task 01: Feasibility Validation — Conversation Revamp

> **Phase**: [README.md](../README.md) — Azure Autonomous Network Demo: Conversation Revamp  
> **Task**: [strategy/task_01_validation.md](../strategy/task_01_validation.md)

---

## 1. Architecture Summary

### Process Model
Three processes run in a single container via `supervisord.conf`:
- **nginx** (port 80) — reverse proxy
- **api** (port 8000) — FastAPI app (`api/app/main.py`)
- **graph-query-api** (port 8100) — FastAPI app (`graph-query-api/main.py`)

### Orchestrator Flow
1. `api/app/routers/sessions.py` `create_session()` creates a `Session` object and calls `session_manager.start()`.
2. `session_manager.start()` launches `run_orchestrator_session()` as an `asyncio.create_task()`.
3. `run_orchestrator_session()` (`orchestrator.py:800–1432`) spawns a `threading.Thread` that runs the synchronous Azure AI Agents SDK.
4. Inside the thread, `SSEEventHandler(AgentEventHandler)` receives callbacks: `on_thread_run`, `on_run_step`, `on_message_delta`, `on_error`.
5. Events are pushed to an `asyncio.Queue` via `call_soon_threadsafe`, yielded as an async generator, and consumed by `session.push_event()`.
6. `push_event()` fans out to all SSE subscribers via `_subscribers` list (queues registered by `session.subscribe()`).

### Agent Architecture
- **Orchestrator agent** — uses `ConnectedAgentTool` to delegate to 4 sub-agents + `FunctionTool` for `dispatch_field_engineer`.
- **Sub-agents** (GraphExplorerAgent, TelemetryAgent, RunbookKBAgent, HistoricalTicketAgent) — each provisioned with their own tools (`OpenApiTool`, `AzureAISearchTool`).
- Sub-agents run **server-side on Azure AI Foundry**. The orchestrator invokes them via `ConnectedAgentTool`, which is opaque — the SDK returns only the final output, not intermediate steps.

### Session Model
- `Session` dataclass (`sessions.py`): `id`, `scenario`, `alert_text`, `status`, `event_log`, `steps`, `diagnosis`, `thread_id`, `turn_count`.
- `MAX_EVENT_LOG_SIZE = 500` — event log is capped; oldest events dropped when exceeded.
- `SessionManager` (`session_manager.py`): `_active` (in-memory dict), `_recent` (OrderedDict LRU cache of 100).
- `_finalize_turn()`: on success → `COMPLETED` + persist to Cosmos + start 10-min idle timeout. On error/cancel → `FAILED`/`CANCELLED` + move to `_recent` + persist.
- `_persist_to_cosmos()`: PUT to `graph-query-api/query/sessions` (3 retries, exponential backoff).

### SSE Lifecycle
- `stream_session()` (`routers/sessions.py:88–132`): subscribes via `session.subscribe(since_index)`, replays history, tails live queue, emits `done` event on completion.
- Frontend `useSession.ts`: `connectToStream()` uses `@microsoft/fetch-event-source`, `updateOrchestratorMessage()` switch dispatches by event type to build `ChatMessage` state.

### Cosmos Persistence
- `graph-query-api/router_sessions.py`: CRUD endpoints for sessions in Cosmos NoSQL (`interactions` database, `interactions` container, pk=`/scenario`).
- `stores/cosmos_nosql.py`: `CosmosDocumentStore` wraps sync Cosmos SDK with `asyncio.to_thread()`.
- Sessions are stored as single documents. No chunking, no compression.

### Frontend Rendering
- `ChatPanel.tsx`: iterates `messages[]`, renders flat sequence of `OrchestratorThoughts`, `StepCard`/`ActionCard`, `DiagnosisBlock`.
- Steps are rendered at top level with optional `reasoning` shown via `OrchestratorThoughts` (collapsible).
- No nested hierarchy — all steps are at the same indentation level.
- `loadSessionMessages()` reconstructs `ChatMessage[]` from `event_log` on session replay.

---

## 2. Per-Requirement Validation

### Requirement 1: Hierarchical Streaming — Orchestrator → Sub-agent → API calls

**Current State**:
- The orchestrator emits a flat sequence of events: `step_started` (agent name + query), `step_response` (agent output), `step_complete`.
- `on_run_step()` in `SSEEventHandler` fires when the orchestrator's own run step starts/completes. It resolves the agent name and query from the tool call object (`orchestrator.py:340–380`).
- Steps are numbered sequentially (`ui_step` counter) and rendered flat in `ChatPanel.tsx:55–88`.
- `OrchestratorThoughts` renders reasoning extracted from `[ORCHESTRATOR_THINKING]` tags, shown as a collapsible bubble *above* the step card — but no true parent-child nesting.

**Gap Analysis**:
1. **No hierarchical data model**: `StepEvent` is flat — it has `step`, `agent`, `query`, `response`. There is no `parent_step` or `children` field. The event stream has no concept of nesting.
2. **No sub-agent internal visibility**: `ConnectedAgentTool` output arrives as a single blob in `ca.output` (`orchestrator.py:507–516`). The orchestrator's `AgentEventHandler` does **not** receive `on_run_step` callbacks for the sub-agent's internal tool calls.
3. **Frontend renders flat**: `ChatPanel.tsx` maps steps flat with `steps.map()`. No tree structure, no indentation based on depth.

**SDK / External Constraints**:
- **Critical**: The Azure AI Agents SDK (`azure-ai-agents==1.2.0b6`) treats `ConnectedAgentTool` as opaque. `on_run_step` fires only for orchestrator-level steps. Sub-agent internal steps (e.g., GraphExplorerAgent calling its OpenApiTool) are NOT surfaced via the streaming API. The orchestrator receives only the final `connected_agent.output` text.
- This is a **service-level limitation**, not a client SDK limitation. The Foundry service does not stream sub-agent run steps to the parent agent's event handler.

**Feasibility Verdict**: ⚠️ **Achievable with significant changes** — but only for the orchestrator → sub-agent level. True 3-level hierarchy (orchestrator → sub-agent → API call) requires **manual sub-agent orchestration** (bypassing `ConnectedAgentTool`).

**Proposed Implementation Path**:
Two options:

**Option A — Manual Sub-Agent Orchestration (recommended for full 3-level hierarchy)**:
1. Remove `ConnectedAgentTool` from the orchestrator.
2. Replace with `FunctionTool` wrappers that, when called, manually create a run on the sub-agent with its own `AgentEventHandler`, collect intermediate events, and merge them into the orchestrator's event stream.
3. Each sub-agent's `on_run_step` events would be tagged with `parent_step` and forwarded to the SSE queue with depth annotations.
4. Requires refactoring `agent_provisioner.py` (no more ConnectedAgentTool), `orchestrator.py` (FunctionTool implementations that run sub-agents), and adding parent-child fields to `StepEvent`.
5. **Risk**: `FunctionTool` runs client-side (in the API container), so sub-agent runs would execute from the API container rather than server-side. This changes the execution model and may increase latency.
6. **Risk**: Auto-function-calls with `ToolSet` may not support multiple concurrent sub-agent runs well.

**Option B — Fake Hierarchy from Parsed Output (simpler, partial)**:
1. Keep `ConnectedAgentTool` as-is.
2. Parse the sub-agent's structured output (delimited `---QUERY---`/`---RESULTS---`/`---ANALYSIS---` blocks) into synthetic child events.
3. Emit these as nested under the parent step in the event stream.
4. Frontend renders them indented.
5. **Limitation**: Only reconstructed after the sub-agent completes — no real-time streaming of sub-agent internals. The "live" feel would be simulated (show parsed queries/results as sub-steps when the full output arrives).

**Effort Estimate**: **XL** (Option A) / **L** (Option B)
- Option A: Major refactor of orchestrator, provisioner, event schema, and frontend rendering. ~5–8 days.
- Option B: Backend parsing + frontend nesting. ~2–3 days.

**Risks**:
- Option A changes the execution model (client-side sub-agent runs), potentially introducing latency and reliability regressions.
- Option B provides a degraded UX (no true live streaming of sub-agent internals).

---

### Requirement 2: Sub-agent Internal Call Visibility

**Current State**:
- Sub-agent output is received as a single string in `connected_agent.output` (`orchestrator.py:507–516`).
- `_parse_structured_output()` (`orchestrator.py:260–330`) extracts `---QUERY---`, `---RESULTS---`, `---ANALYSIS---` blocks and creates visualization payloads.
- These are embedded in the `step_complete` event as `visualizations[]` but as flat data within a single step — not as separate sub-steps.
- `StepCard.tsx` shows the query and response text, plus a "View" button for visualizations modal. No breakdown of individual API calls.

**Gap Analysis**:
- The structured output format already contains individual query/result pairs (multi-query support in `query_blocks` extraction, `orchestrator.py:264–270`).
- However, these are merged into a single `step_complete` event with a `visualizations[]` array, not rendered as separate sub-steps.
- To achieve indented sub-steps, we need: (a) parse individual queries into child events, (b) add depth/parent metadata to the event schema, (c) render indented in the frontend.

**SDK / External Constraints**: Same as Requirement 1 — `ConnectedAgentTool` is opaque.

**Feasibility Verdict**: ⚠️ **Achievable with significant changes**

**Proposed Implementation Path**:
1. **Backend**: In `on_run_step` (status=completed, type=tool_calls), for `connected_agent` type, parse `ca.output` via `_parse_structured_output()` and emit individual `sub_step_complete` events for each query/result pair, tagged with `parent_step`.
2. **Event schema**: Add `parent_step?: number` and `depth?: number` to `StepEvent`.
3. **Frontend**: Modify `ChatPanel.tsx` to group steps by parent and render children indented under the parent `StepCard`.
4. This approach works even with `ConnectedAgentTool` (Option B from Req 1) — the sub-steps are synthetic but informative.
5. **Limitation**: Sub-steps only appear when the parent step completes, not in real-time during sub-agent execution.

**Effort Estimate**: **M** (2–3 days) — doable independently of the full manual orchestration refactor.

**Risks**: Parsing is best-effort; if a sub-agent doesn't follow the delimited format, no sub-steps are generated.

---

### Requirement 3: Async Session Management

**Current State**:
- `SessionManager` already supports multiple concurrent sessions: `_active` dict tracks up to `MAX_ACTIVE_SESSIONS=8` (`session_manager.py:90–94`).
- `create_session()` returns a new `Session` immediately; `start()` launches orchestrator in an `asyncio.create_task()`.
- `list_all_with_history()` returns active + recent + Cosmos DB sessions.
- Frontend `handleNewSession()` (`useSession.ts:250–256`) clears current UI state (`setMessages([])`, `setActiveSessionId(null)`) and starts fresh.
- The prior session persists server-side (active or recently completed).

**Gap Analysis**:
- **Session switching works**: `viewSession()` loads a past session from Cosmos, `loadSessionMessages()` reconstructs chat messages from `event_log`.
- **New scenario doesn't block**: `create_session` is non-blocking (the orchestrator runs in a background task).
- **Minor issue**: When `handleNewSession()` is called, it aborts the SSE connection (`abortRef.current?.abort()`) but does NOT cancel the server-side session. The prior session continues running and persists. This is correct behavior — the requirement says "prior session appears in sidebar," which it does.
- The UI has a sessions sidebar (`SessionSidebar.tsx`) that lists sessions and allows clicking to view them.

**SDK / External Constraints**: None.

**Feasibility Verdict**: ✅ **Achievable** — already mostly implemented.

**Proposed Implementation Path**:
- **Already met**. No significant changes needed.
- Minor enhancement: after `handleNewSession()`, the sidebar should immediately reflect the prior session as active/completed (it does — the session stays in `_active` or moves to `_recent` on finalization).

**Effort Estimate**: **S** (< 1 day) — minor UX polish only.

**Risks**: None.

---

### Requirement 4: Manual Save with Chunked Cosmos Persistence

**Current State**:
- Sessions auto-persist to Cosmos on `_finalize_turn()` (`session_manager.py:166`): `asyncio.create_task(self._persist_to_cosmos(session))`.
- Persist is a single PUT of the whole `session.to_dict()` to `/query/sessions`.
- `MAX_EVENT_LOG_SIZE = 500` caps the event log to prevent exceeding Cosmos's 2MB document size limit (`sessions.py:79`).
- There is no manual save button. Persistence is automatic on turn completion.
- There is no chunking — the entire session (including `event_log`) is a single Cosmos document.

**Gap Analysis**:
1. **Auto-persist vs. manual save**: Currently auto-persists. Requirement wants explicit user-triggered save.
2. **No chunking**: Sessions are single documents. For sessions with 500 events (the cap), the JSON payload can be large but typically under 2MB. However, if `MAX_EVENT_LOG_SIZE` is increased or events carry large visualization payloads, the 2MB limit becomes a concern.
3. **No chunk-based retrieval**: `get_session()` loads a single document. No reconstruction from chunks.

**SDK / External Constraints**:
- Cosmos DB NoSQL max document size: **2 MB**.
- Typical session with 15–20 steps: ~50–100 events × ~2–5KB each = ~100–500KB. Well under 2MB.
- With `MAX_EVENT_LOG_SIZE = 500` and truncation, even large sessions stay under 2MB.

**Feasibility Verdict**: ⚠️ **Achievable with significant changes**

**Proposed Implementation Path**:
1. **Manual save**:
   - Remove auto-persist from `_finalize_turn()` (or make it conditional on a flag).
   - Add a `POST /api/sessions/{id}/save` endpoint that triggers `_persist_to_cosmos()`.
   - Frontend: add a "Save" button on the session card / diagnosis block.
   - Sessions remain in-memory until explicitly saved or until the idle timeout fires (keep idle timeout as safety net).

2. **Chunked persistence** (if needed — see trade-off analysis in §5):
   - Split `event_log` into chunks of N events each.
   - Store a manifest document: `{id, scenario, ...metadata, chunks: ["chunk-1", "chunk-2", ...]}`.
   - Store each chunk as a separate document: `{id: "session-id:chunk-0", events: [...]}`.
   - On retrieval, query for manifest + all chunks, merge `event_log` in order.
   - Modify `router_sessions.py` PUT endpoint to handle multi-document writes.
   - Modify GET endpoint to reconstruct from chunks.

3. **Alternative — compression instead of chunking**:
   - gzip the `event_log` and store as base64 in a single document.
   - Simpler than chunking, but harder to query individual events.
   - May not be worthwhile given current session sizes.

**Effort Estimate**: **L** (3–4 days)
- Manual save: S (1 day)
- Chunked persistence: L (2–3 days) — multi-doc writes, transactional consistency, chunk retrieval, frontend changes.

**Risks**:
- Chunked writes are not atomic in Cosmos DB NoSQL (no multi-document transactions across partition keys). A crash mid-write could leave orphaned chunks.
- Chunk retrieval adds latency (multiple queries).
- If chunking is implemented, `loadSessionMessages()` in the frontend needs to handle partial chunk responses (graceful degradation).

---

### Requirement 5: Graceful Degradation

**Current State**:
- `loadSessionMessages()` (`useSession.ts:296–341`) reconstructs messages from `event_log` by iterating events.
- If `event_log` is truncated (due to `MAX_EVENT_LOG_SIZE` cap), earlier events are lost but the reconstruction still works — it just starts from wherever the log begins.
- If a session has no `event_log` (e.g., Cosmos record without it), `loadSessionMessages()` returns an empty array — no crash.
- `StepCard.tsx` handles missing fields: `step.query` and `step.response` are optional, `step.pending` shows loading state.
- `ActionCard.tsx` guards against incomplete data: `if (!action) return null; if (!action.engineer || !action.destination) return null;`.
- `DiagnosisBlock.tsx` renders only if `msg.diagnosis` is truthy.

**Gap Analysis**:
- Current degradation is mostly graceful for existing data structures.
- If chunked persistence is introduced, partial chunks (missing chunks from a crash) would need handling: the frontend should render whatever chunks are available.
- No explicit "partial data" indicator in the UI.

**SDK / External Constraints**: None.

**Feasibility Verdict**: ✅ **Achievable** — largely already met for current architecture. Will need minor additions if chunked persistence is implemented.

**Proposed Implementation Path**:
1. Add a `partial` flag to `SessionDetail` when chunks are missing.
2. Frontend: show a subtle banner "Some data may be missing" when `partial` is true.
3. Wrap `loadSessionMessages()` in a try-catch — if JSON parsing fails for individual events, skip them and continue.
4. Test edge cases: empty event_log, event_log with malformed entries, missing `steps`/`diagnosis`/`run_meta`.

**Effort Estimate**: **S** (< 1 day)

**Risks**: Minimal — defensive coding.

---

### Requirement 6: Real-time Streaming of All Steps

**Current State**:
- **Already implemented**. The orchestrator streams events in real time via the AgentEventHandler → asyncio.Queue → SSE pipeline.
- `step_started` event fires when `on_run_step(status=in_progress)` detects a tool call, before the sub-agent returns. This gives the UI a pending step immediately.
- `step_response` + `step_complete` fire when `on_run_step(status=completed)` processes the result.
- `step_thinking` fires as a fallback when tool call details aren't available yet.
- Frontend `connectToStream()` processes events immediately as they arrive and updates React state via `updateOrchestratorMessage()`.
- `ThinkingDots` component renders between steps for visual continuity.
- `StepCard` shows `pending: true` with a "Querying…" animation while waiting for response.

**Gap Analysis**:
- **Already working well for orchestrator-level steps**. Each sub-agent call appears in real-time.
- **Gap**: Sub-agent internal steps (API calls within a sub-agent) are NOT streamed — they arrive as a batch when the sub-agent completes (same as Req 1/2).
- **Minor gap**: `on_message_delta` captures final response text character-by-character, but the diagnosis only appears after `stream.until_done()` completes. The `message` event is emitted in one shot, not streamed token-by-token. For truly live diagnosis text, we'd need to emit incremental `message_delta` events.

**SDK / External Constraints**: `on_message_delta` is called by the SDK with text deltas, but the current code accumulates `self.response_text` without emitting incremental events. This is a code choice, not an SDK limitation.

**Feasibility Verdict**: ✅ **Achievable** — mostly done. Token-by-token diagnosis streaming is a minor enhancement.

**Proposed Implementation Path**:
1. **Sub-agent internal streaming**: Requires Option A from Req 1 (manual sub-agent orchestration). If using Option B, sub-agent steps appear in a batch when complete.
2. **Token-by-token diagnosis streaming**:
   - Modify `on_message_delta()` to emit `message_delta` events: `_put("message_delta", {"text": delta.text.value})`.
   - Frontend: accumulate `message_delta` events into a growing `diagnosis` string, rendering progressively.
   - Add `ChatMessage.partialDiagnosis` field for in-progress diagnosis text.
3. **Already working**: orchestrator-level step streaming.

**Effort Estimate**: **S** (1 day) for diagnosis streaming. **XL** if sub-agent internal streaming is required (same as Req 1 Option A).

**Risks**: Token-by-token rendering may cause excessive React re-renders. Use `requestAnimationFrame` batching or debouncing.

---

## 3. Critical Path & Dependency Graph

### Requirements Already Met (no work needed)
- **Req 3**: Async session management — already works.
- **Req 5**: Graceful degradation — already handles partial data.
- **Req 6**: Real-time streaming of orchestrator-level steps — already works.

### Independently Implementable
- **Req 4** (manual save + chunked persistence) — independent of all others.
- **Req 6 enhancement** (token-by-token diagnosis streaming) — independent.
- **Req 2** (sub-agent internal call visibility via parsed output) — can be done with Option B independently.

### Dependencies
```
Req 1 (hierarchical streaming)
  ├── Option A (manual sub-agent orchestration) ← blocks full Req 2, full Req 6
  └── Option B (parsed output hierarchy) ← enables partial Req 2, no help for Req 6
  
Req 2 (sub-agent internal visibility) 
  └── depends on Req 1 approach choice

Req 4 (chunked persistence)
  └── Req 5 (graceful degradation) should be enhanced AFTER Req 4
```

### Highest-Risk / Highest-Effort Item
**Req 1 Option A (manual sub-agent orchestration)** is both the highest-risk and highest-effort item:
- **Risk**: Changes the fundamental execution model. Sub-agents would run client-side from the API container instead of server-side on Foundry. This introduces latency, credential management complexity, and potential reliability issues.
- **Effort**: XL — touches `agent_provisioner.py`, `orchestrator.py` (massive refactor of the handler + thread target), event schema, `sessions.py`, `session_manager.py`, frontend types, `ChatPanel.tsx`, `StepCard.tsx`.

### Recommended Implementation Order

1. **Task 2: Token-by-token diagnosis streaming** (S) — quick win, improves perceived responsiveness.
2. **Task 3: Sub-agent internal call visibility via parsed output** (M) — Option B approach. Parse sub-agent structured output into child events; add `parent_step`/`depth` to event schema; render indented in frontend.
3. **Task 4: Hierarchical event schema + frontend tree rendering** (M) — build the tree rendering infrastructure in `ChatPanel.tsx` that Task 3 populated.
4. **Task 5: Manual save endpoint + UI** (S) — add save button, `POST /api/sessions/{id}/save` endpoint.
5. **Task 6: Chunked Cosmos persistence** (L) — split event_log into chunks, manifest document, chunk retrieval.
6. **Task 7: Graceful degradation for chunked sessions** (S) — handle missing chunks in frontend.
7. **Task 8: (Optional) Manual sub-agent orchestration** (XL) — only if true real-time sub-agent streaming is a hard requirement. This is the highest-risk task and should be deferred unless Option B is insufficient.

---

## 4. SDK Feasibility Deep-Dive

### Central Question: Can the Azure AI Agents SDK stream events from sub-agent runs executed via ConnectedAgentTool?

**Answer: No.**

**Evidence**:

1. **`on_run_step` scope**: The `AgentEventHandler.on_run_step()` callback fires for steps in the *current agent's* run only. When the orchestrator calls a sub-agent via `ConnectedAgentTool`, a new run is created server-side on Foundry, but events from that run are NOT forwarded to the orchestrator's event handler.

2. **`ConnectedAgentTool` output**: When the sub-agent completes, the result appears in `tc.connected_agent.output` as a string (`orchestrator.py:507–516`). No intermediate events, no tool call details, no reasoning steps — just the final output.

3. **SDK reference** (`microsoft_skills/.github/skills/azure-ai-projects-py/references/tools.md`): `ConnectedAgentTool` has three parameters: `agent_id`, `name`, `description`. No `stream_events` or similar option. The reference describes it as simple delegation with no granularity control.

4. **SDK version**: `azure-ai-agents==1.2.0b6` (pinned in `api/pyproject.toml:14`). This is a beta release. Future stable releases may add sub-agent event forwarding, but it does not exist today.

5. **Project documentation** (`VzyQ.md:94`): "Do NOT try to use `FunctionTool` inside `ConnectedAgentTool` sub-agents — they run server-side and cannot execute local callbacks." This confirms sub-agents are opaque server-side processes.

### Manual Sub-Agent Orchestration Alternative

If `ConnectedAgentTool` is abandoned, the orchestrator can be restructured to run sub-agents manually:

```python
# Pseudocode — replace ConnectedAgentTool with FunctionTool
def call_sub_agent(agent_id: str, query: str) -> str:
    """Manually run a sub-agent with its own streaming handler."""
    handler = SubAgentEventHandler(parent_step=current_step)
    with agents_client.runs.stream(
        thread_id=sub_thread.id,
        agent_id=agent_id,
        event_handler=handler,
    ) as stream:
        stream.until_done()
    return handler.response_text
```

**Complexity assessment**:
- **Thread model**: The orchestrator already runs in a background thread. Sub-agent runs would be nested synchronous calls within that thread. This works but serializes sub-agent execution (no parallelism).
- **FunctionTool registration**: The orchestrator would use `FunctionTool` with callables that internally run sub-agents. `enable_auto_function_calls` would handle the tool call loop.
- **Event merging**: Sub-agent events need to be pushed to the same queue with depth/parent annotations. The `_put()` closure captures the queue, so this is straightforward.
- **Provisioning change**: The orchestrator agent would no longer have `ConnectedAgentTool` definitions. Instead, it would have `FunctionToolDefinition` entries describing each sub-agent's capability. The sub-agents still exist as separate agents in Foundry.
- **Thread management**: Each sub-agent call needs its own Foundry thread (or reuse one). Thread creation adds ~500ms latency per call.

**Trade-offs**:
| Aspect | ConnectedAgentTool (current) | Manual Sub-Agent Orchestration |
|--------|------------------------------|-------------------------------|
| Sub-agent event visibility | None (opaque) | Full (own handler per sub-agent) |
| Execution location | Server-side (Foundry) | Client-side (API container) |
| Latency | Lower (server-side transfer) | Higher (network hops) |
| Parallelism | Foundry may parallelize | Sequential (single thread) |
| Reliability | Foundry-managed retries | Must implement own retry logic |
| Code complexity | Simple (tool definition only) | High (FunctionTool + handler + thread mgmt) |

**Recommendation**: Start with Option B (parsed output hierarchy) which provides 80% of the UX value at 20% of the effort. Defer manual sub-agent orchestration to a later phase if stakeholders require true real-time sub-agent streaming.

---

## 5. Chunked Persistence Design Notes

### Current Session Sizes

Typical session characteristics (based on codebase analysis):
- 8–20 steps per investigation, each step generating 3 events (step_started, step_response, step_complete).
- Plus: user_message, run_start, thread_created, step_thinking (×N), message, run_complete.
- Estimated events per single-turn session: 30–70.
- Multi-turn sessions (2–3 turns): 60–210 events.
- `MAX_EVENT_LOG_SIZE = 500` is the hard cap.
- Estimated JSON size per event: 1–5 KB (larger for events with visualization data).
- **Estimated max session document size**: 500 events × 5 KB = 2.5 MB.

This exceeds Cosmos DB's 2 MB limit for worst-case sessions. The current `MAX_EVENT_LOG_SIZE = 500` with tail truncation is a mitigation but not a solution — it drops early events.

### Chunking Design

**Approach: Manifest + Chunk Documents**

```
Manifest document (pk = scenario):
{
  "id": "session-{uuid}",
  "_docType": "session",
  "scenario": "...",
  "status": "completed",
  "created_at": "...",
  "updated_at": "...",
  "diagnosis": "...",
  "run_meta": {...},
  "thread_id": "...",
  "turn_count": 2,
  "chunk_count": 3,
  "chunk_ids": ["session-{uuid}:chunk-0", "session-{uuid}:chunk-1", "session-{uuid}:chunk-2"],
  // event_log and steps REMOVED from manifest
}

Chunk documents (pk = scenario):
{
  "id": "session-{uuid}:chunk-0",
  "_docType": "session_chunk",
  "session_id": "session-{uuid}",
  "scenario": "...",
  "chunk_index": 0,
  "events": [ ...first 100 events... ]
}
```

**Chunk size**: 100 events per chunk → ~100–500 KB per chunk document. Well under 2 MB.

**Write path** (PUT /query/sessions):
1. Receive full session dict.
2. Split `event_log` into chunks of 100.
3. For each chunk, upsert chunk document.
4. Upsert manifest document (without event_log).

**Read path** (GET /query/sessions/{id}):
1. Load manifest document.
2. Query for all chunk documents: `SELECT * FROM c WHERE c.session_id = @id AND c._docType = 'session_chunk' ORDER BY c.chunk_index`.
3. Merge events from chunks into `event_log`.
4. Return reconstructed session.

**Delete path** (DELETE /query/sessions/{id}):
1. Delete all chunk documents.
2. Delete manifest document.

### Impact Analysis

| Component | Change Required |
|-----------|----------------|
| `graph-query-api/router_sessions.py` | PUT: split into chunks + manifest. GET: reconstruct. DELETE: multi-doc delete. |
| `graph-query-api/stores/cosmos_nosql.py` | No change — existing `upsert`/`list`/`delete` methods suffice. |
| `api/app/sessions.py` | Remove `MAX_EVENT_LOG_SIZE` cap (chunking handles size). |
| `api/app/session_manager.py` | No change — `_persist_to_cosmos()` sends full dict; chunking is handled by graph-query-api. |
| `frontend/src/hooks/useSession.ts` | No change — `loadSessionMessages()` receives reconstructed session from API. |
| `frontend/src/types/index.ts` | Add optional `partial?: boolean` to `SessionDetail`. |

### Trade-off: Chunking vs. Alternatives

| Approach | Pros | Cons |
|----------|------|------|
| **Chunking** | No data loss, supports arbitrarily large sessions, clean separation of concerns | Multi-doc writes not atomic, retrieval latency increases, more complex code |
| **Increase MAX_EVENT_LOG_SIZE + compress** | Simple, single document | Still hits 2MB limit eventually, gzip adds CPU overhead, can't query individual events |
| **Event pruning** (current approach) | Already implemented, simple | Loses early events, not suitable for full session replay |
| **Keep current + raise MAX_EVENT_LOG_SIZE to 400** | Zero effort | Current 500 is already borderline; doesn't solve the fundamental problem |

**Recommendation**: Implement chunking at the `graph-query-api` level. This is transparent to the API service and frontend — they continue to send/receive full session dicts. The chunking logic is encapsulated in `router_sessions.py`.

---

## 6. Overall Feasibility Verdict

**The revamp is achievable.** All six requirements can be met, though the degree of sub-agent internal streaming (Requirements 1, 2, 6) depends on the chosen approach:

| Requirement | Verdict | Approach |
|-------------|---------|----------|
| 1. Hierarchical streaming | ⚠️ Achievable (partial) | Option B: parsed output hierarchy. Full 3-level requires XL refactor. |
| 2. Sub-agent internal visibility | ⚠️ Achievable (partial) | Parsed output sub-steps, not real-time. |
| 3. Async session management | ✅ Already met | Minor UX polish. |
| 4. Manual save + chunked persistence | ⚠️ Achievable | Manual save endpoint + chunked Cosmos writes. |
| 5. Graceful degradation | ✅ Already met | Minor hardening for chunked persistence. |
| 6. Real-time streaming of all steps | ✅ Achievable | Orchestrator-level already works. Add diagnosis delta streaming. |

**Recommended Scope Reduction**: Accept Option B (parsed output hierarchy) for Requirements 1 and 2 instead of the full manual sub-agent orchestration. This delivers 80% of the UX value (visible sub-agent queries and results, collapsible tree structure) without the risk and effort of changing the execution model. Manual sub-agent orchestration (Option A) can be revisited in a future phase if the SDK adds sub-agent event forwarding or if the partial approach is deemed insufficient.

---

## 7. Recommended Task Breakdown

| # | Task | Effort | Dependencies | Output |
|---|------|--------|-------------|--------|
| 02 | **Hierarchical event schema** — Add `parent_step`, `depth`, `sub_steps` to `StepEvent`; define `SubStepEvent` type; update Cosmos document schema | S | None | Modified types, event schema |
| 03 | **Sub-agent output decomposition** — Parse `connected_agent.output` in `on_run_step(completed)` into child sub_step events; emit `sub_step_complete` events with parent reference | M | Task 02 | Modified `orchestrator.py` (both handler classes) |
| 04 | **Frontend tree rendering** — Refactor `ChatPanel.tsx` to render steps as a collapsible tree; indent sub-steps under parent; add expand/collapse controls at each level | M | Task 02 | Modified `ChatPanel.tsx`, new `StepTree` component |
| 05 | **Diagnosis delta streaming** — Emit `message_delta` events from `on_message_delta()`; frontend accumulates and renders progressively | S | None | Modified `orchestrator.py`, `useSession.ts`, `ChatPanel.tsx` |
| 06 | **Manual save endpoint** — Add `POST /api/sessions/{id}/save`; remove auto-persist from `_finalize_turn()`; keep idle-timeout persist as safety net; add "Save" button in frontend | S | None | Modified `session_manager.py`, `routers/sessions.py`, frontend |
| 07 | **Chunked Cosmos persistence** — Manifest+chunk document model in `router_sessions.py`; transparent to API service and frontend | L | Task 06 | Modified `router_sessions.py` |
| 08 | **Graceful degradation for chunks** — Handle missing chunks in session retrieval; `partial` flag in API response; frontend banner for incomplete sessions | S | Task 07 | Modified `router_sessions.py`, frontend |
| 09 | **Integration testing** — End-to-end test: create session → stream → save → load → verify hierarchy + chunks + partial rendering | M | Tasks 02–08 | Test scripts |

**Total estimated effort**: ~3–4 weeks for one engineer.

**Critical path**: Tasks 02 → 03 → 04 (hierarchy) and Tasks 06 → 07 → 08 (persistence) can be parallelized.
