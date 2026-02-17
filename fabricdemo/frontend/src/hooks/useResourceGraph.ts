/**
 * useResourceGraph — provides the resource / agent-flow graph.
 *
 * Fetches from GET /api/config/resources which builds the graph
 * from the hardcoded scenario config.
 */

import { useState, useEffect, useCallback } from 'react';
import type { ResourceNode, ResourceEdge } from '../types';

export interface ResourceGraphData {
  nodes: ResourceNode[];
  edges: ResourceEdge[];
  loading: boolean;
  error: string | null;
}

export function useResourceGraph(): ResourceGraphData {
  const [nodes, setNodes] = useState<ResourceNode[]>([]);
  const [edges, setEdges] = useState<ResourceEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/config/resources');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setNodes(data.nodes ?? []);
      setEdges(data.edges ?? []);
      // Surface backend error (partial results may still be returned)
      if (data.error) setError(data.error);
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
