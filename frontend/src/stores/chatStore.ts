/**
 * Chat store — manages messages, streaming state, and tool calls.
 *
 * State machine:
 *   IDLE → sendMessage/sendFollowUp → STREAMING → tokens arrive → IDLE/ERROR
 *                                          ↓
 *                                        abort() → IDLE
 *
 * Preserves all graph_main SSE event handling and rich ToolCall data model
 * (visualizations, sub-steps, action cards) while using Zustand for state.
 */

import { create } from 'zustand';
import type {
  Message,
  AssistantMessage,
  ToolCall,
} from '../types/conversation';
import type { SessionDetail, VisualizationData, ActionData, RunMeta } from '../types';
import { parseSSELines } from './sseParser';
import { replayEventLog } from '../utils/sessionReplay';
import { useSessionStore } from './sessionStore';

type ChatStatus = 'idle' | 'streaming' | 'error';

interface ChatState {
  // State
  messages: Message[];
  status: ChatStatus;
  error: string | null;

  // Internal
  _abortController: AbortController | null;
  _activeMsgId: string | null;

  // Actions
  createSession: (scenario: string, alertText: string) => Promise<void>;
  sendFollowUp: (text: string) => Promise<void>;
  viewSession: (sessionId: string) => Promise<void>;
  cancelSession: () => Promise<void>;
  saveSession: () => Promise<void>;
  abort: () => void;
  handleNewSession: () => void;
  clearChat: () => void;
}

// ---------------------------------------------------------------------------
// SSE event dispatcher — maps SSE events to state updates
// ---------------------------------------------------------------------------

