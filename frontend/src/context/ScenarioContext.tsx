import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

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
  /** Set active scenario (auto-derives all bindings when non-null) */
  setActiveScenario: (name: string | null) => void;
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
  /** Get headers to include in /query/* requests */
  getQueryHeaders: () => Record<string, string>;
}

export type ProvisioningStatus =
  | { state: 'idle' }
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
  useEffect(() => {
    if (!activeScenario) return;
    let cancelled = false;
    fetch('/query/scenarios/saved')
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        const saved: string[] = (data.scenarios ?? []).map((s: { id: string }) => s.id);
        if (!saved.includes(activeScenario)) {
          console.warn(`Persisted scenario "${activeScenario}" no longer exists — clearing.`);
          setActiveScenarioRaw(null);
          localStorage.removeItem('activeScenario');
        }
      })
      .catch(() => {}); // silent — don't clear on network error
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Set active scenario and auto-derive all bindings
  const setActiveScenario = useCallback((name: string | null) => {
    setActiveScenarioRaw(name);
    if (name) {
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
      setActiveScenario,
      setActiveGraph,
      setActiveRunbooksIndex,
      setActiveTicketsIndex,
      setActivePromptSet,
      setProvisioningStatus,
      setScenarioStyles,
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
