# Task 01: Scorched Earth — Delete & Gut

> **Phase**: A (Deletion)
> **Prerequisite**: None
> **Output**: `execution/task_01_scorched_earth_execution_log.md`

## Goal

Remove all old conversation/session code. After this task, the app will not compile. That is expected and intentional.

## Exact Operations

Execute in this exact order. Each step includes the verification command.

### Step 1: Delete frontend files

```bash
rm frontend/src/hooks/useSession.ts
rm frontend/src/components/ChatPanel.tsx
rm frontend/src/components/StepCard.tsx
rm frontend/src/components/ThinkingDots.tsx
```

**Verify**: `ls frontend/src/hooks/useSession.ts 2>&1` → "No such file"

### Step 2: Delete dead backend code

```bash
rm api/app/routers/alert.py
```

**Verify**: `ls api/app/routers/alert.py 2>&1` → "No such file"

### Step 3: Gut `frontend/src/types/index.ts`

Remove these type definitions (keep everything else):

- `SubStepEvent` interface (lines defining `index`, `query`, `result_summary`, etc.)
- `StepEvent` interface (lines defining `step`, `agent`, `duration`, etc.)
- `ThinkingState` interface
- `ChatRole` type alias
- `ChatMessage` interface
- From `SessionDetail`: update `event_log` to `Array<{ event: string; data: unknown; turn?: number; timestamp?: string }>` (change `data: string` → `data: unknown`)

Keep intact:
- `VisualizationColumn`, `GraphVisualizationData`, `TableVisualizationData`, `SearchHit`, `DocumentVisualizationData`, `VisualizationData`
- `ActionData`
- `RunMeta`
- `ResourceNodeType`, `ResourceNode`, `ResourceEdgeType`, `ResourceEdge`
- `TopologyNode`, `TopologyEdge`, `TopologyMeta`
- `SessionSummary`, `SessionDetail` (with updated `event_log` type)

### Step 4: Gut `frontend/src/App.tsx`

Remove:
- `import { useSession } from './hooks/useSession';`
- `import { ChatPanel } from './components/ChatPanel';`
- The `useSession()` destructured call
- The `<ChatPanel>` JSX element
- The `useAutoScroll(messages, thinking)` call (will re-add in Phase B)

Replace the chat section (scroll area + ChatPanel + ChatInput) with a placeholder:

```tsx
{/* PLACEHOLDER: ConversationPanel + ChatInput — rebuilt in Phase B */}
<div className="flex-1 min-h-0 flex items-center justify-center">
  <span className="text-text-muted text-sm">Conversation system removed — rebuilding</span>
</div>
```

Comment out (don't delete) `useAutoScroll`, `useSessions`, session sidebar, and the refetch logic — they'll be restored in Phase B wiring.

### Step 5: Gut backend `api/app/orchestrator.py`

Delete the BODY of both functions (`run_orchestrator` and `run_orchestrator_session`) and the duplicated `SSEEventHandler` classes. Leave the function signatures as stubs:

```python
async def run_orchestrator(alert_text: str) -> AsyncGenerator[dict, None]:
    """Stub — replaced in Task 03."""
    raise NotImplementedError("run_orchestrator gutted — see phase_03 task 03")
    yield  # make it a generator

async def run_orchestrator_session(
    alert_text: str,
    cancel_event: threading.Event = None,
    existing_thread_id: str = None,
) -> AsyncGenerator[dict, None]:
    """Stub — replaced in Task 03."""
    raise NotImplementedError("run_orchestrator_session gutted — see phase_03 task 03")
    yield  # make it a generator
```

Keep intact:
- Module-level imports
- `is_configured()` function
- `_load_orchestrator_id()`, `_load_agent_names()`, `_get_project_client()` helpers
- `_get_credential()` singleton

### Step 6: Update backend event type strings

In `api/app/session_manager.py`, update `start()` and `continue_session()`:
- `"step_complete"` → `"tool_call.complete"`
- `"message"` → `"message.complete"`
- `"run_complete"` → `"run.complete"`
- `"error"` → `"error"` (stays the same)
- `"thread_created"` → `"session.created"`

In `api/app/routers/sessions.py`:
- `"status_change"` → `"status"`

### Step 7: Remove `@microsoft/fetch-event-source`

```bash
cd frontend && npm uninstall @microsoft/fetch-event-source
```

### Step 8: Verify expected breakage

```bash
# Frontend — should show type errors (expected)
cd frontend && npx tsc --noEmit 2>&1 | head -30

# Backend — should compile (stubs are valid Python)
python3 -m py_compile api/app/orchestrator.py
python3 -m py_compile api/app/session_manager.py
python3 -m py_compile api/app/routers/sessions.py
```

**Expected**: Frontend has ~15-20 TypeScript errors (missing types, broken imports in surviving files). Backend compiles cleanly.

## Completion Criteria

- [ ] 4 frontend files deleted
- [ ] 1 backend file deleted (`routers/alert.py`)
- [ ] `types/index.ts` gutted — no `ChatMessage`, `ChatRole`, `ThinkingState`, `SubStepEvent`, `StepEvent`
- [ ] `App.tsx` gutted — no `useSession`, `ChatPanel` references
- [ ] `orchestrator.py` gutted — function stubs only, no SSEEventHandler classes
- [ ] `session_manager.py` uses new event type strings
- [ ] `@microsoft/fetch-event-source` removed from `package.json`
- [ ] Backend Python files compile with `py_compile`
- [ ] TypeScript errors are ONLY in expected surviving files (useAutoScroll, UserMessage, SubStepList, ActionCard, useVisualization, StepVisualizationModal)
