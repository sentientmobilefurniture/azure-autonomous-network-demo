import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import type { StepEvent } from '../types';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // fallback
    }
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="opacity-0 group-hover/section:opacity-100 text-[10px] text-text-muted
                 hover:text-text-primary transition-all px-1 py-0.5 rounded hover:bg-neutral-bg4"
      title="Copy to clipboard"
    >
      {copied ? '✓' : '📋'}
    </button>
  );
}

export function StepCard({ step, forceExpanded }: { step: StepEvent; forceExpanded?: boolean }) {
  const [localExpanded, setLocalExpanded] = useState(false);
  const expanded = forceExpanded ?? localExpanded;

  return (
    <motion.div
      className={`glass-card p-3 mb-2 cursor-pointer transition-colors ${
        step.error ? 'border-status-error/40 bg-red-500/5' : expanded ? 'border-brand/30' : ''
      }`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      onClick={() => setLocalExpanded((v) => !v)}
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
              <div className="mt-2 group/section">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-medium text-text-muted uppercase">
                    ▾ Query
                  </span>
                  <CopyButton text={step.query} />
                </div>
                <div className="text-xs bg-neutral-bg3 rounded p-2 mt-1 text-text-secondary whitespace-pre-wrap break-words">
                  {step.query}
                </div>
              </div>
            )}
            {step.response && (
              <div className="mt-2 group/section">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-medium text-text-muted uppercase">
                    ▾ Response
                  </span>
                  <CopyButton text={step.response} />
                </div>
                <div className="text-xs prose prose-sm max-w-none mt-1 bg-neutral-bg3 rounded p-2">
                  <ReactMarkdown>{step.response}</ReactMarkdown>
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
