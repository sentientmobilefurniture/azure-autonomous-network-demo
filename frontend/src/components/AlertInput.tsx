import { motion } from 'framer-motion';
import clsx from 'clsx';

interface AlertInputProps {
  alert: string;
  onAlertChange: (value: string) => void;
  onSubmit: () => void;
  running: boolean;
  exampleQuestions?: string[];
}

export function AlertInput({ alert, onAlertChange, onSubmit, running, exampleQuestions }: AlertInputProps) {
  const showChips = !alert.trim() && exampleQuestions && exampleQuestions.length > 0;

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

      {/* Example question suggestion chips — visible only when textarea is empty */}
      {showChips && (
        <div className="mt-2">
          <span className="text-[10px] uppercase tracking-wider text-text-muted block mb-1.5">
            Try an example
          </span>
          <div className="flex flex-wrap gap-1.5">
            {exampleQuestions.map((q, i) => (
              <button
                key={i}
                onClick={() => onAlertChange(q)}
                className="text-left text-xs px-2.5 py-1.5 rounded-md
                  bg-white/5 border border-white/10 hover:border-brand/40
                  text-text-secondary hover:text-text-primary transition-all
                  cursor-pointer max-w-full"
              >
                <span className="line-clamp-1">"{q}"</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <motion.button
        whileHover={{ scale: running ? 1 : 1.02 }}
        whileTap={{ scale: running ? 1 : 0.98 }}
        transition={{ type: 'spring', stiffness: 400, damping: 17 }}
        className={clsx(
          'mt-3 w-full py-2.5 text-sm font-medium rounded-lg transition-colors',
          'bg-brand hover:bg-brand-hover text-white',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-neutral-bg1',
          'disabled:opacity-50 disabled:cursor-not-allowed',
        )}
        onClick={onSubmit}
        disabled={running || !alert.trim()}
      >
        {running ? 'Investigating...' : 'Investigate'}
      </motion.button>
    </div>
  );
}
