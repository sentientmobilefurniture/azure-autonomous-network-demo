import { TabbedLogStream } from './TabbedLogStream';

/**
 * Persistent terminal panel — always visible at the bottom of the viewport.
 * Streams logs from all 3 sources regardless of scenario state.
 *
 * Tabs:
 *   API       — orchestrator, config, provisioning logs
 *   Graph API — query service, topology, backend logs
 *   Data Ops  — merged from both services: Cosmos, blob, search, ingest, Fabric
 */

const LOG_STREAMS = [
  { url: '/api/logs', title: 'API' },
  { url: '/query/logs', title: 'Graph API' },
  {
    url: ['/query/logs/data-ops', '/api/logs/data-ops'],
    title: 'Data Ops',
  },
];

export function TerminalPanel() {
  return (
    <div className="h-full border-t border-white/10 bg-neutral-bg1">
      <TabbedLogStream streams={LOG_STREAMS} />
    </div>
  );
}
