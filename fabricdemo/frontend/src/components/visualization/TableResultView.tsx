import { useState, useMemo } from 'react';
import type { TableVisualizationData, VisualizationColumn } from '../../types';

interface TableResultViewProps {
  data: TableVisualizationData;
}

const MAX_DISPLAY_ROWS = 100;

/** Severity → text color mapping for NOC context */
const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: 'text-status-error font-medium',
  MAJOR: 'text-status-warning',
  WARNING: 'text-yellow-400',
  MINOR: 'text-text-secondary',
};

function isNumericType(type: string): boolean {
  const t = type.toLowerCase();
  return ['int', 'long', 'real', 'double', 'float', 'decimal', 'number'].some(
    (n) => t.includes(n),
  );
}

function isDateType(type: string): boolean {
  const t = type.toLowerCase();
  return t.includes('date') || t.includes('time');
}

function formatCell(value: unknown, col: VisualizationColumn): string {
  if (value == null) return '—';
  const s = String(value);

  if (isDateType(col.type)) {
    // Try to extract time portion for compact display
    const m = s.match(/T(\d{2}:\d{2}:\d{2})/);
    if (m) return m[1];
  }
  if (isNumericType(col.type) && typeof value === 'number') {
    return Number.isInteger(value) ? value.toString() : value.toFixed(2);
  }
  return s;
}

export function TableResultView({ data }: TableResultViewProps) {
  const columns = data.data.columns ?? [];
  const allRows = data.data.rows ?? [];
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const toggleSort = (colName: string) => {
    if (sortCol === colName) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(colName);
      setSortDir('asc');
    }
  };

  const sortedRows = useMemo(() => {
    if (!sortCol) return allRows;
    return [...allRows].sort((a, b) => {
      const av = a[sortCol] ?? '';
      const bv = b[sortCol] ?? '';
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      const sa = String(av);
      const sb = String(bv);
      return sortDir === 'asc' ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
  }, [allRows, sortCol, sortDir]);

  const displayRows = sortedRows.slice(0, MAX_DISPLAY_ROWS);
  const truncated = allRows.length > MAX_DISPLAY_ROWS;

  if (columns.length === 0 && allRows.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-text-muted text-sm">
        No data returned
      </div>
    );
  }

  return (
    <div className="p-4 overflow-auto max-h-full">
      {/* Row count header */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted">
          Showing {displayRows.length} of {allRows.length} results
          {truncated && ' (truncated)'}
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-xs text-left">
          <thead>
            <tr className="bg-neutral-bg2 border-b border-border">
              {columns.map((col) => (
                <th
                  key={col.name}
                  className="px-3 py-2 text-[10px] font-medium uppercase tracking-wider
                             text-text-muted cursor-pointer hover:text-text-primary
                             select-none whitespace-nowrap"
                  onClick={() => toggleSort(col.name)}
                  aria-sort={
                    sortCol === col.name
                      ? sortDir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : 'none'
                  }
                >
                  {col.name}
                  {sortCol === col.name && (
                    <span className="ml-1">
                      {sortDir === 'asc' ? '▴' : '▾'}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-border-subtle last:border-0
                           hover:bg-brand/5 transition-colors"
              >
                {columns.map((col) => {
                  const val = row[col.name];
                  const formatted = formatCell(val, col);
                  // Apply severity highlighting
                  const severityClass =
                    col.name === 'Severity'
                      ? SEVERITY_COLORS[String(val)] ?? ''
                      : '';
                  return (
                    <td
                      key={col.name}
                      className={`px-3 py-2 whitespace-nowrap ${
                        isNumericType(col.type)
                          ? 'font-mono tabular-nums'
                          : ''
                      } ${severityClass}`}
                      title={String(val)}
                    >
                      {formatted}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
