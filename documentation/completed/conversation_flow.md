# Incremental Conversation Flow

## Problem

Every step in the conversation appears as a single burst: orchestrator reasoning + agent name + query + response all materialize at once. The user sees "Orchestrator — processing…" for 20–140 seconds, then a fully-formed card pops in. This feels unresponsive and hides the work the orchestrator is doing in real time.

## Current Event Timeline

A single tool-call step currently produces this SSE sequence:

```
T+0s    on_run_step(status=in_progress)
         → emit step_thinking { agent: "Orchestrator", status: "calling sub-agent..." }
         → UI shows ThinkingDots "Orchestrator — calling sub-agent..."

T+20s   on_run_step(status=completed)    ← sub-agent has finished
         → emit step_start  { step: N, agent: "GraphExplorerAgent" }
         → emit step_complete { step: N, agent, query, response, visualizations, reasoning }
         → UI renders OrchestratorThoughts + StepCard in one burst
```

Both `step_start` and `step_complete` are emitted at the same moment — inside the `on_run_step(status=completed)` handler, *after* the sub-agent has already returned. The 20+ second gap between `step_thinking` and the burst is dead air.

## Desired Behaviour

```
T+0s    Orchestrator decides to call GraphExplorerAgent
         → UI: Orchestrator Thoughts bubble appears (reasoning)
         → UI: StepCard appears with agent name + query + spinning indicator
               "● GraphExplorerAgent — Querying..."
               "Query: What MPLS paths depend on LINK-SYD-MEL-FIBRE-01?"

T+22s   Sub-agent responds
         → UI: StepCard updates in-place — spinner replaced with response + View Data button
               Duration stamp appears ("22.7s")

T+22s   Orchestrator decides next call
         → UI: Next Orchestrator Thoughts bubble appears
         → UI: Next StepCard with agent name + query + spinner
         ... and so on
```

Each step unfolds incrementally rather than bursting all at once.

## Root Cause

The Azure AI Agents SDK `AgentEventHandler.on_run_step()` callback fires with the step object at various lifecycle stages. When `status=in_progress`, the `step.step_details.tool_calls` list **already contains the tool call definitions** (agent name, arguments/query) — but the current code ignores this data and emits only a generic "calling sub-agent…" thinking indicator.

The agent name, query, and reasoning are all available at `in_progress` time. Only the **response** requires waiting for `status=completed`.

## Plan

### Layer 1: Backend — Split step_complete Into Two Events

**File:** `api/app/orchestrator.py` — **both** `SSEEventHandler` classes:
- Class inside `run_orchestrator` (around line 357)
- Class inside `run_orchestrator_session` (around line 974)

Apply the identical changes below to **both** classes.

**Prerequisite:** Before implementing, add a temporary log line to verify that `step.step_details.tool_calls` is populated when `status=in_progress`. The entire optimisation depends on this SDK behaviour. Record the SDK version tested against (check with `pip show azure-ai-agents`).

**Change `on_run_step(status=in_progress)`:**

Currently:
```python
if status == "in_progress" and step.id not in self.step_starts:
    self.step_starts[step.id] = time.monotonic()
    _put("step_thinking", {"agent": "Orchestrator", "status": "calling sub-agent..."})
```

New behaviour:
```python
if status == "in_progress" and step.id not in self.step_starts:
    self.step_starts[step.id] = time.monotonic()

    # Try to extract tool call details early
    if step_type == "tool_calls" and hasattr(step, "step_details"):
        tool_calls = getattr(step.step_details, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                self.ui_step += 1
                tc_id = getattr(tc, "id", None) or str(id(tc))
                agent_name = self._resolve_agent_name(tc)
                query, reasoning = self._extract_arguments(tc)
                # Remember step_id → {tc_id → metadata} for the completed handler
                if step.id not in self._pending_steps:
                    self._pending_steps[step.id] = {}
                self._pending_steps[step.id][tc_id] = {
                    "ui_step": self.ui_step,
                    "agent": agent_name,
                    "query": query[:500] if query else "",
                    "reasoning": reasoning,
                }
                event = {
                    "step": self.ui_step,
                    "agent": agent_name,
                    "query": query[:500] if query else "",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                if reasoning:
                    event["reasoning"] = reasoning
                _put("step_started", event)        # ← NEW event name
            return  # Don't emit the generic thinking event

    # Fallback: tool_calls not yet available
    _put("step_thinking", {"agent": "Orchestrator", "status": "calling sub-agent..."})
```

