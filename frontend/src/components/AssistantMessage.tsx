import type { AssistantMessage as AssistantMessageType } from '../types/conversation';
import { ToolCallCard } from './ToolCallCard';
import { ActionCard } from './ActionCard';
import { ThinkingIndicator } from './ThinkingIndicator';
import { StreamingText } from './StreamingText';
import { DiagnosisBlock } from './DiagnosisBlock';

interface AssistantMessageProps {
  message: AssistantMessageType;
  onSave?: () => void;
}

export function AssistantMessage({ message, onSave }: AssistantMessageProps) {
  return (
    <div className="space-y-2">
      {/* Tool calls — progressive disclosure */}
      {message.toolCalls.map((tc) =>
        tc.isAction ? (
          <ActionCard key={tc.id} toolCall={tc} />
        ) : (
          <ToolCallCard key={tc.id} toolCall={tc} />
        ),
      )}

      {/* Thinking indicator — when pending with no tool calls yet */}
      {message.status === 'pending' && message.toolCalls.length === 0 && (
        <ThinkingIndicator />
      )}

      {/* Streaming text — token-by-token with cursor */}
      {message.streamingContent && !message.content && (
        <StreamingText text={message.streamingContent} />
      )}

      {/* Final diagnosis */}
      {message.content && <DiagnosisBlock text={message.content} />}

      {/* Error */}
      {message.errorMessage && (
        <div className="glass-card p-3 border-status-error/30 bg-status-error/5">
          <span className="text-xs text-status-error">
            ⚠ {message.errorMessage}
          </span>
        </div>
      )}

      {/* Status */}
      {message.statusMessage && (
        <div className="glass-card p-2 border-brand/20 bg-brand/5">
          <span className="text-xs text-brand">
            ℹ {message.statusMessage}
          </span>
        </div>
      )}

      {/* Run meta footer */}
      {message.runMeta && (
        <div className="flex items-center justify-between text-[10px] text-text-muted px-1">
          <span>
            {message.runMeta.steps} step
            {message.runMeta.steps !== 1 ? 's' : ''} · {message.runMeta.time}
          </span>
          <div className="flex gap-2">
            {onSave && (
              <button
                onClick={onSave}
                className="hover:text-text-primary transition-colors"
              >
                Save
              </button>
            )}
            <button
              onClick={() => navigator.clipboard.writeText(message.content)}
              className="hover:text-text-primary transition-colors"
            >
              Copy
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
