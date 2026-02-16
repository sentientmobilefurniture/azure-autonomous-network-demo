import { useState, useCallback } from 'react';
import { SavedScenario } from '../types';
import { useScenarioContext } from '../context/ScenarioContext';
import { triggerProvisioning } from '../utils/triggerProvisioning';

export interface ScenarioInfo {
  graph_name: string;
  vertex_count: number;
  has_data: boolean;
}

export interface SearchIndex {
  name: string;
  type: 'runbooks' | 'tickets' | 'other';
  document_count: number | null;
  fields: number;
}

export function useScenarios() {
  // Existing: graph scenarios & search indexes (discovery endpoints)
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [indexes, setIndexes] = useState<SearchIndex[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New: saved scenario records from Cosmos
  const [savedScenarios, setSavedScenarios] = useState<SavedScenario[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);

  const {
    setActiveScenario,
    setProvisioningStatus,
    setScenarioStyles,
  } = useScenarioContext();

  // Fetch graph scenarios (existing discovery endpoint)
  const fetchScenarios = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/query/scenarios');
      const data = await res.json();
      setScenarios(data.scenarios || []);
      if (data.error) setError(data.error);
    } catch (e) {
      setError(`Failed to fetch scenarios: ${e}`);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch search indexes
  const fetchIndexes = useCallback(async () => {
    try {
      const res = await fetch('/query/indexes');
      const data = await res.json();
      setIndexes(data.indexes || []);
    } catch (e) {
      console.warn('Failed to fetch indexes:', e);
    }
  }, []);

  // Fetch saved scenario records from Cosmos
  const fetchSavedScenarios = useCallback(async () => {
    setSavedLoading(true);
    try {
      const res = await fetch('/query/scenarios/saved');
      const data = await res.json();
      setSavedScenarios(data.scenarios || []);
    } catch (e) {
      console.warn('Failed to fetch saved scenarios:', e);
    } finally {
      setSavedLoading(false);
    }
  }, []);

  // Save a scenario record to Cosmos (after all uploads succeed)
  const saveScenario = useCallback(async (meta: {
    name: string;
    display_name?: string;
    description?: string;
    use_cases?: string[];
    example_questions?: string[];
    graph_styles?: Record<string, unknown>;
    domain?: string;
    graph_connector?: string;
    upload_results: Record<string, unknown>;
  }) => {
    const res = await fetch('/query/scenarios/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(meta),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Save failed: ${res.status} ${text}`);
    }
    const data = await res.json();
    // Refresh the list
    await fetchSavedScenarios();
    return data;
  }, [fetchSavedScenarios]);

  // Delete a saved scenario record
  const deleteSavedScenario = useCallback(async (name: string) => {
    const res = await fetch(`/query/scenarios/saved/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Delete failed: ${res.status} ${text}`);
    }
    // Refresh the list
    await fetchSavedScenarios();
  }, [fetchSavedScenarios]);

  // Select a saved scenario: update context bindings + auto-provision agents
  const selectScenario = useCallback(async (name: string) => {
    // 1. Update all frontend bindings instantly, using config-specified resources if available
    const saved = savedScenarios.find(s => s.id === name);
    setActiveScenario(name, saved);

    // 2. Push scenario graph_styles into context for dynamic node colors
    if (saved?.graph_styles) {
      setScenarioStyles(saved.graph_styles as { node_types?: Record<string, { color: string; size: number }> });
    } else {
      setScenarioStyles(null);
    }

    // 3. Derive resource names from saved resources or conventions
    const graph = saved?.resources?.graph ?? `${name}-topology`;
    const runbooks_index = saved?.resources?.runbooks_index ?? `${name}-runbooks-index`;
    const tickets_index = saved?.resources?.tickets_index ?? `${name}-tickets-index`;

    // 4. Auto-provision agents with SSE progress tracking
    await triggerProvisioning(
      { graph, runbooks_index, tickets_index, prompt_scenario: name },
      name,
      setProvisioningStatus,
    );
  }, [savedScenarios, setActiveScenario, setScenarioStyles, setProvisioningStatus]);

  return {
    // Existing discovery
    scenarios,
    indexes,
    loading,
    error,
    fetchScenarios,
    fetchIndexes,

    // Saved scenario management
    savedScenarios,
    savedLoading,
    fetchSavedScenarios,
    saveScenario,
    deleteSavedScenario,
    selectScenario,
  };
}
