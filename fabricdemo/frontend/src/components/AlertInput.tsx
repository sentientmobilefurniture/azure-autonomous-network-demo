import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import { useClickOutside } from '../hooks/useClickOutside';

interface AlertInputProps {
  alert: string;
  onAlertChange: (value: string) => void;
  onSubmit: () => void;
  running: boolean;
  exampleQuestions?: string[];
}

export function AlertInput({ alert, onAlertChange, onSubmit, running, exampleQuestions }: AlertInputProps) {
  const [examplesOpen, setExamplesOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useClickOutside(dropdownRef, () => setExamplesOpen(false), examplesOpen);

  const hasExamples = exampleQuestions && exampleQuestions.length > 0;

  return (
    <div className="glass-card p-4 mb-4">
      <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted block mb-2">
        Submit Alert
      </span>
      <textarea
        className="glass-input w-full rounded-lg p-3 text-sm text-text-primary placeholder-text-muted focus:outline-none resize-none"
        rows={2}
        value={alert}
        onChange={(e) => onAlertChange(e.target.value)}
        placeholder="Paste a NOC alert..."
      />

      <div className="mt-3 flex gap-2">
        {/* Examples dropdown button — opens upward */}
        {hasExamples && (
          <div ref={dropdownRef} className="relative">
            <button
              type="button"
              onClick={() => setExamplesOpen((v) => !v)}
              className={clsx(
                'py-2.5 px-3 text-sm font-medium rounded-lg transition-colors',
                'bg-neutral-bg3 border border-border hover:border-brand/40',
                'text-text-secondary hover:text-text-primary',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand',
                examplesOpen && 'border-brand/40 text-text-primary',
              )}
            >
              💡 Examples
            </button>

            <AnimatePresence>
              {examplesOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 8 }}
                  transition={{ duration: 0.15 }}
                  className="absolute bottom-full left-0 mb-2 w-72 max-h-56 overflow-y-auto
                    bg-neutral-bg2 border border-border rounded-lg shadow-xl z-50 p-1.5"
                >
                  {exampleQuestions!.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => {
                        onAlertChange(q);
                        setExamplesOpen(false);
                      }}
                      className="w-full text-left text-xs px-2.5 py-2 rounded-md
                        hover:bg-neutral-bg3 text-text-secondary hover:text-text-primary
                        transition-colors cursor-pointer"
                    >
                      "{q}"
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        <motion.button
          whileHover={{ scale: running ? 1 : 1.02 }}
          whileTap={{ scale: running ? 1 : 0.98 }}
          transition={{ type: 'spring', stiffness: 400, damping: 17 }}
          className={clsx(
            'flex-1 py-2.5 text-sm font-medium rounded-lg transition-colors',
            'bg-brand hover:bg-brand-hover text-white',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-white',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          )}
          onClick={onSubmit}
          disabled={running || !alert.trim()}
        >
          {running ? 'Investigating...' : 'Investigate'}
        </motion.button>
      </div>
    </div>
  );
}
