import { useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import type { StepEvent, VisualizationData } from '../../types';
import { getVizButtonMeta } from '../../utils/agentType';
import { ThinkingDots } from '../ThinkingDots';
import { GraphResultView } from './GraphResultView';
import { TableResultView } from './TableResultView';
import { DocumentResultView } from './DocumentResultView';

interface StepVisualizationModalProps {
  isOpen: boolean;
  onClose: () => void;
  step: StepEvent;
  vizData: VisualizationData | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

const prefersReducedMotion =
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const backdropVariants = prefersReducedMotion
  ? {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    }
  : {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    };

const panelVariants = prefersReducedMotion
  ? {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    }
  : {
      initial: { opacity: 0, scale: 0.95, y: 10 },
      animate: { opacity: 1, scale: 1, y: 0 },
      exit: { opacity: 0, scale: 0.95, y: 10 },
    };

export function StepVisualizationModal({
  isOpen,
  onClose,
  step,
  vizData,
  loading,
  error,
  onRetry,
}: StepVisualizationModalProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const { icon, tooltip } = getVizButtonMeta(step.agent);

  // Capture the element that had focus before the modal opened
  useEffect(() => {
    if (isOpen) {
      triggerRef.current = document.activeElement as HTMLElement;
      // Focus close button on open
      setTimeout(() => closeButtonRef.current?.focus(), 50);
    } else if (triggerRef.current) {
      triggerRef.current.focus();
      triggerRef.current = null;
    }
  }, [isOpen]);

  // Escape to close
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  // Body scroll lock
  useEffect(() => {
    if (isOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [isOpen]);

  // Focus trap
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const modal = e.currentTarget;
      const focusable = modal.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    },
    [],
  );

  // Get the query text to display in the footer
  const queryText =
    vizData?.type === 'graph'
      ? vizData.data.query
      : vizData?.type === 'table'
        ? vizData.data.query
        : null;

  const copyQuery = useCallback(() => {
    if (queryText) {
      navigator.clipboard.writeText(queryText);
    }
  }, [queryText]);

  // Get modal title
  const title =
    vizData?.type === 'graph'
      ? 'Graph Query Results'
      : vizData?.type === 'table'
        ? 'Telemetry Data'
        : 'Agent Results';

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="glass-overlay fixed inset-0 z-40"
            {...backdropVariants}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            aria-hidden="true"
          />
          {/* Modal panel */}
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-6"
            role="dialog"
            aria-modal="true"
            aria-label={`${step.agent} ${tooltip}`}
            {...panelVariants}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            onKeyDown={handleKeyDown}
          >
            <div className="glass-card w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
              {/* Header */}
              <div className="flex items-center justify-between bg-neutral-bg2 border-b border-border px-4 py-3 shrink-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm">{icon}</span>
                  <span className="text-sm font-medium text-text-primary">
                    {step.agent}
                  </span>
                  <span className="text-xs text-text-muted">— {title}</span>
                </div>
                <button
                  ref={closeButtonRef}
                  onClick={onClose}
                  className="text-text-muted hover:text-text-primary text-lg leading-none
                             w-7 h-7 flex items-center justify-center rounded-md
                             hover:bg-neutral-bg3 transition-colors"
                  aria-label="Close"
                >
                  ✕
                </button>
              </div>

              {/* Content area */}
              <div className="flex-1 overflow-auto min-h-[300px]">
                {loading && (
                  <div className="flex flex-col items-center justify-center h-64 gap-3">
                    <ThinkingDots
                      agent={step.agent}
                      status={`Loading ${step.agent === 'GraphExplorerAgent' ? 'graph' : 'telemetry'} data...`}
                    />
                  </div>
                )}

                {error && !loading && (
                  <div className="flex flex-col items-center justify-center h-64 gap-3 text-center px-6">
                    <span className="text-status-warning text-2xl">⚠</span>
                    <span className="text-sm text-text-primary font-medium">
                      Could not load query results
                    </span>
                    <span className="text-xs text-text-secondary max-w-md">
                      {error}
                    </span>
                    {onRetry && (
                      <button
                        onClick={onRetry}
                        className="mt-2 bg-neutral-bg3 border border-border hover:bg-neutral-bg4
                                   text-xs text-text-primary rounded-md px-3 py-1.5 transition-colors"
                      >
                        Retry
                      </button>
                    )}
                  </div>
                )}

                {!loading && !error && vizData && (
                  <>
                    {vizData.type === 'graph' && (
                      <GraphResultView data={vizData} />
                    )}
                    {vizData.type === 'table' && (
                      <TableResultView data={vizData} />
                    )}
                    {vizData.type === 'documents' && (
                      <DocumentResultView data={vizData} />
                    )}
                  </>
                )}
              </div>

              {/* Footer — query preview + close */}
              <div className="border-t border-border-subtle px-4 py-3 shrink-0">
                {queryText && (
                  <details className="mb-2">
                    <summary className="text-[10px] font-medium text-text-muted uppercase tracking-wider cursor-pointer select-none hover:text-text-secondary">
                      ▾ Query
                    </summary>
                    <div className="flex items-start gap-2 mt-1.5">
                      <div className="flex-1 text-xs bg-neutral-bg3 rounded p-2 text-text-secondary whitespace-pre-wrap break-words font-mono max-h-24 overflow-auto">
                        {queryText}
                      </div>
                      <button
                        onClick={copyQuery}
                        className="text-[10px] text-text-muted hover:text-text-primary
                                   bg-neutral-bg3 border border-border rounded px-2 py-1
                                   hover:bg-neutral-bg4 transition-colors shrink-0"
                        title="Copy query to clipboard"
                      >
                        Copy
                      </button>
                    </div>
                  </details>
                )}
                <div className="flex justify-end">
                  <button
                    onClick={onClose}
                    className="text-xs text-text-muted hover:text-text-primary
                               bg-neutral-bg3 border border-border rounded-md px-3 py-1.5
                               hover:bg-neutral-bg4 transition-colors"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body,
  );
}
