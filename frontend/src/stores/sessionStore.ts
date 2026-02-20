/**
 * Session store — manages session list and active session.
 *
 * Zustand store with async actions that call the backend REST API.
 * Sessions are listed on mount; individual sessions are loaded on selection.
 */

import { create } from 'zustand';
import type { SessionSummary } from '../types';

interface SessionState {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading: boolean;

  fetchSessions: () => Promise<void>;
  createSession: (scenario: string, alertText: string) => Promise<string>;
  selectSession: (id: string) => void;
  deleteSession: (id: string) => Promise<void>;
  clearActive: () => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  loading: false,

  fetchSessions: async () => {
    set({ loading: true });
    try {
      const res = await fetch('/api/sessions');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      set({ sessions: data.sessions ?? [], loading: false });
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
      set({ loading: false });
    }
  },

  createSession: async (scenario: string, alertText: string) => {
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario, alert_text: alertText }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    const sessionId = body.session_id as string;
    set({ activeSessionId: sessionId });
    // Refresh session list in background
    get().fetchSessions();
    return sessionId;
  },

  selectSession: (id: string) => {
    set({ activeSessionId: id });
  },

  deleteSession: async (id: string) => {
    try {
      await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
    } catch { /* best effort */ }
    const { activeSessionId } = get();
    set((s) => ({
      sessions: s.sessions.filter((sess) => sess.id !== id),
      ...(activeSessionId === id ? { activeSessionId: null } : {}),
    }));
  },

  clearActive: () => {
    set({ activeSessionId: null });
  },
}));
