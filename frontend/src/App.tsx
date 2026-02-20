import { useState } from 'react';
import { motion } from 'framer-motion';
import { Header } from './components/Header';
import { TabBar } from './components/TabBar';
import { MetricsBar } from './components/MetricsBar';
// GUTTED: ChatPanel, ChatInput — rebuilt in Phase B task 06/07
// import { ChatInput } from './components/ChatInput';
// import { SessionSidebar } from './components/SessionSidebar';
import { ResizableGraph } from './components/ResizableGraph';
// import { ResizableSidebar } from './components/ResizableSidebar';
import { ResizableTerminal } from './components/ResizableTerminal';
import { Toast } from './components/Toast';
// GUTTED: useSession — rebuilt as useConversation in Phase B task 05
// import { useSessions } from './hooks/useSessions';
// import { useAutoScroll } from './hooks/useAutoScroll';
import { ResourceVisualizer } from './components/ResourceVisualizer';
import { ScenarioPanel } from './components/ScenarioPanel';
import { OntologyPanel } from './components/OntologyPanel';
import { TerminalPanel } from './components/TerminalPanel';
import { useScenario } from './ScenarioContext';

type AppTab = 'investigate' | 'resources' | 'scenario' | 'ontology';

export default function App() {
  const SCENARIO = useScenario();

  // GUTTED: useSession() — rebuilt as useConversation() in Phase B
  // GUTTED: useSessions() — restored in Phase B wiring
  // GUTTED: useAutoScroll() — restored in Phase B wiring

  // Placeholder state — these will be restored from useConversation in Phase B
  // const running = false;
  // const activeSessionId: string | null = null;

  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [_sidebarCollapsed, _setSidebarCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<AppTab>('investigate');
  const [showTabs, setShowTabs] = useState(true);
  const [terminalVisible, setTerminalVisible] = useState(true);

  // GUTTED: triggerRediscovery, handleSubmit — rebuilt in Phase B wiring

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
          <ScenarioPanel onUsePrompt={(_q) => {
            // GUTTED: handleSubmit — rebuilt in Phase B wiring
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

              {/* PLACEHOLDER: ConversationPanel + ChatInput — rebuilt in Phase B */}
              <div className="flex-1 min-h-0 flex items-center justify-center">
                <span className="text-text-muted text-sm">Conversation system removed — rebuilding</span>
              </div>

              {/* Terminal — resizable from top edge, aligned with chat */}
              <ResizableTerminal visible={terminalVisible}>
                <TerminalPanel />
              </ResizableTerminal>
            </main>

            {/* GUTTED: Session sidebar — restored in Phase B wiring */}
          </div>
        )}
      </div>

      {/* GUTTED: Scroll-to-bottom FAB — restored in Phase B */}

      {/* Toast notification */}
      {toastMessage && (
        <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />
      )}
    </motion.div>
  );
}
