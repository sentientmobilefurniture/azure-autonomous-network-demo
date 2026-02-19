import type { ReactNode } from 'react';

interface ModalShellProps {
  /** Visible title in the header */
  title: string;
  /** Close handler (backdrop click, ESC, ✕ button) */
  onClose: () => void;
  /** Optional footer content. If omitted, a default "Close" button is shown. */
  footer?: ReactNode;
  /** Modal body */
  children: ReactNode;
  /** Additional className for the dialog container */
  className?: string;
}

/**
 * Shared modal chrome — backdrop, dialog container, header with title + close,
 * scrollable body, and footer.
 */
export function ModalShell({ title, onClose, footer, children, className }: ModalShellProps) {
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
      onClick={handleBackdropClick}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
    >
      <div
        className={`bg-neutral-bg1 border border-border rounded-xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl ${className ?? ''}`}
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-4 pb-3 border-b border-border">
          <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary transition-colors text-xl leading-none"
          >
            ✕
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {children}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-border flex justify-end">
          {footer ?? (
            <button
              onClick={onClose}
              className="px-4 py-1.5 text-sm text-text-primary bg-neutral-bg3 hover:bg-neutral-bg4 rounded-md transition-colors"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
