import { motion } from 'framer-motion';
import clsx from 'clsx';

interface AlertInputProps {
  alert: string;
  onAlertChange: (value: string) => void;
  onSubmit: () => void;
  running: boolean;
}

export function AlertInput({ alert, onAlertChange, onSubmit, running }: AlertInputProps) {
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
