# Architecture

## Demo built with assistance from Claude Opus 4.6 using the following [skills](https://github.com/microsoft/skills):
* azure-ai-projects-py — `~/references/skills/.github/skills/azure-ai-projects-py`
* hosted-agents-v2-py — `~/references/skills/.github/skills/hosted-agents-v2-py`
* mcp-builder — `~/references/skills/.github/skills/mcp-builder`
* azure-appconfiguration-py — `~/references/skills/.github/skills/azure-appconfiguration-py`
* azure-containerregistry-py — `~/references/skills/.github/skills/azure-containerregistry-py`
* fastapi-router-py (training data, no local reference)
* frontend-ui-dark-ts (training data, no local reference)

## System Overview

Multi-agent NOC diagnosis system. An alert enters via the frontend, flows through
a FastAPI backend that streams SSE progress, and reaches an orchestrator agent in
Azure AI Foundry. The orchestrator delegates to four specialist agents, each backed
by a distinct data source in Microsoft Fabric or Azure AI Search.

```
┌──────────────┐      POST /api/alert       ┌──────────────────┐
│   Frontend   │  ───────────────────────▶   │   FastAPI API    │
│  React/Vite  │  ◀─────── SSE stream ────  │   (uvicorn)      │
│  :5173       │                             │   :8000          │
└──────────────┘                             └────────┬─────────┘
                                                      │ azure-ai-agents SDK
                                                      ▼
                                          ┌───────────────────────┐
                                          │   Orchestrator Agent  │
                                          │   (Azure AI Foundry)  │
                                          └───┬───┬───┬───┬───────┘
                        ┌─────────────────────┘   │   │   └──────────────────────┐
                        ▼                         ▼   ▼                          ▼
              ┌─────────────────┐   ┌──────────────┐ ┌──────────────┐  ┌─────────────────┐
              │ GraphExplorer   │   │ Telemetry    │ │ RunbookKB    │  │ HistoricalTicket│
              │ Agent           │   │ Agent        │ │ Agent        │  │ Agent           │
              └────────┬────────┘   └──────┬───────┘ └──────┬───────┘  └────────┬────────┘
                       │ OpenApiTool       │ OpenApiTool     │ AI Search         │ AI Search
                       ▼                    ▼                ▼                   ▼
              ┌──────────────────┐   ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
              │ fabric-query-api │   │ fabric-query-api │  │ runbooks-    │  │ tickets-         │
              │ POST /query/     │   │ POST /query/     │  │ index        │  │ index            │
              │ graph (GQL)      │   │ telemetry (KQL)  │  │ (hybrid)     │  │ (hybrid)         │
              └────────┬─────────┘   └────────┬─────────┘  └──────────────┘  └──────────────────┘
                       │                      │
                       ▼                      ▼
              ┌──────────────┐   ┌───────────────┐
              │ Fabric       │   │ Fabric        │
              │ GraphModel   │   │ Eventhouse    │
              │ (GQL API)    │   │ (KQL/Kusto)   │
              └──────────────┘   └───────────────┘
```

---

## Project Structure

