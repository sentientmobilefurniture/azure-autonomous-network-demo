import { useState, useCallback } from 'react';
import type { StepEvent, VisualizationData } from '../types';

/**
 * Hook for loading visualization data for a step.
 *
 * Primary path: read persisted `step.visualization`.
 * For AI Search agents: query the search index directly to show raw results.
 * Fallback: show response text as documents view.
 */
export function useVisualization() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<VisualizationData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const getVisualization = useCallback(
    async (step: StepEvent): Promise<VisualizationData | null> => {
      // 1. Primary path: use persisted visualization data (graph/table types)
      if (step.visualization && step.visualization.type !== 'documents') {
        setData(step.visualization);
        setError(null);
        return step.visualization;
      }

      // 2. For AI Search agents: query the index directly to get raw results
      const isSearchAgent = ['RunbookKBAgent', 'HistoricalTicketAgent', 'AzureAISearch'].includes(step.agent);
      if (isSearchAgent && step.query) {
        setLoading(true);
        setError(null);
        try {
          const res = await fetch('/query/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent: step.agent, query: step.query, top: 10 }),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const result = await res.json();
          if (result.error) {
            // Search failed — fall back to response text
            console.warn('Search query failed:', result.error);
          } else if (result.hits && result.hits.length > 0) {
            const searchViz: VisualizationData = {
              type: 'documents',
              data: {
                content: step.response ?? '',
                agent: step.agent,
                citations: step.visualization?.data?.citations,
                searchHits: result.hits,
                indexName: result.index_name,
              },
            };
            setData(searchViz);
            return searchViz;
          }
        } catch (err) {
          console.warn('Search query error:', err);
        } finally {
          setLoading(false);
        }
      }

      // 3. Use persisted documents visualization if available
      if (step.visualization) {
        setData(step.visualization);
        setError(null);
        return step.visualization;
      }

      // 4. Fallback: show response text as documents view
      if (step.response) {
        const docFallback: VisualizationData = {
          type: 'documents',
          data: {
            content: step.response,
            agent: step.agent,
          },
        };
        setData(docFallback);
        setError(null);
        return docFallback;
      }

      // 5. No response at all
      setError('No visualization data available for this step.');
      return null;
    },
    [],
  );

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { getVisualization, data, loading, error, reset };
}
