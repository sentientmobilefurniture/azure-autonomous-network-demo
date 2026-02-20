# Task 02: Implementation Plan — Conversation Revamp

> **Phase**: [README.md](../README.md) — Azure Autonomous Network Demo: Conversation Revamp  
> **Input**: [task_01_validation_plan.md](task_01_validation_plan.md)

---

## Approach

Option B from the validation: keep `ConnectedAgentTool`, decompose sub-agent output into synthetic child steps, render as a collapsible tree. No execution-model change.

Seven implementation tasks, two parallel tracks. Each task is self-contained with exact files, functions, and line-level targets.

---

## Track A — Streaming & Hierarchy

### Task A1: Hierarchical Event Schema

**Goal**: Extend the step data model to support parent/child relationships and sub-steps.

**Files to modify**:

1. **`frontend/src/types/index.ts`** — `StepEvent` interface (L80–96)
   - Add fields:
     ```typescript
     parent_step?: number;       // step number of the parent (undefined = top-level)
     depth?: number;             // 0 = orchestrator level, 1 = sub-agent query
     sub_steps?: SubStepEvent[]; // populated by decomposition, rendered as children
     ```
   - Add new interface:
     ```typescript
     export interface SubStepEvent {
       index: number;           // 0-based within parent
       query: string;           // the sub-agent's individual query
       result_summary: string;  // truncated result text
       agent?: string;          // sub-agent name (from SSE payload)
       parent_step?: number;    // step number of parent (from SSE payload)
       visualization?: VisualizationData;
       timestamp?: string;
     }
     ```

2. **`frontend/src/types/index.ts`** — `ChatMessage` interface (L186–203)
   - No structural change. `steps: StepEvent[]` already carries the data. `sub_steps` lives on each `StepEvent`.

3. **`frontend/src/types/index.ts`** — `SessionDetail` interface (L205–228)
   - Add `partial?: boolean` (for later use by chunked persistence).

**Verification**: `npx tsc --noEmit` passes.

---

### Task A2: Sub-agent Output Decomposition

**Goal**: When a `connected_agent` step completes, parse its structured output into `sub_steps[]` and emit per-query `sub_step_complete` events.

**Files to modify**:

1. **`api/app/orchestrator.py`** — `SSEEventHandler` in `run_orchestrator()` (L508–550)

   Current code at L508–516:
   ```python
   if tc_type == "connected_agent":
       ca = (tc.connected_agent ...)
       out = getattr(ca, "output", None) or ca.get("output", None)
       if out:
           response, visualizations = self._parse_structured_output(agent_name, str(out))
   ```

   **INSIDE the `if out:` block**, after `_parse_structured_output` returns, **add sub-step extraction**:
   ```python
           # Decompose into sub_steps for hierarchical rendering
           sub_steps = self._extract_sub_steps(agent_name, str(out))
   ```

   ⚠️ **Critical**: This MUST be inside the `if out:` guard. Placing it outside would pass `str(None)` → `"None"` to the regex, returning garbage.

   Then, after the truncation block and before `_put("step_response", ...)`, include in `event_data`:
   ```python
   if sub_steps:
       event_data["sub_steps"] = sub_steps
   ```

   And emit individual `sub_step_complete` events:
   ```python
   for ss in sub_steps:
       _put("sub_step_complete", {
           "parent_step": ui_step,
           "index": ss["index"],
           "agent": agent_name,
           "query": ss["query"],
           "result_summary": ss["result_summary"],
           "timestamp": datetime.now(timezone.utc).isoformat(),
       })
   ```

   Also initialise `sub_steps = []` before the `if tc_type == "connected_agent":` block so the variable is always defined when `event_data` is built.