```
.
├── azure.yaml                  # azd project definition (hooks, service targets)
├── azure_config.env            # Runtime config — single source of truth (gitignored)
├── azure_config.env.template   # Checked-in template for azure_config.env
├── pyproject.toml              # Python deps for scripts/ (uv-managed)
│
├── infra/                      # Bicep IaC (deployed by `azd up`)
│   ├── main.bicep              # Subscription-scoped orchestrator
│   ├── main.bicepparam         # Reads env vars via readEnvironmentVariable()
│   └── modules/
│       ├── ai-foundry.bicep    # AI Foundry account + project + GPT deployment
│       ├── search.bicep        # Azure AI Search
│       ├── storage.bicep       # Storage account + blob containers
│       ├── fabric.bicep        # Fabric capacity (F-SKU)
│       ├── container-apps-environment.bicep  # Log Analytics + ACR + Managed Environment
│       ├── container-app.bicep              # Generic Container App (managed identity)
│       └── roles.bicep         # RBAC assignments
│
├── hooks/                      # azd lifecycle hooks
│   ├── preprovision.sh         # Syncs azure_config.env → azd env vars for Bicep
│   └── postprovision.sh        # Uploads data to blob, writes outputs → azure_config.env
│
├── data/                       # Source data (checked in)
│   ├── runbooks/               # Markdown runbook files → uploaded to blob → AI Search
│   ├── tickets/                # JSON ticket files → uploaded to blob → AI Search
│   ├── lakehouse/              # CSV topology data → loaded into Fabric Lakehouse
│   ├── eventhouse/             # CSV telemetry data → ingested into Fabric Eventhouse
│   ├── prompts/                # Agent system prompts (Foundry + Fabric Data Agents)
│   └── scripts/                # Synthetic data generators (run once)
│
├── scripts/                    # Provisioning & operational scripts
│   ├── _config.py              # Shared config module (FABRIC_API, paths, helpers)
│   ├── provision_lakehouse.py  # Create Fabric workspace + lakehouse + load CSVs
│   ├── provision_eventhouse.py # Create Eventhouse + KQL tables + ingest CSVs
│   ├── provision_ontology.py   # Create Ontology item on Lakehouse data
│   ├── create_runbook_indexer.py   # Build AI Search index from blob runbooks
│   ├── create_tickets_indexer.py   # Build AI Search index from blob tickets
│   ├── populate_fabric_config.py   # Discover Fabric IDs → write to azure_config.env
│   ├── collect_fabric_agents.py    # Discover Fabric Data Agent IDs → azure_config.env
│   ├── provision_agents.py     # Create all 5 Foundry agents (orchestrator + 4 sub-agents)
│   ├── assign_fabric_role.py   # Grant Container App identity Fabric workspace access
│   ├── agent_ids.json          # Output: provisioned agent IDs
│   └── testing_scripts/        # CLI test & debug utilities
│       ├── test_orchestrator.py    # Stream orchestrator run with metadata
│       ├── test_fabric_agent.py    # Query a single Fabric Data Agent
│       ├── test_gql_query.py       # GQL queries against Fabric GraphModel API
│       ├── test_kql_query.py       # KQL queries against Fabric Eventhouse
│       ├── test_fabric_query_api.py # Deployment smoke test for fabric-query-api
│       ├── test_function_tool.py   # PoC — Foundry agent with FunctionTool (archived)
│       └── check_status.py         # Inspect Fabric workspace items and job status
│
├── api/                        # FastAPI backend
│   ├── pyproject.toml          # Python deps (fastapi, sse-starlette, mcp, azure SDKs)
│   └── app/
│       ├── main.py             # App factory, CORS, router mounts
│       ├── orchestrator.py     # Foundry agent bridge — sync SDK → async SSE generator
│       ├── routers/
│       │   ├── alert.py        # POST /api/alert → SSE stream of orchestrator steps
│       │   ├── agents.py       # GET /api/agents → list of agent metadata
│       │   └── logs.py         # GET /api/logs + /api/fabric-logs → SSE log streams
│       └── mcp/
│           └── server.py       # FastMCP tool stubs (query_eventhouse, search_tickets, …)
│
├── fabric-query-api/           # Fabric data proxy — Container App micro-service
│   ├── main.py                 # FastAPI app: POST /query/graph, POST /query/telemetry
│   ├── pyproject.toml          # Python deps (fastapi, uvicorn, azure-identity, azure-kusto-data)
│   ├── Dockerfile              # python:3.11-slim, uv for deps, port 8100
│   └── openapi.yaml            # OpenAPI 3.0.3 spec — consumed by OpenApiTool agents
│
├── frontend/                   # React SPA
│   ├── package.json
│   ├── vite.config.ts          # Dev server :5173, proxies /api + SSE routes → :8000
│   ├── tailwind.config.js      # Full colour system (brand, neutral, status)
│   ├── index.html
│   └── src/
│       ├── main.tsx            # React 18 entry
│       ├── App.tsx             # Layout shell — imports hook + zones
│       └── styles/globals.css  # CSS custom properties, glass utilities, dark theme
│
├── documentation/              # Architecture docs, design specs, scenario description
│   ├── ARCHITECTURE.md         # This file
│   ├── SCENARIO.md             # Demo scenario description
│   ├── V4GRAPH.md              # V4 graph model design
│   ├── VUNKAGENTRETHINK.md     # Agent architecture rethink notes
│   └── previous_dev_phases/    # Archived design docs (V2, V3)
│
└── .github/
    └── copilot-instructions.md # Copilot context for this project
```

---

## Architectural Decisions

### FastAPI over Azure Functions

