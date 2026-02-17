import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle, useDefaultLayout } from 'react-resizable-panels';
import type { PanelImperativeHandle } from 'react-resizable-panels';
import { Header } from './components/Header';
import { TabBar } from './components/TabBar';
import { MetricsBar } from './components/MetricsBar';
import { InvestigationPanel } from './components/InvestigationPanel';
import { DiagnosisPanel } from './components/DiagnosisPanel';
import { InteractionSidebar } from './components/InteractionSidebar';
import { useInvestigation } from './hooks/useInvestigation';
import { useInteractions } from './hooks/useInteractions';
import { ResourceVisualizer } from './components/ResourceVisualizer';
import { TerminalPanel } from './components/TerminalPanel';
import { SCENARIO } from './config';
import { formatTimeAgo } from './utils/formatTime';
import type { Interaction } from './types';

type AppTab = 'investigate' | 'resources';

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

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [viewingInteraction, setViewingInteraction] = useState<Interaction | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>('investigate');
  const sidebarPanelRef = useRef<PanelImperativeHandle>(null);

  const handleSidebarToggle = () => {
    const panel = sidebarPanelRef.current;
    if (panel?.isCollapsed()) {
      panel.expand();
    } else {
      panel?.collapse();
    }
  };

  // Layout persistence — save/restore each PanelGroup to localStorage
  const appTerminal = useDefaultLayout({ id: 'app-terminal-layout', storage: localStorage });
  const contentSidebar = useDefaultLayout({ id: 'content-sidebar-layout', storage: localStorage });
  const metricsContent = useDefaultLayout({ id: 'metrics-content-layout', storage: localStorage });
  const investigationDiagnosis = useDefaultLayout({ id: 'investigation-diagnosis-layout', storage: localStorage });

  // Fetch interactions on mount
  useEffect(() => {
    fetchInteractions(SCENARIO.name);
  }, [fetchInteractions]);

  // Auto-save interaction when investigation completes.
  const prevRunningRef = useRef(running);
  const latestValuesRef = useRef({ alert, steps, runMeta });
  useEffect(() => {
    latestValuesRef.current = { alert, steps, runMeta };
  });

  useEffect(() => {
    if (prevRunningRef.current && !running && finalMessage) {
      const { alert: savedAlert, steps: savedSteps, runMeta: savedRunMeta } = latestValuesRef.current;
      saveInteraction({
        scenario: SCENARIO.name,
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

      {/* Outer vertical split: main content (top) + terminal panel (bottom) */}
      <PanelGroup
        orientation="vertical"
        className="flex-1 min-h-0"
        id="app-terminal-layout"
        defaultLayout={appTerminal.defaultLayout}
        onLayoutChanged={appTerminal.onLayoutChanged}
      >
        {/* Main content panel */}
        <Panel defaultSize={75} minSize={30}>
          <div className="h-full flex" role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={activeTab}>
            {activeTab === 'resources' ? (
              <ResourceVisualizer />
            ) : (
              <PanelGroup orientation="horizontal" className="h-full" id="content-sidebar-layout"
                defaultLayout={contentSidebar.defaultLayout}
                onLayoutChanged={contentSidebar.onLayoutChanged}
              >
                {/* Main content area */}
                <Panel defaultSize={80} minSize={40}>
                  <PanelGroup orientation="vertical" className="h-full" id="metrics-content-layout"
                    defaultLayout={metricsContent.defaultLayout}
                    onLayoutChanged={metricsContent.onLayoutChanged}
                  >
                    {/* Zone 2: Metrics bar — draggable bottom edge */}
                    <Panel defaultSize={30} minSize={15}>
                      <div className="h-full border-b border-white/10">
                        <MetricsBar />
                      </div>
                    </Panel>

                    <PanelResizeHandle className="resize-handle resize-handle-vertical" />

                    {/* Zone 3: Two-panel split — fills remaining height */}
                    <Panel defaultSize={70} minSize={20}>
                      <div className="h-full flex flex-col min-h-0">
                        {/* Viewing past interaction banner */}
                        {viewingInteraction && (
                          <div className="flex items-center justify-between px-4 py-1.5 bg-brand/10 border-b border-brand/20 shrink-0">
                            <span className="text-xs text-brand">
                              ◀ Viewing interaction from {formatTimeAgo(viewingInteraction.created_at)}
                            </span>
                            <button
                              onClick={() => setViewingInteraction(null)}
                              className="text-xs text-brand hover:text-brand/80 font-medium"
                            >
                              Clear
                            </button>
                          </div>
                        )}

                        <PanelGroup orientation="horizontal" className="flex-1 min-h-0" id="investigation-diagnosis-layout"
                          defaultLayout={investigationDiagnosis.defaultLayout}
                          onLayoutChanged={investigationDiagnosis.onLayoutChanged}
                        >
                          {/* Left: Investigation */}
                          <Panel defaultSize={50} minSize={25}>
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
                          </Panel>

                          <PanelResizeHandle className="resize-handle resize-handle-horizontal" />

                          {/* Right: Diagnosis */}
                          <Panel defaultSize={50} minSize={25}>
                            <DiagnosisPanel
                              finalMessage={displayDiagnosis}
                              running={running}
                              runMeta={displayRunMeta}
                            />
                          </Panel>
                        </PanelGroup>
                      </div>
                    </Panel>
                  </PanelGroup>
                </Panel>

                <PanelResizeHandle className="resize-handle resize-handle-horizontal" />

                {/* Interaction history sidebar */}
                <Panel
                  defaultSize={20}
                  minSize={5}
                  collapsible
                  panelRef={sidebarPanelRef}
                  onResize={(panelSize) => setSidebarCollapsed(panelSize.asPercentage < 6)}
                >
                  <InteractionSidebar
                    interactions={interactions}
                    loading={interactionsLoading}
                    onSelect={(i) => { setViewingInteraction(i); setAlert(i.query); }}
                    onDelete={deleteInteraction}
                    activeInteractionId={viewingInteraction?.id ?? null}
                    collapsed={sidebarCollapsed}
                    onToggleCollapse={handleSidebarToggle}
                  />
                </Panel>
              </PanelGroup>
            )}
          </div>
        </Panel>

        {/* Resizable divider */}
        <PanelResizeHandle className="resize-handle resize-handle-vertical" />

        {/* Persistent terminal panel — always visible */}
        <Panel defaultSize={25} minSize={8} collapsible>
          <TerminalPanel />
        </Panel>
      </PanelGroup>
    </motion.div>
  );
}


