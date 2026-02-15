# Architecture

## Demo built with assistance from Claude Opus 4.6 using the following [skills](https://github.com/microsoft/skills):
* azure-ai-projects-py — `~/references/skills/.github/skills/azure-ai-projects-py`
* hosted-agents-v2-py — `~/references/skills/.github/skills/hosted-agents-v2-py`
* mcp-builder — `~/references/skills/.github/skills/mcp-builder`
* azure-appconfiguration-py — `~/references/skills/.github/skills/azure-appconfiguration-py`
* azure-containerregistry-py — `~/references/skills/.github/skills/azure-containerregistry-py`
* ~/references/skills/.github/skills/fastapi-router-py 
* ~/references/skills/.github/skills/frontend-ui-dark-ts 
* azure-cosmosdb-gremlin-py — `custom_skills/azure-cosmosdb-gremlin-py`

---

## System Overview

Multi-agent incident investigation platform. An alert enters via the frontend,
flows through a FastAPI backend that streams SSE progress, and reaches an
orchestrator agent in Azure AI Foundry. The orchestrator delegates to four
specialist agents, each backed by a distinct data source in Azure Cosmos DB
or Azure AI Search. The platform is scenario-agnostic — users upload scenario
data packs (.tar.gz) via the UI, and the Container App ingests graph data,
telemetry, knowledge bases, and prompts into the appropriate Azure services.

### Unified Container Architecture

All three services run inside a **single unified container** managed by supervisord:

| Process | Port | Role |
|---------|------|------|
| **nginx** | `:80` (external) | Reverse proxy + React SPA static hosting |
| **API** (uvicorn) | `127.0.0.1:8000` | FastAPI backend, orchestrator bridge, SSE streaming |
| **graph-query-api** (uvicorn) | `127.0.0.1:8100` | Graph & telemetry microservice |

nginx routes all traffic:
- `/` → React SPA (static files)
- `/api/*` → API uvicorn (:8000) with SSE support
- `/health` → API uvicorn (:8000)
- `/query/*` → graph-query-api uvicorn (:8100)

This architecture avoids inter-container networking issues in Azure Container Apps.
All three processes share localhost, so no service discovery is needed.

```
                         ┌──────────────────────────────────────────┐
                         │       Unified Container App (:80)        │
                         │                                          │
Browser ──POST /api/──▶  │  nginx :80                               │
         ◀──SSE stream── │   ├─ /        → React SPA (static)      │
                         │   ├─ /api/*   → uvicorn :8000 (API)     │
                         │   ├─ /health  → uvicorn :8000            │
                         │   └─ /query/* → uvicorn :8100 (graph)   │
                         │                                          │
                         │  supervisord manages all 3 processes     │
                         └────────────────┬─────────────────────────┘
                                          │ azure-ai-agents SDK
                                          ▼
                              ┌───────────────────────┐
                              │   Orchestrator Agent  │
                              │   (Azure AI Foundry)  │
                              └───┬───┬───┬───┬───────┘
                ┌─────────────────┘   │   │   └──────────────────────┐
                ▼                     ▼   ▼                          ▼
      ┌─────────────────┐ ┌──────────────┐ ┌──────────────┐  ┌─────────────────┐
      │ GraphExplorer   │ │ Telemetry    │ │ RunbookKB    │  │ HistoricalTicket│
      │ Agent           │ │ Agent        │ │ Agent        │  │ Agent           │
      └────────┬────────┘ └──────┬───────┘ └──────┬───────┘  └────────┬────────┘
               │ OpenApiTool     │ OpenApiTool     │ AI Search         │ AI Search
               ▼                  ▼                ▼                   ▼
      ┌──────────────────┐ ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
      │ graph-query-api │ │ graph-query-api │  │ runbooks-    │  │ tickets-         │
      │ POST /query/     │ │ POST /query/     │  │ index        │  │ index            │
      │ graph            │ │ telemetry (SQL)  │  │ (hybrid)     │  │ (hybrid)         │
      └────────┬─────────┘ └────────┬─────────┘  └──────────────┘  └──────────────────┘
               │ dispatches         │
               ▼ via GRAPH_BACKEND  ▼
      ┌──────────────────┐   ┌───────────────┐
      │  Backend layer   │   │ Cosmos DB     │
      │  ┌─ cosmosdb.py │   │ NoSQL         │
      │  └─ mock.py     │   │ (SQL API)     │
      └──────────────────┘   └───────────────┘
```

---

## Project Structure

