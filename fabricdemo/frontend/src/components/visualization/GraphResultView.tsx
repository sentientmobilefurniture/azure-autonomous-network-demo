import { useMemo, useRef, useEffect, useCallback, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import type { GraphVisualizationData } from '../../types';

interface GraphResultViewProps {
  data: GraphVisualizationData;
}

interface GraphNode {
  id: string;
  label: string;
  type: string;
  properties: Record<string, unknown>;
  x?: number;
  y?: number;
}

interface GraphLink {
  source: string;
  target: string;
  label: string;
}

// Default color palette
const DEFAULT_TYPE_COLORS: Record<string, string> = {
  CoreRouter: '#1A9C85',
  TransportLink: '#4EA8DF',
  MPLSPath: '#FF8C42',
  Service: '#E05C63',
  AggSwitch: '#9C6ADE',
  BaseStation: '#F7B731',
  SLAPolicy: '#A5D6A7',
  BGPSession: '#78909C',
  entity: '#B0B0B0',
  SECONDARY: '#4EA8DF',
  PRIMARY: '#1A9C85',
  TERTIARY: '#FF8C42',
};

// Preset colors for the picker
const COLOR_PRESETS = [
  '#1A9C85', '#4EA8DF', '#FF8C42', '#E05C63', '#9C6ADE',
  '#F7B731', '#A5D6A7', '#78909C', '#F06292', '#81C784',
  '#FFD54F', '#90CAF9', '#CE93D8', '#FFAB91', '#80DEEA',
];

/**
 * Find the best "ID" column — prefer columns with "Id" in the name.
 */
function findIdColumn(columns: { name: string }[]): { name: string } | undefined {
  return columns.find((c) => c.name.toLowerCase().endsWith('id'))
    ?? columns.find((c) => c.name.toLowerCase().includes('id'))
    ?? columns[0];
}

function parseGraphData(
  columns: { name: string; type: string }[],
  rows: Record<string, unknown>[],
): { nodes: GraphNode[]; links: GraphLink[] } {
  const nodeMap = new Map<string, GraphNode>();
  const links: GraphLink[] = [];

  const colNames = columns.map((c) => c.name.toLowerCase());
  const hasSourceTarget =
    colNames.some((n) => n.includes('source')) &&
    colNames.some((n) => n.includes('target'));

  if (hasSourceTarget) {
    const sourceCol = columns.find((c) => c.name.toLowerCase().includes('source'))!;
    const targetCol = columns.find((c) => c.name.toLowerCase().includes('target'))!;
    const labelCol = columns.find(
      (c) => c.name.toLowerCase().includes('label') ||
             c.name.toLowerCase().includes('type') ||
             c.name.toLowerCase().includes('relationship'),
    );
    for (const row of rows) {
      const src = String(row[sourceCol.name] ?? '');
      const tgt = String(row[targetCol.name] ?? '');
      if (!src || !tgt) continue;
      if (!nodeMap.has(src))
        nodeMap.set(src, { id: src, label: src, type: 'entity', properties: {} });
      if (!nodeMap.has(tgt))
        nodeMap.set(tgt, { id: tgt, label: tgt, type: 'entity', properties: {} });
      links.push({ source: src, target: tgt, label: labelCol ? String(row[labelCol.name] ?? '') : '' });
    }
  } else {
    // Use ID column as node ID and label
    const idCol = findIdColumn(columns);
    const typeCol = columns.find(
      (c) => c.name.toLowerCase().includes('type') || c.name.toLowerCase().includes('pathtype'),
    );

    for (const row of rows) {
      const id = String(row[idCol?.name ?? ''] ?? `row-${nodeMap.size}`);
      if (nodeMap.has(id)) continue;

      const props: Record<string, unknown> = {};
      for (const col of columns) {
        props[col.name] = row[col.name];
      }

      const type = typeCol ? String(row[typeCol.name] ?? 'entity') : 'entity';
      nodeMap.set(id, { id, label: id, type, properties: props });
    }
  }

  return { nodes: Array.from(nodeMap.values()), links };
}

export function GraphResultView({ data }: GraphResultViewProps) {
  const graphRef = useRef<any>();
  const containerRef = useRef<HTMLDivElement>(null);
  const [typeColors, setTypeColors] = useState<Record<string, string>>({ ...DEFAULT_TYPE_COLORS });
  const [editingType, setEditingType] = useState<string | null>(null);

  const columns = data.data.columns ?? [];
  const rawRows = data.data.data ?? [];

  const { nodes, links } = useMemo(
    () => parseGraphData(columns, rawRows),
    [columns, rawRows],
  );

  const nodeTypes = useMemo(() => Array.from(new Set(nodes.map((n) => n.type))), [nodes]);

  const getColor = useCallback(
    (type: string) => typeColors[type] ?? DEFAULT_TYPE_COLORS.entity,
    [typeColors],
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      graphRef.current?.zoomToFit(300, 40);
    }, 500);
    return () => clearTimeout(timer);
  }, [nodes, links]);

  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const r = 6;
      const color = getColor(node.type ?? 'entity');
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.3)';
      ctx.lineWidth = 1;
      ctx.stroke();

      if (globalScale > 0.6) {
        const label = node.label ?? node.id ?? '';
        const fontSize = Math.max(10 / globalScale, 3);
        ctx.font = `${fontSize}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = 'rgba(240,240,240,0.9)';
        ctx.fillText(label, node.x, node.y + r + 2);
      }
    },
    [getColor],
  );

  if (nodes.length === 0 && rawRows.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-text-muted text-sm">
        No graph data returned
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Graph canvas */}
      {nodes.length > 0 && (
        <div ref={containerRef} className="relative flex-shrink-0" style={{ height: '320px' }}>
          <ForceGraph2D
            ref={graphRef}
            graphData={{ nodes, links }}
            nodeCanvasObject={paintNode}
            nodePointerAreaPaint={(node: any, color, ctx) => {
              ctx.beginPath();
              ctx.arc(node.x, node.y, 6, 0, 2 * Math.PI, false);
              ctx.fillStyle = color;
              ctx.fill();
            }}
            linkColor={() => 'rgba(120,120,120,0.4)'}
            linkWidth={1.5}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={0.9}
            linkLabel={(link: any) => link.label || ''}
            nodeLabel={(node: any) => {
              const props = node.properties ?? {};
              const entries = Object.entries(props).slice(0, 5).map(([k, v]) => `${k}: ${v}`).join('\n');
              return `${node.label}\n${entries}`;
            }}
            backgroundColor="transparent"
            width={containerRef.current?.clientWidth ?? 600}
            height={320}
            cooldownTicks={80}
          />
        </div>
      )}

      {/* Legend with color pickers */}
      <div className="px-4 py-2 border-t border-border-subtle flex flex-wrap items-center gap-3 shrink-0">
        <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted mr-1">Legend</span>
        {nodeTypes.map((type) => (
          <div key={type} className="relative flex items-center gap-1.5">
            <button
              onClick={() => setEditingType(editingType === type ? null : type)}
              className="w-3 h-3 rounded-full border border-white/20 cursor-pointer hover:scale-125 transition-transform"
              style={{ backgroundColor: getColor(type) }}
              title={`Click to change color for ${type}`}
            />
            <span className="text-[10px] text-text-muted">{type}</span>
            {/* Color picker dropdown */}
            {editingType === type && (
              <div className="absolute top-5 left-0 z-10 bg-neutral-bg2 border border-border rounded-lg p-2 shadow-lg"
                   onClick={(e) => e.stopPropagation()}>
                <div className="grid grid-cols-5 gap-1">
                  {COLOR_PRESETS.map((c) => (
                    <button
                      key={c}
                      className={`w-5 h-5 rounded-full border-2 transition-transform hover:scale-110 ${
                        getColor(type) === c ? 'border-white' : 'border-transparent'
                      }`}
                      style={{ backgroundColor: c }}
                      onClick={() => {
                        setTypeColors((prev) => ({ ...prev, [type]: c }));
                        setEditingType(null);
                      }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Tabular results section */}
      {rawRows.length > 0 && (
        <div className="border-t border-border-subtle overflow-auto flex-1 min-h-0">
          <div className="px-4 pt-3 pb-1">
            <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted">
              Query Results — {rawRows.length} row{rawRows.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div className="px-4 pb-3 overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="bg-neutral-bg2 border-b border-border">
                  {columns.map((col) => (
                    <th key={col.name}
                        className="px-3 py-2 text-[10px] font-medium uppercase tracking-wider text-text-muted whitespace-nowrap">
                      {col.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rawRows.map((row, i) => (
                  <tr key={i} className="border-b border-border-subtle last:border-0 hover:bg-brand/5 transition-colors">
                    {columns.map((col) => (
                      <td key={col.name} className="px-3 py-2 whitespace-nowrap text-text-secondary">
                        {String(row[col.name] ?? '—')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
