import { useEffect } from 'react';
import { AnimatePresence } from 'framer-motion';
import type { StepEvent, ThinkingState, RunMeta } from '../types';
import { AlertInput } from './AlertInput';
import { AgentTimeline } from './AgentTimeline';
import { ErrorBanner } from './ErrorBanner';
import { useScenarioContext } from '../context/ScenarioContext';
import { useScenarios } from '../hooks/useScenarios';

interface InvestigationPanelProps {
  alert: string;
  onAlertChange: (value: string) => void;
  onSubmit: () => void;
  steps: StepEvent[];
  thinking: ThinkingState | null;
  errorMessage: string;
  running: boolean;
  runStarted: boolean;
  runMeta: RunMeta | null;
}

export function InvestigationPanel({
  alert,
  onAlertChange,
  onSubmit,
  steps,
  thinking,
  errorMessage,
  running,
  runStarted,
  runMeta,
}: InvestigationPanelProps) {
  // Source example questions from the active scenario
  const { activeScenario } = useScenarioContext();
  const { savedScenarios, fetchSavedScenarios } = useScenarios();
  useEffect(() => { fetchSavedScenarios(); }, [fetchSavedScenarios]);
  const scenario = savedScenarios.find(s => s.id === activeScenario);
  const exampleQuestions = scenario?.example_questions;

  return (
    <div className="w-full lg:w-1/2 border-r border-white/10 overflow-y-auto p-4 flex flex-col">
      <AlertInput
        alert={alert}
        onAlertChange={onAlertChange}
        onSubmit={onSubmit}
        running={running}
        exampleQuestions={exampleQuestions}
      />

      <AgentTimeline
        steps={steps}
        thinking={thinking}
        running={running}
        runStarted={runStarted}
        runMeta={runMeta}
      />

      <AnimatePresence>
        {errorMessage && (
          <ErrorBanner
            message={errorMessage}
            stepCount={steps.length}
            onRetry={onSubmit}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
