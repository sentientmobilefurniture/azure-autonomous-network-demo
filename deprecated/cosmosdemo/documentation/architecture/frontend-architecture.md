# Frontend Architecture

## Provider Tree & Layout

```
<React.StrictMode>
  <ScenarioProvider>                    ← Global context (scenario + provisioning state + graph styles)
    <App>                               ← useInvestigation() + useInteractions() hooks
      │                                    Startup overlay: AnimatePresence while !scenarioReady
      ├── <Header>                      ← Fixed 48px top bar
      │   ├── <ScenarioChip>            ← Flyout dropdown: scenario switching + "+ New Scenario" + backend badges (V11)
      │   ├── <HealthDot label="API">   ← Polls /health every 15s
      │   ├── Dynamic agent status      ← "5 Agents ✓" / "Provisioning..." / "Error"
      │   │                                (needs-provisioning falls through to default green dot)
      │   ├── <SettingsModal>           ← useScenarios(), useScenarioContext(), useFabricDiscovery() (V11)
      │   └── <ProvisioningBanner>      ← Rendered inside Header; handles provisioning + needs-provisioning
      ├── <TabBar>                      ← "▸ Investigate" | "ℹ Scenario Info" | "🔗 Resources" tabs
      │
      ├── [activeTab === 'investigate']
      │   ├── [!activeScenario]
      │   │   └── <EmptyState>              ← First-run onboarding: 4-step guide (upload → select → provision → investigate)
      │   ├── [activeScenario]
      │   │   ├── <MetricsBar>                  ← Vertically resizable panel (default 30%)
      │   │   │   ├── <GraphTopologyViewer>     ← useTopology(), owns overlay state
      │   │   │   │   ├── <GraphToolbar>        ← +nodeColorOverride + onSetColor props → useNodeColor()
      │   │   │   │   │   └── <ColorWheelPopover>  ← Opens on color dot click (HSL wheel + hex + presets)
      │   │   │   │   ├── <GraphCanvas>         ← useNodeColor() + scenario-driven sizes
      │   │   │   │   ├── <GraphTooltip>        ← +nodeColorOverride prop → useNodeColor()
      │   │   │   │   └── <GraphContextMenu>    ← Right-click menu (uses shared COLOR_PALETTE)
      │   │   │   └── <TabbedLogStream>             ← Tabs: "API" (/api/logs) + "Graph API" (/query/logs)
      │   │   │       └── <LogStream> (×2)          ← Both kept mounted for SSE continuity
      │   │   ├── <InvestigationPanel>          ← Sources example questions from useScenarios()
      │   │   │   ├── <AlertInput>              ← Textarea + submit button + example question chips
      │   │   │   ├── <AgentTimeline>
      │   │   │   │   ├── <StepCard> (×n)
      │   │   │   │   └── <ThinkingDots>
      │   │   │   └── <ErrorBanner>
      │   │   ├── <DiagnosisPanel>              ← ReactMarkdown rendering
      │   │   ├── <InteractionSidebar>          ← Collapsible right sidebar: saved investigation history
      │   │   │                                    useInteractions() for CRUD; auto-saves on completion;
      │   │   │                                    click to replay past investigation
      │   │   └── <AddScenarioModal>            ← Opened from ScenarioChip or SettingsModal
      │
      ├── [activeTab === 'info']
      │   └── <ScenarioInfoPanel>           ← Fetches savedScenarios on mount; shows description, use cases, example questions
      │       └── onClick(question) → setAlert(q), switch to 'investigate' tab
      │
      └── [activeTab === 'resources']
          └── <ResourceVisualizer>          ← Full-width resource/agent topology graph
              ├── <ResourceToolbar>         ← Type-filter chips, search, pause/play, zoom-to-fit, node/edge counts
              ├── <ResourceCanvas>          ← react-force-graph-2d with custom shapes (circle, diamond, round-rect, hexagon)
              └── <ResourceTooltip>         ← Animated tooltip on node/edge hover
```

**Tab system:** `type AppTab = 'investigate' | 'info' | 'resources'`.

Layout uses `react-resizable-panels` with vertical orientation: MetricsBar (30%) | InvestigationPanel + DiagnosisPanel + InteractionSidebar (70% side-by-side).

## ScenarioContext (React Context)

