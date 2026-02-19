import { useEffect, useRef, useState } from 'react';

interface LogEntry {
  id: number;
  ts: string;
  level: string;
  name: string;
  msg: string;
}

let _logIdCounter = 0;

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-gray-500',
  INFO: 'text-status-success',
  WARNING: 'text-status-warning',
  ERROR: 'text-status-error',
  CRITICAL: 'text-status-error font-bold',
};

const MAX_LINES = 200;

interface LogStreamProps {
  /** Single SSE url or array of urls to merge */
  url?: string | string[];
  title?: string;
}

export function LogStream({ url = '/api/logs', title = 'Logs' }: LogStreamProps) {
  const [lines, setLines] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [minLevel, setMinLevel] = useState<string>('DEBUG');

  const LEVEL_ORDER: Record<string, number> = {
    DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4,
  };

  const filteredLines = lines.filter(l => (LEVEL_ORDER[l.level] ?? 0) >= (LEVEL_ORDER[minLevel] ?? 0));

  // Auto-scroll when new lines arrive
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines, autoScroll]);

  // Detect manual scroll-up to pause auto-scroll
  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  };

  // SSE connection(s) — supports single url or multiple merged sources
  useEffect(() => {
    const urls = Array.isArray(url) ? url : [url];
    const sources: EventSource[] = [];
    let openCount = 0;

    const addEntry = (raw: Record<string, unknown>) => {
      const entry: LogEntry = { ...(raw as Omit<LogEntry, 'id'>), id: ++_logIdCounter };
      setLines((prev) => {
        const next = [...prev, entry];
        return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next;
      });
    };

    for (const u of urls) {
      const evtSource = new EventSource(u);

      evtSource.addEventListener('log', (ev) => {
        try {
          addEntry(JSON.parse(ev.data));
        } catch {
          // ignore malformed events
        }
      });

      evtSource.onopen = () => {
        openCount++;
        if (openCount > 0) setConnected(true);
      };
      evtSource.onerror = () => {
        openCount = Math.max(0, openCount - 1);
        if (openCount === 0) setConnected(false);
      };

      sources.push(evtSource);
    }

    return () => sources.forEach((s) => s.close());
  }, [Array.isArray(url) ? url.join(',') : url]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="glass-card h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-text-secondary">
            &gt;_ {title}
          </span>
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full ${
              connected ? 'bg-status-success' : 'bg-status-error'
            }`}
            title={connected ? 'Connected' : 'Disconnected'}
          />
        </div>
        <div className="flex items-center gap-2">
          {/* Level filter */}
          <select
            value={minLevel}
            onChange={(e) => setMinLevel(e.target.value)}
            className="text-[10px] bg-neutral-bg3 border border-border rounded px-1 py-0.5
                       text-text-secondary focus:outline-none cursor-pointer"
            title="Minimum log level"
          >
            <option value="DEBUG">DEBUG+</option>
            <option value="INFO">INFO+</option>
            <option value="WARNING">WARN+</option>
            <option value="ERROR">ERROR+</option>
          </select>

          {/* Clear button */}
          <button
            onClick={() => setLines([])}
            className="text-[10px] text-text-muted hover:text-text-primary transition-colors"
            title="Clear log output"
          >
            🗑
          </button>

          {!autoScroll && (
            <button
              onClick={() => {
                setAutoScroll(true);
                bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
              }}
              className="text-[10px] text-brand hover:text-brand/80 font-mono"
            >
              ▼ bottom
            </button>
          )}
        </div>
      </div>

      {/* Log body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-2 font-mono text-[11px] leading-[1.6] select-text"
      >
        {lines.length === 0 && (
          <span className="text-text-tertiary italic">Waiting for log output...</span>
        )}
        {filteredLines.map((line) => (
          <div key={line.id} className="whitespace-pre-wrap break-all">
            <span className="text-text-tertiary">{line.ts}</span>{' '}
            <span className={LEVEL_COLORS[line.level] ?? 'text-text-secondary'}>
              {line.level.padEnd(8)}
            </span>{' '}
            <span className="text-text-secondary">{line.name}:</span>{' '}
            <span className="text-text-primary">{line.msg.replace(/^\S+ \S+ \S+: /, '')}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
