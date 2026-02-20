import type { VisualizationData, ActionData, RunMeta } from './index';

// ── Message union ──────────────────────────────────────────────

export interface UserMessage {
  kind: 'user';
  id: string;
  text: string;
  timestamp: string;
}

export interface AssistantMessage {
  kind: 'assistant';
  id: string;
  timestamp: string;
  toolCalls: ToolCall[];
  content: string;               // final complete text
  streamingContent: string;       // accumulated deltas (pre-completion)
  status: 'pending' | 'streaming' | 'complete' | 'error';
  runMeta?: RunMeta;
  errorMessage?: string;
  statusMessage?: string;
}

export type Message = UserMessage | AssistantMessage;

// ── Tool call ──────────────────────────────────────────────────

export type ToolCallStatus = 'pending' | 'running' | 'complete' | 'error';

export interface ToolCall {
  id: string;                     // UUID from backend tool_call.start
  step: number;                   // display order
  agent: string;                  // display name
  query: string;
  reasoning?: string;
  status: ToolCallStatus;
  duration?: string;
  timestamp?: string;
  response?: string;
  error?: boolean;
  visualizations?: VisualizationData[];
  subSteps?: SubStep[];
  isAction?: boolean;
  action?: ActionData;
}

export interface SubStep {
  index: number;
  query: string;
  resultSummary: string;
  agent?: string;
}

// ── Reducer state & actions ────────────────────────────────────

export interface ConversationState {
  messages: Message[];
  running: boolean;
  activeSessionId: string | null;
}

export type ConversationAction =
  | { type: 'ADD_USER_MESSAGE'; payload: { id: string; text: string; timestamp: string } }
  | { type: 'ADD_ASSISTANT_MESSAGE'; payload: { id: string; timestamp: string } }
  | { type: 'TOOL_CALL_START'; payload: { messageId: string; toolCall: ToolCall } }
  | { type: 'TOOL_CALL_COMPLETE'; payload: { messageId: string; toolCallId: string; data: Partial<ToolCall> } }
  | { type: 'MESSAGE_DELTA'; payload: { messageId: string; text: string } }
  | { type: 'MESSAGE_COMPLETE'; payload: { messageId: string; text: string } }
  | { type: 'RUN_COMPLETE'; payload: { messageId: string; runMeta: RunMeta } }
  | { type: 'ERROR'; payload: { messageId: string; message: string } }
  | { type: 'STATUS'; payload: { messageId: string; message: string } }
  | { type: 'SET_MESSAGES'; payload: Message[] }
  | { type: 'SET_SESSION'; payload: { sessionId: string } }
  | { type: 'SET_RUNNING'; payload: boolean }
  | { type: 'CLEAR' };
