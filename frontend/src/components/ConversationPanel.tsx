import type { Message } from '../types/conversation';
import { UserMessage } from './UserMessage';
import { AssistantMessage } from './AssistantMessage';

interface ConversationPanelProps {
  messages: Message[];
  onSave?: () => void;
}

export function ConversationPanel({ messages, onSave }: ConversationPanelProps) {
  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted text-sm">
        <div className="text-center space-y-2">
          <span className="text-2xl">💬</span>
          <p>Select or start an investigation to begin.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 py-3">
      {messages.map((msg) =>
        msg.kind === 'user' ? (
          <UserMessage key={msg.id} message={msg} />
        ) : (
          <AssistantMessage key={msg.id} message={msg} onSave={onSave} />
        ),
      )}
    </div>
  );
}
