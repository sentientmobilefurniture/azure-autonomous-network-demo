import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

interface ScenarioState {
  /** Active Gremlin graph name (e.g. "cloud-outage-topology") */
  activeGraph: string;
  /** Active AI Search runbooks index */
  activeRunbooksIndex: string;
  /** Active AI Search tickets index */
  activeTicketsIndex: string;
  /** Set active graph */
  setActiveGraph: (graph: string) => void;
  /** Set active runbooks index */
  setActiveRunbooksIndex: (index: string) => void;
  /** Set active tickets index */
  setActiveTicketsIndex: (index: string) => void;
  /** Get headers to include in /query/* requests */
  getQueryHeaders: () => Record<string, string>;
}

const ScenarioCtx = createContext<ScenarioState | null>(null);

export function ScenarioProvider({ children }: { children: ReactNode }) {
  const [activeGraph, setActiveGraph] = useState('topology');
  const [activeRunbooksIndex, setActiveRunbooksIndex] = useState('runbooks-index');
  const [activeTicketsIndex, setActiveTicketsIndex] = useState('tickets-index');

  const getQueryHeaders = useCallback((): Record<string, string> => {
    const headers: Record<string, string> = {};
    if (activeGraph) headers['X-Graph'] = activeGraph;
    return headers;
  }, [activeGraph]);

  return (
    <ScenarioCtx.Provider value={{
      activeGraph,
      activeRunbooksIndex,
      activeTicketsIndex,
      setActiveGraph,
      setActiveRunbooksIndex,
      setActiveTicketsIndex,
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
