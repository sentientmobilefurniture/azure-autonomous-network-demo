/**
 * useArchitectureGraph — provides the static architecture graph.
 *
 * Fetches from GET /api/config/architecture which reads the
 * hand-curated architecture_graph.json file.
 */

import { useState, useEffect, useCallback } from 'react';
import type { ResourceNode, ResourceEdge } from '../types';

export interface ArchitectureGraphData {
  nodes: ResourceNode[];
  edges: ResourceEdge[];
  loading: boolean;
  error: string | null;
}

export function useArchitectureGraph(): ArchitectureGraphData {
  const [nodes, setNodes] = useState<ResourceNode[]>([]);
  const [edges, setEdges] = useState<ResourceEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Try static architecture file first, fall back to dynamic resource graph
      let res = await fetch('/api/config/architecture');
      if (res.status === 404) {
        res = await fetch('/api/config/resources');
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setNodes(data.nodes ?? []);
      setEdges(data.edges ?? []);
    } catch (e) {
      setError(String(e));
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  return { nodes, edges, loading, error };
}
