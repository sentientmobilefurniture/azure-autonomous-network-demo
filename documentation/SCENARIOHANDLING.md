# Scenario Management — Implementation Plan

> **Created:** 2026-02-15  
> **Last audited:** 2026-02-15  
> **Implemented:** 2026-02-15  
> **Status:** ✅ Phases 1-3 Complete · Phase 4 Partial  
> **Goal:** Let users create, save, and switch between complete scenarios from the UI — one form to name a scenario, upload all 5 tarballs, and persist it. Selecting a saved scenario auto-configures all agents and data sources.

---

## Implementation Status

| Phase | Status | Files |
|-------|--------|-------|
| **Phase 1:** Foundation — Backend + Shared Utils + Context | ✅ Complete | `router_scenarios.py` (new), `main.py`, `router_ingest.py`, `sseStream.ts` (new), `ScenarioContext.tsx`, `types/index.ts`, `useScenarios.ts` |
| **Phase 2:** Add Scenario Form + Settings Restructure | ✅ Complete | `AddScenarioModal.tsx` (new), `SettingsModal.tsx` |
| **Phase 3:** Header Integration + Scenario Selection | ✅ Complete | `ScenarioChip.tsx` (new), `ProvisioningBanner.tsx` (new), `Header.tsx` |
| **Phase 4:** Polish & Edge Cases | 🔶 Partial | See [Phase 4 Status](#phase-4-polish--edge-cases) below |

### Deviations From Plan

6 minor deviations were made during implementation:

| # | Plan Said | What Was Done | Rationale |
|---|-----------|---------------|----------|
| D-1 | Use `@microsoft/fetch-event-source` for SSE in `selectScenario` | Used native `fetch()` + `ReadableStream` via shared `consumeSSE()` utility | Plan's UX-11 explicitly specifies extracting the *existing* native `ReadableStream` pattern. The `fetchEventSource` reference in the pseudocode contradicts UX-11. Native fetch works correctly with POST + SSE. |
| D-2 | `selectScenario` calls `setActiveScenario` AND all 4 individual setters | Calls only `setActiveScenario(name)` | `setActiveScenario()` already auto-derives all 4 bindings when name is non-null. Individual calls would be redundant. |
| D-3 | Rename runbooks/tickets `scenario` param to `scenario_name` | Kept old `scenario` param AND added `scenario_name`; `scenario_name` takes priority | Backwards compatibility — removing `scenario` would break existing callers/scripts. Priority inversion achieves the plan's behavioral goal. |
| D-4 | `ProvisioningStatus` type in `types/index.ts` | Defined and exported from `ScenarioContext.tsx` | Tightly coupled to `ScenarioState` context interface. Co-locating avoids circular dependency. Type is still exported and available. |
| D-5 | SSE complete-event detection via `event:` type markers | Heuristic field-checking (`scenario`, `index`, `graph`, `prompts_stored` keys) | Backend SSE streams don't use `event:` markers — only `data:` lines. Heuristic matches existing backend behavior. |
| D-6 | Auto-clear setTimeout guards against race conditions | Unconditional `setProvisioningStatus({ state: 'idle' })` after 3s | TypeScript constraint — `setProvisioningStatus` accepts `ProvisioningStatus`, not an updater function. Low practical risk (provisioning takes ~30s). |

### Extra Work Not In Plan

- **Bug fix:** Added missing `COSMOS_GREMLIN_GRAPH` import in `router_ingest.py` (variable used at line 639 but never imported from `config.py`)
- **`uploadWithSSE()` helper:** Added convenience wrapper in `sseStream.ts` combining FormData + fetch + consumeSSE — reduces boilerplate in AddScenarioModal
- **`ProvisioningStatus` as discriminated union:** `{ state: 'idle' } | { state: 'provisioning'; step; scenarioName } | ...` — better TypeScript narrowing than a flat interface

---

## Table of Contents

- [Current State](#current-state)
- [Target State](#target-state)
- [UX Audit & Improvements](#ux-audit--improvements)
- [Naming Convention](#naming-convention)
- [Cosmos DB "scenarios" Registry](#cosmos-db-scenarios-registry)
- [Backend Changes](#backend-changes)
- [Frontend Changes](#frontend-changes)
- [Scenario Selection & Agent Reprovisioning](#scenario-selection--agent-reprovisioning)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)

---

## Current State

Today users perform **6 manual steps** to load a scenario:

1. Generate 5 tarballs via `./data/generate_all.sh`
2. Open Settings → Upload tab → upload each tarball one by one
3. Switch to Data Sources tab → pick graph from dropdown
4. Pick runbooks index, tickets index, prompt set from separate dropdowns
5. Click "Load Topology"
6. Click "Provision Agents"

Each upload is independent — the UI has no concept of a "scenario" as a first-class
object. There's no saved state of "which files belong together." Users must mentally
track which graph goes with which indexes and which prompts.

### Current Resource Naming (Already Correct)

Each upload endpoint reads `scenario.yaml` from the tarball and derives the scenario
name. Resources are already named per-scenario:

| Data Type | Current Resource Name |
|-----------|----------------------|
| Graph | `{name}-topology` (Gremlin graph inside shared `networkgraph` database) |
| Telemetry | `{name}-telemetry` (NoSQL database with containers per `scenario.yaml`) |
| Runbooks | Blob: `{name}-runbooks` → Index: `{name}-runbooks-index` |
| Tickets | Blob: `{name}-tickets` → Index: `{name}-tickets-index` |
| Prompts | Database: `{name}-prompts`, container: `prompts`, PK: `/agent` |

This naming is already consistent. The new feature wraps these uploads in a
single atomic workflow and persists metadata.

---

## Target State

### User Flow

1. Open Settings → click **"+Add Scenario"** button
2. Form appears with:
   - Scenario name text input (required, used for resource naming)
   - 5 file upload slots (Graph, Telemetry, Runbooks, Tickets, Prompts — all required)
   - **"Save Scenario"** button (disabled until name + all 5 files are provided)
3. Click "Save Scenario":
   - Uploads all 5 tarballs sequentially via existing endpoints
   - On success, saves scenario metadata document to `scenarios` database in Cosmos NoSQL
   - If a scenario with the same name already exists, **overrides it** (upsert)
   - Progress shown for each upload step
4. Saved scenarios appear in a **scenario dropdown** in the Data Sources tab (or Header)
5. Selecting a scenario from the dropdown:
   - Sets `activeGraph` to `{name}-topology`
   - Sets `activeRunbooksIndex` to `{name}-runbooks-index`
   - Sets `activeTicketsIndex` to `{name}-tickets-index`
   - Sets `activePromptSet` to `{name}`
   - Auto-triggers **agent reprovisioning** with these bindings
   - Updates `X-Graph` header for graph explorer and telemetry explorer

### What "Select a Scenario" Does Concretely

```
User selects "cloud-outage" from dropdown
  → activeGraph = "cloud-outage-topology"
  → activeRunbooksIndex = "cloud-outage-runbooks-index"  
  → activeTicketsIndex = "cloud-outage-tickets-index"
  → X-Graph header = "cloud-outage-topology" (graph queries + telemetry derivation)
  → POST /api/config/apply {
      graph: "cloud-outage-topology",
      runbooks_index: "cloud-outage-runbooks-index",
      tickets_index: "cloud-outage-tickets-index",
      prompt_scenario: "cloud-outage"
    }
  → 5 agents reprovisioned with correct prompts, search indexes, and OpenAPI X-Graph enum
```

---

## UX Audit & Improvements

> Audit performed 2026-02-15 after reading the full architecture, the current
> `SettingsModal.tsx` (541 lines), `ScenarioContext.tsx` (53 lines),
> `useScenarios.ts` (133 lines), `Header.tsx` (42 lines), and `types/index.ts` (18 lines).

### Summary Verdict

The backend plan is strong — naming conventions, Cosmos schema, endpoint design,
edge-case handling, and phasing are all well-specified. The frontend plan has the
right *structure* but under-specifies the actual user experience. Below are specific
improvements that together turn a "functional" scenario manager into an excellent one.

---

### UX-1: Promote Active Scenario to the Header Bar

**Problem:** The plan puts the scenario dropdown *inside* the SettingsModal on the
Data Sources tab. Users must click Settings ⚙ → Data Sources tab → find dropdown
every time they want to switch scenarios. This is buried — switching scenarios is
the most important action after the initial setup.

**Fix:** Add a compact **scenario selector chip** directly in the `Header.tsx` bar,
between the title and the HealthDot. This shows the currently active scenario at all
times and allows one-click switching without opening Settings.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◆ AI Incident Investigator     ▾ cloud-outage ▾     ● API  ● 5 Agents ⚙│
└──────────────────────────────────────────────────────────────────────────┘
                                  ↑
                         Scenario selector chip
                         (dropdown on click)
                         Shows "(No scenario)" when null
```

**Implementation:** New `ScenarioChip.tsx` component (~50 lines):
- Renders `activeScenario ?? "(No scenario)"` as a pill/chip
- Click opens a flyout dropdown listing saved scenarios + "(Custom)" option
- Selecting a scenario triggers `selectScenario(name)` from context
- While provisioning runs (~30s), shows a small spinner inside the chip
- The bottom of the flyout has a `+ New Scenario` link that opens `AddScenarioModal`

The Data Sources tab in SettingsModal *also* keeps its full scenario dropdown with
detailed bindings — that's the "advanced view". The Header chip is the "quick switch".

**New file:** `frontend/src/components/ScenarioChip.tsx`  
**Modified:** `Header.tsx` — add `<ScenarioChip />` between title and controls

---

### UX-2: Active Scenario Indicator — Always Visible

**Problem:** Once a scenario is selected and Settings is closed, the user has no
visual confirmation of which scenario/data sources are active. The plan's current
Header shows a hardcoded "5 Agents" string.

**Fix:** Replace the hardcoded "5 Agents" badge with a dynamic status that shows:
- Scenario name (from `activeScenario` in context)
- Agent status: "5 Agents ✓" when provisioned, "Provisioning..." when in progress,
  "Not configured" when null
- A subtle colored ring on the `⚙` icon when scenario is active (green) vs not (amber)

This gives constant at-a-glance feedback without opening any modal.

---

### UX-3: Redesign Settings to 3 Tabs — Scenarios | Data Sources | Upload

**Problem:** The plan adds scenario features to the existing 2-tab layout (Data Sources |
Upload). The "+Add Scenario" button and the scenario dropdown both live on the Data
Sources tab, which is already dense with 5 agent binding sections + 2 action buttons.
This will be cluttered.

**Fix:** Add a dedicated **Scenarios** tab as the first tab:

```
┌──────────────────────────────────────────────────────┐
│  Settings                                        ✕   │
│  ┌────────────┐ ┌──────────────┐ ┌────────┐          │
│  │ Scenarios ◄│ │ Data Sources │ │ Upload │          │
│  └────────────┘ └──────────────┘ └────────┘          │
```

**Scenarios tab contents:**

```
┌──────────────────────────────────────────────────────┐
│  Saved Scenarios                    [+ New Scenario] │
│──────────────────────────────────────────────────────│
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ ● Cloud Outage                          Active │  │
│  │   42 vertices · 5 prompts · 2 indexes         │  │
│  │   Last updated: 2 hours ago                   │  │
│  │                                    [⋮ menu]   │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ ○ Telco NOC                                   │  │
│  │   128 vertices · 6 prompts · 2 indexes        │  │
│  │   Last updated: yesterday                     │  │
│  │                                    [⋮ menu]   │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ ○ Customer Recommendation                     │  │
│  │   85 vertices · 5 prompts · 2 indexes         │  │
│  │   Last updated: 3 days ago                    │  │
│  │                                    [⋮ menu]   │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Empty state (when no scenarios saved):              │
│  ┌────────────────────────────────────────────────┐  │
│  │  No scenarios yet                              │  │
│  │  Click "+ New Scenario" to create your first   │  │
│  │  scenario data pack.                           │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**Scenario card interactions:**
- **Click the card** → activates that scenario (same as selecting from dropdown) +
  triggers auto-provisioning. Card shows provisioning spinner, then "Active" badge.
- **⋮ menu** → context menu with:
  - "Re-upload data" → opens AddScenarioModal pre-filled with the scenario name (locked)
  - "Delete scenario" → confirmation dialog → calls `DELETE /query/scenarios/saved/{name}`
- **Active badge** → green pill with "Active" text, shown on the currently active card
- **Radio dot** → `●` for active, `○` for inactive — makes it clear this is a single-select

**Why is this better than a dropdown?**
- Scenarios are a **first-class concept** — they deserve their own dedicated space
- Cards show metadata (vertex count, prompt count, timestamps) at a glance
- Users can see *all* their scenarios without opening a `<select>`
- The empty state guides first-time users
- The ⋮ menu provides management actions (delete, re-upload) that a dropdown can't

**Data Sources tab** becomes simpler: it shows the *current bindings* (read-only when
a saved scenario is active, editable when in Custom mode). The "+Add Scenario" button
moves to the Scenarios tab.

**Upload tab** stays as-is — it's for ad-hoc individual uploads outside the scenario
workflow, same as today.

---

### UX-4: Smart File Auto-Detection in AddScenarioModal

**Problem:** The plan requires users to manually drag 5 files into 5 specific slots.
Given that tarballs from `generate_all.sh` are named `{scenario}-graph.tar.gz`,
`{scenario}-telemetry.tar.gz`, etc., this is needless manual work.

**Fix:** Add two smart file-handling behaviors:

**a) Auto-slot detection from file name:**

`generate_all.sh` produces tarballs with a strict naming convention:
```
{scenario}-graph.tar.gz
{scenario}-telemetry.tar.gz
{scenario}-runbooks.tar.gz
{scenario}-tickets.tar.gz
{scenario}-prompts.tar.gz
```

The suffix is always the **last hyphen-separated segment** before `.tar.gz`. Match
against that suffix, not a loose regex on the full name (avoids false-positives on
scenario names like `"graph-migration"`):

```typescript
type SlotKey = 'graph' | 'telemetry' | 'runbooks' | 'tickets' | 'prompts';

const KNOWN_SUFFIXES: SlotKey[] = ['graph', 'telemetry', 'runbooks', 'tickets', 'prompts'];

function detectSlot(filename: string): { slot: SlotKey; scenarioName: string } | null {
  // Strip .tar.gz / .tgz extension
  const base = filename.replace(/\.(tar\.gz|tgz)$/i, '');
  // Split on last hyphen: "cloud-outage-graph" → ["cloud-outage", "graph"]
  const lastDash = base.lastIndexOf('-');
  if (lastDash < 1) return null;
  const suffix = base.substring(lastDash + 1).toLowerCase() as SlotKey;
  const name = base.substring(0, lastDash);
  if (KNOWN_SUFFIXES.includes(suffix)) {
    return { slot: suffix, scenarioName: name };
  }
  return null;
}
```

If detection succeeds, auto-assign to the correct slot and show a brief inline
label: "Auto-detected: Graph data". If detection fails (non-standard filename),
fall back to letting the user click the specific slot to assign it.

**b) Multi-file drop zone:**
Above the 5 individual slots, add a large drop zone:
```
┌──────────────────────────────────────────────────────┐
│  Drop all 5 tarballs here, or select them below      │
│          ┌───────────────────────────────┐            │
│          │    📂 Drop files anywhere    │            │
│          └───────────────────────────────┘            │
└──────────────────────────────────────────────────────┘
```
When multiple files are dropped at once, run `detectSlot()` on each one. Auto-slot
every file that matches. This turns a 5-click upload into a single drag-and-drop
gesture. Files that can't be auto-detected appear in a small "unassigned" list with
manual slot selectors.

**c) Auto-derive scenario name from filenames (pre-fill only):**
If the scenario name field is **empty** and `detectSlot()` returns a `scenarioName`,
auto-populate the name field with it (e.g., `"cloud-outage-graph.tar.gz"` →
`"cloud-outage"`). If multiple files are dropped and they yield different scenario
names, use the **most common** one and show a warning:
"⚠ Files have mixed scenario names — verify the name is correct."

**The user-typed scenario name is always authoritative.** Auto-detection only
pre-fills the input as a convenience — whatever the user types (or edits to)
is the final name. When "Save Scenario" is clicked, this name is sent as the
`?scenario_name=X` query parameter to every upload endpoint, overriding both
the filename convention *and* the `name` field inside `scenario.yaml`.

Show helper text beneath the input:
- Before user edits: "*Auto-detected from filename — edit freely*"
- After user edits: (no helper text — their input is explicit)

**d) Mismatch hint (informational only, never blocking):**
When the user types a scenario name that differs from the filenames (e.g., name
is `"my-custom"` but graph file is `"cloud-outage-graph.tar.gz"`), show a
non-blocking hint:
"ⓘ File names suggest 'cloud-outage' but resources will be created as 'my-custom'."

This is expected and correct behavior — the whole point of the `?scenario_name`
override is to let users re-label data freely. The hint just prevents accidental
typos, never prevents saving.

---

### UX-5: Enhanced AddScenarioModal Layout & State Machine

**Current plan's wireframe is functional but sparse.** Here's a more detailed spec:

```
┌──────────────────────────────────────────────────────────────┐
│ New Scenario                                             ✕   │
│─────────────────────────────────────────────────────────────│
│                                                              │
│ Scenario Name                                                │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ cloud-outage                                             │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ⓘ Lowercase letters, numbers, and hyphens only. 2-50 chars. │
│                                                              │
│ ▸ Display Name & Description (optional, collapsed)           │
│                                                              │
│ ── Upload Data Files ──────────────────────────────────────  │
│                                                              │
│ ┌─────── Drop all 5 tarballs here ───────────────────────┐  │
│ │              📂 or click to browse                      │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌──────────────────────┐  ┌──────────────────────┐          │
│ │ 🔗 Graph Data        │  │ 📊 Telemetry          │          │
│ │ cloud-outage-gra…    │  │ ─ not selected ─      │          │
│ │ 2.1 MB   ✓  [✕]     │  │                       │          │
│ └──────────────────────┘  └──────────────────────┘          │
│ ┌──────────────────────┐  ┌──────────────────────┐          │
│ │ 📋 Runbooks          │  │ 🎫 Tickets            │          │
│ │ ─ not selected ─     │  │ ─ not selected ─      │          │
│ └──────────────────────┘  └──────────────────────┘          │
│ ┌──────────────────────┐                                     │
│ │ 📝 Prompts           │                                     │
│ │ ─ not selected ─     │                                     │
│ └──────────────────────┘                                     │
│                                                              │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ [Cancel]                          [Save Scenario] (dim) │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ * Save button stays disabled until name is valid AND all     │
│   5 slots have files selected.                               │
└──────────────────────────────────────────────────────────────┘
```

**File slot states (4 states, not just 2):**

| State | Visual | Interactions |
|-------|--------|--------------|
| `empty` | Dashed border, "─ not selected ─", click/drop to add | Click opens file picker; drop accepts `.tar.gz` |
| `staged` | Solid border, filename + file size, `✕` remove button | Click `✕` to clear; click slot to replace |
| `uploading` | Progress bar + percentage + step text, non-interactive | No interaction allowed — disabled |
| `done` | Green border, ✓ checkmark, upload result summary | Click to re-upload (replace) |
| `error` | Red border, error message, "Retry" button | Click "Retry" to re-upload just this file |

**Key difference from current plan:** Files are *staged* locally before any upload
begins. All 5 files are selected first, then "Save Scenario" triggers the upload
sequence. This is already in the plan but the wireframe didn't show the `staged`
state clearly — it jumps from "Drop file here" to "Uploading".

**Save Scenario progress (replaces the single progress bar):**

```
┌──────────────────────────────────────────────────────────────┐
│ Saving Scenario: cloud-outage                                │
│─────────────────────────────────────────────────────────────│
│                                                              │
│  ✓ Graph Data ····················· 42 vertices, 68 edges   │
│  ✓ Telemetry ····················· 2 containers loaded      │
│  ◉ Runbooks ······ ■■■■■■■□□□ 65% Creating search index...  │
│  ○ Tickets ······················· Waiting                   │
│  ○ Prompts ······················· Waiting                   │
│                                                              │
│  Overall: 3 of 5 ■■■■■■■■■■■□□□□ 52%                       │
│                                                              │
│  [Cancel]                                                    │
└──────────────────────────────────────────────────────────────┘
```

**Status icons:** `✓` done, `◉` in-progress (animated), `○` waiting, `✕` failed

This gives users a clear sense of progress across all 5 uploads, not just the active
one. Each step shows its own result (vertex count, container count, etc.) as it
completes — drawn from the SSE `complete` events the upload endpoints already emit.

**Cancel during upload:** The Cancel button during saving should:
1. Abort the current upload's fetch request (`AbortController.abort()`)
2. Warn: "Cancelling will stop remaining uploads. Already-uploaded data will remain in Azure."
3. Return to the form with completed items marked ✓ and remaining items still staged
4. User can click "Save Scenario" again to retry from where they left off

---

### UX-6: Override Confirmation Dialog

**Problem:** The plan mentions showing a confirmation when overriding an existing
scenario, but doesn't spec the dialog.

**Fix:** Before starting uploads, if a scenario with the same name exists in
`savedScenarios`, show a blocking confirmation dialog:

```
┌──────────────────────────────────────────────────────┐
│  ⚠ Scenario Already Exists                           │
│──────────────────────────────────────────────────────│
│                                                      │
│  "cloud-outage" was last updated 2 hours ago.        │
│                                                      │
│  Saving will overwrite all data:                     │
│  • Graph topology (42 vertices → re-upload)          │
│  • Telemetry databases (2 containers → re-upload)    │
│  • Runbook search index (→ re-create)                │
│  • Ticket search index (→ re-create)                 │
│  • Prompts (6 prompts → re-upload)                   │
│                                                      │
│  ┌──────────────────────────────────────────────────┐│
│  │  [Cancel]                [Overwrite & Continue]  ││
│  └──────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────┘
```

This uses metadata from the existing scenario document (vertex count, prompt count,
timestamps) to make the impact concrete.

---

### UX-7: Provisioning Feedback After Scenario Selection

**Problem:** The plan says selecting a scenario auto-triggers `POST /api/config/apply`
(~30s), but doesn't specify what the user *sees* during that time. The Header chip
alone isn't enough.

**Fix:** Use a **non-blocking toast/banner** at the top of the main workspace:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◆ AI Incident Investigator    ▾ cloud-outage ⟳    ● API  ⟳ Provisioning ⚙│
├──────────────────────────────────────────────────────────────────────────┤
│ 🔄 Provisioning agents for "cloud-outage"... Creating RunbookKB agent   │
└──────────────────────────────────────────────────────────────────────────┘
```

- A slim banner (28px high) appears below the header during provisioning
- Shows the current step from the SSE stream (e.g., "Creating RunbookKB agent")
- Auto-dismisses 3 seconds after provisioning completes with a green ✓ flash
- If provisioning fails, banner turns red and stays until dismissed
- The workspace remains **fully interactive** during provisioning — user can view
  the topology (it already loaded via the new X-Graph header) and browse the graph.
  Only the "Submit Alert" button should show a "Provisioning..." disabled state.

This is better than a modal because:
- It doesn't block the UI — the user can explore the topology while agents provision
- It provides continuous feedback without demanding attention
- It naturally resolves itself on success

---

### UX-8: Cleanup SettingsModal — Remove Redundancy

**Problem:** With the Scenarios tab handling scenario lifecycle and the Header chip
handling quick-switching, the Data Sources tab becomes less critical. Currently it has
5 separate dropdown sections + 2 action buttons, and the plan adds a scenario dropdown
at the top. This is redundant with the Scenarios tab.

**Fix — Simplify the Data Sources tab:**

**When a saved scenario is active:**
```
┌──────────────────────────────────────────────────────┐
│  Active Scenario: cloud-outage                       │
│──────────────────────────────────────────────────────│
│  GraphExplorer   →  cloud-outage-topology            │
│  Telemetry       →  cloud-outage-telemetry           │
│  RunbookKB       →  cloud-outage-runbooks-index      │
│  Tickets         →  cloud-outage-tickets-index       │
│  Prompts         →  cloud-outage                     │
│                                                      │
│  All bindings auto-derived from scenario name.       │
│  [Switch to Custom mode] to manually configure.      │
│──────────────────────────────────────────────────────│
│  Agents: ✓ 5 provisioned (14 minutes ago)            │
│  [Re-provision Agents]                               │
└──────────────────────────────────────────────────────┘
```

- Bindings are shown as read-only text (not dropdowns) when a scenario is active
- A "Switch to Custom mode" link unlocks the dropdowns for manual override
- The "Load Topology" button is *removed* — topology auto-loads on scenario select
  (the `useTopology` hook already reacts to `X-Graph` header changes)
- "Provision Agents" becomes "Re-provision Agents" with a timestamp of last provisioning

**When in Custom mode (no scenario selected):**
- Same as the current layout — individual dropdowns for graph, runbooks, tickets, prompt set
- Action buttons: "Load Topology" + "Provision Agents"

---

### UX-9: Escape & Backdrop Dismiss for Modals

**Problem:** The current `SettingsModal` doesn't close on Escape key or backdrop click.
The plan's `AddScenarioModal` doesn't mention this either.

**Fix:** Both modals should:
- Close on `Escape` keypress (except when an upload is in progress — show "Cancel upload first")
- Close on backdrop click (same caveat)
- Trap focus inside the modal for accessibility
- Add `aria-modal="true"` and `role="dialog"` attributes

---

### UX-10: Persist Active Scenario Across Page Refresh

**Problem:** `ScenarioContext.tsx` initializes to `'topology'`, `'runbooks-index'`,
`'tickets-index'` on every mount. If the user refreshes the page, they lose their
scenario selection.

**Fix:** Persist `activeScenario` to `localStorage`:
```typescript
const [activeScenario, setActiveScenario] = useState<string | null>(
  () => localStorage.getItem('activeScenario')
);

useEffect(() => {
  if (activeScenario) {
    localStorage.setItem('activeScenario', activeScenario);
  } else {
    localStorage.removeItem('activeScenario');
  }
}, [activeScenario]);
```

On load, if a persisted scenario name exists, auto-derive all bindings from it.
This means `activeGraph`, `activeRunbooksIndex`, `activeTicketsIndex`, and
`activePromptSet` are all derived from the persisted name — no need to persist
each individually.

Note: This does NOT re-trigger agent provisioning on refresh — agents are long-lived
in AI Foundry. It only restores the *frontend state* so `X-Graph` headers and UI
indicators are correct.

---

### UX-11: Extract SSE Parsing Into a Shared Utility

**Current code problem:** SSE `ReadableStream` parsing (the `reader.read()` +
`decoder.decode()` + `data:` line splitting pattern) is copy-pasted in:
- `UploadBox` inside `SettingsModal.tsx`
- "Provision Agents" `ActionButton` in `SettingsModal.tsx`
- `uploadScenario` in `useScenarios.ts` (dead code, but still)
- The new `AddScenarioModal` will need it too

**Fix:** Extract into `frontend/src/utils/sseStream.ts`:
```typescript
/**
 * Consume an SSE response body and call handlers for each parsed event.
 * Handles the raw ReadableStream text/event-stream format used by the
 * graph-query-api upload and provisioning endpoints.
 */
export async function consumeSSE(
  response: Response,
  handlers: {
    onProgress?: (data: { step: string; detail: string; pct: number }) => void;
    onComplete?: (data: Record<string, unknown>) => void;
    onError?: (data: { error: string }) => void;
  },
  signal?: AbortSignal,
): Promise<void> { ... }
```

This eliminates 3-4 copies of the same 20-line parsing block and ensures consistent
error handling across all SSE consumers.

---

### UX-12: Move `activePromptSet` Into ScenarioContext

**Current code problem:** `activePromptSet` is local state inside `SettingsModal.tsx`.
When the modal is closed and reopened, the state is reset. Other components (like the
Header chip or the provisioning flow) can't access it.

**Fix:** As the plan already partially specifies, `activePromptSet` must be in
`ScenarioContext`. The current frontend code's `SettingsModal` manages this as local
`useState` — that needs to move to the provider. This is already in the plan's
"ScenarioContext Changes" section, but flagging it here for emphasis since it's a
**bug in the existing app** (not just a new-feature concern).

---

### UX-13: Delete Scenario UX

**Problem:** The plan's delete endpoint (`DELETE /query/scenarios/saved/{name}`) is
specified backend-side, but the frontend UX for deletion isn't detailed.

**Fix:** Delete is triggered from the ⋮ menu on a scenario card (Scenarios tab):

```
┌──────────────────────────────────────────────────────┐
│  ⚠ Delete Scenario                                   │
│──────────────────────────────────────────────────────│
│                                                      │
│  Are you sure you want to delete "cloud-outage"?     │
│                                                      │
│  This will remove the scenario record only.          │
│  Underlying Azure resources (graph data, search      │
│  indexes, telemetry) will NOT be deleted.            │
│                                                      │
│  [Cancel]                       [Delete Scenario]    │
└──────────────────────────────────────────────────────┘
```

- "Delete Scenario" button is red/destructive styled
- If the deleted scenario was the active one, `activeScenario` resets to `null`
- The scenario card animates out (e.g., `framer-motion` `layoutId` exit animation —
  already a project dependency)
- Toast: "Scenario 'cloud-outage' deleted"

---

### UX-14: First-Time Upload Performance Warning

**Problem:** The plan notes first-time scenario uploads may take 3-5 minutes due to
ARM resource creation. But this isn't communicated to the user in the UI.

**Fix:** When creating a scenario whose name doesn't match any existing resources,
show a note below the progress section:

```
ⓘ First-time setup: Creating Azure resources for this scenario.
  This may take 3-5 minutes. Subsequent uploads will be faster.
```

The backend can signal this: if `_ensure_gremlin_graph` or `_ensure_nosql_db_and_containers`
actually creates resources (vs finding them already existing), the SSE progress event can
include `"first_time": true`. The frontend uses this to show the message.

---

### UX-15: Existing Dead Code Cleanup

**Problem (from code audit):** `useScenarios.ts` contains `uploadScenario()` which posts
to the deprecated `/query/scenario/upload` endpoint. The plan mentions this but doesn't
explicitly add it to the file change inventory as cleanup.

**Fix:** Add to Phase 2 tasks:
- Remove `uploadScenario`, `cancelUpload`, `uploading`, `progress`, `uploadResult` from
  `useScenarios.ts` — all dead code from a previous iteration
- Remove the `ProgressEvent` and `UploadResult` internal interfaces (unused after cleanup)
- This reduces the hook from 133 lines to ~60 lines before adding the new scenario features

---

### Summary of UX Improvements

| # | Improvement | Impact | Effort | Status |
|---|-------------|--------|--------|--------|
| UX-1 | Scenario chip in Header bar | High — instant access | Small | ✅ `ScenarioChip.tsx` |
| UX-2 | Active scenario indicator always visible | High — situational awareness | Small | ✅ `Header.tsx` dynamic agent status |
| UX-3 | 3-tab Settings (Scenarios / Data Sources / Upload) | High — dedicated scenario space | Medium | ✅ `SettingsModal.tsx` |
| UX-4 | Smart file auto-detection from filename | Medium — friction reduction | Small | ✅ `AddScenarioModal.tsx` `detectSlot()` |
| UX-5 | Enhanced AddScenarioModal layout & states | High — clear progress | Medium | ✅ `AddScenarioModal.tsx` |
| UX-6 | Override confirmation dialog | Medium — data safety | Small | 🔶 Basic confirmation; no detailed metadata breakdown |
| UX-7 | Non-blocking provisioning banner | High — responsive feedback | Small | ✅ `ProvisioningBanner.tsx` |
| UX-8 | Simplified Data Sources tab | Medium — reduced clutter | Small | ✅ Read-only bindings when scenario active |
| UX-9 | Escape & backdrop dismiss for modals | Medium — polish | Small | 🔶 Escape + backdrop done; focus trapping not done |
| UX-10 | Persist active scenario to localStorage | Medium — session continuity | Small | ✅ `ScenarioContext.tsx` |
| UX-11 | Shared SSE parsing utility | Low (code quality) — DRY | Small | ✅ `sseStream.ts` (see deviation D-1) |
| UX-12 | activePromptSet in ScenarioContext | Medium — bug fix | Small | ✅ `ScenarioContext.tsx` |
| UX-13 | Delete scenario UX spec | Medium — complete lifecycle | Small | 🔶 Inline confirmation in Scenarios tab; no exit animation |
| UX-14 | First-time performance warning | Low — expectation setting | Small | 🔶 Static warning in modal; no backend `first_time` signal |
| UX-15 | Dead code cleanup | Low (code quality) — housekeeping | Small | ✅ Dead code removed from `useScenarios.ts` |

---

## Naming Convention

Given a scenario name `SCENARIONAME`, all resources follow this pattern:

| Resource | Name | Location |
|----------|------|----------|
| Gremlin Graph | `SCENARIONAME-topology` | Cosmos Gremlin → `networkgraph` database |
| Telemetry DB | `SCENARIONAME-telemetry` | Cosmos NoSQL (own database) |
| Runbooks Blob | `SCENARIONAME-runbooks` | Azure Storage blob container |
| Runbooks Index | `SCENARIONAME-runbooks-index` | AI Search |
| Tickets Blob | `SCENARIONAME-tickets` | Azure Storage blob container |
| Tickets Index | `SCENARIONAME-tickets-index` | AI Search |
| Prompts DB | `SCENARIONAME-prompts` | Cosmos NoSQL (own database) |
| Scenario Record | `SCENARIONAME` | Cosmos NoSQL → `scenarios` / `scenarios` |

**Scenario name validation rules:**
- Lowercase alphanumeric + hyphens only (`^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$`)
- No consecutive hyphens (`--`) — Azure Blob container names forbid them, and
  scenario names become blob container prefixes (e.g., `{name}-runbooks`)
- Min 2 chars, max 50 chars (total blob container name ≤ 63 chars; longest
  suffix is `-runbooks-index` at 15 chars → 50 + 15 = 65, but blob container
  names stop at `-runbooks` = 9 chars → 50 + 9 = 59 ✓)
- Must not end with `-topology`, `-telemetry`, `-prompts`, `-runbooks`, `-tickets` (reserved suffixes)
- Enforced both frontend (input validation) and backend (API validation)
- Regex with consecutive-hyphen guard:
  ```
  ^[a-z0-9](?!.*--)[a-z0-9-]{0,48}[a-z0-9]$
  ```

---

## Cosmos DB "scenarios" Registry

### Database & Container

| Property | Value |
|----------|-------|
| Account | Same NoSQL account (`{name}-nosql`) |
| Database | `scenarios` |
| Container | `scenarios` |
| Partition Key | `/id` (scenario name) |
| Throughput | Autoscale max 400 RU/s (minimal — low volume) |

The database + container are created on first use (same ARM two-phase pattern as prompts).

### Document Schema

```json
{
  "id": "cloud-outage",
  "display_name": "Cloud Outage",
  "description": "Cooling failure → thermal shutdown cascade",
  "created_at": "2026-02-15T10:30:00Z",
  "updated_at": "2026-02-15T14:20:00Z",
  "created_by": "ui",
  "resources": {
    "graph": "cloud-outage-topology",
    "telemetry_database": "cloud-outage-telemetry",
    "runbooks_index": "cloud-outage-runbooks-index",
    "tickets_index": "cloud-outage-tickets-index",
    "prompts_database": "cloud-outage-prompts"
  },
  "upload_status": {
    "graph": { "status": "complete", "timestamp": "2026-02-15T10:31:00Z", "vertices": 42, "edges": 68 },
    "telemetry": { "status": "complete", "timestamp": "2026-02-15T10:32:00Z", "containers": 2 },
    "runbooks": { "status": "complete", "timestamp": "2026-02-15T10:33:00Z", "index": "cloud-outage-runbooks-index" },
    "tickets": { "status": "complete", "timestamp": "2026-02-15T10:34:00Z", "index": "cloud-outage-tickets-index" },
    "prompts": { "status": "complete", "timestamp": "2026-02-15T10:35:00Z", "prompt_count": 6 }
  }
}
```

### Why a Separate "scenarios" Database?

- Scenario registry is cross-cutting — it tracks resources across Gremlin, NoSQL, Search, Blob
- Per-scenario databases (`{name}-prompts`, `{name}-telemetry`) store actual data
- The `scenarios` database is a lightweight index/catalog — independent of any single scenario
- Low volume (tens of documents max), low RU, simple queries

---

## Backend Changes

### New Endpoints (graph-query-api)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/query/scenarios/saved` | List all saved scenarios from `scenarios` DB |
| POST | `/query/scenarios/save` | Save/upsert a scenario record after uploads complete |
| DELETE | `/query/scenarios/saved/{name}` | Delete a saved scenario record (and optionally its data) |

### `GET /query/scenarios/saved`

Returns all saved scenario documents from the `scenarios` database.

```python
@router.get("/scenarios/saved", summary="List saved scenarios")
async def list_saved_scenarios():
    container = _get_scenarios_container()
    def _list():
        items = list(container.query_items(
            query="SELECT * FROM c ORDER BY c.updated_at DESC",
            enable_cross_partition_query=True,
        ))
        return items
    scenarios = await asyncio.to_thread(_list)
    return {"scenarios": scenarios}
```

### `POST /query/scenarios/save`

Upserts a scenario document. Called by the frontend after all 5 uploads succeed.

```python
class ScenarioSaveRequest(BaseModel):
    name: str                    # Scenario name (becomes document id)
    display_name: str = ""       # Optional friendly name
    description: str = ""        # Optional description
    upload_results: dict         # Results from each upload (graph, telemetry, etc.)

@router.post("/scenarios/save", summary="Save scenario metadata")
async def save_scenario(req: ScenarioSaveRequest):
    # Validate name format
    # Upsert document into scenarios/scenarios container
    # Return the saved document
```

### `_get_scenarios_container()` Helper

Same pattern as `_get_prompts_container()` — lazy-init with optional ARM creation:

```python
_scenarios_container = None

def _get_scenarios_container(*, ensure_created: bool = True):
    global _scenarios_container
    if _scenarios_container is not None:
        return _scenarios_container
    
    # ARM phase: create database "scenarios", container "scenarios", PK "/id"
    # Data plane: CosmosClient → cache and return container
```

### New File: `graph-query-api/router_scenarios.py`

Rather than adding more code to the already-long `router_ingest.py` (1329 lines),
create a new router for scenario management:

```
graph-query-api/
  router_scenarios.py    # NEW — scenario CRUD (save, list, delete)
  router_ingest.py       # UNCHANGED — keeps individual upload endpoints
  router_prompts.py      # UNCHANGED
  main.py                # ADD: mount router_scenarios router
```

### Changes to `graph-query-api/main.py`

Add the new router:

```python
from router_scenarios import router as scenarios_router
app.include_router(scenarios_router)
```

### Tarball `scenario.yaml` Name Override

Currently each upload reads the scenario name from `scenario.yaml` inside the tarball.
The new flow sends the scenario name from the form, which may differ from what's in
`scenario.yaml`. Two options:

**Option A (Recommended): Trust the form name.** Add a `?scenario_name=X` query parameter
to each upload endpoint. If present, the endpoint uses it to override the name from
`scenario.yaml`. This means the user-chosen name in the "+Add Scenario" form controls
everything. Existing behavior (no param) is unchanged.

**Option B: Require match.** Validate that the form name matches `scenario.yaml`.
This is fragile — users would need to edit YAML before uploading.

**Go with Option A.** Add an optional `scenario_name` query parameter to all 5 upload
endpoints. When provided, it overrides the name extracted from `scenario.yaml`.

#### Current State of Upload Endpoint Parameters (Important)

The 5 upload endpoints are **not uniform** today — be aware of these differences:

| Endpoint | Current `scenario_name` param? | Current behavior |
|----------|-------------------------------|------------------|
| `POST /query/upload/graph` | **No** | Reads `scenario.yaml` only |
| `POST /query/upload/telemetry` | **No** | Reads `scenario.yaml` only |
| `POST /query/upload/runbooks` | **Yes** (`scenario: str = "default"`) | `scenario.yaml` **overrides** the query param (param is fallback only) |
| `POST /query/upload/tickets` | **Yes** (`scenario: str = "default"`) | `scenario.yaml` **overrides** the query param (param is fallback only) |
| `POST /query/upload/prompts` | **No** | Reads `scenario.yaml`, defaults to `"default"` if absent |

**Required changes per endpoint:**
- **Graph, Telemetry, Prompts:** Add `scenario_name: str | None = Query(default=None)` parameter.
  When provided, use it **instead of** `manifest["name"]`.
- **Runbooks, Tickets:** These already have a `scenario` param, but it's a **fallback** — the
  tarball's `scenario.yaml` overrides it. **Invert this behavior:** rename to `scenario_name`
  for consistency, and when provided, use it as the **override** (takes priority over `scenario.yaml`).
  This is a behavioral change for these two endpoints.

All 5 endpoints should use the **same parameter name** (`scenario_name`) with the **same semantics**
(override when present, fall back to `scenario.yaml` when absent).

---

## Frontend Changes

### New Components

| Component | Purpose |
|-----------|---------|
| `AddScenarioModal.tsx` | Modal form: name input + 5 file slots + Save button (see UX-5) |
| `ScenarioChip.tsx` | Header bar scenario selector chip + flyout dropdown (see UX-1) |
| `ProvisioningBanner.tsx` | Non-blocking slim banner below header during provisioning (see UX-7) |

### New Utility

| File | Purpose |
|------|---------|
| `utils/sseStream.ts` | Shared SSE ReadableStream parser (see UX-11) |

### Modified Components

| Component | Changes |
|-----------|---------|
| `SettingsModal.tsx` | 3 tabs (Scenarios / Data Sources / Upload); scenario card list on Scenarios tab; simplified Data Sources when scenario active (see UX-3, UX-8); Escape/backdrop dismiss (UX-9) |
| `Header.tsx` | Add `ScenarioChip`; replace hardcoded "5 Agents" with dynamic status (see UX-1, UX-2) |
| `ScenarioContext.tsx` | Add `activeScenario`, `activePromptSet` state; `setActiveScenario()` with auto-derivation; localStorage persistence (see UX-10, UX-12) |
| `useScenarios.ts` | Add `savedScenarios`, `fetchSavedScenarios()`, `saveScenario()`, `selectScenario()`; remove dead `uploadScenario()` code (see UX-15) |

### `AddScenarioModal.tsx` — New Component

A modal/panel that appears when the user clicks "+Add Scenario":

```
┌──────────────────────────────────────────────┐
│  Add Scenario                            ✕   │
│──────────────────────────────────────────────│
│                                              │
│  Scenario Name: [___________________]        │
│                                              │
│  ┌──────────────────┐ ┌──────────────────┐   │
│  │ 🔗 Graph Data    │ │ 📊 Telemetry     │   │
│  │ [selected.tar.gz]│ │ [Drop file here] │   │
│  │         ✓        │ │                  │   │
│  └──────────────────┘ └──────────────────┘   │
│  ┌──────────────────┐ ┌──────────────────┐   │
│  │ 📋 Runbooks      │ │ 🎫 Tickets       │   │
│  │ [Drop file here] │ │ [Drop file here] │   │
│  └──────────────────┘ └──────────────────┘   │
│  ┌──────────────────┐                        │
│  │ 📝 Prompts       │                        │
│  │ [Drop file here] │                        │
│  └──────────────────┘                        │
│                                              │
│  [Save Scenario] (disabled until all ready)  │
│──────────────────────────────────────────────│
│  Progress:                                   │
│  ■■■■■■■■□□ 80% — Uploading runbooks...      │
└──────────────────────────────────────────────┘
```

**State machine:**
1. `idle` — form visible, user fills in name and selects files
2. `uploading` — each tarball uploads sequentially (graph → telemetry → runbooks → tickets → prompts)
3. `saving` — all uploads done, saving metadata to Cosmos
4. `done` — scenario saved, show success message
5. `error` — show error, allow retry

**Key behaviors:**
- "Save Scenario" button disabled unless: name is non-empty + valid + all 5 files selected
- Files are staged locally (not uploaded until Save is clicked)
- Each upload uses the existing `/query/upload/{type}?scenario_name=X` endpoints
- After all 5 uploads succeed, calls `POST /query/scenarios/save` with the results
- On success, refreshes the saved scenarios list and closes the modal

### SettingsModal Changes

**Data Sources tab — New scenario dropdown at the top:**

```
┌──────────────────────────────────────────────┐
│  Active Scenario                             │
│  ┌─────────────────────────────────────────┐ │
│  │ [▾ cloud-outage (42 vertices)        ]  │ │
│  └─────────────────────────────────────────┘ │
│  [+ Add Scenario]                            │
│──────────────────────────────────────────────│
│  GraphExplorer Agent                         │
│  Cosmos Graph: cloud-outage-topology  (auto) │
│                                              │
│  Telemetry Agent                             │
│  NoSQL Database: cloud-outage-telemetry      │
│                                              │
│  RunbookKB Agent                             │
│  AI Search: cloud-outage-runbooks-index      │
│                                              │
│  HistoricalTicket Agent                      │
│  AI Search: cloud-outage-tickets-index       │
│                                              │
│  Prompt Set: cloud-outage                    │
│──────────────────────────────────────────────│
│  [Load Topology]  [Provision Agents]         │
└──────────────────────────────────────────────┘
```

When a saved scenario is selected from the dropdown:
1. All 5 data source bindings auto-populate (derived from scenario name)
2. Individual dropdowns become **read-only** (greyed out, showing the values)
3. "Provision Agents" auto-triggers

Users can still manually configure bindings by selecting "(Custom)" from the
scenario dropdown — this returns to the current manual selection behavior.

### ScenarioContext Changes

Add `activeScenario` and `activePromptSet` to the context:

```typescript
interface ScenarioState {
  activeScenario: string | null;        // NEW — null means custom/manual
  activeGraph: string;
  activeRunbooksIndex: string;
  activeTicketsIndex: string;
  activePromptSet: string;              // NEW — tracks which prompt scenario is active
  setActiveScenario: (name: string | null) => void;  // NEW
  setActiveGraph: (graph: string) => void;
  setActiveRunbooksIndex: (index: string) => void;
  setActiveTicketsIndex: (index: string) => void;
  setActivePromptSet: (name: string) => void;         // NEW
  getQueryHeaders: () => Record<string, string>;
}
```

When `setActiveScenario(name)` is called:
- If `name` is non-null, auto-set all derived values:
  - `activeGraph = "{name}-topology"`
  - `activeRunbooksIndex = "{name}-runbooks-index"`
  - `activeTicketsIndex = "{name}-tickets-index"`
  - `activePromptSet = "{name}"`
- If `name` is null, leave existing values as-is (custom mode)

**Note on `getQueryHeaders()`:** This method only sends the `X-Graph` header.
Runbooks/tickets index names are **not** sent as request headers — they are only
used during agent provisioning (`POST /api/config/apply`). The `X-Graph` header
drives both graph queries and telemetry database routing (via `config.py`'s
`rsplit("-", 1)[0]` derivation).

### useScenarios Hook Changes

> **Warning — Dead code:** The existing `uploadScenario()` function in `useScenarios.ts`
> posts to `/query/scenario/upload` — this is a **deprecated monolithic endpoint** that is
> entirely commented out in `router_ingest.py`. The current `SettingsModal` does NOT use
> this function — it uses `UploadBox` which posts to the 5 per-type endpoints directly.
> The new `AddScenarioModal` must also call the per-type endpoints directly, not
> `uploadScenario()`. Consider removing the dead `uploadScenario()` function during cleanup.

Add:
```typescript
interface SavedScenario {
  id: string;              // scenario name
  display_name: string;
  description: string;
  created_at: string;
  updated_at: string;
  resources: {
    graph: string;
    telemetry_database: string;
    runbooks_index: string;
    tickets_index: string;
    prompts_database: string;
  };
  upload_status: Record<string, { status: string; timestamp: string }>;
}

// New state
const [savedScenarios, setSavedScenarios] = useState<SavedScenario[]>([]);

// New functions
const fetchSavedScenarios = useCallback(async () => { ... }, []);
const saveScenario = useCallback(async (meta: ScenarioSaveRequest) => { ... }, []);
```

---

## Scenario Selection & Agent Reprovisioning

When the user selects a scenario from the dropdown, the system must:

1. **Set all data source bindings** (instant, frontend-only)
2. **Reprovision agents** (takes ~30s, requires API call)

The reprovisioning is necessary because:
- `OpenApiTool` specs have the graph name baked in as a single-value `enum` in the `X-Graph` header
- `AzureAISearchTool` references specific index names via connection IDs
- Agent prompts need to be loaded from the scenario-specific prompts database

### Auto-Provisioning on Scenario Select

When a saved scenario is selected:

```typescript
async function selectScenario(name: string) {
  // 1. Update all bindings (instant — frontend state only)
  setActiveScenario(name);
  setActiveGraph(`${name}-topology`);
  setActiveRunbooksIndex(`${name}-runbooks-index`);
  setActiveTicketsIndex(`${name}-tickets-index`);
  setActivePromptSet(name);
  
  // 2. Graph topology auto-loads (NO explicit call needed):
  //    setActiveGraph() → getQueryHeaders() returns new X-Graph header
  //    → useTopology's fetchTopology useCallback recreated (depends on getQueryHeaders)
  //    → useEffect([fetchTopology]) fires → POST /query/topology with X-Graph: {name}-topology
  //    → GraphTopologyViewer re-renders with new nodes/edges
  //    This chain is already wired in useTopology.ts lines 73-79.
  
  // 3. Telemetry explorer also auto-routes:
  //    The X-Graph header drives ScenarioContext.telemetry_database derivation
  //    (graph-query-api config.py: "cloud-outage-topology" → rsplit("-",1)[0] → "cloud-outage-telemetry")
  //    So telemetry queries also target the correct database immediately.
  
  // 4. Auto-provision agents (takes ~30s, SSE stream)
  //    ⚠ IMPORTANT: POST /api/config/apply returns an SSE stream, NOT a JSON response.
  //    You MUST use @microsoft/fetch-event-source (already a project dependency)
  //    to consume the provisioning progress events. A plain fetch() will not work.
  //    Replicate the pattern already used by the "Provision Agents" button in
  //    SettingsModal.tsx — show a progress indicator while provisioning runs.
  await fetchEventSource('/api/config/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      graph: `${name}-topology`,
      runbooks_index: `${name}-runbooks-index`,
      tickets_index: `${name}-tickets-index`,
      prompt_scenario: name,
    }),
    onmessage(ev) {
      // Handle progress / complete / error events
      // Update provisioning status indicator
    },
  });
}
```

This reuses the existing `POST /api/config/apply` flow — no changes to the API
service or agent provisioner needed. The provisioner already supports:
- `graph` → baked into OpenAPI spec `X-Graph` enum
- `runbooks_index` / `tickets_index` → used for AzureAISearchTool connections
- `prompt_scenario` → fetches prompts from `{name}-prompts` database via loopback

---

## Implementation Phases

### Phase 1: Foundation — Backend + Shared Utils + Context ✅

**Files to create:**
- ✅ `graph-query-api/router_scenarios.py` — scenario CRUD (save, list, delete)
- ✅ `frontend/src/utils/sseStream.ts` — shared SSE parser (UX-11)

**Files to modify:**
- ✅ `graph-query-api/main.py` — mount the new router
- ✅ `graph-query-api/router_ingest.py` — add optional `scenario_name` query parameter to all 5 upload endpoints (see [Backend Changes → Upload Endpoint Parameters](#tarball-scenarioyaml-name-override) for details). **Deviation D-3:** runbooks/tickets retain old `scenario` param for backwards compat.
- ✅ `frontend/src/context/ScenarioContext.tsx` — add `activeScenario`, `activePromptSet`, localStorage persistence (UX-10, UX-12). Also added `provisioningStatus` state + `ProvisioningStatus` discriminated union type (**Deviation D-4**).
- ✅ `frontend/src/types/index.ts` — add `SavedScenario`, `ScenarioUploadSlot`, `SlotKey`, `SlotStatus` interfaces. (`ProvisioningStatus` lives in `ScenarioContext.tsx` per D-4.)
- ✅ `frontend/src/hooks/useScenarios.ts` — add `savedScenarios`, `fetchSavedScenarios()`, `saveScenario()`, `deleteSavedScenario()`, `selectScenario()` (uses native `consumeSSE` per **D-1**); remove dead `uploadScenario()` (UX-15)

### Phase 2: Add Scenario Form + Settings Restructure ✅

**Files to create:**
- ✅ `frontend/src/components/AddScenarioModal.tsx` — scenario creation form with multi-drop zone, auto-slot detection, staged file state, sequential upload with per-step progress (UX-4, UX-5)

**Files to modify:**
- ✅ `frontend/src/components/SettingsModal.tsx` — restructure to 3 tabs (Scenarios / Data Sources / Upload); Scenarios tab shows saved scenario cards with delete confirmation; Data Sources tab simplifies when scenario active (UX-3, UX-8); Escape/backdrop dismiss (UX-9); replaced inline SSE parsing with `consumeSSE` utility

### Phase 3: Header Integration + Scenario Selection ✅

**Files to create:**
- ✅ `frontend/src/components/ScenarioChip.tsx` — header bar scenario selector (UX-1)
- ✅ `frontend/src/components/ProvisioningBanner.tsx` — non-blocking provisioning feedback (UX-7)

**Files to modify:**
- ✅ `frontend/src/components/Header.tsx` — add `ScenarioChip` and `ProvisioningBanner`; replace hardcoded "5 Agents" with dynamic status (UX-1, UX-2)

### Phase 4: Polish & Edge Cases 🔶

| Item | Status | Notes |
|------|--------|-------|
| Override confirmation dialog with existing scenario metadata (UX-6) | 🔶 Partial | Basic confirmation exists in AddScenarioModal; lacks detailed metadata breakdown (vertex count, prompt count) |
| Delete scenario with confirmation dialog and animation (UX-13) | 🔶 Partial | Inline confirmation dropdown in Scenarios tab; no framer-motion exit animation |
| First-time upload performance warning (UX-14) | 🔶 Partial | Static warning note in AddScenarioModal; backend doesn't signal `"first_time": true` |
| Partial upload recovery — retry individual failed uploads | ⬜ Not done | |
| Focus trapping for accessibility (UX-9) | ⬜ Not done | `aria-modal` and `role="dialog"` are set; true tab-cycle trapping not implemented |
| Loading/spinner states during all async operations | 🔶 Partial | Provisioning spinner in ScenarioChip; no global loading states |
| Error toasts with auto-dismiss | ⬜ Not done | Errors display inline, not as toast notifications |
| Empty state illustrations for Scenarios tab | ⬜ Not done | Empty state text present but no illustration graphics |

---

## File Change Inventory

| File | Action | Status | Changes |
|------|--------|--------|--------|
| `graph-query-api/router_scenarios.py` | **CREATE** | ✅ | Scenario CRUD endpoints + `_get_scenarios_container()` — 272 lines |
| `graph-query-api/main.py` | MODIFY | ✅ | Add `from router_scenarios import router` + `app.include_router(...)` |
| `graph-query-api/router_ingest.py` | MODIFY | ✅ | Added `scenario_name` param to all 5 endpoints; graph/telemetry force hardcoded suffixes when override present; runbooks/tickets retain old `scenario` param (D-3); fixed missing `COSMOS_GREMLIN_GRAPH` import (bonus bug fix) |
| `frontend/src/components/AddScenarioModal.tsx` | **CREATE** | ✅ | Scenario creation form — 628 lines. Multi-drop, `detectSlot()`, staged states, AbortController, override confirmation, first-time warning |
| `frontend/src/components/ScenarioChip.tsx` | **CREATE** | ✅ | Header chip + flyout dropdown + "+ New Scenario" + Custom mode |
| `frontend/src/components/ProvisioningBanner.tsx` | **CREATE** | ✅ | 28px banner, SSE step display, 3s auto-dismiss, error dismiss |
| `frontend/src/utils/sseStream.ts` | **CREATE** | ✅ | `consumeSSE()` + `uploadWithSSE()` — native ReadableStream (D-1) — 143 lines |
| `frontend/src/components/SettingsModal.tsx` | MODIFY | ✅ | 3 tabs; scenario cards; read-only Data Sources; `consumeSSE` for provisioning; Escape/backdrop dismiss — ~745 lines |
| `frontend/src/components/Header.tsx` | MODIFY | ✅ | `ScenarioChip` + `ProvisioningBanner`; dynamic agent status from `provisioningStatus` |
| `frontend/src/context/ScenarioContext.tsx` | MODIFY | ✅ | `activeScenario`, `activePromptSet`, `provisioningStatus` + `ProvisioningStatus` type (D-4), localStorage, `setActiveScenario()` auto-derivation — ~105 lines |
| `frontend/src/hooks/useScenarios.ts` | MODIFY | ✅ | `savedScenarios`, `fetchSavedScenarios()`, `saveScenario()`, `deleteSavedScenario()`, `selectScenario()` (uses `consumeSSE`, D-1/D-2); dead code removed (UX-15) — ~175 lines |
| `frontend/src/types/index.ts` | MODIFY | ✅ | `SavedScenario`, `SlotKey`, `SlotStatus`, `ScenarioUploadSlot` — `ProvisioningStatus` in ScenarioContext (D-4) — ~55 lines |

### Files NOT Changed

- `api/app/routers/config.py` — existing `POST /api/config/apply` already handles everything
- `scripts/agent_provisioner.py` — no changes needed
- `graph-query-api/config.py` — `ScenarioContext` and `X-Graph` routing unchanged
- `graph-query-api/router_prompts.py` — prompt CRUD unchanged
- `graph-query-api/search_indexer.py` — indexer pipeline unchanged
- `infra/main.bicep` — no new env vars needed (uses same Cosmos NoSQL account)

> **Note on env var dependencies:** The `_get_scenarios_container()` ARM creation path
> requires `AZURE_SUBSCRIPTION_ID` and `AZURE_RESOURCE_GROUP` — these already exist for
> the prompts feature (set by `hooks/postprovision.sh`). No new env vars to add.

---

## Edge Cases & Validation

### Scenario Name Conflicts

When saving a scenario with an existing name:
- **Backend:** `upsert_item()` naturally overwrites — Cosmos NoSQL upsert is idempotent
- **Frontend:** Show confirmation dialog: "Scenario '{name}' already exists. This will overwrite the existing scenario metadata. Continue?"
- **Data resources:** The individual uploads already overwrite (graph does `g.V().drop()`, telemetry does `upsert_item`, blob does `overwrite=True`, search index recreates)

### Partial Upload Failure

If upload 3 of 5 fails (e.g., runbooks upload errors):
- Show the error inline next to the failed upload slot
- Allow the user to retry just the failed upload (keep the 2 successful results)
- "Save Scenario" remains disabled until all 5 show success
- No partial scenario record is saved to Cosmos

### Scenario Name vs `scenario.yaml` / Filename Mismatch

- The **user-typed name** in the AddScenarioModal is always authoritative
- It is sent as the `?scenario_name=X` query parameter to every upload endpoint
- This overrides **both** the `scenario.yaml` `name` field inside the tarball **and**
  the scenario name implied by the tarball filename convention (`{name}-{type}.tar.gz`)
- A tarball named `telco-noc-graph.tar.gz` containing `scenario.yaml` with `name: telco-noc`
  can be uploaded as `"my-custom-scenario"` — resources will be named
  `my-custom-scenario-topology`, etc., not `telco-noc-topology`
- This is the core design: data files are reusable across scenario names

### Telemetry Database Derivation Coupling

**Critical implementation note:** The telemetry database name is derived in **two different
places** with **two different algorithms** that must produce the same result:

1. **Upload time** (`router_ingest.py`): `f"{scenario_name}-{manifest.get('cosmos',{}).get('nosql',{}).get('database','telemetry')}"`
   → Creates the database named e.g. `cloud-outage-telemetry`

2. **Query time** (`config.py` → `ScenarioContext`): `graph_name.rsplit("-", 1)[0] + "-telemetry"`
   → Derives `cloud-outage-topology` → `cloud-outage` → `cloud-outage-telemetry`

These produce the same result **only when:**
- The `cosmos.nosql.database` value in `scenario.yaml` is `"telemetry"` (the default)
- The `cosmos.gremlin.graph` value in `scenario.yaml` is `"topology"` (the default)
- The suffix values are single words without hyphens

If `scenario.yaml` overrides these (e.g., `cosmos.nosql.database: "metrics"`), the upload
creates `cloud-outage-metrics` but queries look for `cloud-outage-telemetry` — **data is
inaccessible at query time.**

**Mitigation:** When the `scenario_name` override is provided, the upload endpoints should
**ignore** the `cosmos.nosql.database` and `cosmos.gremlin.graph` values from `scenario.yaml`
and always use the hardcoded suffixes (`-topology`, `-telemetry`). This guarantees the
naming convention is consistent with the query-time derivation. Add a code comment
explaining this coupling.

### Empty/Missing Upload Endpoints

If the backend lacks required services (e.g., `AI_SEARCH_NAME` not set):
- Runbooks/tickets uploads will fail with a clear error
- The user sees the error and can't proceed
- This is the same behavior as today — no change needed

### Concurrent Scenario Saves

- Cosmos upsert is last-writer-wins — safe for concurrent saves of different scenarios
- Same scenario by two users: last save wins, which is acceptable given the expected low concurrency

### First-Time Upload Performance

On first scenario upload, up to **4 ARM database creation operations** may trigger:
1. `{name}-topology` Gremlin graph (~20-30s)
2. `{name}-telemetry` NoSQL database + containers (~20-30s)
3. `{name}-prompts` NoSQL database + container (~20-30s)
4. `scenarios` registry database + container (~20-30s, first time only)

Subsequent uploads to the same scenario skip ARM creation (resources already exist).
The per-upload progress indicators in `AddScenarioModal` will show which step is
running, but users should expect first-time uploads to take 3-5 minutes total.

### Delete Scenario Scope

The `DELETE /query/scenarios/saved/{name}` endpoint scope:
- **v1:** Deletes the scenario **metadata record only** from the `scenarios` database.
  The underlying data resources (Gremlin graph, NoSQL databases, blob containers, search
  indexes) are left intact. This is safe and fast.
- **Future:** Add an optional `?delete_data=true` query parameter to also drop the
  Gremlin graph, delete NoSQL databases, remove blob containers, and delete search
  indexes. This is slow (multiple ARM deletions) and destructive — requires confirmation.

### Display Name and Description UX

The scenario document schema includes `display_name` and `description` fields, but the
`AddScenarioModal` form only requires `name`. For v1:
- `display_name` defaults to the scenario name with hyphens replaced by spaces and
  title-cased (e.g., `cloud-outage` → `Cloud Outage`)
- `description` defaults to empty string
- Both can be optionally entered in the form (collapsed "Advanced" section)
- The scenario dropdown shows `display_name` with the `id` in parentheses

---

## Migration & Backwards Compatibility

### Existing Uploaded Data

Data already uploaded via the current per-type upload tab is **not affected**. Those resources
(graphs, indexes, prompts databases) continue to exist and appear in the current dropdowns.

### Opt-In Feature

The "+Add Scenario" button is an addition — the existing Upload tab and manual Data Sources
dropdowns remain available. Users can continue with the manual workflow if they prefer.

### Gradual Adoption

1. Deploy Phase 1+2+3
2. Existing deployments see the new button and dropdown — they're empty initially
3. Users create new scenarios via the new flow, or continue using manual uploads
4. Previously uploaded data still works through the manual dropdowns (no saved scenario record needed)

### Future: Retroactive Scenario Detection

A future enhancement could scan existing resources (graphs, indexes, prompts) and
auto-create scenario records for data that was uploaded before this feature existed.
This would detect patterns like `telco-noc-topology` + `telco-noc-runbooks-index` +
`telco-noc-prompts` and create a `telco-noc` scenario record. **Not in scope for v1.**