2. **`api/app/orchestrator.py`** — Refactor `_parse_structured_output()` to also return sub-steps

   ⚠️ **Do NOT add a separate `_extract_sub_steps()` method.** The regex
   `r'---QUERY---\s*(.+?)\s*---RESULTS---\s*(.+?)\s*(?=---QUERY---|---ANALYSIS---|$)'`
   is already used by `_parse_structured_output()` (L260–265). Running it twice on the same output is wasteful and risks inconsistent truncation lengths (500 chars in sub-steps vs 2000 chars in response).

   Instead, modify `_parse_structured_output()` to return a 3-tuple `(response_text, visualizations, sub_steps)`:
   ```python
   def _parse_structured_output(self, agent_name: str, raw_output: str) -> tuple:
       """Parse sub-agent output into (summary_text, visualizations_list, sub_steps_list)."""
       # ... existing regex parsing for query_blocks ...

       # Build sub_steps from the same blocks (single pass)
       sub_steps = []
       for i, (query_text, results_text) in enumerate(query_blocks):
           sub_steps.append({
               "index": i,
               "query": query_text.strip()[:300],
               "result_summary": results_text.strip()[:500],
           })

       return summary, visualizations, sub_steps
   ```

   Update ALL callers (both `run_orchestrator` at L516 and `run_orchestrator_session` at ~L1180) to unpack the 3-tuple:
   ```python
   response, visualizations, sub_steps = self._parse_structured_output(agent_name, str(out))
   ```

   When no blocks are found, `sub_steps` should be `[]`.

3. **`api/app/orchestrator.py`** — Mirror changes in `run_orchestrator_session()` handler (L1170–1215)

   The session-aware handler is a near-copy of the class. Apply identical changes:
   - Update the `_parse_structured_output()` call to unpack 3-tuple (connected_agent block at ~L1180).
   - Add `sub_steps` to `event_data` and emit `sub_step_complete` events in the `connected_agent` branch of `on_run_step(status=completed)`.
   - Initialise `sub_steps = []` before the type check.

   Note: `on_message_delta` is at L1211–1213 (not L1210 as implied by the range).

4. **`frontend/src/hooks/useSession.ts`** — `updateOrchestratorMessage` switch (L14–80)

   Add case for `sub_step_complete`:
   ```typescript
   case 'sub_step_complete': {
     const parentNum = data.parent_step as number;
     updated.steps = (updated.steps ?? []).map(s =>
       s.step === parentNum
         ? { ...s, sub_steps: [...(s.sub_steps ?? []), data as any] }
         : s
     );
     break;
   }
   ```

   Add case for `message_delta` (Task A3 dependency — add now, handle in A3):
   ```typescript
   case 'message_delta':
     updated.partialDiagnosis = (updated.partialDiagnosis ?? '') + (data.text as string);
     updated.status = 'investigating';
     break;
   ```

   ⚠️ **Also update the existing `message` case** to clear stale `partialDiagnosis`:
   ```typescript
   case 'message':
     updated.diagnosis = data.text as string;
     updated.partialDiagnosis = undefined;  // ← ADD: clear streaming buffer
     updated.status = 'complete';
     break;
   ```
   Without this, after the final diagnosis arrives, both `diagnosis` (full text) and `partialDiagnosis` (accumulated deltas) remain on the message object — doubling memory usage and causing confusion during session replay/serialisation.

5. **`frontend/src/hooks/useSession.ts`** — `loadSessionMessages` (L281–324)

   Inside the `else if (currentOrch)` block, add a **new branch** for `sub_step_complete` (NOT inside the `step_complete` branch — this is a sibling `else if`):
   ```typescript
   else if (evType === 'sub_step_complete') {
     const parentNum = data.parent_step as number;
     if (currentOrch) {
       currentOrch.steps = (currentOrch.steps ?? []).map(s =>
         s.step === parentNum
           ? { ...s, sub_steps: [...(s.sub_steps ?? []), data] }
           : s
       );
     }
   }
   ```

**Verification**: Run the API locally, trigger a session, confirm `sub_step_complete` events appear in the SSE stream. Confirm `event_log` contains them.

---

### Task A3: Diagnosis Delta Streaming

**Goal**: Stream the orchestrator's final diagnosis text token-by-token instead of in a single `message` event.

**Files to modify**:

