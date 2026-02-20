import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Header } from './components/Header';
import { TabBar } from './components/TabBar';
import { MetricsBar } from './components/MetricsBar';
import { ConversationPanel } from './components/ConversationPanel';
import { ChatInput } from './components/ChatInput';
import { SessionSidebar } from './components/SessionSidebar';
import { ResizableGraph } from './components/ResizableGraph';
import { ResizableSidebar } from './components/ResizableSidebar';
import { ResizableTerminal } from './components/ResizableTerminal';
import { Toast } from './components/Toast';
import { useConversation } from './hooks/useConversation';
import { useSessions } from './hooks/useSessions';
import { useAutoScroll } from './hooks/useAutoScroll';
import { ResourceVisualizer } from './components/ResourceVisualizer';
import { ScenarioPanel } from './components/ScenarioPanel';
import { OntologyPanel } from './components/OntologyPanel';
import { TerminalPanel } from './components/TerminalPanel';
import { useScenario } from './ScenarioContext';

type AppTab = 'investigate' | 'resources' | 'scenario' | 'ontology';

export default function App() {
  const SCENARIO = useScenario();
  const {
    messages,
    running,
    activeSessionId,
    createSession,
    sendFollowUp,
    viewSession,
    cancelSession,
    handleNewSession,
    deleteSession,
    saveSession,
  } = useConversation();

  const { sessions, loading: sessionsLoading, refetch: refetchSessions } = useSessions(SCENARIO.name);
  const { isNearBottom, scrollToBottom, scrollRef } = useAutoScroll(messages);

  // Refetch session list when a run finishes (running transitions true → false)
  const prevRunning = useRef(running);
  useEffect(() => {
    if (prevRunning.current && !running) {
      refetchSessions();
    }
    prevRunning.current = running;
  }, [running, refetchSessions]);

  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<AppTab>('investigate');
  const [showTabs, setShowTabs] = useState(true);
  const [terminalVisible, setTerminalVisible] = useState(true);

  // Trigger Fabric rediscovery (best-effort, non-blocking)
  const triggerRediscovery = async () => {
    try {
      await fetch('/query/health/rediscover', { method: 'POST' });
    } catch { /* ignore */ }
  };

  // Handle submit: create new session or send follow-up
  const handleSubmit = async (text: string) => {
    triggerRediscovery();

    if (activeSessionId && !running) {
      await sendFollowUp(text);
    } else if (!running) {
      await createSession(SCENARIO.name, text);
    }
    refetchSessions();
  };

  return (
    <motion.div
      className="h-screen flex flex-col bg-neutral-bg1"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Header — sticky */}
      <Header
        showTabs={showTabs}
        onToggleTabs={() => setShowTabs((v) => !v)}
        terminalVisible={terminalVisible}
        onToggleTerminal={() => setTerminalVisible((v) => !v)}
      />

      {/* Tab bar — sticky below header */}
      {showTabs && <TabBar activeTab={activeTab} onTabChange={setActiveTab} />}

      {/* Main content — fills remaining viewport */}
      <div className="flex-1 flex flex-col min-h-0" role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={activeTab}>
        {activeTab === 'resources' ? (
          <ResourceVisualizer />
        ) : activeTab === 'ontology' ? (
          <OntologyPanel />
        ) : activeTab === 'scenario' ? (
          <ScenarioPanel onUsePrompt={(q) => {
            handleSubmit(q);
            setActiveTab('investigate');
          }} />
        ) : (
          /* ---- Investigate tab ---- */
          <div className="flex-1 flex min-h-0">
            {/* Left column: graph + chat + terminal */}
            <main className="flex-1 min-w-0 flex flex-col min-h-0">
              {/* Graph topology — resizable from bottom edge */}
              <ResizableGraph>
                <MetricsBar />
              </ResizableGraph>

              {/* Chat section — scroll area + pinned input */}
              <div className="flex-1 min-h-0 flex flex-col">
                {/* Scrollable conversation thread */}
                <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto">
                  <ConversationPanel
                    messages={messages}
                    onSave={saveSession}
                  />
                </div>

                {/* Chat input — pinned at bottom of chat section */}
                <ChatInput
                  onSubmit={handleSubmit}
                  onCancel={cancelSession}
                  running={running}
                  exampleQuestions={SCENARIO.exampleQuestions}
                />
              </div>

              {/* Terminal — resizable from top edge, aligned with chat */}
              <ResizableTerminal visible={terminalVisible}>
                <TerminalPanel />
              </ResizableTerminal>
            </main>

            {/* Session sidebar — full height, resizable from left edge */}
            {!sidebarCollapsed ? (
              <ResizableSidebar>
                <SessionSidebar
                  sessions={sessions}
                  loading={sessionsLoading}
                  onSelect={(id) => viewSession(id)}
                  onDelete={(id) => deleteSession(id)}
                  onNewSession={handleNewSession}
                  onRefresh={refetchSessions}
                  activeSessionId={activeSessionId}
                  collapsed={sidebarCollapsed}
                  onToggleCollapse={() => setSidebarCollapsed(v => !v)}
                />
              </ResizableSidebar>
            ) : (
              <aside className="w-8 shrink-0">
                <SessionSidebar
                  sessions={sessions}
                  loading={sessionsLoading}
                  onSelect={(id) => viewSession(id)}
                  onDelete={(id) => deleteSession(id)}
                  onNewSession={handleNewSession}
                  onRefresh={refetchSessions}
                  activeSessionId={activeSessionId}
                  collapsed={sidebarCollapsed}
                  onToggleCollapse={() => setSidebarCollapsed(v => !v)}
                />
              </aside>
            )}
          </div>
        )}
      </div>

      {/* Scroll-to-bottom FAB */}
      {!isNearBottom && running && activeTab === 'investigate' && (
        <button
          onClick={scrollToBottom}
          className="fixed bottom-20 right-80 z-50 px-3 py-2 rounded-full
                     bg-brand text-white text-xs shadow-lg
                     hover:bg-brand-hover transition-colors"
        >
          ↓ New steps
        </button>
      )}

      {/* Toast notification */}
      {toastMessage && (
        <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />
      )}
    </motion.div>
  );
}
