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

// ── Mock data (matches current 5-agent provisioning) ────────────────────────

const MOCK_NODES: ResourceNode[] = [
  // Agents
  { id: 'orchestrator',    label: 'Orchestrator',          type: 'orchestrator', meta: { model: 'gpt-4.1', role: 'Delegates to sub-agents, synthesises diagnosis' } },
  { id: 'graph-explorer',  label: 'GraphExplorerAgent',    type: 'agent',        meta: { model: 'gpt-4.1', role: 'Traverses topology graph via Gremlin' } },
  { id: 'telemetry-agent', label: 'TelemetryAgent',        type: 'agent',        meta: { model: 'gpt-4.1', role: 'Queries alert & link telemetry' } },
  { id: 'runbook-agent',   label: 'RunbookKBAgent',        type: 'agent',        meta: { model: 'gpt-4.1', role: 'Searches operational runbooks' } },
  { id: 'ticket-agent',    label: 'HistoricalTicketAgent',  type: 'agent',        meta: { model: 'gpt-4.1', role: 'Searches past incident tickets' } },

  // Tools
  { id: 'tool-graph-query',      label: 'OpenAPI: query_graph',     type: 'tool', meta: { spec: 'openapi/cosmosdb.yaml', endpoint: '/query/graph/{graph}' } },
  { id: 'tool-telemetry-query',  label: 'OpenAPI: query_telemetry', type: 'tool', meta: { spec: 'openapi/cosmosdb.yaml', endpoint: '/query/telemetry' } },
  { id: 'tool-search-runbooks',  label: 'AzureAISearchTool',        type: 'tool', meta: { queryType: 'semantic', topK: '5' } },
  { id: 'tool-search-tickets',   label: 'AzureAISearchTool',        type: 'tool', meta: { queryType: 'semantic', topK: '5' } },

  // Data sources
  { id: 'cosmos-gremlin', label: 'Cosmos Gremlin',               type: 'datasource',   meta: { backend: 'cosmosdb', database: 'networkgraph', graph: 'telco-noc-topology' } },
  { id: 'cosmos-nosql',   label: 'Cosmos NoSQL (Telemetry)',      type: 'datasource',   meta: { backend: 'cosmosdb', database: 'telco-noc-telemetry', containers: 'AlertStream, LinkTelemetry' } },
  { id: 'search-runbooks', label: 'runbooks-index',              type: 'search-index', meta: { service: 'Azure AI Search', indexer: 'blob → chunked docs' } },
  { id: 'search-tickets',  label: 'tickets-index',               type: 'search-index', meta: { service: 'Azure AI Search', indexer: 'blob → chunked docs' } },
];

const MOCK_EDGES: ResourceEdge[] = [
  // Orchestrator → sub-agents
  { source: 'orchestrator', target: 'graph-explorer',  type: 'delegates_to', label: 'delegates' },
  { source: 'orchestrator', target: 'telemetry-agent', type: 'delegates_to', label: 'delegates' },
  { source: 'orchestrator', target: 'runbook-agent',   type: 'delegates_to', label: 'delegates' },
  { source: 'orchestrator', target: 'ticket-agent',    type: 'delegates_to', label: 'delegates' },

  // Agents → tools
  { source: 'graph-explorer',  target: 'tool-graph-query',     type: 'uses_tool', label: 'uses' },
  { source: 'telemetry-agent', target: 'tool-telemetry-query', type: 'uses_tool', label: 'uses' },
  { source: 'runbook-agent',   target: 'tool-search-runbooks', type: 'uses_tool', label: 'uses' },
  { source: 'ticket-agent',    target: 'tool-search-tickets',  type: 'uses_tool', label: 'uses' },

  // Tools → data sources
  { source: 'tool-graph-query',     target: 'cosmos-gremlin',  type: 'queries', label: 'queries' },
  { source: 'tool-telemetry-query', target: 'cosmos-nosql',    type: 'queries', label: 'queries' },
  { source: 'tool-search-runbooks', target: 'search-runbooks', type: 'queries', label: 'queries' },
  { source: 'tool-search-tickets',  target: 'search-tickets',  type: 'queries', label: 'queries' },
];

// ── Hook ────────────────────────────────────────────────────────────────────

export function useResourceGraph(): ResourceGraphData {
  return useMemo(() => ({ nodes: MOCK_NODES, edges: MOCK_EDGES }), []);
}