1. **`api/app/orchestrator.py`** — `on_message_delta` in `run_orchestrator()` (L552–554)

   Change from:
   ```python
   def on_message_delta(self, delta):
       if delta.text:
           self.response_text += delta.text.value
   ```
   To:
   ```python
   def on_message_delta(self, delta):
       if delta.text:
           self.response_text += delta.text.value
           _put("message_delta", {"text": delta.text.value})
   ```

2. **`api/app/orchestrator.py`** — Same change in `run_orchestrator_session()` handler (L1211–1213).

3. **`frontend/src/types/index.ts`** — `ChatMessage` interface (L186–203)

   Add field:
   ```typescript
   partialDiagnosis?: string;   // accumulated message_delta text, pre-completion
   ```

4. **`frontend/src/hooks/useSession.ts`** — `updateOrchestratorMessage` switch

   Already handled in Task A2 (the `message_delta` case). When the final `message` event arrives, `diagnosis` replaces `partialDiagnosis`.

5. **`frontend/src/hooks/useSession.ts`** — `connectToStream` thinking-state logic (L107–130)

   Add `message_delta` to the thinking-state dispatch. Insert a new `else if` branch:
   ```typescript
   } else if (ev.event === 'message_delta') {
     setThinking(null);  // Clear thinking dots — diagnosis is now streaming
   }
   ```
   Also add `sub_step_complete` to the clearing group:
   ```typescript
   } else if (ev.event === 'sub_step_complete') {
     setThinking(null);
   }
   ```

6. **`frontend/src/components/ChatPanel.tsx`** — Render partial diagnosis (L94–103)

   Before the `{msg.diagnosis && <DiagnosisBlock .../>}` block, add:
   ```tsx
   {!msg.diagnosis && msg.partialDiagnosis && (
     <div className="glass-card overflow-hidden">
       <div className="px-3 py-2 text-xs font-medium text-text-muted">Diagnosis</div>
       <div className="prose prose-sm max-w-none px-3 pb-3 animate-pulse">
         <ReactMarkdown>{msg.partialDiagnosis}</ReactMarkdown>
       </div>
     </div>
   )}
   ```

**Verification**: Run a session. Diagnosis text should appear incrementally in the UI as the orchestrator generates it, then snap to final form on `message` event.

---

### Task A4: Frontend Tree Rendering

**Goal**: Render sub-steps indented under their parent `StepCard`, collapsible.

**Files to modify / create**:

1. **`frontend/src/components/SubStepList.tsx`** — **New file**

   Renders `sub_steps[]` as an indented list under a parent step:
   ```tsx
   interface SubStepListProps {
     subSteps: SubStepEvent[];
     agentName: string;
   }
   export function SubStepList({ subSteps, agentName }: SubStepListProps) {
     // Render each sub-step as a compact query→result row
     // Indented under parent via ml-6
     // Collapsible result text
   }
   ```

   Visual design:
   - Left border (brand color, 2px) connecting to parent.
   - Compact rows: `▸ Query: {query}` / `Result: {summary}` (collapsible).
   - "View" button on each row if visualization data exists.

2. **`frontend/src/components/StepCard.tsx`** — Integrate sub-steps (L120–200, expanded detail section)

   Inside the expanded `<AnimatePresence>` block, after the response section, add:
   ```tsx
   {step.sub_steps && step.sub_steps.length > 0 && (
     <SubStepList subSteps={step.sub_steps} agentName={step.agent} />
   )}
   ```

   In the collapsed preview, add a sub-step count badge:
   ```tsx
   {step.sub_steps && step.sub_steps.length > 0 && (
     <span className="text-[10px] text-brand/60 ml-1">
       ({step.sub_steps.length} queries)
     </span>
   )}
   ```

3. **`frontend/src/components/ChatPanel.tsx`** — No structural changes needed. Steps remain flat in the `steps.map()`. Hierarchy is rendered *within* each `StepCard` via `SubStepList`.

**Verification**: With a session that has multi-query sub-agents (GraphExplorer, Telemetry), sub-steps should appear inside the expanded step card.

---

## Track B — Persistence

### Task B1: Manual Save Endpoint

