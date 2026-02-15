# v9.5 Minor Frontend Fixes

## Issues

1. Where is the node color selector? I don't see it.
2. Scenario info shows nothing even when the latest scenario with expanded yaml is loaded.
3. Where are the example questions? Can we have them in a dropdown selection box?

---

## UX Analysis

### Current flow

```
Header: [◆ AI Incident Investigator] [ScenarioChip ▾] ... [⚙]
TabBar: [▸ Investigate] [ℹ Scenario Info]
┌────────────── Investigate tab ──────────────┐
│ ┌──────────────────┬───────────────────────┐ │
│ │ MetricsBar (top)                        │ │
│ │  ┌─ GraphTopologyViewer ─┬─ Logs ─────┐ │ │
│ │  │ Toolbar: chips, search│            │ │ │
│ │  │ <canvas>              │ API / Graph│ │ │
│ │  └───────────────────────┴────────────┘ │ │
│ ├──────────────────┬───────────────────────┤ │
│ │ InvestigationPanel│ DiagnosisPanel       │ │
│ │  [Submit Alert]   │                      │ │
│ │  <textarea>       │ (diagnosis output)   │ │
│ │  [Investigate]    │                      │ │
│ │  AgentTimeline    │                      │ │
│ └──────────────────┴───────────────────────┘ │
└─────────────────────────────────────────────┘
```

**Problem 1 — Color selector is invisible.** The color picker only exists
inside `GraphContextMenu` (right-click a node → scroll to "Color" section).
No visual hint anywhere that right-click does anything. The toolbar label
chips already have colored dots — users look at them and think "decorative."

**Problem 2 — Scenario Info tab is always empty.** `ScenarioInfoPanel`
creates a fresh `useScenarios()` hook (blank `savedScenarios = []`) and
never calls `fetchSavedScenarios()`. The `find()` always returns
`undefined` → permanent empty state.

**Problem 3 — Example questions are buried.** They only appear on the
(broken) Scenario Info tab as clickable cards. Even if the tab worked,
the user discovers them only by switching tabs. The question cards look
nice, but they're in the wrong place — users need them at the moment of
input, not on a reference tab.

---

## Plan

### Fix 1: Make color selector discoverable from the toolbar

**The right interaction: click the dot, not the label.**

The toolbar label chips already have a colored `●` dot next to each label
name. Two distinct targets, two distinct actions:

| Target | Click action |
|--------|-------------|
| Label text | Toggle visibility filter (existing behavior) |
| Color dot `●` | Open inline color-palette popover |

This requires no new UI elements — the dot is already there. We just need
to: (a) make it a separate click target, (b) show a popover with the
12-color palette on click, (c) add `cursor-pointer` + subtle hover scale
to the dot as affordance.

**Popover: color wheel + hex input.**

Clicking the dot opens a `ColorWheelPopover` anchored below it:
- **HSL color wheel** — a circular hue ring with a brightness/saturation
  square inside (classic Photoshop-style picker). Pure CSS + canvas,
  no dependencies.
- **Hex input** — text field below the wheel showing the current hex
  code (e.g. `#38BDF8`). User can type/paste any hex value directly.
- **Preset swatches** — row of the 12 `COLOR_PALETTE` colors below the
  hex input for quick picks (same grid from `GraphContextMenu`)
- **Live preview** — the dot in the toolbar updates color in real-time
  as the user drags on the wheel or types hex
- Click a preset swatch or press Enter on hex input → applies + closes
- Click anywhere outside → closes (reverts if not committed)
- Current color gets a white checkmark ring in the preset row

**Why not just a swatch grid?**
- Hex input lets power users paste brand colors exactly
- Color wheel gives full spectrum access, not just 12 presets
- Presets still there for quick one-click picks

