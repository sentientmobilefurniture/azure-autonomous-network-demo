// Scenario configuration — fetched from /api/config/scenario at runtime.
// Replaces the previous hardcoded SCENARIO const.

export interface DemoFlowStep {
  prompt: string;
  expect: string;
}

export interface DemoFlow {
  title: string;
  description: string;
  steps: DemoFlowStep[];
}

export interface ScenarioConfig {
  name: string;
  displayName: string;
  description: string;
  graph: string;
  runbooksIndex: string;
  ticketsIndex: string;
  graphStyles: {
    nodeColors: Record<string, string>;
    nodeSizes: Record<string, number>;
    nodeIcons: Record<string, string>;
  };
  exampleQuestions: string[];
  useCases: string[];
  demoFlows: DemoFlow[];
}

let _cached: ScenarioConfig | null = null;
let _fetchPromise: Promise<ScenarioConfig> | null = null;

export async function getScenario(): Promise<ScenarioConfig> {
  if (_cached) return _cached;
  if (!_fetchPromise) {
    _fetchPromise = fetch("/api/config/scenario")
      .then((r) => r.json())
      .then((data: ScenarioConfig) => {
        _cached = data;
        return data;
      });
  }
  return _fetchPromise;
}

// Synchronous fallback for initial render — populated after first fetch
export const SCENARIO_DEFAULTS: ScenarioConfig = {
  name: "",
  displayName: "Loading...",
  description: "",
  graph: "",
  runbooksIndex: "",
  ticketsIndex: "",
  graphStyles: { nodeColors: {}, nodeSizes: {}, nodeIcons: {} },
  exampleQuestions: [],
  useCases: [],
  demoFlows: [],
};

// Backward-compat: synchronous access (returns cached or defaults)
export function getScenarioSync(): ScenarioConfig {
  return _cached ?? SCENARIO_DEFAULTS;
}
