import { useState } from 'react';
import type { FabricItem } from '../../types';

interface FabricSetupTabProps {
  activeScenario: string | null;
  fabric: {
    healthy: boolean | null;
    checking: boolean;
    ontologies: FabricItem[];
    graphModels: FabricItem[];
    eventhouses: FabricItem[];
    loadingSection: string | null;
    error: string | null;
    provisionPct: number;
    provisionStep: string;
    provisionState: 'idle' | 'running' | 'done' | 'error';
    provisionError: string | null;
    fetchAll: () => Promise<void>;
    fetchGraphModels: (ontologyId: string) => Promise<void>;
    runProvisionPipeline: (opts?: {
      workspace_name?: string;
      lakehouse_name?: string;
      eventhouse_name?: string;
      ontology_name?: string;
      scenario_name?: string;
    }) => Promise<void>;
  };
}

export function FabricSetupTab({ activeScenario, fabric }: FabricSetupTabProps) {
  const [selectedOntologyId, setSelectedOntologyId] = useState<string>('');

  return (
    <>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider">
          Fabric Workspace
        </h3>
        <button
          onClick={() => fabric.fetchAll()}
          disabled={fabric.checking}
          className="text-xs bg-brand/20 text-brand hover:bg-brand/30 px-3 py-1 rounded-md transition-colors disabled:opacity-50"
        >
          {fabric.checking ? 'Checking...' : 'Refresh'}
        </button>
      </div>

      {/* Health status */}
      <div className={`bg-neutral-bg1 rounded-lg border p-4 space-y-2 ${
        fabric.healthy === true ? 'border-status-success/20' :
        fabric.healthy === false ? 'border-status-error/20' :
        'border-white/5'
      }`}>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${
            fabric.healthy === true ? 'bg-status-success' :
            fabric.healthy === false ? 'bg-status-error' :
            'bg-text-muted'
          }`} />
          <span className="text-sm font-medium text-text-primary">
            {fabric.healthy === true ? 'Connected' :
             fabric.healthy === false ? 'Not connected' :
             'Not checked'}
          </span>
        </div>
        {fabric.error && (
          <p className="text-xs text-status-error">{fabric.error}</p>
        )}
        <p className="text-[10px] text-text-muted">
          Requires FABRIC_WORKSPACE_ID env var and AAD credentials with Fabric access
        </p>
      </div>

      {/* Ontology selector */}
      <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-cyan-400" />
          <span className="text-sm font-medium text-text-primary">Ontology</span>
          {fabric.loadingSection === 'ontologies' && (
            <span className="text-xs text-text-muted animate-pulse ml-auto">Loading...</span>
          )}
        </div>
        <select
          value={selectedOntologyId}
          onChange={(e) => {
            setSelectedOntologyId(e.target.value);
            if (e.target.value) fabric.fetchGraphModels(e.target.value);
          }}
          className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary"
        >
          <option value="">Select an ontology...</option>
          {fabric.ontologies.map((o) => (
            <option key={o.id} value={o.id}>
              {o.display_name} {o.description ? `— ${o.description}` : ''}
            </option>
          ))}
        </select>
      </div>

      {/* Graph Model selector (only when ontology is selected) */}
      {selectedOntologyId && (
        <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-blue-400" />
            <span className="text-sm font-medium text-text-primary">Graph Model</span>
            {fabric.loadingSection === 'graphModels' && (
              <span className="text-xs text-text-muted animate-pulse ml-auto">Loading...</span>
            )}
          </div>
          {fabric.graphModels.length === 0 ? (
            <p className="text-xs text-text-muted">
              {fabric.loadingSection === 'graphModels' ? 'Loading...' : 'No graph models found for this ontology'}
            </p>
          ) : (
            <div className="space-y-1">
              {fabric.graphModels.map((m) => (
                <div key={m.id} className="flex items-center justify-between px-3 py-1.5 bg-neutral-bg2 rounded text-sm">
                  <span className="text-text-primary">{m.display_name}</span>
                  <span className="text-[10px] text-text-muted font-mono">{m.id.slice(0, 8)}…</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Eventhouse selector */}
      <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-purple-400" />
          <span className="text-sm font-medium text-text-primary">Eventhouses</span>
          {fabric.loadingSection === 'eventhouses' && (
            <span className="text-xs text-text-muted animate-pulse ml-auto">Loading...</span>
          )}
        </div>
        {fabric.eventhouses.length === 0 ? (
          <p className="text-xs text-text-muted">
            {fabric.loadingSection === 'eventhouses' ? 'Loading...' : 'No eventhouses found'}
          </p>
        ) : (
          <div className="space-y-1">
            {fabric.eventhouses.map((eh) => (
              <div key={eh.id} className="flex items-center justify-between px-3 py-1.5 bg-neutral-bg2 rounded text-sm">
                <span className="text-text-primary">{eh.display_name}</span>
                <span className="text-[10px] text-text-muted">{eh.type}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Provision pipeline */}
      <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-medium text-text-primary">Provision Fabric Resources</span>
            <p className="text-[10px] text-text-muted mt-0.5">
              Creates Lakehouse, Eventhouse, and Ontology in the Fabric workspace
            </p>
          </div>
          <button
            onClick={() => fabric.runProvisionPipeline({
              scenario_name: activeScenario || undefined,
            })}
            disabled={fabric.provisionState === 'running' || !fabric.healthy}
            className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
              fabric.provisionState === 'running' || !fabric.healthy
                ? 'bg-white/5 text-text-muted cursor-not-allowed'
                : 'bg-brand text-white hover:bg-brand/90'
            }`}
          >
            {fabric.provisionState === 'running' ? 'Provisioning...' : 'Provision'}
          </button>
        </div>

        {/* Progress bar */}
        {fabric.provisionState === 'running' && (
          <div className="space-y-1">
            <div className="w-full bg-neutral-bg2 rounded-full h-1.5">
              <div className="bg-brand h-1.5 rounded-full transition-all" style={{ width: `${Math.max(fabric.provisionPct, 3)}%` }} />
            </div>
            <p className="text-xs text-text-muted truncate">{fabric.provisionStep}</p>
          </div>
        )}

        {fabric.provisionState === 'done' && (
          <p className="text-xs text-status-success">Provisioning complete</p>
        )}

        {fabric.provisionState === 'error' && (
          <p className="text-xs text-status-error">{fabric.provisionError}</p>
        )}
      </div>
    </>
  );
}