| Concern | Azure Functions | FastAPI |
|---------|-----------------|---------|
| SSE streaming | Not native; requires Durable Functions workarounds | `StreamingResponse` / `sse-starlette` native |
| Orchestrator timeout | 230 s max (Consumption), needs Durable for longer | No limit (process stays alive) |
| MCP server hosting | Separate deployment or complex setup | FastMCP mounts directly on the ASGI app |
| Cold start | Yes (Consumption plan) | Container Apps: scales to zero, minimal cold start |
| Single codebase | Separate Function App project | REST + MCP + SSE all in one process |

**Decision:** FastAPI on Azure Container Apps. Single Python process serves the REST
API, SSE streaming, and MCP tools. No cold-start penalty with min-replicas=1.

### Single `azure_config.env` for all config

A single dotenv file is the source of truth for every part of the system:
infrastructure, scripts, API, and (via proxy) frontend. Avoids config drift between
layers. The `preprovision.sh` hook syncs selected values into `azd env` so Bicep
can read them via `readEnvironmentVariable()`. The `postprovision.sh` hook writes
deployment outputs back into the same file.

### Shared `scripts/_config.py`

All provisioning scripts import from a single module rather than each defining
`FABRIC_API`, `FABRIC_SCOPE`, credential helpers, and path constants locally.
Changes to API URLs, OAuth scopes, or default resource names propagate everywhere
from one file.

### Agent architecture: Connected Agents pattern

The orchestrator doesn't call external APIs directly. It delegates to four
sub-agents via Foundry's `ConnectedAgentTool`. Each sub-agent is scoped to one
data source and has its own system prompt. This keeps each agent focused and
testable independently.

### Fabric data access: OpenApiTool + fabric-query-api (V2)

GraphExplorerAgent and TelemetryAgent access Microsoft Fabric through a dedicated
Container App micro-service (`fabric-query-api`) rather than the Fabric Data Agent
(`FabricTool`). This change was driven by a key constraint: `ConnectedAgentTool`
sub-agents run server-side on Foundry and cannot execute client-side `FunctionTool`
callbacks. `OpenApiTool` makes server-side REST calls, so it works natively.

**fabric-query-api** is a lightweight FastAPI service with two endpoints:
- `POST /query/graph` — executes GQL against the Fabric GraphModel REST API
- `POST /query/telemetry` — executes KQL against Fabric Eventhouse via Kusto SDK

The service authenticates to Fabric using `DefaultAzureCredential` (system-assigned
managed identity in production). Each agent receives an `OpenApiTool` configured
with the service's OpenAPI spec (`fabric-query-api/openapi.yaml`), and Foundry
calls the endpoints directly at runtime.

**Why not FabricTool?** FabricTool requires a Fabric Data Agent connected as a
"Connected Resource" in AI Foundry — a manual portal step that cannot be automated.
It also only supports delegated user identities, not managed identities. The
OpenApiTool approach eliminates both limitations and provides full control over
query construction (GQL/KQL) and error handling (429 retry, etc.).

### Fabric identity and role assignment

The `fabric-query-api` Container App authenticates to the Fabric REST API using
its system-assigned managed identity (via `DefaultAzureCredential`). For this to
work, the identity must be a member of the Fabric workspace.

`scripts/assign_fabric_role.py` automates this:
1. Reads `FABRIC_WORKSPACE_ID` and `FABRIC_QUERY_API_PRINCIPAL_ID` from `azure_config.env`
2. Calls `GET /v1/workspaces/{id}/roleAssignments` to check if the principal already has a role
3. If not, calls `POST /v1/workspaces/{id}/roleAssignments` to add it as **Contributor**

The script is idempotent — re-running it skips if the assignment already exists.
It must run after both `azd up` (which creates the Container App identity) and
`provision_lakehouse.py` (which creates the Fabric workspace).

### Deployment: `azd up` and `azd deploy`

`azd up` runs the full infrastructure + service deployment cycle:
1. `preprovision.sh` syncs `azure_config.env` → azd environment variables
2. Bicep provisions all Azure resources (including Container Apps Environment + ACR)
3. `azd deploy` builds and deploys `fabric-query-api` (Docker image built in ACR via `remoteBuild`)
4. `postprovision.sh` uploads data to blob, writes deployment outputs to `azure_config.env`

For code-only changes to `fabric-query-api`, use `azd deploy fabric-query-api`
without re-running the full `azd up`. This rebuilds the container image and
creates a new Container App revision (~60 seconds).

### SSE event protocol

The API streams structured SSE events to the frontend. Event types:

