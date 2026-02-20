import { useReducer, useRef, useCallback } from 'react';
import { conversationReducer, initialState } from '../reducers/conversationReducer';
import type {
  ConversationAction,
  Message,
  AssistantMessage,
} from '../types/conversation';
import type { SessionDetail, VisualizationData, ActionData, RunMeta } from '../types';

// ---------------------------------------------------------------------------
// SSE line parser — handles chunked data and partial lines
// ---------------------------------------------------------------------------

function parseSSELines(buffer: string): {
  events: Array<{ event: string; data: string }>;
  remainder: string;
} {
  const events: Array<{ event: string; data: string }> = [];
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
    remainder =
      `event: ${currentEvent}\n` +
      (currentData ? `data: ${currentData}\n` : '') +
      remainder;
  }

  return { events, remainder };
}

// ---------------------------------------------------------------------------
// Event → reducer action dispatcher
// ---------------------------------------------------------------------------

function dispatchSSEEvent(
  dispatch: React.Dispatch<ConversationAction>,
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
            visualizations: data.visualizations as VisualizationData[] | undefined,
            subSteps: (data.sub_steps as Array<{
              index: number;
              query: string;
              result_summary: string;
              agent?: string;
            }>)?.map((ss) => ({
              index: ss.index,
              query: ss.query,
              resultSummary: ss.result_summary,
              agent: ss.agent,
            })),
            isAction: data.is_action as boolean | undefined,
            action: data.action as ActionData | undefined,
            reasoning: data.reasoning as string | undefined,
          },
        },
      });
      break;

    case 'message.start':
      // No state change needed — deltas accumulate on streamingContent
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
          runMeta: data as unknown as RunMeta,
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

// ---------------------------------------------------------------------------
// Session replay — reconstruct Message[] from event_log
// ---------------------------------------------------------------------------

function replayEventLog(session: SessionDetail): Message[] {
  const msgs: Message[] = [];
  let current: AssistantMessage | null = null;

  for (const event of session.event_log) {
    const evType = event.event;
    const data =
      typeof event.data === 'string' ? JSON.parse(event.data) : event.data;

    switch (evType) {
      case 'user_message':
        if (current) {
          msgs.push(current);
          current = null;
        }
        msgs.push({
          kind: 'user',
          id: crypto.randomUUID(),
          text: (data as { text: string }).text,
          timestamp: event.timestamp ?? session.created_at,
        });
        break;

      case 'run.start':
        if (current) msgs.push(current);
        current = {
          kind: 'assistant',
          id: crypto.randomUUID(),
          timestamp: event.timestamp ?? session.created_at,
          toolCalls: [],
          content: '',
          streamingContent: '',
          status: 'complete',
        };
        break;

      case 'tool_call.complete': {
        if (!current) break;
        const tc = data as Record<string, unknown>;
        const subStepsRaw = tc.sub_steps as
          | Array<{
              index: number;
              query: string;
              result_summary: string;
              agent?: string;
            }>
          | undefined;
        current.toolCalls.push({
          id: tc.id as string,
          step: tc.step as number,
          agent: tc.agent as string,
          query: (tc.query as string) ?? '',
          status: 'complete',
          duration: tc.duration as string | undefined,
          response: tc.response as string | undefined,
          error: tc.error as boolean | undefined,
          visualizations: tc.visualizations as VisualizationData[] | undefined,
          subSteps: subStepsRaw?.map((ss) => ({
            index: ss.index,
            query: ss.query,
            resultSummary: ss.result_summary,
            agent: ss.agent,
          })),
          isAction: tc.is_action as boolean | undefined,
          action: tc.action as ActionData | undefined,
          reasoning: tc.reasoning as string | undefined,
        });
        break;
      }

      case 'message.complete':
        if (current) current.content = (data as { text: string }).text;
        break;

      case 'run.complete':
        if (current) current.runMeta = data as RunMeta;
        break;

      case 'error':
        if (current) {
          current.errorMessage = (data as { message: string }).message;
          current.status = 'error';
        }
        break;
    }
  }

  if (current) msgs.push(current);

  // Synthesize user message if event_log started without one
  if (msgs.length > 0 && msgs[0].kind !== 'user') {
    msgs.unshift({
      kind: 'user',
      id: crypto.randomUUID(),
      text: session.alert_text,
      timestamp: session.created_at,
    });
  }

  return msgs;
}

// ---------------------------------------------------------------------------
// useConversation — main hook
// ---------------------------------------------------------------------------

