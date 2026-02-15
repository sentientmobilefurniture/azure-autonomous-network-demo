# Minor QOL Improvements — Implementation Plan

> **Created:** 2026-02-15
> **Last audited:** 2026-02-15 (post-audit corrections applied)
> **Status:** ✅ Implemented
> **Goal:** Make the graph visualizer scenario-aware with dynamic node colors from
> `scenario.yaml`, add a Scenario Info tab to the header for viewing scenario
> descriptions/use-cases/example questions, and extend the data generators +
> Cosmos scenario DB to store and serve this metadata end-to-end.

---

## Requirements (Original)

1. Choose colors for each node in the graph visualizer, from a color palette
2. Add a tab to header to allow you to view description of scenario and use-case inherent to it, and see some example questions
3. Add description, use-case and such, and example questions, to the data generators
4. Add this description and the example questions to the scenario db in cosmos. UI should be able to reference it.
5. Upload that description + questions as a new tarball in scenarios.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 1:** Extend scenario.yaml & generators | ✅ Done | `scenario.yaml` (×1 — telco-noc only, cloud-outage & customer-recommendation don't exist on disk), generator scripts |
| **Phase 2:** Backend — persist & serve metadata | ✅ Done | `router_scenarios.py`, `router_ingest.py`, `AddScenarioModal.tsx`, `useScenarios.ts`, `types/index.ts` |
| **Phase 3:** Dynamic graph node colors from scenario | ✅ Done | `useNodeColor.ts` (new), `GraphCanvas.tsx`, `GraphToolbar.tsx`, `GraphTooltip.tsx`, `ScenarioContext.tsx`, `GraphTopologyViewer.tsx` |
| **Phase 4:** Scenario Info tab in header | ✅ Done | `TabBar.tsx` (new), `ScenarioInfoPanel.tsx` (new), `App.tsx` |

### Deviations From Plan

| # | Plan Said | What Was Done | Rationale |
|---|-----------|---------------|-----------|
| D-1 | Modify 3 scenario.yaml files | Only modified telco-noc/scenario.yaml | cloud-outage and customer-recommendation scenario directories don't exist on disk yet |
| D-2 | ScenarioInfoPanel uses useScenarios() directly | Uses useScenarios() hook (creates own state) | Hook is stateless-per-call; scenario data loads independently. Works but may fetch twice if parent also calls useScenarios |

### Extra Work Not In Plan

- {None yet}

---

## Table of Contents

- [Requirements (Original)](#requirements-original)
- [Codebase Conventions & Context](#codebase-conventions--context)
- [Overview of Changes](#overview-of-changes)
- [Item 1: Scenario-Driven Graph Node Colors](#item-1-scenario-driven-graph-node-colors)
- [Item 2: Scenario Info Tab in Header](#item-2-scenario-info-tab-in-header)
- [Item 3: Extend Data Generators with Metadata](#item-3-extend-data-generators-with-metadata)
- [Item 4: Persist Metadata to Cosmos Scenario DB](#item-4-persist-metadata-to-cosmos-scenario-db)
- [Item 5: Include Metadata in Scenario Tarballs](#item-5-include-metadata-in-scenario-tarballs)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)

---

## Codebase Conventions & Context

### Request Routing

| URL prefix | Proxied to | Config |
|------------|-----------|--------|
| `/api/*` | API service on port **8000** | `vite.config.ts` L21-31 (dev), `nginx.conf` `/api/` block (prod) |
| `/query/*` | graph-query-api on port **8100** | `vite.config.ts` L44-53 (dev), `nginx.conf` `/query/` block (prod) |

New endpoints under `/query/*` automatically inherit proxy routing — no nginx/vite changes needed.

### Naming Conventions

| Concept | Example | Derivation |
|---------|---------|-----------|
| Scenario name | `"cloud-outage"` | `scenario.yaml` `name` field, 2–50 chars, lowercase alphanum + hyphens |
| Graph name | `"cloud-outage-topology"` | `${name}-topology` — derived in `ScenarioContext.tsx` L54 |
| Runbooks index | `"cloud-outage-runbooks-index"` | `${name}-runbooks-index` — `ScenarioContext.tsx` L55 |
| Cosmos scenario doc ID | `"cloud-outage"` | Matches scenario name, partition key `/id` |

### Import & Code Style Conventions

```tsx
// Frontend: react-resizable-panels aliases (App.tsx pattern)
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle }
  from 'react-resizable-panels';

// Frontend: Framer Motion for all transitions
import { motion, AnimatePresence } from 'framer-motion';

// Frontend: Tailwind dark theme tokens
// text-text-primary, bg-neutral-bg2, text-brand, glass-card
```

```python
# Backend: async Cosmos calls via asyncio.to_thread()
result = await asyncio.to_thread(container.upsert_item, doc)

# Backend: FastAPI router pattern
router = APIRouter(prefix="/query", tags=["scenarios"])
```

### Data Format Conventions

| Convention | Format | Where Used |
|-----------|--------|------------|
| SSE events | `event: log\ndata: ...\n\n` | `/api/config/apply`, upload endpoints |
| Scenario metadata | JSON in Cosmos `scenarios/scenarios` container, PK `/id` | `router_scenarios.py`, `useScenarios.ts` |
| Graph styles | YAML dict in `scenario.yaml` under `graph_styles.node_types` | Per-scenario, not yet consumed by frontend |
| Node color format | Hex string `"#ef4444"` | `graphConstants.ts`, `scenario.yaml`, `GraphContextMenu.tsx` |

### Key Gap: graph_styles Not Consumed by Frontend

`graphConstants.ts` hardcodes only telco-noc entity types. `scenario.yaml` defines
`graph_styles.node_types` for all three scenarios with different entity types and colors,
but **the frontend never reads this data**. This was flagged in `v7modulardata.md`
(deprecated docs) as a known gap. This plan addresses it.

---

## Overview of Changes

| # | Item | Category | Impact | Effort |
|---|------|----------|--------|--------|
| 1 | Scenario-driven graph node colors | Full-stack | **High** — currently only 1 of 3 scenarios has correct colors | Medium |
| 2 | Scenario Info tab in header | Frontend | **Medium** — improves discoverability and onboarding | Medium |
| 3 | Extend data generators with metadata | Data | **Medium** — enables items 2, 4, 5 | Small |
| 4 | Persist metadata to Cosmos scenario DB | Backend | **Medium** — enables frontend to access descriptions/questions | Small |
| 5 | Include metadata in scenario tarballs | Data/Backend | **Low** — ensures metadata travels with the scenario package | Small |

### Dependency Graph

```
Phase 1 (generators + scenario.yaml) ──┐
                                        ├──▶ Phase 2 (backend persist/serve)
                                        │         │
                                        │         ▼
                                        ├──▶ Phase 4 (Scenario Info tab — needs API)
                                        │
Phase 3 (dynamic graph colors) ─────────┘  (depends on Phase 2 for graph_styles API)
```

Phase 1 must be done first (data schema). Phase 2 depends on Phase 1 (backend
must know the new fields). Phase 3 depends on Phase 2 (frontend needs the API
to serve `graph_styles`). Phase 4 depends on Phase 2 (frontend reads
description/questions from API). Phases 3 and 4 can be parallelized after
Phase 2 is complete.

### UX Audit Summary

| Area | Finding | Severity |
|------|---------|----------|
| Graph colors | Only telco-noc has correct colors. Cloud-outage and customer-recommendation nodes all fall back to gray `#6B7280` | **High** |
| Toolbar/tooltip color dots | `GraphToolbar.tsx` and `GraphTooltip.tsx` read directly from `NODE_COLORS` and don't reflect user overrides from the context menu | Medium |
| Scenario info | No way to see scenario description, use-case, or example questions outside SettingsModal | **High** |
| Empty state guidance | `DiagnosisPanel` shows generic "Submit an alert" but doesn't suggest scenario-specific example questions | Medium |

---

## Item 1: Scenario-Driven Graph Node Colors

### Current State

Node colors are defined in `frontend/src/components/graph/graphConstants.ts` as a static
`Record<string, string>` covering **only telco-noc** entity types:

```typescript
// graphConstants.ts — current (22 lines)
export const NODE_COLORS: Record<string, string> = {
  CoreRouter:     '#38BDF8',
  AggSwitch:      '#FB923C',
  BaseStation:    '#A78BFA',
  TransportLink:  '#3B82F6',
  MPLSPath:       '#C084FC',
  Service:        '#CA8A04',
  SLAPolicy:      '#FB7185',
  BGPSession:     '#F472B6',
};
```

Color resolution in `GraphCanvas.tsx` L62:
```typescript
const color = nodeColorOverride[node.label] ?? NODE_COLORS[node.label] ?? '#6B7280';
```

This means cloud-outage types (Region, AvailabilityZone, Rack, Host, VirtualMachine,
LoadBalancer) and customer-recommendation types (CustomerSegment, Customer,
ProductCategory, Product, Campaign, Supplier, Warehouse) all render as **fallback
gray (#6B7280)**.

Each `scenario.yaml` already defines `graph_styles.node_types` with per-type colors,
sizes, and icons — but this data is never served to or consumed by the frontend.

Additionally, `GraphToolbar.tsx` L47 and `GraphTooltip.tsx` L39 read directly from
`NODE_COLORS` and **do not** respect user color overrides set via the context menu.
Note: `GraphTooltip.tsx` currently has **no fallback color** — if the label is not in
`NODE_COLORS`, the background color is `undefined` (invisible dot).

**Problem:** Two of three scenarios have visually broken graph displays with
all-gray nodes, and the context menu color overrides are inconsistently applied.

### Target State

1. When a scenario is selected, the frontend fetches `graph_styles` from the
   scenario metadata API and uses those colors/sizes as the **base defaults**
   (replacing the hardcoded `NODE_COLORS`).
2. User overrides from the context menu (persisted in localStorage) take priority.
3. The toolbar filter chips and hover tooltips also reflect the correct colors
   (either scenario-driven or user-overridden).
4. When no scenario is selected ("Custom mode"), fall back to the existing
   hardcoded `NODE_COLORS` for backwards compatibility.

```
Color resolution order (updated):
  userOverride[label]  →  scenarioStyles[label]  →  NODE_COLORS[label]  →  '#6B7280'
```

### Backend Changes

#### `graph-query-api/router_scenarios.py` — Serve `graph_styles` in scenario metadata

The saved scenario Cosmos document needs to include `graph_styles` and the new
`use_cases`/`example_questions` fields. The upload pipeline already parses
`scenario.yaml` — extend the save endpoint to accept and store these fields.

```python
# Current ScenarioSaveRequest model (router_scenarios.py L84):
class ScenarioSaveRequest(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    upload_results: dict = {}

# New — add optional fields:
class ScenarioSaveRequest(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    use_cases: list[str] | None = None
    example_questions: list[str] | None = None
    graph_styles: dict | None = None         # from scenario.yaml graph_styles
    domain: str | None = None
    upload_results: dict = {}
```

The inline document construction in `save_scenario()` (L138–157) should include
the new fields:

```python
# In save_scenario(), add to the doc dict (after the existing fields):
"use_cases": req.use_cases or [],
"example_questions": req.example_questions or [],
"graph_styles": req.graph_styles or {},
"domain": req.domain or "",
```

> **⚠️ Implementation note:** The `GET /query/scenarios/saved` endpoint returns
> full documents — no changes needed there. The new fields are automatically
> included in the response because Cosmos returns the entire document.

### Frontend Changes

#### `frontend/src/types/index.ts` — Extend `SavedScenario` type

```typescript
// Add to SavedScenario interface:
export interface SavedScenario {
  // ... existing fields ...
  graph_styles?: {
    node_types?: Record<string, { color: string; size: number; icon?: string }>;
  };
  use_cases?: string[];
  example_questions?: string[];
}
```

#### `frontend/src/context/ScenarioContext.tsx` — Add `scenarioStyles` to context

```typescript
// Add to ScenarioState interface:
interface ScenarioState {
  // ... existing fields ...
  scenarioNodeColors: Record<string, string>;
  scenarioNodeSizes: Record<string, number>;
  setScenarioStyles: (styles: { node_types?: Record<string, { color: string; size: number }> } | null) => void;
}

// In ScenarioProvider:
const [scenarioNodeColors, setScenarioNodeColors] = useState<Record<string, string>>({});
const [scenarioNodeSizes, setScenarioNodeSizes] = useState<Record<string, number>>({});

const setScenarioStyles = useCallback((styles: { ... } | null) => {
  if (styles?.node_types) {
    const colors: Record<string, string> = {};
    const sizes: Record<string, number> = {};
    for (const [type, cfg] of Object.entries(styles.node_types)) {
      colors[type] = cfg.color;
      sizes[type] = cfg.size;
    }
    setScenarioNodeColors(colors);
    setScenarioNodeSizes(sizes);
  } else {
    setScenarioNodeColors({});
    setScenarioNodeSizes({});
  }
}, []);
```

#### `frontend/src/hooks/useScenarios.ts` — Push styles on scenario select

In `selectScenario`, after setting the active scenario, look up the saved
scenario's `graph_styles` and push them into context:

```typescript
const selectScenario = useCallback(async (name: string) => {
  setActiveScenario(name);
  // Find the saved scenario to get graph_styles
  const saved = savedScenarios.find(s => s.id === name);
  if (saved?.graph_styles) {
    setScenarioStyles(saved.graph_styles);
  } else {
    setScenarioStyles(null);
  }
  // ... existing provisioning logic ...
}, [savedScenarios, setActiveScenario, setScenarioStyles, setProvisioningStatus]);
```

#### `frontend/src/components/graph/GraphCanvas.tsx` — Use scenario colors

```typescript
// Current (L61-64 — receives full node object, not just label):
const getNodeColor = useCallback(
  (node: GNode) =>
    nodeColorOverride[node.label] ?? NODE_COLORS[node.label] ?? '#6B7280',
  [nodeColorOverride],
);

// New — add scenarioNodeColors from context:
const { scenarioNodeColors } = useScenarioContext();

const getNodeColor = useCallback(
  (node: GNode) =>
    nodeColorOverride[node.label]
    ?? scenarioNodeColors[node.label]
    ?? NODE_COLORS[node.label]
    ?? '#6B7280',
  [nodeColorOverride, scenarioNodeColors],
);
```

Similarly update `getNodeSize` to use `scenarioNodeSizes`.

> **⚠️ Size scale mismatch:** `graphConstants.ts` uses sizes 5–10, but
> `scenario.yaml` uses sizes 12–30. Applying scenario sizes directly will
> render nodes 2–3× larger than current. Either normalise scenario sizes
> (divide by ~3) before passing to the canvas, or update the canvas renderer
> to handle the larger range. Without this, the graph layout will look
> significantly different when switching to scenario-driven sizes.

#### `frontend/src/components/graph/GraphToolbar.tsx` — Fix color dot consistency

```typescript
// Current (L47):
backgroundColor: NODE_COLORS[label] ?? '#6B7280'

// New — respect overrides and scenario colors:
const { scenarioNodeColors } = useScenarioContext();
// ... also accept nodeColorOverride as a prop or read from parent

backgroundColor: nodeColorOverride?.[label]
  ?? scenarioNodeColors[label]
  ?? NODE_COLORS[label]
  ?? '#6B7280'
```

#### `frontend/src/components/graph/GraphTooltip.tsx` — Fix color dot consistency

Same pattern as toolbar — use scenario colors with override precedence.

```typescript
// Current (L39 — note: no fallback color, undefined if missing):
backgroundColor: NODE_COLORS[node.label]

// New:
backgroundColor: scenarioNodeColors[node.label]
  ?? NODE_COLORS[node.label]
  ?? '#6B7280'
```

> **⚠️ Implementation note:** `GraphTooltip` doesn't currently have access
> to `nodeColorOverride`. To maintain consistency with the canvas, either
> (a) thread overrides as a prop from `GraphTopologyViewer`, or (b) create a
> `useNodeColor(label)` hook that encapsulates the full resolution chain.
> Option (b) is cleaner — it centralizes the logic and avoids prop drilling.

### UX Enhancements

#### 1a. Auto-assign colors for unknown labels

**Problem:** If a scenario has node types not defined in `graph_styles` or
`NODE_COLORS`, they fall back to gray — indistinguishable from each other.

**Fix:** Auto-assign colors from a palette based on label string hash:

```typescript
const AUTO_PALETTE = [
  '#38BDF8', '#FB923C', '#A78BFA', '#3B82F6',
  '#C084FC', '#CA8A04', '#FB7185', '#F472B6',
  '#10B981', '#EF4444', '#6366F1', '#FBBF24',
];

function autoColor(label: string): string {
  let hash = 0;
  for (const ch of label) hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
  return AUTO_PALETTE[Math.abs(hash) % AUTO_PALETTE.length];
}
```

**Why:** Custom scenarios uploaded by users may define novel entity types
not anticipated by hardcoded colors.

#### 1b. `useNodeColor` hook to centralize color resolution

**Problem:** Color resolution is duplicated across `GraphCanvas`, `GraphToolbar`,
`GraphTooltip`, and the context menu — each currently looks up colors differently.

**Fix:** Create `frontend/src/hooks/useNodeColor.ts`:

```typescript
export function useNodeColor(nodeColorOverride: Record<string, string>) {
  const { scenarioNodeColors } = useScenarioContext();

  return useCallback((label: string) =>
    nodeColorOverride[label]
    ?? scenarioNodeColors[label]
    ?? NODE_COLORS[label]
    ?? autoColor(label),
  [nodeColorOverride, scenarioNodeColors]);
}
```

> **⚠️ Implementation note:** The hook accepts `nodeColorOverride` as a parameter
> rather than reading from `localStorage` directly. `GraphTopologyViewer` already
> manages `nodeColorOverride` as React state (initialised from localStorage at L108)
> and syncs changes back to localStorage (L122). Reading localStorage independently
> would create stale state — color overrides set via the context menu wouldn't
> be reflected until the hook re-mounted.

**Why:** Single source of truth prevents color mismatches between components.

---

## Item 2: Scenario Info Tab in Header

### Current State

The header (`Header.tsx`, 65 lines) is a single 48px bar with branding, scenario chip,
health indicators, and a settings button. There is **no tab navigation** at the
app level. The app is a single-view layout with no router.

Scenario metadata (`display_name`, `description`) exists in the `SavedScenario`
type but is only visible in the SettingsModal's scenario list. There is no way for
users to quickly view what the current scenario is about, what use-cases it
demonstrates, or what questions they could ask the AI.

The DiagnosisPanel empty state shows generic text: "Submit an alert to begin
investigation" with no scenario-specific guidance.

**Problem:** New users don't know what the active scenario is about, what
use-cases to explore, or what questions to ask — they must navigate to Settings
to even see the description.

### Target State

A lightweight tab bar below the header with two tabs:
- **Investigate** (default) — the current main view (graph + investigation + diagnosis)
- **Scenario Info** — a full-width panel showing the active scenario's description,
  use-cases, and clickable example questions

```
┌─────────────────────────────────────────────────────────────────────┐
│ ◆ AI Incident Investigator   [cloud-outage ▾]   ● API  ⚙         │
├──────────┬──────────────┬───────────────────────────────────────────┤
│ ▸ Investigate │ ℹ Scenario Info │                                  │
├──────────┴──────────────┴───────────────────────────────────────────┤
│                                                                     │
│  (When "Scenario Info" tab is active:)                             │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Cloud Datacenter Outage — Cooling Cascade                  │   │
│  │                                                             │   │
│  │  A CRAC unit failure in US-East Availability Zone A         │   │
│  │  triggers cascading thermal shutdowns across 5 hosts...     │   │
│  │                                                             │   │
│  │  ── Use Cases ──────────────────────────────────────────    │   │
│  │  • Root cause analysis of cascading infrastructure failures │   │
│  │  • Blast radius assessment across availability zones        │   │
│  │  • SLA impact evaluation for affected services              │   │
│  │                                                             │   │
│  │  ── Example Questions ──────────────────────────────────    │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │  "What caused the thermal shutdown cascade?"        │ ← │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │  "Which services are impacted by the host failures?"│ ← │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │  "What is the SLA exposure for affected customers?" │ ← │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  (Clicking a question copies it to the alert input in       │   │
│  │   InvestigationPanel and switches to the Investigate tab)   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  (When no scenario selected:)                                      │
│  "Select a scenario to view its description and example questions" │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

When an example question is clicked:
1. The question text is copied to the `InvestigationPanel` alert input
2. The active tab switches to "Investigate"
3. The investigation does NOT auto-start — the user can edit the question before submitting

### Frontend Changes

#### `frontend/src/App.tsx` — Add tab state and conditional rendering

```tsx
// Add tab state:
type AppTab = 'investigate' | 'info';
const [activeTab, setActiveTab] = useState<AppTab>('investigate');

// In JSX, before the PanelGroup:
<TabBar activeTab={activeTab} onTabChange={setActiveTab} />

// Wrap main content:
{activeTab === 'investigate' ? (
  <>
    <PanelGroup orientation="vertical">
      {/* existing MetricsBar + Investigation/Diagnosis panels */}
    </PanelGroup>
    <InteractionSidebar ... />
  </>
) : (
  <ScenarioInfoPanel
    onSelectQuestion={(q) => {
      setAlert(q);           // setAlert from useInvestigation() — already in scope
      setActiveTab('investigate');
    }}
  />
)}
```

> **⚠️ Implementation note:** `InvestigationPanel` does NOT own the alert state
> — it receives `alert` and `onAlertChange` as props from `App.tsx`, where
> `setAlert` comes from `useInvestigation()`. Question insertion must use
> `setAlert(q)` directly in `App.tsx` rather than threading a `pendingAlert`
> prop into `InvestigationPanel`.

#### New: `frontend/src/components/TabBar.tsx`

A simple tab bar component matching the app's dark theme:

```tsx
interface TabBarProps {
  activeTab: 'investigate' | 'info';
  onTabChange: (tab: 'investigate' | 'info') => void;
}

export function TabBar({ activeTab, onTabChange }: TabBarProps) {
  return (
    <div className="flex border-b border-white/10 bg-neutral-bg2 px-4">
      <button
        className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
          activeTab === 'investigate'
            ? 'border-brand text-brand'
            : 'border-transparent text-text-secondary hover:text-text-primary'
        }`}
        onClick={() => onTabChange('investigate')}
      >
        ▸ Investigate
      </button>
      <button
        className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
          activeTab === 'info'
            ? 'border-brand text-brand'
            : 'border-transparent text-text-secondary hover:text-text-primary'
        }`}
        onClick={() => onTabChange('info')}
      >
        ℹ Scenario Info
      </button>
    </div>
  );
}
```

#### New: `frontend/src/components/ScenarioInfoPanel.tsx`

```tsx
interface ScenarioInfoPanelProps {
  onSelectQuestion: (question: string) => void;
}

export function ScenarioInfoPanel({ onSelectQuestion }: ScenarioInfoPanelProps) {
  const { activeScenario } = useScenarioContext();
  const { savedScenarios } = useScenarios();

  const scenario = savedScenarios.find(s => s.id === activeScenario);

  if (!activeScenario || !scenario) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-secondary">
        <div className="text-center">
          <span className="text-4xl mb-4 block">ℹ</span>
          <p>Select a scenario to view its description and example questions</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-8">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Title */}
        <div>
          <h2 className="text-2xl font-bold text-text-primary">
            {scenario.display_name || scenario.id}
          </h2>
          <p className="mt-3 text-text-secondary leading-relaxed">
            {scenario.description}
          </p>
        </div>

        {/* Use Cases */}
        {scenario.use_cases?.length && (
          <div>
            <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
              Use Cases
            </h3>
            <ul className="space-y-2">
              {scenario.use_cases.map((uc, i) => (
                <li key={i} className="flex items-start gap-2 text-text-primary">
                  <span className="text-brand mt-0.5">•</span>
                  <span>{uc}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Example Questions */}
        {scenario.example_questions?.length && (
          <div>
            <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
              Example Questions
            </h3>
            <div className="space-y-2">
              {scenario.example_questions.map((q, i) => (
                <button
                  key={i}
                  onClick={() => onSelectQuestion(q)}
                  className="w-full text-left px-4 py-3 rounded-lg
                    bg-white/5 hover:bg-white/10 border border-white/10
                    hover:border-brand/50 text-text-primary transition-all
                    group cursor-pointer"
                >
                  <span className="text-sm">"{q}"</span>
                  <span className="ml-2 text-brand opacity-0 group-hover:opacity-100
                    transition-opacity text-xs">
                    → Use this question
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

#### `frontend/src/components/InvestigationPanel.tsx` — No changes needed

`InvestigationPanel` does not own alert state. It receives `alert` and
`onAlertChange` as props from `App.tsx`. When an example question is clicked
in the Scenario Info tab, `App.tsx` calls `setAlert(q)` directly (from
`useInvestigation()`), which flows into `InvestigationPanel` via the
existing `alert` prop. No new props or effects needed.

> **⚠️ Implementation note:** The investigation does NOT auto-start —
> only the input value is set. The user must click submit.

### UX Enhancements

#### 2a. Auto-switch to Info tab when scenario changes

**Problem:** When a user selects a new scenario, they don't get any visual
feedback about what the scenario contains.

**Fix:** When `setActiveScenario` is called and the selected scenario has
`use_cases` or `example_questions`, briefly auto-switch to the Info tab.
Implement as an opt-in behavior — only switch if the user hasn't started
an investigation yet (no `steps` in the current session).

**Why:** Helps new users discover scenario context without requiring them to
manually navigate to the info tab.

#### 2b. Example questions in DiagnosisPanel empty state

**Problem:** The empty state in `DiagnosisPanel` shows generic text that
doesn't help users know what to ask.

**Fix:** When a scenario with `example_questions` is active, show 1-2
example questions as clickable suggestions below the generic prompt:

```tsx
// In DiagnosisPanel empty state (currently L23-44):
<p>Submit an alert to begin investigation</p>
{scenario?.example_questions?.slice(0, 2).map((q, i) => (
  <button key={i} onClick={() => onSelectQuestion?.(q)}
    className="text-sm text-brand/70 hover:text-brand">
    Try: "{q}"
  </button>
))}
```

**Why:** Reduces the blank-page problem — users immediately see actionable
starting points.

---

## Item 3: Extend Data Generators with Metadata

### Current State

Each `scenario.yaml` already has `name`, `display_name`, `description`,
`domain`, and `version`. It does **not** have `use_cases` or
`example_questions` fields.

The generators (`scripts/generate_topology.py`, etc.) produce CSV data files
but don't generate metadata about use-cases or example questions.

**Problem:** There's no structured data for use-cases or example questions
to surface in the UI.

### Target State

Add `use_cases` and `example_questions` arrays to each `scenario.yaml`:

```yaml
# cloud-outage/scenario.yaml — new fields
use_cases:
  - "Root cause analysis of cascading infrastructure failures"
  - "Blast radius assessment across availability zones and racks"
  - "SLA impact evaluation for affected services during thermal events"
  - "Incident timeline reconstruction from correlated alert streams"
  - "Capacity planning based on thermal resilience gaps"

example_questions:
  - "What caused the thermal shutdown cascade in US-East?"
  - "Which services are affected by the host failures in AZ-A?"
  - "What is the SLA exposure for customers depending on the affected services?"
  - "Show me the blast radius — how many VMs, hosts, and racks are impacted?"
  - "What is the timeline of alerts leading to the outage?"
  - "Are there any healthy hosts that could absorb the failed workloads?"
```

```yaml
# telco-noc/scenario.yaml — new fields
use_cases:
  - "Fibre cut incident investigation and root cause correlation"
  - "MPLS path failover analysis and traffic rerouting assessment"
  - "Enterprise service impact mapping across BGP sessions"
  - "Alert storm triage and deduplication across transport links"
  - "SLA breach risk assessment for affected customers"

example_questions:
  - "What caused the alert storm on the Sydney-Melbourne corridor?"
  - "Which enterprise services are affected by the fibre cut?"
  - "How are MPLS paths rerouting around the failed transport link?"
  - "What BGP sessions are down and what's their blast radius?"
  - "Which SLA policies are at risk of being breached?"
  - "Show me the correlation between optical power drops and service degradation"
```

```yaml
# customer-recommendation/scenario.yaml — new fields
use_cases:
  - "Recommendation model bias detection and impact analysis"
  - "Customer segment exposure assessment from model drift"
  - "Return rate anomaly investigation across product categories"
  - "A/B test comparison of recommendation model performance"
  - "Supply chain impact from recommendation-driven demand shifts"

example_questions:
  - "Why are return rates spiking across budget customer segments?"
  - "Which product categories are being incorrectly recommended?"
  - "What's the revenue impact of the model bias on high-value segments?"
  - "Show me the correlation between recommendation changes and return rates"
  - "Which campaigns are amplifying the biased recommendations?"
  - "What customer segments are most affected by the model update?"
```

### Backend Changes

No generator script changes needed — the `use_cases` and `example_questions`
fields are authored directly in `scenario.yaml` (they are editorial content,
not generated data). The generators produce CSV data; the metadata is written
by hand as part of scenario authoring.

### Files Modified

- `data/scenarios/cloud-outage/scenario.yaml` — add `use_cases` + `example_questions`
- `data/scenarios/telco-noc/scenario.yaml` — add `use_cases` + `example_questions`
- `data/scenarios/customer-recommendation/scenario.yaml` — add `use_cases` + `example_questions`

---

## Item 4: Persist Metadata to Cosmos Scenario DB

### Current State

The scenario save flow works as follows:
1. Frontend `AddScenarioModal` uploads 5 tarballs via `/query/upload/{type}`
2. After all uploads complete, frontend calls `POST /query/scenarios/save`
   with a `ScenarioSaveRequest` containing `name`, `display_name`, `description`,
   and `upload_results`
3. `router_scenarios.py` upserts the document to Cosmos `scenarios/scenarios`

The upload endpoints extract `scenario.yaml` from each tarball for name
resolution. The `display_name` and `description` from `scenario.yaml` are
passed through to the save call. But `use_cases`, `example_questions`, and
`graph_styles` are **not** extracted or forwarded.

**Problem:** Even after adding these fields to `scenario.yaml`, the upload
pipeline doesn't extract them and the frontend has no way to access them.

### Target State

1. During tarball upload (at least the graph tarball, which always includes
   `scenario.yaml`), extract `use_cases`, `example_questions`, and
   `graph_styles` from the manifest.
2. Return them in the upload response so the frontend can pass them through
   to the save endpoint.
3. Store them in the Cosmos scenario document.

Option: Parse `scenario.yaml` in the graph upload endpoint and return the
extra fields in the response. The frontend already reads the upload response
to build the save payload.

### Backend Changes

#### `graph-query-api/router_ingest.py` — Extract metadata from scenario.yaml

In the graph upload handler (which already parses `scenario.yaml` to extract
the scenario `name`), also extract the new fields:

```python
# In the graph upload handler, after parsing scenario.yaml:
manifest = yaml.safe_load(scenario_yaml_content)
scenario_name = manifest.get("name", "unknown")

# NEW — extract metadata for frontend passthrough
scenario_metadata = {
    "display_name": manifest.get("display_name"),
    "description": manifest.get("description"),
    "use_cases": manifest.get("use_cases"),
    "example_questions": manifest.get("example_questions"),
    "graph_styles": manifest.get("graph_styles"),
    "domain": manifest.get("domain"),
}
```

Include `scenario_metadata` in the SSE `complete` event payload (via
`progress.complete()`):

```python
# The graph upload returns SSE (not JSON). Metadata must be included in
# the final complete event that the frontend receives via onComplete callback.
progress.complete({
    "scenario": sc_name,
    "graph": gremlin_graph,
    "vertices": total_v,
    "edges": total_e,
    "scenario_metadata": scenario_metadata,  # NEW
})
```

> **⚠️ Implementation note:** All upload endpoints return SSE streams via
> `sse_upload_response()`, NOT JSON responses. The frontend receives data
> through `onComplete` callbacks in `uploadWithSSE()`, not as direct return
> values. The `scenario_metadata` must be embedded in the `complete` event.

#### `graph-query-api/router_scenarios.py` — Accept new fields in save body

```python
class ScenarioSaveRequest(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    use_cases: list[str] | None = None          # NEW
    example_questions: list[str] | None = None  # NEW
    graph_styles: dict | None = None            # NEW
    domain: str | None = None                   # NEW
    upload_results: dict = {}
```

In the inline doc construction within `save_scenario()` (L138–157),
include the new fields:

```python
doc = {
    "id": name,
    "display_name": display_name,
    "description": req.description,
    # ... existing fields ...
    "use_cases": req.use_cases or [],
    "example_questions": req.example_questions or [],
    "graph_styles": req.graph_styles or {},
    "domain": req.domain or "",
}
```

### Frontend Changes

#### `frontend/src/hooks/useScenarios.ts` — Forward metadata to save

In `saveScenario`, the call already passes `upload_results`. Extend it to
also forward the metadata extracted during graph upload:

```typescript
const saveScenario = useCallback(async (meta: {
  name: string;
  display_name?: string;
  description?: string;
  use_cases?: string[];           // NEW
  example_questions?: string[];   // NEW
  graph_styles?: Record<string, unknown>;  // NEW
  domain?: string;                // NEW
  upload_results: Record<string, unknown>;
}) => {
  // POST /query/scenarios/save with all fields
}, [fetchSavedScenarios]);
```

#### `frontend/src/components/AddScenarioModal.tsx` — Extract metadata from graph upload SSE response

The `AddScenarioModal` uploads tarballs sequentially using `uploadWithSSE()`,
which processes SSE streams via callbacks. The graph upload's `onComplete`
callback receives the complete event data. Store `scenario_metadata` from
that callback for use in the save call:

```typescript
// In the upload loop, when handling the graph slot's onComplete:
onComplete: (data) => {
  updateSlot(def.key, { status: 'done', result: data, progress: 'Complete', pct: 100 });
  uploadResults[def.key] = data;
  // NEW — capture metadata from graph upload complete event
  if (def.key === 'graph' && data.scenario_metadata) {
    scenarioMetadataRef.current = data.scenario_metadata;
  }
},

// When saving (after all uploads):
await saveScenarioMeta({
  name,
  display_name: scenarioMetadataRef.current?.display_name || displayName || undefined,
  description: scenarioMetadataRef.current?.description || description || undefined,
  use_cases: scenarioMetadataRef.current?.use_cases,
  example_questions: scenarioMetadataRef.current?.example_questions,
  graph_styles: scenarioMetadataRef.current?.graph_styles,
  domain: scenarioMetadataRef.current?.domain,
  upload_results: uploadResults,
});
```

> **⚠️ Implementation note:** The `Props` interface for `saveScenarioMeta` in
> `AddScenarioModal.tsx` (L64–68) must also be updated to accept the new fields,
> matching the extended `saveScenario` signature in `useScenarios.ts`.

> **⚠️ Implementation note:** Only the graph tarball is guaranteed to have
> `scenario.yaml`. The metadata extraction should happen from the graph upload
> response. If graph hasn't been uploaded yet, the metadata fields will be null.

---

## Item 5: Include Metadata in Scenario Tarballs

### Current State

Each tarball already includes `scenario.yaml` at the root for name resolution.
The `generate_all.sh` script packages specific directories per tarball type.
Since `scenario.yaml` is already included, and we're adding `use_cases` and
`example_questions` directly to `scenario.yaml` (Item 3), the metadata is
**already included in the tarballs** with no changes needed to the packaging.

**Problem:** None — this requirement is satisfied by Item 3 automatically.

### Target State

After Item 3 is implemented, every tarball for every scenario will contain:
- `scenario.yaml` with the original fields PLUS `use_cases` and
  `example_questions`

The `generate_all.sh` script already packages `scenario.yaml` into every
tarball. The only requirement is to re-run `./data/generate_all.sh` to
regenerate the tarballs with the updated `scenario.yaml` files.

### Verification

```bash
# After updating scenario.yaml files:
./data/generate_all.sh

# Verify metadata is present in tarball:
tar -xzf data/scenarios/cloud-outage-graph.tar.gz -O cloud-outage/scenario.yaml \
  | grep -A 10 "use_cases"
```

---

## Implementation Phases

### Phase 1: Extend scenario.yaml & Regenerate Tarballs

> Independent — no dependencies. **Prerequisite for Phases 2, 3, 4.**

**Files to modify:**
- `data/scenarios/cloud-outage/scenario.yaml` — add `use_cases`, `example_questions`
- `data/scenarios/telco-noc/scenario.yaml` — add `use_cases`, `example_questions`
- `data/scenarios/customer-recommendation/scenario.yaml` — add `use_cases`, `example_questions`

**Commands to run:**
- `./data/generate_all.sh` — regenerate all tarballs with updated manifests

**Verification:**
- `tar -xzf data/scenarios/cloud-outage-graph.tar.gz -O cloud-outage/scenario.yaml | grep use_cases` → shows YAML array
- `tar -xzf data/scenarios/telco-noc-graph.tar.gz -O telco-noc/scenario.yaml | grep example_questions` → shows YAML array
- All 3 scenarios × 5 tarballs each = 15 tarballs regenerated

---

### Phase 2: Backend — Persist & Serve Scenario Metadata

> Depends on Phase 1. **Prerequisite for Phases 3 and 4.**

**Files to modify:**
- `graph-query-api/router_scenarios.py` — extend `ScenarioSaveRequest` with `use_cases`, `example_questions`, `graph_styles`, `domain`; include in inline doc construction within `save_scenario()`
- `graph-query-api/router_ingest.py` — extract metadata from `scenario.yaml` in graph upload handler; include `scenario_metadata` in SSE `complete` event

**Verification:**
- Upload a scenario via the UI → check graph upload SSE `complete` event includes `scenario_metadata` with non-null `use_cases` and `example_questions`
- After save, `GET /query/scenarios/saved` returns documents with `use_cases`, `example_questions`, and `graph_styles` fields populated
- Verify existing scenarios (without new fields) still load correctly (fields default to `[]`/`{}`)

---

### Phase 3: Frontend — Dynamic Graph Node Colors

> Depends on Phase 2 (needs `graph_styles` in saved scenario data).

**Files to create:**
- `frontend/src/hooks/useNodeColor.ts` — centralized color resolution hook (~30 lines)

**Files to modify:**
- `frontend/src/types/index.ts` — add `graph_styles?`, `use_cases?`, `example_questions?` to `SavedScenario`
- `frontend/src/context/ScenarioContext.tsx` — add `scenarioNodeColors`, `scenarioNodeSizes`, `setScenarioStyles` to context
- `frontend/src/hooks/useScenarios.ts` — push `graph_styles` into context on scenario select
- `frontend/src/components/graph/GraphCanvas.tsx` — use `useNodeColor` hook instead of direct `NODE_COLORS` lookup
- `frontend/src/components/graph/GraphToolbar.tsx` — use `useNodeColor` hook for chip dot colors
- `frontend/src/components/graph/GraphTooltip.tsx` — use `useNodeColor` hook for tooltip dot
- `frontend/src/components/GraphTopologyViewer.tsx` — pass `scenarioNodeSizes` to `GraphCanvas`

**Verification:**
- Select "cloud-outage" scenario → graph nodes use cloud-outage colors (red Region, orange AvailabilityZone, etc.) instead of all-gray
- Select "customer-recommendation" → nodes use e-commerce colors
- Select "telco-noc" → nodes use scenario.yaml telco colors (note: these differ from the old hardcoded `graphConstants.ts` colors — e.g. CoreRouter changes from `#38BDF8` to `#60a5fa`)
- Right-click a node → change its color → toolbar chip and tooltip show the override color
- Deselect scenario ("Custom mode") → nodes revert to hardcoded `NODE_COLORS` (telco-noc defaults)
- **Labels not in any color map** → auto-assigned from palette (not gray)

---

### Phase 4: Frontend — Scenario Info Tab

> Depends on Phase 2 (needs `use_cases`/`example_questions` in saved scenario data).
> Can be implemented in parallel with Phase 3.

**Files to create:**
- `frontend/src/components/TabBar.tsx` — tab bar component (~35 lines)
- `frontend/src/components/ScenarioInfoPanel.tsx` — info panel component (~90 lines)

**Files to modify:**
- `frontend/src/App.tsx` — add tab state, `TabBar`, conditional rendering, call `setAlert(q)` directly on question select
- `frontend/src/components/InvestigationPanel.tsx` — no changes needed (alert state owned by `App.tsx` via `useInvestigation()`)

**Verification:**
- Two tabs visible below header: "▸ Investigate" (active) and "ℹ Scenario Info"
- Click "Scenario Info" → shows active scenario description, use-cases list, clickable example questions
- Click an example question → tab switches to "Investigate", question appears in alert input
- Investigation does NOT auto-start — user must click submit
- No scenario selected → info tab shows "Select a scenario..." empty state
- Tab state does NOT persist across page refreshes (always starts on "Investigate")
- **Existing functionality not broken** — all investigation flows work identically when on the Investigate tab

---

## File Change Inventory

| File | Action | Phase | Changes |
|------|--------|-------|---------|
| `data/scenarios/cloud-outage/scenario.yaml` | MODIFY | 1 | Add `use_cases` + `example_questions` arrays (~15 lines) |
| `data/scenarios/telco-noc/scenario.yaml` | MODIFY | 1 | Add `use_cases` + `example_questions` arrays (~15 lines) |
| `data/scenarios/customer-recommendation/scenario.yaml` | MODIFY | 1 | Add `use_cases` + `example_questions` arrays (~15 lines) |
| `graph-query-api/router_scenarios.py` | MODIFY | 2 | Extend `ScenarioSaveRequest` + inline doc construction in `save_scenario()` with 4 new fields |
| `graph-query-api/router_ingest.py` | MODIFY | 2 | Extract `scenario_metadata` from manifest in graph upload; include in SSE `complete` event |
| `frontend/src/types/index.ts` | MODIFY | 3 | Add `graph_styles?`, `use_cases?`, `example_questions?` to `SavedScenario` |
| `frontend/src/context/ScenarioContext.tsx` | MODIFY | 3 | Add `scenarioNodeColors`, `scenarioNodeSizes`, `setScenarioStyles` |
| `frontend/src/hooks/useScenarios.ts` | MODIFY | 3 | Push `graph_styles` into context on select; extend `saveScenario` signature |
| `frontend/src/hooks/useNodeColor.ts` | **CREATE** | 3 | Centralized color resolution hook (~30 lines) |
| `frontend/src/components/graph/GraphCanvas.tsx` | MODIFY | 3 | Replace `NODE_COLORS` lookup with `useNodeColor` hook |
| `frontend/src/components/graph/GraphToolbar.tsx` | MODIFY | 3 | Replace `NODE_COLORS` lookup with `useNodeColor` hook |
| `frontend/src/components/graph/GraphTooltip.tsx` | MODIFY | 3 | Replace `NODE_COLORS` lookup with `useNodeColor` hook |
| `frontend/src/components/GraphTopologyViewer.tsx` | MODIFY | 3 | Pass scenario sizes to `GraphCanvas` |
| `frontend/src/components/TabBar.tsx` | **CREATE** | 4 | Tab bar component (~35 lines) |
| `frontend/src/components/ScenarioInfoPanel.tsx` | **CREATE** | 4 | Scenario info panel with clickable questions (~90 lines) |
| `frontend/src/App.tsx` | MODIFY | 4 | Add tab state, TabBar, conditional rendering, `setAlert(q)` on question select |
| `frontend/src/components/InvestigationPanel.tsx` | — | 4 | No changes needed — alert state owned by `App.tsx` |
| `frontend/src/components/AddScenarioModal.tsx` | MODIFY | 2 | Extract `scenario_metadata` from graph upload SSE `onComplete` callback; update `saveScenarioMeta` Props type to accept new fields |

### Files NOT Changed

- `frontend/src/components/graph/graphConstants.ts` — **kept as fallback**. Still used as the default color map when no scenario is selected. Not deleted.
- `frontend/src/components/graph/GraphContextMenu.tsx` — color picker palette stays as-is. The 12 hardcoded colors are appropriate for user overrides regardless of scenario.
- `frontend/src/components/Header.tsx` — no changes. The tab bar is below the header, not inside it.
- `frontend/src/components/SettingsModal.tsx` — no changes. Scenario metadata in settings is out of scope.
- `frontend/src/main.tsx` — no changes. No new providers needed.
- `data/generate_all.sh` — no changes to the script itself. Only needs to be re-run after scenario.yaml updates.
- `graph-query-api/router_ingest.py` (telemetry/runbooks/tickets/prompts upload handlers) — no changes. Only the graph upload handler extracts metadata.
- `nginx.conf`, `vite.config.ts` — no proxy changes needed. All new data flows through existing endpoints.

---

## Cross-Cutting UX Gaps

### Gap 1: graphConstants.ts Only Covers Telco-NOC Types

**Current state:** The hardcoded `NODE_COLORS` and `NODE_SIZES` in `graphConstants.ts`
only define 8 telco-noc entity types. Other scenarios' node types fall back to gray.

**Where this matters for the current plan:** Item 1 (dynamic colors) directly
addresses this. After Phase 3, scenario-driven colors replace the need for
per-type hardcoding.

**Recommendation:** Keep `graphConstants.ts` as a fallback for "Custom mode"
(no scenario selected). In a future iteration, consider making `graphConstants.ts`
merge all known scenario colors, or remove it entirely in favour of a
`DEFAULT_NODE_COLORS` extracted from all scenarios.

**Scope:** Addressed in this plan (Phase 3).

### Gap 2: Color Override Inconsistency

**Current state:** User color overrides (from the context menu, stored in
localStorage as `'graph-colors'`) are applied in `GraphCanvas.tsx` but NOT
reflected in `GraphToolbar.tsx` chip dots or `GraphTooltip.tsx` tooltip dots.

**Where this matters for the current plan:** Item 1 introduces the `useNodeColor`
hook that centralizes all color resolution. This naturally fixes the inconsistency.

**Recommendation:** The `useNodeColor` hook accepts `nodeColorOverride` as a
parameter (from `GraphTopologyViewer`'s React state) and resolves through
scenario colors, hardcoded fallbacks, and auto-palette in that order.

**Scope:** Addressed in this plan (Phase 3, Enhancement 1b).

---

## UX Priority Matrix

| Priority | Enhancement | Item | Effort | Impact |
|----------|------------|------|--------|--------|
| **P0** | Scenario-driven node colors | 1 | Medium | **High** — 2 of 3 scenarios have broken visuals |
| **P0** | Scenario Info tab with clickable questions | 2 | Medium | **High** — core onboarding UX |
| **P0** | Backend metadata persistence | 4 | Small | **High** — enables all frontend features |
| **P1** | `useNodeColor` hook (centralized resolution) | 1 | Small | Medium — eliminates color inconsistency bug |
| **P1** | Auto-assign colors for unknown labels | 1 | Tiny | Medium — future-proofs custom scenarios |
| **P1** | Example questions in DiagnosisPanel empty state | 2 | Tiny | Medium — reduces blank-page anxiety |
| **P2** | Auto-switch to Info tab on new scenario | 2 | Tiny | Low — nice discovery UX |
| **P3** | Scenario-driven node sizes | 1 | Small | Low — sizes are less impactful than colors |
| **Backlog** | Remove `graphConstants.ts` entirely | 1 | Small | Low — cleanup only |

### Implementation Notes

- **P0 items** are the core deliverables and should be implemented in Phases 1-4.
- **P1 items** are small additions that should be included in their respective
  phases as they prevent inconsistencies or improve UX with minimal effort.
- **P2 items** are optional polish that can be added if time permits.
- **P3 items** can be deferred to a future iteration.

---

## Edge Cases & Validation

### Scenario-Driven Graph Colors (Item 1)

**No scenario selected ("Custom mode"):** Falls back to `NODE_COLORS` from
`graphConstants.ts`. This is the current behaviour and remains unchanged.
Verified by: select "✦ Custom mode" → graph uses telco-noc hardcoded colors.

**Scenario without `graph_styles`:** If a saved scenario document has no
`graph_styles` field (e.g., older scenarios saved before this feature),
`scenarioNodeColors` will be empty `{}` and fall through to `NODE_COLORS`
then auto-palette. No error thrown.

**User override + scenario color conflict:** The override always wins.
If the user overrides CoreRouter to red, and then switches to a scenario
where CoreRouter is blue, the override (red) persists. This is intentional —
overrides are per-label across scenarios (stored globally in localStorage).
Clear overrides: right-click → reset color.

**Label not in any map:** Auto-assigned from the 12-color palette using a
stable string hash. The same label always gets the same color. Worst case:
two labels hash to the same palette index — acceptable for an auto-assign.

**Large number of unique labels:** The 12-color auto-palette wraps around.
With >12 unique unknown labels, some will share colors. This is acceptable —
users can override via the context menu for disambiguation.

### Scenario Info Tab (Item 2)

**Scenario with no `use_cases`/`example_questions`:** Shows title and
description only. The "Use Cases" and "Example Questions" sections are
conditionally rendered. No empty section headers shown.

**Very long description:** The panel scrolls (`overflow-y-auto`). No
truncation — full description is shown.

**Very long example question text:** Wraps within the button container.
Max width is constrained by `max-w-3xl` wrapper.

**Clicking question while investigation is running:** The question is set
in the input field but the running investigation is NOT interrupted. The user
sees the previous investigation complete and can then submit the new question.

**Tab state on page refresh:** Always resets to "Investigate". Tab state is
not persisted to localStorage (intentional — investigation is the primary
view).

### Metadata Persistence (Item 4)

**Graph tarball uploaded without `use_cases` in scenario.yaml:** The
`scenario_metadata` in the SSE `complete` event will have `use_cases: null`.
The save endpoint defaults to `[]`. No error.

**Non-graph tarballs uploaded first:** Only the graph upload extracts
`scenario_metadata`. If runbooks or tickets are uploaded before graph,
metadata won't be available until graph is uploaded. The save call at the
end includes whatever metadata was extracted. Order doesn't matter as long
as graph is uploaded at some point before save.

**Cosmos document already exists (re-upload):** The `upsert_item` call
in `router_scenarios.py` replaces the entire document. New fields overwrite
old ones. If a re-upload doesn't include metadata (e.g., manual API call
without these fields), fields default to `[]`/`{}` — the data is not
"lost" from the tarball, only from Cosmos until the next upload.

---

## Migration & Backwards Compatibility

### Existing Data

**Existing scenario documents in Cosmos** lack `use_cases`, `example_questions`,
and `graph_styles` fields. The frontend handles this gracefully:

- `SavedScenario` types mark all new fields as optional (`?`)
- `ScenarioInfoPanel` conditionally renders sections only when arrays are non-empty
- `useNodeColor` falls through to `NODE_COLORS` → auto-palette when no scenario styles exist
- No migration script needed — existing documents work as-is

To populate existing scenarios with the new metadata, simply re-upload them
using tarballs generated from the updated `scenario.yaml` files. The upsert
will add the new fields.

### API Surface Compatibility

All changes are **additive**:
- `ScenarioSaveRequest` gains 4 new optional fields (default `None`)
- Graph upload SSE `complete` event gains `scenario_metadata` (new key, existing consumers ignore it)
- `GET /query/scenarios/saved` response includes new fields if present (existing consumers ignore unknown keys)

**No breaking changes.** Old frontends work with new backends and vice versa.

### Gradual Adoption

Each phase is independently deployable:
- Phase 1 alone: scenario.yaml files are updated, tarballs regenerated. No visible change until Phase 2+.
- Phase 1+2: backend accepts and serves metadata. No visible frontend change until Phase 3+4.
- Phase 1+2+3: graph colors work correctly for all scenarios. Info tab not yet visible.
- Full (1+2+3+4): complete feature set.

### Rollback Plan

**Phase 4 (tab bar):** Remove `TabBar` and `ScenarioInfoPanel`, revert `App.tsx`.
No data impact.

**Phase 3 (dynamic colors):** Remove `useNodeColor` hook, revert to direct
`NODE_COLORS` lookups. Graph reverts to hardcoded telco-noc colors.

**Phase 2 (backend):** Optional fields in `ScenarioSaveRequest` can be ignored. Extra
fields in Cosmos documents are harmless (JSON is schema-free).

**Phase 1 (scenario.yaml):** Extra YAML fields are ignored by the existing
pipeline. No rollback needed.

No feature flags required. All changes are backwards-compatible and can be
reverted independently.