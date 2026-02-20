import { useState, useRef, useCallback } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { ChatMessage, ThinkingState, SessionDetail } from '../types';

export function useSession() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [thinking, setThinking] = useState<ThinkingState | null>(null);
  const [running, setRunning] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ---- Immutable state update targeting a specific orchestrator message by ID ----

  const updateOrchestratorMessage = useCallback((
    msgId: string, eventType: string, data: Record<string, unknown>
  ) => {
    setMessages(prev => prev.map(msg => {
      if (msg.id !== msgId) return msg;
      const updated = { ...msg };
      switch (eventType) {
        case 'step_thinking':
        case 'step_start':
          // Transient — drives ThinkingDots indicator, not stored on message
          updated.status = 'investigating';
          break;
        case 'step_started':
          // Add a pending step — agent + query known, no response yet
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
            s.step === (data as any).step
              ? { ...s, ...(data as any), pending: false }
              : s
          );
          updated.status = 'investigating';
          break;
        case 'step_complete':
          // If a pending step already exists for this step number, update it;
          // otherwise append (backward compat for replay & non-incremental path)
          if ((updated.steps ?? []).some(s => s.step === (data as any).step)) {
            updated.steps = (updated.steps ?? []).map(s =>
              s.step === (data as any).step
                ? { ...s, ...(data as any), pending: false }
                : s
            );
          } else {
            updated.steps = [...(updated.steps ?? []), data as any];
          }
          updated.status = 'investigating';
          break;
        case 'message':
          updated.diagnosis = data.text as string;
          updated.status = 'complete';
          break;
        case 'run_complete':
          updated.runMeta = data as any;
          updated.status = 'complete';
          break;
        case 'error':
          updated.errorMessage = data.message as string;
          updated.status = 'error';
          break;
        case 'action_executed':
          // action_executed is informational — the actual step data comes
          // via step_complete with is_action:true. No additional state update needed.
          break;
      }
      return updated;
    }));
  }, []);

  // ---- SSE connection ----

  const connectToStream = useCallback((sessionId: string, targetMsgId: string, since = 0) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRunning(true);

    const streamUrl = since > 0
      ? `/api/sessions/${sessionId}/stream?since=${since}`
      : `/api/sessions/${sessionId}/stream`;
    fetchEventSource(streamUrl, {
      signal: ctrl.signal,
      onmessage: (ev) => {
        if (!ev.event || !ev.data) return;
        try {
          const data = JSON.parse(ev.data);

          // Server sends 'done' when the turn is finished — close cleanly
          if (ev.event === 'done') {
            ctrl.abort();
            return;
          }

          // Update thinking state for live feedback
          if (ev.event === 'step_thinking') {
            setThinking({ agent: data.agent ?? 'Orchestrator', status: data.status ?? '' });
          } else if (ev.event === 'step_start') {
            setThinking({ agent: data.agent ?? '', status: 'processing...' });
          } else if (ev.event === 'step_started') {
            setThinking(null);  // Clear dots — the step card itself shows loading
          } else if (ev.event === 'step_response') {
            setThinking(null);
          } else if (ev.event === 'step_complete' || ev.event === 'message' || ev.event === 'run_complete') {
            setThinking(null);
          } else if (ev.event === 'action_executed') {
            setThinking(null);  // Clear thinking state — action executed
          }
          updateOrchestratorMessage(targetMsgId, ev.event, data);
        } catch (parseErr) {
          console.warn('Failed to parse SSE data:', ev.data, parseErr);
        }
      },
      onerror: () => {
        // Throw to prevent fetchEventSource from retrying.
        // The session persists server-side; the user can reconnect
        // via viewSession or by sending a follow-up.
        throw new Error('SSE closed');
      },
      openWhenHidden: true,
    }).catch(() => {
      // Expected — thrown by onerror to stop retries, or by abort
    }).finally(() => {
      setRunning(false);
      setThinking(null);
    });
  }, [updateOrchestratorMessage]);

  // ---- Create new session ----

  const createSession = useCallback(async (scenario: string, alertText: string) => {
    // Add user message immediately (optimistic)
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      text: alertText,
      timestamp: new Date().toISOString(),
    };
    setMessages([userMsg]);

    // Create session + start orchestrator
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario, alert_text: alertText }),
    });
    const { session_id } = await res.json();
    setActiveSessionId(session_id);

    // Add placeholder orchestrator message
    const orchMsgId = crypto.randomUUID();
    const orchMsg: ChatMessage = {
      id: orchMsgId,
      role: 'orchestrator',
      timestamp: new Date().toISOString(),
      steps: [],
      status: 'thinking',
    };
    setMessages(prev => [...prev, orchMsg]);

    // Connect SSE — events update the orchestrator message by ID
    connectToStream(session_id, orchMsgId);
  }, [connectToStream]);

  // ---- Send follow-up ----

  const sendFollowUp = useCallback(async (text: string) => {
    if (!activeSessionId) return;

    // Add user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      text,
      timestamp: new Date().toISOString(),
    };
    const orchMsgId = crypto.randomUUID();
    const orchMsg: ChatMessage = {
      id: orchMsgId,
      role: 'orchestrator',
      timestamp: new Date().toISOString(),
      steps: [],
      status: 'thinking',
    };
    setMessages(prev => [...prev, userMsg, orchMsg]);

    // POST follow-up to existing session
    const res = await fetch(`/api/sessions/${activeSessionId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const { event_offset = 0 } = await res.json();

    // Reconnect SSE starting from the new turn's events only
    connectToStream(activeSessionId, orchMsgId, event_offset);
  }, [activeSessionId, connectToStream]);

  // ---- New session (park current, clear UI) ----

  const handleNewSession = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setActiveSessionId(null);
    setRunning(false);
    setThinking(null);
  }, []);

  // ---- Delete session ----

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
      // If we're viewing the deleted session, clear the UI
      if (sessionId === activeSessionId) {
        abortRef.current?.abort();
        setMessages([]);
        setActiveSessionId(null);
        setRunning(false);
        setThinking(null);
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  }, [activeSessionId]);

  // ---- Cancel ----

  const cancelSession = useCallback(async () => {
    if (!activeSessionId) {
      abortRef.current?.abort();
      return;
    }
    await fetch(`/api/sessions/${activeSessionId}/cancel`, { method: 'POST' });
  }, [activeSessionId]);

  // ---- Reconstruct ChatMessage[] from a session's event_log ----

  const loadSessionMessages = useCallback((session: SessionDetail): ChatMessage[] => {
    const msgs: ChatMessage[] = [];
    let currentOrch: ChatMessage | null = null;

    for (const event of session.event_log) {
      const evType = event.event;
      const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;

      if (evType === 'user_message') {
        if (currentOrch) { msgs.push(currentOrch); currentOrch = null; }
        msgs.push({
          id: crypto.randomUUID(), role: 'user',
          text: data.text, timestamp: event.timestamp ?? session.created_at,
        });
      } else if (evType === 'run_start') {
        if (currentOrch) msgs.push(currentOrch);
        currentOrch = {
          id: crypto.randomUUID(), role: 'orchestrator',
          timestamp: data.timestamp ?? session.created_at,
          steps: [], status: 'complete',
        };
      } else if (currentOrch) {
        if (evType === 'step_complete') currentOrch.steps = [...(currentOrch.steps ?? []), data];
        else if (evType === 'message') currentOrch.diagnosis = data.text;
        else if (evType === 'run_complete') currentOrch.runMeta = data;
        else if (evType === 'error') { currentOrch.errorMessage = data.message; currentOrch.status = 'error'; }
        else if (evType === 'action_executed') {
          // action_executed is supplementary — step_complete already carries the data
          // No additional processing needed for replay
        }
      }
    }
    if (currentOrch) msgs.push(currentOrch);

    // If no user_message events (single-turn session), synthesise one
    if (msgs.length > 0 && msgs[0].role !== 'user') {
      msgs.unshift({
        id: crypto.randomUUID(), role: 'user',
        text: session.alert_text, timestamp: session.created_at,
      });
    }
    return msgs;
  }, []);

  // ---- View a past session ----

  const viewSession = useCallback(async (sessionId: string) => {
    abortRef.current?.abort();
    setRunning(false);
    setThinking(null);

    const res = await fetch(`/api/sessions/${sessionId}`);
    const session: SessionDetail = await res.json();
    setActiveSessionId(sessionId);
    const reconstructed = loadSessionMessages(session);
    setMessages(reconstructed);

    // If still running, connect to live stream targeting the last orch message
    if (session.status === 'in_progress') {
      const lastOrch = [...reconstructed].reverse().find((m: ChatMessage) => m.role === 'orchestrator');
      if (lastOrch) connectToStream(sessionId, lastOrch.id);
    }
  }, [loadSessionMessages, connectToStream]);

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
  };
}
