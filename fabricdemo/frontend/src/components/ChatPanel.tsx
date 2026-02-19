import type { ChatMessage, ThinkingState } from '../types';
import { UserBubble } from './UserBubble';
import { OrchestratorBubble } from './OrchestratorBubble';
import { ThinkingDots } from './ThinkingDots';
import { ChatInput } from './ChatInput';
import { EmptyState } from './EmptyState';

interface ChatPanelProps {
  messages: ChatMessage[];
  currentThinking: ThinkingState | null;
  running: boolean;
  onSubmit: (text: string) => void;
  onCancel: () => void;
  exampleQuestions?: string[];
}

export function ChatPanel({
  messages, currentThinking, running, onSubmit, onCancel, exampleQuestions,
}: ChatPanelProps) {
  return (
    <div className="flex flex-col">
      {/* Chat thread — participates in page scroll (no overflow-y-auto) */}
      <div className="p-4 space-y-4">
        {messages.length === 0 && (
          <EmptyState exampleQuestions={exampleQuestions} onSelect={onSubmit} />
        )}

        {messages.map((msg) =>
          msg.role === 'user'
            ? <UserBubble key={msg.id} message={msg} />
            : <OrchestratorBubble key={msg.id} message={msg} />
        )}

        {/* Live thinking indicator (not yet part of a message) */}
        {currentThinking && (
          <ThinkingDots agent={currentThinking.agent} status={currentThinking.status} />
        )}
      </div>

      {/* Bottom-pinned input */}
      <ChatInput
        onSubmit={onSubmit}
        onCancel={onCancel}
        running={running}
        exampleQuestions={exampleQuestions}
      />
    </div>
  );
}
