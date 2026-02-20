import { useState } from 'react';
import { LogStream } from './LogStream';

interface StreamDef {
  url: string | string[];
  title: string;
}

interface TabbedLogStreamProps {
  streams: StreamDef[];
}

export function TabbedLogStream({ streams }: TabbedLogStreamProps) {
  const [activeTab, setActiveTab] = useState(0);

  return (
    <div className="h-full flex flex-col">
      {/* Tab bar */}
      <div className="flex border-b border-border px-2 shrink-0">
        {streams.map((s, i) => (
          <button
            key={s.title}
            onClick={() => setActiveTab(i)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              activeTab === i
                ? 'text-brand border-b-2 border-brand'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            {s.title}
          </button>
        ))}
      </div>

      {/* Active log stream — keep all mounted for SSE continuity */}
      <div className="flex-1 min-h-0 relative">
        {streams.map((s, i) => (
          <div
            key={s.title}
            className={i === activeTab ? 'h-full' : 'hidden'}
          >
            <LogStream url={s.url} title={s.title} />
          </div>
        ))}
      </div>
    </div>
  );
}
