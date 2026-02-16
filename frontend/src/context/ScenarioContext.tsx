import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import type { SavedScenario } from '../types';

interface ScenarioState {
  /** Currently active saved scenario name, or null for custom/manual mode */
  activeScenario: string | null;
  /** Active Gremlin graph name (e.g. "cloud-outage-topology") */
  activeGraph: string;
  /** Active AI Search runbooks index */
  activeRunbooksIndex: string;
  /** Active AI Search tickets index */
  activeTicketsIndex: string;
  /** Active prompt set scenario name */
  activePromptSet: string;
  /** Provisioning status */
  provisioningStatus: ProvisioningStatus;
  /** Scenario-driven node colors from graph_styles */
  scenarioNodeColors: Record<string, string>;
  /** Scenario-driven node sizes from graph_styles */
  scenarioNodeSizes: Record<string, number>;
  /** All saved scenarios from Cosmos (single source of truth) */
  savedScenarios: SavedScenario[];
  /** The full record for the currently active scenario, or null */
  activeScenarioRecord: SavedScenario | null;
  /** Whether saved scenarios are loading */
  scenariosLoading: boolean;
  /** Refresh saved scenarios from Cosmos */
  refreshScenarios: () => Promise<void>;
  /** Set active scenario (auto-derives all bindings when non-null) */
  setActiveScenario: (name: string | null, scenario?: { resources?: { graph?: string; runbooks_index?: string; tickets_index?: string; prompts_container?: string } }) => void;
  /** Set active graph */
  setActiveGraph: (graph: string) => void;
  /** Set active runbooks index */
  setActiveRunbooksIndex: (index: string) => void;
  /** Set active tickets index */
  setActiveTicketsIndex: (index: string) => void;
  /** Set active prompt set */
  setActivePromptSet: (name: string) => void;
  /** Set provisioning status */
  setProvisioningStatus: (status: ProvisioningStatus) => void;
  /** Set scenario-driven graph styles (colors + sizes) */
  setScenarioStyles: (styles: { node_types?: Record<string, { color: string; size: number }> } | null) => void;
  /** Whether the initial scenario validation has completed */
  scenarioReady: boolean;
  /** Get headers to include in /query/* requests */
  getQueryHeaders: () => Record<string, string>;
}

export type ProvisioningStatus =
  | { state: 'idle' }
  | { state: 'needs-provisioning'; scenarioName: string }
  | { state: 'provisioning'; step: string; scenarioName: string }
  | { state: 'done'; scenarioName: string }
  | { state: 'error'; error: string; scenarioName: string };

const ScenarioCtx = createContext<ScenarioState | null>(null);

