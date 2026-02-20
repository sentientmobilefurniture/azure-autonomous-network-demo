# Project Curtains — Fabric Light-Theme Migration

> Migrate the AI Incident Investigator frontend from a dark glassmorphism theme to Microsoft Fabric's light-mode design language.

---

## 1. Scope

| Metric | Count |
|--------|-------|
| Total files scanned | 53 |
| Files needing changes | 37 |
| HIGH severity (structural) | 12 |
| MEDIUM severity (class swap) | 22 |
| No changes needed | 19 |

---

## 2. Target Design Tokens (Fabric / Fluent UI v9)

### 2.1 Brand

| Token | Current (dark) | Target (Fabric) |
|-------|---------------|-----------------|
| `brand.DEFAULT` | `#8251EE` | `#117865` |
| `brand.hover` | `#9366F5` | `#0E6658` |
| `brand.light` | `#A37EF5` | `#1A9C85` |
| `brand.subtle` | `rgba(130,81,238,0.15)` | `rgba(17,120,101,0.08)` |

### 2.2 Backgrounds

| Token | Current | Target |
|-------|---------|--------|
| `neutral.bg1` | `hsl(240,6%,10%)` | `#FFFFFF` |
| `neutral.bg2` | `hsl(240,5%,12%)` | `#FAF9F8` |
| `neutral.bg3` | `hsl(240,5%,14%)` | `#F3F2F1` |
| `neutral.bg4` | `hsl(240,4%,18%)` | `#EDEBE9` |
| `neutral.bg5` | `hsl(240,4%,22%)` | `#E1DFDD` |
| `neutral.bg6` | `hsl(240,4%,26%)` | `#D2D0CE` |

### 2.3 Text

| Token | Current | Target |
|-------|---------|--------|
| `text.primary` | `#FFFFFF` | `#242424` |
| `text.secondary` | `#A1A1AA` | `#616161` |
| `text.muted` | `#71717A` | `#A19F9D` |
| `text.tertiary` | `#52525B` | `#C8C6C4` |

### 2.4 Borders

| Token | Current | Target |
|-------|---------|--------|
| `border.subtle` | `hsla(0,0%,100%,0.08)` | `#F0F0F0` |
| `border.DEFAULT` | `hsla(0,0%,100%,0.12)` | `#E0E0E0` |
| `border.strong` | `hsla(0,0%,100%,0.20)` | `#D1D1D1` |

### 2.5 Status

| Token | Current | Target |
|-------|---------|--------|
| `status.success` | `#10B981` | `#107C10` |
| `status.warning` | `#F59E0B` | `#F7630C` |
| `status.error` | `#EF4444` | `#A4262C` |
| `status.info` | `#3B82F6` | `#0078D4` |

### 2.6 Font

No change needed — already `Segoe UI`. Consider adding `Segoe UI Variable` as first choice:

```
fontFamily: { sans: ['"Segoe UI Variable"', '"Segoe UI"', 'system-ui', 'sans-serif'] }
```

---

## 3. Migration Phases

### Phase 0: Token Swap (globals.css + tailwind.config.js)

**Files:** `tailwind.config.js`, `src/styles/globals.css`
**Effort:** 15 min

Update all CSS custom properties and Tailwind color tokens from the dark palette to the Fabric palette (Section 2 above). Also:

- Change `color-scheme: dark` → `color-scheme: light`
- Change `body` from `bg-neutral-bg1 text-text-primary` (unchanged class, but now resolves to white bg / dark text)
- Update scrollbar track/thumb colors
- Update focus ring offset to new bg color
- **`index.html`**: Change `<meta name="theme-color" content="#18181B" />` → `content="#FFFFFF"`

After this phase, **all components using semantic tokens** (`text-text-primary`, `bg-neutral-bg2`, `text-brand`, `border-border-subtle`) automatically pick up the new values with zero class changes. This covers the majority of MEDIUM-severity files.

---

### Phase 1: Glass Utilities → Fabric Cards

**Files:** `src/styles/globals.css` (4 utility definitions)
**Effort:** 15 min  
**Cascading impact:** 7+ component files

Replace dark glassmorphism utilities with Fabric-style solid surfaces:

