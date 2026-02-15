import { useScenarioContext } from '../context/ScenarioContext';
import { useScenarios } from '../hooks/useScenarios';

interface ScenarioInfoPanelProps {
  onSelectQuestion: (question: string) => void;
}

export function ScenarioInfoPanel({ onSelectQuestion }: ScenarioInfoPanelProps) {
  const { activeScenario } = useScenarioContext();
  const { savedScenarios } = useScenarios();

  const scenario = savedScenarios.find(s => s.id === activeScenario);

  if (!activeScenario || !scenario) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-secondary">
        <div className="text-center">
          <span className="text-4xl mb-4 block">ℹ</span>
          <p>Select a scenario to view its description and example questions</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-8">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Title */}
        <div>
          <h2 className="text-2xl font-bold text-text-primary">
            {scenario.display_name || scenario.id}
          </h2>
          {scenario.domain && (
            <span className="inline-block mt-2 px-2 py-0.5 rounded-full bg-brand/15 text-brand text-xs font-medium">
              {scenario.domain}
            </span>
          )}
          <p className="mt-3 text-text-secondary leading-relaxed">
            {scenario.description}
          </p>
        </div>

        {/* Use Cases */}
        {scenario.use_cases && scenario.use_cases.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
              Use Cases
            </h3>
            <ul className="space-y-2">
              {scenario.use_cases.map((uc, i) => (
                <li key={i} className="flex items-start gap-2 text-text-primary">
                  <span className="text-brand mt-0.5">•</span>
                  <span>{uc}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Example Questions */}
        {scenario.example_questions && scenario.example_questions.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
              Example Questions
            </h3>
            <div className="space-y-2">
              {scenario.example_questions.map((q, i) => (
                <button
                  key={i}
                  onClick={() => onSelectQuestion(q)}
                  className="w-full text-left px-4 py-3 rounded-lg
                    bg-white/5 hover:bg-white/10 border border-white/10
                    hover:border-brand/50 text-text-primary transition-all
                    group cursor-pointer"
                >
                  <span className="text-sm">"{q}"</span>
                  <span className="ml-2 text-brand opacity-0 group-hover:opacity-100
                    transition-opacity text-xs">
                    → Use this question
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
