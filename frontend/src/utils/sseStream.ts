/**
 * Shared SSE (Server-Sent Events) stream parser.
 *
 * Consumes a ReadableStream from a fetch Response (text/event-stream)
 * and dispatches parsed events to handler callbacks.
 *
 * Used by:
 *  - AddScenarioModal (upload progress)
 *  - SettingsModal (provision agents, individual uploads)
 *  - ScenarioChip / selectScenario (auto-provisioning)
 */

export interface SSEProgressData {
  step: string;
  detail: string;
  pct: number;
}

export interface SSEHandlers {
  onProgress?: (data: SSEProgressData) => void;
  onComplete?: (data: Record<string, unknown>) => void;
  onError?: (data: { error: string }) => void;
}

/**
 * Consume an SSE response body and call handlers for each parsed event.
 *
 * Handles the raw ReadableStream text/event-stream format used by the
 * graph-query-api upload and provisioning endpoints.
 *
 * @param response - The fetch Response with a readable body
 * @param handlers - Callbacks for progress, complete, and error events
 * @param signal   - Optional AbortSignal to cancel consumption
 * @returns The final complete event data, or undefined if no complete event was received
 */
export async function consumeSSE(
  response: Response,
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<Record<string, unknown> | undefined> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';
  let lastComplete: Record<string, unknown> | undefined;

  try {
    while (true) {
      if (signal?.aborted) {
        reader.cancel();
        break;
      }

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;

        const jsonStr = line.slice(6);
        try {
          const parsed = JSON.parse(jsonStr);

          if ('error' in parsed) {
            handlers.onError?.({ error: parsed.error });
          } else if (
            'scenario' in parsed ||
            'index' in parsed ||
            'database' in parsed ||
            'graph' in parsed ||
            'prompts_stored' in parsed
          ) {
            // Complete event — final result from an upload/provisioning step
            lastComplete = parsed;
            handlers.onComplete?.(parsed);
          } else if ('pct' in parsed) {
            // Progress event
            handlers.onProgress?.({
              step: parsed.step ?? '',
              detail: parsed.detail ?? parsed.step ?? '',
              pct: parsed.pct ?? 0,
            });
          }
        } catch {
          // Not valid JSON — skip
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  return lastComplete;
}

/**
 * Upload a file to an SSE endpoint and track progress.
 *
 * Wraps the common pattern: FormData POST → SSE stream → handlers.
 *
 * @param endpoint - The upload URL (e.g. '/query/upload/graph')
 * @param file     - The File to upload
 * @param handlers - SSE event handlers
 * @param params   - Optional query parameters (e.g. { scenario_name: 'foo' })
 * @param signal   - Optional AbortSignal
 * @returns The final complete event data
 */
export async function uploadWithSSE(
  endpoint: string,
  file: File,
  handlers: SSEHandlers,
  params?: Record<string, string>,
  signal?: AbortSignal,
): Promise<Record<string, unknown> | undefined> {
  const url = new URL(endpoint, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v) url.searchParams.set(k, v);
    }
  }

  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(url.toString(), {
    method: 'POST',
    body: formData,
    signal,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${res.status} ${text}`);
  }

  return consumeSSE(res, handlers, signal);
}
