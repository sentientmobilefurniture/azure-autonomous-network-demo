/**
 * First-run empty state — shown in the Investigate tab when no scenario
 * is loaded. Onboarding for Fabric users.
 */

import type { SavedScenario } from '../types';

interface FabricHealth {
  configured: boolean;
  workspace_connected: boolean;
  query_ready: boolean;
}

interface EmptyStateProps {
  onUpload: () => void;
  fabricHealth?: FabricHealth | null;
  onFabricSetup?: () => void;
  savedScenarios?: SavedScenario[];
  onSelectScenario?: (id: string) => void;
}

export function EmptyState({
  onUpload,
  fabricHealth,
  onFabricSetup,
  savedScenarios,
  onSelectScenario,
}: EmptyStateProps) {
  // State 3: Scenarios exist but none selected
  if (savedScenarios && savedScenarios.length > 0 && onSelectScenario) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="max-w-md w-full text-center space-y-6">
          <div className="space-y-2">
            <h2 className="text-lg font-semibold text-text-primary">Select a scenario</h2>
            <p className="text-sm text-text-secondary">
              {savedScenarios.length} scenario{savedScenarios.length > 1 ? 's' : ''} available.
              Select one to start investigating.
            </p>
          </div>
          <div className="space-y-2 max-w-xs mx-auto">
            {savedScenarios.map((s) => (
              <button
                key={s.id}
                onClick={() => onSelectScenario(s.id)}
                className="w-full text-left px-4 py-2.5 bg-neutral-bg1 border border-white/10 rounded-lg
                  hover:bg-white/5 transition-colors text-sm text-text-primary flex items-center justify-between"
              >
                <span className="truncate">{s.display_name || s.id}</span>
                <span className="text-[9px] text-text-muted flex-shrink-0 ml-2">
                  {s.graph_connector === 'fabric-gql' ? 'Fabric' : 'Backend'}
                </span>
              </button>
            ))}
          </div>
          <button
            onClick={onUpload}
            className="text-xs text-brand hover:text-brand/80 transition-colors"
          >
            + Upload new scenario
          </button>
        </div>
      </div>
    );
  }

  // State 1: Fabric partially configured
  if (fabricHealth?.workspace_connected && !fabricHealth?.query_ready && onFabricSetup) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="max-w-md w-full space-y-6">
          <div className="space-y-2 text-center">
            <h2 className="text-lg font-semibold text-text-primary">Get started</h2>
            <p className="text-sm text-amber-400">
              ⚠ Fabric workspace connected — resources not yet set up
            </p>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2 text-status-success"><span>✓</span> API connected</div>
            <div className="flex items-center gap-2 text-status-success"><span>✓</span> Workspace connected</div>
            <div className="flex items-center gap-2 text-text-muted"><span>○</span> Provision Fabric resources</div>
            <div className="flex items-center gap-2 text-text-muted"><span>○</span> Create a scenario</div>
            <div className="flex items-center gap-2 text-text-muted"><span>○</span> Investigate with AI agents</div>
          </div>
          <div className="flex gap-3 justify-center">
            <button
              onClick={onFabricSetup}
              className="px-5 py-2.5 bg-brand hover:bg-brand/90 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Set Up Fabric →
            </button>
            <button
              onClick={onUpload}
              className="px-5 py-2.5 bg-white/10 hover:bg-white/15 text-text-primary text-sm rounded-lg transition-colors"
            >
              Or: Upload Scenario
            </button>
          </div>
        </div>
      </div>
    );
  }

  // State 2: Default — two-card onboarding
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-lg w-full text-center space-y-6">
        <div className="space-y-2">
          <h2 className="text-lg font-semibold text-text-primary">Get started</h2>
          <p className="text-sm text-text-secondary">
            Upload a scenario data pack or connect Microsoft Fabric.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4 text-left">
          <button
            onClick={onUpload}
            className="p-4 bg-neutral-bg1 border border-white/10 rounded-xl hover:bg-white/5 transition-colors space-y-2"
          >
            <p className="text-sm font-medium text-text-primary">📂 Upload Scenario</p>
            <p className="text-[11px] text-text-muted">Graph + Telemetry + Search</p>
            <p className="text-[10px] text-text-muted mt-1">
              Upload 5 data packs and start investigating.
            </p>
          </button>
          <button
            onClick={() => onFabricSetup?.()}
            disabled={!onFabricSetup}
            className="p-4 bg-neutral-bg1 border border-white/10 rounded-xl hover:bg-white/5 transition-colors space-y-2 disabled:opacity-50"
          >
            <p className="text-sm font-medium text-text-primary">⬡ Connect Fabric</p>
            <p className="text-[11px] text-text-muted">Graph via Lakehouse</p>
            <p className="text-[10px] text-text-muted mt-1">
              Connect workspace, provision resources, create scenario.
            </p>
          </button>
        </div>
      </div>
    </div>
  );
}
