import { motion, AnimatePresence } from 'framer-motion';
import type { ActionData } from '../types';

interface ActionEmailModalProps {
  isOpen: boolean;
  onClose: () => void;
  action: ActionData;
}

export function ActionEmailModal({ isOpen, onClose, action }: ActionEmailModalProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 bg-black/60 z-50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            className="fixed inset-0 flex items-center justify-center z-50 p-4"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
          >
            <div className="glass-card w-full max-w-2xl max-h-[80vh] overflow-hidden
                            flex flex-col border border-amber-500/30">
              {/* Header — email style */}
              <div className="p-4 border-b border-border-subtle">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-amber-400">📧</span>
                    <span className="text-sm font-semibold text-text-primary">
                      Dispatch Email Preview
                    </span>
                  </div>
                  <button
                    onClick={onClose}
                    className="text-text-muted hover:text-text-primary text-lg
                               transition-colors"
                  >
                    ✕
                  </button>
                </div>

                {/* Email metadata */}
                <div className="space-y-1 text-xs text-text-secondary">
                  <div>
                    <span className="text-text-muted w-12 inline-block">To:</span>
                    <span className="font-medium">{action.engineer.name}</span>
                    <span className="text-text-muted"> &lt;{action.engineer.email}&gt;</span>
                  </div>
                  <div>
                    <span className="text-text-muted w-12 inline-block">Subject:</span>
                    <span className="font-medium">{action.email_subject}</span>
                  </div>
                  <div>
                    <span className="text-text-muted w-12 inline-block">Sent:</span>
                    <span>{new Date(action.dispatch_time).toLocaleString()}</span>
                  </div>
                </div>
              </div>

              {/* Email body — monospace to preserve formatting */}
              <div className="p-4 overflow-y-auto flex-1">
                <pre className="text-xs text-text-primary whitespace-pre-wrap
                               font-mono leading-relaxed">
                  {action.email_body}
                </pre>
              </div>

              {/* Footer with map link */}
              <div className="p-3 border-t border-border-subtle flex items-center
                             justify-between">
                <a
                  href={action.destination.maps_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-brand hover:text-brand/80 underline
                             transition-colors"
                >
                  📍 Open in Google Maps
                </a>
                <button
                  onClick={() => navigator.clipboard.writeText(action.email_body)}
                  className="text-xs text-text-muted hover:text-text-primary
                             transition-colors"
                >
                  Copy email
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
