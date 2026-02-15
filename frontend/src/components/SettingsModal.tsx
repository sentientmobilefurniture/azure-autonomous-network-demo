import { useEffect, useRef, useState, useCallback } from 'react';
import { useScenarios } from '../hooks/useScenarios';
import { useScenarioContext } from '../context/ScenarioContext';

interface UploadBoxProps {
  label: string;
  icon: string;
  hint: string;
  endpoint: string;
  accept: string;
  onComplete?: () => void;
}

type ActionStatus = 'idle' | 'working' | 'done' | 'error';

function UploadBox({ label, icon, hint, endpoint, accept, onComplete }: UploadBoxProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [progress, setProgress] = useState('');
  const [pct, setPct] = useState(0);
  const [result, setResult] = useState('');

  const handleFile = useCallback(async (file: File) => {
    setStatus('uploading');
    setProgress('Uploading...');
    setPct(0);
    setResult('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(endpoint, { method: 'POST', body: formData });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      if (!reader) throw new Error('No response body');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const d = JSON.parse(line.slice(6));
              if ('pct' in d) { setProgress(d.detail || d.step); setPct(d.pct); }
              if ('error' in d) { setStatus('error'); setResult(d.error); return; }
              if ('scenario' in d || 'index' in d || 'database' in d || 'graph' in d) {
                setStatus('done');
                setResult(JSON.stringify(d));
                onComplete?.();
              }
            } catch { /* skip */ }
          }
        }
      }
      if (status !== 'done' && status !== 'error') setStatus('done');
    } catch (e) {
      setStatus('error');
      setResult(String(e));
    }
  }, [endpoint, onComplete]);

  return (
    <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <span className="text-sm font-medium text-text-primary">{label}</span>
        {status === 'done' && <span className="text-xs text-status-success ml-auto">✓</span>}
        {status === 'error' && <span className="text-xs text-status-error ml-auto">✗</span>}
      </div>

      {status === 'idle' && (
        <div
          className="border border-dashed border-white/20 hover:border-white/40 rounded p-3 text-center cursor-pointer transition-colors"
          onClick={() => inputRef.current?.click()}
        >
          <p className="text-xs text-text-muted">{hint}</p>
          <input ref={inputRef} type="file" accept={accept} className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
        </div>
      )}

      {status === 'uploading' && (
        <div className="space-y-1">
          <div className="w-full bg-neutral-bg2 rounded-full h-1.5">
            <div className="bg-brand h-1.5 rounded-full transition-all" style={{ width: `${Math.max(pct, 5)}%` }} />
          </div>
          <p className="text-xs text-text-muted truncate">{progress}</p>
        </div>
      )}

      {status === 'done' && (
        <div className="text-xs text-status-success">
          Loaded successfully
          <button onClick={() => setStatus('idle')} className="ml-2 text-brand hover:text-brand/80">
            Upload again
          </button>
        </div>
      )}

      {status === 'error' && (
        <div className="text-xs text-status-error">
          {result.substring(0, 120)}
          <button onClick={() => setStatus('idle')} className="ml-2 text-brand hover:text-brand/80">
            Retry
          </button>
        </div>
      )}
    </div>
  );
}

