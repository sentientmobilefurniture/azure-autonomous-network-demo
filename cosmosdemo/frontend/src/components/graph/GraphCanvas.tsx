import { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from 'react';
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d';
import type { TopologyNode, TopologyEdge } from '../../hooks/useTopology';
import { useNodeColor } from '../../hooks/useNodeColor';
import { useScenarioContext } from '../../context/ScenarioContext';

type GNode = NodeObject<TopologyNode>;
type GLink = LinkObject<TopologyNode, TopologyEdge>;

export interface GraphCanvasHandle {
  zoomToFit: () => void;
  setFrozen: (frozen: boolean) => void;
}

interface GraphCanvasProps {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  width: number;
  height: number;
  nodeDisplayField: Record<string, string>;
  nodeColorOverride: Record<string, string>;
  onNodeHover: (node: TopologyNode | null) => void;
  onLinkHover: (edge: TopologyEdge | null) => void;
  onNodeRightClick: (node: TopologyNode, event: MouseEvent) => void;
  onBackgroundClick: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  function GraphCanvas(
    { nodes, edges, width, height,
      nodeDisplayField, nodeColorOverride,
      onNodeHover, onLinkHover, onNodeRightClick, onBackgroundClick,
      onMouseEnter, onMouseLeave },
    ref,
  ) {
    const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
    const [frozen, setFrozen] = useState(false);

    // Expose zoomToFit and setFrozen to parent via imperative handle
    useImperativeHandle(ref, () => ({
      zoomToFit: () => fgRef.current?.zoomToFit(400, 40),
      setFrozen: (f: boolean) => {
        setFrozen(f);
        if (!f) fgRef.current?.d3ReheatSimulation();
      },
    }), []);

    // Fit graph to view on data change
    useEffect(() => {
      if (fgRef.current && nodes.length > 0) {
        setTimeout(() => fgRef.current?.zoomToFit(400, 40), 500);
      }
    }, [nodes.length]);

    // Color resolver (centralized: override → scenario → constants → auto)
    const getNodeColor = useNodeColor(nodeColorOverride);

    // Size resolver (scenario sizes normalized to canvas scale)
    const { scenarioNodeSizes } = useScenarioContext();
    const getNodeSize = useCallback(
      (label: string) => {
        const scenarioSize = scenarioNodeSizes[label];
        if (scenarioSize != null) return Math.round(scenarioSize / 3); // normalize from 12-30 to 4-10
        return 6; // default size
      },
      [scenarioNodeSizes],
    );

    // Custom node rendering (colored circle + label)
    const nodeCanvasObject = useCallback(
      (node: GNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const size = getNodeSize(node.label);
        const color = getNodeColor(node.label);

        // Circle
        ctx.beginPath();
        ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 0.5;
        ctx.stroke();

        // Label (show custom field or id)
        const displayField = nodeDisplayField[node.label] ?? 'id';
        const label = displayField === 'id'
          ? node.id
          : String(node.properties[displayField] ?? node.id);

        const fontSize = Math.max(10 / globalScale, 3);
        ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
        ctx.fillStyle = '#E4E4E7';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(label, node.x!, node.y! + size + 2);
      },
      [getNodeColor, getNodeSize, nodeDisplayField],
    );

    // Edge label rendering
    const linkCanvasObjectMode = () => 'after' as const;
    const linkCanvasObject = useCallback(
      (link: GLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const src = link.source as GNode;
        const tgt = link.target as GNode;
        if (!src.x || !tgt.x) return;

        const midX = (src.x + tgt.x) / 2;
        const midY = (src.y! + tgt.y!) / 2;
        const fontSize = Math.max(8 / globalScale, 2.5);

        ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
        ctx.fillStyle = '#71717A';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(link.label, midX, midY);
      },
      [],
    );

    // Double-click handler: center + zoom to specific node
    const handleNodeDoubleClick = useCallback((node: GNode) => {
      fgRef.current?.centerAt(node.x, node.y, 600);
      fgRef.current?.zoom(4, 600);
    }, []);

    // Hover wrappers — library passes (obj, prevObj), we forward only the obj
    const handleNodeHoverInternal = useCallback(
      (node: GNode | null) => onNodeHover(node as TopologyNode | null),
      [onNodeHover],
    );
    const handleLinkHoverInternal = useCallback(
      (link: GLink | null) => onLinkHover(link as TopologyEdge | null),
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
          linkColor={() => 'rgba(255,255,255,0.12)'}
          linkWidth={1.5}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={0.9}
          linkDirectionalArrowColor={() => 'rgba(255,255,255,0.2)'}
          linkCanvasObjectMode={linkCanvasObjectMode}
          linkCanvasObject={linkCanvasObject}
          // Interaction
          onNodeHover={handleNodeHoverInternal}
          onLinkHover={handleLinkHoverInternal}
          onNodeRightClick={onNodeRightClick as (node: GNode, event: MouseEvent) => void}
          onNodeClick={handleNodeDoubleClick}
          onBackgroundClick={onBackgroundClick}
          // Physics
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
          cooldownTicks={frozen ? 0 : Infinity}
          cooldownTime={3000}
          enableNodeDrag={true}
          enableZoomInteraction={true}
          enablePanInteraction={true}
        />
      </div>
    );
  },
);
