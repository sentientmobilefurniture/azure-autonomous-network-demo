import type { ConversationState, ConversationAction } from '../types/conversation';

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
