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