```typescript
// Discriminated union for provisioning status tracking
type ProvisioningStatus =
  | { state: 'idle' }
  | { state: 'needs-provisioning'; scenarioName: string }  // NEW — agents not yet created
  | { state: 'provisioning'; step: string; scenarioName: string }
  | { state: 'done'; scenarioName: string }
  | { state: 'error'; error: string; scenarioName: string };

interface ScenarioState {
  activeScenario: string | null;    // Saved scenario name, or null for custom/manual mode
  activeGraph: string;              // e.g. "telco-noc-topology" (default: "topology")
  activeRunbooksIndex: string;      // default: "runbooks-index"
  activeTicketsIndex: string;       // default: "tickets-index"
  activePromptSet: string;          // Prompt scenario name (default: "")
  provisioningStatus: ProvisioningStatus; // Agent provisioning state (5 states)
  scenarioReady: boolean;           // NEW — false during startup validation of persisted scenario
  scenarioNodeColors: Record<string, string>;  // Graph style: node label → hex color
  scenarioNodeSizes: Record<string, number>;   // Graph style: node label → size
  setActiveScenario(name: string | null, scenario?: SavedScenario): void; // Optional saved scenario for exact resource names
  setActiveGraph(g: string): void;
  setActiveRunbooksIndex(i: string): void;
  setActiveTicketsIndex(i: string): void;
  setActivePromptSet(name: string): void;
  setProvisioningStatus(status: ProvisioningStatus): void;
  setScenarioStyles(styles: { node_types?: Record<string, { color: string; size: number }> } | null): void;
  getQueryHeaders(): Record<string, string>;  // { "X-Graph": activeGraph }
}
```

**Auto-derivation logic** — when `setActiveScenario(name, scenario?)` is called:
- If `scenario?.resources` provided: uses exact resource names from saved scenario
- Otherwise: derives `activeGraph = "{name}-topology"`, `activeRunbooksIndex = "{name}-runbooks-index"`, etc.
- When called with `null` (custom mode): existing individual bindings are left as-is

**`scenarioReady`** — on mount, validates the persisted `activeScenario` against Cosmos
(with 5s timeout). App shows an `AnimatePresence` overlay until ready. This prevents
rendering stale scenario state before validation completes.

**`needs-provisioning` flow** — detected by `ProvisioningBanner` (not ScenarioContext):
1. On `activeScenario` change, banner fetches `GET /api/agents`
2. If `agents.length === 0`, sets `provisioningStatus` to `{ state: 'needs-provisioning', scenarioName }`
3. Banner shows amber ⚠ bar with "Provision Now" button
4. Clicking button triggers `POST /api/config/apply` SSE flow → `provisioning` → `done`

**localStorage persistence**: `activeScenario` is persisted to and restored from
`localStorage` on mount. On page refresh, all bindings are re-derived from the
persisted scenario name. This does NOT re-trigger agent provisioning — agents are
long-lived in AI Foundry. It only restores frontend state so `X-Graph` headers
and UI indicators are correct. Scenario graph styles (`scenarioNodeColors`, `scenarioNodeSizes`)
are NOT persisted to localStorage — they are re-populated from saved scenario data when
`selectScenario()` runs.

`getQueryHeaders()` is memoized on `activeGraph`. It's consumed by `useInvestigation` and `useTopology`.

**Critical**: Only `activeGraph` generates an HTTP header (`X-Graph`). `activeRunbooksIndex` and `activeTicketsIndex` are NOT sent as headers — they're only passed in the `POST /api/config/apply` body.

**ProvisioningStatus** is defined and exported from `ScenarioContext.tsx` (co-located
with `ScenarioState` to avoid circular dependencies). It is a discriminated union type
for better TypeScript narrowing than a flat interface.

## TypeScript Types (`types/index.ts`)

