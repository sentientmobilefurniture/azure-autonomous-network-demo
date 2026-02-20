import { useState, useRef, useEffect, useCallback } from 'react';
import { COLOR_PALETTE } from './graphConstants';

interface ColorWheelPopoverProps {
  /** Current color hex for this label */
  currentColor: string;
  /** Anchor element rect for positioning */
  anchorRect: DOMRect;
  /** Called with final hex color on commit */
  onSelect: (color: string) => void;
  /** Close without committing */
  onClose: () => void;
}

// ── Helpers ──

function hslToHex(h: number, s: number, l: number): string {
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * Math.max(0, Math.min(1, color)))
      .toString(16)
      .padStart(2, '0');
  };
  return `#${f(0)}${f(8)}${f(4)}`.toUpperCase();
}

function hexToHsl(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
  else if (max === g) h = ((b - r) / d + 2) * 60;
  else h = ((r - g) / d + 4) * 60;
  return [h, s, l];
}

function isValidHex(v: string): boolean {
  return /^#[0-9A-Fa-f]{6}$/.test(v);
}

const WHEEL_SIZE = 160;
const RING_WIDTH = 20;
const SL_SIZE = WHEEL_SIZE - RING_WIDTH * 2 - 12; // inner SL square

export function ColorWheelPopover({ currentColor, anchorRect, onSelect, onClose }: ColorWheelPopoverProps) {
  const [hsl, setHsl] = useState<[number, number, number]>(() => hexToHsl(currentColor));
  const [hexInput, setHexInput] = useState(currentColor.toUpperCase());
  const hueCanvasRef = useRef<HTMLCanvasElement>(null);
  const slCanvasRef = useRef<HTMLCanvasElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const [h, s, l] = hsl;

  // Keep hex input in sync when HSL changes via wheel interaction
  useEffect(() => {
    setHexInput(hslToHex(h, s, l));
  }, [h, s, l]);

  // ── Draw hue ring ──
  useEffect(() => {
    const canvas = hueCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const cx = WHEEL_SIZE / 2, cy = WHEEL_SIZE / 2;
    const outerR = WHEEL_SIZE / 2 - 1;
    const innerR = outerR - RING_WIDTH;

    ctx.clearRect(0, 0, WHEEL_SIZE, WHEEL_SIZE);

    // Draw hue ring using conic gradient approximation
    for (let angle = 0; angle < 360; angle++) {
      const startRad = (angle - 0.5) * Math.PI / 180;
      const endRad = (angle + 0.5) * Math.PI / 180;
      ctx.beginPath();
      ctx.arc(cx, cy, outerR, startRad, endRad);
      ctx.arc(cx, cy, innerR, endRad, startRad, true);
      ctx.closePath();
      ctx.fillStyle = `hsl(${angle}, 100%, 50%)`;
      ctx.fill();
    }

    // Draw selection indicator on hue ring
    const selRad = (h - 90) * Math.PI / 180;
    const midR = (outerR + innerR) / 2;
    const sx = cx + Math.cos(selRad) * midR;
    const sy = cy + Math.sin(selRad) * midR;
    ctx.beginPath();
    ctx.arc(sx, sy, RING_WIDTH / 2 - 1, 0, Math.PI * 2);
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.stroke();
  }, [h]);

  // ── Draw SL square ──
  useEffect(() => {
    const canvas = slCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const size = SL_SIZE;

    ctx.clearRect(0, 0, size, size);

    for (let x = 0; x < size; x++) {
      for (let y = 0; y < size; y++) {
        const sat = x / size;
        const light = 1 - y / size;
        ctx.fillStyle = `hsl(${h}, ${sat * 100}%, ${light * 100}%)`;
        ctx.fillRect(x, y, 1, 1);
      }
    }

    // Selection crosshair
    const sx = s * size;
    const sy = (1 - l) * size;
    ctx.beginPath();
    ctx.arc(sx, sy, 5, 0, Math.PI * 2);
    ctx.strokeStyle = l > 0.5 ? '#000' : '#fff';
    ctx.lineWidth = 2;
    ctx.stroke();
  }, [h, s, l]);

  // ── Hue ring interaction ──
  const draggingHue = useRef(false);

  const updateHueFromEvent = useCallback((e: { clientX: number; clientY: number }) => {
    const canvas = hueCanvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const x = e.clientX - rect.left - cx;
    const y = e.clientY - rect.top - cy;
    let angle = Math.atan2(y, x) * 180 / Math.PI + 90;
    if (angle < 0) angle += 360;
    setHsl(([, s, l]) => [angle, s, l]);
  }, []);

  const onHueDown = useCallback((e: React.MouseEvent) => {
    const canvas = hueCanvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const x = e.clientX - rect.left - cx;
    const y = e.clientY - rect.top - cy;
    const dist = Math.sqrt(x * x + y * y);
    const outerR = WHEEL_SIZE / 2 - 1;
    const innerR = outerR - RING_WIDTH;
    if (dist >= innerR && dist <= outerR) {
      draggingHue.current = true;
      updateHueFromEvent(e);
    }
  }, [updateHueFromEvent]);

  // ── SL square interaction ──
  const draggingSL = useRef(false);

  const updateSLFromEvent = useCallback((e: { clientX: number; clientY: number }) => {
    const canvas = slCanvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    setHsl(([h]) => [h, x, 1 - y]);
  }, []);

  const onSLDown = useCallback((e: React.MouseEvent) => {
    draggingSL.current = true;
    updateSLFromEvent(e);
  }, [updateSLFromEvent]);

  // Global mouse handlers for drag
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (draggingHue.current) updateHueFromEvent(e);
      if (draggingSL.current) updateSLFromEvent(e);
    };
    const onUp = () => {
      draggingHue.current = false;
      draggingSL.current = false;
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [updateHueFromEvent, updateSLFromEvent]);

  // Close on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Delay to avoid the click that opened the popover from closing it
    const id = setTimeout(() => document.addEventListener('mousedown', handler), 0);
    return () => { clearTimeout(id); document.removeEventListener('mousedown', handler); };
  }, [onClose]);

  // Handle hex input
  const commitHex = useCallback(() => {
    const v = hexInput.startsWith('#') ? hexInput : `#${hexInput}`;
    if (isValidHex(v)) {
      setHsl(hexToHsl(v));
    }
  }, [hexInput]);

  const previewHex = hslToHex(h, s, l);

  // Position: below anchor, clamped to viewport
  const top = anchorRect.bottom + 6;
  const left = Math.max(8, anchorRect.left - WHEEL_SIZE / 2 + anchorRect.width / 2);

  return (
    <div
      ref={popoverRef}
      className="fixed z-50 bg-neutral-bg3 border border-border-strong rounded-lg shadow-xl p-3"
      style={{ top, left, width: WHEEL_SIZE + 24 }}
    >
      {/* Color wheel: hue ring + SL square inside */}
      <div className="relative" style={{ width: WHEEL_SIZE, height: WHEEL_SIZE, margin: '0 auto' }}>
        <canvas
          ref={hueCanvasRef}
          width={WHEEL_SIZE}
          height={WHEEL_SIZE}
          className="absolute inset-0 cursor-crosshair"
          onMouseDown={onHueDown}
        />
        <canvas
          ref={slCanvasRef}
          width={SL_SIZE}
          height={SL_SIZE}
          className="absolute cursor-crosshair rounded-sm"
          style={{
            top: (WHEEL_SIZE - SL_SIZE) / 2,
            left: (WHEEL_SIZE - SL_SIZE) / 2,
          }}
          onMouseDown={onSLDown}
        />
      </div>

      {/* Hex input + preview swatch */}
      <div className="flex items-center gap-2 mt-3">
        <div
          className="h-6 w-6 rounded border border-border-strong shrink-0"
          style={{ backgroundColor: previewHex }}
        />
        <input
          type="text"
          value={hexInput}
          onChange={(e) => setHexInput(e.target.value.toUpperCase())}
          onBlur={commitHex}
          onKeyDown={(e) => { if (e.key === 'Enter') commitHex(); }}
          className="flex-1 bg-neutral-bg3 border border-border rounded px-2 py-1
                     text-xs text-text-primary font-mono
                     focus:outline-none focus:border-brand"
          maxLength={7}
          placeholder="#FFFFFF"
        />
        <button
          onClick={() => { onSelect(previewHex); onClose(); }}
          className="px-2 py-1 text-[10px] font-medium rounded
                     bg-brand hover:bg-brand-hover text-white transition-colors"
        >
          Apply
        </button>
      </div>

      {/* Preset swatches */}
      <div className="flex flex-wrap gap-1.5 mt-2.5">
        {COLOR_PALETTE.map((color) => (
          <button
            key={color}
            className="h-4 w-4 rounded-full border border-border-strong hover:scale-125
                       transition-transform relative"
            style={{ backgroundColor: color }}
            onClick={() => { onSelect(color); onClose(); }}
            title={color}
          >
            {color.toUpperCase() === currentColor.toUpperCase() && (
              <span className="absolute inset-0 flex items-center justify-center text-white text-[8px] font-bold drop-shadow-sm">
                ✓
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