```
.
├── azure.yaml                  # azd project definition (hooks, 1 unified service target)
├── azure_config.env            # Runtime config — single source of truth (gitignored)
├── azure_config.env.template   # Checked-in template for azure_config.env
├── deploy.sh                   # End-to-end deployment script (all steps)
├── Dockerfile                  # Unified container: nginx + API + graph-query-api
├── nginx.conf                  # Reverse proxy + SPA serving (hardcoded localhost)
├── supervisord.conf            # Process manager: nginx, api, graph-query-api
├── .dockerignore               # Build context exclusions
├── pyproject.toml              # Python deps for scripts/ (uv-managed)
│
├── infra/                      # Bicep IaC (deployed by `azd up`)
│   ├── main.bicep              # Subscription-scoped orchestrator (1 Container App)
│   ├── main.bicepparam         # Reads env vars via readEnvironmentVariable()
│   └── modules/
│       ├── ai-foundry.bicep    # AI Foundry account + project + GPT deployment
│       ├── search.bicep        # Azure AI Search
│       ├── storage.bicep       # Storage account + blob containers
│       ├── container-apps-environment.bicep  # Log Analytics + ACR + Managed Environment
│       ├── container-app.bicep              # Generic Container App (managed identity)
│       ├── cosmos-gremlin.bicep              # Cosmos DB Gremlin + NoSQL (graph + telemetry)
│       ├── cosmos-private-endpoints.bicep    # VNet private endpoints for Cosmos DB
│       ├── vnet.bicep                        # VNet (Container Apps + Private Endpoints subnets)
│       └── roles.bicep         # RBAC assignments (user + service + container app roles)
│
├── hooks/                      # azd lifecycle hooks
│   ├── preprovision.sh         # Syncs azure_config.env → azd env vars for Bicep
│   └── postprovision.sh        # Uploads data to blob, writes outputs → azure_config.env
│
├── data/                       # Modular scenario data (v7 architecture)
│   ├── scenarios/              # One subdirectory per scenario
│   │   ├── telco-noc/          # Australian Telco NOC — fibre cut incident
│   │   │   ├── scenario.yaml   # Scenario manifest (cosmos, search, graph styles)
│   │   │   ├── graph_schema.yaml  # Graph ontology (vertices + edges)
│   │   │   ├── scripts/        # Data generation scripts + generate_all.sh
│   │   │   └── data/           # Generated output
│   │   │       ├── entities/   # Vertex + edge CSVs (gitignored)
│   │   │       ├── telemetry/  # Alert + metric CSVs (gitignored)
│   │   │       ├── knowledge/  # runbooks/ (.md) + tickets/ (.txt)
│   │   │       └── prompts/    # Agent prompt fragments
│   │   ├── cloud-outage/       # Cloud DC outage — cooling cascade
│   │   └── customer-recommendation/  # E-commerce — model bias incident
│   ├── graph_schema.yaml       # ← symlink → scenarios/telco-noc/graph_schema.yaml
│   ├── network/                # ← symlink → scenarios/telco-noc/data/entities/
│   ├── telemetry/              # ← symlink → scenarios/telco-noc/data/telemetry/
│   ├── runbooks/               # ← symlink → scenarios/telco-noc/data/knowledge/runbooks/
│   ├── tickets/                # ← symlink → scenarios/telco-noc/data/knowledge/tickets/
│   ├── prompts/                # ← symlink → scenarios/telco-noc/data/prompts/
│   └── scripts/                # ← symlink → scenarios/telco-noc/scripts/
│
├── scripts/                    # Provisioning & operational scripts
│   ├── scenario_loader.py      # ScenarioLoader — resolves paths/config for any scenario
│   ├── agent_provisioner.py    # AgentProvisioner class — importable agent creation logic
│   ├── provision_agents.py     # CLI wrapper for agent provisioning (uses agent_provisioner)
│   ├── agent_ids.json          # Output: provisioned agent IDs
│   ├── cosmos/                 # (empty — Cosmos scripts moved to deprecated/)
│   └── testing_scripts/        # CLI test & debug utilities
│       ├── test_orchestrator.py    # Stream orchestrator run with metadata
│       └── test_graph_query_api.py # Deployment smoke test for graph-query-api
│
├── api/                        # FastAPI backend (NOC API)
│   ├── pyproject.toml          # Python deps (fastapi, sse-starlette, azure SDKs)
│   ├── Dockerfile              # (Legacy — per-service, unused in unified deploy)
│   └── app/
│       ├── main.py             # App factory, CORS, router mounts, /health
│       ├── orchestrator.py     # Foundry agent bridge — sync SDK → async SSE with retry
│       └── routers/
│           ├── alert.py        # POST /api/alert → SSE stream of orchestrator steps
│           ├── agents.py       # GET /api/agents → list of agent metadata
│           ├── config.py       # POST /api/config/apply → re-provision agents with new bindings
│           └── logs.py         # GET /api/logs → SSE log stream
│
├── graph-query-api/           # Graph, telemetry & data management microservice
│   ├── main.py                 # App factory: middleware, health, log SSE, router mounts
│   ├── config.py               # GRAPH_BACKEND enum, ScenarioContext, env var loading
│   ├── models.py               # Pydantic request/response models (shared across backends)
│   ├── router_graph.py         # POST /query/graph — dispatches to backend via ScenarioContext
│   ├── router_telemetry.py     # POST /query/telemetry — SQL via Cosmos SDK (scenario-aware)
│   ├── router_topology.py      # POST /query/topology — graph topology for visual explorer
│   ├── router_ingest.py        # POST /query/scenario/upload — scenario upload + ingestion
│   ├── router_prompts.py       # CRUD /query/prompts — prompt management in Cosmos DB
│   ├── search_indexer.py       # AI Search indexer pipeline (blob → index + vectorize)
│   ├── backends/               # Backend abstraction layer with per-graph client cache
│   │   ├── __init__.py         # GraphBackend Protocol + get_backend_for_context() factory
│   │   ├── cosmosdb.py         # Cosmos DB Gremlin (parameterised per-graph instances)
│   │   └── mock.py             # Static topology responses (offline demos)
│   ├── openapi/                # Per-backend OpenAPI specs for Foundry OpenApiTool
│   │   ├── cosmosdb.yaml       # Gremlin description
│   │   └── mock.yaml           # Generic description
│   ├── pyproject.toml          # Python deps (fastapi, azure-cosmos, gremlinpython, azure-search, azure-storage-blob)
│   └── Dockerfile              # (Legacy — per-service, unused in unified deploy)
│
├── frontend/                   # React SPA — NOC Dashboard
│   ├── package.json
│   ├── vite.config.ts          # Dev server :5173, proxies /api → :8000, /query → :8100
│   ├── tailwind.config.js      # Full colour system (brand, neutral, status)
│   ├── index.html
│   ├── Dockerfile              # (Legacy — per-service, unused in unified deploy)
│   └── src/
│       ├── main.tsx            # React 18 entry
│       ├── App.tsx             # Layout shell — three-zone resizable dashboard
│       ├── types/index.ts      # StepEvent, ThinkingState, RunMeta
│       ├── hooks/
│       │   ├── useInvestigation.ts   # SSE connection + all investigation state
│       │   ├── useTopology.ts        # Topology data fetching (POST /query/topology)
│       │   └── useScenarios.ts       # Scenario listing, upload with SSE progress
│       ├── context/
│       │   └── ScenarioContext.tsx    # React context: active graph, indexes, X-Graph header
│       ├── components/
│       │   ├── Header.tsx            # Branding + HealthDot + ⚙ Settings button
│       │   ├── SettingsModal.tsx      # Tabbed modal: Data Sources + Upload
│       │   ├── MetricsBar.tsx        # PanelGroup with 2 resizable panels (graph + logs)
│       │   ├── MetricCard.tsx        # KPI display (hardcoded for demo)
│       │   ├── AlertChart.tsx        # Static anomaly detection chart image
│       │   ├── LogStream.tsx         # Generic SSE log viewer (url + title props)
│       │   ├── InvestigationPanel.tsx # Left panel: alert input + agent timeline
│       │   ├── AlertInput.tsx        # Textarea + submit button
│       │   ├── AgentTimeline.tsx     # Step list + thinking dots + run-complete footer
│       │   ├── StepCard.tsx          # Collapsible step with query/response expand
│       │   ├── ThinkingDots.tsx      # Bouncing dots indicator
│       │   ├── ErrorBanner.tsx       # Contextual error messages + retry
│       │   ├── DiagnosisPanel.tsx    # Right panel: empty → loading → markdown
│       │   ├── HealthDot.tsx         # API health check indicator
│       │   ├── GraphTopologyViewer.tsx # Interactive graph topology explorer (V6)
│       │   └── graph/                # Graph visualisation sub-components
│       │       ├── graphConstants.ts  # NODE_COLORS, NODE_SIZES per vertex type
│       │       ├── GraphCanvas.tsx    # react-force-graph-2d wrapper + custom rendering
│       │       ├── GraphTooltip.tsx   # Hover tooltip (node/edge properties)
│       │       ├── GraphContextMenu.tsx # Right-click menu (display field, colour picker)
│       │       └── GraphToolbar.tsx   # Search, label chips, zoom-to-fit, refresh
│       └── styles/
│           └── globals.css           # CSS custom properties, glass utilities, dark theme
│
├── documentation/              # Architecture docs, design specs, scenario description
│   ├── ARCHITECTURE.md         # This file
│   ├── SCENARIO.md             # Demo scenario description
│   ├── TASKS.md                # Task tracking
│   ├── V5MULTISCENARIODEMO.md  # V5 multi-scenario demo spec
│   ├── V6Interactive.md        # V6 interactive graph topology viewer spec
│   ├── VUNKAGENTRETHINK.md     # Agent architecture rethink notes
│   ├── azure_deployment_lessons.md  # Deployment troubleshooting & lessons learned
│   ├── assets/                 # Screenshots & diagrams
│   └── deprecated/             # Archived docs (SETUP_COSMOSDB.md, etc.)
│
├── deprecated/                 # V8 deprecated files (superseded by UI data management)
│   ├── scripts/
│   │   ├── create_runbook_indexer.py   # → replaced by router_ingest.py + search_indexer.py
│   │   ├── create_tickets_indexer.py   # → replaced by router_ingest.py + search_indexer.py
│   │   ├── _indexer_common.py          # → replaced by search_indexer.py
│   │   └── cosmos/
│   │       ├── provision_cosmos_gremlin.py   # → replaced by router_ingest.py
│   │       └── provision_cosmos_telemetry.py # → replaced by router_ingest.py
│   └── shared_prompts/         # → replaced by Cosmos DB platform-config.prompts
│
└── .github/
    └── copilot-instructions.md # Copilot context for this project
```

