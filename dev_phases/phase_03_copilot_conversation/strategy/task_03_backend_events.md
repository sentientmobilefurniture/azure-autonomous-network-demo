# Task 03: Backend Event Emitter

> **Phase**: B (Rebuild)
> **Prerequisite**: Task 01 (orchestrator gutted to stubs)
> **Output**: `execution/task_03_backend_events_execution_log.md`

## Goal

Rebuild `api/app/orchestrator.py` with a single unified `SSEEventHandler` class and a single orchestrator entry point. The handler emits the new SSE event schema.

## File to Modify

`api/app/orchestrator.py` — replace the stubs from Task 01 with the new implementation.

## Architecture

```
orchestrator.py
├── Config helpers (KEPT from Task 01)
│   ├── is_configured()
│   ├── _load_orchestrator_id()
│   ├── _load_agent_names()
│   ├── _get_project_client()
│   └── _get_credential()
│
├── SSEEventHandler (NEW — single class)
│   ├── on_thread_run(run) — tracks run status, token usage
│   ├── on_run_step(step) — emits tool_call.start / tool_call.complete
│   ├── on_message_delta(delta) — emits message.delta (with message.start on first chunk)
│   ├── on_error(data) — emits error
│   ├── _resolve_agent_name(tc) — KEPT, maps tool call → display name
│   ├── _extract_arguments(tc) — KEPT, parses query + reasoning
│   └── _parse_structured_output(agent, raw) — KEPT, parses summary/viz/substeps
│
├── _run_in_thread() (NEW — single thread target)
│   ├── Creates or reuses Foundry thread
│   ├── Sets up FunctionTool (dispatch_field_engineer)
│   ├── Runs agent with retry logic (MAX_RUN_ATTEMPTS=2)
│   ├── Emits: run.start, session.created, message.start, message.complete, run.complete, error
│   └── Supports cancel_event for session cancellation
│
└── run_orchestrator_session() (NEW — single async generator)
    ├── Accepts: alert_text, cancel_event, existing_thread_id
    ├── Bridges _run_in_thread via asyncio.Queue
    └── Yields SSE event dicts
```

**Elimination of `run_orchestrator()`**: The old standalone `run_orchestrator()` (used by the deleted `alert.py` router) is no longer needed. Only `run_orchestrator_session()` remains.

## Event Emission Mapping

| Handler callback | Old events | New events |
|-----------------|-----------|------------|
| `on_run_step(status=in_progress)` | `step_thinking` + `step_started` | `tool_call.start` |
| `on_run_step(status=completed)` | `step_response` + `step_complete` + `sub_step_complete` + `action_executed` | `tool_call.complete` (includes sub_steps, action, viz in payload) |
| `on_run_step(status=failed)` | `step_response(error)` + `step_complete(error)` | `tool_call.complete` with `error: true` |
| `on_message_delta` | `message_delta` | `message.start` (first chunk only) + `message.delta` |
| `_run_in_thread` (success) | `run_start` + `message` + `run_complete` | `run.start` + `message.complete` + `run.complete` |
| `_run_in_thread` (thread created) | `thread_created` | `session.created` |
| `_run_in_thread` (error) | `error` | `error` |

## Key Design Decisions

1. **tool_call IDs**: Generate a UUID for each tool call in `on_run_step(in_progress)`. Store in `_pending_steps[step_id][tc_id]["tool_call_id"]`. Use this stable ID in both `tool_call.start` and `tool_call.complete`.

2. **message IDs**: Generate a UUID when the first `message_delta` arrives. Emit `message.start` with this ID, then use it in all subsequent `message.delta` and `message.complete` events.

3. **Sub-steps bundled**: Sub-steps are included in the `tool_call.complete` payload as `sub_steps: [...]`. No separate `sub_step_complete` events.

4. **No `step_thinking`**: The `tool_call.start` event replaces both `step_thinking` and `step_started`. If tool call details aren't available yet (rare fallback), emit `status` instead.

5. **Cancel support**: `cancel_event` is checked between retry attempts in `_run_in_thread`. If set, emit `status` with "Cancelling..." and break.

## Completion Criteria

- [ ] Single `SSEEventHandler` class (no duplication)
- [ ] Single `run_orchestrator_session()` entry point
- [ ] `run_orchestrator()` removed (no callers remain)
- [ ] All new event types emitted correctly
- [ ] FunctionTool (dispatch_field_engineer) still auto-executes
- [ ] Retry logic preserved (MAX_RUN_ATTEMPTS=2)
- [ ] Cancel support works
- [ ] `python3 -m py_compile api/app/orchestrator.py` passes
- [ ] `is_configured()` and config helpers unchanged
