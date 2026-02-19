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
          updated.thinking = [...(updated.thinking ?? []), data.status as string];
          updated.status = 'thinking';
          break;
        case 'step_start':
          updated.status = 'investigating';
          break;
        case 'step_complete':
          updated.steps = [...(updated.steps ?? []), data as any];
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
      }
      return updated;
    }));
  }, []);

  // ---- SSE connection ----

  const connectToStream = useCallback((sessionId: string, targetMsgId: string) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRunning(true);

    fetchEventSource(`/api/sessions/${sessionId}/stream`, {
      signal: ctrl.signal,
      onmessage: (ev) => {
        if (!ev.event || !ev.data) return;
        try {
          const data = JSON.parse(ev.data);
          // Update thinking state for live feedback
          if (ev.event === 'step_thinking') {
            setThinking({ agent: data.agent ?? 'Orchestrator', status: data.status ?? '' });
          } else if (ev.event === 'step_start') {
            setThinking({ agent: data.agent ?? '', status: 'processing...' });
          } else if (ev.event === 'step_complete' || ev.event === 'message' || ev.event === 'run_complete') {
            setThinking(null);
          }
          updateOrchestratorMessage(targetMsgId, ev.event, data);
        } catch (parseErr) {
          console.warn('Failed to parse SSE data:', ev.data, parseErr);
        }
      },
      onerror: () => {
        // SSE dropped — session continues server-side
      },
      openWhenHidden: true,
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
    await fetch(`/api/sessions/${activeSessionId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });

    // Reconnect SSE for new events
    connectToStream(activeSessionId, orchMsgId);
  }, [activeSessionId, connectToStream]);

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
          steps: [], thinking: [], status: 'complete',
        };
      } else if (currentOrch) {
        if (evType === 'step_complete') currentOrch.steps = [...(currentOrch.steps ?? []), data];
        else if (evType === 'step_thinking') currentOrch.thinking = [...(currentOrch.thinking ?? []), data.status];
        else if (evType === 'message') currentOrch.diagnosis = data.text;
        else if (evType === 'run_complete') currentOrch.runMeta = data;
        else if (evType === 'error') { currentOrch.errorMessage = data.message; currentOrch.status = 'error'; }
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
  };
}
