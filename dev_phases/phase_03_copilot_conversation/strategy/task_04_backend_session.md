# Task 04: Backend Session Integration

> **Phase**: B (Rebuild)
> **Prerequisite**: Task 03 (backend event emitter)
> **Output**: `execution/task_04_backend_session_execution_log.md`

## Goal

Update `session_manager.py` and `routers/sessions.py` to work with the new event types from Task 03. Verify the full backend compiles and the event flow is correct.

## Files to Modify

### `api/app/session_manager.py`

The event type string references in `start()` and `continue_session()` were already updated in Task 01 Step 6. Verify they match the actual events emitted by the new `run_orchestrator_session()`:

| Session field | Event type to check | Data extraction |
|--------------|-------------------|-----------------|
| `session.steps` | `tool_call.complete` | `data` (full tool call payload) |
| `session.diagnosis` | `message.complete` | `data.get("text", "")` |
| `session.run_meta` | `run.complete` | `data` |
| `session.error_detail` | `error` | `data.get("message", "")` |
| `session.thread_id` | `session.created` | `data.get("thread_id")` |

Also verify:
- The `user_message` event pushed in `start()` and `continue_session()` is unchanged (it's a session-internal event, not part of the SSE protocol).
- `_finalize_turn()` logic is event-type-agnostic — no changes needed.
- `_persist_to_cosmos()` is event-type-agnostic — no changes needed.

### `api/app/routers/sessions.py`

The `status_change` → `status` rename was done in Task 01 Step 6. Verify:
- SSE stream handler (`GET /api/sessions/{id}/stream`) correctly serializes dotted event names.
- Cancel endpoint emits `{"event": "status", "data": ...}` instead of `{"event": "status_change", "data": ...}`.

Test that `sse_starlette.EventSourceResponse` handles dotted event names (`tool_call.start`, `message.delta`, etc.). If it doesn't, add a note and use underscores instead.

### `api/app/sessions.py`

Minimal changes:
- Verify docstrings don't reference old event types.
- `to_dict()` output is unchanged (event_log is stored as-is).

## Verification

```bash
# All Python files compile
python3 -m py_compile api/app/orchestrator.py
python3 -m py_compile api/app/sessions.py
python3 -m py_compile api/app/session_manager.py
python3 -m py_compile api/app/routers/sessions.py
python3 -m py_compile api/app/main.py

# Verify the import chain works
python3 -c "from app.session_manager import session_manager; print('OK')"
```

## Completion Criteria

- [ ] `session_manager.py` event type strings match new schema
- [ ] `routers/sessions.py` uses `status` instead of `status_change`
- [ ] SSE endpoint verified to handle dotted event names
- [ ] All 5 Python files compile
- [ ] Import chain works end-to-end