| Utility | Current | Target |
|---------|---------|--------|
| `.glass-card` | `backdrop-blur-md bg-white/5 border-white/10 rounded-xl` | `bg-white border border-[#E0E0E0] rounded-xl shadow-sm` |
| `.glass-panel` | `backdrop-blur-lg bg-black/40 border-white/5` | `bg-[#FAF9F8] border border-[#E0E0E0]` |
| `.glass-overlay` | `backdrop-blur-sm bg-black/60` | `bg-black/40 backdrop-blur-sm` |
| `.glass-input` | `bg-white/5 border-white/10 focus:border-brand` | `bg-white border border-[#E0E0E0] focus:border-brand` |

Components affected:
- `AlertInput.tsx`
- `DiagnosisPanel.tsx`
- `ErrorBanner.tsx`
- `GraphTopologyViewer.tsx`
- `LogStream.tsx`
- `ResourceVisualizer.tsx`
- `StepCard.tsx`

---

### Phase 2: Translucent White/Black → Solid Tokens

**Effort:** 30 min  
**22 files affected**

Search-and-replace hardcoded translucent patterns with semantic tokens:

| Find | Replace with |
|------|-------------|
| `border-white/10` | `border-border` (resolves to `#E0E0E0`) |
| `border-white/15` | `border-border-strong` |
| `border-white/20` | `border-border-strong` |
| `border-white/5` | `border-border-subtle` |
| `bg-white/5` | `bg-neutral-bg3` |
| `bg-white/10` | `bg-neutral-bg4` |
| `bg-white/15` | `bg-neutral-bg5` |
| `bg-black/30` | `bg-black/10` |
| `bg-black/40` | `bg-black/15` |
| `bg-black/60` | `bg-black/30` |
| `hover:bg-white/5` | `hover:bg-neutral-bg3` |
| `hover:bg-white/10` | `hover:bg-neutral-bg4` |
| `hover:bg-white/15` | `hover:bg-neutral-bg5` |
| `hover:ring-white/40` | `hover:ring-brand/40` |
| `focus:border-white/25` | `focus:border-brand` |

Files with highest density of these patterns:
- `InteractionSidebar.tsx` (7 occurrences)
- `AlertInput.tsx` (6 occurrences)
- `GraphToolbar.tsx` (6 occurrences)
- `ModalShell.tsx` (5 occurrences)
- `ColorWheelPopover.tsx` (5 occurrences)

---

### Phase 3: Hardcoded Color Overrides

**Effort:** 20 min

Fix remaining non-token color references:

| Pattern | Files | Action |
|---------|-------|--------|
| `text-white` (on brand buttons) | `AlertInput`, `ColorWheelPopover`, `ErrorBanner` | **Keep** — white-on-teal is correct |
| `text-white` (labels on color swatches) | `ColorWheelPopover` | **Keep** — data-viz overlay |
| `text-green-400` / `text-red-400` / `text-yellow-400` | `LogStream`, `DataSourceCard`, `ResourceVisualizer` | Replace with `text-status-success` / `text-status-error` / `text-status-warning` |
| `bg-green-400` / `bg-red-400` | `LogStream` (connection dot) | Replace with `bg-status-success` / `bg-status-error` |
| `text-amber-400` | `ServiceHealthPopover`, `ServiceHealthSummary` | Replace with `text-status-warning` |
| `text-red-500 font-bold` (CRITICAL log level) | `LogStream` | Replace with `text-status-error font-bold` |
| `bg-yellow-500/10 border-yellow-500/30 text-yellow-400` | `ResourceVisualizer` | Replace with `bg-status-warning/10 border-status-warning/30 text-status-warning` |
| `prose-invert` | `DiagnosisPanel`, `StepCard` | Remove — `prose` without `invert` is correct for light theme |

---

### Phase 4: Canvas Rendering (Graph + Resource)

**Files:** `GraphCanvas.tsx`, `ResourceCanvas.tsx`
**Effort:** 45 min

These files use imperative Canvas 2D drawing with hardcoded `rgba(255,255,255,…)` and hex colors. They cannot be fixed by Tailwind class swaps.

**Strategy:** Read CSS custom properties from the DOM at render time.

```typescript
// Add to each canvas component:
const styles = getComputedStyle(document.documentElement);
const textPrimary = styles.getPropertyValue('--color-text-primary').trim();
const textMuted = styles.getPropertyValue('--color-text-muted').trim();
const borderDefault = styles.getPropertyValue('--color-border-default').trim();
```

