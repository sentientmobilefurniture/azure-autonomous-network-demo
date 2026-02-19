import { useState, useCallback } from 'react';
import { AnimatePresence } from 'framer-motion';
import type { StepEvent, ThinkingState, RunMeta } from '../types';
import { StepCard } from './StepCard';
import { ThinkingDots } from './ThinkingDots';
import { OrchestratorThoughts } from './OrchestratorThoughts';

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
  // Track expanded state for each step, keyed by step number
  const [expandedSteps, setExpandedSteps] = useState<Record<number, boolean>>({});
  // Track expanded state for orchestrator thoughts, keyed by "t-{step}"
  const [expandedThoughts, setExpandedThoughts] = useState<Record<string, boolean>>({});

  const toggleStep = useCallback((stepNum: number) => {
    setExpandedSteps((prev) => ({ ...prev, [stepNum]: !prev[stepNum] }));
  }, []);

  const toggleThought = useCallback((stepNum: number) => {
    const key = `t-${stepNum}`;
    setExpandedThoughts((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const expandAll = useCallback(() => {
    const allSteps: Record<number, boolean> = {};
    const allThoughts: Record<string, boolean> = {};
    for (const s of steps) {
      allSteps[s.step] = true;
      if (s.reasoning) allThoughts[`t-${s.step}`] = true;
    }
    setExpandedSteps(allSteps);
    setExpandedThoughts(allThoughts);
  }, [steps]);

  const collapseAll = useCallback(() => {
    setExpandedSteps({});
    setExpandedThoughts({});
  }, []);

  const allExpanded = steps.length > 0
    && steps.every((s) => expandedSteps[s.step])
    && steps.filter((s) => s.reasoning).every((s) => expandedThoughts[`t-${s.step}`]);

  // Nothing to show yet
  if (!runStarted && steps.length === 0) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted">
          Investigation
        </span>
        {steps.length > 0 && (
          <button
            onClick={allExpanded ? collapseAll : expandAll}
            className="text-[10px] font-medium text-text-muted hover:text-brand
                       transition-colors px-1.5 py-0.5 rounded
                       hover:bg-brand/8"
            title={allExpanded ? 'Collapse all steps' : 'Expand all steps'}
          >
            {allExpanded ? '▴ Collapse All' : '▾ Expand All'}
          </button>
        )}
      </div>

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
        <div key={s.step} className="mb-2">
          {/* Reasoning box (renders null if no reasoning) */}
          {s.reasoning && (
            <>
              <OrchestratorThoughts
                reasoning={s.reasoning}
                expanded={expandedThoughts[`t-${s.step}`] ?? false}
                onToggle={() => toggleThought(s.step)}
              />
              {/* Visual connector: thin vertical line linking thought to its step */}
              <div className="ml-4 h-1.5 border-l-2 border-brand/20" aria-hidden="true" />
            </>
          )}
          {/* Step card */}
          <StepCard
            step={s}
            expanded={expandedSteps[s.step] ?? false}
            onToggle={() => toggleStep(s.step)}
          />
        </div>
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