**Key points:**
- New SSE event type: `step_started` (distinct from `step_start` so existing behavior is preserved during rollout)
- Contains: `step`, `agent`, `query`, `reasoning`, `timestamp`
- Does NOT contain: `response`, `duration`, `visualizations`
- The `_pending_steps` dict maps SDK step IDs → `{tc_id → metadata}` so the completed handler can match by tool-call ID (not list index, since the SDK does not guarantee ordering stability across status transitions)
- **Init required:** Add `self._pending_steps: dict[str, dict] = {}` alongside `self.step_starts` in `__init__` for both handler classes

**Change `on_run_step(status=completed)`:**

When a step completes and was already emitted via `step_started`:
```python
elif status == "completed" and step_type == "tool_calls":
    start = self.step_starts.get(step.id, self.t0)
    duration = f"{time.monotonic() - start:.1f}s"
    pending = self._pending_steps.pop(step.id, None)

    if not hasattr(step.step_details, "tool_calls"):
        return

    for tc in step.step_details.tool_calls:
        tc_id = getattr(tc, "id", None) or str(id(tc))
        # If we already emitted step_started, reuse the same ui_step number
        if pending and tc_id in pending:
            ui_step = pending[tc_id]["ui_step"]
        else:
            self.ui_step += 1
            ui_step = self.ui_step

        agent_name = self._resolve_agent_name(tc)
        query, reasoning = self._extract_arguments(tc)
        # ... extract response, visualizations as before ...

        event_data = {
            "step": ui_step,
            "agent": agent_name,
            "duration": duration,
            "query": query[:500] if query else "",
            "response": response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if visualizations:
            event_data["visualizations"] = visualizations
        if reasoning:
            event_data["reasoning"] = reasoning

        _put("step_response", event_data)   # ← NEW: incremental response
        _put("step_complete", event_data)    # ← KEEP: backward compat for replay & Cosmos
```

- New SSE event type: `step_response` — carries only the response half
- Uses the same `step` number as the earlier `step_started` so frontend can match them
- Falls back to emitting combined `step_start`/`step_complete` if no pending entry exists (defensive)

**Backward compat:** Keep emitting `step_complete` as well (with full data) so:
  - Session replay (viewSession) still works unchanged
  - Cosmos DB persistence still captures complete events


### Layer 2: Frontend — Two-Phase Step Rendering

#### 2a. Type Changes

**File:** `frontend/src/types/index.ts`

Add `pending` status to `StepEvent`:
```typescript
export interface StepEvent {
  step: number;
  agent: string;
  duration?: string;     // absent while pending
  timestamp?: string;
  query?: string;
  response?: string;     // absent while pending
  pending?: boolean;     // true = waiting for response
  error?: boolean;
  visualizations?: VisualizationData[];
  reasoning?: string;
  is_action?: boolean;
  action?: ActionData;
}
```

#### 2b. SSE Handler Changes

**File:** `frontend/src/hooks/useSession.ts`

Add `step_started` and `step_response` to `updateOrchestratorMessage`:

```typescript
case 'step_started':
  // Add a pending step — agent + query, no response yet
  updated.steps = [...(updated.steps ?? []), {
    step: data.step as number,
    agent: data.agent as string,
    query: data.query as string | undefined,
    reasoning: data.reasoning as string | undefined,
    timestamp: data.timestamp as string | undefined,
    pending: true,
  }];
  updated.status = 'investigating';
  break;

case 'step_response':
  // Match by step number and fill in the response
  updated.steps = (updated.steps ?? []).map(s =>
    s.step === data.step
      ? { ...s, ...data, pending: false }
      : s
  );
  updated.status = 'investigating';
  break;
```

