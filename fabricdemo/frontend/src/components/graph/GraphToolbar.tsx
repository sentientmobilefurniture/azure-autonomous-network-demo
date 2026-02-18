import { useState, useRef } from 'react';
import { useNodeColor } from '../../hooks/useNodeColor';
import type { TopologyMeta } from '../../hooks/useTopology';
import { ColorWheelPopover } from './ColorWheelPopover';

interface GraphToolbarProps {
  meta: TopologyMeta | null;
  loading: boolean;
  availableLabels: string[];
  activeLabels: string[];
  onToggleLabel: (label: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onRefresh: () => void;
  onZoomToFit: () => void;
  isPaused?: boolean;
  onTogglePause?: () => void;
  nodeColorOverride: Record<string, string>;
  onSetColor?: (label: string, color: string) => void;
}

export function GraphToolbar({
  meta, loading, availableLabels, activeLabels,
  onToggleLabel, searchQuery, onSearchChange, onRefresh, onZoomToFit,
  isPaused, onTogglePause, nodeColorOverride, onSetColor,
}: GraphToolbarProps) {
  const getColor = useNodeColor(nodeColorOverride);
  const [colorPickerLabel, setColorPickerLabel] = useState<string | null>(null);
  const [colorPickerAnchor, setColorPickerAnchor] = useState<DOMRect | null>(null);
  const dotRefs = useRef<Record<string, HTMLSpanElement | null>>({});

  const openColorPicker = (label: string) => {
    const el = dotRefs.current[label];
    if (!el) return;
    setColorPickerAnchor(el.getBoundingClientRect());
    setColorPickerLabel(label);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border shrink-0">
      {/* Title */}
      <span className="text-xs font-semibold text-text-primary whitespace-nowrap">◆ Network Topology</span>

      {/* Label filter chips */}
      <div className="flex items-center gap-1 ml-2 overflow-x-auto">
        {availableLabels.map((label) => {
          const active = activeLabels.length === 0 || activeLabels.includes(label);
          return (
            <span
              key={label}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]
                         border transition-colors
                         ${active
                           ? 'border-border-strong text-text-secondary'
                           : 'border-transparent text-text-muted opacity-40'}`}
            >
              {/* Color dot — click opens color wheel */}
              <span
                ref={(el) => { dotRefs.current[label] = el; }}
                className="h-2.5 w-2.5 rounded-full shrink-0 cursor-pointer
                           hover:scale-150 transition-transform ring-1 ring-transparent
                           hover:ring-brand/40"
                style={{ backgroundColor: getColor(label) }}
                onClick={(e) => { e.stopPropagation(); openColorPicker(label); }}
                title={`Change color for ${label}`}
              />
              {/* Label text — click toggles filter */}
              <button
                className="hover:text-text-primary transition-colors"
                onClick={() => onToggleLabel(label)}
              >
                {label}
              </button>
            </span>
          );
        })}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Search */}
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search nodes..."
        className="bg-neutral-bg3 border border-border rounded px-2 py-0.5
                   text-[11px] text-text-secondary placeholder:text-text-muted
                   w-32 focus:w-44 transition-all focus:outline-none focus:border-brand"
      />

      {/* Counts */}
      {meta && (
        <span className="text-[10px] text-text-muted whitespace-nowrap">
          {meta.node_count}N · {meta.edge_count}E
        </span>
      )}

      {/* Pause/Play toggle */}
      {onTogglePause && (
        <button
          onClick={onTogglePause}
          className={`text-xs px-1 transition-colors ${
            isPaused ? 'text-brand hover:text-brand/80' : 'text-text-muted hover:text-text-primary'
          }`}
          title={isPaused ? 'Resume simulation' : 'Pause simulation'}
        >{isPaused ? '▶' : '⏸'}</button>
      )}

      {/* Zoom-to-fit */}
      <button
        onClick={onZoomToFit}
        className="text-text-muted hover:text-text-primary text-xs px-1"
        title="Fit to view"
      >⤢</button>

      {/* Refresh */}
      <button
        onClick={onRefresh}
        className={`text-text-muted hover:text-text-primary text-xs px-1
                   ${loading ? 'animate-spin' : ''}`}
        title="Refresh"
      >⟳</button>

      {/* Color wheel popover */}
      {colorPickerLabel && colorPickerAnchor && onSetColor && (
        <ColorWheelPopover
          currentColor={getColor(colorPickerLabel)}
          anchorRect={colorPickerAnchor}
          onSelect={(color) => onSetColor(colorPickerLabel, color)}
          onClose={() => { setColorPickerLabel(null); setColorPickerAnchor(null); }}
        />
      )}
    </div>
  );
}
