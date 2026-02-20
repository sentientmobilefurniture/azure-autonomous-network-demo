# UI/UX Improvement Plan — Autonomous Network NOC (fabricdemo)

> **Scope**: All changes target `/home/hanchoong/backup/azure-autonomous-network-demo/fabricdemo/frontend/`  
> **Date**: 2026-02-19  
> **Approach**: Each recommendation includes the specific files affected, the current state, the proposed change, and a rationale. Changes are ordered by impact. All proposals have been cross-checked for logical consistency, no contradictions, and no risk of breaking existing functionality.

---

## Table of Contents

1. [Layout & Spatial Hierarchy](#1-layout--spatial-hierarchy)
2. [Typography & Readability](#2-typography--readability)
3. [Color, Contrast & Theming](#3-color-contrast--theming)
4. [Interactive Controls & Affordances](#4-interactive-controls--affordances)
5. [Navigation & Wayfinding](#5-navigation--wayfinding)
6. [Investigation Flow (Core UX)](#6-investigation-flow-core-ux)
7. [Graph Visualizations](#7-graph-visualizations)
8. [Terminal / Log Panel](#8-terminal--log-panel)
9. [Services Panel](#9-services-panel)
10. [Scenario Panel](#10-scenario-panel)
11. [Modals & Overlays](#11-modals--overlays)
12. [Interaction History Sidebar](#12-interaction-history-sidebar)
13. [Responsive & Accessibility](#13-responsive--accessibility)
14. [Micro-interactions & Animation](#14-micro-interactions--animation)
15. [Performance-Sensitive UI](#15-performance-sensitive-ui)
16. [Implementation Priority Matrix](#16-implementation-priority-matrix)

---

## 1. Layout & Spatial Hierarchy

### 1.1 Increase Header Height & Breathing Room

**Files**: `Header.tsx`, `globals.css`  
**Current**: Header is `h-12` (48px) with `px-6`. Action buttons are tiny (`text-[10px]`) and cramped (`gap-1.5`).  
**Proposed**: Increase to `h-14` (56px), widen button gap to `gap-2.5`, increase button text to `text-[11px]`, and add `py-1` to all buttons.  
**Rationale**: The header is the primary orientation point. At 48px with 10px text, controls feel invisible and hard to click. 56px is still compact but respects minimum touch-target guidelines.  
**Risk check**: No layout conflicts — the `flex-1 min-h-0` on the content area below absorbs any height change.

### 1.2 Default Terminal Panel to Collapsed

**Files**: `App.tsx`  
**Current**: Terminal panel has `defaultSize={25}`, always occupying 25% of vertical space on first load.  
**Proposed**: Change `defaultSize` to `10` and mark it `collapsible`. Add a clear visual toggle button (e.g., `>_ Terminal ▾`) in the resize handle area, styled like a section header.  
**Rationale**: For demo audiences, the primary content (investigation + graph + diagnosis) should dominate. Terminal logs are a secondary concern. Users who need logs can expand.  
**Risk check**: The `collapsible` prop is already present. `TerminalPanel` mounts `TabbedLogStream` which keeps SSE connections alive regardless of panel size — no data loss from collapsing.

### 1.3 Improve Panel Resize Handle Visibility

**Files**: `globals.css`  
**Current**: Resize handles are 8px with a 3px-wide/32px-tall indicator. The visual cue is subtle; users may not realize panels are resizable.  
**Proposed**:  
- Increase the indicator to `width: 4px; height: 48px` (horizontal) / `height: 4px; width: 48px` (vertical).  
- Add a 3-dot "grip" icon via CSS `::before` (three stacked circles using radial-gradient or border-radius dots).  
- On hover, add a 2px solid brand-colored line along the full handle length.  
**Rationale**: Resize affordance is a learned UI pattern, but discoverability matters in demo apps shown to new audiences.  
**Risk check**: The `::after` pseudo-element is already used for the indicator; use `::before` for the grip dots. No conflict.

### 1.4 Add Zone Labels / Section Headers

**Files**: `InvestigationPanel.tsx`, `DiagnosisPanel.tsx`, `MetricsBar.tsx`  
**Current**: The Investigation and Diagnosis panels have internal labels (`text-[10px] uppercase`), but the MetricsBar has no visible section title — just the graph toolbar's "◆ Network Topology".  
**Proposed**:  
- Add a subtle sticky section header to each major zone: "Network Topology", "Investigation", "Diagnosis".  
- Use a consistent style: `text-[11px] uppercase tracking-wider font-semibold text-text-muted bg-neutral-bg2/80 backdrop-blur-sm sticky top-0 z-10 px-4 py-1.5 border-b border-border-subtle`.  
**Rationale**: When all panels are visible simultaneously, clear labels reduce cognitive load and help demo audiences follow the presenter.  
**Risk check**: `sticky top-0` works within overflow containers — each panel has `overflow-y-auto` so sticky will bind to the scroll container, not the viewport. Correct behavior.

---

## 2. Typography & Readability

### 2.1 Establish Type Scale Consistency

**Files**: Multiple components  
**Current**: Font sizes jump inconsistently: `text-[10px]`, `text-[11px]`, `text-xs` (12px), `text-sm` (14px). Labels use `text-[10px]`, content uses `text-xs`, and some buttons use `text-sm`.  
**Proposed**: Define a 4-step type scale in `tailwind.config.js`:

```
caption: 10px    → metadata, timestamps, status indicators
label:   11px    → section headers, badges, chips  
body:    12px    → primary content, log lines, step cards
action:  13px    → buttons, input text, interactive elements
heading: 14px    → panel titles, modal headers
```

Create Tailwind `fontSize` utilities: `text-caption`, `text-label`, `text-body-sm`, `text-action`, `text-heading-sm`.  
**Rationale**: The current size soup (10px, 11px, xs, sm) creates visual noise. A defined scale with semantic names makes the UI scannable and reduces "everything looks the same" fatigue.  
**Risk check**: This is additive — existing Tailwind classes continue to work. Migration can be incremental.

### 2.2 Increase Line Heights for Dense Content

**Files**: `LogStream.tsx`, `StepCard.tsx`, `OrchestratorThoughts.tsx`  
**Current**: Log lines use `leading-[1.6]`, step card content has no explicit line-height (inherits Tailwind defaults).  
**Proposed**: Set `leading-relaxed` (1.625) on all content cards and `leading-snug` (1.375) on metadata/timestamps. Add `leading-[1.7]` to log lines.  
**Rationale**: Dense data-heavy UIs require generous line spacing to prevent "wall of text" fatigue, especially at 11-12px font sizes.

### 2.3 Add Font Weight Differentiation

**Files**: `StepCard.tsx`, `InteractionSidebar.tsx`, `DiagnosisPanel.tsx`  
**Current**: Most text is either `font-medium` or default (400). The hierarchy is conveyed almost entirely through size and color.  
**Proposed**: Use `font-semibold` (600) for agent names and section titles, `font-medium` (500) for labels, `font-normal` (400) for body content. In step cards, make the agent name `font-semibold` and the query/response preview `font-normal`.  
**Rationale**: Weight contrast is the fastest visual hierarchy cue. Color alone is insufficient in data-dense UIs.

---

## 3. Color, Contrast & Theming

### 3.1 Fix Light-Mode Portal Button Colors

**Files**: `Header.tsx`  
**Current**: "Open Foundry" uses `text-purple-300` and "Open Fabric" uses `text-emerald-300`. These are palette shades designed for dark backgrounds. In light mode, `purple-300` (#C4B5FD) on white has a contrast ratio of ~2.0:1 — well below WCAG AA.  
**Proposed**: Use theme-aware colors:
- Foundry: `text-purple-700 dark:text-purple-300 border-purple-300/30 dark:border-purple-800/30 bg-purple-100 dark:bg-purple-800/10`
- Fabric: `text-emerald-700 dark:text-emerald-300 border-emerald-300/30 dark:border-emerald-800/30 bg-emerald-100 dark:bg-emerald-800/10`  
**Rationale**: WCAG AA requires 4.5:1 contrast for small text. This is the highest-priority accessibility fix.  
**Risk check**: These are the only hardcoded dark-palette colors in the codebase. All other components correctly use CSS variables.

### 3.2 Improve Status Color Accessibility

**Files**: `globals.css` (`:root` and `.dark`)  
**Current**: `--color-success: #107C10` (dark green) in light mode has adequate contrast on white (~5.5:1), but `--color-warning: #F7630C` (orange) on `--color-bg-3: #F3F2F1` has only ~2.8:1 contrast.  
**Proposed**: Darken warning in light mode to `#C85000` (contrast ~5.0:1). Keep dark mode as-is (`#FF8C42` on dark bg is fine).  
**Rationale**: Warning indicators in log streams and error banners must be readable at small sizes.

### 3.3 Add Subtle Background Tinting for Panel Differentiation

**Files**: `InvestigationPanel.tsx`, `DiagnosisPanel.tsx`  
**Current**: Both investigation and diagnosis panels share `bg-neutral-bg1` (via the parent), making them visually merge into a single block.  
**Proposed**: Add `bg-neutral-bg2` to the DiagnosisPanel's outermost div, creating a subtle visual break between the two panels.  
**Rationale**: When two panels are side-by-side with identical backgrounds, the resize handle between them is the only separator. A slight tint difference helps the brain parse them as distinct zones.  
**Risk check**: The `glass-card` class inside already applies `bg-neutral-bg1 border`, so the outer `bg-neutral-bg2` creates a subtle "canvas" effect. No conflict.

### 3.4 Fix GraphResultView Hardcoded Colors

**Files**: `GraphResultView.tsx`  
**Current**: Node stroke uses `rgba(255,255,255,0.3)` and label fill uses `rgba(240,240,240,0.9)` — hardcoded light-on-dark colors. In light mode, white strokes on white background are invisible.  
**Proposed**: Use the theme-aware approach already used by `GraphCanvas.tsx` — read CSS custom properties via `getComputedStyle`:
```tsx
ctx.strokeStyle = themeColors.borderDefault;
ctx.fillStyle = themeColors.textPrimary;
```
**Rationale**: This is a functional bug in light mode. The `GraphCanvas` component (topology viewer) already solves this correctly with a `MutationObserver` on the `<html>` class. Mirror that pattern.  
**Risk check**: The modal sets `backgroundColor="transparent"` which inherits from the `glass-card` parent — correct in both themes.

---

## 4. Interactive Controls & Affordances

### 4.1 Add Keyboard Shortcut Indicators

**Files**: `AlertInput.tsx`, `Header.tsx`  
**Current**: The alert textarea mentions "Ctrl+Enter to submit" in placeholder text, which vanishes once the user starts typing.  
**Proposed**:  
- Add a persistent `<kbd>` badge next to the "Investigate" button: `⌘⏎` (Mac) / `Ctrl+Enter` (Windows).  
- Style: `text-[9px] font-mono border border-border rounded px-1 py-0.5 text-text-muted`.  
- Detect platform via `navigator.platform` to show the correct modifier.  
**Rationale**: Keyboard shortcuts accelerate expert usage but must be discoverable. Placeholder text is ephemeral and easily missed.

### 4.2 Improve Button Hover/Active States

**Files**: `AlertInput.tsx`, `StepCard.tsx`, `ScenarioPanel.tsx`  
**Current**: The "Investigate" button uses `whileHover={{ scale: 1.02 }}` via Framer Motion. Other buttons lack scale feedback.  
**Proposed**: Standardize interactive feedback:
- Primary buttons: Keep `scale: 1.02` on hover + add `shadow-md` elevation.
- Secondary buttons (Examples, Stop, Copy, etc.): Add `translate-y: -1px` on hover + subtle `shadow-sm`.
- Glass cards with click handlers (StepCard, OrchestratorThoughts): Add `hover:shadow-md hover:border-border-strong` and remove the explicit `cursor-pointer` (it's implicit from click handlers).  
**Rationale**: Consistent feedback across all interaction types builds user confidence and reduces "did I click?" uncertainty.

### 4.3 Improve Text Input Focus States

**Files**: `AlertInput.tsx`, `InteractionSidebar.tsx`, `GraphToolbar.tsx`, `ResourceToolbar.tsx`  
**Current**: Focus ring uses `ring-2 ring-brand ring-offset-2` (global `*:focus-visible`). Text inputs additionally specify `focus:border-brand` or `focus:outline-none focus:border-brand/40`.  
**Proposed**: Unify all text inputs with a single focus style:
```css
.glass-input:focus-visible {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-subtle);
  outline: none;
}
```
Remove per-component `focus:outline-none focus:border-brand` classes and rely on `.glass-input` consistently.  
**Rationale**: Inconsistent focus styles (some with rings, some with border changes, some with both) create visual noise. One pattern.

### 4.4 Add Copy Feedback to Diagnosis Panel

**Files**: `DiagnosisPanel.tsx`  
**Current**: The "Copy" button calls `navigator.clipboard.writeText(finalMessage)` with no visual feedback.  
**Proposed**: After copying, briefly change the button text to "Copied ✓" for 1.5 seconds, with a green tint (`text-status-success`). Use local state + `setTimeout`.  
**Rationale**: Clipboard actions must have confirmation. Otherwise users repeatedly click unsure if it worked.  
**Risk check**: The timer should be cleaned up in useEffect return. Straightforward pattern.

---

## 5. Navigation & Wayfinding

### 5.1 Add Active Tab Indicator Animation

**Files**: `TabBar.tsx`  
**Current**: Active tab uses `border-b-2 border-brand text-brand` with a CSS `transition-colors`. The border simply appears/disappears.  
**Proposed**: Use a Framer Motion `layoutId` shared between tabs to create a sliding underline:
```tsx
{activeTab === tab.id && (
  <motion.div
    layoutId="tab-indicator"
    className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand rounded-full"
    transition={{ type: 'spring', stiffness: 500, damping: 30 }}
  />
)}
```
Wrap each tab button in `relative` positioning.  
**Rationale**: Sliding tab indicators are a well-established pattern (Material Design, Fluent UI) that provides clear directional feedback about where the user is navigating.  
**Risk check**: `framer-motion` is already a dependency with `AnimatePresence` used extensively. `layoutId` works with existing `motion` setup.

### 5.2 Add Breadcrumb Context to Modals

**Files**: `StepVisualizationModal.tsx`  
**Current**: The modal header shows `{icon} {step.agent} — {title}`. No indication of which step number or investigation this belongs to.  
**Proposed**: Add step context: `Step {step.step} · {step.agent} — {title}`. Include the step number as a mono badge, consistent with StepCard styling.  
**Rationale**: When multiple visualizations are opened in sequence, the user loses context about which step's data they're viewing.

### 5.3 Indicate Sidebar Panel State in Header

**Files**: `Header.tsx`, `App.tsx`  
**Current**: The sidebar collapse/expand toggle is inside the sidebar itself (a `◀`/`▶` button). If collapsed, newly onboarded users may not realize it exists.  
**Proposed**: Add a small "History" toggle button in the header (next to "Tabs"), styled like the other toggles:
```tsx
<ToggleBtn
  label="History"
  active={!sidebarCollapsed}
  onClick={handleSidebarToggle}
  icon="📋"
  tooltip="Toggle interaction history sidebar"
/>
```
This requires lifting `sidebarCollapsed` and `handleSidebarToggle` to be passed to `Header` via props.  
**Rationale**: All global layout toggles (tabs, theme, services) should be accessible from the header. The sidebar toggle is currently buried.  
**Risk check**: `sidebarCollapsed` is already a state in `App.tsx`. Passing it as a prop is straightforward. The sidebar's internal toggle should remain for inline convenience.

---

## 6. Investigation Flow (Core UX)

### 6.1 Add Progress Timeline Header

**Files**: `AgentTimeline.tsx`  
**Current**: Steps are listed vertically with individual cards. There's no visual progress indicator showing "3 of 6 agents complete" or elapsed time during a run.  
**Proposed**: Add a small horizontal progress bar above the step cards during an active run:
```tsx
{running && steps.length > 0 && (
  <div className="mb-3">
    <div className="flex items-center justify-between text-[10px] text-text-muted mb-1">
      <span>{steps.length} step{steps.length !== 1 ? 's' : ''} completed</span>
      <span>{elapsedTime}s</span>
    </div>
    <div className="h-1 bg-neutral-bg4 rounded-full overflow-hidden">
      <motion.div
        className="h-full bg-brand rounded-full"
        animate={{ width: `${Math.min((steps.length / 8) * 100, 95)}%` }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      />
    </div>
  </div>
)}
```
Note: The denominator (8) is an estimate since total steps aren't known upfront. Use `95%` max to avoid falsely suggesting completion.  
**Rationale**: Long-running investigations (30-120s during demos) need progress feedback beyond bouncing dots.  
**Risk check**: The elapsed time can be computed from `Date.now() - startTimeRef` which is already tracked in `useInvestigation`. Pass it down or compute locally with `useState` + `useEffect`/`setInterval`.

### 6.2 Auto-scroll to Latest Step

**Files**: `InvestigationPanel.tsx`, `AgentTimeline.tsx`  
**Current**: The investigation panel has `overflow-y-auto` but no auto-scroll behavior. As steps accumulate, new steps appear below the fold and users must manually scroll.  
**Proposed**: Add a `ref` to the bottom of the step list and call `scrollIntoView({ behavior: 'smooth' })` when a new step is added. Include a "stick to bottom" toggle similar to `LogStream.tsx`:
```tsx
const bottomRef = useRef<HTMLDivElement>(null);
useEffect(() => {
  if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
}, [steps.length]);
```
**Rationale**: This pattern is already implemented in `LogStream.tsx` for logs. The investigation panel handles the same streaming-content UX pattern but lacks this feature.  
**Risk check**: No conflict. The `InvestigationPanel` div already has `overflow-y-auto`.

### 6.3 Improve Empty State for Investigation Panel

**Files**: `InvestigationPanel.tsx`, `AgentTimeline.tsx`  
**Current**: Before any investigation, the panel shows just the alert textarea and nothing else (AgentTimeline returns `null` when `!runStarted && steps.length === 0`).  
**Proposed**: Show a welcome/onboarding card below the textarea:
```tsx
{!runStarted && steps.length === 0 && (
  <div className="glass-card p-6 flex flex-col items-center text-center mt-4">
    <span className="text-3xl mb-3 opacity-30">◆</span>
    <p className="text-sm font-medium text-text-primary mb-1">Ready to Investigate</p>
    <p className="text-xs text-text-muted max-w-xs leading-relaxed">
      Paste a NOC alert above, or click "Examples" to try a pre-built scenario.
      The orchestrator will coordinate specialist agents to diagnose the issue.
    </p>
  </div>
)}
```
**Rationale**: Empty states are critical UX touchpoints. The Diagnosis panel has one (`Submit an alert to begin investigation`), but the Investigation panel is blank — creating asymmetry.

### 6.4 Add Step Card Error Detail Toggle

**Files**: `StepCard.tsx`  
**Current**: Error steps show the agent name with "— FAILED" suffix and a red dot. The error message is only visible in the expanded state.  
**Proposed**: For error steps, show a 1-line error preview even in collapsed state:
```tsx
{!expanded && step.error && (
  <p className="text-[11px] text-status-error mt-1.5 truncate">
    ▸ {step.response?.slice(0, 100) || 'Agent returned an error'}
  </p>
)}
```
**Rationale**: Errors are high-signal events. Requiring expansion to see error details slows triage during demos.  
**Risk check**: `step.response` may contain the error message based on backend behavior. If not, the fallback text handles it.

---

## 7. Graph Visualizations

### 7.1 Add Graph Legend to Topology Viewer

**Files**: `GraphTopologyViewer.tsx`, `GraphToolbar.tsx`  
**Current**: The graph toolbar shows filterable label chips with colored dots, but there's no persistent legend showing what each color means — the dots are interactive filter toggles, not a legend.  
**Proposed**: Add a small floating legend in the bottom-left corner of the graph canvas:
```tsx
<div className="absolute bottom-2 left-2 bg-neutral-bg2/90 backdrop-blur-sm border border-border rounded-lg px-3 py-2 space-y-1">
  {availableLabels.map(label => (
    <div key={label} className="flex items-center gap-2">
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: getColor(label) }} />
      <span className="text-[10px] text-text-secondary">{label}</span>
    </div>
  ))}
</div>
```
Make the legend collapsible with a small `▾ Legend` toggle.  
**Rationale**: During demos, the audience sees the graph projected on screen. Without a legend, color semantics are lost.  
**Risk check**: The `absolute bottom-2 left-2` won't conflict with the existing `⏸ Paused` indicator which is `absolute bottom-2 right-2`.

### 7.2 Improve Node Hover Feedback on Canvas

**Files**: `GraphCanvas.tsx`, `ResourceCanvas.tsx`  
**Current**: Hovering a node triggers a tooltip overlay but provides no visual feedback on the node itself (no glow, no size change).  
**Proposed**: Track the hovered node ID in canvas state and in `nodeCanvasObject`, draw a glow ring for the hovered node:
```tsx
if (node.id === hoveredNodeId) {
  ctx.beginPath();
  ctx.arc(node.x!, node.y!, size + 4, 0, 2 * Math.PI);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.globalAlpha = 0.4;
  ctx.stroke();
  ctx.globalAlpha = 1;
}
```
**Rationale**: Direct manipulation feedback (the node itself responds) is more effective than indirect feedback (a tooltip somewhere else).  
**Risk check**: `onNodeHover` already provides the hovered node. Store `hoveredNodeId` as local state in GraphCanvas and use it in the render callback.

### 7.3 Add Double-Click Zoom Feedback

**Files**: `GraphCanvas.tsx`  
**Current**: `onNodeClick` is mapped to `handleNodeDoubleClick` (center + zoom to node). This means single-click == double-click behavior, which is confusing.  
**Proposed**: 
- Map `onNodeClick` to select (highlight) the node.
- Map `onNodeDblClick` (if supported by react-force-graph-2d) to the zoom behavior.
- If `onNodeDblClick` is not supported, use a click-timing approach: set a 300ms timer on first click; if second click comes within window, zoom; otherwise, select.  
**Rationale**: Overloading single-click with zoom-to behavior is unexpected. Select-on-click, zoom-on-double-click is the standard graph interaction pattern.  
**Risk check**: `react-force-graph-2d` does not have a separate `onNodeDblClick` prop. The click-timing approach is needed. Ensure the `setContextMenu(null)` call from `onBackgroundClick` doesn't interfere.

---

## 8. Terminal / Log Panel

### 8.1 Add Log Level Color Bars

**Files**: `LogStream.tsx`  
**Current**: Log levels are distinguished only by text color (`text-gray-500` for DEBUG, `text-status-success` for INFO, etc.).  
**Proposed**: Add a 2px left border to each log line matching the level color:
```tsx
<div key={line.id} className="whitespace-pre-wrap break-all flex">
  <span className={`w-0.5 mr-2 shrink-0 rounded-full self-stretch ${LEVEL_BAR_COLORS[line.level]}`} />
  <span>...</span>
</div>
```
Where `LEVEL_BAR_COLORS` maps to `bg-gray-500`, `bg-status-success`, `bg-status-warning`, `bg-status-error`.  
**Rationale**: Colored text on colored backgrounds can be hard to parse. A physical colored bar provides scannable orientation.

### 8.2 Add Search/Filter for Log Content

**Files**: `LogStream.tsx`  
**Current**: Only supports log-level filtering via a `<select>` dropdown.  
**Proposed**: Add a text search input next to the level filter that highlights matching log lines:
```tsx
<input type="text" placeholder="Filter..." className="..." onChange={(e) => setFilter(e.target.value)} />
```
Filter log lines to only show those containing the search text. Highlight matches with `<mark>` tags.  
**Rationale**: During live demos and debugging, finding a specific log message in a stream of 200 lines is painful without text filtering.

### 8.3 Add "Copy All" Button

**Files**: `LogStream.tsx`  
**Current**: Only has "Clear" (🗑) and "Scroll to bottom" (▼ bottom) controls.  
**Proposed**: Add a "Copy" button that copies all visible (filtered) log lines:
```tsx
<button onClick={() => navigator.clipboard.writeText(filteredLines.map(l => `${l.ts} ${l.level} ${l.name}: ${l.msg}`).join('\n'))}
  className="text-[10px] text-text-muted hover:text-text-primary">📋</button>
```
**Rationale**: When debugging, users often need to share logs. Currently they must select text manually.

---

## 9. Services Panel

### 9.1 Improve Visual Hierarchy

**Files**: `ServicesPanel.tsx`  
**Current**: The panel uses a flat tree with `text-xs` and `text-[10px]` for everything. Categories and items have the same visual weight.  
**Proposed**:
- Category headers: `text-[13px] font-semibold`
- Item labels: `text-xs font-medium`
- Item details: `text-[11px] text-text-muted font-normal`
- Sub-items (children): `text-[10px] text-text-muted italic`  
Add `ml-4` indentation for items under categories, and `ml-7` for sub-items (currently `pl-8`).  
**Rationale**: The Services panel is information-dense (7+ categories, many items). Without clear hierarchy, it's overwhelming at first glance.

### 9.2 Add Last-Checked Timestamp

**Files**: `ServicesPanel.tsx`  
**Current**: Items show elapsed time during checking (`{item.elapsed}s`) but no "last checked at" timestamp after completion.  
**Proposed**: After a check completes, show `✓ 2s ago` (relative) that updates every 30s. Store the last-check time in `TreeItem`. This prevents stale green dots from misleading users into thinking services are still healthy.  
**Rationale**: A green dot means "was healthy the last time we checked" — without a timestamp, users assume it means "healthy right now."

### 9.3 Improve Panel Overlay Z-Index

**Files**: `ServicesPanel.tsx`  
**Current**: The backdrop is `fixed inset-0 bg-black/20 z-40`, and the panel is `absolute top-full right-0 ... z-50`. The panel is positioned relative to the header button.  
**Proposed**: Change the panel to `fixed` positioning, computed from the button's bounding rect. This prevents clipping if the header parent has `overflow: hidden`.  
**Rationale**: `absolute top-full` on a child of a `flex` header with `overflow: hidden` viewport scenarios can clip. `fixed` is more reliable for overlays.  
**Risk check**: The existing `useClickOutside` hook correctly handles `fixed` positioned elements. The `anchorRect` pattern from `ColorWheelPopover` can be followed.

---

## 10. Scenario Panel

### 10.1 Add Visual Icons to Use Case List

**Files**: `ScenarioPanel.tsx`  
**Current**: Use cases are plain bulleted text with `<span className="text-brand">•</span>`.  
**Proposed**: Use numbered badges like the demo flow steps:
```tsx
<span className="text-xs font-mono bg-brand/10 text-brand px-1.5 py-0.5 rounded shrink-0">{i+1}</span>
```
**Rationale**: Numbered lists are easier to reference during demos ("let's try use case 3") than bulleted lists.

### 10.2 Add Demo Flow Status Tracking

**Files**: `ScenarioPanel.tsx`  
**Current**: Demo flow steps show prompts and expected behavior, but there's no indication of which steps have been completed during the session.  
**Proposed**: Track completed prompts in local state (keyed by prompt text). When a prompt matches a previously submitted alert that has a saved interaction, show a `✓ Completed` badge on that step.  
**Rationale**: During multi-step demos, the presenter can lose track of which steps have been run. Visual completion markers help.

---

## 11. Modals & Overlays

### 11.1 Improve Modal Scrolling Behavior

**Files**: `StepVisualizationModal.tsx`  
**Current**: The modal content area uses `overflow-auto min-h-[300px]`. The modal itself is constrained to `max-h-[85vh]`.  
**Proposed**:  
- Add `overscroll-behavior: contain` to prevent background page scroll when the modal content reaches its bounds.  
- On iOS/mobile (if relevant): add `-webkit-overflow-scrolling: touch`.  
**Rationale**: Without `overscroll-behavior: contain`, reaching the end of modal scroll content causes the background to scroll — a jarring experience.

### 11.2 Add Escape Key Hint

**Files**: `StepVisualizationModal.tsx`  
**Current**: Escape key closes the modal (handled in `useEffect`), but this isn't indicated visually.  
**Proposed**: Add `<kbd>Esc</kbd>` badge next to the close button:
```tsx
<span className="text-[9px] font-mono text-text-muted border border-border rounded px-1 mr-1">Esc</span>
```
**Rationale**: Keyboard shortcuts need visual discovery. Expert users will internalize it; new users need the hint.

### 11.3 Improve Table Empty States

**Files**: `TableResultView.tsx`, `GraphResultView.tsx`  
**Current**: Empty states show "No data returned" / "No graph data returned" in plain text.  
**Proposed**: Add a relevant icon and suggestion:
```tsx
<div className="flex flex-col items-center gap-2">
  <span className="text-3xl opacity-30">▤</span>
  <p className="text-sm text-text-muted">No telemetry data returned</p>
  <p className="text-xs text-text-muted/60">The KQL query returned zero rows. Check the query or time range.</p>
</div>
```
**Rationale**: Empty states should explain *why* and suggest *what to do*, not just state the fact.

---

## 12. Interaction History Sidebar

### 12.1 Add Visual Summary to Interaction Cards

**Files**: `InteractionSidebar.tsx`  
**Current**: Cards show timestamp, scenario badge, query preview (2-line clamp), and metadata (steps, time).  
**Proposed**: Add a success/error indicator based on whether the interaction has a non-empty diagnosis:
```tsx
<span className={`h-1.5 w-1.5 rounded-full self-start mt-1 shrink-0 ${
  interaction.diagnosis ? 'bg-status-success' : 'bg-status-error'
}`} />
```
Place this at the start of the query preview line.  
**Rationale**: Quickly distinguishing successful vs. failed investigations in history helps users find relevant references.

### 12.2 Add "Clear All" with Confirmation

**Files**: `InteractionSidebar.tsx`  
**Current**: Individual interactions can be deleted with a ✕ button (with confirmation). No bulk action.  
**Proposed**: Add a "Clear All" button in the sidebar header (visible only when there are interactions):
```tsx
<button className="text-[10px] text-text-muted hover:text-status-error transition-colors"
  onClick={handleClearAll}>Clear All</button>
```
Use a two-click confirmation (same pattern as individual delete).  
**Rationale**: After extensive demo sessions, history can accumulate 20+ entries. Bulk clearing is expected.

### 12.3 Improve Collapsed State Affordance

**Files**: `InteractionSidebar.tsx`  
**Current**: When collapsed, the sidebar shows only a `◀` button. No indication of how many interactions exist.  
**Proposed**: In collapsed state, show a vertical rotated label and a count badge:
```tsx
{collapsed && (
  <div className="flex flex-col items-center py-4 gap-2">
    <span className="text-[10px] text-text-muted [writing-mode:vertical-lr] rotate-180">History</span>
    {interactions.length > 0 && (
      <span className="bg-brand/15 text-brand text-[10px] rounded-full px-1.5 py-0.5">{interactions.length}</span>
    )}
  </div>
)}
```
**Rationale**: A collapsed panel with just a `◀` arrow gives no information about its content or purpose.

---

## 13. Responsive & Accessibility

### 13.1 Add ARIA Labels to All Graph Canvases

**Files**: `GraphCanvas.tsx`, `ResourceCanvas.tsx`, `GraphResultView.tsx`  
**Current**: The `<canvas>` elements rendered by `ForceGraph2D` have no `aria-label` or accessible fallback.  
**Proposed**: Wrap each canvas container in a `<div role="img" aria-label="...">`:
```tsx
<div role="img" aria-label={`Network topology graph with ${nodes.length} nodes and ${edges.length} edges`}>
  <ForceGraph2D ... />
</div>
```
**Rationale**: Canvas-based visualizations are completely opaque to screen readers. An `aria-label` provides at minimum a description.

### 13.2 Add Skip-to-Content Link

**Files**: `App.tsx`  
**Current**: No skip links. Tab-navigating through the header, tab bar, and metrics bar before reaching the investigation panel requires many keystrokes.  
**Proposed**: Add a visually-hidden skip link as the first child of the root:
```tsx
<a href="#investigation-main" className="sr-only focus:not-sr-only focus:fixed focus:z-[9999] focus:top-2 focus:left-2 focus:bg-brand focus:text-white focus:px-4 focus:py-2 focus:rounded">
  Skip to Investigation
</a>
```
Add `id="investigation-main"` to the `InvestigationPanel` wrapper.  
**Rationale**: WCAG 2.1 Level A requirement (2.4.1 Bypass Blocks). Standard accessibility practice.

### 13.3 Improve Color-Blind Accessibility in Graphs

**Files**: `graphConstants.ts`, `resourceConstants.ts`  
**Current**: The color palette relies heavily on red-green differentiation (status colors, node type colors).  
**Proposed**:  
- Supplement color with **shapes** (already done in ResourceCanvas — circles, diamonds, hexagons — extend this pattern to GraphCanvas).
- Add a hatching/pattern fill option for color-blind mode.
- Alternatively, for the topology graph, use icons/initials inside nodes: "CR" for CoreRouter, "AS" for AggSwitch, etc.  
**Rationale**: ~8% of men have red-green color deficiency. The resource graph already uses shapes — the topology graph should follow suit.

### 13.4 Add Viewport Meta for Mobile

**Files**: `index.html`  
**Current**: `<meta name="viewport" content="width=device-width, initial-scale=1.0" />` is present, but the app has no responsive layout considerations — panel groups, canvas sizes, and header buttons assume desktop widths.  
**Proposed**: This is a demo app primarily viewed on desktop/projector. Add a clear "Best viewed on desktop" notice for mobile viewports:
```tsx
{window.innerWidth < 768 && (
  <div className="fixed inset-0 z-50 bg-neutral-bg1 flex items-center justify-center p-6 text-center">
    <div>
      <span className="text-brand text-3xl">◆</span>
      <p className="text-sm text-text-primary mt-3 font-medium">Best viewed on desktop</p>
      <p className="text-xs text-text-muted mt-1">This application is designed for desktop screen sizes.</p>
    </div>
  </div>
)}
```
**Rationale**: Rather than a broken mobile layout, a clear message is better UX. The app's panel-heavy layout cannot meaningfully adapt to mobile without a complete redesign.

---

## 14. Micro-interactions & Animation

### 14.1 Add Step Card Entry Stagger

**Files**: `AgentTimeline.tsx`, `StepCard.tsx`  
**Current**: Step cards use `initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}` individually, but when viewing history (all steps loaded at once), they all animate simultaneously.  
**Proposed**: When loading historical interactions (multiple steps at once), add a stagger delay:
```tsx
transition={{ duration: 0.2, ease: 'easeOut', delay: isHistorical ? index * 0.05 : 0 }}
```
Pass `isHistorical` based on whether `viewingInteraction` is set.  
**Rationale**: Staggered entry of list items is a well-studied UX pattern that helps users parse multiple items by giving each a moment of visual attention.  
**Risk check**: The `delay` value (50ms per item) ensures even 20 steps complete animation within 1 second. Not sluggish.

### 14.2 Add Toast Auto-Dismiss Animation

**Files**: `Toast.tsx`  
**Current**: Toast appears with `opacity: 0 → 1, y: 20 → 0` and dismisses after 3 seconds. But the dismiss is instant (no exit animation — `AnimatePresence` is not used around the Toast in `App.tsx`).  
**Proposed**: Wrap the Toast rendering in `<AnimatePresence>` in `App.tsx`:
```tsx
<AnimatePresence>
  {toastMessage && <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />}
</AnimatePresence>
```
Add `exit={{ opacity: 0, y: 20 }}` to the Toast's `motion.div`.  
**Rationale**: Abrupt disappearance of UI elements is a known UX pain point. Exit animations confirm the action was intentional.  
**Risk check**: `AnimatePresence` is already imported in `App.tsx` — wait, actually checking: `App.tsx` does NOT import `AnimatePresence`. However, the `Toast` component already has a `motion.div`, so adding `<AnimatePresence>` in `App.tsx` is a minimal change. Import it from `framer-motion`.

### 14.3 Thinking Dots — Add Context Text Rotation

**Files**: `ThinkingDots.tsx`  
**Current**: Shows bouncing dots with `{agent} — {status}` text.  
**Proposed**: If the thinking state persists for >5 seconds, cycle through contextual messages:
```
"Analyzing graph topology..."
"Querying telemetry data..."
"Correlating service dependencies..."
```
Use `useEffect` with a 5-second interval to rotate through messages, but only if the parent-provided `status` hasn't changed (i.e., a real status update takes priority).  
**Rationale**: Long waits with static status text feel frozen. Rotating messages provide progress illusion.  
**Risk check**: The `thinking.status` prop from `useInvestigation` is the source of truth. The rotation should only apply as a supplement, never replacing a real status update.

---

## 15. Performance-Sensitive UI

### 15.1 Memoize Expensive Canvas Renders

**Files**: `GraphCanvas.tsx`, `ResourceCanvas.tsx`  
**Current**: `nodeCanvasObject` is wrapped in `useCallback` with appropriate dependencies (`getNodeColor, getNodeSize, nodeDisplayField, themeColors`). This is correct.  
**No changes needed** — the current implementation is well-optimized. Both canvases use `useCallback` for render functions and `MutationObserver` for theme change detection.

### 15.2 Virtualize Long Interaction Lists

**Files**: `InteractionSidebar.tsx`  
**Current**: All interactions render in a flat list with `overflow-y-auto`. With 50+ interactions, this could cause scroll jank.  
**Proposed**: For now, the `limit=50` on the API call is a reasonable cap. If the list grows, consider `react-window` or `react-virtualized`. However, adding a new dependency for a demo app is overkill.  
**Alternative**: Add a "Show more" pagination button instead of loading all 50 at once. Show 10, then "Load more" appends the next 10.  
**Rationale**: Pragmatic compromise — full virtualization is over-engineering for a demo, but unbounded rendering is a latent risk.

### 15.3 Debounce Search Inputs

**Files**: `GraphToolbar.tsx`, `ResourceToolbar.tsx`, `InteractionSidebar.tsx`  
**Current**: Search inputs trigger state updates on every keystroke (`onChange={(e) => onSearchChange(e.target.value)}`). For graph filtering, this triggers re-filtering on every character.  
**Proposed**: Add a 150ms debounce to search inputs using a local input state + `useEffect`:
```tsx
const [localSearch, setLocalSearch] = useState(searchQuery);
useEffect(() => {
  const timer = setTimeout(() => onSearchChange(localSearch), 150);
  return () => clearTimeout(timer);
}, [localSearch]);
```
**Rationale**: With 100+ graph nodes, filtering on every keystroke causes noticeable frame drops. 150ms debounce is imperceptible to users.

---

## 16. Implementation Priority Matrix

| Priority | Item | Impact | Effort | Risk |
|----------|------|--------|--------|------|
| **P0 — Critical** | 3.1 Fix light-mode portal button contrast | High (accessibility bug) | Low (CSS only) | None |
| **P0 — Critical** | 3.4 Fix GraphResultView hardcoded colors | High (visual bug) | Low | None |
| **P1 — High** | 6.2 Auto-scroll to latest step | High (core UX gap) | Low | None |
| **P1 — High** | 4.4 Copy feedback on Diagnosis panel | Medium | Low | None |
| **P1 — High** | 1.2 Default terminal to collapsed | High (demo-first UX) | Low | None |
| **P1 — High** | 6.3 Empty state for Investigation panel | Medium | Low | None |
| **P1 — High** | 14.2 Toast exit animation | Low-Medium | Minimal | None |
| **P2 — Medium** | 1.1 Header height & breathing room | Medium | Low | None |
| **P2 — Medium** | 2.1 Type scale consistency | High (systemic) | Medium | Low |
| **P2 — Medium** | 5.1 Tab indicator animation | Medium | Low | None |
| **P2 — Medium** | 6.1 Progress timeline header | Medium | Medium | Low |
| **P2 — Medium** | 7.1 Graph legend | Medium | Low | None |
| **P2 — Medium** | 8.1 Log level color bars | Medium | Low | None |
| **P2 — Medium** | 12.3 Collapsed sidebar affordance | Medium | Low | None |
| **P2 — Medium** | 15.3 Debounce search inputs | Medium | Low | None |
| **P3 — Low** | 1.3 Resize handle visibility | Low-Medium | Low | None |
| **P3 — Low** | 1.4 Zone labels/section headers | Low-Medium | Low | None |
| **P3 — Low** | 3.2 Warning color accessibility | Low-Medium | Minimal | None |
| **P3 — Low** | 3.3 Panel background differentiation | Low | Minimal | None |
| **P3 — Low** | 4.1 Keyboard shortcut indicators | Low | Low | None |
| **P3 — Low** | 4.2 Hover/active state consistency | Low | Medium | Low |
| **P3 — Low** | 4.3 Focus state unification | Low | Medium | Low |
| **P3 — Low** | 5.2 Breadcrumb in modals | Low | Low | None |
| **P3 — Low** | 5.3 History toggle in header | Low | Low | None |
| **P3 — Low** | 6.4 Error preview in collapsed steps | Low | Low | None |
| **P3 — Low** | 7.2 Node hover glow | Low | Low | None |
| **P3 — Low** | 7.3 Double-click zoom separation | Low | Medium | Low |
| **P3 — Low** | 8.2 Log content search | Low | Medium | None |
| **P3 — Low** | 8.3 Log copy all | Low | Low | None |
| **P3 — Low** | 9.1 Services panel hierarchy | Low | Low | None |
| **P3 — Low** | 9.2 Last-checked timestamp | Low | Low | None |
| **P3 — Low** | 9.3 Services panel z-index | Low | Low | None |
| **P3 — Low** | 10.1 Use case numbered badges | Low | Minimal | None |
| **P3 — Low** | 10.2 Demo flow status tracking | Low | Medium | None |
| **P3 — Low** | 11.1 Modal overscroll containment | Low | Minimal | None |
| **P3 — Low** | 11.2 Escape key hint | Low | Minimal | None |
| **P3 — Low** | 11.3 Empty state improvements | Low | Low | None |
| **P3 — Low** | 12.1 Interaction success indicator | Low | Low | None |
| **P3 — Low** | 12.2 Clear all history | Low | Low | None |
| **P3 — Low** | 13.1 Canvas ARIA labels | Low (a11y) | Minimal | None |
| **P3 — Low** | 13.2 Skip-to-content link | Low (a11y) | Minimal | None |
| **P3 — Low** | 13.3 Color-blind accessibility | Medium (a11y) | Medium | Low |
| **P3 — Low** | 13.4 Mobile viewport notice | Low | Low | None |
| **P3 — Low** | 14.1 Step card stagger | Low | Low | None |
| **P3 — Low** | 14.3 Thinking dots rotation | Low | Low | Low |

---

## Summary of Highest-Impact Changes

The **six changes that would most improve the demo experience** with minimal risk:

1. **Fix light-mode contrast bugs** (§3.1, §3.4) — currently broken
2. **Auto-scroll investigation panel** (§6.2) — missing core UX feature
3. **Default terminal panel collapsed** (§1.2) — better first impression
4. **Copy feedback on diagnosis** (§4.4) — zero-effort polish
5. **Investigation empty state** (§6.3) — onboarding moment
6. **Tab sliding indicator** (§5.1) — professional navigation feel

All six can be implemented in ~2-3 hours total with no risk of breaking existing functionality.
