import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import { useScenario } from '../ScenarioContext';
import type { DemoFlow } from '../config';

function DemoFlowCard({ flow, onUsePrompt }: { flow: DemoFlow; onUsePrompt?: (prompt: string) => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="glass-card overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-neutral-bg3/50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-text-primary truncate">{flow.title}</h3>
          <p className="text-xs text-text-muted mt-0.5 line-clamp-2">{flow.description}</p>
        </div>
        <span
          className={clsx(
            'ml-3 text-text-muted transition-transform shrink-0',
            expanded && 'rotate-90',
          )}
        >
          ▸
        </span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3 border-t border-border pt-3">
              {flow.steps.map((step, i) => (
                <div key={i} className="rounded-lg border border-border bg-neutral-bg1 p-3">
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-mono bg-brand/10 text-brand px-1.5 py-0.5 rounded shrink-0">
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-text-primary font-medium">"{step.prompt}"</p>
                      <p className="text-xs text-text-muted mt-1.5 leading-relaxed">{step.expect}</p>
                    </div>
                    {onUsePrompt && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onUsePrompt(step.prompt); }}
                        className="shrink-0 text-xs text-brand hover:text-brand-hover font-medium px-2 py-1 rounded hover:bg-brand/10 transition-colors"
                        title="Use this prompt"
                      >
                        Use ▸
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

interface ScenarioPanelProps {
  onUsePrompt?: (prompt: string) => void;
}

export function ScenarioPanel({ onUsePrompt }: ScenarioPanelProps) {
  const SCENARIO = useScenario();

  const isLoading = !SCENARIO.name;

  return (
    <div className="h-full w-full overflow-y-auto p-6">
      {isLoading ? (
        <div className="flex items-center justify-center h-full text-text-muted text-sm">
          Loading scenario…
        </div>
      ) : (
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Scenario header */}
        <div className="glass-card p-5">
          <h1 className="text-lg font-semibold text-text-primary">{SCENARIO.displayName}</h1>
          <p className="text-sm text-text-secondary mt-2 leading-relaxed">{SCENARIO.description}</p>

          <div className="flex flex-wrap gap-2 mt-4">
            <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted bg-neutral-bg3 px-2 py-0.5 rounded">
              {SCENARIO.name}
            </span>
            <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted bg-neutral-bg3 px-2 py-0.5 rounded">
              Graph: {SCENARIO.graph || '—'}
            </span>
          </div>
        </div>

        {/* Use cases */}
        {SCENARIO.useCases.length > 0 && (
          <div>
            <h2 className="text-xs uppercase tracking-wider font-medium text-text-muted mb-3">
              Use Cases
            </h2>
            <ul className="space-y-1.5">
              {SCENARIO.useCases.map((uc, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                  <span className="text-brand mt-0.5 shrink-0">•</span>
                  {uc}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Example questions */}
        {SCENARIO.exampleQuestions.length > 0 && (
          <div>
            <h2 className="text-xs uppercase tracking-wider font-medium text-text-muted mb-3">
              Example Questions
            </h2>
            <div className="grid gap-2">
              {SCENARIO.exampleQuestions.map((q, i) => (
                <button
                  key={i}
                  onClick={() => onUsePrompt?.(q)}
                  className={clsx(
                    'text-left text-sm px-3 py-2 rounded-lg border border-border',
                    'bg-neutral-bg1 hover:bg-neutral-bg3 text-text-secondary hover:text-text-primary',
                    'transition-colors cursor-pointer',
                    onUsePrompt ? '' : 'cursor-default',
                  )}
                >
                  "{q}"
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Demo flows */}
        {SCENARIO.demoFlows && SCENARIO.demoFlows.length > 0 && (
          <div>
            <h2 className="text-xs uppercase tracking-wider font-medium text-text-muted mb-3">
              Demo Flows
            </h2>
            <div className="space-y-3">
              {SCENARIO.demoFlows.map((flow, i) => (
                <DemoFlowCard key={i} flow={flow} onUsePrompt={onUsePrompt} />
              ))}
            </div>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
