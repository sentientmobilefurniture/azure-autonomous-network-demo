import { motion } from 'framer-motion';

interface ErrorBannerProps {
  message: string;
  stepCount: number;
  onRetry: () => void;
}

export function ErrorBanner({ message, stepCount, onRetry }: ErrorBannerProps) {
  const lm = message.toLowerCase();
  let detail: string;
  let suggestion = '';

  if (message.includes('404')) {
    detail = 'A backend data source returned 404 — the graph database may be temporarily unavailable.';
    suggestion = 'Check that Fabric capacity is resumed and run Fabric Discovery from the Services panel.';
  } else if (message.includes('429')) {
    detail = 'Rate-limited by Azure AI. Wait a moment and retry.';
    suggestion = 'Consider reducing concurrent requests or upgrading model capacity.';
  } else if (message.includes('400')) {
    detail = 'A backend query returned an error. The graph schema or data may not match the query.';
  } else if (message.includes('503') || message.includes('502')) {
    detail = 'A backend service is temporarily unavailable (HTTP 502/503).';
    suggestion = 'Check that Fabric capacity is resumed, then run the Services health check.';
  } else if (message.includes('500')) {
    detail = 'Internal server error — the backend encountered an unexpected failure.';
    suggestion = 'Check the terminal logs for stack traces.';
  } else if (lm.includes('timeout') || lm.includes('timed out')) {
    detail = 'The investigation timed out — the backend took too long to respond.';
    suggestion = 'The query may be too complex or the backend is under heavy load. Try a simpler alert or retry.';
  } else if (lm.includes('econnrefused') || lm.includes('connection refused')) {
    detail = 'Connection refused — the backend service is not running.';
    suggestion = 'Ensure all services are started (api, graph-query-api). Check the terminal panel.';
  } else if (lm.includes('connection') && lm.includes('lost')) {
    detail = 'Connection to the server was lost — the investigation may still be running.';
    suggestion = 'Check the terminal logs and try again.';
  } else if (lm.includes('agent') && (lm.includes('not found') || lm.includes('missing'))) {
    detail = 'An agent was not found — it may not be provisioned.';
    suggestion = 'Run Agent Discovery from the Services panel to refresh the agent list.';
  } else {
    detail = `The orchestrator encountered an error: ${message.slice(0, 200)}`;
  }

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
          {suggestion && (
            <p className="text-xs text-brand/80 mt-1">💡 {suggestion}</p>
          )}
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
