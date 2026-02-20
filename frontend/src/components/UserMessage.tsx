import { useState } from 'react';
import type { ChatMessage } from '../types';

interface UserMessageProps {
  message: ChatMessage;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

export function UserMessage({ message }: UserMessageProps) {
  const [expanded, setExpanded] = useState(false);
  const text = message.text ?? '';
  const isLong = text.length > 200;

  return (
    <div
      className={`glass-card p-3 transition-colors ${isLong ? 'cursor-pointer hover:border-brand/20' : ''}`}
      onClick={() => isLong && setExpanded(v => !v)}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] uppercase font-medium text-text-muted">You</span>
        <span className="text-[10px] text-text-muted">
          {formatTime(message.timestamp)}
        </span>
      </div>
      <p className={`text-sm text-text-primary whitespace-pre-wrap ${
        !expanded && isLong ? 'line-clamp-3' : ''
      }`}>
        {text}
      </p>
      {isLong && (
        <button
          className="text-[10px] text-text-muted hover:text-brand mt-1"
          onClick={(e) => { e.stopPropagation(); setExpanded(v => !v); }}
        >
          {expanded ? '▴ Collapse' : '▾ Show full alert'}
        </button>
      )}
    </div>
  );
}
