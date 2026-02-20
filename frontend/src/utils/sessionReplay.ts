/**
 * Session replay — reconstruct Message[] from a persisted event_log.
 *
 * Used when viewing a historical session loaded from Cosmos DB.
 * Extracted from useConversation.ts.
 */

import type {
  Message,
  AssistantMessage,
} from '../types/conversation';
import type { SessionDetail, VisualizationData, ActionData, RunMeta } from '../types';

export function replayEventLog(session: SessionDetail): Message[] {
  const msgs: Message[] = [];
  let current: AssistantMessage | null = null;

  for (const event of session.event_log) {
    const evType = event.event;
    const data =
      typeof event.data === 'string' ? JSON.parse(event.data) : event.data;

    switch (evType) {
      case 'user_message':
        if (current) {
          msgs.push(current);
          current = null;
        }
        msgs.push({
          kind: 'user',
          id: crypto.randomUUID(),
          text: (data as { text: string }).text,
          timestamp: event.timestamp ?? session.created_at,
        });
        break;

      case 'run.start':
        if (current) msgs.push(current);
        current = {
          kind: 'assistant',
          id: crypto.randomUUID(),
          timestamp: event.timestamp ?? session.created_at,
          toolCalls: [],
          content: '',
          streamingContent: '',
          status: 'complete',
        };
        break;

      case 'tool_call.complete': {
        if (!current) break;
        const tc = data as Record<string, unknown>;
        const subStepsRaw = tc.sub_steps as
          | Array<{
              index: number;
              query: string;
              result_summary: string;
              agent?: string;
            }>
          | undefined;
        current.toolCalls.push({
          id: tc.id as string,
          step: tc.step as number,
          agent: tc.agent as string,
          query: (tc.query as string) ?? '',
          status: 'complete',
          duration: tc.duration as string | undefined,
          response: tc.response as string | undefined,
          error: tc.error as boolean | undefined,
          visualizations: tc.visualizations as VisualizationData[] | undefined,
          subSteps: subStepsRaw?.map((ss) => ({
            index: ss.index,
            query: ss.query,
            resultSummary: ss.result_summary,
            agent: ss.agent,
          })),
          isAction: tc.is_action as boolean | undefined,
          action: tc.action as ActionData | undefined,
          reasoning: tc.reasoning as string | undefined,
        });
        break;
      }

      case 'message.complete':
        if (current) current.content = (data as { text: string }).text;
        break;

      case 'run.complete':
        if (current) current.runMeta = data as RunMeta;
        break;

      case 'error':
        if (current) {
          current.errorMessage = (data as { message: string }).message;
          current.status = 'error';
        }
        break;
    }
  }

  if (current) msgs.push(current);

  // Synthesize user message if event_log started without one
  if (msgs.length > 0 && msgs[0].kind !== 'user') {
    msgs.unshift({
      kind: 'user',
      id: crypto.randomUUID(),
      text: session.alert_text,
      timestamp: session.created_at,
    });
  }

  return msgs;
}
