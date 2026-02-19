import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import type { StepEvent } from '../types';
import { getVizButtonMeta } from '../utils/agentType';
import { useVisualization } from '../hooks/useVisualization';
import { StepVisualizationModal } from './visualization/StepVisualizationModal';

interface StepCardProps {
  step: StepEvent;
  expanded?: boolean;
  onToggle?: () => void;
}

export function StepCard({ step, expanded: controlledExpanded, onToggle }: StepCardProps) {
  const [localExpanded, setLocalExpanded] = useState(false);
  const expanded = controlledExpanded ?? localExpanded;
  const toggleExpanded = onToggle ?? (() => setLocalExpanded((v) => !v));

  const [modalOpen, setModalOpen] = useState(false);
  const {
    getVisualization,
    data: vizData,
    loading: vizLoading,
    error: vizError,
    reset: vizReset,
  } = useVisualization();

  // Show viz button for ANY agent with meaningful content (not just doc agents)
  const hasContent = !!(step.response && step.response.length > 10);
  const showVizButton = !step.error && hasContent;

  const { icon, label, tooltip } = getVizButtonMeta(step.agent);

  const openModal = useCallback(async () => {
    setModalOpen(true);
    await getVisualization(step);
  }, [getVisualization, step]);

  const handleRetry = useCallback(async () => {
    vizReset();
    await getVisualization(step);
  }, [getVisualization, vizReset, step]);

  const closeModal = useCallback(() => {
    setModalOpen(false);
    vizReset();
  }, [vizReset]);

  return (
    <motion.div
      className={`glass-card p-3 cursor-pointer transition-colors ${
        step.error ? 'border-status-error/40 bg-red-500/5' : expanded ? 'border-brand/30' : ''
      }`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      onClick={() => toggleExpanded()}
    >
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full flex-shrink-0 ${
            step.error ? 'bg-status-error' : 'bg-brand'
          }`} />
          <span className={`text-sm font-medium ${
            step.error ? 'text-status-error' : 'text-text-primary'
          }`}>{step.agent}{step.error ? ' — FAILED' : ''}</span>
        </div>
        {step.duration && (
          <span className="text-xs text-text-muted">{step.duration}</span>
        )}
      </div>

      {/* Collapsed preview */}
      {!expanded && (
        <>
          {step.query && (
            <p className="text-[11px] text-text-muted mt-1.5 truncate">
              ▸ Query: {step.query.slice(0, 80)}
            </p>
          )}
          {step.response && (
            <p className="text-[11px] text-text-muted mt-0.5 truncate">
              ▸ Response: {step.response.slice(0, 80)}
            </p>
          )}
        </>
      )}

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            {step.query && (
              <div className="mt-2">
                <span className="text-[10px] font-medium text-text-muted uppercase">
                  ▾ Query
                </span>
                <div className="text-xs bg-neutral-bg3 rounded p-2 mt-1 text-text-secondary whitespace-pre-wrap break-words">
                  {step.query}
                </div>
              </div>
            )}
            {step.response && (
              <div className="mt-2">
                <span className="text-[10px] font-medium text-text-muted uppercase">
                  ▾ Response
                </span>
                <div className="text-xs prose prose-sm max-w-none mt-1 bg-neutral-bg3 rounded p-2">
                  <ReactMarkdown>{step.response}</ReactMarkdown>
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Visualization button — bottom-right */}
      {showVizButton && (
        <div className="flex justify-end mt-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              openModal();
            }}
            className="flex items-center gap-1.5 text-[10px] font-medium px-2.5 py-1
                       rounded-md border border-brand/30 bg-brand/8
                       text-brand hover:bg-brand/15 hover:border-brand/50
                       focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1
                       transition-all group/viz"
            aria-label={`${tooltip} for step ${step.step}`}
            title={tooltip}
          >
            <span className="text-xs group-hover/viz:scale-110 transition-transform">
              {icon}
            </span>
            <span>{label}</span>
          </button>
        </div>
      )}

      {/* Visualization modal */}
      <StepVisualizationModal
        isOpen={modalOpen}
        onClose={closeModal}
        step={step}
        vizData={vizData}
        loading={vizLoading}
        error={vizError}
        onRetry={handleRetry}
      />
    </motion.div>
  );
}
