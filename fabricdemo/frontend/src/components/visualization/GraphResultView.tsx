import { useMemo, useRef, useEffect, useCallback } from 'react';
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

/**
 * Parse tabular GQL results into nodes and edges for force-graph visualization.
 *
 * Heuristic: rows with source/target fields → edges; otherwise → nodes.
 * Falls back to showing tabular data as labeled nodes if no graph structure detected.
 */
function parseGraphData(
  columns: { name: string; type: string }[],
  rows: Record<string, unknown>[],
): { nodes: GraphNode[]; links: GraphLink[] } {
  const nodeMap = new Map<string, GraphNode>();
  const links: GraphLink[] = [];

  // Check if results have source/target columns (edge-shaped data)
  const colNames = columns.map((c) => c.name.toLowerCase());
  const hasSourceTarget =
    colNames.some((n) => n.includes('source')) &&
    colNames.some((n) => n.includes('target'));

  if (hasSourceTarget) {
    // Edge-shaped data
    const sourceCol = columns.find((c) =>
      c.name.toLowerCase().includes('source'),
    )!;
    const targetCol = columns.find((c) =>
      c.name.toLowerCase().includes('target'),
    )!;
    const labelCol = columns.find(
      (c) =>
        c.name.toLowerCase().includes('label') ||
        c.name.toLowerCase().includes('type') ||
        c.name.toLowerCase().includes('relationship'),
    );

    for (const row of rows) {
      const src = String(row[sourceCol.name] ?? '');
      const tgt = String(row[targetCol.name] ?? '');
      if (!src || !tgt) continue;

      if (!nodeMap.has(src)) {
        nodeMap.set(src, {
          id: src,
          label: src,
          type: 'entity',
          properties: {},
        });
      }
      if (!nodeMap.has(tgt)) {
        nodeMap.set(tgt, {
          id: tgt,
          label: tgt,
          type: 'entity',
          properties: {},
        });
      }
      links.push({
        source: src,
        target: tgt,
        label: labelCol ? String(row[labelCol.name] ?? '') : '',
      });
    }
  } else {
    // Node/tabular data — treat each row as a node
    // Use the first column as ID, second (if any) as label
    const idCol = columns[0];
    const labelCol = columns.length > 1 ? columns[1] : columns[0];

    for (const row of rows) {
      const id = String(row[idCol?.name ?? ''] ?? `row-${nodeMap.size}`);
      const label = String(row[labelCol?.name ?? ''] ?? id);
      if (nodeMap.has(id)) continue;

      const props: Record<string, unknown> = {};
      for (const col of columns) {
        if (col.name !== idCol?.name) {
          props[col.name] = row[col.name];
        }
      }

      // Try to determine entity type from column names
      const typeCol = columns.find(
        (c) =>
          c.name.toLowerCase().includes('type') ||
          c.name.toLowerCase().includes('label'),
      );
      const type = typeCol ? String(row[typeCol.name] ?? 'entity') : 'entity';

      nodeMap.set(id, { id, label, type, properties: props });
    }
  }

  return { nodes: Array.from(nodeMap.values()), links };
}

// Color palette for different entity types
const TYPE_COLORS: Record<string, string> = {
  CoreRouter: '#1A9C85',
  TransportLink: '#4EA8DF',
  MPLSPath: '#FF8C42',
  Service: '#E05C63',
  AggSwitch: '#9C6ADE',
  BaseStation: '#F7B731',
  SLAPolicy: '#A5D6A7',
  BGPSession: '#78909C',
  entity: '#B0B0B0',
};

function getNodeColor(type: string): string {
  return TYPE_COLORS[type] ?? TYPE_COLORS.entity;
}

export function GraphResultView({ data }: GraphResultViewProps) {
  const graphRef = useRef<any>();
  const containerRef = useRef<HTMLDivElement>(null);

  const { nodes, links } = useMemo(
    () => parseGraphData(data.data.columns, data.data.data),
    [data],
  );

  // Zoom to fit when data changes
  useEffect(() => {
    const timer = setTimeout(() => {
      graphRef.current?.zoomToFit(300, 40);
    }, 500);
    return () => clearTimeout(timer);
  }, [nodes, links]);

  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const r = 6;
      const color = getNodeColor(node.type ?? 'entity');

      // Circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.3)';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Label (only show if zoomed in enough)
      if (globalScale > 0.8) {
        const label = node.label ?? node.id ?? '';
        const fontSize = Math.max(10 / globalScale, 3);
        ctx.font = `${fontSize}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = 'rgba(240,240,240,0.9)';
        ctx.fillText(label, node.x, node.y + r + 2);
      }
    },
    [],
  );

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-text-muted text-sm">
        No graph data returned — results may be tabular
      </div>
    );
  }

  return (
    <div ref={containerRef} className="w-full h-full min-h-[300px] relative">
      <ForceGraph2D
        ref={graphRef}
        graphData={{ nodes, links }}
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node: any, color, ctx) => {
          const r = 6;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
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
          const entries = Object.entries(props)
            .slice(0, 5)
            .map(([k, v]) => `${k}: ${v}`)
            .join('\n');
          return `${node.label}\n${entries}`;
        }}
        backgroundColor="transparent"
        width={containerRef.current?.clientWidth ?? 600}
        height={containerRef.current?.clientHeight ?? 400}
        cooldownTicks={80}
      />
      {/* Legend */}
      <div className="absolute bottom-2 left-2 flex flex-wrap gap-2 text-[10px] text-text-muted">
        {Array.from(new Set(nodes.map((n) => n.type))).map((type) => (
          <span key={type} className="flex items-center gap-1">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: getNodeColor(type) }}
            />
            {type}
          </span>
        ))}
      </div>
    </div>
  );
}
