import { motion, AnimatePresence } from 'framer-motion';
import type { TopologyNode, TopologyEdge } from '../../hooks/useTopology';
import { NODE_COLORS } from './graphConstants';

interface GraphTooltipProps {
  tooltip: {
    x: number;
    y: number;
    node?: TopologyNode;
    edge?: TopologyEdge;
  } | null;
}

export function GraphTooltip({ tooltip }: GraphTooltipProps) {
  return (
    <AnimatePresence>
      {tooltip && (
        <motion.div
          className="fixed z-50 bg-neutral-bg3 border border-white/15 rounded-lg shadow-xl
                     px-3 py-2 pointer-events-none max-w-xs"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.1 }}
        >
          {tooltip.node && <NodeTooltipContent node={tooltip.node} />}
          {tooltip.edge && <EdgeTooltipContent edge={tooltip.edge} />}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function NodeTooltipContent({ node }: { node: TopologyNode }) {
  return (
    <>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: NODE_COLORS[node.label] }} />
        <span className="text-xs font-semibold text-text-primary">{node.id}</span>
      </div>
      <span className="text-[10px] uppercase tracking-wider text-text-muted block mb-1">
        {node.label}
      </span>
      <div className="space-y-0.5">
        {Object.entries(node.properties).map(([key, val]) => (
          <div key={key} className="text-[11px]">
            <span className="text-text-muted">{key}:</span>{' '}
            <span className="text-text-secondary">{String(val)}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function EdgeTooltipContent({ edge }: { edge: TopologyEdge }) {
  const srcId = typeof edge.source === 'string' ? edge.source : edge.source.id;
  const tgtId = typeof edge.target === 'string' ? edge.target : edge.target.id;
  return (
    <>
      <div className="text-xs font-semibold text-text-primary mb-1">{edge.label}</div>
      <div className="text-[11px] text-text-muted mb-1">
        {srcId} → {tgtId}
      </div>
      {Object.keys(edge.properties).length > 0 && (
        <div className="space-y-0.5">
          {Object.entries(edge.properties).map(([key, val]) => (
            <div key={key} className="text-[11px]">
              <span className="text-text-muted">{key}:</span>{' '}
              <span className="text-text-secondary">{String(val)}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
