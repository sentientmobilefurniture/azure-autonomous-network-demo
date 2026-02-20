import { useState, useCallback } from 'react';
import type { ToolCall } from '../types/conversation';
import type { VisualizationData } from '../types';

/**
 * Hook for loading visualization data for a step.
 *
 * Returns an array of VisualizationData (supports multi-query viz tabs).
 * Primary path: read persisted `step.visualizations` (v18+) or `step.visualization` (legacy).
 * For AI Search agents: query the search index directly to show raw results.
 * Fallback: show response text as documents view.
 */
export function useVisualization() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<VisualizationData[]>([]);
  const [error, setError] = useState<string | null>(null);

  const getVisualization = useCallback(
    async (tc: ToolCall): Promise<VisualizationData[]> => {
      const vizArray = tc.visualizations ?? [];

      // 1. Primary path: use persisted structured visualization data (graph/table types)
      if (vizArray.length) {
        const structured = vizArray.filter(v => v.type !== 'documents');
        if (structured.length) {
          setData(structured);
          setError(null);
          return structured;
        }
      }

      // 2. For AI Search agents: query the index directly to get raw results
      const isSearchAgent = ['RunbookKBAgent', 'HistoricalTicketAgent', 'AzureAISearch'].includes(tc.agent);
      if (isSearchAgent && tc.query) {
        setLoading(true);
        setError(null);
        try {
          const res = await fetch('/query/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent: tc.agent, query: tc.query, top: 10 }),
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
                content: tc.response ?? '',
                agent: tc.agent,
                citations: vizArray[0]?.type === 'documents' ? vizArray[0].data.citations : undefined,
                searchHits: result.hits,
                indexName: result.index_name,
              },
            };
            setData([searchViz]);
            return [searchViz];
          }
        } catch (err) {
          console.warn('Search query error:', err);
        } finally {
          setLoading(false);
        }
      }

      // 3. Use persisted documents visualization if available
      if (vizArray.length) {
        setData(vizArray);
        setError(null);
        return vizArray;
      }

      // 4. Fallback: show response text as documents view
      if (tc.response) {
        const docFallback: VisualizationData = {
          type: 'documents',
          data: {
            content: tc.response,
            agent: tc.agent,
          },
        };
        setData([docFallback]);
        setError(null);
        return [docFallback];
      }

      // 5. No response at all
      setError('No visualization data available for this step.');
      return [];
    },
    [],
  );

  const reset = useCallback(() => {
    setData([]);
    setError(null);
    setLoading(false);
  }, []);

  return { getVisualization, data, loading, error, reset };
}