---

## graph-query-api — Backend-Agnostic Architecture (V8)

The most architecturally significant service. A FastAPI microservice that provides
query endpoints, scenario upload/ingestion, prompt CRUD, and scenario listing.
Consumed by Foundry agents (graph/telemetry), the frontend graph explorer
(topology), and the Settings UI (upload/config). Runs inside the unified
Container App, authenticated via system-assigned managed identity.

### Design Principle

Agents don't know or care which graph database backs `/query/graph`. They send a
query string and get back `{columns, data}`. The **query language** changes per
backend (Gremlin, natural language), but the **API contract** is identical.
A single environment variable controls the backend:

```bash
GRAPH_BACKEND=cosmosdb          # Options: "cosmosdb" | "mock"
```

### Module Breakdown

#### `config.py` — Centralised Configuration + Scenario Context

- `GraphBackendType` enum: `COSMOSDB`, `MOCK`
- `ScenarioContext` dataclass: per-request routing context resolved from `X-Graph` header
- `get_scenario_context()` FastAPI dependency: extracts graph name from header,
  derives telemetry database name from the graph prefix
- Reads all env vars once: Cosmos DB connection strings, AI Search name
- Exports shared `credential = DefaultAzureCredential()`
- `BACKEND_REQUIRED_VARS` dict validates that each backend has its required env vars

#### `models.py` — Shared Request/Response Models

| Model | Fields | Notes |
|-------|--------|-------|
| `GraphQueryRequest` | `query` | Query string (Gremlin or natural language) |
| `GraphQueryResponse` | `columns=[]`, `data=[]`, `error: str \| None` | Error field enables LLM self-repair |
| `TelemetryQueryRequest` | `query` | SQL query string |
| `TelemetryQueryResponse` | `columns=[]`, `rows=[]`, `error: str \| None` | Same error pattern |
| `TopologyNode` | `id`, `label`, `type`, `properties: dict` | Single graph vertex |
| `TopologyEdge` | `id`, `source`, `target`, `type`, `properties: dict` | Single graph edge |
| `TopologyMeta` | `node_count`, `edge_count`, `vertex_labels`, `edge_labels` | Topology summary stats |
| `TopologyRequest` | `query`, `vertex_labels: list[str]` | Topology filter request |
| `TopologyResponse` | `nodes`, `edges`, `meta`, `error: str \| None` | Full topology payload |

