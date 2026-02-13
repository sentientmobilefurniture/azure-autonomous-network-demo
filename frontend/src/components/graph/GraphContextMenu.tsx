import { motion } from 'framer-motion';
import type { TopologyNode } from '../../hooks/useTopology';

const COLOR_PALETTE = [
  '#38BDF8', '#FB923C', '#A78BFA', '#3B82F6',
  '#C084FC', '#CA8A04', '#FB7185', '#F472B6',
  '#10B981', '#EF4444', '#6366F1', '#FBBF24',
];

interface GraphContextMenuProps {
  menu: { x: number; y: number; node: TopologyNode } | null;
  onClose: () => void;
  onSetDisplayField: (label: string, field: string) => void;
  onSetColor: (label: string, color: string) => void;
}

export function GraphContextMenu({ menu, onClose, onSetDisplayField, onSetColor }: GraphContextMenuProps) {
  if (!menu) return null;

  const propertyKeys = ['id', ...Object.keys(menu.node.properties)];

  return (
    <>
      {/* Backdrop to catch clicks */}
      <div className="fixed inset-0 z-40" onClick={onClose} onContextMenu={(e) => {e.preventDefault(); onClose();}} />

      <motion.div
        className="fixed z-50 bg-neutral-bg3 border border-white/15 rounded-lg shadow-xl
                   py-1 min-w-[180px]"
        style={{ left: menu.x, top: menu.y }}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.12 }}
      >
        {/* Header */}
        <div className="px-3 py-1.5 border-b border-white/10">
          <span className="text-xs font-semibold text-text-primary">{menu.node.id}</span>
          <span className="text-[10px] text-text-muted ml-2">{menu.node.label}</span>
        </div>

        {/* Display field selector */}
        <div className="px-3 py-1.5">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">Display Field</span>
          <div className="mt-1 space-y-0.5">
            {propertyKeys.map((key) => (
              <button
                key={key}
                className="block w-full text-left text-xs px-2 py-1 rounded
                           hover:bg-white/10 text-text-secondary hover:text-text-primary"
                onClick={() => { onSetDisplayField(menu.node.label, key); onClose(); }}
              >
                {key}
              </button>
            ))}
          </div>
        </div>

        {/* Color picker */}
        <div className="px-3 py-1.5 border-t border-white/10">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">
            Color ({menu.node.label})
          </span>
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {COLOR_PALETTE.map((color) => (
              <button
                key={color}
                className="h-4 w-4 rounded-full border border-white/20 hover:scale-125 transition-transform"
                style={{ backgroundColor: color }}
                onClick={() => { onSetColor(menu.node.label, color); onClose(); }}
              />
            ))}
          </div>
        </div>
      </motion.div>
    </>
  );
}
