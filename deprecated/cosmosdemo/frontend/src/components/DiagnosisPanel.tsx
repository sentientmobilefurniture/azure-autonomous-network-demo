import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import { ThinkingDots } from './ThinkingDots';
import type { RunMeta } from '../types';

interface DiagnosisPanelProps {
  finalMessage: string;
  running: boolean;
  runMeta: RunMeta | null;
}

export function DiagnosisPanel({
  finalMessage,
  running,
  runMeta,
}: DiagnosisPanelProps) {
  return (
    <div className="h-full overflow-y-auto p-4 flex flex-col">
      <AnimatePresence mode="wait">
        {/* State 1: Empty — before any investigation */}
        {!finalMessage && !running && (
          <motion.div
            key="empty"
            className="glass-card p-6 flex-1 flex flex-col items-center justify-center text-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <span className="text-brand text-3xl opacity-40 mb-4">◇</span>
            <p className="text-sm text-text-muted">
              Submit an alert to begin investigation
            </p>
            <p className="text-xs text-text-muted mt-2 max-w-[260px]">
              The orchestrator will coordinate specialist agents to diagnose the
              incident.
            </p>
          </motion.div>
        )}

        {/* State 2: Loading — investigation running, no final message yet */}
        {!finalMessage && running && (
          <motion.div
            key="loading"
            className="glass-card p-6 flex-1 flex flex-col items-center justify-center text-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted mb-4">
              Diagnosis
            </span>
            <div className="flex gap-1 mb-3">
              <ThinkingDots />
            </div>
            <p className="text-xs text-text-muted">
              Agents are investigating...
            </p>
          </motion.div>
        )}

        {/* State 3: Complete — diagnosis rendered */}
        {finalMessage && (
          <motion.div
            key="result"
            className="glass-card p-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
          >
            <div className="flex items-center justify-between mb-4">
              <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted">
                Diagnosis
              </span>
              <button
                className="text-xs text-text-muted hover:text-text-primary transition-colors px-2 py-1 rounded hover:bg-white/5"
                onClick={() => navigator.clipboard.writeText(finalMessage)}
              >
                Copy
              </button>
            </div>

            <div className="prose prose-sm prose-invert max-w-none">
              <ReactMarkdown>{finalMessage}</ReactMarkdown>
            </div>

            {runMeta && (
              <div className="text-xs text-text-muted border-t border-white/5 pt-3 mt-6">
                {runMeta.steps} agent step{runMeta.steps !== 1 ? 's' : ''} ·{' '}
                {runMeta.time}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
