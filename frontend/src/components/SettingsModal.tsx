import { useEffect, useState } from 'react';
import { useScenarios } from '../hooks/useScenarios';
import { useScenarioContext } from '../context/ScenarioContext';
import { useFabricDiscovery } from '../hooks/useFabricDiscovery';
import { AddScenarioModal } from './AddScenarioModal';
import { ScenarioSettingsTab } from './settings/ScenarioSettingsTab';
import { DataSourceSettingsTab } from './settings/DataSourceSettingsTab';
import { UploadSettingsTab } from './settings/UploadSettingsTab';
import { FabricSetupTab } from './settings/FabricSetupTab';

interface Props {
  open: boolean;
  onClose: () => void;
}

type Tab = 'scenarios' | 'datasources' | 'upload' | 'fabric';

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

  // Fabric discovery hook (V11)
  const fabric = useFabricDiscovery();

  // Determine if active scenario is Fabric-backed
  const activeScenarioRecord = savedScenarios.find(s => s.id === activeScenario);
  const isFabricScenario = activeScenarioRecord?.graph_connector === 'fabric-gql';

  useEffect(() => {
    if (open) {
      fetchScenarios();
      fetchIndexes();
      fetchSavedScenarios();
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
            {isFabricScenario && (
              <button
                onClick={() => setTab('fabric')}
                className={`px-4 py-2 text-sm rounded-t-md transition-colors ${
                  tab === 'fabric'
                    ? 'bg-neutral-bg1 text-text-primary border-t border-x border-white/10'
                    : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                Fabric Setup
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {tab === 'scenarios' && (
            <ScenarioSettingsTab
              savedScenarios={savedScenarios}
              savedLoading={savedLoading}
              activeScenario={activeScenario}
              selectScenario={selectScenario}
              deleteSavedScenario={deleteSavedScenario}
              setActiveScenario={setActiveScenario}
              onAddScenario={() => setAddModalOpen(true)}
            />
          )}
          {tab === 'datasources' && (
            <DataSourceSettingsTab
              activeScenario={activeScenario}
              activeGraph={activeGraph}
              activeRunbooksIndex={activeRunbooksIndex}
              activeTicketsIndex={activeTicketsIndex}
              activePromptSet={activePromptSet}
              setActiveScenario={setActiveScenario}
              setActiveGraph={setActiveGraph}
              setActiveRunbooksIndex={setActiveRunbooksIndex}
              setActiveTicketsIndex={setActiveTicketsIndex}
              setActivePromptSet={setActivePromptSet}
              graphScenarios={graphScenarios}
              runbookIndexes={runbookIndexes}
              ticketIndexes={ticketIndexes}
              promptScenarios={promptScenarios}
              error={error}
            />
          )}
          {tab === 'upload' && (
            <UploadSettingsTab
              scenarios={scenarios}
              loading={loading}
              fetchScenarios={fetchScenarios}
              fetchIndexes={fetchIndexes}
            />
          )}
          {tab === 'fabric' && isFabricScenario && (
            <FabricSetupTab
              activeScenario={activeScenario}
              fabric={fabric}
            />
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