export function ScenarioProvider({ children }: { children: ReactNode }) {
  // Restore active scenario from localStorage on mount
  const [activeScenario, setActiveScenarioRaw] = useState<string | null>(
    () => localStorage.getItem('activeScenario'),
  );

  // Derive initial bindings from persisted scenario, or use defaults
  const deriveGraph = (name: string | null) => name ? `${name}-topology` : 'topology';
  const deriveRunbooks = (name: string | null) => name ? `${name}-runbooks-index` : 'runbooks-index';
  const deriveTickets = (name: string | null) => name ? `${name}-tickets-index` : 'tickets-index';
  const derivePrompts = (name: string | null) => name ?? '';

  const [activeGraph, setActiveGraph] = useState(() => deriveGraph(activeScenario));
  const [activeRunbooksIndex, setActiveRunbooksIndex] = useState(() => deriveRunbooks(activeScenario));
  const [activeTicketsIndex, setActiveTicketsIndex] = useState(() => deriveTickets(activeScenario));
  const [activePromptSet, setActivePromptSet] = useState(() => derivePrompts(activeScenario));
  const [provisioningStatus, setProvisioningStatus] = useState<ProvisioningStatus>({ state: 'idle' });

  // Saved scenarios from Cosmos (single source of truth — eliminates 4x independent fetches)
  const [savedScenarios, setSavedScenarios] = useState<SavedScenario[]>([]);
  const [scenariosLoading, setScenariosLoading] = useState(false);

  const refreshScenarios = useCallback(async () => {
    setScenariosLoading(true);
    try {
      const res = await fetch('/query/scenarios/saved');
      const data = await res.json();
      setSavedScenarios(data.scenarios || []);
    } catch (e) {
      console.warn('Failed to fetch saved scenarios:', e);
    } finally {
      setScenariosLoading(false);
    }
  }, []);

  // Derived: full record for the currently active scenario
  const activeScenarioRecord = savedScenarios.find(s => s.id === activeScenario) ?? null;

  // Whether we've finished validating the persisted scenario against Cosmos
  const [scenarioReady, setScenarioReady] = useState<boolean>(
    () => localStorage.getItem('activeScenario') === null,
  );

  // Scenario-driven graph styles (from graph_styles.node_types in scenario.yaml)
  const [scenarioNodeColors, setScenarioNodeColors] = useState<Record<string, string>>({});
  const [scenarioNodeSizes, setScenarioNodeSizes] = useState<Record<string, number>>({});

  const setScenarioStyles = useCallback((styles: { node_types?: Record<string, { color: string; size: number }> } | null) => {
    if (styles?.node_types) {
      const colors: Record<string, string> = {};
      const sizes: Record<string, number> = {};
      for (const [type, cfg] of Object.entries(styles.node_types)) {
        colors[type] = cfg.color;
        sizes[type] = cfg.size;
      }
      setScenarioNodeColors(colors);
      setScenarioNodeSizes(sizes);
    } else {
      setScenarioNodeColors({});
      setScenarioNodeSizes({});
    }
  }, []);

  // Persist activeScenario to localStorage
  useEffect(() => {
    if (activeScenario) {
      localStorage.setItem('activeScenario', activeScenario);
    } else {
      localStorage.removeItem('activeScenario');
    }
  }, [activeScenario]);

  // Validate persisted scenario still exists in the backend on mount.
  // Clears the ghost if the Cosmos record was deleted (e.g. after azd up).
  // Sets scenarioReady=true when done (or after 5s timeout).
  useEffect(() => {
    if (!activeScenario) {
      // Still fetch scenarios for ScenarioChip etc.
      refreshScenarios();
      return;
    }
    let cancelled = false;
    const timeout = setTimeout(() => {
      if (!cancelled) setScenarioReady(true);
    }, 5000);
    fetch('/query/scenarios/saved')
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        const scenarios = data.scenarios ?? [];
        setSavedScenarios(scenarios);
        const saved: string[] = scenarios.map((s: { id: string }) => s.id);
        if (!saved.includes(activeScenario)) {
          console.warn(`Persisted scenario "${activeScenario}" no longer exists — clearing.`);
          setActiveScenarioRaw(null);
          localStorage.removeItem('activeScenario');
        }
      })
      .catch(() => {}) // silent — don't clear on network error
      .finally(() => {
        if (!cancelled) setScenarioReady(true);
      });
    return () => { cancelled = true; clearTimeout(timeout); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Set active scenario and auto-derive all bindings
  // If a SavedScenario with resources is provided, use exact resource names.
  // Otherwise derive from naming conventions (backward compatibility).
  const setActiveScenario = useCallback((name: string | null, scenario?: { resources?: { graph?: string; runbooks_index?: string; tickets_index?: string; prompts_container?: string } }) => {
    setActiveScenarioRaw(name);
    if (scenario?.resources) {
      // Use exact resource names from saved scenario config
      setActiveGraph(scenario.resources.graph ?? (name ? `${name}-topology` : 'topology'));
      setActiveRunbooksIndex(scenario.resources.runbooks_index ?? (name ? `${name}-runbooks-index` : 'runbooks-index'));
      setActiveTicketsIndex(scenario.resources.tickets_index ?? (name ? `${name}-tickets-index` : 'tickets-index'));
      setActivePromptSet(scenario.resources.prompts_container ?? name ?? '');
    } else if (name) {
      // Fallback: derive from conventions (backward compatibility)
      setActiveGraph(`${name}-topology`);
      setActiveRunbooksIndex(`${name}-runbooks-index`);
      setActiveTicketsIndex(`${name}-tickets-index`);
      setActivePromptSet(name);
    }
    // When null (custom mode), leave existing bindings as-is
  }, []);

  const getQueryHeaders = useCallback((): Record<string, string> => {
    const headers: Record<string, string> = {};
    if (activeGraph) headers['X-Graph'] = activeGraph;
    return headers;
  }, [activeGraph]);

  return (
    <ScenarioCtx.Provider value={{
      activeScenario,
      activeGraph,
      activeRunbooksIndex,
      activeTicketsIndex,
      activePromptSet,
      provisioningStatus,
      scenarioNodeColors,
      scenarioNodeSizes,
      savedScenarios,
      activeScenarioRecord,
      scenariosLoading,
      refreshScenarios,
      setActiveScenario,
      setActiveGraph,
      setActiveRunbooksIndex,
      setActiveTicketsIndex,
      setActivePromptSet,
      setProvisioningStatus,
      setScenarioStyles,
      scenarioReady,
      getQueryHeaders,
    }}>
      {children}
    </ScenarioCtx.Provider>
  );
}

export function useScenarioContext() {
  const ctx = useContext(ScenarioCtx);
  if (!ctx) throw new Error('useScenarioContext must be inside ScenarioProvider');
  return ctx;
}
