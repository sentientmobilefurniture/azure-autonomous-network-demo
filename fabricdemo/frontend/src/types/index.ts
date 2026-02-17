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
  /** Graph backend connector type — "fabric-gql" | "mock" */
  graph_connector?: string;
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
  /** High-level stage category from SSE stream (e.g. "validating", "creating_graph") */
  category?: string;
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

export type ResourceNodeType =
  | 'agent'
  | 'orchestrator'
  | 'datasource'
  | 'tool'
  | 'search-index'
  // Infrastructure layer
  | 'foundry'
  | 'storage'
  | 'search-service'
  | 'container-app'
  | 'blob-container';

export interface ResourceNode {
  id: string;
  label: string;
  type: ResourceNodeType;
  /** Extra metadata displayed in tooltip */
  meta?: Record<string, string>;
}

export type ResourceEdgeType =
  | 'delegates_to'
  | 'uses_tool'
  | 'queries'
  // Data-flow & infrastructure edges
  | 'stores_in'
  | 'hosted_on'
  | 'indexes_from'
  | 'runs_on'
  | 'contains';

export interface ResourceEdge {
  source: string;
  target: string;
  type: ResourceEdgeType;
  label: string;
}

// ---------------------------------------------------------------------------
// Graph topology types (used by GraphTopologyViewer and graph subcomponents)
// ---------------------------------------------------------------------------

export interface TopologyNode {
  id: string;
  label: string;     // vertex label (CoreRouter, AggSwitch, etc.)
  properties: Record<string, unknown>;
  // Force-graph internal fields (added by the library)
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

export interface TopologyEdge {
  id: string;
  source: string | TopologyNode;
  target: string | TopologyNode;
  label: string;     // edge label (connects_to, etc.)
  properties: Record<string, unknown>;
}

export interface TopologyMeta {
  node_count: number;
  edge_count: number;
  query_time_ms: number;
  labels: string[];
}

// ---------------------------------------------------------------------------
// Fabric discovery types (V11)
// ---------------------------------------------------------------------------

export interface FabricItem {
  id: string;
  display_name: string;
  type: string;
  description: string;
}