function ActionButton({ label, icon, description, onClick }: {
  label: string;
  icon: string;
  description: string;
  onClick: () => Promise<string>;
}) {
  const [status, setStatus] = useState<ActionStatus>('idle');
  const [result, setResult] = useState('');

  const handleClick = useCallback(async () => {
    setStatus('working');
    setResult('');
    try {
      const msg = await onClick();
      setResult(msg);
      setStatus('done');
    } catch (e) {
      setResult(String(e));
      setStatus('error');
    }
  }, [onClick]);

  return (
    <button
      onClick={handleClick}
      disabled={status === 'working'}
      className={`flex-1 p-3 rounded-lg border text-left transition-colors ${
        status === 'done' ? 'border-status-success/30 bg-status-success/5' :
        status === 'error' ? 'border-status-error/30 bg-status-error/5' :
        status === 'working' ? 'border-brand/30 bg-brand/5 animate-pulse' :
        'border-white/10 bg-neutral-bg1 hover:border-white/20'
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span>{icon}</span>
        <span className="text-sm font-medium text-text-primary">{label}</span>
        {status === 'done' && <span className="text-xs text-status-success ml-auto">✓</span>}
        {status === 'error' && <span className="text-xs text-status-error ml-auto">✗</span>}
        {status === 'working' && <span className="text-xs text-text-muted ml-auto">...</span>}
      </div>
      <p className="text-xs text-text-muted">
        {status === 'done' ? result : status === 'error' ? result.substring(0, 80) : description}
      </p>
    </button>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
}

type Tab = 'datasources' | 'upload';

export function SettingsModal({ open, onClose }: Props) {
  const {
    scenarios,
    indexes,
    loading,
    error,
    fetchScenarios,
    fetchIndexes,
  } = useScenarios();

  const {
    activeGraph,
    activeRunbooksIndex,
    activeTicketsIndex,
    setActiveGraph,
    setActiveRunbooksIndex,
    setActiveTicketsIndex,
  } = useScenarioContext();

  const [tab, setTab] = useState<Tab>('datasources');

  useEffect(() => {
    if (open) {
      fetchScenarios();
      fetchIndexes();
    }
  }, [open, fetchScenarios, fetchIndexes]);

  if (!open) return null;

  const graphScenarios = scenarios.filter(s => s.has_data);
  const runbookIndexes = indexes.filter(i => i.type === 'runbooks');
  const ticketIndexes = indexes.filter(i => i.type === 'tickets');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-neutral-bg2 border border-white/10 rounded-xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl">
        {/* Header with tabs */}
        <div className="border-b border-white/10">
          <div className="flex items-center justify-between px-6 pt-4 pb-0">
            <h2 className="text-lg font-semibold text-text-primary">Settings</h2>
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary transition-colors text-xl leading-none"
            >
              ✕
            </button>
          </div>
          <div className="flex px-6 mt-3 gap-1">
            {(['datasources', 'upload'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm rounded-t-md transition-colors ${
                  tab === t
                    ? 'bg-neutral-bg1 text-text-primary border-t border-x border-white/10'
                    : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                {t === 'datasources' ? 'Data Sources' : 'Upload'}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* ── Data Sources Tab ──────────────────────────────────── */}
          {tab === 'datasources' && (
            <>
              <p className="text-xs text-text-muted">
                Each agent reads from an independent data source. Graph switching
                is instant. Search index changes take ~30s (agents re-provision).
              </p>

              {/* Agent → Data Source bindings */}
              <div className="space-y-4">
                {/* GraphExplorer → Graph */}
                <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-blue-400" />
                    <span className="text-sm font-medium text-text-primary">GraphExplorer Agent</span>
                  </div>
                  <div>
                    <label className="text-xs text-text-muted block mb-1">Cosmos Graph</label>
                    <select
                      value={activeGraph}
                      onChange={(e) => setActiveGraph(e.target.value)}
                      className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary"
                    >
                      {graphScenarios.length === 0 && (
                        <option value="topology">topology (default)</option>
                      )}
                      {graphScenarios.map((s) => (
                        <option key={s.graph_name} value={s.graph_name}>
                          {s.graph_name} ({s.vertex_count} vertices)
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Telemetry → NoSQL Database */}
                <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-purple-400" />
                    <span className="text-sm font-medium text-text-primary">Telemetry Agent</span>
                  </div>
                  <div>
                    <label className="text-xs text-text-muted block mb-1">Cosmos NoSQL Database</label>
                    <div className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-secondary">
                      {activeGraph.includes('-') ? `${activeGraph.substring(0, activeGraph.lastIndexOf('-'))}-telemetry` : 'telemetry'}
                    </div>
                    <p className="text-xs text-text-muted mt-1">
                      Auto-derived from Graph selection above
                    </p>
                  </div>
                </div>

                {/* RunbookKB → Search Index */}
                <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-green-400" />
                    <span className="text-sm font-medium text-text-primary">RunbookKB Agent</span>
                  </div>
                  <div>
                    <label className="text-xs text-text-muted block mb-1">AI Search Index</label>
                    <select
                      value={activeRunbooksIndex}
                      onChange={(e) => setActiveRunbooksIndex(e.target.value)}
                      className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary"
                    >
                      <option value="runbooks-index">runbooks-index (default)</option>
                      {runbookIndexes.map((idx) => (
                        <option key={idx.name} value={idx.name}>
                          {idx.name} ({idx.document_count ?? '?'} docs)
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* HistoricalTicket → Search Index */}
                <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-yellow-400" />
                    <span className="text-sm font-medium text-text-primary">HistoricalTicket Agent</span>
                  </div>
                  <div>
                    <label className="text-xs text-text-muted block mb-1">AI Search Index</label>
                    <select
                      value={activeTicketsIndex}
                      onChange={(e) => setActiveTicketsIndex(e.target.value)}
                      className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary"
                    >
                      <option value="tickets-index">tickets-index (default)</option>
                      {ticketIndexes.map((idx) => (
                        <option key={idx.name} value={idx.name}>
                          {idx.name} ({idx.document_count ?? '?'} docs)
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              {error && <p className="text-xs text-status-error">{error}</p>}

              {/* Action buttons */}
              <div className="flex gap-3">
                <ActionButton
                  label="Load Topology"
                  icon="🔗"
                  description={`Reload graph from ${activeGraph}`}
                  onClick={async () => {
                    // Trigger a topology refetch by posting to /query/topology with X-Graph
                    const res = await fetch('/query/topology', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json', 'X-Graph': activeGraph },
                      body: JSON.stringify({}),
                    });
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    const data = await res.json();
                    if (data.error) throw new Error(data.error);
                    return `${data.meta?.node_count ?? '?'} nodes, ${data.meta?.edge_count ?? '?'} edges`;
                  }}
                />
                <ActionButton
                  label="Provision Agents"
                  icon="🤖"
                  description={`Bind agents to selected data sources`}
                  onClick={async () => {
                    const res = await fetch('/api/config/apply', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        graph: activeGraph,
                        runbooks_index: activeRunbooksIndex,
                        tickets_index: activeTicketsIndex,
                      }),
                    });
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    // Read SSE stream for progress
                    const reader = res.body?.getReader();
                    const decoder = new TextDecoder();
                    let lastMsg = '';
                    if (reader) {
                      let buf = '';
                      while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        buf += decoder.decode(value, { stream: true });
                        const lines = buf.split('\n');
                        buf = lines.pop() || '';
                        for (const line of lines) {
                          if (line.startsWith('data: ')) {
                            try {
                              const d = JSON.parse(line.slice(6));
                              if (d.detail) lastMsg = d.detail;
                              if (d.error) throw new Error(d.error);
                            } catch (e) {
                              if (e instanceof Error && e.message !== 'Unexpected') throw e;
                            }
                          }
                        }
                      }
                    }
                    return lastMsg || 'Agents provisioned';
                  }}
                />
              </div>
            </>
          )}

          {/* ── Upload Tab ────────────────────────────────────────── */}
          {tab === 'upload' && (
            <>
              {/* Loaded scenarios list */}
              <div>
                <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
                  Loaded Data
                </h3>
                {loading ? (
                  <p className="text-text-muted text-sm">Loading...</p>
                ) : scenarios.length === 0 ? (
                  <p className="text-text-muted text-sm">No graphs loaded yet.</p>
                ) : (
                  <div className="space-y-2">
                    {scenarios.filter(s => s.has_data).map((s) => (
                      <div
                        key={s.graph_name}
                        className="flex items-center justify-between px-4 py-2 bg-neutral-bg1 rounded-lg border border-white/5"
                      >
                        <div className="flex items-center gap-3">
                          <span className="h-2 w-2 rounded-full bg-status-success" />
                          <span className="text-sm text-text-primary font-medium">{s.graph_name}</span>
                        </div>
                        <span className="text-xs text-text-muted">{s.vertex_count} vertices</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 4 independent upload areas */}
              <div className="grid grid-cols-2 gap-3">
                <UploadBox
                  label="Graph Data"
                  icon="🔗"
                  hint="scenario.yaml + graph_schema.yaml + data/entities/*.csv"
                  endpoint="/query/upload/graph"
                  accept=".tar.gz,.tgz"
                  onComplete={() => fetchScenarios()}
                />
                <UploadBox
                  label="Telemetry"
                  icon="📊"
                  hint="scenario.yaml + data/telemetry/*.csv"
                  endpoint="/query/upload/telemetry"
                  accept=".tar.gz,.tgz"
                />
                <UploadBox
                  label="Runbooks"
                  icon="📋"
                  hint=".md runbook files → AI Search"
                  endpoint="/query/upload/runbooks"
                  accept=".tar.gz,.tgz"
                  onComplete={() => fetchIndexes()}
                />
                <UploadBox
                  label="Tickets"
                  icon="🎫"
                  hint=".txt ticket files → AI Search"
                  endpoint="/query/upload/tickets"
                  accept=".tar.gz,.tgz"
                  onComplete={() => fetchIndexes()}
                />
              </div>

              <p className="text-xs text-text-muted">
                Generate tarballs: <code>./data/generate_all.sh</code>
              </p>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-white/10 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-sm text-text-primary bg-white/10 hover:bg-white/15 rounded-md transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
