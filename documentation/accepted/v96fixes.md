# v9.6 UI Fixes — Implementation Plan

> **Created:** 2026-02-15
> **Last audited:** 2026-02-15
> **Status:** ⬜ Not Started
> **Goal:** Fix two UI polish issues: (1) show a loading overlay on startup while
> the persisted scenario is validated against CosmosDB, and (2) remove the
> redundant color-palette from the right-click context menu since the toolbar
> color wheel already provides this functionality.

---

## Requirements (Original)

1. When I start the app and go the UI, it initializes to the last scenario used even though the scenarios have not yet been fetched from cosmosdb. This is confusing. UI should init to some kind of blank or placeholder, or there should be a loading wheel or transparent screen overlay or something to let you know that scenarios are being fetched from db. If it is possible to log this on that transparent screen overlay, even better
2. Color selection on the nodes themselves is redundant. only color wheel is needed.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 1:** Startup scenario loading overlay | ⬜ Not started | `ScenarioContext.tsx`, `App.tsx` |
| **Phase 2:** Remove context menu color picker | ⬜ Not started | `GraphContextMenu.tsx` |

### Deviations From Plan

| # | Plan Said | What Was Done | Rationale |
|---|-----------|---------------|-----------|
| D-1 | — | — | — |

### Extra Work Not In Plan

- {None yet}

---

## Table of Contents

