import type { ReactNode } from 'react';

interface BindingCardProps {
  /** Agent name label */
  label: string;
  /** Dot color (Tailwind class, e.g. "bg-blue-400") */
  color: string;
  /** Card body content (select, text display, etc.) */
  children: ReactNode;
}

/**
 * Reusable data-source binding card for SettingsModal custom mode.
 * Shows a colored dot + agent label header and renders children as the binding control.
 */
export function BindingCard({ label, color, children }: BindingCardProps) {
  return (
    <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${color}`} />
        <span className="text-sm font-medium text-text-primary">{label}</span>
      </div>
      {children}
    </div>
  );
}
