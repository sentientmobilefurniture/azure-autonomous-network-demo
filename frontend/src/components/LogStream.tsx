import { useEffect, useRef, useState } from 'react';

interface LogEntry {
  ts: string;
  level: string;
  name: string;
  msg: string;
}

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-gray-500',
  INFO: 'text-green-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-500 font-bold',
};

const MAX_LINES = 200;

interface LogStreamProps {
  url?: string;
  title?: string;
}

export function LogStream({ url = '/api/logs', title = 'Logs' }: LogStreamProps) {
  const [lines, setLines] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

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

  // SSE connection
  useEffect(() => {
    const evtSource = new EventSource(url);

    evtSource.addEventListener('log', (ev) => {
      try {
        const entry: LogEntry = JSON.parse(ev.data);
        setLines((prev) => {
          const next = [...prev, entry];
          return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next;
        });
      } catch {
        // ignore malformed events
      }
    });

    evtSource.onopen = () => setConnected(true);
    evtSource.onerror = () => {
      setConnected(false);
      // EventSource auto-reconnects
    };

    return () => evtSource.close();
  }, [url]);

  return (
    <div className="glass-card h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/10 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-text-secondary">
            &gt;_ {title}
          </span>
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full ${
              connected ? 'bg-green-400' : 'bg-red-400'
            }`}
            title={connected ? 'Connected' : 'Disconnected'}
          />
        </div>
        {!autoScroll && (
          <button
            onClick={() => {
              setAutoScroll(true);
              bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="text-[10px] text-brand hover:text-brand/80 font-mono"
          >
            ▼ scroll to bottom
          </button>
        )}
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
        {lines.map((line, i) => (
          <div key={i} className="whitespace-pre-wrap break-all">
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
