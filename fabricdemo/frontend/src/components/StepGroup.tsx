import { motion, AnimatePresence } from 'framer-motion';
import type { StepEvent } from '../types';
import { StepCard } from './StepCard';

interface StepGroupProps {
  steps: StepEvent[];
  expanded: boolean;
  onToggle: () => void;
}

export function StepGroup({ steps, expanded, onToggle }: StepGroupProps) {
  const failedCount = steps.filter(s => s.error).length;

  return (
    <div className="my-2">
      {/* Summary header (always visible, clickable) */}
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-xs text-text-secondary
                   hover:text-text-primary transition-colors w-full text-left
                   py-1.5 px-2 rounded hover:bg-neutral-bg3"
      >
        <span className="text-[10px]">{expanded ? '▾' : '▸'}</span>
        <span>
          Investigated with {steps.length} agent{steps.length !== 1 ? 's' : ''}
          {failedCount > 0 && (
            <span className="text-status-error ml-1">
              ({failedCount} failed)
            </span>
          )}
        </span>
        <span className="text-text-muted ml-auto text-[10px]">
          {steps.map(s => s.agent).join(', ')}
        </span>
      </button>

      {/* Expanded: individual step cards */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden pl-4 border-l-2 border-brand/20 mt-1 space-y-2"
          >
            {steps.map((s) => (
              <StepCard key={s.step} step={s} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
