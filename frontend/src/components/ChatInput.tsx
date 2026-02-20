import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface ChatInputProps {
  onSubmit: (text: string) => void;
  onCancel: () => void;
  running: boolean;
  exampleQuestions?: string[];
}

export function ChatInput({ onSubmit, onCancel, running, exampleQuestions }: ChatInputProps) {
  const [text, setText] = useState('');
  const [examplesOpen, setExamplesOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

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

  // Close dropdown on outside click
  useEffect(() => {
    if (!examplesOpen) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setExamplesOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [examplesOpen]);

  const hasExamples = exampleQuestions && exampleQuestions.length > 0;

  return (
    <div className="shrink-0 border-t border-border p-3 bg-neutral-bg2">
      <div className="flex items-end gap-2">
        {/* Examples dropdown button */}
        {hasExamples && (
          <div ref={dropdownRef} className="relative">
            <button
              type="button"
              onClick={() => setExamplesOpen(v => !v)}
              className={`px-2.5 py-2 text-sm rounded-lg border transition-colors ${
                examplesOpen
                  ? 'border-brand/40 bg-brand/10 text-brand'
                  : 'border-border bg-neutral-bg3 text-text-muted hover:text-text-primary hover:border-brand/30'
              }`}
              title="Example questions"
            >
              💡
            </button>
            <AnimatePresence>
              {examplesOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 8 }}
                  transition={{ duration: 0.15 }}
                  className="absolute bottom-full left-0 mb-2 w-80 max-h-64 overflow-y-auto
                             bg-neutral-bg2 border border-border rounded-lg shadow-xl z-50 p-1.5"
                >
                  {exampleQuestions!.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => {
                        setText(q);
                        setExamplesOpen(false);
                        textareaRef.current?.focus();
                      }}
                      className="w-full text-left text-xs px-2.5 py-2 rounded-md
                                 hover:bg-neutral-bg3 text-text-secondary hover:text-text-primary
                                 transition-colors cursor-pointer"
                    >
                      💡 {q}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Text input */}
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

        {/* Submit / Cancel button */}
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
