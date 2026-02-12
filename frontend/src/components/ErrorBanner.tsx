import { motion } from 'framer-motion';

interface ErrorBannerProps {
  message: string;
  stepCount: number;
  onRetry: () => void;
}

export function ErrorBanner({ message, stepCount, onRetry }: ErrorBannerProps) {
  const detail = message.includes('404')
    ? 'A backend data source returned 404 — the graph database may be temporarily unavailable.'
    : message.includes('429')
      ? 'Rate-limited by Azure AI. Wait a moment and retry.'
      : message.includes('400')
        ? 'A backend query returned an error. The graph schema or data may not match the query.'
        : `The orchestrator encountered an error: ${message.slice(0, 200)}`;

  return (
    <motion.div
      className="glass-card p-4 border border-status-error/30"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25 }}
    >
      <div className="flex items-start gap-3">
        <span className="text-status-error text-lg leading-none mt-0.5">!</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-status-error mb-1">
            Agent run interrupted
          </p>
          <p className="text-xs text-text-muted">{detail}</p>
          {stepCount > 0 && (
            <p className="text-xs text-text-muted mt-1">
              {stepCount} step{stepCount > 1 ? 's' : ''} completed before the
              error — results shown above.
            </p>
          )}
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="mt-3 px-4 py-1.5 text-xs font-medium rounded-md bg-brand hover:bg-brand-hover text-white"
            onClick={onRetry}
          >
            Retry
          </motion.button>
        </div>
      </div>
    </motion.div>
  );
}