| Event | Payload | Purpose |
|-------|---------|---------|
| `run_start` | `{run_id, alert, timestamp}` | Signals diagnosis began |
| `step_thinking` | `{agent, status}` | Agent is working (shows thinking dots) |
| `step_start` | `{step, agent}` | Agent invocation starting |
| `step_complete` | `{step, agent, duration, query, response, error?}` | Agent returned; includes I/O. `error: true` on failure |
| `message` | `{text}` | Final diagnosis (markdown) |
| `error` | `{message}` | Run-level error (agent failure, timeout, etc.) |
| `run_complete` | `{steps, tokens, time}` | Run finished; summary stats |

### Frontend design system

Dark theme following the `frontend-ui-dark-ts` skill specification:
- CSS custom properties for all colours (`--brand`, `--bg-*`, `--text-*`, `--status-*`)
- Glass morphism utilities: `glass-card`, `glass-panel`, `glass-input`, `glass-overlay`
- Framer Motion for all transitions: `AnimatePresence`, stagger containers, spring-physics buttons
- `clsx` for conditional class composition
- `focus-visible` ring styles for keyboard accessibility

### Frontend architecture: V4 NOC Dashboard

The frontend is a component-based three-zone dashboard layout with
vertically and horizontally resizable panels.

**Layout structure** (`h-screen flex flex-col`, no page scroll):

```
┌──────────────────────────────────────────────────────────────────────┐
│  Header          (h-12, fixed)                              Zone 1  │
├──────────────────────────────────────────────────────────────────────┤
│  MetricsBar      (resizable height, default 30%)            Zone 2  │
│  [KPI] [KPI] [KPI] [KPI] [AlertChart] [API Logs] [Fabric Logs]     │
│  ←──── resizable panels (react-resizable-panels) ────→              │
├═══════════════════════════ vertical drag handle ═════════════════════┤
│                  (resizable height, default 70%)            Zone 3  │
│  ┌────────────────────────┬─────────────────────────────────┐       │
│  │  InvestigationPanel    │  DiagnosisPanel                 │       │
│  │  (w-1/2, scroll-y)    │  (w-1/2, scroll-y)              │       │
│  │  AlertInput            │  Empty → Loading → Markdown     │       │
│  │  AgentTimeline         │                                 │       │
│  │  ErrorBanner           │                                 │       │
│  └────────────────────────┴─────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```

Zone 2 and Zone 3 are vertically resizable via a `PanelGroup` with
`orientation="vertical"`. Users can drag the handle between them to
allocate more space to metrics or investigation.

**Component tree:**

```
App.tsx                        Layout shell — imports hook + zones
├── Header.tsx                 Branding + HealthDot + "5 Agents" indicator
├── MetricsBar.tsx             PanelGroup with 7 resizable panels
│   ├── MetricCard.tsx ×4      KPI display (hardcoded values for demo)
│   ├── AlertChart.tsx         Static <img> of anomaly detection chart
│   ├── LogStream.tsx ×2       Live SSE log panels (API logs + Fabric logs)
├── InvestigationPanel.tsx     Left panel container
│   ├── AlertInput.tsx         Textarea + submit button
│   ├── AgentTimeline.tsx      Step list + thinking dots + run-complete footer
│   │   ├── StepCard.tsx       Collapsible step with query/response expand
│   │   └── ThinkingDots.tsx   Bouncing dots indicator
│   └── ErrorBanner.tsx        Contextual error messages + retry
├── DiagnosisPanel.tsx         Right panel — 3 states: empty / loading / result
└── HealthDot.tsx              API health check indicator (reused in Header)
```

**File layout:**

```
frontend/src/
├── App.tsx                    # ~80 lines — layout shell with vertical PanelGroup
├── main.tsx                   # React 18 entry
├── types/
│   └── index.ts               # StepEvent, ThinkingState, RunMeta
├── hooks/
│   └── useInvestigation.ts    # SSE connection + all state (uses @microsoft/fetch-event-source)
├── components/
│   ├── Header.tsx
│   ├── MetricsBar.tsx         # PanelGroup with 7 panels (react-resizable-panels)
│   ├── MetricCard.tsx
│   ├── AlertChart.tsx
│   ├── LogStream.tsx          # Generic SSE log viewer (url + title props)
│   ├── InvestigationPanel.tsx
│   ├── AlertInput.tsx
│   ├── AgentTimeline.tsx
│   ├── StepCard.tsx
│   ├── ThinkingDots.tsx
│   ├── ErrorBanner.tsx
│   ├── DiagnosisPanel.tsx
│   └── HealthDot.tsx
└── styles/
    └── globals.css            # Includes .metrics-resize-handle + .vertical-resize-handle styles
```

