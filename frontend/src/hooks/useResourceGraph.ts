/**
 * useResourceGraph — provides the resource / agent-flow graph.
 *
 * Currently returns **mock data** matching the hardcoded 5-agent telco-noc
 * scenario.  Once the genericised config-YAML endpoint lands, swap the
 * constant for a `fetch('/api/config/resources')` call.
 */

import { useMemo } from 'react';
import type { ResourceNode, ResourceEdge } from '../types';

export interface ResourceGraphData {
  nodes: ResourceNode[];
  edges: ResourceEdge[];
}

// ── Mock data (matches current 5-agent telco-noc + full infra) ──────────────

const MOCK_NODES: ResourceNode[] = [
  // ── Agent layer ───────────────────────────────────────────────────────────
  { id: 'orchestrator',    label: 'Orchestrator',          type: 'orchestrator', meta: { model: 'gpt-4.1', role: 'Delegates to sub-agents, synthesises diagnosis' } },
  { id: 'graph-explorer',  label: 'GraphExplorerAgent',    type: 'agent',        meta: { model: 'gpt-4.1', role: 'Traverses topology graph via Gremlin' } },
  { id: 'telemetry-agent', label: 'TelemetryAgent',        type: 'agent',        meta: { model: 'gpt-4.1', role: 'Queries alert & link telemetry' } },
  { id: 'runbook-agent',   label: 'RunbookKBAgent',        type: 'agent',        meta: { model: 'gpt-4.1', role: 'Searches operational runbooks' } },
  { id: 'ticket-agent',    label: 'HistoricalTicketAgent',  type: 'agent',        meta: { model: 'gpt-4.1', role: 'Searches past incident tickets' } },

  // ── Tool layer ────────────────────────────────────────────────────────────
  { id: 'tool-graph-query',      label: 'OpenAPI: query_graph',     type: 'tool', meta: { spec: 'openapi/cosmosdb.yaml', endpoint: '/query/graph/{graph}' } },
  { id: 'tool-telemetry-query',  label: 'OpenAPI: query_telemetry', type: 'tool', meta: { spec: 'openapi/cosmosdb.yaml', endpoint: '/query/telemetry' } },
  { id: 'tool-search-runbooks',  label: 'AzureAISearchTool',        type: 'tool', meta: { queryType: 'semantic', index: 'runbooks' } },
  { id: 'tool-search-tickets',   label: 'AzureAISearchTool',        type: 'tool', meta: { queryType: 'semantic', index: 'tickets' } },

  // ── Data source layer ─────────────────────────────────────────────────────
  { id: 'ds-graph',    label: 'Graph: telco-noc-topology', type: 'datasource',   meta: { backend: 'cosmosdb-gremlin', database: 'networkgraph' } },
  { id: 'ds-telemetry', label: 'Telemetry NoSQL',          type: 'datasource',   meta: { backend: 'cosmosdb-nosql', containers: 'AlertStream, LinkTelemetry' } },
  { id: 'ds-runbooks',  label: 'runbooks-index',           type: 'search-index', meta: { indexer: 'blob → chunked docs' } },
  { id: 'ds-tickets',   label: 'tickets-index',            type: 'search-index', meta: { indexer: 'blob → chunked docs' } },

  // ── Blob containers (upload targets) ──────────────────────────────────────
  { id: 'blob-runbooks',      label: 'runbooks',       type: 'blob-container', meta: { purpose: 'Operational runbook documents' } },
  { id: 'blob-tickets',       label: 'tickets',        type: 'blob-container', meta: { purpose: 'Historical incident tickets' } },
  { id: 'blob-telemetry',     label: 'telemetry-data', type: 'blob-container', meta: { purpose: 'Telemetry CSV uploads' } },
  { id: 'blob-network',       label: 'network-data',   type: 'blob-container', meta: { purpose: 'Network topology CSV uploads' } },

  // ── Cosmos databases ──────────────────────────────────────────────────────
  { id: 'db-networkgraph', label: 'networkgraph',  type: 'cosmos-database', meta: { api: 'Gremlin', graph: 'telco-noc-topology' } },
  { id: 'db-telemetry',    label: 'telemetry',     type: 'cosmos-database', meta: { api: 'NoSQL', containers: 'scenarios, interactions, telco-noc-*' } },
  { id: 'db-prompts',      label: 'prompts',       type: 'cosmos-database', meta: { api: 'NoSQL', containers: 'telco-noc' } },

  // ── Infrastructure services ───────────────────────────────────────────────
  { id: 'infra-foundry',  label: 'AI Foundry',          type: 'foundry',        meta: { resource: 'aif-*', region: 'Sweden Central' } },
  { id: 'infra-cosmos-g', label: 'Cosmos DB (Gremlin)',  type: 'cosmos-account', meta: { resource: 'cosmos-gremlin-*', api: 'Gremlin' } },
  { id: 'infra-cosmos-n', label: 'Cosmos DB (NoSQL)',    type: 'cosmos-account', meta: { resource: 'cosmos-gremlin-*-nosql', api: 'NoSQL' } },
  { id: 'infra-storage',  label: 'Storage Account',     type: 'storage',        meta: { resource: 'st*', kind: 'BlobStorage' } },
  { id: 'infra-search',   label: 'AI Search',           type: 'search-service', meta: { resource: 'srch-*', tier: 'Standard' } },
  { id: 'infra-app',      label: 'Container App',       type: 'container-app',  meta: { resource: 'ca-app-*', image: 'api + graph-query-api + frontend' } },
];

