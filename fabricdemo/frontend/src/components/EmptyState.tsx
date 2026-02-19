interface EmptyStateProps {
  exampleQuestions?: string[];
  onSelect: (text: string) => void;
}

export function EmptyState({ exampleQuestions, onSelect }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-4">
      <span className="text-brand text-4xl opacity-40 mb-4">◇</span>
      <p className="text-sm text-text-muted mb-2">
        Submit an alert to begin investigation
      </p>
      <p className="text-xs text-text-muted max-w-[300px] mb-6">
        The orchestrator will coordinate specialist agents to diagnose the incident.
      </p>

      {exampleQuestions && exampleQuestions.length > 0 && (
        <div className="w-full max-w-md space-y-2">
          {exampleQuestions.map((q, i) => (
            <button
              key={i}
              onClick={() => onSelect(q)}
              className="w-full text-left text-xs px-3 py-2.5 rounded-lg
                         border border-border-subtle bg-neutral-bg3
                         hover:border-brand/30 hover:bg-neutral-bg4
                         text-text-secondary hover:text-text-primary
                         transition-colors cursor-pointer"
            >
              💡 {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
