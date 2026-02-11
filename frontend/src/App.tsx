import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import ReactMarkdown from 'react-markdown';
import { fetchEventSource } from '@microsoft/fetch-event-source';

interface StepEvent {
  step: number;
  agent: string;
  duration?: string;
  query?: string;
  response?: string;
}

interface ThinkingState {
  agent: string;
  status: string;
}

// Animation variants
const fadeSlideUp = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 20 },
  transition: { duration: 0.3, ease: 'easeOut' as const },
};

const staggerContainer = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.05, delayChildren: 0.1 },
  },
};

const staggerItem = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.2, ease: 'easeOut' as const },
  },
};

export default function App() {
  const [alert, setAlert] = useState(
    '14:31:14.259 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down'
  );
  const [steps, setSteps] = useState<StepEvent[]>([]);
  const [thinking, setThinking] = useState<ThinkingState | null>(null);
  const [finalMessage, setFinalMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [running, setRunning] = useState(false);
  const [runStarted, setRunStarted] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const submitAlert = async () => {
    // Abort any previous run
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setSteps([]);
    setThinking(null);
    setFinalMessage('');
    setErrorMessage('');
    setRunning(true);
    setRunStarted(false);

    try {
      await fetchEventSource('/api/alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: alert }),
        signal: ctrl.signal,

        onopen: async (res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
        },

        onmessage: (ev) => {
          if (!ev.event || !ev.data) return;
          try {
            const data = JSON.parse(ev.data);
            switch (ev.event) {
              case 'run_start':
                setRunStarted(true);
                break;
              case 'step_thinking':
                setThinking(data as ThinkingState);
                break;
              case 'step_start':
                setThinking({ agent: data.agent, status: 'processing...' });
                break;
              case 'step_complete':
                setThinking(null);
                setSteps((prev) => [...prev, data as StepEvent]);
                break;
              case 'message':
                setThinking(null);
                setFinalMessage(data.text);
                break;
              case 'run_complete':
                setThinking(null);
                break;
              case 'error':
                setThinking(null);
                setErrorMessage(data.message);
                break;
            }
          } catch (parseErr) {
            console.warn('Failed to parse SSE data:', ev.data, parseErr);
          }
        },

        onerror: (err) => {
          console.error('SSE error:', err);
          // Don't retry — just let it close
          throw err;
        },

        // Keep the connection open until the server closes it
        openWhenHidden: true,
      });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      console.error('SSE stream error:', err);
    } finally {
      setRunning(false);
    }
  };

  return (
    <motion.div
      className="min-h-screen p-8 max-w-4xl mx-auto"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Header */}
      <h1 className="text-2xl font-semibold text-text-primary mb-1">Autonomous Network NOC</h1>
      <p className="text-text-muted text-sm mb-8">Multi-agent diagnosis system</p>

      {/* Alert Input */}
      <motion.div className="glass-card p-6 mb-6" {...fadeSlideUp}>
        <label className="text-sm font-medium text-text-secondary block mb-2">
          Alert
        </label>
        <textarea
          className="glass-input w-full rounded-lg p-3 text-sm text-text-primary placeholder-text-muted focus:outline-none resize-none"
          rows={3}
          value={alert}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setAlert(e.target.value)}
          placeholder="Paste a NOC alert..."
        />
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          transition={{ type: 'spring', stiffness: 400, damping: 17 }}
          className={clsx(
            'mt-4 px-6 py-2 text-sm font-medium rounded-lg transition-colors',
            'bg-brand hover:bg-brand-hover text-white',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-neutral-bg1',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
          onClick={submitAlert}
          disabled={running || !alert.trim()}
        >
          {running ? 'Running...' : 'Send Alert'}
        </motion.button>
      </motion.div>

      {/* Running indicator */}
      <AnimatePresence>
        {running && runStarted && steps.length === 0 && !thinking && (
          <motion.div
            className="glass-card p-6 mb-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
          >
            <div className="flex items-center gap-3">
              <div className="animate-pulse h-2 w-2 rounded-full bg-brand" />
              <span className="text-sm text-text-secondary">Orchestrator is starting...</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Steps Timeline */}
      <AnimatePresence>
        {steps.length > 0 && (
          <motion.div
            className="glass-card p-6 mb-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
          >
            <h2 className="text-lg font-semibold text-text-primary mb-4">Agent Steps</h2>
            <motion.div
              className="space-y-3"
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
            >
              {steps.map((s) => (
                <motion.div
                  key={s.step}
                  variants={staggerItem}
                  className="border-l-2 border-brand pl-4"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-brand">Step {s.step}</span>
                    <span className="text-sm text-text-primary">{s.agent}</span>
                    {s.duration && (
                      <span className="text-xs text-text-muted">{s.duration}</span>
                    )}
                  </div>
                  {s.query && (
                    <div className="text-xs text-text-muted mt-1">
                      <span className="font-medium">Query: </span>
                      <span className="inline prose prose-xs prose-invert max-w-none"><ReactMarkdown>{s.query}</ReactMarkdown></span>
                    </div>
                  )}
                  {s.response && (
                    <div className="text-xs text-text-secondary mt-2 prose prose-xs prose-invert max-w-none">
                      <span className="font-medium">Response:</span>
                      <ReactMarkdown>{s.response}</ReactMarkdown>
                    </div>
                  )}
                </motion.div>
              ))}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Thinking indicator */}
      <AnimatePresence>
        {thinking && (
          <motion.div
            className="glass-card p-4 mb-6"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            <div className="flex items-center gap-3">
              <div className="flex gap-1">
                <div className="animate-bounce h-1.5 w-1.5 rounded-full bg-brand" style={{ animationDelay: '0ms' }} />
                <div className="animate-bounce h-1.5 w-1.5 rounded-full bg-brand" style={{ animationDelay: '150ms' }} />
                <div className="animate-bounce h-1.5 w-1.5 rounded-full bg-brand" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-sm text-text-secondary">
                {thinking.agent} — {thinking.status}
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error banner */}
      <AnimatePresence>
        {errorMessage && (
          <motion.div
            className="glass-card p-5 mb-6 border border-status-error/30"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.25 }}
          >
            <div className="flex items-start gap-3">
              <span className="text-status-error text-lg leading-none mt-0.5">!</span>
              <div className="flex-1">
                <p className="text-sm font-medium text-status-error mb-1">Agent run interrupted</p>
                <p className="text-xs text-text-muted">
                  {errorMessage.includes('404')
                    ? 'A backend data source returned 404 — the Fabric graph model may still be refreshing after an ontology update. This usually resolves within 30–45 minutes.'
                    : errorMessage.includes('429')
                      ? 'Rate-limited by Azure AI. Wait a moment and retry.'
                      : errorMessage.includes('400')
                        ? 'A backend query returned an error. The graph schema or data may not match the query.'
                        : `The orchestrator encountered an error: ${errorMessage.slice(0, 200)}`
                  }
                </p>
                {steps.length > 0 && (
                  <p className="text-xs text-text-muted mt-1">
                    {steps.length} step{steps.length > 1 ? 's' : ''} completed before the error — results shown above.
                  </p>
                )}
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="mt-3 px-4 py-1.5 text-xs font-medium rounded-md bg-brand hover:bg-brand-hover text-white"
                  onClick={submitAlert}
                >
                  Retry
                </motion.button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Final Response */}
      <AnimatePresence>
        {finalMessage && (
          <motion.div
            className="glass-card p-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
          >
            <h2 className="text-lg font-semibold text-text-primary mb-4">Diagnosis</h2>
            <div className="text-sm text-text-secondary prose prose-sm prose-invert max-w-none">
              <ReactMarkdown>{finalMessage}</ReactMarkdown>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Health check indicator */}
      <div className="mt-8 text-xs text-text-muted">
        API: <HealthDot />
      </div>
    </motion.div>
  );
}

function HealthDot() {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    fetch('/health')
      .then((r) => setOk(r.ok))
      .catch(() => setOk(false));
  }, []);

  return (
    <span className={ok === null ? 'text-text-muted' : ok ? 'text-status-success' : 'text-status-error'}>
      {ok === null ? '...' : ok ? '● Connected' : '● Disconnected'}
    </span>
  );
}
