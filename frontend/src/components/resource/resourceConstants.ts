import type { ResourceNodeType, ResourceEdgeType } from '../../types';

/** Colours per resource-node type */
export const RESOURCE_NODE_COLORS: Record<ResourceNodeType, string> = {
  orchestrator:     '#3b82f6', // blue-500
  agent:            '#60a5fa', // blue-400
  datasource:       '#22c55e', // green-500
  tool:             '#f59e0b', // amber-500
  'search-index':   '#a855f7', // purple-500
  // Infrastructure layer
  foundry:          '#ec4899', // pink-500
  storage:          '#06b6d4', // cyan-500
  'cosmos-account': '#10b981', // emerald-500
  'search-service': '#8b5cf6', // violet-500
  'container-app':  '#f97316', // orange-500
  'blob-container': '#67e8f9', // cyan-300
  'cosmos-database':'#34d399', // emerald-400
};

/** Canvas radius per resource-node type */
export const RESOURCE_NODE_SIZES: Record<ResourceNodeType, number> = {
  orchestrator:     14,
  agent:            10,
  datasource:       10,
  tool:              8,
  'search-index':   10,
  // Infrastructure layer
  foundry:          12,
  storage:          12,
  'cosmos-account': 12,
  'search-service': 12,
  'container-app':  12,
  'blob-container':  8,
  'cosmos-database': 8,
};

/** Edge colour per relationship type */
export const RESOURCE_EDGE_COLORS: Record<ResourceEdgeType, string> = {
  delegates_to: 'rgba(96,165,250,0.7)',   // blue — up from 0.5
  uses_tool:    'rgba(245,158,11,0.6)',    // amber — up from 0.4
  queries:      'rgba(34,197,94,0.6)',     // green — up from 0.4
  // Data-flow & infrastructure edges
  stores_in:    'rgba(6,182,212,0.6)',     // cyan — up from 0.4
  hosted_on:    'rgba(249,115,22,0.5)',    // orange — up from 0.3
  indexes_from: 'rgba(139,92,246,0.6)',    // violet — up from 0.4
  runs_on:      'rgba(249,115,22,0.5)',    // orange — up from 0.3
  contains:     'rgba(255,255,255,0.3)',   // up from 0.15
};

/** Edge dash pattern (empty = solid) */
export const RESOURCE_EDGE_DASH: Record<ResourceEdgeType, number[]> = {
  delegates_to: [],
  uses_tool:    [4, 2],
  queries:      [2, 2],
  stores_in:    [6, 3],
  hosted_on:    [3, 3],
  indexes_from: [4, 2],
  runs_on:      [3, 3],
  contains:     [1, 2],
};

/** Human-readable labels shown on filter chips */
export const RESOURCE_TYPE_LABELS: Record<ResourceNodeType, string> = {
  orchestrator:     'Orchestrator',
  agent:            'Agent',
  datasource:       'Data Source',
  tool:             'Tool',
  'search-index':   'Search Index',
  foundry:          'AI Foundry',
  storage:          'Storage',
  'cosmos-account': 'Cosmos DB',
  'search-service': 'Search Service',
  'container-app':  'Container App',
  'blob-container': 'Blob Container',
  'cosmos-database':'Database',
};