export function useConversation() {
  const [state, dispatch] = useReducer(conversationReducer, initialState);
  const abortRef = useRef<AbortController | null>(null);
  const activeMsgIdRef = useRef<string | null>(null);

  // ── SSE stream consumer ─────────────────────────────────────

  const connectToStream = useCallback(
    async (sessionId: string, msgId: string, since?: number) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      dispatch({ type: 'SET_RUNNING', payload: true });
      activeMsgIdRef.current = msgId;

      try {
        const url = since != null
          ? `/api/sessions/${sessionId}/stream?since=${since}`
          : `/api/sessions/${sessionId}/stream`;
        const response = await fetch(url, { signal: ctrl.signal });
        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`);
        }

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
            if (event === 'done') {
              ctrl.abort();
              return;
            }
            try {
              const parsed = JSON.parse(data);
              dispatchSSEEvent(dispatch, msgId, event, parsed);
            } catch {
              /* skip malformed events */
            }
          }
        }
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return;
        console.warn('SSE stream error:', e);
      } finally {
        dispatch({ type: 'SET_RUNNING', payload: false });
        activeMsgIdRef.current = null;
      }
    },
    [],
  );

  // ── Create a new session ────────────────────────────────────

  const createSession = useCallback(
    async (scenario: string, alertText: string) => {
      abortRef.current?.abort();
      dispatch({ type: 'CLEAR' });

      const now = new Date().toISOString();
      const userMsgId = crypto.randomUUID();
      const asstMsgId = crypto.randomUUID();

      dispatch({
        type: 'ADD_USER_MESSAGE',
        payload: { id: userMsgId, text: alertText, timestamp: now },
      });
      dispatch({
        type: 'ADD_ASSISTANT_MESSAGE',
        payload: { id: asstMsgId, timestamp: now },
      });

      try {
        const res = await fetch('/api/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ scenario, alert_text: alertText }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json();
        const sessionId = body.session_id;
        dispatch({ type: 'SET_SESSION', payload: { sessionId } });
        connectToStream(sessionId, asstMsgId);
      } catch (e) {
        dispatch({
          type: 'ERROR',
          payload: {
            messageId: asstMsgId,
            message: e instanceof Error ? e.message : 'Failed to create session',
          },
        });
      }
    },
    [connectToStream],
  );

  // ── Send a follow-up message ────────────────────────────────

  const sendFollowUp = useCallback(
    async (text: string) => {
      const sessionId = state.activeSessionId;
      if (!sessionId) return;

      const now = new Date().toISOString();
      const userMsgId = crypto.randomUUID();
      const asstMsgId = crypto.randomUUID();

      dispatch({
        type: 'ADD_USER_MESSAGE',
        payload: { id: userMsgId, text, timestamp: now },
      });
      dispatch({
        type: 'ADD_ASSISTANT_MESSAGE',
        payload: { id: asstMsgId, timestamp: now },
      });

      try {
        const res = await fetch(`/api/sessions/${sessionId}/message`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json();
        const eventOffset = body.event_offset as number | undefined;
        connectToStream(sessionId, asstMsgId, eventOffset);
      } catch (e) {
        dispatch({
          type: 'ERROR',
          payload: {
            messageId: asstMsgId,
            message: e instanceof Error ? e.message : 'Failed to send follow-up',
          },
        });
      }
    },
    [state.activeSessionId, connectToStream],
  );

  // ── View an existing session (replay from Cosmos / memory) ──

  const viewSession = useCallback(
    async (sessionId: string) => {
      abortRef.current?.abort();
      dispatch({ type: 'CLEAR' });
      dispatch({ type: 'SET_SESSION', payload: { sessionId } });

      try {
        const res = await fetch(`/api/sessions/${sessionId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const session: SessionDetail = await res.json();
        const messages = replayEventLog(session);
        dispatch({ type: 'SET_MESSAGES', payload: messages });

        // If the session is still running, connect to live stream
        if (session.status === 'in_progress') {
          const lastAsst = [...messages]
            .reverse()
            .find((m): m is AssistantMessage => m.kind === 'assistant');
          const msgId = lastAsst?.id ?? crypto.randomUUID();
          connectToStream(sessionId, msgId, session.event_log.length);
        }
      } catch (e) {
        console.warn('Failed to load session:', e);
      }
    },
    [connectToStream],
  );

  // ── Cancel a running session ────────────────────────────────

  const cancelSession = useCallback(async () => {
    const sessionId = state.activeSessionId;
    if (!sessionId) return;
    try {
      await fetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' });
    } catch {
      /* best effort */
    }
  }, [state.activeSessionId]);

  // ── Start a new (empty) session ─────────────────────────────

  const handleNewSession = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: 'CLEAR' });
  }, []);

  // ── Delete a session ────────────────────────────────────────

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
      } catch {
        /* best effort */
      }
      // If we're viewing this session, clear the conversation
      if (state.activeSessionId === sessionId) {
        dispatch({ type: 'CLEAR' });
      }
    },
    [state.activeSessionId],
  );

  // ── Save a session to Cosmos ────────────────────────────────

  const saveSession = useCallback(async () => {
    const sessionId = state.activeSessionId;
    if (!sessionId) return;
    try {
      await fetch(`/api/sessions/${sessionId}/save`, { method: 'POST' });
    } catch {
      /* best effort */
    }
  }, [state.activeSessionId]);

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
