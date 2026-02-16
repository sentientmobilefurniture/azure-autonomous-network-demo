/**
 * First-run empty state — shown in the Investigate tab when no scenario
 * is loaded and no saved scenarios exist yet.
 *
 * Guides the user through the 4-step onboarding flow:
 *   1. Upload data  →  2. Select scenario  →  3. Provision agents  →  4. Investigate
 */

const STEPS = [
  { num: 1, label: 'Upload data', icon: '📂' },
  { num: 2, label: 'Select scenario', icon: '🎯' },
  { num: 3, label: 'Provision agents', icon: '🤖' },
  { num: 4, label: 'Investigate', icon: '🔍' },
] as const;

interface EmptyStateProps {
  onUpload: () => void;
}

export function EmptyState({ onUpload }: EmptyStateProps) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md w-full text-center space-y-6">
        {/* Heading */}
        <div className="space-y-2">
          <h2 className="text-lg font-semibold text-text-primary">
            No scenario loaded
          </h2>
          <p className="text-sm text-text-secondary">
            Upload a scenario data pack to start investigating with AI agents.
          </p>
        </div>

        {/* Step indicators */}
        <div className="flex items-center justify-center gap-2">
          {STEPS.map((step, i) => (
            <div key={step.num} className="flex items-center gap-2">
              <div className="flex flex-col items-center gap-1">
                <span className="text-lg">{step.icon}</span>
                <span className="text-[10px] text-text-muted whitespace-nowrap">
                  {step.num}. {step.label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <span className="text-text-muted/40 text-xs mt-[-14px]">→</span>
              )}
            </div>
          ))}
        </div>

        {/* Primary CTA */}
        <button
          onClick={onUpload}
          className="px-6 py-2.5 bg-brand hover:bg-brand/90 text-white text-sm font-medium rounded-lg transition-colors shadow-lg shadow-brand/20"
        >
          📂 Upload Scenario
        </button>
      </div>
    </div>
  );
}