The `error` field is key to error resilience — see [Error Resilience](#error-resilience).

#### `router_graph.py` — Graph Query Dispatch

- `POST /query/graph` — dispatches to the correct `GraphBackend` based on `ScenarioContext`
- Backend resolved per-request via `get_backend_for_context(ctx)` using the
  `X-Graph` header (e.g. `cloud-outage-topology`)
- Per-graph backend instances are cached in a thread-safe dict
- All exceptions caught and returned as **HTTP 200 with `error` in the response body**

#### `router_telemetry.py` — SQL Queries (Scenario-Aware)

- `POST /query/telemetry` — SQL queries against Cosmos DB NoSQL
- Target database derived from `ScenarioContext.telemetry_database`
  (e.g. `cloud-outage-telemetry` from graph `cloud-outage-topology`)
- No hardcoded container whitelist — accepts any container name from the agent
- Thread-safe cached `CosmosClient` (recreated if URI changes)
- Sync SQL execution wrapped in `asyncio.to_thread()`
- `CosmosHttpResponseError` caught → 200 + error payload

#### `router_topology.py` — Full Graph Topology (V6)

- `POST /query/topology` — returns all nodes and edges for the interactive graph explorer
- Uses `get_backend_for_context(ctx)` (same per-graph cache as `router_graph`)
- Accepts optional `vertex_labels` filter (array of vertex types to include)
- Returns `TopologyResponse` with `nodes`, `edges`, `meta` (counts + label lists)
- Same error-as-200 pattern as other routers

#### `router_ingest.py` — Scenario Upload + Ingestion

- `POST /query/scenario/upload` — upload `.tar.gz` scenario archive
  - Extracts archive, reads `scenario.yaml` + `graph_schema.yaml`
  - Creates Gremlin graph via ARM API (DocumentDB Account Contributor role)
  - Loads vertices + edges from Dim/Fact CSVs via Gremlin
  - Loads telemetry into Cosmos NoSQL containers
  - Stores prompts in Cosmos `platform-config.prompts` container
  - Uploads runbooks/tickets to blob storage
  - Creates AI Search indexer pipelines (data source + index + skillset + indexer)
  - Returns SSE progress stream throughout
- `GET /query/scenarios` — lists loaded Gremlin graphs via ARM
- `GET /query/indexes` — lists AI Search indexes with document counts
- `DELETE /query/scenario/{graph_name}` — drops graph data

#### `router_prompts.py` — Prompts CRUD

- `GET /query/prompts` — list prompts (filter by agent, scenario)
- `POST /query/prompts` — create new prompt (auto-versioned)
- `GET /query/prompts/{id}` — get prompt with content
- `PUT /query/prompts/{id}` — update metadata (tags, is_active)
- `DELETE /query/prompts/{id}` — soft-delete
- Storage: Cosmos NoSQL `platform-config.prompts` container, partition key `/agent`

#### `search_indexer.py` — AI Search Pipeline Service

- `create_search_index()` function creates a complete indexer pipeline:
  data source (blob) → index (with HNSW vector search) → skillset (chunk + embed) → indexer
- Uses Azure OpenAI vectorizer for embeddings
- Polls indexer status until completion (max 5 min)
- Called by `router_ingest.py` during scenario upload

#### `backends/` — Protocol + Implementations

```python
class GraphBackend(Protocol):
    async def execute_query(self, query: str, **kwargs) -> dict: ...
    async def get_topology(self, query: str = "", vertex_labels: list[str] | None = None) -> dict: ...
    def close(self) -> None: ...
```

`get_backend()` factory returns the correct implementation based on `GRAPH_BACKEND`:

| Backend | Implementation | Query Language | Status |
|---------|---------------|----------------|--------|
| `cosmosdb` | `CosmosDBGremlinBackend` | Gremlin | Production — Cosmos DB Gremlin via gremlinpython |
| `mock` | `MockGraphBackend` | Natural language | Working — static topology data (50 nodes, 54 edges) |

**`backends/cosmosdb.py`** — Cosmos DB Gremlin backend:
- Singleton `gremlinpython` client with `GraphSONSerializersV2d0` over WSS
- Key-based auth (`COSMOS_GREMLIN_PRIMARY_KEY`)
- Thread-safe client creation with `threading.Lock()`
- Retry with exponential backoff on `GremlinServerError` (429/408) and
  `WSServerHandshakeError` (max 3 retries)
- `_flatten_valuemap()` + `_normalise_results()` convert Gremlin valueMap
  output to the standard `{columns, data}` response shape
- Sync Gremlin execution wrapped in `asyncio.to_thread()`

**`backends/mock.py`** — Pattern-matches query strings for entity types ("corerouter",
"transportlink", etc.) and returns canned topology data. Also provides full
topology via `get_topology()` — 50 nodes across 8 vertex types (CoreRouter,
AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession)
and 54 edges across 7 relationship types. Supports `vertex_labels` filtering.
Useful for offline demos and the interactive graph explorer.

#### `main.py` — Slim App Factory

~211 lines. Responsibilities:
- FastAPI app with lifespan handler (validates env vars at startup)
- CORS middleware for localhost dev
- HTTP request logging middleware with timing
- SSE log broadcasting (asyncio.Queue subscribers + deque buffer, max 100 lines)
- Mounts `router_graph`, `router_telemetry`, `router_topology`, `router_ingest`, and `router_prompts`
- `GET /health` with backend type and version
- `GET /api/logs` SSE stream

#### Per-Backend OpenAPI Specs

Two standalone OpenAPI 3.0.3 specs in `openapi/`, each consumed by Foundry's
`OpenApiTool` when provisioning agents:

| Spec | `/query/graph` description | Extra params |
|------|---------------------------|--------------|
| `cosmosdb.yaml` | Gremlin query language, Gremlin examples | None (server-side config) |
| `mock.yaml` | Generic "send any query string" | None |

All specs share the same `/query/telemetry` definition (SQL, unchanged across backends).
Each 200 response schema includes an `error` field (nullable string) with a description
instructing the LLM to read the error and retry with corrected syntax.

`provision_agents.py` selects the correct spec at provisioning time based on
`GRAPH_BACKEND`.

---

## API Service — Orchestrator Bridge

The API (`api/`) bridges the synchronous Azure AI Agents SDK to the async SSE-based
frontend. It does **not** query any data source directly — all data access
flows through the Foundry agents.

### `orchestrator.py` — Foundry → SSE Bridge

The most complex module in the API. Architecture:

```
submitAlert() ─────────┐
                        ▼
              ┌─────────────────────────┐
              │  Background thread      │
              │  ├─ Create thread       │
              │  ├─ Create run          │◀── Retry loop (MAX_RUN_ATTEMPTS=2)
              │  ├─ Stream events       │
              │  │  ├─ on_thread_run    │──→ tracks run_failed status
              │  │  ├─ on_run_step      │──→ emits step_start/step_complete
              │  │  └─ on_message_done  │──→ emits final message
              │  └─ On failure: post    │
              │     recovery message    │
              │     and retry           │
              └──────────┬──────────────┘
                         │ asyncio.Queue
                         ▼
              ┌─────────────────────────┐
              │  Async SSE generator    │
              │  yields EventSourceResponse
              └─────────────────────────┘
```

Key design patterns:

1. **Thread bridging**: Foundry's `AgentEventHandler` is synchronous (callbacks).
   The orchestrator runs it in a daemon thread and pushes SSE event dicts to an
   `asyncio.Queue`. The async generator yields from the queue for Starlette's
   `EventSourceResponse`.

2. **Run retry with recovery** (`MAX_RUN_ATTEMPTS = 2`): If a run fails (e.g.,
   sub-agent tool error), the handler sets `run_failed = True` instead of
   immediately emitting an SSE error. The retry loop posts a recovery message to
   the thread and creates a new run on the same thread. Only emits an SSE error
   on the final failed attempt.

3. **Configuration check**: `is_configured()` validates that `agent_ids.json`
   exists and required env vars (`PROJECT_ENDPOINT`, `AI_FOUNDRY_PROJECT_NAME`)
   are set. If not configured, the alert endpoint falls back to a stub generator
   with synthetic 4-agent walkthrough events.

### Router Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/alert` | POST | Accept alert text, return SSE stream of investigation |
| `/api/agents` | GET | Return list of provisioned agents from `agent_ids.json` |
| `/api/config/current` | GET | Return current data source + agent bindings |
| `/api/config/apply` | POST | Apply new data source + prompt bindings (re-provisions agents, returns SSE progress) |
| `/api/logs` | GET | SSE stream of API process logs |
| `/health` | GET | Health check |

---

## Agent Architecture

### Connected Agents Pattern

Five Foundry agents, each scoped to one responsibility:

| Agent | Role | Data Source | Tool Type |
|-------|------|-------------|-----------|
| **Orchestrator** | Supervisor — coordinates investigation, synthesises diagnosis | — | `ConnectedAgentTool` → 4 sub-agents |
| **GraphExplorerAgent** | Topology & dependency analysis (forward/reverse trace) | Cosmos DB Gremlin | `OpenApiTool` → `/query/graph` |
| **TelemetryAgent** | Raw telemetry & alert retrieval | Cosmos DB NoSQL (SQL) | `OpenApiTool` → `/query/telemetry` |
| **RunbookKBAgent** | Procedure lookup (SOPs, diagnostics, escalation) | AI Search `runbooks-index` | `AzureAISearchTool` |
| **HistoricalTicketAgent** | Precedent search (past incidents, resolution patterns) | AI Search `tickets-index` | `AzureAISearchTool` |

The orchestrator never accesses data directly. It delegates to sub-agents via
`ConnectedAgentTool`, which creates a child thread + run on the sub-agent. Each
sub-agent has its own system prompt, tool configuration, and data scope.

### Agent Prompt Architecture

The GraphExplorerAgent prompt is **decomposed into composable parts** and assembled
at provisioning time based on `GRAPH_BACKEND`:

```
data/prompts/graph_explorer/
├── core_instructions.md    ← Role, rules, scope (backend-agnostic)
├── core_schema.md          ← 8 entity types, 7 relationship types, all instances
├── language_gremlin.md     ← Gremlin traversals, g.V() patterns (Cosmos DB)
├── language_mock.md        ← Natural language instructions (offline)
└── description.md          ← Agent description one-liner
```

`provision_agents.py` composes the full prompt:

```python
LANGUAGE_FILE_MAP = {
    "cosmosdb": "language_gremlin.md",
    "mock": "language_mock.md",
}

def load_graph_explorer_prompt() -> str:
    parts = [core_instructions, core_schema, language_file]
    return "\n\n---\n\n".join(parts)
```

All other agent prompts remain monolithic (single `.md` file) as they are
backend-agnostic.

### Backend-Aware Provisioning

`provision_agents.py` adjusts three things based on `GRAPH_BACKEND`:

1. **OpenAPI spec** — selects `openapi/{backend}.yaml`
2. **GraphExplorer prompt** — assembles from `graph_explorer/` parts with the
   correct language file
3. **Tool description** — backend-specific one-liner ("Execute a Gremlin query..." /
   "Query the topology graph...")

### Investigation Flows

The orchestrator prompt defines two investigation strategies:

- **Flow A** (known infrastructure trigger) — forward trace from cause to impact:
  infrastructure failure → affected paths → affected services → SLA exposure
- **Flow B** (alert storm / service symptoms) — backward trace from symptoms to
  root cause: service alerts → dependency chains → common infrastructure ancestor

The orchestrator autonomously selects the appropriate flow based on the alert content.

---

## Modular Data Architecture (V7)

The platform is **scenario-agnostic** — it supports multiple investigation domains
simultaneously. Each scenario is a self-contained data pack under `data/scenarios/`.

### Scenarios

| Scenario | Domain | Entity Types | Incident |
|----------|--------|-------------|----------|
| `telco-noc` | Telecommunications | CoreRouter, AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession | Fibre cut triggers cascading alert storm |
| `cloud-outage` | Cloud Infrastructure | Region, AvailabilityZone, Rack, Host, VirtualMachine, LoadBalancer, Service, SLAPolicy | Cooling failure causes thermal shutdown cascade |
| `customer-recommendation` | E-Commerce | CustomerSegment, Customer, ProductCategory, Product, Campaign, Supplier, Warehouse, SLAPolicy | Recommendation model bias spikes return rates |

### ScenarioLoader

`scripts/scenario_loader.py` provides a single entry point for resolving all
paths and configuration for any scenario:

```python
from scripts.scenario_loader import ScenarioLoader

scenario = ScenarioLoader("cloud-outage")
scenario.entities_dir          # Path to entity CSVs
scenario.graph_schema          # Path to graph_schema.yaml
scenario.default_alert         # Contents of default alert text
scenario.gremlin_graph_name()  # "cloud-outage-topology"
scenario.telemetry_database_name()  # "cloud-outage-telemetry"
scenario.to_api_response()     # Dict for /api/scenario endpoint

ScenarioLoader.list_scenarios()  # All available scenarios
```

### Scenario Structure

Each scenario provides:

```
data/scenarios/<name>/
├── scenario.yaml         # Manifest: cosmos mapping, search indexes, graph styles, baselines
├── graph_schema.yaml     # Graph ontology: vertex/edge definitions → CSV mappings
├── scripts/              # Data generation scripts (generate_topology.py, etc.)
└── data/
    ├── entities/         # Vertex CSVs (Dim*.csv) + edge CSVs (Fact*.csv)
    ├── telemetry/        # AlertStream.csv + domain-specific metrics CSV
    ├── knowledge/
    │   ├── runbooks/     # Operational procedures (.md) → AI Search
    │   └── tickets/      # Historical incidents (.txt) → AI Search
    └── prompts/          # Scenario-specific prompt fragments + default_alert.md
```

### Backwards Compatibility

Symlinks at `data/network`, `data/prompts`, `data/runbooks`, `data/tickets`,
`data/telemetry`, `data/scripts`, and `data/graph_schema.yaml` point to the
default scenario (`telco-noc`). All existing deployment scripts work unchanged
through these symlinks during the transition to multi-scenario support.

### Environment Variables

```bash
DEFAULT_SCENARIO=telco-noc      # Scenario loaded on UI start
LOADED_SCENARIOS=telco-noc      # Comma-separated list for deployment
```

---

## Error Resilience

A three-layer defence against sub-agent tool failures, designed to prevent a single
failed tool call from terminating the entire investigation.

### The Problem

Foundry's `OpenApiTool` treats HTTP 4xx/5xx responses as fatal:

```
HTTP 400 from graph-query-api
  → Foundry: tool_server_error (sub-agent run step fails)
  → Sub-agent run status = "failed"
  → ConnectedAgentTool returns failure to orchestrator
  → Orchestrator run status = "failed"
  → Entire investigation terminates
```

The orchestrator LLM **never sees** the error message. It cannot retry or adapt.

### Layer 1: Errors as 200 + Error Payload (Most Impactful)

Both `router_graph.py` and `router_telemetry.py` now catch **all** exceptions and
return HTTP 200 with the error message in the response body:

```json
{
  "columns": [],
  "data": [],
  "error": "Query error: Column 'nonexistent' not found. Please check column names and retry."
}
```

The sub-agent LLM sees the error in the tool response, reads it, and can self-correct.
The TelemetryAgent prompt already has a rule: "If a query returns an error, read the
error message and fix the query. Retry with corrected syntax."

The OpenAPI specs include the `error` field in their 200 response schemas with a
description that instructs the LLM: "If this field is present, the query failed.
Read the error, fix your query, and try again."

### Layer 2: Orchestrator Run Retry (Safety Net)

If a run still fails despite Layer 1 (e.g., transient Foundry platform error),
`orchestrator.py` retries:

- `MAX_RUN_ATTEMPTS = 2`
- On failure: posts a recovery message to the existing thread with error details
  and instructions to retry
- Creates a new run on the same thread (preserving conversation context)
- Only emits SSE error event to the frontend on the final failed attempt

### Layer 3: Graceful Degradation (Orchestrator Prompt)

Rule #8 in the orchestrator system prompt:

> **Handle sub-agent failures gracefully.** If a sub-agent call fails or returns
> an error response, do NOT terminate the investigation. Instead: note which data
> source was unavailable, continue with remaining agents, produce a situation
> report even if incomplete.

This ensures even if one data source is entirely down, the investigation continues
with the remaining agents and produces a partial but useful report.

---

## Architectural Decisions

### FastAPI over Azure Functions

| Concern | Azure Functions | FastAPI |
|---------|-----------------|---------|
| SSE streaming | Not native; requires Durable Functions workarounds | `StreamingResponse` / `sse-starlette` native |
| Orchestrator timeout | 230 s max (Consumption), needs Durable for longer | No limit (process stays alive) |
| Cold start | Yes (Consumption plan) | Container Apps: scales to zero, minimal cold start |
| Single codebase | Separate Function App project | REST + SSE all in one process |

**Decision:** FastAPI on Azure Container Apps. Single Python process serves the REST
API and SSE streaming. No cold-start penalty with min-replicas=1.

### Unified Container over Multi-Container

Originally the system deployed three separate Container Apps (`ca-api-*`,
`ca-graphquery-*`, `ca-frontend-*`). This caused inter-container networking
failures — the frontend's nginx reverse proxy couldn't reach the API container
reliably in Azure Container Apps due to internal DNS resolution and VNet routing
issues.

**Decision:** Consolidate all three services into a single container managed by
supervisord. nginx listens on `:80` and proxies to `127.0.0.1:8000` (API) and
`127.0.0.1:8100` (graph-query-api) — no cross-container networking needed.

| Concern | Multi-container | Unified container |
|---------|-----------------|-------------------|
| Networking | Container-to-container DNS, internal ingress | `127.0.0.1` — no networking issues |
| Deployment | 3 separate `azd deploy` commands | Single `azd deploy app` |
| RBAC | 3 separate managed identities | 1 identity, simpler role assignments |
| Resource efficiency | 3 × min replicas, 3 × ACR images | 1 replica, 1 image |
| Scaling | Independent scaling per service | All scale together |

The trade-off (coupled scaling) is acceptable for a demo. Production would benefit
from separating if scale demands differ significantly.

### Single `azure_config.env` for All Config

A single dotenv file is the source of truth for every part of the system:
infrastructure, scripts, API, and (via proxy) frontend. Avoids config drift between
layers. The `preprovision.sh` hook syncs selected values into `azd env` so Bicep
can read them via `readEnvironmentVariable()`. The `postprovision.sh` hook writes
deployment outputs back into the same file.

### Connected Agents over Direct Tool Calls

The orchestrator doesn't call external APIs directly. It delegates to four
sub-agents via Foundry's `ConnectedAgentTool`. Each sub-agent is scoped to one
data source and has its own system prompt. This keeps each agent focused and
testable independently.

### OpenApiTool + graph-query-api

GraphExplorerAgent and TelemetryAgent access data through a dedicated
Container App micro-service (`graph-query-api`). `ConnectedAgentTool`
sub-agents run server-side on Foundry and cannot execute client-side `FunctionTool`
callbacks. `OpenApiTool` enables server-side REST calls, so it works natively
and provides full control over query construction and error handling
(retry logic, errors-as-200, etc.).

### Backend-Agnostic Graph Abstraction (V4)

The graph endpoint (`/query/graph`) is decoupled from any specific graph database
via a `GraphBackend` Protocol. Switching backends requires only changing
`GRAPH_BACKEND` env var and re-provisioning agents. No code changes to the agent
layer, API, or frontend.

---

## SSE Event Protocol

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

---

## Frontend Architecture — V6 NOC Dashboard

Dark theme component-based three-zone dashboard with vertically and horizontally
resizable panels. Built with React 18, Vite, Tailwind CSS, Framer Motion, and
react-force-graph-2d (interactive graph topology explorer).

### Design System

- CSS custom properties for all colours (`--brand`, `--bg-*`, `--text-*`, `--status-*`)
- Glass morphism utilities: `glass-card`, `glass-panel`, `glass-input`, `glass-overlay`
- Framer Motion for all transitions: `AnimatePresence`, stagger containers, spring-physics buttons
- `clsx` for conditional class composition
- `focus-visible` ring styles for keyboard accessibility

### Layout Structure

(`h-screen flex flex-col`, no page scroll):

```
┌──────────────────────────────────────────────────────────────────────┐
│  Header          (h-12, fixed)                              Zone 1  │
├──────────────────────────────────────────────────────────────────────┤
│  MetricsBar      (resizable height, default 30%)            Zone 2  │
│  [GraphTopologyViewer (64%)]  [API Logs (36%)]                      │
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

### State Management

All SSE state lives in `useInvestigation()` custom hook. The hook returns
`{ alert, setAlert, steps, thinking, finalMessage, errorMessage, running,
runStarted, runMeta, submitAlert }`. `App.tsx` calls the hook and passes
props down. Both panels read from the same hook instance. The hook uses
`@microsoft/fetch-event-source` to issue POST-based SSE requests (standard
`EventSource` is GET-only).

### Live Log Streaming

A `LogStream` component in the metrics bar displays real-time backend logs via SSE:
- **API logs** (`/api/logs`) — captures `app.*`, `azure.*`, and `uvicorn` log
  output from the FastAPI process

The LogStream supports auto-scroll, manual scroll-pause, and connection status.

### Interactive Graph Topology Explorer (V6)

The `GraphTopologyViewer` in Zone 2 renders the full network topology as an
interactive force-directed graph powered by `react-force-graph-2d`.

**Data flow:** `useTopology` hook → `POST /query/topology` → `graph-query-api`
→ `GraphBackend.get_topology()` → returns nodes + edges → rendered in `GraphCanvas`.

**Component tree:**

```
GraphTopologyViewer.tsx          ← Orchestrator: composes all sub-components
├── useTopology()                ← Data hook: fetches topology, manages loading/error
├── GraphToolbar.tsx             ← Search input, label filter chips, zoom-to-fit, refresh
├── GraphCanvas.tsx              ← react-force-graph-2d wrapper with custom node rendering
├── GraphTooltip.tsx             ← Hover tooltip showing node/edge properties
└── GraphContextMenu.tsx         ← Right-click: display field picker + colour customisation
```

**Key features:**
- Colour-coded nodes by vertex type (8 types × distinct colours in `graphConstants.ts`)
- Label filter chips in the toolbar — click to show/hide vertex types
- Client-side search across node IDs and display fields
- Right-click any node to change its display field or colour
- Customisations persisted to `localStorage`
- `ResizeObserver` dynamically sizes canvas to fill available panel space
- Edge labels rendered on hover, curved edges between multi-connected nodes

### Hardcoded vs Live Data

The investigation panel (SSE steps), diagnosis panel (final markdown), log streams,
and the graph topology explorer are all connected to the live backend. Previous
hardcoded KPI cards and alert chart have been replaced by the interactive graph
topology viewer.

---

## Infrastructure as Code

Subscription-scoped Bicep deployment via `azd up`. The parameter file reads from
environment variables (synced from `azure_config.env` by `preprovision.sh`).
Resources use a deterministic `resourceToken` derived from subscription + env name +
location, so names are globally unique and reproducible.

### Bicep Modules

| Module | Resources |
|--------|-----------|
| `ai-foundry.bicep` | AI Foundry account + project + GPT-4.1 deployment |
| `search.bicep` | Azure AI Search service |
| `storage.bicep` | Storage account + blob containers (runbooks, tickets) |
| `container-apps-environment.bicep` | Log Analytics workspace + ACR + Managed Environment |
| `container-app.bicep` | Generic Container App template (managed identity) |
| `cosmos-gremlin.bicep` | Cosmos DB account (Gremlin API + NoSQL), database, graph, telemetry containers |
| `vnet.bicep` | VNet with Container Apps + Private Endpoints subnets |
| `cosmos-private-endpoints.bicep` | Private endpoints for Cosmos DB Gremlin + NoSQL accounts |
| `roles.bicep` | RBAC assignments (user + service principals + container app identity) |

### RBAC Roles (Container App Identity)

The unified container app's system-assigned managed identity requires these roles
to invoke Foundry agents and access data:

| Role | Scope | Why |
|------|-------|-----|
| Cognitive Services OpenAI User | Foundry account | Invoke GPT models |
| Cognitive Services Contributor | Foundry account | Manage agents, threads, runs |
| Azure AI Developer | Resource group | `MachineLearningServices/workspaces/agents/*` actions |
| Cognitive Services User | Foundry account | Broad `Microsoft.CognitiveServices/*` including `AIServices/agents/read` |
| Cosmos DB Built-in Data Contributor | NoSQL account | Query/write telemetry via DefaultAzureCredential |
| DocumentDB Account Contributor | Gremlin account | Create/delete graphs via ARM (scenario upload) |
| Storage Blob Data Contributor | Storage account | Upload runbooks/tickets to blob (scenario upload) |
| Search Service Contributor | AI Search | Create indexes, data sources, skillsets, indexers |
| Search Index Data Contributor | AI Search | Read/write index data |

All roles are codified in `roles.bicep` and applied automatically during `azd up`.

### Deployment: `deploy.sh` (End-to-End) and `azd up`

The primary deployment method is `deploy.sh`, which orchestrates the entire
pipeline in one command:

1. Prerequisites check and Azure login
2. Environment selection / creation
3. `azd up` (infra + unified container deployment)
4. (Informational) AI Search indexes are created during scenario upload via UI
5. (Informational) Cosmos DB data is loaded during scenario upload via UI
6. Health verification
7. AI Foundry agent provisioning (5 agents — initial CLI bootstrap)
8. Redeploy container with `agent_ids.json` baked in
9. Local API + Frontend startup (optional)

After initial deployment, all data operations (graph loading, telemetry ingestion,
search indexing, agent reconfiguration) are managed through the UI Settings page
(⚙ icon in the header).

**Skip flags** allow selectively bypassing steps during iterative development:

| Flag | Skips |
|------|-------|
| `--skip-infra` | Step 3 (`azd up`) — skip infrastructure provisioning |
| `--skip-index` | Step 4 — already informational |
| `--skip-data` | Step 5 — already informational |
| `--skip-agents` | Step 7 — skip agent provisioning |
| `--skip-local` | Step 9 — skip local API + frontend startup |
| `--yes` | Auto-confirm all prompts |

`azd up` runs the infrastructure + service deployment cycle:
1. `preprovision.sh` syncs `azure_config.env` → azd environment variables
2. Bicep provisions all Azure resources (VNet, Container Apps Environment + ACR, etc.)
3. Builds and deploys the unified container (Docker image built in ACR via `remoteBuild`)
4. `postprovision.sh` uploads data to blob, writes deployment outputs to `azure_config.env`

For code-only changes, use `azd deploy app` without re-running the full
`azd up`. This rebuilds the container image and creates a new Container App
revision (~60 seconds).

---

## Configuration Signpost

All runtime configuration lives in `azure_config.env`. The template
(`azure_config.env.template`) documents every variable, its purpose, and whether
it's user-set or auto-populated.

### Variable Groups

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
| **Model Deployments** | | |
| `MODEL_DEPLOYMENT_NAME` | user | scripts (provision_agents), Bicep |
| `EMBEDDING_MODEL` | user | scripts (create_*_indexer) |
| `EMBEDDING_DIMENSIONS` | user | scripts (create_*_indexer) |
| `GPT_CAPACITY_1K_TPM` | user | preprovision → Bicep |
| **AI Search** | | |
| `AI_SEARCH_NAME` | postprovision | scripts (create_*_indexer) |
| `RUNBOOKS_INDEX_NAME` | user | scripts (create_runbook_indexer) |
| `TICKETS_INDEX_NAME` | user | scripts (create_tickets_indexer) |
| **Storage** | | |
| `STORAGE_ACCOUNT_NAME` | postprovision | scripts |
| `RUNBOOKS_CONTAINER_NAME` | user | scripts, must match Bicep container name |
| `TICKETS_CONTAINER_NAME` | user | scripts, must match Bicep container name |
| **Graph Backend** | | |
| `GRAPH_BACKEND` | user | graph-query-api (config.py), provision_agents.py |
| **graph-query-api / Unified App** | | |
| `APP_URI` | postprovision (azd output) | scripts (provision_agents — used as GRAPH_QUERY_API_URI) |
| `APP_PRINCIPAL_ID` | postprovision (azd output) | scripts |
| `GRAPH_QUERY_API_URI` | postprovision (= APP_URI) | scripts (provision_agents — OpenApiTool server URL) |
| **Cosmos DB Gremlin** | | |
| `COSMOS_GREMLIN_ENDPOINT` | postprovision | graph-query-api |
| `COSMOS_GREMLIN_PRIMARY_KEY` | postprovision | graph-query-api |
| `COSMOS_GREMLIN_DATABASE` | user (default: networkgraph) | graph-query-api |
| `COSMOS_GREMLIN_GRAPH` | user (default: topology) | graph-query-api |
| **Cosmos DB NoSQL (Telemetry)** | | |
| `COSMOS_NOSQL_ENDPOINT` | postprovision | graph-query-api |
| `COSMOS_NOSQL_DATABASE` | user (default: telemetry) | graph-query-api |
| **App / CORS** | | |
| `CORS_ORIGINS` | user | API (main.py CORS middleware) |

### Config Files Beyond azure_config.env

| File | Purpose | Consumed by |
|------|---------|-------------|
| `azure.yaml` | azd project definition: hook paths, service targets | azd CLI |
| `pyproject.toml` (root) | Python deps for scripts/ | uv (scripts) |
| `api/pyproject.toml` | Python deps for API | uv (api) |
| `graph-query-api/pyproject.toml` | Python deps for graph-query-api | uv (graph-query-api) |
| `frontend/package.json` | Node deps for frontend | npm |
| `frontend/vite.config.ts` | Dev server port, `/api` proxy → :8000, `/query` proxy → :8100 | Vite |
| `frontend/tailwind.config.js` | Colour system, fonts | Tailwind CSS |
| `infra/main.bicepparam` | Bicep parameter values (reads env vars) | azd/Bicep |
| `scripts/agent_ids.json` | Provisioned Foundry agent IDs | scripts, API (orchestrator) |
| `scripts/agent_provisioner.py` | Importable agent creation class | API config endpoint, CLI wrapper |
| `data/scenarios/*/data/prompts/*.md` | Scenario prompt fragments (seed data) | Uploaded to Cosmos during scenario upload |

---

## Data Flow

### Provisioning Pipeline (One-Time Setup)

```
azure_config.env → preprovision.sh → azd up (Bicep) → postprovision.sh → azure_config.env
                                       │                ├─ uploads runbooks/ → blob (fallback)
                                       │                └─ uploads tickets/  → blob (fallback)
                                       │
                                       ├─ VNet (Container Apps + Private Endpoints subnets)
                                       ├─ Container Apps Environment (ACR + Log Analytics)
                                       ├─ Unified Container App (nginx + API + graph-query-api)
                                       └─ Cosmos DB Private Endpoints (Gremlin + NoSQL)

# Data loading (via UI — POST /query/scenario/upload):
Upload .tar.gz → graph-query-api:
  ├─ Graph data (CSVs → Cosmos Gremlin via ARM + gremlinpython)
  ├─ Telemetry data (CSVs → Cosmos NoSQL via azure-cosmos)
  ├─ Prompts (.md → Cosmos platform-config.prompts)
  ├─ Runbooks (.md → Blob → AI Search indexer pipeline)
  └─ Tickets (.txt → Blob → AI Search indexer pipeline)

provision_agents.py ──── creates 5 Foundry agents ─────▶ agent_ids.json
  ├─ GraphExplorerAgent   (OpenApiTool → graph-query-api /query/graph)
  ├─ TelemetryAgent       (OpenApiTool → graph-query-api /query/telemetry)
  ├─ RunbookKBAgent       (AzureAISearchTool → {scenario}-runbooks-index)
  ├─ HistoricalTicketAgent(AzureAISearchTool → {scenario}-tickets-index)
  └─ Orchestrator         (ConnectedAgentTool → all 4 above)

# After agent provisioning:
azd deploy app ─── rebakes container with agent_ids.json ──▶ Container App updated
```

### Runtime Flow (Per Alert)

```
User types alert in frontend
  → POST /api/alert {text: "..."}
  → API creates orchestrator thread + run (azure-ai-agents SDK)
  → Background thread streams AgentEvents via SSEEventHandler callbacks
  → Orchestrator delegates to sub-agents via ConnectedAgentTool:
  ├─ GraphExplorerAgent → OpenApiTool → graph-query-api /query/graph
      │   → dispatches to backends/{GRAPH_BACKEND}.py (graph from X-Graph header)
      ├─ TelemetryAgent → OpenApiTool → graph-query-api /query/telemetry
      │   → CosmosClient → Cosmos DB NoSQL (database from ScenarioContext)
      ├─ RunbookKBAgent → AzureAISearchTool → {scenario}-runbooks-index
      └─ HistoricalTicketAgent → AzureAISearchTool → {scenario}-tickets-index
  → Each sub-agent call yields SSE events (step_start, step_thinking, step_complete)
  → Orchestrator synthesises situation report → SSE message event
  → Frontend renders timeline + diagnosis markdown
```

### Error Recovery Flow

```
Sub-agent tool call returns error (e.g., bad SQL syntax)
  → graph-query-api catches exception, returns 200 + {error: "..."}
  → Sub-agent LLM reads error message
  → Sub-agent retries with corrected query (prompt instructs self-repair)
  → If sub-agent run still fails:
      → Orchestrator run fails
      → orchestrator.py retry loop posts recovery message
      → New run created on same thread
      → If final attempt fails: SSE error event to frontend
```

---

## Deployment Targets

| Component | Local | Production |
|-----------|-------|------------|
| Unified container (nginx + API + graph-query-api) | N/A | Azure Container Apps (via `azd deploy app`) |
| API | `uvicorn :8000` | Inside unified container (:8000 on localhost) |
| graph-query-api | `uvicorn :8100` | Inside unified container (:8100 on localhost) |
| Frontend | Vite dev server `:5173` | Static build inside unified container (nginx :80) |
| Infra | n/a | `azd up` → Azure |

All three services are bundled into a single Container App (`ca-app-{token}`) via
the root `Dockerfile`. The `azure.yaml` defines one service `app` that builds from
the project root. For code-only changes, use `azd deploy app` (~60 seconds).

---

## SDK Versions

| Package | Version | Notes |
|---------|---------|-------|
| `azure-ai-projects` | `>=1.0.0,<2.0.0` | v2 has breaking API changes |
| `azure-ai-agents` | `1.2.0b6` | `OpenApiTool`, `ConnectedAgentTool`, `AzureAISearchTool` |
| `azure-cosmos` | `>=4.9.0` | SQL queries + NoSQL upserts |
| `azure-storage-blob` | `>=12.19.0` | Blob upload for knowledge files |
| `azure-search-documents` | `>=11.6.0` | AI Search indexer pipeline creation |
| `azure-mgmt-cosmosdb` | `>=9.0.0` | ARM graph creation (management plane) |
| `gremlinpython` | `>=3.7.0` | Cosmos DB Gremlin data-plane operations |
| `fastapi` | `>=0.115` | ASGI framework |
| `sse-starlette` | `>=1.6` | SSE responses (progress streaming) |
| `react` | `18.x` | UI library |
| `framer-motion` | `11.x` | Animation |
| `@microsoft/fetch-event-source` | `^2.0.1` | POST-capable SSE client |
| `react-markdown` | `^10.1.0` | Markdown rendering in diagnosis + step cards |
| `react-resizable-panels` | `^4.6.2` | Resizable panel layout |
| `react-force-graph-2d` | `^1.26.9` | Force-directed graph visualisation |
| `tailwindcss` | `3.x` | Utility-first CSS |

---

## Extension Guidance

### Add a New Graph Backend

1. Create `graph-query-api/backends/{name}.py` implementing `GraphBackend` Protocol
   (constructor must accept `graph_name` parameter)
2. Add the backend to `config.py` `GraphBackendType` enum and `BACKEND_REQUIRED_VARS`
3. Register in `backends/__init__.py` `get_backend_for_graph()` factory
4. Create `graph-query-api/openapi/{name}.yaml` with query language description
5. Create language prompt file in scenario data (`graph_explorer/language_{name}.md`)
6. Add to `OPENAPI_SPEC_MAP`, `GRAPH_TOOL_DESCRIPTIONS` in `agent_provisioner.py`
7. Re-provision agents via UI Settings → Apply Changes (or CLI fallback)

### Add a New Sub-Agent

1. Create system prompt as a `.md` file in the scenario's `data/prompts/` directory
2. Add to `PROMPT_AGENT_MAP` in `router_ingest.py` (for auto-import during upload)
3. Add agent creation function in `agent_provisioner.py`
4. Add as `ConnectedAgentTool` to the orchestrator in `provision_all()`
5. Update orchestrator prompt to describe the new agent's capabilities
6. Re-provision agents via UI Settings or CLI

### Frontend Customisation

- **Adjust zone split:** Change `defaultSize` props in `App.tsx` (currently 30/70)
- **Add panels to metrics bar:** Add `<Panel>` entries in `MetricsBar.tsx` alongside the graph viewer
- **Customise graph colours:** Edit `NODE_COLORS` in `graphConstants.ts` (or use server-driven styles from `scenario.yaml`)
- **Add graph context menu actions:** Extend `GraphContextMenu.tsx`
- **Settings tabs:** Add new tabs to `SettingsModal.tsx` (next: Agent Config tab for prompt editors)
- **Scenario context:** Access active graph/index state via `useScenarioContext()` from any component
