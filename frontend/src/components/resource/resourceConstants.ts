import type { ResourceNodeType, ResourceEdgeType } from '../../types';

/** Colours per resource-node type */
export const RESOURCE_NODE_COLORS: Record<ResourceNodeType, string> = {
  orchestrator:   '#3b82f6', // blue-500
  agent:          '#60a5fa', // blue-400
  datasource:     '#22c55e', // green-500
  tool:           '#f59e0b', // amber-500
  'search-index': '#a855f7', // purple-500
};

/** Canvas radius per resource-node type */
export const RESOURCE_NODE_SIZES: Record<ResourceNodeType, number> = {
  orchestrator:   14,
  agent:          10,
  datasource:     10,
  tool:            8,
  'search-index': 10,
};

/** Edge colour per relationship type */
export const RESOURCE_EDGE_COLORS: Record<ResourceEdgeType, string> = {
  delegates_to: 'rgba(96,165,250,0.5)',   // blue
  uses_tool:    'rgba(245,158,11,0.4)',    // amber
  queries:      'rgba(34,197,94,0.4)',     // green
};

/** Edge dash pattern (empty = solid) */
export const RESOURCE_EDGE_DASH: Record<ResourceEdgeType, number[]> = {
  delegates_to: [],
  uses_tool:    [4, 2],
  queries:      [2, 2],
};

/** Human-readable labels shown on filter chips */
export const RESOURCE_TYPE_LABELS: Record<ResourceNodeType, string> = {
  orchestrator:   'Orchestrator',
  agent:          'Agent',
  datasource:     'Data Source',
  tool:           'Tool',
  'search-index': 'Search Index',
};
