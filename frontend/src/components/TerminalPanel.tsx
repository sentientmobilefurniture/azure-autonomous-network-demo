import { TabbedLogStream } from './TabbedLogStream';

/**
 * Persistent terminal panel — always visible at the bottom of the viewport.
 * Streams logs from both services regardless of scenario state.
 *
 * Tabs:
 *   API       — orchestrator, config, provisioning logs
 *   Graph API — query service, topology, backend logs
 */

const LOG_STREAMS = [
  { url: '/api/logs', title: 'API' },
  { url: '/query/logs', title: 'Graph API' },
];

export function TerminalPanel() {
  return (
    <div className="h-full border-t border-border bg-neutral-bg1">
      <TabbedLogStream streams={LOG_STREAMS} />
    </div>
  );
}
