import type { VisualizationType } from '../types';

/**
 * Resolve an agent name to its visualization type.
 */
export function getVisualizationType(agent: string): VisualizationType {
  switch (agent) {
    case 'GraphExplorerAgent':
      return 'graph';
    case 'TelemetryAgent':
      return 'table';
    case 'RunbookKBAgent':
    case 'HistoricalTicketAgent':
    case 'AzureAISearch':
      return 'documents';
    default:
      return 'documents';
  }
}

/**
 * Get the icon, label, and tooltip for a visualization button based on agent name.
 */
export function getVizButtonMeta(agent: string): {
  icon: string;
  label: string;
  tooltip: string;
} {
  switch (agent) {
    case 'GraphExplorerAgent':
      return { icon: '⬡', label: 'View Graph', tooltip: 'View graph query results' };
    case 'TelemetryAgent':
      return { icon: '▤', label: 'View Data', tooltip: 'View telemetry data table' };
    case 'RunbookKBAgent':
      return { icon: '▧', label: 'View Docs', tooltip: 'View runbook search results' };
    case 'HistoricalTicketAgent':
      return { icon: '▧', label: 'View Docs', tooltip: 'View historical ticket results' };
    case 'dispatch_field_engineer':
      return { icon: '⚡', label: 'View Action', tooltip: 'View field dispatch details' };
    default:
      return { icon: '▧', label: 'View Docs', tooltip: 'View results' };
  }
}