```typescript
// --- Investigation types ---
interface StepEvent {
  step: number;
  agent: string;
  duration?: string;    // "2.3s"
  query?: string;
  response?: string;    // Markdown
  error?: boolean;      // True if step failed
}

interface ThinkingState {
  agent: string;
  status: string;       // "processing...", "querying graph", etc.
}

interface RunMeta {
  steps: number;
  time: string;         // "42s"
}

// --- Scenario management types ---
interface SavedScenario {
  id: string;               // scenario name (e.g. "cloud-outage")
  display_name: string;
  description: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  graph_connector?: string;     // V11: "cosmosdb-gremlin" | "fabric-gql" | "mock" — determines backend
  resources: {
    graph: string;                // "cloud-outage-topology"
    telemetry_database: string;   // "cloud-outage-telemetry"
    runbooks_index: string;       // "cloud-outage-runbooks-index"
    tickets_index: string;        // "cloud-outage-tickets-index"
    prompts_database: string;     // "cloud-outage-prompts"
    telemetry_container_prefix?: string;  // NEW — per-scenario container prefix
    prompts_container?: string;           // NEW — per-scenario prompts container
  };
  upload_status: Record<string, {
    status: string;
    timestamp: string;
    [key: string]: unknown;       // vertices, edges, containers, etc.
  }>;
  graph_styles?: {                // Scenario-driven graph visualization styles
    node_types?: Record<string, { color: string; size: number; icon?: string }>;
  };
  use_cases?: string[];           // Scenario use case descriptions
  example_questions?: string[];   // Clickable example investigation prompts
  domain?: string;                // Scenario domain (e.g. "telecommunications")
}

// V11: Fabric workspace resource item
interface FabricItem {
  id: string;
  display_name: string;
  type: string;
  description?: string;
}

type SlotKey = 'graph' | 'telemetry' | 'runbooks' | 'tickets' | 'prompts';

type SlotStatus = 'empty' | 'staged' | 'uploading' | 'done' | 'error';

interface ScenarioUploadSlot {
  key: SlotKey;
  label: string;
  icon: string;
  file: File | null;
  status: SlotStatus;
  progress: string;
  pct: number;
  result: Record<string, unknown> | null;
  error: string | null;
}

// --- Resource graph types (V10) ---
type ResourceNodeType =
  | 'agent' | 'orchestrator' | 'tool'            // Agent layer
  | 'datasource' | 'search-index'                // Data layer
  | 'foundry' | 'storage' | 'cosmos-account'     // Infrastructure layer
  | 'search-service' | 'container-app'
  | 'blob-container' | 'cosmos-database';

interface ResourceNode {
  id: string;
  label: string;
  type: ResourceNodeType;
  meta?: Record<string, string>;
}

type ResourceEdgeType =
  | 'delegates_to' | 'uses_tool' | 'queries'     // Agent flow
  | 'stores_in' | 'hosted_on' | 'indexes_from'   // Infrastructure
  | 'runs_on' | 'contains';

interface ResourceEdge {
  source: string;
  target: string;
  type: ResourceEdgeType;
  label: string;
}
```