**Goal**: Replace auto-persist with user-triggered save. Keep idle-timeout persist as safety net.

**Files to modify**:

1. **`api/app/session_manager.py`** — `_finalize_turn()` (L162–190)

   Change the success path from:
   ```python
   session.status = SessionStatus.COMPLETED
   asyncio.create_task(self._persist_to_cosmos(session))
   self._schedule_idle_timeout(session)
   ```
   To:
   ```python
   session.status = SessionStatus.COMPLETED
   # Do NOT auto-persist — user must explicitly save.
   # Keep idle timeout as safety net: persist after 10 min if not saved.
   self._schedule_idle_timeout(session)
   ```

2. **`api/app/session_manager.py`** — Add `save_session()` method

   ```python
   async def save_session(self, session_id: str) -> bool:
       """Explicitly persist a session to Cosmos DB (user-triggered)."""
       session = self.get(session_id)
       if not session:
           return False
       await self._persist_to_cosmos(session)
       return True
   ```

3. **`api/app/routers/sessions.py`** — Add `POST /api/sessions/{id}/save` endpoint

   ```python
   @router.post("/{session_id}/save")
   async def save_session(session_id: str):
       session = session_manager.get(session_id)
       if not session:
           raise HTTPException(404, "Session not found")
       ok = await session_manager.save_session(session_id)
       if not ok:
           raise HTTPException(500, "Save failed")
       return {"saved": session_id}
   ```

4. **Frontend** — Add save button

   In `frontend/src/components/DiagnosisBlock.tsx` or the run-meta footer in `ChatPanel.tsx` (L113–124), add a "Save" button next to the "Copy" button:
   ```tsx
   <button
     onClick={() => fetch(`/api/sessions/${activeSessionId}/save`, { method: 'POST' })}
     className="hover:text-text-primary transition-colors"
   >
     Save
   </button>
   ```

   This requires passing `activeSessionId` down through props or using a context. Simplest: add `sessionId` prop to `ChatPanel` and pass it to the footer.

5. **`frontend/src/hooks/useSession.ts`** — Expose `saveSession` callback

   ```typescript
   const saveSession = useCallback(async () => {
     if (!activeSessionId) return;
     await fetch(`/api/sessions/${activeSessionId}/save`, { method: 'POST' });
   }, [activeSessionId]);
   ```
   **Add `saveSession` to the return object** (currently at L353–363):
   ```typescript
   return {
     messages,
     thinking,
     running,
     activeSessionId,
     createSession,
     sendFollowUp,
     viewSession,
     cancelSession,
     handleNewSession,
     deleteSession,
     saveSession,       // ← ADD
   };
   ```

**Verification**: Complete a session. Refresh the page. Session should NOT appear in Cosmos (until save is clicked or 10-min idle timeout fires). Click save. Refresh. Session loads from Cosmos.

---

### Task B2: Chunked Cosmos Persistence

**Goal**: Split session `event_log` into chunks on write, reconstruct on read. Transparent to the API service.

**Files to modify**:

1. **`graph-query-api/router_sessions.py`** — `upsert_session()` (PUT endpoint)

   Replace the current single-document write with:
   ```python
   CHUNK_SIZE = 100  # events per chunk

   @router.put("/sessions")
   async def upsert_session(request: Request):
       body = await request.json()
       if "id" not in body or "scenario" not in body:
           raise HTTPException(400, "...")
       store = _get_store()

       event_log = body.pop("event_log", [])
       steps = body.pop("steps", [])

       # Split event_log into chunks
       chunks = [event_log[i:i+CHUNK_SIZE] for i in range(0, len(event_log), CHUNK_SIZE)] if event_log else [[]]
       # Note: the previous `max(len, 1)` + `if not chunks` pattern had dead code — the fallback was unreachable.

       chunk_ids = []
       for idx, chunk_events in enumerate(chunks):
           chunk_id = f"{body['id']}:chunk-{idx}"
           chunk_ids.append(chunk_id)
           await store.upsert({
               "id": chunk_id,
               "_docType": "session_chunk",
               "session_id": body["id"],
               "scenario": body["scenario"],
               "chunk_index": idx,
               "events": chunk_events,
           })

       # Delete any orphaned chunks from prior saves with more chunks
       old_chunks = await store.list(
           query="SELECT c.id, c.chunk_index FROM c WHERE c.session_id = @sid AND c._docType = 'session_chunk' AND c.chunk_index >= @max_idx",
           parameters=[
               {"name": "@sid", "value": body["id"]},
               {"name": "@max_idx", "value": len(chunks)},
           ],
           partition_key=body["scenario"],
       )
       for oc in old_chunks:
           try:
               await store.delete(oc["id"], partition_key=body["scenario"])
           except Exception:
               pass

       # Upsert manifest (without event_log)
       body["_docType"] = "session"
       body["chunk_count"] = len(chunks)
       body["chunk_ids"] = chunk_ids
       body["steps"] = steps  # keep steps on manifest (small)
       await store.upsert(body)
       return {"ok": True, "id": body["id"], "chunks": len(chunks)}
   ```

