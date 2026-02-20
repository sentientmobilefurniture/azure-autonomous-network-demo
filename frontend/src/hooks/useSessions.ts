import { useState, useCallback, useEffect } from 'react';
import type { SessionSummary } from '../types';

/**
 * Hook to fetch the session list from the backend.
 * Fetches once on mount; call `refetch` manually after session
 * create / complete / delete or from the sidebar refresh button.
 */
export function useSessions(_scenario?: string) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch('/api/sessions');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSessions(data.sessions ?? []);
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch once on mount
  useEffect(() => {
    setLoading(true);
    fetchSessions();
  }, [fetchSessions]);

  return { sessions, loading, refetch: fetchSessions };
}
