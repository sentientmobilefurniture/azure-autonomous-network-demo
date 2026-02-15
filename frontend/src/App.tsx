import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
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
import { useScenarioContext } from './context/ScenarioContext';
import type { Interaction } from './types';

type AppTab = 'investigate' | 'info';

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
  } = useInvestigation();

  const { interactions, loading: interactionsLoading, fetchInteractions,
    saveInteraction, deleteInteraction } = useInteractions();
  const { activeScenario } = useScenarioContext();

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [viewingInteraction, setViewingInteraction] = useState<Interaction | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>('investigate');

  // Fetch interactions on mount and when scenario changes
  useEffect(() => {
    fetchInteractions(activeScenario ?? undefined);
  }, [activeScenario, fetchInteractions]);

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
      {/* Zone 1: Header */}
      <Header />

      {/* Tab bar */}
      <TabBar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Zone 2 + 3: Main content + sidebar */}
      <div className="flex-1 min-h-0 flex">
        {activeTab === 'investigate' ? (
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
                        runStarted={runStarted}
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
        ) : (
          <ScenarioInfoPanel
            onSelectQuestion={(q) => {
              setAlert(q);
              setActiveTab('investigate');
            }}
          />
        )}
      </div>
    </motion.div>
  );
}

/** Format ISO timestamp to relative time */
function formatTimeAgo(isoString: string): string {
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
