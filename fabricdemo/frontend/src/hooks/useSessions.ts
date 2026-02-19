import { useState, useCallback, useEffect, useRef } from 'react';
import type { SessionSummary } from '../types';

/**
 * Hook to fetch and poll the session list from the backend.
 * Replaces the interaction-based sidebar data source.
 */
export function useSessions(scenario?: string) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const url = scenario
        ? `/api/sessions?scenario=${encodeURIComponent(scenario)}`
        : '/api/sessions';
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSessions(data.sessions ?? []);
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    } finally {
      setLoading(false);
    }
  }, [scenario]);

  // Initial fetch
  useEffect(() => {
    setLoading(true);
    fetchSessions();
  }, [fetchSessions]);

  // Poll every 5 seconds
  useEffect(() => {
    intervalRef.current = setInterval(fetchSessions, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchSessions]);

  return { sessions, loading, refetch: fetchSessions };
}
