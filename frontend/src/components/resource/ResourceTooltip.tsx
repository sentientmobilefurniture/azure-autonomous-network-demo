import { motion, AnimatePresence } from 'framer-motion';
import type { ResourceNode, ResourceEdge } from '../../types';
import { RESOURCE_NODE_COLORS, RESOURCE_TYPE_LABELS } from './resourceConstants';

interface ResourceTooltipProps {
  tooltip: {
    x: number;
    y: number;
    node?: ResourceNode;
    edge?: ResourceEdge;
  } | null;
}

export function ResourceTooltip({ tooltip }: ResourceTooltipProps) {
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
          {tooltip.node && <NodeContent node={tooltip.node} />}
          {tooltip.edge && <EdgeContent edge={tooltip.edge} />}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function NodeContent({ node }: { node: ResourceNode }) {
  const color = RESOURCE_NODE_COLORS[node.type];
  return (
    <>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
        <span className="text-xs font-semibold text-text-primary">{node.label}</span>
      </div>
      <span className="text-[10px] uppercase tracking-wider text-text-muted block mb-1">
        {RESOURCE_TYPE_LABELS[node.type]}
      </span>
      {node.meta && Object.keys(node.meta).length > 0 && (
        <div className="space-y-0.5 mt-1">
          {Object.entries(node.meta).map(([key, val]) => (
            <div key={key} className="text-[11px]">
              <span className="text-text-muted">{key}:</span>{' '}
              <span className="text-text-secondary">{val}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function EdgeContent({ edge }: { edge: ResourceEdge }) {
  return (
    <>
      <div className="text-xs font-semibold text-text-primary mb-1">{edge.label}</div>
      <div className="text-[11px] text-text-muted">
        {edge.source as string} → {edge.target as string}
      </div>
      <div className="text-[10px] text-text-muted mt-0.5 uppercase tracking-wider">
        {edge.type.replace('_', ' ')}
      </div>
    </>
  );
}
