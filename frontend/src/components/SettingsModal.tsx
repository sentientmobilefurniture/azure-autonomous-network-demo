import { useEffect, useRef, useState, useCallback } from 'react';
import { useScenarios } from '../hooks/useScenarios';
import { useScenarioContext } from '../context/ScenarioContext';
import { AddScenarioModal } from './AddScenarioModal';
import { consumeSSE } from '../utils/sseStream';

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

type Tab = 'scenarios' | 'datasources' | 'upload';

export function SettingsModal({ open, onClose }: Props) {
  const {
    scenarios,
    indexes,
    loading,
    error,
    fetchScenarios,
    fetchIndexes,
    savedScenarios,
    savedLoading,
    fetchSavedScenarios,
    saveScenario,
    deleteSavedScenario,
    selectScenario,
  } = useScenarios();

  const {
    activeScenario,
    activeGraph,
    activeRunbooksIndex,
    activeTicketsIndex,
    activePromptSet,
    setActiveScenario,
    setActiveGraph,
    setActiveRunbooksIndex,
    setActiveTicketsIndex,
    setActivePromptSet,
  } = useScenarioContext();

  const [tab, setTab] = useState<Tab>('scenarios');
  const [promptScenarios, setPromptScenarios] = useState<{scenario: string; prompt_count: number}[]>([]);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      fetchScenarios();
      fetchIndexes();
      fetchSavedScenarios();
      // Fetch available prompt sets
      fetch('/query/prompts/scenarios')
        .then(r => r.json())
        .then(d => {
          setPromptScenarios(d.prompt_scenarios || []);
          if (!activePromptSet && d.prompt_scenarios?.length) {
            setActivePromptSet(d.prompt_scenarios[0].scenario);
          }
        })
        .catch(() => {});
    }
  }, [open, fetchScenarios, fetchIndexes, fetchSavedScenarios, activePromptSet, setActivePromptSet]);

  if (!open) return null;

  const graphScenarios = scenarios.filter(s => s.has_data);
  const runbookIndexes = indexes.filter(i => i.type === 'runbooks');
  const ticketIndexes = indexes.filter(i => i.type === 'tickets');

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <>
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleBackdropClick}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
    >
      <div className="bg-neutral-bg2 border border-white/10 rounded-xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl" role="dialog" aria-modal="true">
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
            {(['scenarios', 'datasources', 'upload'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm rounded-t-md transition-colors ${
                  tab === t
                    ? 'bg-neutral-bg1 text-text-primary border-t border-x border-white/10'
                    : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                {t === 'scenarios' ? 'Scenarios' : t === 'datasources' ? 'Data Sources' : 'Upload'}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* ── Scenarios Tab ──────────────────────────────────── */}
          {tab === 'scenarios' && (
            <>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider">
                  Saved Scenarios
                </h3>
                <button
                  onClick={() => setAddModalOpen(true)}
                  className="text-xs bg-brand/20 text-brand hover:bg-brand/30 px-3 py-1 rounded-md transition-colors"
                >
                  + New Scenario
                </button>
              </div>

              {savedLoading ? (
                <p className="text-text-muted text-sm">Loading...</p>
              ) : savedScenarios.length === 0 ? (
                <div className="border border-dashed border-white/10 rounded-lg p-6 text-center">
                  <p className="text-sm text-text-muted">No scenarios yet</p>
                  <p className="text-xs text-text-muted mt-1">
                    Click "+ New Scenario" to create your first scenario data pack.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {savedScenarios.map((sc) => {
                    const isActive = activeScenario === sc.id;
                    return (
                      <div
                        key={sc.id}
                        onClick={() => { if (!isActive) selectScenario(sc.id); }}
                        className={`p-4 rounded-lg border transition-colors cursor-pointer ${
                          isActive
                            ? 'border-status-success/40 bg-status-success/5'
                            : 'border-white/10 bg-neutral-bg1 hover:border-white/20'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <span className={`h-3 w-3 rounded-full border-2 flex items-center justify-center ${
                              isActive ? 'border-status-success' : 'border-white/30'
                            }`}>
                              {isActive && <span className="h-1.5 w-1.5 rounded-full bg-status-success" />}
                            </span>
                            <div>
                              <span className="text-sm font-medium text-text-primary">
                                {sc.display_name || sc.id}
                              </span>
                              {isActive && (
                                <span className="ml-2 text-[10px] bg-status-success/20 text-status-success px-1.5 py-0.5 rounded">
                                  Active
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="relative">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setDeleteConfirm(deleteConfirm === sc.id ? null : sc.id);
                              }}
                              className="text-text-muted hover:text-text-primary text-sm px-1"
                            >
                              ⋮
                            </button>
                            {deleteConfirm === sc.id && (
                              <div className="absolute right-0 top-6 bg-neutral-bg2 border border-white/10 rounded-lg shadow-xl p-3 z-10 min-w-[180px]">
                                <p className="text-xs text-text-muted mb-2">Delete "{sc.id}"?</p>
                                <p className="text-[10px] text-text-muted mb-3">
                                  This removes the record only. Azure resources will remain.
                                </p>
                                <div className="flex gap-2">
                                  <button
                                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(null); }}
                                    className="text-[10px] px-2 py-1 bg-white/10 rounded hover:bg-white/15 text-text-primary"
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    onClick={async (e) => {
                                      e.stopPropagation();
                                      await deleteSavedScenario(sc.id);
                                      if (activeScenario === sc.id) setActiveScenario(null);
                                      setDeleteConfirm(null);
                                    }}
                                    className="text-[10px] px-2 py-1 bg-status-error/80 rounded hover:bg-status-error text-white"
                                  >
                                    Delete
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                        {sc.description && (
                          <p className="text-xs text-text-muted mt-1 ml-6">{sc.description}</p>
                        )}
                        <div className="flex gap-3 mt-2 ml-6 text-[10px] text-text-muted">
                          {sc.upload_status?.graph?.status === 'complete' && (
                            <span>{String((sc.upload_status.graph as Record<string,unknown>)?.vertices ?? '?')} vertices</span>
                          )}
                          {sc.upload_status?.prompts?.status === 'complete' && (
                            <span>{String((sc.upload_status.prompts as Record<string,unknown>)?.prompts_stored ?? '?')} prompts</span>
                          )}
                          <span>Updated {new Date(sc.updated_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {/* ── Data Sources Tab ──────────────────────────────────── */}
          {tab === 'datasources' && (
            <>
              {/* Scenario-derived read-only bindings */}
              {activeScenario ? (
                <>
                  <div className="bg-neutral-bg1 rounded-lg border border-status-success/20 p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-text-primary">
                        Active Scenario: {activeScenario}
                      </span>
                      <button
                        onClick={() => setActiveScenario(null)}
                        className="text-[10px] text-brand hover:text-brand/80"
                      >
                        Switch to Custom mode
                      </button>
                    </div>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-text-muted">GraphExplorer</span>
                        <span className="text-text-secondary">{activeGraph}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">Telemetry</span>
                        <span className="text-text-secondary">
                          {activeGraph.includes('-') ? `${activeGraph.substring(0, activeGraph.lastIndexOf('-'))}-telemetry` : 'telemetry'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">RunbookKB</span>
                        <span className="text-text-secondary">{activeRunbooksIndex}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">Tickets</span>
                        <span className="text-text-secondary">{activeTicketsIndex}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">Prompts</span>
                        <span className="text-text-secondary">{activePromptSet || '(none)'}</span>
                      </div>
                    </div>
                    <p className="text-[10px] text-text-muted">
                      All bindings auto-derived from scenario name.
                    </p>
                  </div>

                  {/* Re-provision button */}
                  <div className="flex gap-3">
                    <ActionButton
                      label="Re-provision Agents"
                      icon="🤖"
                      description={`Rebind agents to ${activeScenario} data sources`}
                      onClick={async () => {
                        const res = await fetch('/api/config/apply', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                            graph: activeGraph,
                            runbooks_index: activeRunbooksIndex,
                            tickets_index: activeTicketsIndex,
                            prompt_scenario: activePromptSet || undefined,
                          }),
                        });
                        if (!res.ok) throw new Error(`HTTP ${res.status}`);
                        let lastMsg = '';
                        await consumeSSE(res, {
                          onProgress: (d) => { lastMsg = d.detail; },
                          onError: (d) => { throw new Error(d.error); },
                        });
                        return lastMsg || 'Agents provisioned';
                      }}
                    />
                  </div>
                </>
              ) : (
                /* Custom mode — full dropdowns */
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

              {/* Prompt Set selection */}
              <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-pink-400" />
                  <span className="text-sm font-medium text-text-primary">Prompt Set</span>
                </div>
                <div>
                  <label className="text-xs text-text-muted block mb-1">Agent Prompts (from Cosmos)</label>
                  <select
                    value={activePromptSet}
                    onChange={(e) => setActivePromptSet(e.target.value)}
                    className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary"
                  >
                    {promptScenarios.length === 0 && (
                      <option value="">No prompts uploaded yet</option>
                    )}
                    {promptScenarios.map((ps) => (
                      <option key={ps.scenario} value={ps.scenario}>
                        {ps.scenario} ({ps.prompt_count} prompts)
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-text-muted mt-1">
                    Upload prompts via the Upload tab, then select the set here
                  </p>
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
                        prompt_scenario: activePromptSet || undefined,
                      }),
                    });
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    let lastMsg = '';
                    await consumeSSE(res, {
                      onProgress: (d) => { lastMsg = d.detail; },
                      onError: (d) => { throw new Error(d.error); },
                    });
                    return lastMsg || 'Agents provisioned';
                  }}
                />
              </div>
            </>
              )}
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
                <UploadBox
                  label="Prompts"
                  icon="📝"
                  hint=".md prompt files → Cosmos DB"
                  endpoint="/query/upload/prompts"
                  accept=".tar.gz,.tgz"
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
    <AddScenarioModal
      open={addModalOpen}
      onClose={() => setAddModalOpen(false)}
      onSaved={() => fetchSavedScenarios()}
      existingNames={savedScenarios.map(s => s.id)}
      saveScenarioMeta={saveScenario}
    />
    </>
  );
}
