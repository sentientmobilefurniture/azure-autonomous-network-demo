# Task 05: Frontend Streaming Hook

> **Phase**: B (Rebuild)
> **Prerequisite**: Task 02 (types & reducer)
> **Output**: `execution/task_05_streaming_hook_execution_log.md`

## Goal

Create `useConversation.ts` — the single hook that owns all conversation state and SSE streaming. Replaces `useSession.ts`.

## File to Create

### `frontend/src/hooks/useConversation.ts`

## Design

```typescript
export function useConversation() {
  const [state, dispatch] = useReducer(conversationReducer, initialState);
  const abortRef = useRef<AbortController | null>(null);
  // Track the current assistant message ID for event dispatch
  const activeMsgIdRef = useRef<string | null>(null);

  return {
    // State
    messages: state.messages,
    running: state.running,
    activeSessionId: state.activeSessionId,

    // Actions
    createSession,
    sendFollowUp,
    viewSession,
    cancelSession,
    handleNewSession,
    deleteSession,
    saveSession,
  };
}
```

## SSE Parser

Native `ReadableStream` + manual SSE line parsing. No external library.

```typescript
function parseSSELines(buffer: string): { events: Array<{event: string; data: string}>; remainder: string } {
  const events: Array<{event: string; data: string}> = [];
  const lines = buffer.split('\n');
  let currentEvent = '';
  let currentData = '';
  let remainder = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7).trim();
    } else if (line.startsWith('data: ')) {
      currentData = line.slice(6);
    } else if (line === '' && currentEvent) {
      events.push({ event: currentEvent, data: currentData });
      currentEvent = '';
      currentData = '';
    } else if (i === lines.length - 1 && line !== '') {
      // Incomplete line — keep as remainder for next chunk
      remainder = line;
    }
  }

  // If we have a partial event at the end (event set but no blank line yet)
  if (currentEvent) {
    // Put it back as remainder
    remainder = `event: ${currentEvent}\n` + (currentData ? `data: ${currentData}\n` : '') + remainder;
  }

  return { events, remainder };
}
```

## Event → Action Mapping

```typescript
function dispatchSSEEvent(
  dispatch: Dispatch<ConversationAction>,
  msgId: string,
  event: string,
  data: Record<string, unknown>,
) {
  switch (event) {
    case 'tool_call.start':
      dispatch({
        type: 'TOOL_CALL_START',
        payload: {
          messageId: msgId,
          toolCall: {
            id: data.id as string,
            step: data.step as number,
            agent: data.agent as string,
            query: (data.query as string) ?? '',
            reasoning: data.reasoning as string | undefined,
            status: 'running',
            timestamp: data.timestamp as string | undefined,
          },
        },
      });
      break;

    case 'tool_call.complete':
      dispatch({
        type: 'TOOL_CALL_COMPLETE',
        payload: {
          messageId: msgId,
          toolCallId: data.id as string,
          data: {
            duration: data.duration as string,
            query: data.query as string,
            response: data.response as string,
            error: data.error as boolean | undefined,
            visualizations: data.visualizations as any[] | undefined,
            subSteps: (data.sub_steps as any[])?.map(ss => ({
              index: ss.index, query: ss.query,
              resultSummary: ss.result_summary, agent: ss.agent,
            })),
            isAction: data.is_action as boolean | undefined,
            action: data.action as any | undefined,
            reasoning: data.reasoning as string | undefined,
          },
        },
      });
      break;

    case 'message.start':
      // No state change needed — deltas accumulate on streaming content
      break;

    case 'message.delta':
      dispatch({
        type: 'MESSAGE_DELTA',
        payload: { messageId: msgId, text: data.text as string },
      });
      break;

    case 'message.complete':
      dispatch({
        type: 'MESSAGE_COMPLETE',
        payload: { messageId: msgId, text: data.text as string },
      });
      break;

    case 'run.complete':
      dispatch({
        type: 'RUN_COMPLETE',
        payload: {
          messageId: msgId,
          runMeta: data as { steps: number; tokens: number; time: string },
        },
      });
      break;

    case 'error':
      dispatch({
        type: 'ERROR',
        payload: { messageId: msgId, message: data.message as string },
      });
      break;

    case 'status':
      dispatch({
        type: 'STATUS',
        payload: { messageId: msgId, message: data.message as string },
      });
      break;

    case 'done':
      // Stream closed — no dispatch needed
      break;
  }
}
```