Update the thinking state logic:
```typescript
if (ev.event === 'step_started') {
  setThinking(null);  // clear dots — the step card itself shows loading
} else if (ev.event === 'step_response') {
  setThinking(null);
}
```

#### 2c. StepCard Pending State

**File:** `frontend/src/components/StepCard.tsx`

When `step.pending === true`, render a streamlined card:
- Show agent name + query (already available)
- Show a pulsing/spinner indicator instead of response
- Hide duration (not yet known)
- Hide View Data button

When `step.pending` becomes `false` (step_response arrives), the card updates in-place with response, duration, and visualization button via React re-render.

```tsx
{step.pending ? (
  <div className="flex items-center gap-2 text-xs text-text-muted animate-pulse mt-1">
    <div className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce" />
    <span>Querying…</span>
  </div>
) : (
  // existing response rendering
)}
```

#### 2d. ChatPanel — No Structural Changes Needed

The ChatPanel already iterates `steps.map(...)` and renders each step. When a `step_started` event appends a pending step object, a new StepCard will appear. When `step_response` updates that object, the StepCard re-renders in place. No changes to ChatPanel needed.

#### 2e. Session Replay (viewSession) — No Changes Needed

`loadSessionMessages` in `useSession.ts` reconstructs messages from `event_log` entries. It only processes `step_complete` events (which we continue to emit). The `step_started`/`step_response` events are simply ignored during replay. Completed sessions always render with fully-populated step data.


### Layer 3: Fallback & Edge Cases

| Scenario | Handling |
|----------|----------|
| `step_details.tool_calls` is empty at `in_progress` time | Fall back to `step_thinking` (current behavior). `step_complete` fires as normal — no `step_started` was emitted, so existing path applies. |
| Multiple tool calls in one step | Emit one `step_started` per tool call. Match by step number in `step_response`. |
| SDK upgrade changes callback timing | `step_complete` is always emitted as a safety net. Frontend handles both old (step_complete-only) and new (step_started + step_response) patterns. |
| Failed steps | `on_run_step(status=failed)` pops any `_pending_steps[step.id]` entry, then emits `step_complete` with `error: true`. Uses the pending `ui_step` if available so the existing pending card gets replaced by the error card via `step_complete` handling. |
| Action (function tool) steps | Same split: `step_started` with the action name + args, then `step_response` with the output. |


## Execution Order

1. **Backend first** — Add `step_started`/`step_response` events to `orchestrator.py` (both handler classes). Keep `step_complete` for backward compat.
2. **Types** — Add `pending` field to `StepEvent`.
3. **useSession.ts** — Handle new SSE events.
4. **StepCard.tsx** — Add pending state rendering.
5. **Test** — Send an alert; verify steps appear incrementally.
6. **Cleanup** — Once confirmed working, consider removing redundant `step_start` events (not `step_complete`, which is needed for replay).

## Files to Touch

| File | Change |
|------|--------|
| `api/app/orchestrator.py` | Add `self._pending_steps = {}` to `__init__`. Emit `step_started` at `in_progress`, `step_response` + `step_complete` at `completed`. Apply to **both** handler classes (~L357 and ~L974). |
| `frontend/src/types/index.ts` | Add `pending?: boolean` to `StepEvent` |
| `frontend/src/hooks/useSession.ts` | Handle `step_started` and `step_response` events |
| `frontend/src/components/StepCard.tsx` | Render pending state with spinner |

## Risk Assessment

- **Low risk:** Frontend changes are additive — existing `step_complete` handling remains, new events are handled alongside.
- **Medium risk:** `step.step_details.tool_calls` availability at `in_progress` time depends on SDK version. If the SDK doesn't populate tool calls early (unlikely but possible in future versions), the fallback path fires and behavior is identical to today. **Mitigated** by the prerequisite validation step (add a temporary log to confirm before implementing).
- **No Cosmos/persistence risk:** `step_complete` continues to be emitted for all completed steps, so session replay and Cosmos records are unaffected.
- **No ordering risk:** Tool-call matching between `step_started` and `step_response` uses `tc.id` (the SDK's stable tool-call identifier), not list index position.