**Files:**
- New: [ColorWheelPopover.tsx](frontend/src/components/graph/ColorWheelPopover.tsx) — self-contained color wheel + hex input + preset swatch row
- [GraphToolbar.tsx](frontend/src/components/graph/GraphToolbar.tsx) — split label chip into two click targets (text + dot), add `onSetColor` prop, render `ColorWheelPopover` when a dot is clicked
- [GraphTopologyViewer.tsx](frontend/src/components/GraphTopologyViewer.tsx) — pass `setNodeColorOverride` as `onSetColor` to `GraphToolbar`
- Extract `COLOR_PALETTE` to [graphConstants.ts](frontend/src/components/graph/graphConstants.ts) so both `GraphContextMenu`, `GraphToolbar`, and `ColorWheelPopover` share it

**Scope:** ~120 lines (mostly the new popover component). No new dependencies — canvas API for the wheel.

---

### Fix 2: Scenario info panel loads data

**Bug fix — one missing `useEffect`.**

`ScenarioInfoPanel` calls `useScenarios()` which starts with
`savedScenarios = []`. Nobody ever calls `fetchSavedScenarios()`.

**Fix:** Add `useEffect(() => { fetchSavedScenarios(); }, [])` in
`ScenarioInfoPanel`. That's it.

**Files:**
- [ScenarioInfoPanel.tsx](frontend/src/components/ScenarioInfoPanel.tsx) — import `useEffect`, add mount-fetch effect

**Scope:** 4 lines added.

---

### Fix 3: Example questions as suggestion chips on the investigate tab

**Not a `<select>` — suggestion chips, like ChatGPT.**

A native `<select>` dropdown is the wrong pattern here:
- Can't style it in dark theme without a custom component anyway
- Long questions get truncated in `<select>` options
- Semantically, a `<select>` is for choosing a *setting*, not for
  populating free-text input

**Better pattern: suggestion chips.** Compact pill buttons that appear
inside the `AlertInput` card, between the textarea and the submit button,
only when:
1. The textarea is **empty** (chips disappear once user types — saves space)
2. A scenario is active and has `example_questions`

Clicking a chip populates the textarea. The user can edit it before
submitting, or just hit Investigate immediately.

**Visual design:**
```
┌─ glass-card ──────────────────────────────────┐
│ SUBMIT ALERT                                  │
│ ┌────────────────────────────────────────────┐│
│ │ Paste a NOC alert...                       ││
│ └────────────────────────────────────────────┘│
│                                               │
│ Try an example:                               │
│ ┌──────────────────────┐ ┌─────────────────┐  │
│ │ "What caused the     │ │ "Show me all    │  │
│ │  regional outage?"   │ │  affected nodes"│  │
│ └──────────────────────┘ └─────────────────┘  │
│ ┌──────────────────────────────────────────┐  │
│ │ "Which customers are impacted by the     │  │
│ │  backbone failure?"                      │  │
│ └──────────────────────────────────────────┘  │
│                                               │
│ [            Investigate            ]         │
└───────────────────────────────────────────────┘
```

- Chips: `bg-white/5 border border-white/10 hover:border-brand/40`
  (matches existing ScenarioInfoPanel question card styling)
- Text: `text-xs text-text-secondary`
- Label: `text-[10px] uppercase tracking-wider text-text-muted`
  (matches existing "SUBMIT ALERT" label styling)
- Max 2 rows visible, rest accessible via horizontal scroll or wrap

**Files:**
- [AlertInput.tsx](frontend/src/components/AlertInput.tsx) — add optional `exampleQuestions?: string[]` prop, render suggestion chips when `alert` is empty and questions exist
- [InvestigationPanel.tsx](frontend/src/components/InvestigationPanel.tsx) — add `exampleQuestions` prop, source it from scenario context/hook
- [App.tsx](frontend/src/App.tsx) — pass example questions through (or let `InvestigationPanel` self-source from context)

**Scope:** ~35 lines. No new dependencies.

---

## Execution Order

1. **Fix 2** first — 4-line bug fix, unblocks scenario data everywhere
2. **Fix 3** — suggestion chips on investigate tab (depends on scenario data)
3. **Fix 1** — color dot popover on toolbar (independent)