## Methods

### `connectToStream(sessionId, msgId, since?)`

```typescript
async function connectToStream(sessionId: string, msgId: string, since?: number) {
  abortRef.current?.abort();
  const ctrl = new AbortController();
  abortRef.current = ctrl;
  dispatch({ type: 'SET_RUNNING', payload: true });
  activeMsgIdRef.current = msgId;

  try {
    const url = since
      ? `/api/sessions/${sessionId}/stream?since=${since}`
      : `/api/sessions/${sessionId}/stream`;
    const response = await fetch(url, { signal: ctrl.signal });
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const { events, remainder } = parseSSELines(buffer);
      buffer = remainder;

      for (const { event, data } of events) {
        if (event === 'done') { ctrl.abort(); return; }
        try {
          const parsed = JSON.parse(data);
          dispatchSSEEvent(dispatch, msgId, event, parsed);
        } catch { /* skip malformed */ }
      }
    }
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return;
    console.warn('SSE stream error:', e);
  } finally {
    dispatch({ type: 'SET_RUNNING', payload: false });
    activeMsgIdRef.current = null;
  }
}
```

### `createSession(scenario, alertText)`

POST `/api/sessions` → dispatch user msg + assistant msg → connect SSE.

### `sendFollowUp(text)`

POST `/api/sessions/{id}/message` → dispatch user msg + assistant msg → reconnect SSE with `since` offset.

### `viewSession(sessionId)`

GET `/api/sessions/{id}` → replay event_log into messages → if in_progress, connect SSE.

### `handleNewSession()`, `deleteSession()`, `cancelSession()`, `saveSession()`

Same behavior as old hook, but using `dispatch({ type: 'CLEAR' })` etc.

## Session Replay (`viewSession`)

Reconstruct `Message[]` from `event_log` using the new event types:

```typescript
function replayEventLog(session: SessionDetail): Message[] {
  const msgs: Message[] = [];
  let current: AssistantMessage | null = null;

  for (const event of session.event_log) {
    const evType = event.event;
    const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;

    switch (evType) {
      case 'user_message':
        if (current) { msgs.push(current); current = null; }
        msgs.push({ kind: 'user', id: crypto.randomUUID(), text: data.text, timestamp: event.timestamp ?? session.created_at });
        break;

      case 'run.start':
        if (current) msgs.push(current);
        current = { kind: 'assistant', id: crypto.randomUUID(), timestamp: event.timestamp ?? session.created_at, toolCalls: [], content: '', streamingContent: '', status: 'complete' };
        break;

      case 'tool_call.complete':
        if (current) {
          current.toolCalls.push({
            id: data.id, step: data.step, agent: data.agent, query: data.query ?? '',
            status: 'complete', duration: data.duration, response: data.response,
            error: data.error, visualizations: data.visualizations,
            subSteps: data.sub_steps?.map((ss: any) => ({ index: ss.index, query: ss.query, resultSummary: ss.result_summary, agent: ss.agent })),
            isAction: data.is_action, action: data.action, reasoning: data.reasoning,
          });
        }
        break;

      case 'message.complete':
        if (current) current.content = data.text;
        break;

      case 'run.complete':
        if (current) current.runMeta = data;
        break;

      case 'error':
        if (current) { current.errorMessage = data.message; current.status = 'error'; }
        break;
    }
  }
  if (current) msgs.push(current);

  // Synthesize user message if missing
  if (msgs.length > 0 && msgs[0].kind !== 'user') {
    msgs.unshift({ kind: 'user', id: crypto.randomUUID(), text: session.alert_text, timestamp: session.created_at });
  }
  return msgs;
}
```

## Completion Criteria

- [ ] `useConversation.ts` created
- [ ] SSE parser handles chunked data, partial lines, and multi-line events
- [ ] All event types dispatched to correct reducer actions
- [ ] `createSession`, `sendFollowUp`, `viewSession` work
- [ ] `cancelSession`, `deleteSession`, `saveSession`, `handleNewSession` work
- [ ] Session replay reconstructs messages from new event_log
- [ ] `AbortController` properly cancels on unmount/new session
- [ ] No dependency on `@microsoft/fetch-event-source`
