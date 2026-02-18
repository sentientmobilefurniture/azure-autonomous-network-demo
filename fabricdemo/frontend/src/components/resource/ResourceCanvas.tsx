import {
  useRef, useCallback, useEffect,
  forwardRef, useImperativeHandle, useState,
} from 'react';
import ForceGraph2D, {
  ForceGraphMethods, NodeObject, LinkObject,
} from 'react-force-graph-2d';
import type { ResourceNode, ResourceEdge } from '../../types';
import {
  RESOURCE_NODE_COLORS,
  RESOURCE_NODE_SIZES,
  RESOURCE_EDGE_COLORS,
  RESOURCE_EDGE_DASH,
} from './resourceConstants';

// ── Force-graph generic wrappers ────────────────────────────────────────────

type GNode = NodeObject<ResourceNode>;
type GLink = LinkObject<ResourceNode, ResourceEdge>;

export interface ResourceCanvasHandle {
  zoomToFit: () => void;
  setFrozen: (frozen: boolean) => void;
}

interface ResourceCanvasProps {
  nodes: ResourceNode[];
  edges: ResourceEdge[];
  width: number;
  height: number;
  onNodeHover: (node: ResourceNode | null) => void;
  onLinkHover: (edge: ResourceEdge | null) => void;
  onBackgroundClick: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  /** Optional: highlight all nodes/edges on this path */
  highlightIds?: Set<string>;
}

// ── Shape helpers ───────────────────────────────────────────────────────────

function drawCircle(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, fill: string, doubleBorder = false) {
  const styles = getComputedStyle(document.documentElement);
  const borderDefault = styles.getPropertyValue('--color-border-default').trim();
  const borderStrong = styles.getPropertyValue('--color-border-strong').trim();
  const textSecondary = styles.getPropertyValue('--color-text-secondary').trim();

  ctx.beginPath();
  ctx.arc(x, y, r, 0, 2 * Math.PI);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = doubleBorder ? textSecondary : borderDefault;
  ctx.lineWidth = doubleBorder ? 1.5 : 0.5;
  ctx.stroke();
  if (doubleBorder) {
    ctx.beginPath();
    ctx.arc(x, y, r + 2.5, 0, 2 * Math.PI);
    ctx.strokeStyle = borderStrong;
    ctx.lineWidth = 0.7;
    ctx.stroke();
  }
}

function drawDiamond(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, fill: string) {
  const borderDefault = getComputedStyle(document.documentElement).getPropertyValue('--color-border-default').trim();
  ctx.beginPath();
  ctx.moveTo(x, y - r);
  ctx.lineTo(x + r, y);
  ctx.lineTo(x, y + r);
  ctx.lineTo(x - r, y);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = borderDefault;
  ctx.lineWidth = 0.5;
  ctx.stroke();
}

function drawRoundRect(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, fill: string) {
  const borderDefault = getComputedStyle(document.documentElement).getPropertyValue('--color-border-default').trim();
  const w = r * 2.2;
  const h = r * 1.4;
  const radius = 3;
  ctx.beginPath();
  ctx.moveTo(x - w / 2 + radius, y - h / 2);
  ctx.lineTo(x + w / 2 - radius, y - h / 2);
  ctx.quadraticCurveTo(x + w / 2, y - h / 2, x + w / 2, y - h / 2 + radius);
  ctx.lineTo(x + w / 2, y + h / 2 - radius);
  ctx.quadraticCurveTo(x + w / 2, y + h / 2, x + w / 2 - radius, y + h / 2);
  ctx.lineTo(x - w / 2 + radius, y + h / 2);
  ctx.quadraticCurveTo(x - w / 2, y + h / 2, x - w / 2, y + h / 2 - radius);
  ctx.lineTo(x - w / 2, y - h / 2 + radius);
  ctx.quadraticCurveTo(x - w / 2, y - h / 2, x - w / 2 + radius, y - h / 2);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = borderDefault;
  ctx.lineWidth = 0.5;
  ctx.stroke();
}

function drawHexagon(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, fill: string) {
  const borderStrong = getComputedStyle(document.documentElement).getPropertyValue('--color-border-strong').trim();
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 6;
    const px = x + r * Math.cos(angle);
    const py = y + r * Math.sin(angle);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = borderStrong;
  ctx.lineWidth = 0.7;
  ctx.stroke();
}

// ── Component ───────────────────────────────────────────────────────────────

