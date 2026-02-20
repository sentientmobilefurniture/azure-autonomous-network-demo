/**
 * SSE line parser — handles chunked data and partial lines.
 *
 * Extracted from useConversation.ts for reuse by the Zustand chatStore.
 */

export interface SSEEvent {
  event: string;
  data: string;
}

export function parseSSELines(buffer: string): {
  events: SSEEvent[];
  remainder: string;
} {
  const events: SSEEvent[] = [];
  const lines = buffer.split('\n');
  let currentEvent = '';
  let currentData = '';
  let remainder = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7).trim();
    } else if (line.startsWith('data: ')) {
      currentData = line.slice(6);
    } else if (line === '' && currentEvent) {
      events.push({ event: currentEvent, data: currentData });
      currentEvent = '';
      currentData = '';
    } else if (i === lines.length - 1 && line !== '') {
      remainder = line;
    }
  }

  // Partial event at the end (event set but no blank line yet)
  if (currentEvent) {
    remainder =
      `event: ${currentEvent}\n` +
      (currentData ? `data: ${currentData}\n` : '') +
      remainder;
  }

  return { events, remainder };
}
