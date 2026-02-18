import { AnimatePresence } from 'framer-motion';
import type { StepEvent, ThinkingState, RunMeta } from '../types';
import { StepCard } from './StepCard';
import { ThinkingDots } from './ThinkingDots';

interface AgentTimelineProps {
  steps: StepEvent[];
  thinking: ThinkingState | null;
  running: boolean;
  runStarted: boolean;
  runMeta: RunMeta | null;
}

export function AgentTimeline({
  steps,
  thinking,
  running,
  runStarted,
  runMeta,
}: AgentTimelineProps) {
  // Nothing to show yet
  if (!runStarted && steps.length === 0) return null;

  return (
    <div>
      <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted block mb-3">
        Investigation
      </span>

      {/* Orchestrator starting indicator */}
      {running && runStarted && steps.length === 0 && !thinking && (
        <div className="flex items-center gap-3 px-3 py-2 mb-2">
          <div className="animate-pulse h-2 w-2 rounded-full bg-brand" />
          <span className="text-xs text-text-secondary">
            Orchestrator is starting...
          </span>
        </div>
      )}

      {/* Step cards */}
      {steps.map((s) => (
        <StepCard key={s.step} step={s} />
      ))}

      {/* Thinking dots */}
      <AnimatePresence>
        {thinking && (
          <ThinkingDots agent={thinking.agent} status={thinking.status} />
        )}
      </AnimatePresence>

      {/* Run complete footer */}
      {!running && runMeta && runMeta.steps > 0 && (
        <div className="text-xs text-text-muted border-t border-border-subtle pt-3 mt-3 text-center">
          Run complete — {runMeta.steps} step{runMeta.steps > 1 ? 's' : ''} ·{' '}
          {runMeta.time}
        </div>
      )}
    </div>
  );
}
