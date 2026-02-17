import { AnimatePresence } from 'framer-motion';
import type { StepEvent, ThinkingState, RunMeta } from '../types';
import { AlertInput } from './AlertInput';
import { AgentTimeline } from './AgentTimeline';
import { ErrorBanner } from './ErrorBanner';
import { SCENARIO } from '../config';

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
  const exampleQuestions = SCENARIO.exampleQuestions;

  return (
    <div className="h-full overflow-y-auto p-4 flex flex-col">
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
