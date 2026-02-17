interface ProgressBarProps {
  /** Percentage complete (0–100) */
  pct: number;
  className?: string;
}

/** Reusable slim progress bar with brand color fill. */
export function ProgressBar({ pct, className }: ProgressBarProps) {
  return (
    <div className={`bg-neutral-bg2 rounded-full h-1.5 ${className ?? ''}`}>
      <div
        className="bg-brand h-1.5 rounded-full transition-all"
        style={{ width: `${Math.max(pct, 0)}%` }}
      />
    </div>
  );
}
