import { useState } from 'react';
import type { SavedScenario } from '../../types';

interface ScenarioSettingsTabProps {
  savedScenarios: SavedScenario[];
  savedLoading: boolean;
  activeScenario: string | null;
  selectScenario: (id: string) => void;
  deleteSavedScenario: (id: string) => Promise<void>;
  setActiveScenario: (id: string | null, saved?: SavedScenario) => void;
  onAddScenario: () => void;
}

export function ScenarioSettingsTab({
  savedScenarios,
  savedLoading,
  activeScenario,
  selectScenario,
  deleteSavedScenario,
  setActiveScenario,
  onAddScenario,
}: ScenarioSettingsTabProps) {
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  return (
    <>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider">
          Saved Scenarios
        </h3>
        <button
          onClick={onAddScenario}
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
            Click &quot;+ New Scenario&quot; to create your first scenario data pack.
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
                        <p className="text-xs text-text-muted mb-2">Delete &quot;{sc.id}&quot;?</p>
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
  );
}
