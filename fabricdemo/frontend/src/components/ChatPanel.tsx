import { useState, useCallback } from 'react';
import type { ChatMessage, ThinkingState } from '../types';
import { UserMessage } from './UserMessage';
import { OrchestratorThoughts } from './OrchestratorThoughts';
import { StepCard } from './StepCard';
import { ActionCard } from './ActionCard';
import { DiagnosisBlock } from './DiagnosisBlock';
import { ThinkingDots } from './ThinkingDots';

interface ChatPanelProps {
  messages: ChatMessage[];
  currentThinking: ThinkingState | null;
}

export function ChatPanel({
  messages, currentThinking,
}: ChatPanelProps) {
  // Per-step expand/collapse state, shared across the whole thread
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});
  const [expandedThoughts, setExpandedThoughts] = useState<Record<string, boolean>>({});

  const toggleStep = useCallback((msgId: string, stepNum: number) => {
    const key = `${msgId}-${stepNum}`;
    setExpandedSteps(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const toggleThought = useCallback((msgId: string, stepNum: number) => {
    const key = `${msgId}-t-${stepNum}`;
    setExpandedThoughts(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  if (messages.length === 0 && !currentThinking) {
    return (
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="text-center">
          <span className="text-brand text-3xl opacity-40 block mb-3">◇</span>
          <p className="text-sm text-text-muted">Submit an alert to begin investigation</p>
          <p className="text-xs text-text-muted mt-1">Use the examples dropdown or paste a NOC alert below.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-2">

        {messages.map((msg) => {
          if (msg.role === 'user') {
            return <UserMessage key={msg.id} message={msg} />;
          }

          // Orchestrator turn — render elements FLAT, no wrapper box
          const steps = msg.steps ?? [];
          const isLive = msg.status === 'thinking' || msg.status === 'investigating';

          return (
            <div key={msg.id} className="space-y-2">
              {/* Each step renders at the top level with its reasoning */}
              {steps.map((s) => (
                <div key={s.step}>
                  {s.reasoning && (
                    <>
                      <OrchestratorThoughts
                        reasoning={s.reasoning}
                        expanded={expandedThoughts[`${msg.id}-t-${s.step}`] ?? false}
                        onToggle={() => toggleThought(msg.id, s.step)}
                      />
                      <div className="ml-4 h-1.5 border-l-2 border-brand/20" aria-hidden="true" />
                    </>
                  )}
                  {/* Branch on is_action — ternary, not early return */}
                  {s.is_action
                    ? <ActionCard step={s} />
                    : <StepCard
                        step={s}
                        expanded={expandedSteps[`${msg.id}-${s.step}`] ?? false}
                        onToggle={() => toggleStep(msg.id, s.step)}
                      />
                  }
                </div>
              ))}

              {/* Live thinking indicator between steps */}
              {isLive && !msg.diagnosis && (
                <ThinkingDots agent="Orchestrator" status="processing..." />
              )}

              {/* Error */}
              {msg.errorMessage && (
                <div className="glass-card p-3 border-status-error/30 bg-status-error/5">
                  <span className="text-xs text-status-error">⚠ {msg.errorMessage}</span>
                </div>
              )}

              {/* Diagnosis — standalone glass-card, collapsible */}
              {msg.diagnosis && (
                <DiagnosisBlock text={msg.diagnosis} />
              )}

              {/* Run meta footer */}
              {msg.runMeta && (
                <div className="flex items-center justify-between text-[10px] text-text-muted px-1">
                  <span>
                    {msg.runMeta.steps} step{msg.runMeta.steps !== 1 ? 's' : ''} · {msg.runMeta.time}
                  </span>
                  <button
                    onClick={() => navigator.clipboard.writeText(msg.diagnosis ?? '')}
                    className="hover:text-text-primary transition-colors"
                  >
                    Copy
                  </button>
                </div>
              )}
            </div>
          );
        })}

        {/* Global thinking indicator for new turns */}
        {currentThinking && (
          <ThinkingDots agent={currentThinking.agent} status={currentThinking.status} />
        )}
    </div>
  );
}
