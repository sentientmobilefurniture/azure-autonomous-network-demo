import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import type { StepEvent } from '../types';
import { getVizButtonMeta } from '../utils/agentType';
import { useVisualization } from '../hooks/useVisualization';
import { StepVisualizationModal } from './visualization/StepVisualizationModal';

// ---------------------------------------------------------------------------
// Error message parser — turns raw backend error strings into friendly UI
// ---------------------------------------------------------------------------

interface ErrorInfo {
  summary: string;
  detail: string;
  code: string;
  icon: string;
}

function parseErrorMessage(raw: string): ErrorInfo {
  // Strip "FAILED: " prefix
  const cleaned = raw.replace(/^FAILED:\s*/i, '');

  // Extract error code in brackets: [tool_server_error]
  const codeMatch = cleaned.match(/\[([^\]]+)\]/);
  const code = codeMatch ? codeMatch[1] : '';

  // Detect common error patterns
  if (/504|gateway\s*timeout/i.test(cleaned)) {
    return {
      summary: 'Gateway timeout — the backend query took too long',
      detail: 'The data source did not respond within the time limit. This is usually transient. The orchestrator will retry with a simpler query.',
      code,
      icon: '⏱',
    };
  }
  if (/502|bad\s*gateway/i.test(cleaned)) {
    return {
      summary: 'Bad gateway — upstream service unavailable',
      detail: 'The data source returned an invalid response. This may indicate a temporary outage.',
      code,
      icon: '🔌',
    };
  }
  if (/404|not\s*found|endpoint.*not\s*exist/i.test(cleaned)) {
    return {
      summary: 'Endpoint not found — data source may need rediscovery',
      detail: 'The query endpoint was not reachable. Try clicking rediscover or resubmitting the alert.',
      code,
      icon: '🔍',
    };
  }
  if (/401|403|unauthorized|forbidden/i.test(cleaned)) {
    return {
      summary: 'Authentication failed',
      detail: 'The service credential may have expired. Check the managed identity configuration.',
      code,
      icon: '🔒',
    };
  }
  if (/rate\s*limit|429|throttl/i.test(cleaned)) {
    return {
      summary: 'Rate limited — too many requests',
      detail: 'The API rate limit was exceeded. The orchestrator will back off and retry.',
      code,
      icon: '🚦',
    };
  }

  // Generic fallback
  return {
    summary: 'Agent call failed',
    detail: cleaned.replace(/\[.*?\]\s*/g, '').slice(0, 200),
    code,
    icon: '⚠',
  };
}

// ---------------------------------------------------------------------------

interface StepCardProps {
  step: StepEvent;
  expanded?: boolean;
  onToggle?: () => void;
}

export function StepCard({ step, expanded: controlledExpanded, onToggle }: StepCardProps) {
  const [localExpanded, setLocalExpanded] = useState(false);
  const expanded = controlledExpanded ?? localExpanded;
  const toggleExpanded = onToggle ?? (() => setLocalExpanded((v) => !v));

  // Parse error responses into friendly messages
  const errorInfo = step.error && step.response ? parseErrorMessage(step.response) : null;

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
        <div className="flex items-center gap-2 text-xs text-text-muted">
          {step.timestamp && (
            <span>{new Date(step.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
          )}
          {step.duration && step.timestamp && (
            <span className="text-text-muted/40">·</span>
          )}
          {step.duration && (
            <span>{step.duration}</span>
          )}
        </div>
      </div>

      {/* Collapsed preview */}
      {!expanded && (
        <>
          {step.error && errorInfo ? (
            <div className="mt-1.5 flex items-center gap-1.5">
              <span className="text-xs">{errorInfo.icon}</span>
              <p className="text-[11px] text-status-error">{errorInfo.summary}</p>
            </div>
          ) : (
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
                {step.error && errorInfo ? (
                  <>
                    <span className="text-[10px] font-medium text-status-error uppercase">
                      ▾ Error
                    </span>
                    <div className="mt-1 rounded-lg border border-status-error/30 bg-status-error/5 p-3">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-sm">{errorInfo.icon}</span>
                        <span className="text-xs font-medium text-status-error">{errorInfo.summary}</span>
                      </div>
                      {errorInfo.detail && (
                        <p className="text-[11px] text-text-muted leading-relaxed">{errorInfo.detail}</p>
                      )}
                      {errorInfo.code && (
                        <span className="inline-block mt-1.5 text-[10px] px-1.5 py-0.5 rounded
                                         bg-status-error/10 text-status-error/70 font-mono">
                          {errorInfo.code}
                        </span>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <span className="text-[10px] font-medium text-text-muted uppercase">
                      ▾ Response
                    </span>
                    <div className="text-xs prose prose-sm max-w-none mt-1 bg-neutral-bg3 rounded p-2">
                      <ReactMarkdown>{step.response}</ReactMarkdown>
                    </div>
                  </>
                )}
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
