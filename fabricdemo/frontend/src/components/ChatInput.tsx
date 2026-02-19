import { useState, useRef, useEffect } from 'react';

interface ChatInputProps {
  onSubmit: (text: string) => void;
  onCancel: () => void;
  running: boolean;
  exampleQuestions?: string[];
}

export function ChatInput({ onSubmit, onCancel, running }: ChatInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    if (!text.trim() || running) return;
    onSubmit(text.trim());
    setText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
  }, [text]);

  return (
    <div className="sticky bottom-0 z-40 border-t border-border p-3 bg-neutral-bg2">
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={running ? 'Investigation in progress...' : 'Ask a follow-up or paste a new alert...'}
          disabled={running}
          rows={1}
          className="flex-1 glass-input rounded-lg p-2.5 text-sm text-text-primary
                     placeholder-text-muted resize-none min-h-[2.5rem] max-h-[7.5rem]
                     focus:outline-none disabled:opacity-50"
        />

        {running ? (
          <button
            onClick={onCancel}
            className="px-3 py-2 text-sm rounded-lg bg-status-error/20 text-status-error
                       hover:bg-status-error/30 transition-colors"
            title="Cancel investigation"
          >
            ⏹
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!text.trim()}
            className="px-3 py-2 text-sm rounded-lg bg-brand text-white
                       hover:bg-brand-hover disabled:opacity-30
                       transition-colors"
            title="Send (Ctrl+Enter)"
          >
            ↑
          </button>
        )}
      </div>
    </div>
  );
}
