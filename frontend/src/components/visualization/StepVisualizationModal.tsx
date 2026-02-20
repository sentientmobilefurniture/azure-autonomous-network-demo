import { useEffect, useRef, useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import type { ToolCall } from '../../types/conversation';
import type { VisualizationData } from '../../types';
import { getVizButtonMeta } from '../../utils/agentType';
import { GraphResultView } from './GraphResultView';
import { TableResultView } from './TableResultView';
import { DocumentResultView } from './DocumentResultView';

interface StepVisualizationModalProps {
  isOpen: boolean;
  onClose: () => void;
  toolCall: ToolCall;
  vizData: VisualizationData[];
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

const prefersReducedMotion =
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const backdropVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};

const panelVariants = prefersReducedMotion
  ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
  : {
      initial: { opacity: 0, scale: 0.95, y: 10 },
      animate: { opacity: 1, scale: 1, y: 0 },
      exit: { opacity: 0, scale: 0.95, y: 10 },
    };

type ModalTab = 'visualization' | 'summary';

export function StepVisualizationModal({
  isOpen,
  onClose,
  toolCall,
  vizData,
  loading,
  error,
  onRetry,
}: StepVisualizationModalProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const { icon, tooltip } = getVizButtonMeta(toolCall.agent);

  // Active viz item for multi-query tabs
  const [activeVizIndex, setActiveVizIndex] = useState(0);
  const activeViz = vizData.length > 0 ? vizData[activeVizIndex] ?? vizData[0] : null;

  // Tab state — graph/table get a "Visualization | Agent Summary" toggle
  const hasStructuredViz = activeViz && (activeViz.type === 'graph' || activeViz.type === 'table');
  const [activeTab, setActiveTab] = useState<ModalTab>('visualization');

  // Reset tab and viz index when modal opens
  useEffect(() => {
    if (isOpen) {
      setActiveTab('visualization');
      setActiveVizIndex(0);
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) {
      triggerRef.current = document.activeElement as HTMLElement;
      setTimeout(() => closeButtonRef.current?.focus(), 50);
    } else if (triggerRef.current) {
      triggerRef.current.focus();
      triggerRef.current = null;
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose(); }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = prev; };
    }
  }, [isOpen]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key !== 'Tab') return;
    const modal = e.currentTarget;
    const focusable = modal.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }, []);

  const queryText =
    activeViz?.type === 'graph' ? activeViz.data.query
    : activeViz?.type === 'table' ? activeViz.data.query
    : null;

  const copyQuery = useCallback(() => {
    if (queryText) navigator.clipboard.writeText(queryText);
  }, [queryText]);

  const title =
    activeViz?.type === 'graph' ? 'Graph Query Results'
    : activeViz?.type === 'table' ? 'Telemetry Data'
    : 'Agent Results';

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className="glass-overlay fixed inset-0 z-40"
            {...backdropVariants}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            aria-hidden="true"
          />
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-6"
            role="dialog"
            aria-modal="true"
            aria-label={`${toolCall.agent} ${tooltip}`}
            {...panelVariants}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            onKeyDown={handleKeyDown}
          >
            <div className="glass-card w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
              {/* Header */}
              <div className="flex items-center justify-between bg-neutral-bg2 border-b border-border px-4 py-3 shrink-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm">{icon}</span>
                  <span className="text-sm font-medium text-text-primary">{toolCall.agent}</span>
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

              {/* Tab toggle for graph/table views */}
              {hasStructuredViz && toolCall.response && (
                <div className="flex gap-1 px-4 pt-3 pb-0 shrink-0">
                  <div className="flex gap-1 p-0.5 bg-neutral-bg3 rounded-lg w-fit">
                    <button
                      onClick={() => setActiveTab('visualization')}
                      className={`text-[10px] font-medium px-3 py-1 rounded-md transition-colors ${
                        activeTab === 'visualization'
                          ? 'bg-neutral-bg1 text-text-primary shadow-sm'
                          : 'text-text-muted hover:text-text-secondary'
                      }`}
                    >
                      {activeViz?.type === 'graph' ? 'Graph & Data' : 'Data Table'}
                    </button>
                    <button
                      onClick={() => setActiveTab('summary')}
                      className={`text-[10px] font-medium px-3 py-1 rounded-md transition-colors ${
                        activeTab === 'summary'
                          ? 'bg-neutral-bg1 text-text-primary shadow-sm'
                          : 'text-text-muted hover:text-text-secondary'
                      }`}
                    >
                      Agent Summary
                    </button>
                  </div>
                </div>
              )}

              {/* Multi-query tab bar — only when more than 1 viz */}
              {vizData.length > 1 && activeTab === 'visualization' && (
                <div className="flex gap-1 px-4 pt-2 pb-0 shrink-0 overflow-x-auto">
                  {vizData.map((v, i) => {
                    const q = (v.type === 'graph' || v.type === 'table') ? v.data.query : undefined;
                    const tabLabel = q
                      ? q.length > 40 ? q.slice(0, 40) + '…' : q
                      : `Query ${i + 1}`;
                    return (
                      <button
                        key={i}
                        onClick={() => setActiveVizIndex(i)}
                        className={`text-[10px] font-mono px-2.5 py-1 rounded-md border transition-colors whitespace-nowrap ${
                          activeVizIndex === i
                            ? 'bg-brand/10 border-brand/40 text-brand'
                            : 'bg-neutral-bg3 border-border text-text-muted hover:text-text-secondary hover:border-border'
                        }`}
                        title={q ?? `Query ${i + 1}`}
                      >
                        {tabLabel}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Content area */}
              <div className="flex-1 overflow-auto min-h-[300px]">
                {loading && (
                  <div className="flex flex-col items-center justify-center h-64 gap-3">
                    <div className="flex items-center gap-2">
                      <svg className="animate-spin h-5 w-5 text-brand" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      <span className="text-sm text-text-muted">
                        Loading {toolCall.agent === 'GraphExplorerAgent' ? 'graph' : 'telemetry'} data…
                      </span>
                    </div>
                  </div>
                )}

                {error && !loading && (
                  <div className="flex flex-col items-center justify-center h-64 gap-3 text-center px-6">
                    <span className="text-status-warning text-2xl">⚠</span>
                    <span className="text-sm text-text-primary font-medium">Could not load query results</span>
                    <span className="text-xs text-text-secondary max-w-md">{error}</span>
                    {onRetry && (
                      <button onClick={onRetry}
                        className="mt-2 bg-neutral-bg3 border border-border hover:bg-neutral-bg4
                                   text-xs text-text-primary rounded-md px-3 py-1.5 transition-colors">
                        Retry
                      </button>
                    )}
                  </div>
                )}

                {!loading && !error && activeViz && (
                  <>
                    {/* Visualization tab (or default for documents) */}
                    {activeTab === 'visualization' && (
                      <>
                        {activeViz.type === 'graph' && <GraphResultView data={activeViz} />}
                        {activeViz.type === 'table' && <TableResultView data={activeViz} />}
                        {activeViz.type === 'documents' && <DocumentResultView data={activeViz} />}
                      </>
                    )}

                    {/* Agent Summary tab */}
                    {activeTab === 'summary' && toolCall.response && (
                      <div className="p-4">
                        <div className="text-sm prose prose-sm max-w-none">
                          <ReactMarkdown>{toolCall.response}</ReactMarkdown>
                        </div>
                      </div>
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
