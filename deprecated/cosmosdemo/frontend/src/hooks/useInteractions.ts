import { useState, useCallback } from 'react';
import type { Interaction, StepEvent, RunMeta } from '../types';

export function useInteractions() {
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchInteractions = useCallback(async (scenario?: string) => {
    setLoading(true);
    try {
      const url = scenario
        ? `/query/interactions?scenario=${encodeURIComponent(scenario)}&limit=50`
        : '/query/interactions?limit=50';
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setInteractions(data.interactions ?? []);
    } catch (err) {
      console.error('Failed to fetch interactions:', err);
      // Don't clear existing interactions on error — keep stale data visible
    } finally {
      setLoading(false);
    }
  }, []);

  const saveInteraction = useCallback(async (interaction: {
    scenario: string;
    query: string;
    steps: StepEvent[];
    diagnosis: string;
    run_meta: RunMeta | null;
  }) => {
    try {
      const res = await fetch('/query/interactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(interaction),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const saved = await res.json();
      setInteractions(prev => [saved, ...prev]);
      return saved;
    } catch (err) {
      console.error('Failed to save interaction:', err);
      return null;
    }
  }, []);

  const deleteInteraction = useCallback(async (id: string, scenario: string) => {
    try {
      const res = await fetch(
        `/query/interactions/${id}?scenario=${encodeURIComponent(scenario)}`,
        { method: 'DELETE' },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setInteractions(prev => prev.filter(i => i.id !== id));
    } catch (err) {
      console.error('Failed to delete interaction:', err);
    }
  }, []);

  return { interactions, loading, fetchInteractions, saveInteraction, deleteInteraction };
}
