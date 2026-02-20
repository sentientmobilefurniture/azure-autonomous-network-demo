# Task 02: New Types & Reducer

> **Phase**: B (Rebuild)
> **Prerequisite**: Task 01 (scorched earth)
> **Output**: `execution/task_02_types_reducer_execution_log.md`

## Goal

Define the new TypeScript type system and pure reducer function. This is the foundation that all other Phase B tasks build on.

## Files to Create

### `frontend/src/types/conversation.ts`

The single source of truth for all conversation types.

```typescript
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
```

Import `VisualizationData`, `ActionData`, `RunMeta` from `./index` (the surviving types).

### `frontend/src/reducers/conversationReducer.ts`

Pure reducer function:

```typescript
import type { ConversationState, ConversationAction, AssistantMessage } from '../types/conversation';

export const initialState: ConversationState = {
  messages: [],
  running: false,
  activeSessionId: null,
};

export function conversationReducer(
  state: ConversationState,
  action: ConversationAction,
): ConversationState {
  switch (action.type) {
    case 'ADD_USER_MESSAGE':
      return {
        ...state,
        messages: [...state.messages, {
          kind: 'user',
          id: action.payload.id,
          text: action.payload.text,
          timestamp: action.payload.timestamp,
        }],
      };

    case 'ADD_ASSISTANT_MESSAGE':
      return {
        ...state,
        messages: [...state.messages, {
          kind: 'assistant',
          id: action.payload.id,
          timestamp: action.payload.timestamp,
          toolCalls: [],
          content: '',
          streamingContent: '',
          status: 'pending',
        }],
      };

    case 'TOOL_CALL_START':
      return {
        ...state,
        messages: state.messages.map(msg =>
          msg.kind === 'assistant' && msg.id === action.payload.messageId
            ? { ...msg, toolCalls: [...msg.toolCalls, action.payload.toolCall], status: 'streaming' as const }
            : msg
        ),
      };

    case 'TOOL_CALL_COMPLETE':
      return {
        ...state,
        messages: state.messages.map(msg =>
          msg.kind === 'assistant' && msg.id === action.payload.messageId
            ? {
                ...msg,
                toolCalls: msg.toolCalls.map(tc =>
                  tc.id === action.payload.toolCallId
                    ? { ...tc, ...action.payload.data, status: 'complete' as const }
                    : tc
                ),
              }
            : msg
        ),
      };

    case 'MESSAGE_DELTA':
      return {
        ...state,
        messages: state.messages.map(msg =>
          msg.kind === 'assistant' && msg.id === action.payload.messageId
            ? { ...msg, streamingContent: msg.streamingContent + action.payload.text, status: 'streaming' as const }
            : msg
        ),
      };

    case 'MESSAGE_COMPLETE':
      return {
        ...state,
        messages: state.messages.map(msg =>
          msg.kind === 'assistant' && msg.id === action.payload.messageId
            ? { ...msg, content: action.payload.text, streamingContent: '', status: 'complete' as const }
            : msg
        ),
      };

    case 'RUN_COMPLETE':
      return {
        ...state,
        running: false,
        messages: state.messages.map(msg =>
          msg.kind === 'assistant' && msg.id === action.payload.messageId
            ? { ...msg, runMeta: action.payload.runMeta, status: 'complete' as const }
            : msg
        ),
      };

    case 'ERROR':
      return {
        ...state,
        running: false,
        messages: state.messages.map(msg =>
          msg.kind === 'assistant' && msg.id === action.payload.messageId
            ? { ...msg, errorMessage: action.payload.message, status: 'error' as const }
            : msg
        ),
      };

    case 'STATUS':
      return {
        ...state,
        messages: state.messages.map(msg =>
          msg.kind === 'assistant' && msg.id === action.payload.messageId
            ? { ...msg, statusMessage: action.payload.message }
            : msg
        ),
      };

    case 'SET_MESSAGES':
      return { ...state, messages: action.payload };

    case 'SET_SESSION':
      return { ...state, activeSessionId: action.payload.sessionId };

    case 'SET_RUNNING':
      return { ...state, running: action.payload };

    case 'CLEAR':
      return initialState;

    default:
      return state;
  }
}
```

## Files to Update

### `frontend/src/types/index.ts`

After Task 01 gutted this file, add re-exports so consumers can still import from `'../types'`:

```typescript
// Re-export conversation types for convenience
export type {
  Message, UserMessage, AssistantMessage,
  ToolCall, ToolCallStatus, SubStep,
  ConversationState, ConversationAction,
} from './conversation';
```

### `frontend/src/hooks/useAutoScroll.ts`

Update type imports:
- `ChatMessage` → `Message`
- Remove `ThinkingState` parameter (status is now on the message itself)

### `frontend/src/components/UserMessage.tsx`

Update prop type:
- `ChatMessage` → `UserMessage` (from `'../types/conversation'`)

### `frontend/src/components/SubStepList.tsx`

Update prop type:
- `SubStepEvent` → `SubStep` (from `'../types/conversation'`)
- `ss.result_summary` → `ss.resultSummary` (camelCase)

### `frontend/src/components/ActionCard.tsx`

Update prop type:
- `StepEvent` → `ToolCall` (from `'../types/conversation'`)

### `frontend/src/hooks/useVisualization.ts`

Update type:
- `StepEvent` → `ToolCall` (from `'../types/conversation'`)
- Field access: `step.visualization` → `tc.visualizations?.[0]` (no legacy single viz)
- `step.visualizations` → `tc.visualizations`
- `step.response` → `tc.response`
- `step.agent` → `tc.agent`

### `frontend/src/components/visualization/StepVisualizationModal.tsx`

Update:
- `StepEvent` → `ToolCall`
- `ThinkingDots` → inline spinner or simple loading indicator (ThinkingDots is deleted)

## Completion Criteria

- [ ] `frontend/src/types/conversation.ts` created with all types
- [ ] `frontend/src/reducers/conversationReducer.ts` created with pure reducer
- [ ] `frontend/src/types/index.ts` re-exports new types
- [ ] `useAutoScroll.ts` compiles with new types
- [ ] `UserMessage.tsx` compiles with new `UserMessage` type
- [ ] `SubStepList.tsx` compiles with new `SubStep` type
- [ ] `ActionCard.tsx` compiles with new `ToolCall` type
- [ ] `useVisualization.ts` compiles with new `ToolCall` type
- [ ] `StepVisualizationModal.tsx` compiles (no ThinkingDots, new types)
- [ ] `npx tsc --noEmit` — errors only in files not yet rebuilt (App.tsx, missing hook/components)