2. **`graph-query-api/router_sessions.py`** — `get_session()` (GET by ID)

   Replace with chunk reconstruction:
   ```python
   @router.get("/sessions/{session_id}")
   async def get_session(session_id: str):
       store = _get_store()
       # Load manifest
       manifests = await store.list(
           query="SELECT * FROM c WHERE c.id = @id AND (c._docType = 'session' OR NOT IS_DEFINED(c._docType))",
           parameters=[{"name": "@id", "value": session_id}],
       )
       if not manifests:
           raise HTTPException(404, "Session not found")
       manifest = manifests[0]

       # Load chunks
       chunk_count = manifest.get("chunk_count", 0)
       if chunk_count > 0:
           chunks = await store.list(
               query="SELECT * FROM c WHERE c.session_id = @sid AND c._docType = 'session_chunk' ORDER BY c.chunk_index",
               parameters=[{"name": "@sid", "value": session_id}],
               partition_key=manifest.get("scenario"),
           )
           event_log = []
           for chunk in sorted(chunks, key=lambda c: c.get("chunk_index", 0)):
               event_log.extend(chunk.get("events", []))
           manifest["event_log"] = event_log
           if len(chunks) < chunk_count:
               manifest["partial"] = True
       elif "event_log" not in manifest:
           manifest["event_log"] = []

       return manifest
   ```

3. **`graph-query-api/router_sessions.py`** — `delete_session()` (DELETE)

   Before deleting the manifest, also delete all chunks:
   ```python
   # Delete chunks first
   chunks = await store.list(
       query="SELECT c.id FROM c WHERE c.session_id = @sid AND c._docType = 'session_chunk'",
       parameters=[{"name": "@sid", "value": session_id}],
       partition_key=pk,
   )
   for chunk in chunks:
       try:
           await store.delete(chunk["id"], partition_key=pk)
       except Exception:
           pass
   ```

4. **`api/app/sessions.py`** — `MAX_EVENT_LOG_SIZE` (L71)

   Increase or remove the cap now that chunking handles size:
   ```python
   MAX_EVENT_LOG_SIZE = 2000  # chunking at persistence layer handles Cosmos limits
   ```

   ⚠️ **Cross-track dependency**: Task A2 adds `sub_step_complete` events (~5 extra per step × ~10 steps = ~50 extra events per turn). Under the current 500 cap, multi-turn sessions will lose early events faster. This `MAX_EVENT_LOG_SIZE` increase **should be applied alongside Task A2**, not deferred to B2. If B2 ships later than A2, temporarily increase the cap in A2 to at least 1000.

5. **`graph-query-api/router_sessions.py`** — `list_sessions()` (GET list)

   Ensure the list query filters to `_docType = 'session'` (already does — L52). Chunks won't appear in list results.

**Verification**: Save a session with >100 events. Inspect Cosmos — should see 1 manifest + N chunk documents. Load the session — event_log should be fully reconstructed.

---

### Task B3: Graceful Degradation for Chunks

**Goal**: Handle missing chunks without crashing. Surface partial-data indicator in UI.