**State management:** All SSE state lives in `useInvestigation()` custom hook.
The hook returns `{ alert, setAlert, steps, thinking, finalMessage, errorMessage,
running, runStarted, runMeta, submitAlert }`. `App.tsx` calls the hook and passes
props down. Both panels read from the same hook instance — investigation panel
gets the steps/thinking state, diagnosis panel gets the final message. The hook
uses `@microsoft/fetch-event-source` to issue a POST-based SSE request (standard
`EventSource` is GET-only).

**Resizable metrics panels:** The metrics bar uses `react-resizable-panels`
(exported as `Group`, `Panel`, `Separator`). 7 panels (4 KPI cards + alert chart
+ API log stream + Fabric log stream) are horizontally resizable. Handle styling
is in `globals.css` under `.metrics-resize-handle`.

**Live log streaming:** Two `LogStream` components in the metrics bar display
real-time backend logs via SSE:
- **API logs** (`/api/logs`) — captures all `app.*`, `azure.*`, and `uvicorn`
  log output from the FastAPI process.
- **Fabric logs** (`/api/fabric-logs`) — synthetic logs emitted by the
  orchestrator showing the queries and responses that flow through
  `fabric-query-api` (graph/telemetry endpoints). These are reconstructed from
  the orchestrator's view of agent tool calls, since the real fabric-query-api
  runs in Azure and isn't directly observable locally.

Each LogStream supports auto-scroll, manual scroll-pause, and connection status.

**Hardcoded vs live data:** Metrics values (12 alerts, 3 services, $115k SLA,
231 anomalies) and the alert chart image are hardcoded for demo reliability.
The investigation panel (SSE steps), diagnosis panel (final markdown), and log
streams are connected to the live backend.

**Extension guidance:**

- **Add a new metric card:** Add an entry to the `metrics` array in `MetricsBar.tsx`
  and add a new `<Panel>` with `<ResizeHandle>` in the JSX. Adjust `defaultSize`
  percentages so all panels sum to 100.

- **Make metrics live:** Replace hardcoded values in `MetricsBar.tsx` with state
  from a new hook (e.g., `useMetrics()`) that polls `/api/metrics` or subscribes
  to an SSE stream. Each `MetricCard` accepts props — no component changes needed.

- **Replace the alert chart image:** Swap `AlertChart.tsx` from a static `<img>`
  to a Recharts/D3 component. The parent `Panel` provides the container dimensions.

- **Adjust vertical split ratio:** Zone 2 and Zone 3 are already in a vertical
  `PanelGroup`. Change the `defaultSize` props (currently 30/70) in `App.tsx` to
  adjust. The `minSize` props prevent either zone from collapsing completely.

- **State migration to Zustand:** Replace `useInvestigation` props-drilling with
  a Zustand store. Both panels import `useInvestigationStore()` directly. The
  `InvestigationState` interface maps to the hook's current return shape.

- **Sub-agent step expansion:** `StepCard.tsx` already supports click-to-expand
  with query/response sections and renders responses as Markdown via
  `react-markdown`. Failed steps are visually distinguished with red borders and
  error styling. For post-hoc enrichment (fetching sub-agent thread details
  after run completes), add a `useStepDetails(threadId)` hook and render inside
  the expanded card.

### Infrastructure as Code

Subscription-scoped Bicep deployment via `azd up`. The parameter file reads from
environment variables (synced from `azure_config.env` by `preprovision.sh`).
Resources use a deterministic `resourceToken` derived from subscription + env name +
location, so names are globally unique and reproducible.

Modules: `ai-foundry` (Foundry account + project + GPT deployment), `search`,
`storage` (account + containers), `fabric` (capacity), `roles` (RBAC for user +
service principals).

---

## Configuration Signpost

All runtime configuration lives in `azure_config.env`. The template
(`azure_config.env.template`) documents every variable, its purpose, and whether
it's user-set or auto-populated.

### Variable groups and which system layers consume them

