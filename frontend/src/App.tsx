import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { Header } from './components/Header';
import { TabBar } from './components/TabBar';
import { ScenarioInfoPanel } from './components/ScenarioInfoPanel';
import { MetricsBar } from './components/MetricsBar';
import { InvestigationPanel } from './components/InvestigationPanel';
import { DiagnosisPanel } from './components/DiagnosisPanel';
import { InteractionSidebar } from './components/InteractionSidebar';
import { useInvestigation } from './hooks/useInvestigation';
import { useInteractions } from './hooks/useInteractions';
import { ResourceVisualizer } from './components/ResourceVisualizer';
import { EmptyState } from './components/EmptyState';
import { AddScenarioModal } from './components/AddScenarioModal';
import { useScenarioContext } from './context/ScenarioContext';
import { useScenarios } from './hooks/useScenarios';
import { formatTimeAgo } from './utils/formatTime';
import type { Interaction } from './types';

type AppTab = 'investigate' | 'info' | 'resources';

export default function App() {
  const {
    alert,
    setAlert,
    steps,
    thinking,
    finalMessage,
    errorMessage,
    running,
    runStarted,
    runMeta,
    submitAlert,
    resetInvestigation,
  } = useInvestigation();

  const { interactions, loading: interactionsLoading, fetchInteractions,
    saveInteraction, deleteInteraction } = useInteractions();
  const { activeScenario, scenarioReady, refreshScenarios, savedScenarios } = useScenarioContext();
  const { saveScenario } = useScenarios();

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [viewingInteraction, setViewingInteraction] = useState<Interaction | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>('investigate');
  const [addModalOpen, setAddModalOpen] = useState(false);

  // Fetch interactions on mount and when scenario changes
  useEffect(() => {
    fetchInteractions(activeScenario ?? undefined);
    // Clear stale investigation state from previous scenario
    resetInvestigation();
    setViewingInteraction(null);
  }, [activeScenario, fetchInteractions, resetInvestigation]);

  // Auto-save interaction when investigation completes.
  const prevRunningRef = useRef(running);
  const latestValuesRef = useRef({ alert, steps, runMeta, activeScenario });
  useEffect(() => {
    latestValuesRef.current = { alert, steps, runMeta, activeScenario };
  });

  useEffect(() => {
    if (prevRunningRef.current && !running && finalMessage && latestValuesRef.current.activeScenario) {
      const { alert: savedAlert, steps: savedSteps, runMeta: savedRunMeta, activeScenario: savedScenario } = latestValuesRef.current;
      saveInteraction({
        scenario: savedScenario!,
        query: savedAlert,
        steps: savedSteps,
        diagnosis: finalMessage,
        run_meta: savedRunMeta,
      });
    }
    prevRunningRef.current = running;
  }, [running, finalMessage, saveInteraction]);

  // When viewing a past interaction, override displayed data
  const displaySteps = viewingInteraction?.steps ?? steps;
  const displayDiagnosis = viewingInteraction?.diagnosis ?? finalMessage;
  const displayRunMeta = viewingInteraction?.run_meta ?? runMeta;

  // Clear viewing state when a new investigation starts
  useEffect(() => {
    if (running) setViewingInteraction(null);
  }, [running]);

  return (
    <motion.div
      className="h-screen flex flex-col bg-neutral-bg1"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Startup loading overlay while validating persisted scenario */}
      <AnimatePresence>
        {!scenarioReady && (
          <motion.div
            key="startup-overlay"
            className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm
                       flex items-center justify-center"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="flex flex-col items-center gap-4 text-text-secondary">
              <span className="inline-block h-8 w-8 animate-spin rounded-full
                              border-[3px] border-brand border-t-transparent" />
              <span className="text-sm animate-pulse">
                Validating scenario &ldquo;{activeScenario}&rdquo;&hellip;
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Zone 1: Header */}
      <Header />

      {/* Tab bar */}
      <TabBar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Zone 2 + 3: Main content + sidebar */}
      <div className="flex-1 min-h-0 flex" role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={activeTab}>
        {activeTab === 'resources' ? (
          <ResourceVisualizer />
        ) : activeTab === 'investigate' ? (
          !activeScenario ? (
            <EmptyState onUpload={() => setAddModalOpen(true)} />
          ) : (
          <>
            {/* Main content area */}
            <div className="flex-1 min-w-0">
              <PanelGroup orientation="vertical" className="h-full">
                {/* Zone 2: Metrics bar — draggable bottom edge */}
                <Panel defaultSize={30} minSize={15}>
                  <div className="h-full border-b border-white/10">
                    <MetricsBar />
                  </div>
                </Panel>

                <PanelResizeHandle className="vertical-resize-handle" />

                {/* Zone 3: Two-panel split — fills remaining height */}
                <Panel defaultSize={70} minSize={20}>
                  <div className="h-full flex flex-col min-h-0">
                    {/* Viewing past interaction banner */}
                    {viewingInteraction && (
                      <div className="flex items-center justify-between px-4 py-1.5 bg-brand/10 border-b border-brand/20 shrink-0">
                        <span className="text-xs text-brand">
                          ◀ Viewing interaction from {formatTimeAgo(viewingInteraction.created_at)}
                          <span className="ml-2 px-1.5 py-0.5 rounded bg-brand/15 text-[10px] font-medium">
                            {viewingInteraction.scenario}
                          </span>
                        </span>
                        <button
                          onClick={() => setViewingInteraction(null)}
                          className="text-xs text-brand hover:text-brand/80 font-medium"
                        >
                          Clear
                        </button>
                      </div>
                    )}

                    <div className="flex-1 flex min-h-0">
                      {/* Left: Investigation */}
                      <InvestigationPanel
                        alert={alert}
                        onAlertChange={setAlert}
                        onSubmit={submitAlert}
                        steps={displaySteps}
                        thinking={thinking}
                        errorMessage={errorMessage}
                        running={running}
                        runStarted={runStarted}
                        runMeta={displayRunMeta}
                      />

                      {/* Right: Diagnosis */}
                      <DiagnosisPanel
                        finalMessage={displayDiagnosis}
                        running={running}
                        runMeta={displayRunMeta}
                      />
                    </div>
                  </div>
                </Panel>
              </PanelGroup>
            </div>

            {/* Interaction history sidebar */}
            <InteractionSidebar
              interactions={interactions}
              loading={interactionsLoading}
              onSelect={(i) => { setViewingInteraction(i); setAlert(i.query); }}
              onDelete={deleteInteraction}
              activeInteractionId={viewingInteraction?.id ?? null}
              collapsed={sidebarCollapsed}
              onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
            />
          </>
          )
        ) : (
          <ScenarioInfoPanel
            onSelectQuestion={(q) => {
              setAlert(q);
              setActiveTab('investigate');
            }}
          />
        )}
      </div>

      {/* Upload scenario modal — triggered from empty state or ScenarioChip */}
      <AddScenarioModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSaved={() => refreshScenarios()}
        existingNames={savedScenarios.map(s => s.id)}
        saveScenarioMeta={saveScenario}
      />
    </motion.div>
  );
}