**Files to modify**:

1. **`graph-query-api/router_sessions.py`** — `get_session()`

   Already handled in Task B2: `manifest["partial"] = True` when `len(chunks) < chunk_count`.

2. **`frontend/src/types/index.ts`** — `SessionDetail` (L205–228)

   Add: `partial?: boolean;` (already planned in Task A1).

3. **`frontend/src/hooks/useSession.ts`** — `loadSessionMessages()` (L296–341)

   Wrap each event parse in try-catch:
   ```typescript
   for (const event of session.event_log) {
     try {
       const evType = event.event;
       const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
       // ... existing logic
     } catch {
       continue; // skip malformed events
     }
   }
   ```

4. **`frontend/src/components/ChatPanel.tsx`** — Add partial-data banner

   Accept `partial?: boolean` prop. At the top of the message list:
   ```tsx
   {partial && (
     <div className="glass-card p-2 border-amber-500/20 bg-amber-500/5 text-xs text-amber-400">
       ⚠ Some session data may be incomplete
     </div>
   )}
   ```

5. **`frontend/src/hooks/useSession.ts`** — `viewSession()` (L327–350)

   Pass `session.partial` to the UI state or into the messages array so `ChatPanel` can render the banner.

**Verification**: Manually delete a chunk document from Cosmos. Load the session. Banner should appear. Remaining data should render without crash.

---

## Execution Order

```
Week 1:
  A1 (schema)          → A2 (decomposition)     → A3 (diagnosis delta)
  B1 (manual save)     ← independent

Week 2:
  A4 (tree rendering)  ← depends on A1, A2
  B2 (chunking)        ← depends on B1

Week 3:
  B3 (degradation)     ← depends on B2
  Integration testing  ← depends on all
```

Both tracks are independent until integration testing **except for one cross-track dependency**: Task A2 (sub_step_complete events) increases event volume, which interacts with `MAX_EVENT_LOG_SIZE` (raised in B2). If A2 ships before B2, temporarily increase `MAX_EVENT_LOG_SIZE` from 500 to 1000 in A2 to prevent early event loss in multi-turn sessions.

A1→A2→A3→A4 is serial. B1→B2→B3 is serial. The two chains can otherwise run in parallel.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Sub-agent output doesn't follow `---QUERY---/---RESULTS---` format | No sub-steps generated | `_extract_sub_steps` returns empty list gracefully. Prompt engineering ensures format compliance. |
| `message_delta` causes excessive React re-renders | UI jank during diagnosis streaming | Debounce: batch deltas in a `useRef` buffer, flush to state every 100ms via `requestAnimationFrame`. |
| Chunked writes partially fail (Cosmos crash mid-write) | Orphaned chunks | `get_session` handles missing chunks (`partial: true`). Orphan cleanup can run on next save. |
| Removing auto-persist loses sessions on container crash | Data loss for unsaved sessions | Idle-timeout persist (10 min) remains as safety net. Document this behavior for users. |
| Asymmetric persist behavior (error/cancel auto-persist, success doesn't) | Confusing mental model | Intentional: failed/cancelled sessions persist immediately via `_move_to_recent` so users see them. Success path waits for manual save or idle timeout. Document this asymmetry. |
| Sub_step_complete events fill event_log faster under 500-event cap | Early events lost in multi-turn sessions before B2 ships | Temporarily raise `MAX_EVENT_LOG_SIZE` to 1000 in A2. B2 raises it to 2000 permanently. |
| Duplicated handler code in `orchestrator.py` (two copies of `SSEEventHandler`) | Maintenance burden | Out of scope for this phase. Future refactor: extract a shared base class. Note as tech debt. |

---

## Out of Scope

- **Manual sub-agent orchestration** (Option A) — deferred. Too high risk/effort for this phase.
- **Refactoring duplicated `SSEEventHandler`** — tech debt, not blocking.
- **Concurrent sub-agent streaming** — requires SDK support for `ConnectedAgentTool` event forwarding. Not available in `azure-ai-agents==1.2.0b6`.
- **Session export/import** — not in requirements.
