import { useState } from 'react';
import type { ChatMessage } from '../types';
import { OrchestratorThoughts } from './OrchestratorThoughts';
import { StepGroup } from './StepGroup';
import { DiagnosisBlock } from './DiagnosisBlock';
import { ThinkingDots } from './ThinkingDots';

interface OrchestratorBubbleProps {
  message: ChatMessage;
}

export function OrchestratorBubble({ message }: OrchestratorBubbleProps) {
  const [stepsExpanded, setStepsExpanded] = useState(false);
  const [diagnosisExpanded, setDiagnosisExpanded] = useState(true);
  const steps = message.steps ?? [];
  const isLive = message.status === 'thinking' || message.status === 'investigating';

  return (
    <div className="flex justify-start">
      <div className="glass-card p-3 w-full">
        <span className="text-[10px] uppercase text-text-muted block mb-2">
          <span className="text-brand">◇</span> Orchestrator
          {isLive && <span className="ml-2 animate-pulse text-brand">●</span>}
        </span>

        {/* Orchestrator reasoning (if any) */}
        {message.thinking?.map((t, i) => (
          <OrchestratorThoughts key={i} reasoning={t} />
        ))}

        {/* Collapsible step group */}
        {steps.length > 0 && (
          <StepGroup
            steps={steps}
            expanded={stepsExpanded}
            onToggle={() => setStepsExpanded(v => !v)}
          />
        )}

        {/* Live thinking indicator within this bubble */}
        {isLive && !message.diagnosis && (
          <ThinkingDots agent="Orchestrator" status={message.status} />
        )}

        {/* Error */}
        {message.errorMessage && (
          <div className="mt-2 p-2 rounded bg-status-error/10 border border-status-error/30
                          text-xs text-status-error">
            ⚠ {message.errorMessage}
          </div>
        )}

        {/* Collapsible diagnosis */}
        {message.diagnosis && (
          <DiagnosisBlock
            text={message.diagnosis}
            expanded={diagnosisExpanded}
            onToggle={() => setDiagnosisExpanded(v => !v)}
          />
        )}

        {/* Footer */}
        {message.runMeta && (
          <div className="flex items-center justify-between text-[10px] text-text-muted
                          border-t border-border-subtle pt-2 mt-3">
            <span>
              {message.runMeta.steps} step{message.runMeta.steps !== 1 ? 's' : ''} · {message.runMeta.time}
            </span>
            <button
              onClick={() => navigator.clipboard.writeText(message.diagnosis ?? '')}
              className="hover:text-text-primary transition-colors"
            >
              Copy
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
