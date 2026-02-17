/**
 * First-run empty state — shown in the Investigate tab when no scenario
 * is loaded. Onboarding for Cosmos users.
 */

import type { SavedScenario } from '../types';

interface EmptyStateProps {
  onUpload: () => void;
  savedScenarios?: SavedScenario[];
  onSelectScenario?: (id: string) => void;
}

export function EmptyState({
  onUpload,
  savedScenarios,
  onSelectScenario,
}: EmptyStateProps) {
  // State 2: Scenarios exist but none selected
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

  // State 1: Default — upload onboarding
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-lg w-full text-center space-y-6">
        <div className="space-y-2">
          <h2 className="text-lg font-semibold text-text-primary">Get started</h2>
          <p className="text-sm text-text-secondary">
            Upload a scenario data pack to begin investigating.
          </p>
        </div>

        <button
          onClick={onUpload}
          className="p-4 bg-neutral-bg1 border border-white/10 rounded-xl hover:bg-white/5 transition-colors space-y-2 mx-auto"
        >
          <p className="text-sm font-medium text-text-primary">📂 Upload Scenario</p>
          <p className="text-[11px] text-text-muted">CosmosDB + Blob</p>
          <p className="text-[10px] text-text-muted mt-1">
            Upload 5 data packs and start investigating.
          </p>
        </button>
      </div>
    </div>
  );
}
