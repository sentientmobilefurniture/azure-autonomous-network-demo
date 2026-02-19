import { useState } from 'react';
import { motion } from 'framer-motion';
import { Header } from './components/Header';
import { TabBar } from './components/TabBar';
import { MetricsBar } from './components/MetricsBar';
import { ChatPanel } from './components/ChatPanel';
import { SessionSidebar } from './components/SessionSidebar';
import { Toast } from './components/Toast';
import { useSession } from './hooks/useSession';
import { useSessions } from './hooks/useSessions';
import { useAutoScroll } from './hooks/useAutoScroll';
import { ResourceVisualizer } from './components/ResourceVisualizer';
import { ScenarioPanel } from './components/ScenarioPanel';
import { TerminalPanel } from './components/TerminalPanel';
import { useScenario } from './ScenarioContext';

type AppTab = 'investigate' | 'resources' | 'scenario';

export default function App() {
  const SCENARIO = useScenario();
  const {
    messages,
    thinking,
    running,
    activeSessionId,
    createSession,
    sendFollowUp,
    viewSession,
    cancelSession,
  } = useSession();

  const { sessions, loading: sessionsLoading } = useSessions(SCENARIO.name);
  const { isNearBottom, scrollToBottom } = useAutoScroll(messages, thinking);

  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<AppTab>('investigate');
  const [showTabs, setShowTabs] = useState(true);
  const [terminalVisible] = useState(true);



  // Handle submit: create new session or send follow-up
  const handleSubmit = (text: string) => {
    if (activeSessionId && !running) {
      sendFollowUp(text);
    } else if (!running) {
      createSession(SCENARIO.name, text);
    }
  };

  return (
    <motion.div
      className="min-h-screen flex flex-col bg-neutral-bg1"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Header — sticky */}
      <Header showTabs={showTabs} onToggleTabs={() => setShowTabs((v) => !v)} />

      {/* Tab bar — sticky below header */}
      {showTabs && <TabBar activeTab={activeTab} onTabChange={setActiveTab} />}

      {/* Main content */}
      <div className="flex-1 flex flex-col" role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={activeTab}>
        {activeTab === 'resources' ? (
          <ResourceVisualizer />
        ) : activeTab === 'scenario' ? (
          <ScenarioPanel onUsePrompt={(q) => {
            handleSubmit(q);
            setActiveTab('investigate');
          }} />
        ) : (
          /* ---- Investigate tab: Chat + Sidebar ---- */
          <div className="flex-1 flex">
            {/* Main scrollable content */}
            <main className="flex-1 min-w-0 flex flex-col">
              {/* Metrics bar — natural height */}
              <div className="h-[280px] border-b border-border shrink-0">
                <MetricsBar />
              </div>

              {/* Chat thread — grows with content */}
              <ChatPanel
                messages={messages}
                currentThinking={thinking}
                running={running}
                onSubmit={handleSubmit}
                onCancel={cancelSession}
                exampleQuestions={SCENARIO.exampleQuestions}
              />
            </main>

            {/* Session sidebar — sticky within scroll */}
            {!sidebarCollapsed ? (
              <aside className="w-72 shrink-0 sticky top-12 h-[calc(100vh-3rem)] overflow-y-auto">
                <SessionSidebar
                  sessions={sessions}
                  loading={sessionsLoading}
                  onSelect={(id) => viewSession(id)}
                  activeSessionId={activeSessionId}
                  collapsed={sidebarCollapsed}
                  onToggleCollapse={() => setSidebarCollapsed(v => !v)}
                />
              </aside>
            ) : (
              <aside className="w-8 shrink-0 sticky top-12 h-[calc(100vh-3rem)]">
                <SessionSidebar
                  sessions={sessions}
                  loading={sessionsLoading}
                  onSelect={(id) => viewSession(id)}
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

      {/* Terminal panel — collapsible at bottom */}
      {terminalVisible && activeTab === 'investigate' && (
        <div className="border-t border-border h-[200px] shrink-0">
          <TerminalPanel />
        </div>
      )}

      {/* Toast notification */}
      {toastMessage && (
        <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />
      )}
    </motion.div>
  );
}