**ProvisioningStatus** type is defined in `ScenarioContext.tsx` (not in `types/index.ts`)
to avoid circular dependency. See [ScenarioContext](#scenariocontext-react-context) above.

Additional types in hooks (not in shared types file):

```typescript
// useTopology.ts
interface TopologyNode {
  id: string;
  label: string;
  properties: Record<string, unknown>;
  x?: number; y?: number;           // force-graph internal
  fx?: number; fy?: number;         // pinned position
}
interface TopologyEdge {
  id: string;
  source: string | TopologyNode;    // string before hydration, object after
  target: string | TopologyNode;
  label: string;
  properties: Record<string, unknown>;
}
interface TopologyMeta {
  node_count: number;
  edge_count: number;
  query_time_ms: number;
  labels: string[];
}

// useScenarios.ts
interface ScenarioInfo {
  graph_name: string;
  vertex_count: number;
  has_data: boolean;
}
interface SearchIndex {
  name: string;
  type: 'runbooks' | 'tickets' | 'other';
  document_count: number | null;
  fields: number;
}
```

## Hooks

| Hook | Returns | Key Behaviors |
|------|---------|---------------|
| `useInvestigation()` | `{alert, setAlert, steps, thinking, finalMessage, errorMessage, running, runStarted, runMeta, submitAlert}` | Aborts prior SSE stream; 5min auto-abort timeout; uses refs for step counter (closure capture issue); injects `X-Graph` header |
| `useTopology()` | `{data, loading, error, refetch}` | Auto-refetches when `getQueryHeaders` changes (activeGraph change triggers `useEffect`); aborts prior in-flight request |
| `useScenarios()` | `{scenarios, indexes, savedScenarios, loading, error, fetchScenarios, fetchIndexes, fetchSavedScenarios, saveScenario, deleteSavedScenario, selectScenario}` | `fetchScenarios()` → GET `/query/scenarios`; `fetchIndexes()` → GET `/query/indexes` (failure non-fatal); `fetchSavedScenarios()` → GET `/query/scenarios/saved`; `selectScenario(name)` → auto-provisions agents via `consumeSSE` + updates `provisioningStatus` + pushes `graph_styles` into context |
| `useInteractions()` | `{interactions, loading, fetchInteractions, saveInteraction, deleteInteraction}` | `fetchInteractions()` → GET `/query/interactions?scenario=X&limit=50`; auto-fetches on mount and `activeScenario` change; `saveInteraction()` called automatically when investigation completes (running→false with finalMessage); `deleteInteraction()` → DELETE `/query/interactions/{id}` |
| `useNodeColor(nodeColorOverride)` | `(label: string) => string` | Centralised color resolution hook — 4-tier fallback: `nodeColorOverride → scenarioNodeColors → NODE_COLORS → autoColor`. Uses a 12-color auto-palette with stable string hash for unknown labels |
| `useResourceGraph()` | `{nodes, edges, loading, error}` | **NEW (V10)** — fetches `GET /api/config/resources`; re-fetches on `activeScenario` change and when `provisioningStatus.state === 'done'`; returns typed `ResourceNode[]` + `ResourceEdge[]` for the resource visualizer |
| `useFabricDiscovery()` | `{healthy, checking, ontologies, graphModels, eventhouses, loadingSection, error, provisionPct, provisionStep, provisionState, provisionError, checkHealth, fetchOntologies, fetchGraphModels, fetchEventhouses, runProvisionPipeline, fetchAll}` | **NEW (V11)** — Fabric workspace discovery: health check (`/query/fabric/health`), list ontologies/graph models/eventhouses, run provision pipeline (`/api/fabric/provision/pipeline`) with SSE progress tracking. Used by SettingsModal Fabric tab |

**`selectScenario(name)` flow** (in `useScenarios`):
1. Calls `setActiveScenario(name)` → auto-derives all bindings
2. Looks up saved scenario's `graph_styles` and calls `setScenarioStyles()` to push colors/sizes into context
3. Sets `provisioningStatus` to `{ state: 'provisioning', step: 'Starting...', scenarioName: name }`
4. POSTs to `/api/config/apply` with `{graph, runbooks_index, tickets_index, prompt_scenario}`
4. Consumes SSE stream via shared `consumeSSE()` utility from `utils/sseStream.ts`
5. Updates `provisioningStatus.step` on each progress event
6. On complete: sets `provisioningStatus` to `{ state: 'done', scenarioName: name }`
7. On error: sets `provisioningStatus` to `{ state: 'error', error: msg, scenarioName: name }`
8. After 3 seconds of 'done', auto-resets to `{ state: 'idle' }`

**Note:** Uses native `fetch()` + `ReadableStream` via `consumeSSE()` — NOT `@microsoft/fetch-event-source`. This is deviation D-1 from the SCENARIOHANDLING plan. Native fetch works correctly with POST + SSE and aligns with the shared utility pattern.

## All Frontend API Calls

| Endpoint | Method | Headers | Trigger | Consumer |
|----------|--------|---------|---------|----------|
| `/api/alert` | POST | `Content-Type: application/json` + `X-Graph` | User clicks "Investigate" | `useInvestigation` |
| `/query/topology` | POST | `Content-Type: application/json` + `X-Graph` | On mount, graph change, manual refresh, "Load Topology" | `useTopology` / `SettingsModal` |
| `/query/scenarios` | GET | — | Settings modal opens | `useScenarios` |
| `/query/scenarios/saved` | GET | — | Settings modal opens, ScenarioChip mount, after save/delete | `useScenarios` |
| `/query/scenarios/save` | POST | `Content-Type: application/json` | After all 5 uploads complete in AddScenarioModal | `useScenarios` |
| `/query/scenarios/saved/{name}` | DELETE | — | Delete scenario from Scenarios tab ⋮ menu | `useScenarios` |
| `/query/indexes` | GET | — | Settings modal opens | `useScenarios` |
| `/query/prompts/scenarios` | GET | — | Settings modal opens | `SettingsModal` |
| `/query/upload/graph` | POST | multipart/form-data | Upload box or AddScenarioModal | `UploadBox` / `AddScenarioModal` |
| `/query/upload/telemetry` | POST | multipart/form-data | Upload box or AddScenarioModal | `UploadBox` / `AddScenarioModal` |
| `/query/upload/runbooks` | POST | multipart/form-data | Upload box or AddScenarioModal | `UploadBox` / `AddScenarioModal` |
| `/query/upload/tickets` | POST | multipart/form-data | Upload box or AddScenarioModal | `UploadBox` / `AddScenarioModal` |
| `/query/upload/prompts` | POST | multipart/form-data | Upload box or AddScenarioModal | `UploadBox` / `AddScenarioModal` |
| `/api/config/apply` | POST | `Content-Type: application/json` | "Provision Agents" button, `selectScenario()` auto-provision, or ProvisioningBanner "Provision Now" | `SettingsModal` / `useScenarios` / `ProvisioningBanner` |
| `/api/config/resources` | GET | — | Resources tab mount, `activeScenario` change, provisioning done | `useResourceGraph` |
| `/api/agents` | GET | — | `activeScenario` change (checks if agents provisioned) | `ProvisioningBanner` |
| `/query/interactions` | GET | — | On mount, `activeScenario` change | `useInteractions` |
| `/query/interactions` | POST | `Content-Type: application/json` | Auto-save when investigation completes | `useInteractions` |
| `/query/interactions/{id}` | DELETE | — | Delete from InteractionSidebar | `useInteractions` |
| `/health` | GET | — | Every 15s polling | `HealthDot` |
| `/api/logs` | GET (EventSource) | — | On mount | `LogStream` |
| `/query/fabric/health` | GET | — | Fabric Setup tab opens | `useFabricDiscovery` |
| `/query/fabric/ontologies` | GET | — | Fabric Setup tab opens | `useFabricDiscovery` |
| `/query/fabric/ontologies/{id}/models` | GET | — | User selects ontology | `useFabricDiscovery` |
| `/query/fabric/eventhouses` | GET | — | Fabric Setup tab opens | `useFabricDiscovery` |
| `/api/fabric/provision/pipeline` | POST | `Content-Type: application/json` | "Provision Pipeline" button | `useFabricDiscovery` |

**Note on AddScenarioModal uploads:** When triggered from AddScenarioModal, each upload
appends `?scenario_name=X` to the URL to override the tarball's `scenario.yaml` name.
Uses the shared `uploadWithSSE()` utility from `utils/sseStream.ts`.

## SettingsModal — 4 Tabs

**Scenarios tab (first tab):**
- Lists saved scenarios as cards from `GET /query/scenarios/saved`
- Each card shows: scenario name, display name, vertex/prompt/index counts, timestamps
- Click a card → activates that scenario (same as `selectScenario()`) + auto-provisions
- Active scenario shows green "Active" badge; inactive scenarios show `○` radio dot
- ⋮ menu per card: "Delete scenario" with inline confirmation
- "+New Scenario" button → opens `AddScenarioModal`
- Empty state: "No scenarios yet — Click '+New Scenario' to create your first scenario"

**Data Sources tab:**
- When a saved scenario is active: shows read-only bindings (auto-derived from name)
  with "Re-provision Agents" button and timestamp of last provisioning
- When in Custom mode (no scenario): shows individual dropdowns for graph, runbooks,
  tickets, prompt set + "Load Topology" and "Provision Agents" buttons (same as before)
- GraphExplorer Agent → dropdown of `ScenarioInfo[]` where `has_data === true` → sets `activeGraph`
- Telemetry Agent → auto-derived display: `activeGraph.substring(0, activeGraph.lastIndexOf('-')) + '-telemetry'`
- RunbookKB Agent → dropdown of `SearchIndex[]` where `type === 'runbooks'` → sets `activeRunbooksIndex`
- HistoricalTicket Agent → dropdown of `SearchIndex[]` where `type === 'tickets'` → sets `activeTicketsIndex`
- Prompt Set → dropdown from `GET /query/prompts/scenarios` → sets `activePromptSet`

**Upload tab:**
- Loaded Data section: lists graphs where `has_data === true`
- 5 UploadBox components: Graph Data, Telemetry, Runbooks, Tickets, Prompts
- Each uses `uploadWithSSE()` from `utils/sseStream.ts`: drag-drop → upload → SSE progress bar → done/error state machine
- For ad-hoc individual uploads outside the scenario workflow

**Fabric Setup tab (V11 — conditional, only shown when active scenario uses `fabric-gql`):**
- Conditionally visible: only appears when `activeScenarioRecord?.graph_connector === 'fabric-gql'`
- Workspace health status card (calls `/query/fabric/health`)
- Ontology selector dropdown (populated from `/query/fabric/ontologies`)
- Graph Model list (populated from `/query/fabric/ontologies/{id}/models` on ontology select)
- Eventhouse list (populated from `/query/fabric/eventhouses`)
- "Provision Pipeline" button → calls `POST /api/fabric/provision/pipeline` with SSE progress bar
- Uses `useFabricDiscovery()` hook for all API calls and state management

**Modal behavior:** Closes on Escape keypress and backdrop click (except during active
upload/provisioning). Uses `aria-modal="true"` and `role="dialog"` attributes.

## Graph Viewer Architecture

`GraphTopologyViewer` owns all overlay state and delegates rendering:

| Component | Role |
|-----------|------|
| `GraphCanvas` | `forwardRef` wrapper around `react-force-graph-2d`. Uses `useNodeColor()` hook for color resolution (replaces direct `NODE_COLORS` lookup). Scenario-driven node sizes via `scenarioNodeSizes` from context (normalised by `/3`). Exposes `zoomToFit()` via `useImperativeHandle`. |
| `GraphToolbar` | Label filter chips (split click targets: text toggles filter, dot opens `ColorWheelPopover`), node search input, node/edge counts, zoom-to-fit + refresh buttons. Accepts `nodeColorOverride` + `onSetColor` props; uses `useNodeColor()` for chip dot colors |
| `GraphTooltip` | Fixed-position tooltip on hover. Uses `framer-motion`. Accepts `nodeColorOverride` prop; uses `useNodeColor()` for dot color. Handles `source`/`target` as both string (before hydration) and object (after). |
| `GraphContextMenu` | Right-click menu: change display field (pick any property as label), change color (12-color palette from shared `COLOR_PALETTE`). Persisted to `localStorage` keys `graph-display-fields` and `graph-colors`. |
| `ColorWheelPopover` | HSL color wheel (hue ring + saturation/lightness square via canvas), hex code text input, and 12-color preset swatch row. Opens anchored below the toolbar dot. Apply button commits; click-outside closes. No external dependencies — pure canvas API. |
| `graphConstants.ts` | `NODE_COLORS`, `NODE_SIZES` maps keyed by vertex label (static defaults; overridden by scenario-driven values when available), and shared `COLOR_PALETTE` (12-color array used by both `GraphContextMenu` and `ColorWheelPopover`) |

**Node color resolution** (via `useNodeColor` hook, ~42 lines):

The `useNodeColor(nodeColorOverride)` hook provides a single source of truth for all
graph node colors with a 4-tier fallback chain:

```
1. nodeColorOverride[label]    ← User right-click override (localStorage-persisted)
2. scenarioNodeColors[label]   ← Scenario-defined colors from graph_styles.node_types
3. NODE_COLORS[label]          ← Static defaults in graphConstants.ts
4. autoColor(label)            ← Deterministic auto-palette (12 colors, stable hash)
```

`GraphTopologyViewer` passes `nodeColorOverride` (from its state/localStorage) down to
`GraphToolbar`, `GraphTooltip`, and `GraphCanvas`. It also passes `onSetColor` to `GraphToolbar`
so color changes from both the toolbar color wheel popover and the right-click context menu
flow to the same `setNodeColorOverride` state setter. `GraphCanvas` also receives
`nodeColorOverride` and calls `useNodeColor()` directly.

## Resource Visualizer Architecture (V10)

`ResourceVisualizer` renders a force-directed graph of the scenario's agent/tool/data-source
topology, sourced from `GET /api/config/resources`. Self-contained — takes no props.

| Component | Role |
|-----------|------|
| `ResourceVisualizer` | Top-level container. Uses `useResourceGraph()` for data, `ResizeObserver` for container sizing. Manages pause/freeze, tooltip state, type/search filtering. Renders loading spinner, error overlay, and empty-state overlay as conditional overlays. |
| `ResourceCanvas` | `forwardRef` wrapper around `react-force-graph-2d`. Custom canvas rendering with 4 shape types per `ResourceNodeType`: **circle** (agent, orchestrator), **diamond** (tool), **round-rect** (datasource, search-index), **hexagon** (infrastructure types). Layered y-force groups nodes by type tier. Exposes `zoomToFit()` + `setFrozen()` via `ResourceCanvasHandle`. |
| `ResourceToolbar` | Filter chips by node type (using `RESOURCE_TYPE_LABELS`), search input, node/edge counts badge, pause/play toggle, zoom-to-fit button. |
| `ResourceTooltip` | Fixed-position animated tooltip. Node hover: shows type badge + meta key/value pairs. Edge hover: shows label, source→target, edge type. Uses `framer-motion`. |
| `resourceConstants.ts` | Central design tokens: `RESOURCE_NODE_COLORS` (12 types), `RESOURCE_NODE_SIZES`, `RESOURCE_EDGE_COLORS` (8 types), `RESOURCE_EDGE_DASH` (dash patterns), `RESOURCE_TYPE_LABELS` (human-readable labels for filter chips). |

Files live in `src/components/resource/` subdirectory, mirroring the `GraphTopologyViewer`
pattern but for infrastructure topology rather than network topology.

## Frontend Patterns & Gotchas

1. **AbortController pattern**: Every async hook stores an `AbortController` ref, aborts prior requests, ignores `AbortError` in catch blocks.

2. **Ref-based counters**: `useInvestigation` uses `stepCountRef` and `startTimeRef` as refs (not state) because the SSE `onmessage` closure captures stale state values. The `finally` block reads from refs.

3. **Three SSE consumption patterns**:
   - Investigation uses `@microsoft/fetch-event-source` (POST + named events)
   - LogStream uses native `EventSource` (GET-only)
   - Upload, provisioning, and scenario selection use the shared `consumeSSE()` utility from `utils/sseStream.ts` (native `fetch` + `ReadableStream` with manual `data:` line parsing)

4. **`openWhenHidden: true`**: On `fetchEventSource` — SSE stream continues in background tabs. Important for long investigations.

5. **Force-graph source/target mutation**: `TopologyEdge.source` and `.target` start as `string` (vertex id) but `react-force-graph-2d` mutates them in-place to `TopologyNode` objects. Code must handle both: `typeof e.source === 'string' ? e.source : e.source.id`.

6. **Unused components**: `AlertChart` and `MetricCard` exist in `src/components/` but are not imported by any parent component.

7. **`activePromptSet`** is now in `ScenarioContext` (previously was local state in `SettingsModal` — see SCENARIOHANDLING.md deviation D-4).

8. **ScenarioContext has localStorage persistence** for `activeScenario`: scenario selection survives browser refresh. All bindings are re-derived from the persisted scenario name on mount. Other individual bindings (`activeGraph`, etc.) are NOT independently persisted — they're derived. Graph styles (`scenarioNodeColors`, `scenarioNodeSizes`) are not localStorage-persisted — they reload from saved scenario data.

9. **UploadBox `onComplete` gap** — After uploading prompts, the Prompt Set dropdown is NOT auto-refreshed. User must close/reopen the modal. Graph upload triggers `fetchScenarios()`, Runbooks/Tickets trigger `fetchIndexes()`, but Prompts and Telemetry trigger nothing.

10. **UploadBox now uses `uploadWithSSE`** (V8 refactor): Previously hand-rolled SSE parsing; now uses the shared `uploadWithSSE()` utility from `utils/sseStream.ts`, eliminating a duplicate SSE parsing implementation.

11. **Tab navigation in App.tsx**: `activeTab` state (`'investigate' | 'info'`) controls whether the main content area shows the investigation layout (MetricsBar + InvestigationPanel + DiagnosisPanel) or the ScenarioInfoPanel. Clicking an example question in ScenarioInfoPanel calls `setAlert(q)` and switches to the investigate tab.

12. **Vite dev proxy has 5 entries**, not 3: `/api/alert` → :8000 (SSE configured), `/api/logs` → :8000 (SSE configured), `/api` → :8000 (plain), `/health` → :8000, `/query` → :8100 (SSE configured). The SSE-configured entries add `cache-control: no-cache` and `x-accel-buffering: no` headers — without these, SSE streams are buffered during local dev.

13. **`useInvestigation` stale closure bug** — `getQueryHeaders` is NOT in the `submitAlert` `useCallback` dependency array. If user switches `activeGraph` without changing alert text, the OLD `X-Graph` header is sent.

14. **Shared SSE utility pattern** (`utils/sseStream.ts`): Two exports:
    - `consumeSSE(response, handlers, signal?)` — Low-level: takes a `Response`, reads `ReadableStream`, parses `data:` lines, dispatches to `onProgress`/`onComplete`/`onError` handlers. Returns the last complete event payload.
    - `uploadWithSSE(endpoint, file, handlers, params?, signal?)` — High-level: takes a `File` (not `FormData`), builds `FormData` internally, appends optional `params` as URL query parameters, wraps `fetch` + `consumeSSE` for form upload endpoints
    - Completion detection uses heuristic field-checking (`scenario`, `index`, `graph`, `prompts_stored` keys in parsed JSON) because backend SSE streams use `data:` lines only, not `event:` type markers (deviation D-5)

15. **AddScenarioModal auto-slot detection**: `detectSlot(filename)` parses the last hyphen-separated segment before `.tar.gz` to match file to upload slot. E.g., `cloud-outage-graph.tar.gz` → slot `graph`, scenarioName `cloud-outage`. Auto-fills scenario name input if empty. Multi-file drop assigns all matching files in one gesture. On graph upload completion, captures `scenario_metadata` (display_name, description, use_cases, example_questions, graph_styles, domain) from the SSE response and stores it in a `scenarioMetadataRef`; these metadata fields are forwarded to `saveScenario()` when the user clicks Save. **V11:** Also detects `graph_connector` from uploaded manifest metadata (`scenario_metadata.graph_connector` or `scenario_metadata.data_sources.graph.connector`). When `fabric-gql` is detected, shows a cyan info banner: "Fabric Graph Connector Detected — graph data will be managed via Fabric". The `graph_connector` value is passed through `saveScenarioMeta()` → `useScenarios.saveScenario()` → `POST /query/scenarios/save` for persistence.

16. **ProvisioningBanner lifecycle**: Appears during provisioning **and** `needs-provisioning` state. Rendered inside `<Header>` (not as a sibling). During provisioning: shows current step from SSE stream, auto-dismisses 3s after completion with green flash. On error: banner turns red and stays until manually dismissed. On `needs-provisioning`: amber banner with ⚠ icon and "Provision Now" button → clicking triggers `POST /api/config/apply` SSE flow. Detection: on `activeScenario` change, fetches `GET /api/agents`; if `agents.length === 0`, transitions to `needs-provisioning`. Workspace remains interactive during provisioning — only "Submit Alert" is disabled.

17. **ScenarioChip flyout dropdown**: Shows saved scenarios + "(Custom)" option. Selecting triggers `selectScenario()` which auto-provisions. Small spinner inside chip during provisioning. "+ New Scenario" link at bottom opens AddScenarioModal. **V11:** Each scenario shows a color-coded backend badge: Fabric (cyan), Mock (yellow), Cosmos (emerald). Active chip also displays the badge next to the scenario name.

18. **Example question suggestion chips**: `InvestigationPanel` self-sources example questions from `useScenarios()` + `useScenarioContext()` (no prop threading through App.tsx needed). `AlertInput` accepts an optional `exampleQuestions` prop and renders suggestion chips between the textarea and submit button, but ONLY when the textarea is empty. Clicking a chip populates the textarea; chips auto-hide once the user types. This gives users the same quick-pick functionality as the ScenarioInfoPanel tab but at the point of input.

19. **ColorWheelPopover architecture**: Pure canvas-based HSL color picker. The hue ring is drawn as 360 arc segments with `hsl(angle, 100%, 50%)` fill. Inside the ring, a saturation (x-axis) × lightness (y-axis) square is drawn per-pixel. Drag interaction uses `mousedown` on the specific canvas, `mousemove`/`mouseup` on `window` to support dragging outside the canvas bounds. Hex input field with live preview dot; apply button commits. Preset swatch row shows the shared `COLOR_PALETTE` with a checkmark on the current color. Positioned via `anchorRect` (from `getBoundingClientRect()` of the toolbar dot), clamped to viewport left edge.

20. **ScenarioInfoPanel data loading fix**: `ScenarioInfoPanel` calls `useScenarios()` which initializes `savedScenarios` as `[]`. Without a `fetchSavedScenarios()` call, the array stays empty and the scenario lookup always fails → permanent empty state. Fixed by adding `useEffect(() => fetchSavedScenarios(), [])` on mount.
