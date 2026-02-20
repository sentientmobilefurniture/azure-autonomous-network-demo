import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import type { DocumentVisualizationData } from '../../types';

interface DocumentResultViewProps {
  data: DocumentVisualizationData;
}

const AGENT_BADGES: Record<string, { subtitle: string; className: string }> = {
  RunbookKBAgent: {
    subtitle: 'Operational Runbook Results',
    className: 'border-blue-500/20 bg-blue-500/5 text-blue-300',
  },
  HistoricalTicketAgent: {
    subtitle: 'Historical Incident Records',
    className: 'border-amber-500/20 bg-amber-500/5 text-amber-300',
  },
  AzureAISearch: {
    subtitle: 'Search Results',
    className: 'border-brand/20 bg-brand/5 text-brand',
  },
};

export function DocumentResultView({ data }: DocumentResultViewProps) {
  const badge = AGENT_BADGES[data.data.agent] ?? {
    subtitle: 'Agent Results',
    className: 'border-brand/20 bg-brand/5 text-brand',
  };

  const hasSearchHits = data.data.searchHits && data.data.searchHits.length > 0;
  const [activeTab, setActiveTab] = useState<'search' | 'summary'>(hasSearchHits ? 'search' : 'summary');

  return (
    <div className="p-4 overflow-auto max-h-full">
      {/* Agent badge */}
      <div
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border mb-4 ${badge.className}`}
      >
        <span className="text-xs">▧</span>
        <div>
          <span className="text-xs font-medium">{data.data.agent}</span>
          <span className="text-[10px] text-text-muted ml-2">
            {badge.subtitle}
          </span>
        </div>
      </div>

      {/* Tab toggle (only if search hits available) */}
      {hasSearchHits && (
        <div className="flex gap-1 mb-4 p-0.5 bg-neutral-bg3 rounded-lg w-fit">
          <button
            onClick={() => setActiveTab('search')}
            className={`text-[10px] font-medium px-3 py-1 rounded-md transition-colors ${
              activeTab === 'search'
                ? 'bg-neutral-bg1 text-text-primary shadow-sm'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            Search Results ({data.data.searchHits!.length})
          </button>
          <button
            onClick={() => setActiveTab('summary')}
            className={`text-[10px] font-medium px-3 py-1 rounded-md transition-colors ${
              activeTab === 'summary'
                ? 'bg-neutral-bg1 text-text-primary shadow-sm'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            Agent Summary
          </button>
        </div>
      )}

      {/* Search Results tab */}
      {activeTab === 'search' && hasSearchHits && (
        <div className="space-y-3">
          {data.data.indexName && (
            <div className="text-[10px] text-text-muted uppercase tracking-wider mb-2">
              Index: {data.data.indexName} — {data.data.searchHits!.length} results
            </div>
          )}
          {data.data.searchHits!.map((hit, i) => (
            <div
              key={hit.chunk_id || i}
              className="rounded-lg border border-border-subtle bg-neutral-bg2 overflow-hidden"
            >
              {/* Hit header */}
              <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle bg-neutral-bg3">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-text-muted">#{i + 1}</span>
                  <span className="text-xs font-medium text-text-primary truncate max-w-[400px]">
                    {hit.title || hit.chunk_id || `Result ${i + 1}`}
                  </span>
                </div>
                <span className="text-[10px] font-mono text-text-muted"
                      title="Search relevance score">
                  score: {hit.score.toFixed(2)}
                </span>
              </div>
              {/* Hit content */}
              <div className="px-3 py-2 text-xs text-text-secondary whitespace-pre-wrap break-words max-h-48 overflow-auto">
                {hit.content || '(no content)'}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Summary tab (agent response) */}
      {activeTab === 'summary' && (
        <>
          {/* Citations section (if present) */}
          {data.data.citations && (
            <div className="mb-4 p-3 rounded-lg bg-neutral-bg2 border border-border-subtle">
              <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider block mb-1.5">
                Sources Referenced
              </span>
              <div className="text-xs text-text-secondary whitespace-pre-wrap">
                {data.data.citations}
              </div>
            </div>
          )}

          {/* Main content rendered as Markdown */}
          <div className="max-w-prose">
            <div className="text-sm prose prose-sm max-w-none">
              <ReactMarkdown>{data.data.content}</ReactMarkdown>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
