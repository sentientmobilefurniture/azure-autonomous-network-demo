export interface StepEvent {
  step: number;
  agent: string;
  duration?: string;
  query?: string;
  response?: string;
  error?: boolean;
}

export interface ThinkingState {
  agent: string;
  status: string;
}

export interface RunMeta {
  steps: number;
  time: string;
}

// ---------------------------------------------------------------------------
// Scenario management types
// ---------------------------------------------------------------------------

export interface SavedScenario {
  id: string;               // scenario name (e.g. "cloud-outage")
  display_name: string;
  description: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  resources: {
    graph: string;
    telemetry_database: string;
    telemetry_container_prefix?: string;   // NEW — scenario prefix for container names
    runbooks_index: string;
    tickets_index: string;
    prompts_database: string;
    prompts_container?: string;            // NEW — per-scenario container in shared DB
  };
  upload_status: Record<string, {
    status: string;
    timestamp: string;
    [key: string]: unknown;
  }>;
  graph_styles?: {
    node_types?: Record<string, { color: string; size: number; icon?: string }>;
  };
  use_cases?: string[];
  example_questions?: string[];
  domain?: string;
}

export type SlotKey = 'graph' | 'telemetry' | 'runbooks' | 'tickets' | 'prompts';

export type SlotStatus = 'empty' | 'staged' | 'uploading' | 'done' | 'error';

export interface ScenarioUploadSlot {
  key: SlotKey;
  label: string;
  icon: string;
  file: File | null;
  status: SlotStatus;
  progress: string;
  pct: number;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface Interaction {
  id: string;
  scenario: string;
  query: string;
  steps: StepEvent[];
  diagnosis: string;
  run_meta: RunMeta | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Resource visualizer types
// ---------------------------------------------------------------------------

export type ResourceNodeType = 'agent' | 'orchestrator' | 'datasource' | 'tool' | 'search-index';

export interface ResourceNode {
  id: string;
  label: string;
  type: ResourceNodeType;
  /** Extra metadata displayed in tooltip */
  meta?: Record<string, string>;
}

export type ResourceEdgeType = 'delegates_to' | 'uses_tool' | 'queries';

export interface ResourceEdge {
  source: string;
  target: string;
  type: ResourceEdgeType;
  label: string;
}
