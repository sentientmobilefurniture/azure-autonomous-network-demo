import { motion } from 'framer-motion';
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { Header } from './components/Header';
import { MetricsBar } from './components/MetricsBar';
import { InvestigationPanel } from './components/InvestigationPanel';
import { DiagnosisPanel } from './components/DiagnosisPanel';
import { useInvestigation } from './hooks/useInvestigation';

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

  return (
    <motion.div
      className="h-screen flex flex-col bg-neutral-bg1"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Zone 1: Header */}
      <Header />

      {/* Zone 2 + 3: Vertically resizable split */}
      <div className="flex-1 min-h-0">
        <PanelGroup orientation="vertical" className="h-full">
          {/* Zone 2: Metrics bar — draggable bottom edge */}
          <Panel defaultSize={30} minSize={15} maxSize={60}>
            <div className="h-full border-b border-white/10">
              <MetricsBar />
            </div>
          </Panel>

          <PanelResizeHandle className="vertical-resize-handle" />

          {/* Zone 3: Two-panel split — fills remaining height */}
          <Panel defaultSize={70} minSize={20}>
            <div className="h-full flex min-h-0">
              {/* Left: Investigation */}
              <InvestigationPanel
                alert={alert}
                onAlertChange={setAlert}
                onSubmit={submitAlert}
                steps={steps}
                thinking={thinking}
                errorMessage={errorMessage}
                running={running}
                runStarted={runStarted}
                runMeta={runMeta}
              />

              {/* Right: Diagnosis */}
              <DiagnosisPanel
                finalMessage={finalMessage}
                running={running}
                runStarted={runStarted}
                runMeta={runMeta}
              />
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </motion.div>
  );
}
