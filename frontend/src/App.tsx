import { useState, useEffect } from 'react';

interface StepEvent {
  step: number;
  agent: string;
  duration?: string;
  query?: string;
  response?: string;
}

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
    <div className="min-h-screen p-8 max-w-4xl mx-auto">
      {/* Header */}
      <h1 className="text-2xl font-semibold mb-1">Autonomous Network NOC</h1>
      <p className="text-text-muted text-sm mb-8">Multi-agent diagnosis system</p>

      {/* Alert Input */}
      <div className="glass-card p-6 mb-6">
        <label className="text-sm font-medium text-text-secondary block mb-2">
          Alert
        </label>
        <textarea
          className="w-full bg-neutral-bg3 border border-border rounded-lg p-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-brand resize-none"
          rows={3}
          value={alert}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setAlert(e.target.value)}
          placeholder="Paste a NOC alert..."
        />
        <button
          className="mt-4 px-6 py-2 bg-brand hover:bg-brand-hover text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          onClick={submitAlert}
          disabled={running || !alert.trim()}
        >
          {running ? 'Running...' : 'Send Alert'}
        </button>
      </div>

      {/* Steps Timeline */}
      {steps.length > 0 && (
        <div className="glass-card p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Agent Steps</h2>
          <div className="space-y-3">
            {steps.map((s) => (
              <div key={s.step} className="border-l-2 border-brand pl-4">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-brand">Step {s.step}</span>
                  <span className="text-sm text-text-primary">{s.agent}</span>
                  {s.duration && (
                    <span className="text-xs text-text-muted">{s.duration}</span>
                  )}
                </div>
                {s.query && (
                  <p className="text-xs text-text-muted mt-1">Query: {s.query}</p>
                )}
                {s.response && (
                  <p className="text-xs text-text-secondary mt-1">Response: {s.response}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Final Response */}
      {finalMessage && (
        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold mb-4">Diagnosis</h2>
          <div className="text-sm text-text-secondary whitespace-pre-wrap">{finalMessage}</div>
        </div>
      )}

      {/* Health check indicator */}
      <div className="mt-8 text-xs text-text-muted">
        API: <HealthDot />
      </div>
    </div>
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
