import { useState, useEffect, useCallback, useRef } from 'react';
import type { TopologyNode, TopologyEdge, TopologyMeta } from '../types';

// Re-export types for consumers that import from this module
export type { TopologyNode, TopologyEdge, TopologyMeta };

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

  const fetchTopology = useCallback(async (vertexLabels?: string[]) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/query/topology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

  // Fetch on mount
  useEffect(() => {
    fetchTopology();
    return () => { abortRef.current?.abort(); };
  }, [fetchTopology]);

  return { data, loading, error, refetch: fetchTopology };
}
