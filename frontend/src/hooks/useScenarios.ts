import { useState, useRef, useCallback } from 'react';

interface ProgressEvent {
  step: string;
  detail: string;
  pct: number;
}

interface UploadResult {
  scenario: string;
  display_name: string;
  graph: string;
  vertices: number;
  edges: number;
}

export interface ScenarioInfo {
  graph_name: string;
  vertex_count: number;
  has_data: boolean;
}

export interface SearchIndex {
  name: string;
  type: 'runbooks' | 'tickets' | 'other';
  document_count: number | null;
  fields: number;
}

export function useScenarios() {
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [indexes, setIndexes] = useState<SearchIndex[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchScenarios = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/query/scenarios');
      const data = await res.json();
      setScenarios(data.scenarios || []);
      if (data.error) setError(data.error);
    } catch (e) {
      setError(`Failed to fetch scenarios: ${e}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchIndexes = useCallback(async () => {
    try {
      const res = await fetch('/query/indexes');
      const data = await res.json();
      setIndexes(data.indexes || []);
    } catch (e) {
      // AI Search indexes are optional — don't set top-level error
      console.warn('Failed to fetch indexes:', e);
    }
  }, []);

  const uploadScenario = useCallback(async (file: File) => {
    setUploading(true);
    setProgress(null);
    setUploadResult(null);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    abortRef.current = new AbortController();

    try {
      const res = await fetch('/query/scenario/upload', {
        method: 'POST',
        body: formData,
        signal: abortRef.current.signal,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Upload failed: ${res.status} ${text}`);
      }

      // Read SSE stream
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      if (!reader) throw new Error('No response body');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            try {
              const parsed = JSON.parse(jsonStr);
              // Check the event type from the preceding event: line
              if ('pct' in parsed) {
                setProgress(parsed as ProgressEvent);
              } else if ('scenario' in parsed) {
                setUploadResult(parsed as UploadResult);
              } else if ('error' in parsed) {
                setError(parsed.error);
              }
            } catch {
              // not JSON, skip
            }
          }
        }
      }

      // Refresh scenario list after upload
      await fetchScenarios();
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        setError('Upload cancelled');
      } else {
        setError(`Upload failed: ${e}`);
      }
    } finally {
      setUploading(false);
      abortRef.current = null;
    }
  }, [fetchScenarios]);

  const cancelUpload = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    scenarios,
    indexes,
    loading,
    uploading,
    progress,
    uploadResult,
    error,
    fetchScenarios,
    fetchIndexes,
    uploadScenario,
    cancelUpload,
  };
}
