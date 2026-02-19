// ---------------------------------------------------------------------------
// Visualization types (Story 1)
// ---------------------------------------------------------------------------

export type VisualizationType = 'graph' | 'table' | 'documents';

export interface VisualizationColumn {
  name: string;
  type: string;
}

export interface GraphVisualizationData {
  type: 'graph';
  data: {
    columns: VisualizationColumn[];
    data: Record<string, unknown>[];
    query: string;
  };
}

export interface TableVisualizationData {
  type: 'table';
  data: {
    columns: VisualizationColumn[];
    rows: Record<string, unknown>[];
    query: string;
  };
}

export interface SearchHit {
  score: number;
  title: string;
  content: string;
  chunk_id: string;
}

export interface DocumentVisualizationData {
  type: 'documents';
  data: {
    content: string;
    agent: string;
    citations?: string;
    searchHits?: SearchHit[];
    indexName?: string;
  };
}

export type VisualizationData =
  | GraphVisualizationData
  | TableVisualizationData
  | DocumentVisualizationData;

// ---------------------------------------------------------------------------
// Core event types
// ---------------------------------------------------------------------------

export interface StepEvent {
  step: number;
  agent: string;
  duration?: string;
  timestamp?: string;
  query?: string;
  response?: string;
  error?: boolean;
  visualization?: VisualizationData;
  reasoning?: string;
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

// ---------------------------------------------------------------------------
// Chat / Session types (persistent async conversations)
// ---------------------------------------------------------------------------

export type ChatRole = 'user' | 'orchestrator';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  timestamp: string;

  // User messages
  text?: string;

  // Orchestrator messages
  steps?: StepEvent[];           // reasoning lives on each step.reasoning
  diagnosis?: string;
  runMeta?: RunMeta;
  status?: 'thinking' | 'investigating' | 'complete' | 'error';
  errorMessage?: string;
}

export interface SessionSummary {
  id: string;
  scenario: string;
  alert_text: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  step_count: number;
  created_at: string;
  updated_at: string;
}

export interface SessionDetail {
  id: string;
  scenario: string;
  alert_text: string;
  status: string;
  created_at: string;
  updated_at: string;
  event_log: Array<{ event: string; data: string; turn?: number; timestamp?: string }>;
  steps: StepEvent[];
  diagnosis: string;
  run_meta: RunMeta | null;
  error_detail: string;
  thread_id: string | null;
  turn_count: number;
}
