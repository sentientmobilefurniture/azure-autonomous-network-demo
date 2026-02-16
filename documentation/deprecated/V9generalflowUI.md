# V9 Config-Driven Orchestration — UI/UX Review & Suggestions

> **Date:** 2026-02-16
> **Reviewer perspective:** UI/UX Expert
> **Source document:** `V9generalflow.md`
> **Scope:** UI/UX observations, gaps, and improvement suggestions for the
> config-driven multi-agent orchestration plan (Phases 0–13)

---

## Executive Summary

The V9 plan is architecturally thorough but approaches the frontend primarily as
a "make it generic" exercise — swap hardcoded values for config-driven ones. This
review identifies **16 UI/UX observations** across 5 categories where the plan
either misses user-facing impact, introduces UX regressions, or leaves
opportunities on the table to improve the experience during genericization.

The suggestions are ordered by severity within each category:
- **Critical** — will cause user confusion or broken flows if unaddressed
- **Important** — meaningful quality improvement with modest effort
- **Nice-to-have** — polish items for a more professional result

---

## Category 1: Scenario Switching & Onboarding

### 1.1 No "First-Run" or Empty-State Guidance (Critical)

**What the plan says:** Phase 0 removes all pre-created scenario-specific
resources (Gremlin graph, blob containers). A fresh deployment has zero
scenarios — they must be uploaded.

**Problem:** A user hitting the app for the first time after `azd up` sees an
empty Investigate tab with no scenario, no data, no agents. The current UI has
no onboarding flow — no wizard, no callout to "Upload a scenario to get
started," no link to the settings modal's Upload tab.

**Suggestion:**
- Add a **first-run empty state** to the Investigate tab: a centered card with
  icon, "No scenario loaded" heading, brief explanation, and a primary CTA
  button ("Upload Scenario") that opens the Settings modal on the Upload tab.
- Show this state whenever `activeScenario` is `null` and the saved scenarios
  list is empty.
- Consider a subtle **guided steps** indicator: "1. Upload data → 2. Select
  scenario → 3. Provision agents → 4. Investigate" — shown inline until the
  user completes provisioning for the first time.

**Plan item affected:** Phase 11 (Frontend Genericization) — add first-run
empty state to the scope.

---

### 1.2 Scenario Switching Has No Validation Feedback (Important)

**What the plan says:** Phase 11a changes `ScenarioContext` to use resource
names from `SavedScenario.resources` when available, with convention fallback.

**Problem:** When a user selects a new scenario in the Settings modal, the
switch happens instantly with no validation that backend resources actually
exist. If a scenario was only partially uploaded (e.g., graph data loaded but
prompts not uploaded), the user gets silent failures later when trying to
investigate.

**Suggestion:**
- After scenario selection, perform a **lightweight health check** — ping
  `GET /query/scenarios/saved/{name}` or a dedicated status endpoint that
  returns which resources are ready (graph: ✓, telemetry: ✓, prompts: ✗,
  agents: ✗).
- Show a **scenario readiness indicator** in the header's `ScenarioChip`
  component — green dot for fully ready, amber for partially loaded, red for
  missing critical resources.
- Display a **non-blocking banner** at the top of the Investigate tab if the
  active scenario is missing agents: "Agents not provisioned — open Settings
  to provision."

**Plan item affected:** Phase 11 + Phase 12 (the `GET /api/config/resources`
endpoint already has the metadata to drive this).

---

### 1.3 No Scenario Comparison or Preview (Nice-to-have)

**What the plan says:** Phase 13 migrates telco-noc to config. Future scenarios
require only a new config file.

**Problem:** As the number of scenarios grows, users need to understand what
each scenario contains before switching. Currently the only metadata visible in
the scenario list is the name.

**Suggestion:**
- In the Settings modal's Scenarios tab, expand each scenario card to show
  `display_name`, `description`, `domain`, agent count, and data source types
  (read from the scenario config stored in Phase 8).
- Add a **preview tooltip** or expandable accordion rather than requiring the
  user to select a scenario to see what it contains.

