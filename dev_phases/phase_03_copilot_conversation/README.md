# Project: Copilot-Style Conversation — Scorched Earth Rewrite

## Objective

Delete the entire existing session/conversation system (frontend + backend) and rebuild it from scratch using a GitHub Copilot–inspired architecture:

- **`useReducer`** with discriminated union types (no `useState` chains)
- **Native `ReadableStream`** SSE consumer (no `@microsoft/fetch-event-source`)
- **Progressive tool-call disclosure** (pending → running → complete per tool call)
- **Token-by-token message streaming** with cursor animation
- **Redesigned SSE event protocol** (OpenAI-style dotted event types)
- **Clean backend**: single `SSEEventHandler` (no duplication), unified orchestrator entry point

## Approach: Scorched Earth → Rebuild

**Phase A** — Delete all old conversation code. The app will not compile.
**Phase B** — Build new code from scratch into the empty slots. The app compiles again only when Phase B completes.

No backward compatibility. Old Cosmos sessions will not replay. Infrastructure will be redeployed.

## Success Criteria

- [ ] All old conversation code deleted (no dead code left behind)
- [ ] Backend emits new SSE event schema from a single unified handler
- [ ] Frontend consumes events via `useReducer` + `ReadableStream`
- [ ] Tool calls render with progressive disclosure
- [ ] Message text streams token-by-token
- [ ] Session CRUD works end-to-end (create, list, view, delete, save)
- [ ] Multi-turn follow-up works
- [ ] `npx tsc --noEmit` — 0 errors
- [ ] `python3 -m py_compile` — all Python files pass
- [ ] No regressions in non-conversation features

## General Instructions

- **Preserve** non-conversation components: graph viewer, resource visualizer, scenario panel, ontology panel, terminal panel, metrics bar, header, tab bar, resizable panels.
- **Preserve** the Tailwind + `glass-card` design system.
- **Preserve** the visualization system (`StepVisualizationModal`, `useVisualization`, graph/table/document result views). These will need type updates but not rewrites.
- **Preserve** `ActionCard` and `ActionEmailModal` — update their prop types only.
- The `graph-query-api/router_sessions.py` Cosmos persistence layer is event-type-agnostic (it stores `event_log` as an opaque list). No changes needed there.

---

## Deletion Manifest (Phase A)

### Frontend — DELETE these files

| File | Reason |
|------|--------|
| `frontend/src/hooks/useSession.ts` | Entire session hook — replaced by `useConversation` |
| `frontend/src/components/ChatPanel.tsx` | Main chat renderer — replaced by `ConversationPanel` |
| `frontend/src/components/StepCard.tsx` | Step renderer — replaced by `ToolCallCard` |
| `frontend/src/components/ThinkingDots.tsx` | Thinking indicator — replaced by `ThinkingIndicator` |

### Frontend — GUT these files (remove conversation types, keep the rest)

| File | What to remove | What to keep |
|------|---------------|-------------|
| `frontend/src/types/index.ts` | `ChatMessage`, `ChatRole`, `ThinkingState`, `SubStepEvent`, old `StepEvent` fields | `VisualizationData`, `ActionData`, `RunMeta`, `SessionSummary`, `SessionDetail`, graph/topology/resource types |
| `frontend/src/hooks/useAutoScroll.ts` | `ChatMessage`/`ThinkingState` type imports | The hook itself (update to use new `Message` type) |
| `frontend/src/components/UserMessage.tsx` | `ChatMessage` type import | The component (update to use new `UserMessage` type) |
| `frontend/src/components/SubStepList.tsx` | `SubStepEvent` type import | The component (update to use new `SubStep` type) |
| `frontend/src/components/ActionCard.tsx` | `StepEvent` type import | The component (update to use new `ToolCall` type) |
| `frontend/src/components/visualization/StepVisualizationModal.tsx` | `ThinkingDots` import, `StepEvent` type | The modal (update to new types + new loading indicator) |
| `frontend/src/hooks/useVisualization.ts` | `StepEvent` type import | The hook (update to use new `ToolCall` type) |
| `frontend/src/App.tsx` | `useSession`, `ChatPanel` imports + JSX | Layout shell, other tabs, non-conversation wiring |

### Frontend — REMOVE dependency

| Package | File |
|---------|------|
| `@microsoft/fetch-event-source` | `package.json` |

