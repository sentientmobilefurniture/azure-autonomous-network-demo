/**
 * useResourceGraph — provides the resource / agent-flow graph.
 *
 * Fetches from GET /api/config/resources which builds the graph
 * dynamically from the active scenario's config YAML.
 */

import { useState, useEffect, useCallback } from 'react';
import type { ResourceNode, ResourceEdge } from '../types';
import { useScenarioContext } from '../context/ScenarioContext';

export interface ResourceGraphData {
  nodes: ResourceNode[];
  edges: ResourceEdge[];
  loading: boolean;
  error: string | null;
}

export function useResourceGraph(): ResourceGraphData {
  const { activeScenario, provisioningStatus } = useScenarioContext();
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
    } catch (e) {
      setError(String(e));
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-fetch when scenario changes or provisioning completes
  useEffect(() => {
    fetchGraph();
  }, [activeScenario, fetchGraph]);

  useEffect(() => {
    if (provisioningStatus.state === 'done') {
      fetchGraph();
    }
  }, [provisioningStatus, fetchGraph]);

  return { nodes, edges, loading, error };
}