| Variable | Set by | Consumed by |
|----------|--------|-------------|
| **Core Azure** | | |
| `AZURE_SUBSCRIPTION_ID` | postprovision | scripts |
| `AZURE_RESOURCE_GROUP` | postprovision | scripts |
| `AZURE_LOCATION` | user | preprovision → Bicep |
| **AI Foundry** | | |
| `AI_FOUNDRY_NAME` | postprovision | scripts |
| `AI_FOUNDRY_ENDPOINT` | postprovision | scripts |
| `AI_FOUNDRY_PROJECT_NAME` | postprovision | scripts |
| `PROJECT_ENDPOINT` | postprovision | scripts (provision_agents, test_orchestrator) |
| **Model deployments** | | |
| `MODEL_DEPLOYMENT_NAME` | user | scripts (provision_agents), Bicep |
| `EMBEDDING_MODEL` | user | scripts (create_*_indexer) |
| `EMBEDDING_DIMENSIONS` | user | scripts (create_*_indexer) |
| `GPT_CAPACITY_1K_TPM` | user | preprovision → Bicep |
| **AI Search** | | |
| `AI_SEARCH_NAME` | postprovision | scripts (create_*_indexer) |
| `RUNBOOKS_INDEX_NAME` | user | scripts (create_runbook_indexer), API (MCP) |
| `TICKETS_INDEX_NAME` | user | scripts (create_tickets_indexer), API (MCP) |
| **Storage** | | |
| `STORAGE_ACCOUNT_NAME` | postprovision | scripts |
| `RUNBOOKS_CONTAINER_NAME` | user | scripts, must match Bicep container name |
| `TICKETS_CONTAINER_NAME` | user | scripts, must match Bicep container name |
| **Fabric API** | | |
| `FABRIC_API_URL` | user (default ok) | scripts/_config.py → all scripts |
| `FABRIC_SCOPE` | user (default ok) | scripts/_config.py → all scripts |
| **App / CORS** | | |
| `CORS_ORIGINS` | user | API (main.py CORS middleware) |
| **Fabric deployment** | | |
| `FABRIC_SKU` | user | preprovision → Bicep |
| `AZURE_FABRIC_ADMIN` | user | preprovision → Bicep |
| **Fabric resource names** | | |
| `FABRIC_WORKSPACE_NAME` | user | scripts (provision_lakehouse, populate_fabric_config) |
| `FABRIC_LAKEHOUSE_NAME` | user | scripts/_config.py → provision_lakehouse |
| `FABRIC_EVENTHOUSE_NAME` | user | scripts/_config.py → provision_eventhouse |
| `FABRIC_KQL_DB_DEFAULT` | user | scripts (provision_eventhouse) |
| `FABRIC_ONTOLOGY_NAME` | user | scripts/_config.py → provision_ontology |
| **Fabric IDs** | | |
| `FABRIC_CAPACITY_ID` | populate_fabric_config | scripts (provision_lakehouse, provision_eventhouse) |
| `FABRIC_WORKSPACE_ID` | populate_fabric_config | scripts/_config.py → all Fabric scripts |
| `FABRIC_LAKEHOUSE_ID` | populate_fabric_config | scripts (provision_ontology) |
| `FABRIC_EVENTHOUSE_ID` | populate_fabric_config | scripts (provision_eventhouse) |
| `FABRIC_KQL_DB_ID` | populate_fabric_config | scripts |
| `FABRIC_KQL_DB_NAME` | populate_fabric_config | scripts/_config.py |
| `EVENTHOUSE_QUERY_URI` | populate_fabric_config | scripts (provision_eventhouse — Kusto ingestion) |
| **Fabric Data Agents** | | |
| `GRAPH_DATA_AGENT_ID` | collect_fabric_agents | (legacy — unused in V2) |
| `TELEMETRY_DATA_AGENT_ID` | collect_fabric_agents | (legacy — unused in V2) |
| `FABRIC_DATA_AGENT_API_VERSION` | user (default ok) | scripts (test_fabric_agent) |
| **fabric-query-api** | | |
| `FABRIC_QUERY_API_URI` | postprovision (azd output) | scripts (provision_agents) |
| `FABRIC_QUERY_API_PRINCIPAL_ID` | postprovision (azd output) | scripts (assign_fabric_role) |
| `FABRIC_GRAPH_MODEL_ID` | provision_ontology | fabric-query-api (env var) |
| `FABRIC_ONTOLOGY_ID` | provision_ontology | scripts |

### Config files beyond azure_config.env

