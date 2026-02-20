import { useState } from 'react';
import type { SubStep } from '../types/conversation';

interface SubStepListProps {
  subSteps: SubStep[];
  agentName: string;
}

export function SubStepList({ subSteps, agentName }: SubStepListProps) {
  const [expandedIdx, setExpandedIdx] = useState<Record<number, boolean>>({});

  const toggle = (idx: number) => {
    setExpandedIdx(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  if (!subSteps.length) return null;

  return (
    <div className="mt-2 ml-6 border-l-2 border-brand/30 pl-3 space-y-1.5">
      <span className="text-[10px] font-medium text-text-muted uppercase tracking-wide">
        Sub-queries ({subSteps.length})
      </span>
      {subSteps.map((ss) => {
        const isOpen = expandedIdx[ss.index] ?? false;
        return (
          <div
            key={ss.index}
            className="rounded border border-neutral-border/30 bg-neutral-bg2/50"
          >
            <button
              onClick={() => toggle(ss.index)}
              className="w-full text-left px-2.5 py-1.5 flex items-start gap-1.5 text-[11px] hover:bg-neutral-bg3/50 transition-colors"
            >
              <span className="text-brand/60 mt-0.5 flex-shrink-0">
                {isOpen ? '▾' : '▸'}
              </span>
              <span className="text-text-secondary truncate">
                <span className="font-medium text-text-muted">Q{ss.index + 1}:</span>{' '}
                {ss.query}
              </span>
            </button>
            {isOpen && (
              <div className="px-2.5 pb-2 text-[11px]">
                <div className="bg-neutral-bg3 rounded p-2 text-text-muted whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
                  {ss.resultSummary}
                </div>
                {ss.agent && ss.agent !== agentName && (
                  <span className="text-[10px] text-text-muted mt-1 block">
                    via {ss.agent}
                  </span>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