Then replace:

| Hardcoded | CSS Variable |
|-----------|-------------|
| `rgba(255,255,255,0.15)` (edge stroke) | `var(--color-border-default)` |
| `rgba(255,255,255,0.12)` (link color) | `var(--color-border-default)` |
| `rgba(255,255,255,0.2)` (arrow) | `var(--color-border-strong)` |
| `rgba(255,255,255,0.25)` (double border) | `var(--color-border-strong)` |
| `rgba(255,255,255,0.5)` (strong stroke) | `var(--color-text-secondary)` |
| `#E4E4E7` (label fill) | `var(--color-text-primary)` |
| `#71717A` (sublabel fill) | `var(--color-text-muted)` |
| `#888` (fallback node) | `var(--color-text-muted)` |
| `rgba(228,228,231,0.2)` | `var(--color-text-secondary)` + alpha |

Also in `ColorWheelPopover.tsx`:
| `#fff` / `#000` (canvas strokes) | Keep — these are color picker UI, theme-independent |

---

### Phase 5: Modal & Overlay Adjustments

**Files:** `ModalShell.tsx`
**Effort:** 10 min

- Overlay: `bg-black/60 backdrop-blur-sm` → `bg-black/30 backdrop-blur-sm` (lighter scrim for light theme)
- Modal body: `bg-neutral-bg2 border-white/10` → `bg-white border-border` (already handled by token swap + Phase 2)
- Button in footer: `bg-white/10 hover:bg-white/15 text-text-primary` → `bg-neutral-bg3 hover:bg-neutral-bg4 text-text-primary`

---

### Phase 6: Resize Handle

**File:** `src/styles/globals.css` (lines ~95-110)
**Effort:** 5 min

The resize handle uses inline `hsla(0,0%,100%,…)` values. Replace with token-aligned grays:

| Current | Target |
|---------|--------|
| `hsla(0,0%,100%,0.15)` | `#E0E0E0` |
| `hsla(0,0%,100%,0.3)` | `#D1D1D1` |
| `hsla(0,0%,100%,0.5)` | `#C8C6C4` |

---

## 4. File-by-File Change Matrix

### HIGH Severity (structural changes needed)

| # | File | Phases | Key Changes |
|---|------|--------|-------------|
| 1 | `styles/globals.css` | 0, 1, 6 | Token swap, glass utilities, resize handle, scrollbars |
| 2 | `AlertInput.tsx` | 1, 2 | Glass classes, translucent borders/bgs |
| 3 | `DiagnosisPanel.tsx` | 1, 2, 3 | Glass classes, `prose-invert` removal |
| 4 | `GraphTopologyViewer.tsx` | 1, 2 | Glass classes, backdrop-blur overlay |
| 5 | `ResourceVisualizer.tsx` | 1, 2, 3 | Glass classes, backdrop-blur, hardcoded warning colors |
| 6 | `StepCard.tsx` | 1, 2, 3 | Glass classes, `prose-invert` removal |
| 7 | `LogStream.tsx` | 1, 2, 3 | Glass classes, hardcoded `text-green/red/yellow-400` |
| 8 | `InteractionSidebar.tsx` | 2 | 7 translucent patterns |
| 9 | `ModalShell.tsx` | 2, 5 | Overlay, translucent button |
| 10 | `GraphCanvas.tsx` | 4 | Canvas hardcoded rgba/hex |
| 11 | `ResourceCanvas.tsx` | 4 | Canvas hardcoded rgba/hex |
| 12 | `ColorWheelPopover.tsx` | 2, 3 | Translucent borders, glass bg |

### MEDIUM Severity (token swap auto-fixes + minor class swaps)

