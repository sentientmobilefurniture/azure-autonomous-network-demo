import type { ScenarioInfo, SearchIndex } from '../../hooks/useScenarios';
import { ActionButton } from '../ActionButton';
import { BindingCard } from '../BindingCard';
import { consumeSSE } from '../../utils/sseStream';

interface DataSourceSettingsTabProps {
  activeScenario: string | null;
  activeGraph: string;
  activeRunbooksIndex: string;
  activeTicketsIndex: string;
  activePromptSet: string;
  setActiveScenario: (id: string | null) => void;
  setActiveGraph: (v: string) => void;
  setActiveRunbooksIndex: (v: string) => void;
  setActiveTicketsIndex: (v: string) => void;
  setActivePromptSet: (v: string) => void;
  graphScenarios: ScenarioInfo[];
  runbookIndexes: SearchIndex[];
  ticketIndexes: SearchIndex[];
  promptScenarios: { scenario: string; prompt_count: number }[];
  error: string | null;
}

export function DataSourceSettingsTab({
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
  graphScenarios,
  runbookIndexes,
  ticketIndexes,
  promptScenarios,
  error,
}: DataSourceSettingsTabProps) {
  return (
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
                <span className="text-text-muted">Graph database</span>
                <span className="text-text-secondary">{activeGraph}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Telemetry store</span>
                <span className="text-text-secondary">
                  {activeGraph.includes('-') ? `${activeGraph.substring(0, activeGraph.lastIndexOf('-'))}-telemetry` : 'telemetry'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Runbooks index</span>
                <span className="text-text-secondary">{activeRunbooksIndex}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Tickets index</span>
                <span className="text-text-secondary">{activeTicketsIndex}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Prompt set</span>
                <span className="text-text-secondary">{activePromptSet || '(none)'}</span>
              </div>
            </div>
            <p className="text-[10px] text-text-muted">
              Bindings derived from scenario configuration. Switch to Custom mode for manual control.
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
            <BindingCard label="GraphExplorer Agent" color="bg-blue-400">
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
            </BindingCard>

            {/* Telemetry → NoSQL Database */}
            <BindingCard label="Telemetry Agent" color="bg-purple-400">
              <div>
                <label className="text-xs text-text-muted block mb-1">Cosmos NoSQL Database</label>
                <div className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-secondary">
                  {activeGraph.includes('-') ? `${activeGraph.substring(0, activeGraph.lastIndexOf('-'))}-telemetry` : 'telemetry'}
                </div>
                <p className="text-xs text-text-muted mt-1">
                  Auto-derived from Graph selection above
                </p>
              </div>
            </BindingCard>

            {/* RunbookKB → Search Index */}
            <BindingCard label="RunbookKB Agent" color="bg-green-400">
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
            </BindingCard>

            {/* HistoricalTicket → Search Index */}
            <BindingCard label="HistoricalTicket Agent" color="bg-yellow-400">
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
            </BindingCard>
          </div>

          {/* Prompt Set selection */}
          <BindingCard label="Prompt Set" color="bg-pink-400">
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
          </BindingCard>

          {error && <p className="text-xs text-status-error">{error}</p>}

          {/* Action buttons */}
          <div className="flex gap-3">
            <ActionButton
              label="Load Topology"
              icon="🔗"
              description={`Reload graph from ${activeGraph}`}
              onClick={async () => {
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
  );
}