### Backend — GUT these files (rewrite internals, keep file structure)

| File | What changes |
|------|-------------|
| `api/app/orchestrator.py` | Delete both duplicated `SSEEventHandler` classes + both `_thread_target` functions. Rebuild as single handler + single entry point emitting new event schema. |
| `api/app/sessions.py` | Update event type references in any docstrings. The `Session` dataclass itself is event-type-agnostic — minimal changes. |
| `api/app/session_manager.py` | Update `ev_type` string checks in `start()` and `continue_session()` to match new event names. |
| `api/app/routers/sessions.py` | Minimal — update `status_change` emission to `status`. SSE transport is event-type-agnostic. |

### Backend — DELETE (dead code)

| File | Reason |
|------|--------|
| `api/app/routers/alert.py` | Legacy single-shot alert endpoint, not mounted in `main.py`. Uses old `run_orchestrator`. |

---

## Dependency Graph — What Breaks When

```
PHASE A DELETIONS cascade like this:

useSession.ts DELETED
  └── App.tsx BREAKS (missing import + 12 destructured symbols)

ChatPanel.tsx DELETED
  └── App.tsx BREAKS (missing import + JSX)

StepCard.tsx DELETED
  └── ChatPanel.tsx already deleted (no cascade)

ThinkingDots.tsx DELETED
  ├── ChatPanel.tsx already deleted (no cascade)
  └── StepVisualizationModal.tsx BREAKS (missing import)
      → Fix: replace ThinkingDots with new ThinkingIndicator or inline spinner

types/index.ts GUTTED (ChatMessage, ThinkingState, SubStepEvent removed)
  ├── useAutoScroll.ts BREAKS (missing types) → Fix in Phase B
  ├── UserMessage.tsx BREAKS (missing type) → Fix in Phase B
  ├── SubStepList.tsx BREAKS (missing type) → Fix in Phase B
  ├── ActionCard.tsx BREAKS (missing StepEvent) → Fix in Phase B
  ├── useVisualization.ts BREAKS (missing StepEvent) → Fix in Phase B
  └── StepVisualizationModal.tsx BREAKS (missing StepEvent) → Fix in Phase B

orchestrator.py GUTTED
  └── session_manager.py expects run_orchestrator_session → Must rebuild before backend compiles
```

## New SSE Event Schema

| Event Type | Payload | When |
|------------|---------|------|
| `session.created` | `{session_id, thread_id}` | Session + thread initialized |
| `run.start` | `{run_id, alert, timestamp}` | Orchestrator run begins |
| `tool_call.start` | `{id, step, agent, query?, reasoning?, timestamp}` | Tool call initiated |
| `tool_call.complete` | `{id, step, agent, duration, query, response, error?, visualizations?, sub_steps?, is_action?, action?, reasoning?}` | Tool call finished |
| `message.start` | `{id}` | Final response streaming begins |
| `message.delta` | `{id, text}` | Token chunk |
| `message.complete` | `{id, text}` | Full final text |
| `run.complete` | `{steps, tokens, time}` | Run finished successfully |
| `error` | `{message, code?, recoverable?}` | Error |
| `status` | `{message}` | Informational |
| `done` | `{}` | Stream closed |
| `user_message` | `{text}` | User message logged (session-internal, for replay) |

## Task Index

| # | Task | File | Phase | Output |
|---|------|------|-------|--------|
| 01 | Scorched Earth — Delete & Gut | `strategy/task_01_scorched_earth.md` | A | `execution/task_01_scorched_earth_execution_log.md` |
| 02 | New Types & Reducer | `strategy/task_02_types_reducer.md` | B | `execution/task_02_types_reducer_execution_log.md` |
| 03 | Backend Event Emitter | `strategy/task_03_backend_events.md` | B | `execution/task_03_backend_events_execution_log.md` |
| 04 | Backend Session Integration | `strategy/task_04_backend_session.md` | B | `execution/task_04_backend_session_execution_log.md` |
| 05 | Frontend Streaming Hook | `strategy/task_05_streaming_hook.md` | B | `execution/task_05_streaming_hook_execution_log.md` |
| 06 | Frontend Components | `strategy/task_06_components.md` | B | `execution/task_06_components_execution_log.md` |
| 07 | Wiring & Verification | `strategy/task_07_wiring.md` | B | `execution/task_07_wiring_execution_log.md` |