export const ResourceCanvas = forwardRef<ResourceCanvasHandle, ResourceCanvasProps>(
  function ResourceCanvas(
    { nodes, edges, width, height,
      onNodeHover, onLinkHover, onBackgroundClick,
      onMouseEnter, onMouseLeave, highlightIds },
    ref,
  ) {
    const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
    const [frozen, setFrozen] = useState(false);

    useImperativeHandle(ref, () => ({
      zoomToFit: () => fgRef.current?.zoomToFit(400, 60),
      setFrozen: (f: boolean) => {
        setFrozen(f);
        if (!f) fgRef.current?.d3ReheatSimulation();
      },
    }), []);

    // Fit on data change
    useEffect(() => {
      if (fgRef.current && nodes.length > 0) {
        setTimeout(() => fgRef.current?.zoomToFit(400, 60), 600);
      }
    }, [nodes.length]);

    // Apply layered y-force so nodes stratify by type
    useEffect(() => {
      const fg = fgRef.current;
      if (!fg) return;
      const layerY: Record<string, number> = {
        orchestrator: -180,
        agent: -90,
        tool: 0,
        datasource: 90,
        'search-index': 90,
        // Infrastructure layer
        'blob-container': 150,
        foundry: 210,
        storage: 210,
        'search-service': 210,
        'container-app': 210,
      };
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (fg as any).d3Force('y')?.strength(0.15);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      fg.d3Force('charge')?.strength(-300);
      // Set initial positions based on layer so layout converges faster
      nodes.forEach((n) => {
        const gn = n as GNode;
        if (gn.y == null) gn.y = layerY[n.type] ?? 0;
      });
    }, [nodes]);

    // ── Custom rendering ────────────────────────────────────────────────

    const nodeCanvasObject = useCallback(
      (node: GNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const size = RESOURCE_NODE_SIZES[node.type] ?? 8;
        const color = RESOURCE_NODE_COLORS[node.type] ?? getComputedStyle(document.documentElement).getPropertyValue('--color-text-muted').trim();
        const dimmed = highlightIds && highlightIds.size > 0 && !highlightIds.has(node.id);
        const alpha = dimmed ? 0.2 : 1;

        ctx.globalAlpha = alpha;

        switch (node.type) {
          case 'orchestrator':
            drawCircle(ctx, node.x!, node.y!, size, color, true);
            break;
          case 'agent':
            drawCircle(ctx, node.x!, node.y!, size, color);
            break;
          case 'tool':
            drawDiamond(ctx, node.x!, node.y!, size, color);
            break;
          case 'datasource':
          case 'search-index':
            drawRoundRect(ctx, node.x!, node.y!, size, color);
            break;
          // Infrastructure — hexagons for services, round-rects for sub-resources
          case 'foundry':
          case 'storage':
          case 'search-service':
          case 'container-app':
            drawHexagon(ctx, node.x!, node.y!, size, color);
            break;
          case 'blob-container':
            drawRoundRect(ctx, node.x!, node.y!, size, color);
            break;
          default:
            drawCircle(ctx, node.x!, node.y!, size, color);
        }

        // Label
        const styles = getComputedStyle(document.documentElement);
        const textPrimary = styles.getPropertyValue('--color-text-primary').trim();
        const textSecondary = styles.getPropertyValue('--color-text-secondary').trim();

        const fontSize = Math.max(10 / globalScale, 3);
        ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
        ctx.fillStyle = dimmed ? textSecondary : textPrimary;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(node.label, node.x!, node.y! + size + 3);

        ctx.globalAlpha = 1;
      },
      [highlightIds],
    );

    // Edge rendering with dash patterns
    const linkCanvasObjectMode = () => 'after' as const;
    const linkCanvasObject = useCallback(
      (link: GLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const src = link.source as GNode;
        const tgt = link.target as GNode;
        if (!src.x || !tgt.x) return;

        const midX = (src.x + tgt.x) / 2;
        const midY = (src.y! + tgt.y!) / 2;
        const fontSize = Math.max(8 / globalScale, 2.5);

        const textMuted = getComputedStyle(document.documentElement).getPropertyValue('--color-text-muted').trim();

        ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
        ctx.fillStyle = textMuted;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(link.label, midX, midY);
      },
      [],
    );

    // Link colour + dash
    const linkColor = useCallback(
      (link: GLink) => {
        const edgeColor = RESOURCE_EDGE_COLORS[link.type];
        if (edgeColor) return edgeColor;
        return getComputedStyle(document.documentElement).getPropertyValue('--color-border-default').trim();
      },
      [],
    );
    const linkDash = useCallback(
      (link: GLink) => {
        const d = RESOURCE_EDGE_DASH[link.type];
        return d && d.length > 0 ? d : null;
      },
      [],
    );

    // Hover wrappers
    const handleNodeHover = useCallback(
      (node: GNode | null) => onNodeHover(node as ResourceNode | null),
      [onNodeHover],
    );
    const handleLinkHover = useCallback(
      (link: GLink | null) => onLinkHover(link as ResourceEdge | null),
      [onLinkHover],
    );

    return (
      <div
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        style={{ width, height }}
      >
        <ForceGraph2D
          ref={fgRef}
          width={width}
          height={height}
          graphData={{ nodes: nodes as GNode[], links: edges as GLink[] }}
          backgroundColor="transparent"
          // Node rendering
          nodeCanvasObject={nodeCanvasObject}
          nodeCanvasObjectMode={() => 'replace'}
          nodeId="id"
          // Edge rendering
          linkSource="source"
          linkTarget="target"
          linkColor={linkColor}
          linkWidth={1.5}
          linkDirectionalArrowLength={5}
          linkDirectionalArrowRelPos={0.85}
          linkDirectionalArrowColor={linkColor}
          linkLineDash={linkDash}
          linkCanvasObjectMode={linkCanvasObjectMode}
          linkCanvasObject={linkCanvasObject}
          // Interaction
          onNodeHover={handleNodeHover}
          onLinkHover={handleLinkHover}
          onBackgroundClick={onBackgroundClick}
          // Physics
          d3AlphaDecay={0.03}
          d3VelocityDecay={0.35}
          cooldownTicks={frozen ? 0 : Infinity}
          cooldownTime={2000}
          enableNodeDrag={true}
          enableZoomInteraction={true}
          enablePanInteraction={true}
        />
      </div>
    );
  },
);
