# Task 07: Wiring & Verification

> **Phase**: B (Rebuild)
> **Prerequisite**: Tasks 02–06 all complete
> **Output**: `execution/task_07_wiring_execution_log.md`

## Goal

Wire everything together in `App.tsx`. After this task, the app compiles, builds, and the full conversation flow works end-to-end.

## Files to Modify

### `frontend/src/App.tsx`

Restore the conversation UI that was replaced with a placeholder in Task 01:

1. **Replace imports**:
   ```tsx
   // OLD (deleted)
   import { useSession } from './hooks/useSession';
   import { ChatPanel } from './components/ChatPanel';

   // NEW
   import { useConversation } from './hooks/useConversation';
   import { ConversationPanel } from './components/ConversationPanel';
   ```

2. **Replace hook usage**:
   ```tsx
   // OLD
   const { messages, thinking, running, activeSessionId, partial, createSession, ... } = useSession();

   // NEW
   const { messages, running, activeSessionId, createSession, sendFollowUp, viewSession, cancelSession, handleNewSession, deleteSession, saveSession } = useConversation();
   ```

3. **Update `useAutoScroll`**:
   ```tsx
   // OLD
   const { isNearBottom, scrollToBottom, scrollRef } = useAutoScroll(messages, thinking);

   // NEW
   const { isNearBottom, scrollToBottom, scrollRef } = useAutoScroll(messages);
   ```

4. **Replace chat section JSX**:
   Remove the placeholder div, restore:
   ```tsx
   <div className="flex-1 min-h-0 flex flex-col">
     <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto">
       <ConversationPanel
         messages={messages}
         onSave={saveSession}
       />
     </div>
     <ChatInput
       onSubmit={handleSubmit}
       onCancel={cancelSession}
       running={running}
       exampleQuestions={SCENARIO.exampleQuestions}
     />
   </div>
   ```

5. **Restore session sidebar** (uncomment if commented in Task 01).

6. **Remove `partial` prop** — no longer needed (old Cosmos sessions won't be replayed).

7. **Restore `useSessions` hook** and refetch logic.

### `frontend/src/hooks/useAutoScroll.ts`

Verify it works with the updated `Message[]` type (done in Task 02). If the second parameter (`currentThinking`) was removed, update the scroll trigger to watch `messages` length and the last assistant message's `status` field.

### `frontend/package.json`

Verify `@microsoft/fetch-event-source` was removed in Task 01. Run `npm install` to clean `node_modules`.

## Verification Checklist

### TypeScript

```bash
cd frontend && npx tsc --noEmit
```
**Expected**: 0 errors.

### Python

```bash
python3 -m py_compile api/app/orchestrator.py
python3 -m py_compile api/app/sessions.py
python3 -m py_compile api/app/session_manager.py
python3 -m py_compile api/app/routers/sessions.py
python3 -m py_compile api/app/main.py
```
**Expected**: All pass.

### Build

```bash
cd frontend && npm run build
```
**Expected**: Builds without errors.

### Dead Code Scan

```bash
# No references to deleted files
grep -r "useSession\|ChatPanel\|StepCard\|ThinkingDots" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v ".d.ts"

# No references to old event types in frontend
grep -r "step_thinking\|step_started\|step_response\|step_complete\|sub_step_complete\|action_executed\|status_change\|message_delta" frontend/src/ --include="*.ts" --include="*.tsx"

# No references to old event types in backend
grep -r "step_thinking\|step_started\|step_response\|step_complete\|sub_step_complete\|action_executed\|status_change\|message_delta" api/app/ --include="*.py" | grep -v __pycache__

# No references to old types
grep -r "ChatMessage\|ChatRole\|ThinkingState\|SubStepEvent" frontend/src/ --include="*.ts" --include="*.tsx"

# fetch-event-source gone
grep -r "fetch-event-source" frontend/ --include="*.json" --include="*.ts"
```
**Expected**: All searches return empty.

### Smoke Test (if environment available)

```bash
# Start frontend dev server
cd frontend && npm run dev &

# Start API
cd api && uvicorn app.main:app --port 8000 &

# Create a session and verify events
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"scenario": "test", "alert_text": "test alert"}'
```

## Completion Criteria

- [ ] `App.tsx` uses `useConversation` + `ConversationPanel`
- [ ] `useAutoScroll` works with new `Message[]` type
- [ ] `npx tsc --noEmit` — 0 errors
- [ ] `npm run build` — succeeds
- [ ] All Python files compile
- [ ] Dead code scan — no references to old code
- [ ] `@microsoft/fetch-event-source` fully removed
- [ ] No TODO/FIXME placeholders from the refactor