function applySSEEvent(
  messages: Message[],
  msgId: string,
  event: string,
  data: Record<string, unknown>,
): { messages: Message[]; running?: boolean } {
  const updateAssistant = (
    fn: (msg: AssistantMessage) => AssistantMessage,
  ): Message[] =>
    messages.map((msg) =>
      msg.kind === 'assistant' && msg.id === msgId ? fn(msg) : msg,
    );

  switch (event) {
    case 'tool_call.start':
      return {
        messages: updateAssistant((msg) => ({
          ...msg,
          status: 'streaming',
          toolCalls: [
            ...msg.toolCalls,
            {
              id: data.id as string,
              step: data.step as number,
              agent: data.agent as string,
              query: (data.query as string) ?? '',
              reasoning: data.reasoning as string | undefined,
              status: 'running',
              timestamp: data.timestamp as string | undefined,
            },
          ],
        })),
      };

    case 'tool_call.complete': {
      const tcData: Partial<ToolCall> = {
        duration: data.duration as string,
        query: data.query as string,
        response: data.response as string,
        error: data.error as boolean | undefined,
        visualizations: data.visualizations as VisualizationData[] | undefined,
        isAction: data.is_action as boolean | undefined,
        action: data.action as ActionData | undefined,
        reasoning: data.reasoning as string | undefined,
        status: 'complete',
      };
      const subStepsRaw = data.sub_steps as
        | Array<{ index: number; query: string; result_summary: string; agent?: string }>
        | undefined;
      if (subStepsRaw) {
        tcData.subSteps = subStepsRaw.map((ss) => ({
          index: ss.index,
          query: ss.query,
          resultSummary: ss.result_summary,
          agent: ss.agent,
        }));
      }
      return {
        messages: updateAssistant((msg) => ({
          ...msg,
          toolCalls: msg.toolCalls.map((tc) =>
            tc.id === data.id ? { ...tc, ...tcData } : tc,
          ),
        })),
      };
    }

    case 'message.delta':
      return {
        messages: updateAssistant((msg) => ({
          ...msg,
          streamingContent: msg.streamingContent + (data.text as string),
          status: 'streaming',
        })),
      };

    case 'message.complete':
      return {
        messages: updateAssistant((msg) => ({
          ...msg,
          content: data.text as string,
          streamingContent: '',
          status: 'complete',
        })),
      };

    case 'run.complete':
      return {
        messages: updateAssistant((msg) => ({
          ...msg,
          runMeta: data as unknown as RunMeta,
          status: 'complete',
        })),
        running: false,
      };

    case 'error':
      return {
        messages: updateAssistant((msg) => ({
          ...msg,
          errorMessage: (data as { message: string }).message,
          status: 'error',
        })),
        running: false,
      };

    case 'status':
      return {
        messages: updateAssistant((msg) => ({
          ...msg,
          statusMessage: (data as { message: string }).message,
        })),
      };

    default:
      return { messages };
  }
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useChatStore = create<ChatState>((set, get) => {
  // ── SSE stream consumer ───────────────────────────────────

  async function connectToStream(
    sessionId: string,
    msgId: string,
    since?: number,
  ) {
    const ctrl = new AbortController();
    set({ status: 'streaming', _abortController: ctrl, _activeMsgId: msgId });

    try {
      const url =
        since != null
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
            set({ status: 'idle', _abortController: null, _activeMsgId: null });
            return;
          }
          try {
            const parsed = JSON.parse(data);
            const current = get();
            const result = applySSEEvent(current.messages, msgId, event, parsed);
            set({
              messages: result.messages,
              ...(result.running === false
                ? { status: 'idle', _abortController: null, _activeMsgId: null }
                : {}),
            });
          } catch {
            /* skip malformed events */
          }
        }
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return;
      console.warn('SSE stream error:', e);
    } finally {
      set({ status: 'idle', _abortController: null, _activeMsgId: null });
    }
  }

  return {
    messages: [],
    status: 'idle',
    error: null,
    _abortController: null,
    _activeMsgId: null,

    // ── Create a new session ──────────────────────────────────

    createSession: async (scenario: string, alertText: string) => {
      get()._abortController?.abort();
      const now = new Date().toISOString();
      const userMsgId = crypto.randomUUID();
      const asstMsgId = crypto.randomUUID();

      set({
        messages: [
          {
            kind: 'user',
            id: userMsgId,
            text: alertText,
            timestamp: now,
          },
          {
            kind: 'assistant',
            id: asstMsgId,
            timestamp: now,
            toolCalls: [],
            content: '',
            streamingContent: '',
            status: 'pending',
          },
        ],
        status: 'streaming',
        error: null,
      });

      try {
        const sessionId = await useSessionStore
          .getState()
          .createSession(scenario, alertText);
        connectToStream(sessionId, asstMsgId);
      } catch (e) {
        set((s) => ({
          ...s,
          status: 'error',
          error: e instanceof Error ? e.message : 'Failed to create session',
          messages: s.messages.map((msg) =>
            msg.kind === 'assistant' && msg.id === asstMsgId
              ? {
                  ...msg,
                  errorMessage:
                    e instanceof Error ? e.message : 'Failed to create session',
                  status: 'error' as const,
                }
              : msg,
          ),
        }));
      }
    },

    // ── Send a follow-up message ──────────────────────────────

    sendFollowUp: async (text: string) => {
      const sessionId = useSessionStore.getState().activeSessionId;
      if (!sessionId) return;

      const now = new Date().toISOString();
      const userMsgId = crypto.randomUUID();
      const asstMsgId = crypto.randomUUID();

      set((s) => ({
        messages: [
          ...s.messages,
          { kind: 'user' as const, id: userMsgId, text, timestamp: now },
          {
            kind: 'assistant' as const,
            id: asstMsgId,
            timestamp: now,
            toolCalls: [],
            content: '',
            streamingContent: '',
            status: 'pending' as const,
          },
        ],
        status: 'streaming',
        error: null,
      }));

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
        set((s) => ({
          ...s,
          status: 'error',
          error: e instanceof Error ? e.message : 'Failed to send follow-up',
          messages: s.messages.map((msg) =>
            msg.kind === 'assistant' && msg.id === asstMsgId
              ? {
                  ...msg,
                  errorMessage:
                    e instanceof Error ? e.message : 'Failed to send follow-up',
                  status: 'error' as const,
                }
              : msg,
          ),
        }));
      }
    },

    // ── View an existing session (replay from Cosmos / memory) ──

    viewSession: async (sessionId: string) => {
      get()._abortController?.abort();
      useSessionStore.getState().selectSession(sessionId);

      set({ messages: [], status: 'idle', error: null });

      try {
        const res = await fetch(`/api/sessions/${sessionId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const session: SessionDetail = await res.json();
        const messages = replayEventLog(session);
        set({ messages });

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

    // ── Cancel a running session ──────────────────────────────

    cancelSession: async () => {
      const sessionId = useSessionStore.getState().activeSessionId;
      if (!sessionId) return;
      try {
        await fetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' });
      } catch { /* best effort */ }
    },

    // ── Save a session to Cosmos ──────────────────────────────

    saveSession: async () => {
      const sessionId = useSessionStore.getState().activeSessionId;
      if (!sessionId) return;
      try {
        await fetch(`/api/sessions/${sessionId}/save`, { method: 'POST' });
      } catch { /* best effort */ }
    },

    // ── Abort streaming ───────────────────────────────────────

    abort: () => {
      const { _abortController } = get();
      if (_abortController) {
        _abortController.abort();
      }
      set({ status: 'idle', _abortController: null, _activeMsgId: null });
      // Also cancel on the server
      const sessionId = useSessionStore.getState().activeSessionId;
      if (sessionId) {
        fetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' }).catch(
          () => {},
        );
      }
    },

    // ── Start a new (empty) session ───────────────────────────

    handleNewSession: () => {
      get()._abortController?.abort();
      useSessionStore.getState().clearActive();
      set({
        messages: [],
        status: 'idle',
        error: null,
        _abortController: null,
        _activeMsgId: null,
      });
    },

    // ── Clear all state ───────────────────────────────────────

    clearChat: () =>
      set({
        messages: [],
        status: 'idle',
        error: null,
        _abortController: null,
        _activeMsgId: null,
      }),
  };
});
