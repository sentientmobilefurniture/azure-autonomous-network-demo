import { useState, useEffect, useCallback, useRef } from 'react';
import { useScenarioContext } from '../context/ScenarioContext';

// ── Types ──────────────────────────────────────────────────────

export interface TopologyNode {
  id: string;
  label: string;     // vertex label (CoreRouter, AggSwitch, etc.)
  properties: Record<string, unknown>;
  // Force-graph internal fields (added by the library)
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

export interface TopologyEdge {
  id: string;
  source: string | TopologyNode;
  target: string | TopologyNode;
  label: string;     // edge label (connects_to, etc.)
  properties: Record<string, unknown>;
}

export interface TopologyMeta {
  node_count: number;
  edge_count: number;
  query_time_ms: number;
  labels: string[];
}

interface TopologyData {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  meta: TopologyMeta | null;
}

// ── Hook ───────────────────────────────────────────────────────

export function useTopology() {
  const [data, setData] = useState<TopologyData>({ nodes: [], edges: [], meta: null });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { getQueryHeaders } = useScenarioContext();

  const fetchTopology = useCallback(async (vertexLabels?: string[]) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/query/topology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getQueryHeaders() },
        body: JSON.stringify({ vertex_labels: vertexLabels }),
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      setData({ nodes: json.nodes, edges: json.edges, meta: json.meta });
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch full topology on mount
  useEffect(() => {
    fetchTopology();
  }, [fetchTopology]);

  return { data, loading, error, refetch: fetchTopology };
}