---

## Category 2: Upload & Provisioning UX

### 2.1 Upload Progress Lacks Context for Multi-Stage Ingest (Critical)

**What the plan says:** Phases 5–6 restructure the ingest pipeline. Phase 8
adds config validation during upload. Phase 13 adds `_normalize_manifest()`.

**Problem:** The current upload flow shows a single progress bar per upload
card. But the ingest pipeline is actually multi-stage: parse YAML → validate
config → create Cosmos containers → load data → create search indexes. If
validation fails at stage 2, the user sees a vague "Error" state with no
indication of what went wrong or how to fix it.

**Suggestion:**
- Replace the single progress bar with a **multi-step progress indicator**
  showing the current stage (e.g., "Validating config…", "Creating graph
  resource…", "Loading vertices 42/300…", "Indexing documents…").
- The SSE events already carry `category` and `message` fields — surface
  the `category` as a stage label above the progress bar.
- On validation failure (Phase 8's `ConfigValidationError`), show the
  specific error messages returned by `validate_scenario_config()` in a
  scrollable error panel within the upload card, not just a generic "Error".

**Plan item affected:** Phase 8 (config validation) + Phase 5 (blob
extraction) — the backend already emits granular SSE events; the frontend
just needs to surface them better.

---

### 2.2 Provisioning Flow is Buried in Settings Modal (Important)

**What the plan says:** Phase 8 changes provisioning to read from scenario
config. Currently triggered via "Re-provision Agents" button in the Data
Sources tab of the Settings modal.

**Problem:** Agent provisioning is a critical step — without it, investigations
don't work. But it's hidden behind Settings → Data Sources tab → scroll down →
button. New users may not discover it. The existing `ProvisioningBanner`
component appears in the main UI during provisioning, but there's no call-to-
action to *start* provisioning from the main UI.

**Suggestion:**
- When a scenario is selected but agents are not provisioned (or stale), show a
  **persistent banner** in the Investigate tab: "Agents need provisioning for
  this scenario" with a primary "Provision Now" button that triggers provisioning
  directly — no need to navigate to the Settings modal.
- After switching scenarios, auto-check if agents match the scenario config. If
  not, show the banner automatically.
- The `ProvisioningBanner` component already exists — extend it to also serve
  as a prompt when provisioning is needed, not just during provisioning.

---

### 2.3 No Upload Drag-and-Drop Guidance (Nice-to-have)

**What the plan says:** The Settings modal Upload tab has file upload cards.

**Problem:** The upload cards use basic drag-and-drop boxes but don't indicate
what file formats are expected (`.tar.gz`), what the tarball should contain, or
size limits. Users creating custom scenarios won't know how to structure their
data packs without reading documentation.

**Suggestion:**
- Add a **help icon** or expandable "?" section on each upload card with format
  requirements: "Upload a .tar.gz containing scenario.yaml, graph_schema.yaml,
  and data/ directory."
- Link to an in-app help page or external docs for scenario pack structure.
- Show **file type validation** immediately on drop — reject non-`.tar.gz` files
  with a clear message rather than waiting for the backend to fail.

---

## Category 3: Resource Visualizer UX

### 3.1 Resource Visualizer Needs Loading & Error States (Critical)

**What the plan says:** Phase 12 swaps mock data for a real API call to
`GET /api/config/resources`. The current `useResourceGraph.ts` falls back to
mock data on fetch error.

**Problem:** The plan's fallback-to-mock pattern means errors are invisible.
If the API is down or the scenario has no config, the user sees mock data
without realizing it's not real. The existing "Mock data" badge is a
development artifact — it will be removed, but no replacement error state is
defined.

**Suggestion:**
- Add three explicit states: **Loading** (skeleton/spinner while fetching),
  **Error** (message with retry button), **Empty** ("Select a scenario to view
  its resource graph" — already mentioned in the plan but not in any code).
- Do NOT fall back to mock data in production. Mock data should only be used
  when `GRAPH_BACKEND=mock` or in development builds. In production, an API
  failure should show the error state.
- Add a subtle **"Last updated: X seconds ago"** timestamp or refresh button
  to indicate data freshness.

---

### 3.2 Resource Visualizer Node Interaction is View-Only (Important)

**What the plan says:** The Resource Visualizer shows agents, tools, data
sources, and infrastructure with hover tooltips and type filtering.

**Problem:** The visualizer is read-only — there's no way to drill into a
node for details or take action. For a tool like this to be useful in
operations, users need to:
- Click an agent node → see its prompt, model, connected agents, last
  provisioned time.
- Click a data source → see its connection status, document count, last
  ingested time.
- Click an infrastructure node → see its endpoint, region, SKU.

**Suggestion:**
- Add a **detail panel** (slide-in sidebar or modal) that appears when a node
  is clicked. Contents vary by node type:
  - Agent: name, model, role, connected agents, prompt preview (first 200
    chars), provisioned status
  - Data source: connector type, database/container, record count (if
    available from API)
  - Tool: type (OpenAPI / AzureAISearch), spec template, target endpoint
  - Infrastructure: endpoint URL, region, resource group
- The `GET /api/config/resources` endpoint should include enough `meta` fields
  to populate this panel without extra API calls.
- This can be a follow-up enhancement — but the data model (`meta` field in
  resource nodes) should be designed with this in mind **now** in Phase 12.

---

### 3.3 6-Layer Y-Force Layout May Not Scale (Nice-to-have)

**What the plan says:** `ResourceCanvas.tsx` uses a 6-layer Y-force to
stratify nodes vertically (Agent → Tool → Data source → Upload/DB →
Database → Infrastructure).

**Problem:** With hardcoded 28 nodes the layout works. But a custom scenario
with 10+ agents, each with 2–3 tools, would produce 50+ nodes. Force-directed
layouts degrade at that scale — nodes overlap, labels collide, and the graph
becomes unreadable.

**Suggestion:**
- Add a **layout toggle** between force-directed and a structured
  **hierarchical/tree layout** (e.g., dagre or ELK). Hierarchical layouts
  handle stratified graphs much better at scale.
- Alternatively, add **collapse/expand** on agent nodes — clicking an agent
  toggles visibility of its tool and data-source subtree, reducing visual
  clutter.
- Show a **node count warning** when the graph exceeds ~40 nodes: "Large
  graph — consider filtering by type to improve readability."

---

## Category 4: Investigation Experience

### 4.1 Agent Names in Timeline Should Be Human-Readable (Important)

**What the plan says:** Phase 11d makes agent names dynamic (read from
`agent_ids.json`). The `AgentTimeline` component shows agent steps as cards.

**Problem:** Config-driven agent names like `"GraphExplorerAgent"` are
developer-facing identifiers, not user-friendly labels. The timeline shows
these raw names. With custom scenarios, users might name agents anything —
`"KustoQueryAgent_v2"`, `"InventorySearchBot"` — and the timeline should
present them cleanly.

**Suggestion:**
- Add a `display_name` field to the agent definition in `scenario.yaml`
  (optional, defaults to `name`). Example:
  ```yaml
  - name: "GraphExplorerAgent"
    display_name: "Network Graph Explorer"
  ```
- In the `AgentTimeline` and `StepCard` components, display the
  `display_name` and show the technical `name` in a tooltip or smaller
  subtitle.
- Apply the same pattern in the Resource Visualizer — node labels should
  use `display_name` when available.

**Plan item affected:** Phase 8 (agent YAML schema) — add optional
`display_name` field. Phase 11d (stub agents) — surface it in the API
response.

---

### 4.2 Example Questions Should Be Context-Aware (Important)

**What the plan says:** `ScenarioInfoPanel` and `AlertInput` source example
questions from the scenario's `example_questions` list.

**Problem:** The plan stores `example_questions` in `scenario.yaml` as a
flat list. But in a real ops scenario, questions become more or less relevant
based on context — e.g., after graph data is loaded, graph-related questions
are relevant; before telemetry is loaded, telemetry questions would fail.

**Suggestion:**
- Tag example questions with their required data sources:
  ```yaml
  example_questions:
    - text: "What caused the alert storm?"
      requires: [telemetry]
    - text: "Which services are affected?"
      requires: [graph]
  ```
- In the UI, gray out / hide questions whose required data sources aren't
  loaded yet. This acts as implicit guidance for what the user should upload.
- Lower priority: this can be a V10+ enhancement; the basic flat list works
  for V9.

---

### 4.3 No Investigation Context When Switching Scenarios (Nice-to-have)

**Problem:** If a user switches scenarios mid-investigation, the investigation
panel doesn't reset — it shows stale steps from the previous scenario. The
interaction sidebar doesn't filter by scenario (it shows all history), which
gets confusing with multiple scenarios.

**Suggestion:**
- Clear (or archive) the current investigation state on scenario switch.
  Show a confirmation if an investigation is in progress.
- Add a **scenario filter** to the `InteractionSidebar` — show a chip per
  scenario and let users filter history by scenario. Currently the sidebar
  shows a scenario badge per interaction but doesn't offer filtering.

---

## Category 5: Accessibility & General Polish

### 5.1 Tab Bar Missing ARIA Semantics (Critical for Accessibility)

**What the plan says:** Phase 11 modifies the tab system but doesn't address
accessibility.

**Problem:** The 3-tab navigation (`TabBar.tsx`) uses `<button>` elements
without `role="tablist"`, `role="tab"`, or `aria-selected` attributes. Screen
readers cannot identify the tab structure. This is a WCAG 2.1 Level A failure
(4.1.2 Name, Role, Value).

**Suggestion:**
- Wrap the tab buttons in a container with `role="tablist"`.
- Each button gets `role="tab"`, `aria-selected={isActive}`, and a unique
  `aria-controls` referencing the tab panel.
- The tab content panel gets `role="tabpanel"` and `aria-labelledby`
  referencing its tab.
- This is a minimal change (~10 lines) that should be included in Phase 11.

---

### 5.2 Keyboard Shortcuts for Power Users (Important)

**Problem:** The application has no keyboard shortcuts. For an operational
tool used during incident investigations, speed matters.

**Suggestion — add global keyboard shortcuts:**
| Shortcut | Action |
|----------|--------|
| `Ctrl+Enter` | Submit investigation (when alert input is focused) |
| `Ctrl+1/2/3` | Switch tabs (Investigate / Info / Resources) |
| `Ctrl+,` | Open Settings modal |
| `Escape` | Close modal / cancel investigation |

- Register shortcuts via a `useHotkeys` hook or `keydown` listener on
  `document`.
- Show a **keyboard shortcut help** tooltip on `?` key press (common
  pattern in web tools).

---

### 5.3 Destructive Actions Need Consistent Confirmation (Important)

**Problem:** Scenario deletion has a 2-step confirmation popup, but
interaction deletion in the sidebar is single-click with no confirmation. Both
are destructive actions with different UX treatment.

**Suggestion:**
- Apply the same confirmation pattern to interaction deletion: hover-reveal
  delete button → click → inline "Are you sure?" with Confirm/Cancel.
- Alternatively, add an **undo toast** pattern: delete immediately, show a
  5-second "Interaction deleted — Undo" toast. If the user doesn't undo,
  the deletion persists. This is faster than confirmation dialogs for
  high-frequency actions.

---

### 5.4 SettingsModal is 674 Lines — Component Decomposition (Nice-to-have)

**Problem:** The Settings modal is the largest component (674 lines) and handles
3 tabs with very different concerns (scenario CRUD, data source configuration,
file uploads). This makes it hard to maintain and test.

**Suggestion:**
- Split into `ScenariosTab.tsx`, `DataSourcesTab.tsx`, and `UploadTab.tsx`
  sub-components. The Settings modal becomes a thin shell (~50 lines) that
  renders the active sub-tab.
- This decomposition aligns naturally with Phase 11's changes — the Data
  Sources tab is being modified to be config-aware, making it a good time to
  extract it.

---

### 5.5 No Global Toast/Notification System (Nice-to-have)

**Problem:** Success and error feedback is scattered: upload progress is inline
in the modal, provisioning feedback is in a banner, investigation errors are in
the investigation panel. There's no global notification mechanism.

**Suggestion:**
- Add a lightweight **toast provider** (e.g., `react-hot-toast` or a custom
  implementation) for cross-cutting notifications:
  - "Scenario uploaded successfully"
  - "Agents provisioned (5 agents, 4.2s)"
  - "Failed to connect to Graph API"
- Keep inline progress for long-running operations (uploads, provisioning)
  but use toasts for completion/failure summaries that should be visible
  regardless of which modal or tab the user is on.

---

### 5.6 Color Accessibility in Resource Visualizer (Nice-to-have)

**Problem:** The Resource Visualizer uses 12 distinct node colors. Several
pairs are perceptually similar for color-blind users (green `#22c55e` vs
emerald `#34d399`; blue `#3b82f6` vs cyan `#06b6d4`).

**Suggestion:**
- Reduce reliance on color alone — the shape-per-type system (circles,
  diamonds, rounded rects, hexagons) already helps. But there are only 4
  shapes for 12 types, so several types share the same shape.
- Add **text labels** or **icons inside nodes** to provide a secondary
  identification channel (the `graph_styles` YAML already has an `icon`
  field — render it).
- Run the color palette through a color-blindness simulator (e.g.,
  Coblis) and adjust any conflicting pairs.

---

## Summary Table

| # | Category | Severity | Suggestion | Plan Phase |
|---|----------|----------|------------|------------|
| 1.1 | Onboarding | Critical | First-run empty state + guided steps | 11 |
| 1.2 | Scenario Switching | Important | Scenario readiness indicator + health check | 11, 12 |
| 1.3 | Scenario Switching | Nice-to-have | Scenario preview cards | 11 |
| 2.1 | Upload/Provision | Critical | Multi-stage progress + validation errors | 5, 8 |
| 2.2 | Upload/Provision | Important | Provisioning CTA in main UI | 8, 11 |
| 2.3 | Upload/Provision | Nice-to-have | Upload format guidance / file validation | 11 |
| 3.1 | Resource Visualizer | Critical | Loading, error, empty states (no mock fallback) | 12 |
| 3.2 | Resource Visualizer | Important | Clickable nodes → detail panel | 12 |
| 3.3 | Resource Visualizer | Nice-to-have | Hierarchical layout + collapse/expand | 12 |
| 4.1 | Investigation | Important | `display_name` for agents | 8, 11 |
| 4.2 | Investigation | Important | Context-aware example questions | 11 |
| 4.3 | Investigation | Nice-to-have | Scenario-scoped investigation history | 11 |
| 5.1 | Accessibility | Critical | ARIA tablist/tab/tabpanel roles | 11 |
| 5.2 | Accessibility | Important | Keyboard shortcuts for power users | 11 |
| 5.3 | Accessibility | Important | Consistent destructive action confirmation | 11 |
| 5.4 | General Polish | Nice-to-have | Decompose SettingsModal (674 lines) | 11 |
| 5.5 | General Polish | Nice-to-have | Global toast/notification system | 11 |
| 5.6 | General Polish | Nice-to-have | Color-blind accessible visualizer palette | 12 |

---

## Recommended Priority

If only 5 items can be addressed in V9, prioritize these:

1. **1.1** — First-run empty state (without it, fresh deployments are a blank screen)
2. **5.1** — ARIA tab semantics (tiny effort, fixes a real accessibility gap)
3. **2.1** — Multi-stage upload progress (prevents user confusion on errors)
4. **3.1** — Resource Visualizer loading/error states (prevents silent failures)
5. **4.1** — Agent `display_name` (small schema addition with outsized UX impact)