| File | Purpose | Consumed by |
|------|---------|-------------|
| `azure.yaml` | azd project definition: hook paths, service targets | azd CLI |
| `pyproject.toml` (root) | Python deps for scripts/ | uv (scripts) |
| `api/pyproject.toml` | Python deps for API | uv (api) |
| `frontend/package.json` | Node deps for frontend | npm |
| `frontend/vite.config.ts` | Dev server port, `/api` proxy target | Vite |
| `frontend/tailwind.config.js` | Colour system, fonts | Tailwind CSS |
| `infra/main.bicepparam` | Bicep parameter values (reads env vars) | azd/Bicep |
| `scripts/agent_ids.json` | Provisioned Foundry agent IDs | scripts (test_orchestrator) |
| `data/prompts/*.md` | System prompts for each agent | scripts (provision_agents) |

---

## Data Flow

### Provisioning pipeline (one-time setup)

```
azure_config.env → preprovision.sh → azd up (Bicep) → postprovision.sh → azure_config.env
                                       │                ├─ uploads runbooks/ → blob → create_runbook_indexer.py → AI Search
                                       │                └─ uploads tickets/  → blob → create_tickets_indexer.py → AI Search
                                       │
                                       ├─ Container Apps Environment (ACR + Log Analytics)
                                       └─ fabric-query-api Container App (deployed by azd deploy)

provision_lakehouse.py ─── CSV topology data ──────────▶ Fabric Lakehouse
provision_eventhouse.py ── CSV telemetry data ─────────▶ Fabric Eventhouse (KQL)
provision_ontology.py ──── ontology definition ────────▶ Fabric Ontology (graph index)
populate_fabric_config.py ── discovers IDs ────────────▶ azure_config.env
assign_fabric_role.py ──── grants managed identity ────▶ Fabric workspace Contributor
provision_agents.py ──── creates 5 Foundry agents ─────▶ agent_ids.json
  ├─ GraphExplorerAgent   (OpenApiTool → fabric-query-api /query/graph)
  ├─ TelemetryAgent       (OpenApiTool → fabric-query-api /query/telemetry)
  ├─ RunbookKBAgent       (AzureAISearchTool → runbooks-index)
  ├─ HistoricalTicketAgent(AzureAISearchTool → tickets-index)
  └─ Orchestrator         (ConnectedAgentTool → all 4 above)
```

### Runtime flow (per alert)

```
User types alert → Frontend POST /api/alert
  → FastAPI receives AlertRequest
  → Creates orchestrator thread + run (azure-ai-agents SDK)
  → OrchestratorEventHandler streams AgentEvents
  → Each sub-agent invocation yields SSE events
  → Frontend parses SSE, renders step timeline
  → Final diagnosis rendered as markdown
```

---

## Deployment Targets

| Component | Local | Production |
|-----------|-------|------------|
| API | `uvicorn :8000` | Azure Container Apps |
| fabric-query-api | `uvicorn :8100` | Azure Container Apps (via `azd deploy`) |
| Frontend | Vite dev server `:5173` | Azure Static Web Apps |
| Infra | n/a | `azd up` → Azure |

Production deployment uses `azd up` for infrastructure and `azd deploy` for
services. The `fabric-query-api` service is configured with `remoteBuild: true`
in `azure.yaml` so Docker images are built in ACR (cross-platform safe).
CORS_ORIGINS must be updated to the production frontend URL before deploying.

---

## SDK Versions

| Package | Version | Notes |
|---------|---------|-------|
| `azure-ai-projects` | `>=1.0.0,<2.0.0` | v2 has breaking API changes |
| `azure-ai-agents` | `1.2.0b6` | `OpenApiTool`, `ConnectedAgentTool`, `AzureAISearchTool` |
| `azure-kusto-data` | `>=4.6.0` | KQL queries against Eventhouse |
| `fastapi` | `>=0.115` | ASGI framework |
| `sse-starlette` | `>=2.0` | SSE responses |
| `mcp[cli]` | `>=1.9.0` | FastMCP server framework |
| `react` | `18.x` | UI library |
| `framer-motion` | `11.x` | Animation |
| `@microsoft/fetch-event-source` | `^2.0.1` | POST-capable SSE client |
| `react-markdown` | `^10.1.0` | Markdown rendering in diagnosis + step cards |
| `react-resizable-panels` | `^4.6.2` | Resizable panel layout (metrics bar + vertical split) |
| `tailwindcss` | `3.x` | Utility-first CSS |
