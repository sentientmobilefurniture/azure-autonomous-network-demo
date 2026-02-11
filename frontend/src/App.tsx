import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import ReactMarkdown from 'react-markdown';

interface StepEvent {
  step: number;
  agent: string;
  duration?: string;
  query?: string;
  response?: string;
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
  const [finalMessage, setFinalMessage] = useState('');
  const [running, setRunning] = useState(false);

  const submitAlert = async () => {
    setSteps([]);
    setFinalMessage('');
    setRunning(true);

    try {
      const res = await fetch('/api/alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: alert }),
      });

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = '';
        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            const data = JSON.parse(line.slice(5).trim());
            if (currentEvent === 'step_complete') {
              setSteps((prev: StepEvent[]) => [...prev, data as StepEvent]);
            } else if (currentEvent === 'message') {
              setFinalMessage(data.text);
            } else if (currentEvent === 'error') {
              setFinalMessage(`**Error:** ${data.message}`);
            }
          }
        }
      }
    } catch (err) {
      console.error('SSE error:', err);
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