| # | File | Phases | Key Changes |
|---|------|--------|-------------|
| 13 | `tailwind.config.js` | 0 | All token values |
| 14 | `App.tsx` | 2 | `border-white/10`, `bg-brand/10` |
| 15 | `Header.tsx` | 2 | `border-white/10` |
| 16 | `TabBar.tsx` | 2 | `border-white/10` |
| 17 | `ActionButton.tsx` | 2 | `border-white/10`, `hover:border-white/20` |
| 18 | `AgentBar.tsx` | 2 | `border-white/10`, `bg-white/10` divider |
| 19 | `AgentCard.tsx` | 2 | `bg-white/5`, `hover:bg-white/10` |
| 20 | `AgentTimeline.tsx` | 2 | `border-white/5` |
| 21 | `DataSourceBar.tsx` | — | Auto-fixed by Phase 0 token swap |
| 22 | `DataSourceCard.tsx` | 2, 3 | `text-green/red-400` → status tokens |
| 23 | `ErrorBanner.tsx` | 1 | Glass class (auto-fixed) |
| 24 | `GraphToolbar.tsx` | 2 | 6 translucent patterns |
| 25 | `GraphTooltip.tsx` | 2 | `border-white/15` |
| 26 | `GraphContextMenu.tsx` | 2 | `border-white/15`, `hover:bg-white/10` |
| 27 | `HealthDot.tsx` | — | Auto-fixed by Phase 0 |
| 28 | `ProgressBar.tsx` | — | Auto-fixed by Phase 0 |
| 29 | `ServiceHealthPopover.tsx` | 2, 3 | `border-white/10`, `text-amber-400` |
| 30 | `ServiceHealthSummary.tsx` | 2, 3 | `border-white/10`, `text-amber-400` |
| 31 | `TabbedLogStream.tsx` | 2 | `border-white/10` |
| 32 | `TerminalPanel.tsx` | 2 | `border-white/10` |
| 33 | `ThinkingDots.tsx` | — | Auto-fixed by Phase 0 |
| 34 | `ResourceToolbar.tsx` | 2 | Same pattern as `GraphToolbar` |
| 35 | `ResourceTooltip.tsx` | 2 | `border-white/15` |

### LOW Severity (no changes)

Files with no dark-theme patterns: `ScenarioContext.tsx`, `config.ts`, `main.tsx`, `types/index.ts`, `vite-env.d.ts`, `MetricsBar.tsx`, `InvestigationPanel.tsx`, hooks (`useClickOutside`, `useInteractions`, `useInvestigation`, `usePausableSimulation`, `useResourceGraph`, `useTooltipTracking`, `useTopology`, `useNodeColor`), `formatTime.ts`, `sseStream.ts`, `graphConstants.ts`, `resourceConstants.ts`.

---

## 5. Execution Order

```
Phase 0  ──→  Phase 1  ──→  Phase 2  ──→  Phase 3  ──→  Phase 4  ──→  Phase 5  ──→  Phase 6
 tokens      glass utils    translucent    hardcoded      canvas        modal        resize
 (15 min)    (15 min)       (30 min)       (20 min)       (45 min)      (10 min)     (5 min)
  2 files     1 file         22 files       8 files        2 files       1 file       1 file
```

**Total estimated effort: ~2.5 hours**

Build & visual check recommended after each phase.

---

## 6. Testing Checklist

After each phase, verify:

- [ ] `npm run build` succeeds with no errors
- [ ] Body background is white (`#FFFFFF`)
- [ ] Header bar uses `#FAF9F8` with `#E0E0E0` bottom border
- [ ] Brand buttons show Fabric teal (`#117865`)
- [ ] Text is dark on light backgrounds (readable contrast)
- [ ] Glass cards render as solid white with subtle border/shadow
- [ ] Modals have a semi-transparent scrim (not opaque black)
- [ ] Graph canvas node labels are dark text on light canvas
- [ ] Graph edges are visible (light gray, not white-on-white)
- [ ] Log stream level colors match Fabric status palette
- [ ] Scrollbar thumb is visible on light background
- [ ] Focus rings are visible (teal ring, white offset)
- [ ] Color wheel popover still renders correctly (theme-independent)

---

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Graph data-viz colors may have poor contrast on white | Keep `COLOR_PALETTE` / `RESOURCE_NODE_COLORS` as-is; they were chosen for distinctness and work on both light/dark |
| Canvas `getComputedStyle` reads may cause perf issues | Cache values in a `useMemo` keyed on a theme version counter |
| Third-party components (force-graph-2d) style their own canvas | Verify `backgroundColor` prop is passed; check float-tooltip CSS |
| `prose-invert` removal may break markdown content styling | Test with long-form diagnosis content to verify readability |