- [Requirements (Original)](#requirements-original)
- [Codebase Conventions & Context](#codebase-conventions--context)
- [Overview of Changes](#overview-of-changes)
- [Item 1: Startup Scenario Loading Overlay](#item-1-startup-scenario-loading-overlay)
- [Item 2: Remove Context Menu Color Picker](#item-2-remove-context-menu-color-picker)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)

---

## Codebase Conventions & Context

### Request Routing

| URL prefix | Proxied to | Config |
|------------|-----------|--------|
| `/query/*` | graph-query-api on port 8100 | `vite.config.ts` proxy + `nginx.conf` |

### Loading Pattern Conventions

The app uses several existing loading patterns. The startup overlay should be
consistent with them:

| Pattern | Location | Style |
|---------|----------|-------|
| Pulse skeleton blocks | `InteractionSidebar.tsx` L120-126 | `h-20 rounded-lg bg-white/5 animate-pulse` |
| Pulsing text | `GraphTopologyViewer.tsx` L170-173 | `"Loading topology…"` with `animate-pulse` |
| Spinner circle | `ScenarioChip.tsx` L64 | `animate-spin rounded-full border-2 border-brand border-t-transparent` |
| Progress banner | `ProvisioningBanner.tsx` | Colored banner with icon + step text |

### Data Format Conventions

| Convention | Format | Where Used |
|-----------|--------|------------|
| Saved scenarios API | `GET /query/scenarios/saved` → `{ scenarios: [...] }` | `ScenarioContext.tsx`, `useScenarios.ts` |
| localStorage keys | `'activeScenario'` (string name), `'graph-colors'` (JSON) | `ScenarioContext.tsx`, `GraphTopologyViewer.tsx` |

### Color System

Node colors follow a priority chain defined in `useNodeColor.ts`:

```
userOverride[label]  →  scenarioNodeColors[label]  →  NODE_COLORS[label]  →  autoColor(label)
```

Both the context menu palette and the toolbar color wheel call the same
`onSetColor(label, color)` callback. The toolbar `ColorWheelPopover` provides
a superset of the same functionality (HSL wheel + hex input + preset swatches).

---

## Overview of Changes

| # | Item | Category | Impact | Effort |
|---|------|----------|--------|--------|
| 1 | Startup scenario loading overlay | Frontend | High — UX confusion on every app load | Small |
| 2 | Remove context menu color picker | Frontend | Low — removes redundancy | Tiny |

### Dependency Graph

```
Phase 1 (loading overlay)     ← independent
Phase 2 (color picker removal) ← independent
```

Both phases are fully independent and can be implemented in parallel or any order.

---

## Item 1: Startup Scenario Loading Overlay

### Current State

**`ScenarioContext.tsx`** (L50-52): `activeScenario` is initialized synchronously from
`localStorage.getItem('activeScenario')` on mount. All bindings (`activeGraph`,
`activeRunbooksIndex`, etc.) are derived immediately from this persisted name.

**`ScenarioContext.tsx`** (L92-105): A validation `useEffect` fires on mount —
it calls `fetch('/query/scenarios/saved')` to check the persisted scenario still
exists in CosmosDB. If not found, it clears the state. But this is completely
**fire-and-forget** with **no loading indicator**.

```tsx
// Current: silent validation, no loading state exposed
useEffect(() => {
  if (!activeScenario) return;
  let cancelled = false;
  fetch('/query/scenarios/saved')
    .then((r) => r.json())
    .then((data) => {
      if (cancelled) return;
      const saved: string[] = (data.scenarios ?? []).map((s: { id: string }) => s.id);
      if (!saved.includes(activeScenario)) {
        console.warn(`Persisted scenario "${activeScenario}" no longer exists — clearing.`);
        setActiveScenarioRaw(null);
        localStorage.removeItem('activeScenario');
      }
    })
    .catch(() => {}); // silent
  return () => { cancelled = true; };
}, []);
```

**Problem:** When a user returns to the app, the UI immediately renders with
the stale scenario name from localStorage and all derived bindings. This
creates a confusing state — the scenario chip shows a name, the graph tries
to load data for that scenario — but the backend validation hasn't completed
yet. If the scenario was deleted, the user sees errors before the silent
validation clears it. There is no visual cue that initialization is in progress.

### Target State

A semi-transparent overlay covers the entire app until the persisted scenario
validation completes. The overlay shows a spinner and status text indicating
what's happening. Once validation finishes (scenario confirmed or cleared),
the overlay fades out and the app becomes interactive.

If no scenario was persisted (`activeScenario === null` on mount), no overlay
is shown — the app renders immediately in "Custom mode".

```
┌──────────────────────────────────────────────────┐
│  ┌──────────────────────────────────────────┐    │
│  │                                          │    │
│  │       ◠ (spinner)                        │    │
│  │                                          │    │
│  │   Validating scenario "cloud-outage"…    │    │
│  │                                          │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  (app content visible but darkened underneath)   │
└──────────────────────────────────────────────────┘
```

### Backend Changes

None — the existing `/query/scenarios/saved` endpoint is sufficient.

### Frontend Changes

#### `ScenarioContext.tsx` — Add `scenarioReady` state

Add a `scenarioReady: boolean` field to the context that starts `false` when
there's a persisted scenario to validate, and becomes `true` once validation
completes (success, not-found, or error).

```tsx
// Add to ScenarioState interface:
/** Whether the initial scenario validation has completed */
scenarioReady: boolean;

// In ScenarioProvider:
const [scenarioReady, setScenarioReady] = useState<boolean>(
  () => localStorage.getItem('activeScenario') === null, // true immediately if nothing to validate
);

// Update the validation useEffect to set ready when done:
useEffect(() => {
  if (!activeScenario) return; // scenarioReady already true
  let cancelled = false;
  fetch('/query/scenarios/saved')
    .then((r) => r.json())
    .then((data) => {
      if (cancelled) return;
      const saved: string[] = (data.scenarios ?? []).map((s: { id: string }) => s.id);
      if (!saved.includes(activeScenario)) {
        console.warn(`Persisted scenario "${activeScenario}" no longer exists — clearing.`);
        setActiveScenarioRaw(null);
        localStorage.removeItem('activeScenario');
      }
    })
    .catch(() => {}) // silent — keep scenario on network error
    .finally(() => {
      if (!cancelled) setScenarioReady(true);
    });
  return () => { cancelled = true; };
}, []);

// Add to provider value:
scenarioReady,
```

#### `App.tsx` — Render overlay when `!scenarioReady`

```tsx
const { activeScenario, scenarioReady } = useScenarioContext();

// At the top of the JSX return, before other content:
{!scenarioReady && (
  <div className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm
                  flex items-center justify-center transition-opacity">
    <div className="flex flex-col items-center gap-4 text-text-secondary">
      <span className="inline-block h-8 w-8 animate-spin rounded-full
                       border-3 border-brand border-t-transparent" />
      <span className="text-sm animate-pulse">
        Validating scenario "{activeScenario}"…
      </span>
    </div>
  </div>
)}
```

> **⚠️ Implementation note:** The overlay must use `z-[100]` to sit above
> all other z-indexed elements (the context menu uses `z-50`, modals use
> `z-50`). Use `fixed inset-0` so it covers the full viewport.

> **⚠️ Implementation note:** `activeScenario` is safe to read in the
> overlay text because it's set synchronously from localStorage before
> the first render — it won't be `null` here (the overlay only shows when
> there IS a persisted scenario to validate).

### UX Enhancements

#### 1a. Fade-out transition

**Problem:** An abrupt overlay disappearance is jarring.

**Fix:** Wrap the overlay in a `framer-motion` `<AnimatePresence>` with
`exit={{ opacity: 0 }}` and `transition={{ duration: 0.3 }}`. The app
already uses `framer-motion` throughout.

#### 1b. Timeout fallback

**Problem:** If the `/query/scenarios/saved` endpoint is unreachable, the
overlay would hang indefinitely.

**Fix:** Add a `setTimeout` in the validation effect that sets
`scenarioReady = true` after 5 seconds regardless. The existing `catch`
block already keeps the scenario on network error, so the app will just
render with the stale scenario name (acceptable — better than hanging).

```tsx
const timeout = setTimeout(() => {
  if (!cancelled) setScenarioReady(true);
}, 5000);
// In cleanup: clearTimeout(timeout);
```

---

## Item 2: Remove Context Menu Color Picker

### Current State

**`GraphContextMenu.tsx`** (L53-69): The right-click context menu on graph
nodes includes a color palette section — 12 colored circle buttons under a
"Color (label)" heading. Clicking a swatch applies the color and closes the menu.

```tsx
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
```

This is **redundant** with the `ColorWheelPopover` in the toolbar, which
provides a full HSL color wheel, hex input, AND the same 12 preset swatches.

**Problem:** Two places to change node colors is confusing and adds
unnecessary UI clutter to the context menu.

### Target State

The context menu retains only the **Display Field** selector. The entire
color picker section is removed. The toolbar color wheel remains the sole
mechanism for changing node colors.

```
┌─────────────────────┐
│ node-001   Router   │   ← header (unchanged)
│─────────────────────│
│ Display Field       │
│  id                 │   ← display field selector (unchanged)
│  name               │
│  status             │
│  region             │
└─────────────────────┘
                          ← color picker section REMOVED
```

### Frontend Changes

#### `GraphContextMenu.tsx` — Remove color picker section

Delete the entire `{/* Color picker */}` block (L53-69). This is the `<div>`
with `border-t border-white/10` containing the `COLOR_PALETTE.map(...)`.

Remove `onSetColor` from the component's props interface since it's no longer
needed. Remove the `COLOR_PALETTE` import from `graphConstants`.

```tsx
// Before:
interface GraphContextMenuProps {
  menu: { x: number; y: number; node: TopologyNode } | null;
  onClose: () => void;
  onSetDisplayField: (label: string, field: string) => void;
  onSetColor: (label: string, color: string) => void;  // ← REMOVE
}

// After:
interface GraphContextMenuProps {
  menu: { x: number; y: number; node: TopologyNode } | null;
  onClose: () => void;
  onSetDisplayField: (label: string, field: string) => void;
}
```

#### Parent component — Remove `onSetColor` prop from `<GraphContextMenu>`

The parent that renders `<GraphContextMenu>` passes `onSetColor` — update
that call site to remove the prop. This is likely in `GraphTopologyViewer.tsx`
or `GraphCanvas.tsx`.

> **⚠️ Implementation note:** Verify the parent call site — search for
> `<GraphContextMenu` in the codebase to find where `onSetColor` is passed.
> The `onSetColor` callback itself should remain in the parent since the
> `ColorWheelPopover` (via `GraphToolbar`) still uses it.

---

## Implementation Phases

### Phase 1: Startup Scenario Loading Overlay

> Independent — no dependencies

**Files to modify:**
- `frontend/src/context/ScenarioContext.tsx` — add `scenarioReady` state + expose via context
- `frontend/src/App.tsx` — consume `scenarioReady`, render overlay

**Verification:**
1. Set localStorage `activeScenario` to a valid scenario name, reload the app
   → **observe** spinner overlay with "Validating scenario…" text, then fade-out
2. Set localStorage `activeScenario` to a deleted scenario name, reload
   → **observe** overlay appears, scenario is cleared, overlay fades out, chip shows "(No scenario)"
3. Clear localStorage `activeScenario`, reload
   → **observe** no overlay, app loads immediately in custom mode
4. **Kill the graph-query-api service**, set a valid scenario in localStorage, reload
   → **observe** overlay shows for ≤5 seconds, then app renders with the scenario still set (timeout fallback)

### Phase 2: Remove Context Menu Color Picker

> Independent — no dependencies

**Files to modify:**
- `frontend/src/components/graph/GraphContextMenu.tsx` — remove color picker section + `onSetColor` prop + `COLOR_PALETTE` import
- Parent of `GraphContextMenu` (find via `<GraphContextMenu` search) — remove `onSetColor` prop

**Verification:**
1. Right-click a node on the graph → **observe** context menu shows only Display Field section, no color swatches
2. Click a label's color dot in the toolbar → **observe** ColorWheelPopover still opens and works correctly
3. Change a color via the color wheel → **observe** node colors update as expected
4. **TypeScript build** (`npm run build`) passes with no errors

---

## File Change Inventory

| File | Action | Phase | Changes |
|------|--------|-------|---------|
| `frontend/src/context/ScenarioContext.tsx` | MODIFY | 1 | Add `scenarioReady` state, update validation `useEffect` to set it, expose in context value |
| `frontend/src/App.tsx` | MODIFY | 1 | Import `scenarioReady`, add overlay JSX with `AnimatePresence` |
| `frontend/src/components/graph/GraphContextMenu.tsx` | MODIFY | 2 | Remove color picker `<div>`, remove `onSetColor` prop, remove `COLOR_PALETTE` import |
| Parent of `<GraphContextMenu>` (TBD — find via search) | MODIFY | 2 | Remove `onSetColor` prop from `<GraphContextMenu>` usage |

### Files NOT Changed

- `frontend/src/hooks/useScenarios.ts` — `savedLoading` state isn't used; we use a simpler `scenarioReady` boolean directly in the context instead
- `frontend/src/components/ScenarioChip.tsx` — No changes needed; it already handles null/non-null `activeScenario` display correctly
- `frontend/src/components/graph/ColorWheelPopover.tsx` — Remains untouched; this is the color picker we're keeping
- `frontend/src/components/graph/GraphToolbar.tsx` — No changes; it owns the ColorWheelPopover trigger
- `frontend/src/components/graph/graphConstants.ts` — `COLOR_PALETTE` is still used by `ColorWheelPopover`; do NOT remove it

---

## Edge Cases & Validation

### Startup Overlay (Item 1)

**No persisted scenario:** If `localStorage.getItem('activeScenario')` returns
`null`, `scenarioReady` is initialized to `true` — overlay never shows.

**Scenario deleted between sessions:** Validation fetch returns a list that
doesn't include the persisted name → scenario is cleared, overlay dismissed.
User sees "(No scenario)" chip.

**Network error / API unreachable:** The `catch` block keeps the scenario,
and the 5-second timeout ensures the overlay dismisses. The app renders with
the stale scenario name — graph queries will fail but that's the existing
behavior when the API is down.

**Rapid navigation during overlay:** The overlay uses `fixed inset-0 z-[100]`
with pointer-events, so users cannot interact with the app during validation.
This is intentional — prevents race conditions from clicking things before
validation completes.

**Multiple mounts (React StrictMode):** The `cancelled` flag in the cleanup
function handles this correctly. Only the latest effect's result is applied.

### Context Menu Color Picker (Item 2)

**TypeScript compilation:** Removing `onSetColor` from the interface is a
breaking change for the parent component. The parent must be updated in the
same commit to remove the prop. Run `tsc --noEmit` to verify.

**`COLOR_PALETTE` still needed elsewhere:** `ColorWheelPopover.tsx` imports
`COLOR_PALETTE` from `graphConstants.ts`. Do NOT remove `COLOR_PALETTE` from
the constants file — only remove the import from `GraphContextMenu.tsx`.

---

## UX Priority Matrix

| Priority | Enhancement | Item | Effort | Impact |
|----------|------------|------|--------|--------|
| **P0** | Loading overlay with spinner + text | 1 | Small | High — eliminates startup confusion |
| **P0** | Remove context menu color swatches | 2 | Tiny | Low — reduces UI clutter |
| **P1** | Fade-out transition (AnimatePresence) | 1a | Tiny | Medium — polish |
| **P1** | 5-second timeout fallback | 1b | Tiny | Medium — prevents hang on API failure |