const MOCK_EDGES: ResourceEdge[] = [
  // ── Orchestrator → sub-agents ─────────────────────────────────────────────
  { source: 'orchestrator', target: 'graph-explorer',  type: 'delegates_to', label: 'delegates' },
  { source: 'orchestrator', target: 'telemetry-agent', type: 'delegates_to', label: 'delegates' },
  { source: 'orchestrator', target: 'runbook-agent',   type: 'delegates_to', label: 'delegates' },
  { source: 'orchestrator', target: 'ticket-agent',    type: 'delegates_to', label: 'delegates' },

  // ── Agents → tools ────────────────────────────────────────────────────────
  { source: 'graph-explorer',  target: 'tool-graph-query',     type: 'uses_tool', label: 'uses' },
  { source: 'telemetry-agent', target: 'tool-telemetry-query', type: 'uses_tool', label: 'uses' },
  { source: 'runbook-agent',   target: 'tool-search-runbooks', type: 'uses_tool', label: 'uses' },
  { source: 'ticket-agent',    target: 'tool-search-tickets',  type: 'uses_tool', label: 'uses' },

  // ── Tools → data sources ──────────────────────────────────────────────────
  { source: 'tool-graph-query',     target: 'ds-graph',    type: 'queries', label: 'queries' },
  { source: 'tool-telemetry-query', target: 'ds-telemetry', type: 'queries', label: 'queries' },
  { source: 'tool-search-runbooks', target: 'ds-runbooks', type: 'queries', label: 'queries' },
  { source: 'tool-search-tickets',  target: 'ds-tickets',  type: 'queries', label: 'queries' },

  // ── Data sources → infrastructure databases ───────────────────────────────
  { source: 'ds-graph',     target: 'db-networkgraph', type: 'stores_in',    label: 'stored in' },
  { source: 'ds-telemetry', target: 'db-telemetry',    type: 'stores_in',    label: 'stored in' },

  // ── Search indexes ← blob containers (indexing pipeline) ──────────────────
  { source: 'blob-runbooks', target: 'ds-runbooks', type: 'indexes_from', label: 'indexes' },
  { source: 'blob-tickets',  target: 'ds-tickets',  type: 'indexes_from', label: 'indexes' },

  // ── Blob containers → data upload flow ────────────────────────────────────
  { source: 'blob-telemetry', target: 'ds-telemetry', type: 'indexes_from', label: 'ingested into' },
  { source: 'blob-network',   target: 'ds-graph',     type: 'indexes_from', label: 'ingested into' },

  // ── Databases → Cosmos accounts ───────────────────────────────────────────
  { source: 'db-networkgraph', target: 'infra-cosmos-g', type: 'contains', label: '' },
  { source: 'db-telemetry',    target: 'infra-cosmos-n', type: 'contains', label: '' },
  { source: 'db-prompts',      target: 'infra-cosmos-n', type: 'contains', label: '' },

  // ── Blob containers → storage account ─────────────────────────────────────
  { source: 'blob-runbooks',  target: 'infra-storage', type: 'contains', label: '' },
  { source: 'blob-tickets',   target: 'infra-storage', type: 'contains', label: '' },
  { source: 'blob-telemetry', target: 'infra-storage', type: 'contains', label: '' },
  { source: 'blob-network',   target: 'infra-storage', type: 'contains', label: '' },

  // ── Search indexes → search service ───────────────────────────────────────
  { source: 'ds-runbooks', target: 'infra-search', type: 'hosted_on', label: 'hosted on' },
  { source: 'ds-tickets',  target: 'infra-search', type: 'hosted_on', label: 'hosted on' },

  // ── Agents → Foundry (provisioned on) ─────────────────────────────────────
  { source: 'orchestrator',    target: 'infra-foundry', type: 'runs_on', label: 'provisioned on' },
  { source: 'graph-explorer',  target: 'infra-foundry', type: 'runs_on', label: '' },
  { source: 'telemetry-agent', target: 'infra-foundry', type: 'runs_on', label: '' },
  { source: 'runbook-agent',   target: 'infra-foundry', type: 'runs_on', label: '' },
  { source: 'ticket-agent',    target: 'infra-foundry', type: 'runs_on', label: '' },
];

// ── Hook ────────────────────────────────────────────────────────────────────

export function useResourceGraph(): ResourceGraphData {
  return useMemo(() => ({ nodes: MOCK_NODES, edges: MOCK_EDGES }), []);
}
