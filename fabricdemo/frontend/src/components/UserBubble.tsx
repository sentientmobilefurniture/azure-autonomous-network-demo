import type { ChatMessage } from '../types';

interface UserBubbleProps {
  message: ChatMessage;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

export function UserBubble({ message }: UserBubbleProps) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] glass-card p-3 bg-brand/8 border-brand/20">
        <span className="text-[10px] uppercase text-brand/60 block mb-1">You</span>
        <p className="text-sm text-text-primary whitespace-pre-wrap">{message.text}</p>
        <span className="text-[10px] text-text-muted mt-1 block">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
}
