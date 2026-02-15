# Architecture — AI Incident Investigator

> **Last updated:** 2026-02-15 — reflects V8 data management plane +
> scenario management (SCENARIOHANDLING.md) with first-class scenario
> CRUD, per-type uploads, per-request graph routing, Cosmos-backed prompts,
> unified container deployment, and UI scenario switching with auto-provisioning.

---

## Table of Contents

- [System Overview](#system-overview)
- [Unified Container Architecture](#unified-container-architecture)
- [Project Structure](#project-structure-as-of-2026-02-15)
- [Complete API Surface](#complete-api-surface)
- [Data Flow](#data-flow)
- [SSE Event Protocols](#sse-event-protocols)
- [Key Components Detail](#key-components-detail)
- [Frontend Architecture](#frontend-architecture)
- [Data Schema & Generation](#data-schema--generation)
- [Infrastructure (Bicep)](#infrastructure-bicep)
- [Dockerfile & Container Build](#dockerfile--container-build)
- [RBAC Roles](#rbac-roles-container-app-managed-identity)
- [Deployment](#deployment)
- [Error Resilience](#error-resilience)
- [Critical Patterns & Lessons](#critical-patterns--lessons)
- [Known Issues & Gotchas](#known-issues--gotchas)
- [Configuration Reference](#configuration-reference)
- [Quick Reference: Where to Fix Things](#quick-reference-where-to-fix-things)
- [Scenario Management](#scenario-management)
- [SDK Versions](#sdk-versions)

---

## System Overview

Multi-agent incident investigation platform. Five AI agents collaborate
(via Azure AI Foundry) to diagnose operational incidents across any domain—
telecommunications, cloud infrastructure, e-commerce, etc.

The platform is **scenario-agnostic**: users upload scenario data packs via
the browser UI. The Container App ingests graph data, telemetry, knowledge
bases, and prompts into Azure services. No CLI-based data loading required.

**Scenario management** is a first-class feature: users create named scenarios
that bundle all 5 data types, switch between them with one click (auto-provisioning
agents), and persist selections across sessions via `localStorage`. See
[Scenario Management](#scenario-management) and `documentation/SCENARIOHANDLING.md`.

### Available Scenarios

| Scenario | Domain | Entity Types | Incident |
|----------|--------|-------------|----------|
| `telco-noc` | Telecom | CoreRouter, AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession | Fibre cut → cascading alert storm |
| `cloud-outage` | Cloud | Region, AZ, Rack, Host, VM, LoadBalancer, Service, SLAPolicy | Cooling failure → thermal shutdown cascade |
| `customer-recommendation` | E-Commerce | CustomerSegment, Customer, ProductCategory, Product, Campaign, Supplier, Warehouse, SLAPolicy | Recommendation model bias → return rate spike |

---

## Unified Container Architecture

All three services run in a **single container** managed by supervisord:

| Process | Bind Address | Role |
|---------|-------------|------|
| nginx | `0.0.0.0:80` (external) | Reverse proxy + React SPA |
| API (uvicorn) | `127.0.0.1:8000` | Agent orchestrator, SSE streaming, config endpoints |
| graph-query-api (uvicorn) | `127.0.0.1:8100` | Graph/telemetry queries, data upload, prompt CRUD |

### nginx Routes

| Path | Upstream | Timeout | Notes |
|------|----------|---------|-------|
| `/` | React SPA (`/usr/share/nginx/html`) | — | `try_files $uri $uri/ /index.html` (SPA fallback) |
| `/api/*` | `proxy_pass http://127.0.0.1:8000` | 300s | SSE: `proxy_buffering off`, `proxy_cache off` |
| `/health` | `proxy_pass http://127.0.0.1:8000` | — | Health check |
| `/query/*` | `proxy_pass http://127.0.0.1:8100` | 600s | SSE: `proxy_buffering off`, `proxy_cache off` |

**`client_max_body_size 100m`** is set at **server block level** — applies to ALL routes, not just `/query/*`.

Security headers: `X-Frame-Options SAMEORIGIN`, `X-Content-Type-Options nosniff`.
Gzip enabled for text/CSS/JSON/JS/XML.

### Request Flow Diagram

```
Browser ─── POST /api/alert ──▶ nginx :80 ──▶ API :8000 ──▶ AI Foundry
       ◀── SSE stream ─────────                              (5 agents)
                                                                │
Browser ─── POST /query/upload/graph ──▶ nginx :80 ──▶ graph-query-api :8100
       ◀── SSE progress ──────────                    ├── Cosmos Gremlin
                                                      ├── Cosmos NoSQL
                                                      ├── AI Search
                                                      └── Blob Storage
```

### supervisord Config

3 programs, all `autostart=true`, `autorestart=true`:

| Program | Command | Working Dir | Priority |
|---------|---------|-------------|----------|
| nginx | `nginx -g "daemon off;"` | — | 10 |
| api | `/usr/local/bin/uv run uvicorn app.main:app --host 127.0.0.1 --port 8000` | `/app/api` | 20 |
| graph-query-api | `/usr/local/bin/uv run uvicorn main:app --host 127.0.0.1 --port 8100` | `/app/graph-query-api` | 20 |

All programs log to `stdout`/`stderr` (`logfile_maxbytes=0`). Pid file: `/var/run/supervisord.pid`.

---

## Project Structure (as of 2026-02-15)

```
.
├── deploy.sh                   # Deployment: infra only (Steps 0-3, 6-7)
├── Dockerfile                  # Unified container (nginx + API + graph-query-api)
├── nginx.conf                  # Reverse proxy (100m upload, SSE support)
├── supervisord.conf            # Process manager
├── azure.yaml                  # azd service definition
├── azure_config.env            # Runtime config (gitignored, auto-populated)
├── azure_config.env.template   # Config template
│
├── api/                        # FastAPI backend (:8000)
│   ├── pyproject.toml          # Deps: fastapi, sse-starlette, azure-ai-agents, pyyaml
│   └── app/
│       ├── main.py             # Mounts 4 routers + /health + CORS
│       ├── orchestrator.py     # Foundry agent bridge (sync SDK → async SSE)
│       └── routers/
│           ├── alert.py        # POST /api/alert → SSE investigation stream
│           ├── agents.py       # GET /api/agents → agent list from agent_ids.json
│           ├── config.py       # POST /api/config/apply → SSE provisioning stream
│           │                   # GET /api/config/current → current config state
│           └── logs.py         # GET /api/logs → SSE log broadcast
│
├── graph-query-api/            # Data management + query microservice (:8100)
│   ├── pyproject.toml          # Deps: fastapi, gremlinpython, azure-cosmos,
│   │                           #       azure-mgmt-cosmosdb, azure-storage-blob,
│   │                           #       azure-search-documents, sse-starlette, pyyaml
│   ├── config.py               # ScenarioContext, X-Graph header, env vars, credential
│   ├── main.py                 # Mounts 6 routers + /health + /api/logs (SSE) + request logging middleware
│   ├── models.py               # Pydantic request/response models
│   ├── router_graph.py         # POST /query/graph (per-scenario Gremlin)
│   ├── router_telemetry.py     # POST /query/telemetry (per-scenario NoSQL)
│   ├── router_topology.py      # POST /query/topology (graph visualization)
│   ├── router_ingest.py        # Upload endpoints + scenario/index listing (1329 lines)
│   ├── router_prompts.py       # Prompts CRUD in Cosmos (334 lines)
│   ├── router_scenarios.py     # Scenario metadata CRUD in Cosmos (272 lines)
│   ├── search_indexer.py       # AI Search indexer pipeline creation
│   ├── openapi/
│   │   ├── cosmosdb.yaml       # OpenAPI spec for live mode (has {base_url} placeholder)
│   │   └── mock.yaml           # OpenAPI spec for mock mode
│   └── backends/
│       ├── __init__.py         # GraphBackend Protocol + per-graph cache + factory
│       ├── cosmosdb.py         # CosmosDBGremlinBackend (304 lines, retry logic)
│       └── mock.py             # Static topology (offline demos)
│
├── frontend/                   # React/Vite dashboard
│   ├── package.json            # Deps: react, react-force-graph-2d,
│   │                           #       @microsoft/fetch-event-source, framer-motion,
│   │                           #       react-markdown, react-resizable-panels, tailwindcss
│   ├── vite.config.ts          # Dev proxy: /api→:8000, /query→:8100, /health→:8000
│   └── src/
│       ├── main.tsx            # Wraps App in ScenarioProvider
│       ├── App.tsx             # 3-zone layout (useInvestigation hook)
│       ├── types/index.ts      # Shared TypeScript interfaces (StepEvent, SavedScenario, etc.)
│       ├── context/
│       │   └── ScenarioContext.tsx  # Full scenario state: activeScenario, bindings,
│       │                           # provisioningStatus, localStorage persistence,
│       │                           # auto-derivation (105 lines)
│       ├── hooks/
│       │   ├── useInvestigation.ts  # SSE alert investigation (POST, sends X-Graph)
│       │   ├── useTopology.ts       # Topology fetch (POST, sends X-Graph, auto-refetch)
│       │   └── useScenarios.ts      # Graph/index discovery + saved scenario CRUD +
│       │                            # selectScenario with auto-provisioning (180 lines)
│       ├── utils/
│       │   └── sseStream.ts         # Shared consumeSSE() + uploadWithSSE() utilities (143 lines)
│       └── components/
│           ├── Header.tsx           # Title bar + ScenarioChip + ProvisioningBanner + HealthDot + ⚙
│           ├── ScenarioChip.tsx     # Header scenario selector chip + flyout dropdown (154 lines)
│           ├── ProvisioningBanner.tsx # Non-blocking 28px banner during agent provisioning (102 lines)
│           ├── AddScenarioModal.tsx  # Scenario creation: name + 5 slot file upload + auto-detect (621 lines)
│           ├── HealthDot.tsx        # Polls /health every 15s
│           ├── SettingsModal.tsx     # 3 tabs: Scenarios + Data Sources + Upload (contains UploadBox)
│           ├── MetricsBar.tsx       # Resizable panel: topology viewer + log stream
│           ├── GraphTopologyViewer.tsx  # Owns all overlay state, delegates to graph/*
│           ├── InvestigationPanel.tsx   # Alert input + agent timeline
│           ├── DiagnosisPanel.tsx    # Final markdown report (ReactMarkdown)
│           ├── AlertInput.tsx       # Textarea + submit button
│           ├── AgentTimeline.tsx     # Step cards + thinking dots
│           ├── StepCard.tsx         # Individual agent step display
│           ├── ThinkingDots.tsx     # Animated thinking indicator
│           ├── ErrorBanner.tsx      # Error display
│           ├── LogStream.tsx        # SSE log viewer (EventSource → /api/logs)
│           └── graph/
│               ├── GraphCanvas.tsx      # ForceGraph2D wrapper (forwardRef, canvas rendering)
│               ├── GraphToolbar.tsx     # Label filters, search, zoom controls
│               ├── GraphTooltip.tsx     # Hover tooltip (framer-motion)
│               ├── GraphContextMenu.tsx # Right-click: display field + color picker
│               └── graphConstants.ts    # NODE_COLORS and NODE_SIZES by vertex label
│
├── data/
│   ├── generate_all.sh         # Generate + package all scenarios as 5 per-type tarballs
│   ├── prompts                 # Symlink → scenarios/telco-noc/data/prompts
│   └── scenarios/
│       ├── telco-noc/          # scenario.yaml, graph_schema.yaml, scripts/, data/
│       ├── cloud-outage/       # Same structure
│       └── customer-recommendation/  # Same structure
│
├── scripts/
│   ├── scenario_loader.py      # ScenarioLoader class (resolves scenario paths)
│   ├── agent_provisioner.py    # AgentProvisioner class (importable, 277 lines)
│   ├── provision_agents.py     # CLI wrapper for agent provisioning
│   ├── agent_ids.json          # Output of provisioning (agent IDs) — read by orchestrator
│   └── testing_scripts/        # CLI test tools
│
├── infra/                      # Bicep IaC
│   ├── main.bicep              # Subscription-scoped (creates RG, deploys 9 modules)
│   └── modules/                # vnet, search, storage, cosmosGremlin, aiFoundry,
│                               # containerAppsEnv, app, roles, cosmosPrivateEndpoints
│
├── hooks/
│   ├── preprovision.sh         # Syncs azure_config.env → azd env (5 vars)
│   └── postprovision.sh        # Populates azure_config.env + Cosmos credentials
│
└── deprecated/                 # Superseded scripts (kept for reference)
    └── scripts/                # Old CLI-based indexers + Cosmos provisioners
```

---

## Complete API Surface

### API Service (`:8000`)

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| POST | `/api/alert` | SSE stream | Submit alert text → orchestrator investigation |
| GET | `/api/agents` | JSON | List provisioned agents (from `agent_ids.json` or stubs) |
| POST | `/api/config/apply` | SSE stream | Re-provision 5 agents with new bindings |
| GET | `/api/config/current` | JSON | Current active configuration state |
| GET | `/api/logs` | SSE stream | Real-time log broadcast (fan-out to all clients) |
| GET | `/health` | JSON `{"status": "ok"}` | Health check |

### graph-query-api Service (`:8100`)

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| POST | `/query/graph` | JSON | Gremlin query (per-scenario via `X-Graph` header) |
| POST | `/query/telemetry` | JSON | Cosmos SQL query (per-scenario via `X-Graph` header) |
| POST | `/query/topology` | JSON | Graph topology for visualization (via `X-Graph` header) |
| GET | `/query/scenarios` | JSON | List loaded graphs (ARM discovery + fallback Gremlin) |
| DELETE | `/query/scenario/{graph_name}` | JSON | Drop all vertices/edges from a graph |
| GET | `/query/indexes` | JSON | List AI Search indexes (typed: runbooks/tickets/other) |
| GET | `/api/logs` | SSE stream | graph-query-api’s own log stream (only `graph-query-api.*` loggers; shadowed by nginx routing `/api/*`→:8000 — only reachable directly on :8100) |
| POST | `/query/upload/graph` | SSE stream | Upload graph tarball → Cosmos Gremlin |
| POST | `/query/upload/telemetry` | SSE stream | Upload telemetry tarball → Cosmos NoSQL |
| POST | `/query/upload/runbooks` | SSE stream | Upload runbooks tarball → Blob + AI Search |
| POST | `/query/upload/tickets` | SSE stream | Upload tickets tarball → Blob + AI Search |
| POST | `/query/upload/prompts` | SSE stream | Upload prompts tarball → Cosmos NoSQL |
| GET | `/query/prompts` | JSON | List prompts (filter: `?agent=X&scenario=Y`) |
| GET | `/query/prompts/scenarios` | JSON | List distinct scenario names with prompt counts |
| GET | `/query/prompts/{prompt_id}` | JSON | Get specific prompt (requires `?agent=X` for partition key) |
| POST | `/query/prompts` | JSON | Create new prompt (auto-versions) |
| PUT | `/query/prompts/{prompt_id}` | JSON | Update metadata only (content is immutable per version) |
| DELETE | `/query/prompts/{prompt_id}` | JSON | Soft-delete (`deleted=True`, `is_active=False`) |
| GET | `/query/scenarios/saved` | JSON | List all saved scenario records from Cosmos |
| POST | `/query/scenarios/save` | JSON | Upsert scenario metadata document after uploads |
| DELETE | `/query/scenarios/saved/{name}` | JSON | Delete scenario metadata (preserves underlying data) |
| GET | `/health` | JSON | Health check |

### Request/Response Models (`graph-query-api/models.py`)

```python
# --- Graph Query ---
class GraphQueryRequest:
    query: str                           # Gremlin query string

class GraphQueryResponse:
    columns: list[dict]                  # [{name: str, type: str}]
    data: list[dict]                     # Flattened vertex/edge property dicts
    error: str | None                    # If set, query failed — LLM reads this to self-correct

# --- Telemetry Query ---
class TelemetryQueryRequest:
    query: str                           # Cosmos SQL query string
    container_name: str = "AlertStream"  # NoSQL container to query

class TelemetryQueryResponse:
    columns: list[dict]
    rows: list[dict]
    error: str | None

# --- Topology (graph viewer) ---
class TopologyRequest:
    query: str | None = None             # Reserved but NOT supported — raises ValueError
    vertex_labels: list[str] | None      # Optional label filter

class TopologyResponse:
    nodes: list[TopologyNode]            # {id, label, properties}
    edges: list[TopologyEdge]            # {id, source, target, label, properties}
    meta: TopologyMeta | None            # {node_count, edge_count, query_time_ms, labels}
    error: str | None
```

---

## Data Flow

### Upload Flow (5 independent paths)

Each data type has its own tarball and upload endpoint. All uploads stream
SSE progress events and run sync Azure SDK calls in background threads.

```
./data/generate_all.sh telco-noc
  → telco-noc-graph.tar.gz      (scenario.yaml + graph_schema.yaml + data/entities/*.csv)
  → telco-noc-telemetry.tar.gz  (scenario.yaml + data/telemetry/*.csv)
  → telco-noc-runbooks.tar.gz   (scenario.yaml + data/knowledge/runbooks/*.md)
  → telco-noc-tickets.tar.gz    (scenario.yaml + data/knowledge/tickets/*.txt)
  → telco-noc-prompts.tar.gz    (scenario.yaml + data/prompts/*.md + graph_explorer/)
```

| Upload Box | Endpoint | Backend | Storage Target |
|------------|----------|---------|----------------|
| 🔗 Graph | `POST /query/upload/graph` | Gremlin addV/addE (key auth, single thread) | Cosmos Gremlin graph `{scenario}-topology` |
| 📊 Telemetry | `POST /query/upload/telemetry` | ARM create db/containers + data-plane upsert | Cosmos NoSQL db `{scenario}-telemetry` |
| 📋 Runbooks | `POST /query/upload/runbooks` | Blob upload + AI Search indexer pipeline | Blob `{scenario}-runbooks` → index `{scenario}-runbooks-index` |
| 🎫 Tickets | `POST /query/upload/tickets` | Blob upload + AI Search indexer pipeline | Blob `{scenario}-tickets` → index `{scenario}-tickets-index` |
| 📝 Prompts | `POST /query/upload/prompts` | ARM create db/container + data-plane upsert | Cosmos NoSQL db `{scenario}-prompts`, container `prompts`, PK `/agent` |

### Upload Endpoint Internal Pattern

All upload endpoints follow this exact pattern and accept an optional
`scenario_name` query parameter that **overrides** the name from `scenario.yaml`:

```python
@router.post("/upload/{type}")
async def upload_type(file: UploadFile, scenario_name: str | None = Query(default=None)):
    content = await file.read()
    async def stream():
        progress = asyncio.Queue()
        def emit(step, detail, pct):
            progress.put_nowait({"step": step, "detail": detail, "pct": pct})
        async def run():
            def _load():               # ← ALL Azure SDK calls happen here (sync)
                # Extract tarball → temp dir
                # Read scenario.yaml for scenario name
                # If scenario_name param provided, OVERRIDE manifest name
                name = scenario_name or manifest["name"]
                # ARM phase (create resources) → Data plane (upsert data)
                emit("phase", "message", 50)
            await asyncio.to_thread(_load)  # ← Critical: must use to_thread
            progress.put_nowait(None)        # ← Sentinel: end of stream
        task = asyncio.create_task(run())
        while True:
            ev = await progress.get()
            if ev is None: break
            if "_result" in ev:
                yield {"event": "complete", "data": json.dumps(ev)}
            elif ev.get("pct", 0) < 0:
                yield {"event": "error", "data": json.dumps(ev)}
            else:
                yield {"event": "progress", "data": json.dumps(ev)}
    return EventSourceResponse(stream())
```

**Upload endpoint `scenario_name` parameter status:**

| Endpoint | `scenario_name` param | Override behavior |
|----------|----------------------|-------------------|
| `POST /query/upload/graph` | `scenario_name: str \| None = Query(default=None)` | Overrides `scenario.yaml` name; forces `-topology` suffix |
| `POST /query/upload/telemetry` | `scenario_name: str \| None = Query(default=None)` | Overrides `scenario.yaml` name; forces `-telemetry` suffix |
| `POST /query/upload/runbooks` | `scenario_name: str \| None = Query(default=None)` + legacy `scenario: str = "default"` | `scenario_name` takes priority over `scenario.yaml` over legacy `scenario` param |
| `POST /query/upload/tickets` | `scenario_name: str \| None = Query(default=None)` + legacy `scenario: str = "default"` | Same as runbooks |
| `POST /query/upload/prompts` | `scenario_name: str \| None = Query(default=None)` | Overrides `scenario.yaml` name |

**Critical naming coupling when `scenario_name` is used:** When the override is
provided, upload endpoints **ignore** the custom `cosmos.nosql.database` and
`cosmos.gremlin.graph` values from `scenario.yaml` and force hardcoded suffixes
(`-topology`, `-telemetry`). This guarantees naming consistency with the query-time
derivation in `config.py` (`graph_name.rsplit("-", 1)[0] + "-telemetry"`). Without
this enforcement, custom suffixes in `scenario.yaml` would create databases that
the query layer can't find.

### Tarball Extraction

`_extract_tar(content, tmppath)`:
- Opens `tarfile.open(fileobj=BytesIO(content), mode="r:gz")`
- Uses `filter="data"` (Python 3.12+ safe extraction)
- Searches for `scenario.yaml` at root then one subdirectory level deep
- Returns the directory containing `scenario.yaml`

### Two-Phase ARM + Data-Plane Pattern

**For Gremlin graph uploads:**
1. **ARM phase** (`_ensure_gremlin_graph`): `CosmosDBManagementClient.gremlin_resources.begin_create_update_gremlin_graph()` — creates graph with autoscale max 1000 RU/s, partition key `/partitionKey`. Derives account name from endpoint by splitting on `.`.
2. **Data plane**: `gremlin_python.driver.client.Client` over WSS with key auth — Gremlin `addV` and `addE` traversals

**For telemetry uploads:**
1. **ARM phase** (`_ensure_nosql_db_and_containers`): `CosmosDBManagementClient.sql_resources.begin_create_update_sql_database()` + `begin_create_update_sql_container()` per container. Catches `Conflict` errors (already exists).
2. **Data plane**: `CosmosClient(url, credential=get_credential())` — RBAC auth — `upsert_item()` calls

**For prompt uploads:**
1. **ARM phase**: Creates database `{scenario}-prompts`, container `prompts` with PK `/agent`
2. **Data plane**: `container.upsert_item()` with versioned prompt documents

**For runbook/ticket uploads:**
1. **Blob upload**: `BlobServiceClient` → `get_container_client(name)` → `upload_blob()`
2. **AI Search pipeline**: `search_indexer.create_search_index()` → creates data source → index (with vector field + HNSW) → skillset (chunk + embed) → indexer, then polls until complete

### Gremlin Retry Logic

`CosmosDBGremlinBackend._submit_query(query, max_retries=3)`:
- Retries on HTTP 429 (throttling) or 408 (timeout) with exponential backoff (`2^attempt` seconds)
- On `WSServerHandshakeError` (401): raises immediately with helpful error message
- On generic connection error: closes client, sets `self._client = None`, reconnects on next attempt
- All retries wrapped in explicit exception handling per attempt

### Per-Request Graph Routing

Every `/query/*` request can target a different graph via the `X-Graph` header:

```
Frontend → X-Graph: telco-noc-topology → graph-query-api reads header
  → ScenarioContext(graph_name="telco-noc-topology",
                    telemetry_database="telco-noc-telemetry")
  → get_backend_for_context(ctx) → cached CosmosDBGremlinBackend per graph
```

Telemetry database derivation: `graph_name.rsplit("-", 1)[0]` → strip last `-*` segment → append `-telemetry`. Falls back to `COSMOS_NOSQL_DATABASE` env var if graph name has no hyphens.

### Prompt Upload — GraphExplorer Composition

The GraphExplorer agent prompt is special — it's **composed from 3 files**:
- `graph_explorer/core_instructions.md`
- `graph_explorer/core_schema.md`
- `graph_explorer/language_gremlin.md`

Joined with `\n\n---\n\n` separator.

Other agent prompts map 1:1 via `PROMPT_AGENT_MAP`:
```python
PROMPT_AGENT_MAP = {
    "foundry_orchestrator_agent.md": "orchestrator",
    "orchestrator.md": "orchestrator",
    "foundry_telemetry_agent_v2.md": "telemetry",
    "telemetry_agent.md": "telemetry",
    "foundry_runbook_kb_agent.md": "runbook",
    "runbook_agent.md": "runbook",
    "foundry_historical_ticket_agent.md": "ticket",
    "ticket_agent.md": "ticket",
    "alert_storm.md": "default_alert",
    "default_alert.md": "default_alert",
}
```

**Note**: `graph_explorer` is NOT in `PROMPT_AGENT_MAP` — it’s handled separately
by composing from the `graph_explorer/` subdirectory in the upload logic.
```

### Agent Provisioning

Agents are provisioned via `POST /api/config/apply` which:
1. Receives `{graph, runbooks_index, tickets_index, prompt_scenario}` from frontend
2. Calls `GET http://127.0.0.1:8100/query/prompts?scenario={prefix}&include_content=true` (localhost loopback via `urllib.request`, timeout 30s) to fetch prompts
3. Falls back to minimal placeholder prompts if Cosmos has no prompts for that scenario:
   - `orchestrator: "You are an investigation orchestrator."`
   - `graph_explorer: "You are a graph explorer agent."`
   - `telemetry: "You are a telemetry analysis agent."`
   - `runbook: "You are a runbook knowledge base agent."`
   - `ticket: "You are a historical ticket search agent."`
4. Imports `AgentProvisioner` from `scripts/agent_provisioner.py` via `sys.path` manipulation
5. Calls `provisioner.provision_all()` with `force=True` (deletes existing agents first)
6. Stores result in memory (`_current_config` protected by `threading.Lock()`) + writes `agent_ids.json`
7. Streams SSE progress events back to frontend

### AgentProvisioner — What It Creates

Creates 5 agents in order:

| # | Agent | Tool Type | Tool Config |
|---|-------|-----------|-------------|
| 1 | GraphExplorerAgent | `OpenApiTool` | Spec filtered to `/query/graph` only, anonymous auth |
| 2 | TelemetryAgent | `OpenApiTool` | Spec filtered to `/query/telemetry` only, anonymous auth |
| 3 | RunbookKBAgent | `AzureAISearchTool` | `query_type=SEMANTIC`, `top_k=5` |
| 4 | HistoricalTicketAgent | `AzureAISearchTool` | Same pattern as RunbookKB |
| 5 | Orchestrator | `ConnectedAgentTool` (×4) | References all 4 sub-agents by ID |

**OpenAPI spec loading**: Reads from `graph-query-api/openapi/{cosmosdb|mock}.yaml`.
The spec contains a literal `{base_url}` placeholder in the `servers` section:
```yaml
servers:
  - url: "{base_url}"
```
Replaced at runtime via string replace with `GRAPH_QUERY_API_URI` (Container App public URL).

**Search connection ID format**:
```
/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{foundry}/projects/{project}/connections/aisearch-connection
```

**Progress callback**: `on_progress(step: str, detail: str)` — steps are: `"cleanup"`, `"graph_explorer"`, `"telemetry"`, `"runbook"`, `"ticket"`, `"orchestrator"`, `"save"`.

**`AlertRequest` validation**: `text: str`, `min_length=1`, `max_length=10_000`.

**Stub mode**: When `is_configured()` returns False, `alert.py` returns a simulated
investigation with 4 fake agent steps (TelemetryAgent, GraphExplorerAgent,
RunbookKBAgent, HistoricalTicketAgent) with 0.5s delays. The stub response tells
the user to provision agents.

**Default alert text** (hardcoded in `useInvestigation.ts`):
```
14:31:14.259 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down
```

### Investigation Flow

```
User pastes alert → POST /api/alert {text: "..."}
  → orchestrator.py checks is_configured() (agent_ids.json + env vars)
  → If not configured: returns stub SSE events (fake steps + stub message)
  → If configured:
      → Creates thread + run via azure-ai-agents SDK
      → SSEEventHandler bridges sync callbacks → async queue → SSE stream
      → Orchestrator delegates to sub-agents via ConnectedAgentTool:
          ├─ GraphExplorerAgent → OpenApiTool → /query/graph (X-Graph header)
          ├─ TelemetryAgent → OpenApiTool → /query/telemetry (X-Graph header)
          ├─ RunbookKBAgent → AzureAISearchTool → {scenario}-runbooks-index
          └─ HistoricalTicketAgent → AzureAISearchTool → {scenario}-tickets-index
      → SSE events streamed to frontend (step_start, step_complete, message)
```

**Orchestrator retry logic**:
- `MAX_RUN_ATTEMPTS = 2` (initial + 1 retry)
- On failure: posts a `[SYSTEM]` recovery message to the thread telling the orchestrator the previous attempt failed and to try simpler queries or skip failing data sources
- On no response text after completion: falls back to `agents_client.messages.list()` to extract assistant messages from the thread
- Per-event timeout: `EVENT_TIMEOUT = 120` seconds — if no SSE event received for 2 minutes, emits a stuck error and breaks

---

## SSE Event Protocols

### Investigation SSE (`POST /api/alert`)

**Library**: `@microsoft/fetch-event-source` (allows POST + named events)

| Event Name | Payload Shape | UI Effect |
|------------|---------------|-----------|
| `run_start` | `{run_id, alert, timestamp}` | Sets `runStarted = true` |
| `step_thinking` | `{agent: string, status: string}` | Shows thinking dots with agent name + status |
| `step_start` | `{step: number, agent: string}` | Sets thinking to `{agent, status: 'processing...'}` |
| `step_complete` | `{step, agent, duration?, query?, response?, error?: boolean}` | Clears thinking; appends to `steps[]`; increments step counter |
| `message` | `{text: string}` | Clears thinking; sets `finalMessage` (markdown diagnosis) |
| `run_complete` | `{steps: number, tokens: number, time: string}` | Clears thinking; sets `runMeta` |
| `error` | `{message: string}` | Clears thinking; sets `errorMessage` |

**Frontend state machine**:
```
idle → submitAlert() → running=true, clear all state
  → run_start → runStarted=true
  → step_thinking (0..n times per agent call)
  → step_start → step_complete (repeats per agent step)
  → message (final markdown diagnosis)
  → run_complete (sets runMeta {steps, time})
  → finally: running=false, runMeta updated from refs
```

Frontend auto-abort timeout: **5 minutes** of total SSE stream time.

### Upload SSE (`POST /query/upload/*`)

Uses raw `ReadableStream` parsing of `data:` lines (not named events).

| Payload Shape | Meaning |
|---------------|---------|
| `{step: string, detail: string, pct: number}` | Progress update (0-100%) |
| `{graph: string, ...}` or `{database: string, ...}` or `{index: string, ...}` | Completion result |
| `{error: string}` | Error (pct = -1 internally) |

Server-side event types: `progress`, `complete`, `error`.

### Agent Provisioning SSE (`POST /api/config/apply`)

Same raw `ReadableStream` pattern as uploads.

| Event | Payload | Meaning |
|-------|---------|---------|
| `progress` | `{step: string, detail: string}` | Step progress |
| `complete` | `{step: "done", detail: string, result: {...}}` | All 5 agents created |
| `error` | `{step: "error", detail: string}` | Provisioning failed |

### Log Stream SSE (`GET /api/logs`)

**Library**: Native `EventSource` (GET-only)

| Event Name | Payload Shape | Notes |
|------------|---------------|-------|
| `log` | `{ts: string, level: string, name: string, msg: string}` | `ts` format: `HH:MM:SS.mmm` |

Implementation: Custom `logging.Handler` installed on root logger → broadcasts to all connected subscriber queues. Filter: only `app.*`, `azure.*`, `uvicorn.*` loggers. Buffer: last 100 records replayed to new connections. Thread-safe via `_event_loop.call_soon_threadsafe()`.

---

## Key Components Detail

### `graph-query-api/config.py` — ScenarioContext & Shared Resources

**Request logging middleware** (in `main.py`): Logs every incoming request with `▶`/`◀` markers. For POST/PUT/PATCH, logs body (first 1000 bytes). Logs response status and elapsed time in ms. Warns on 4xx/5xx.

```python
# --- Backend selector ---
class GraphBackendType(str, Enum):
    COSMOSDB = "cosmosdb"
    MOCK = "mock"

GRAPH_BACKEND = GraphBackendType(os.getenv("GRAPH_BACKEND", "cosmosdb").lower())

# --- Shared credential (lazy-init, cached singleton) ---
_credential = None
def get_credential() -> DefaultAzureCredential:
    # WARNING: Do NOT use this in asyncio.to_thread() sync functions.
    # Create a fresh DefaultAzureCredential() inside the thread function instead.

# --- Per-request context (FastAPI dependency) ---
@dataclass
class ScenarioContext:
    graph_name: str              # e.g. "telco-noc-topology"
    gremlin_database: str        # "networkgraph" (shared across all scenarios)
    telemetry_database: str      # "telco-noc-telemetry" (derived from graph_name)
    backend_type: GraphBackendType

def get_scenario_context(
    x_graph: str | None = Header(default=None, alias="X-Graph")
) -> ScenarioContext:
    # Falls back to COSMOS_GREMLIN_GRAPH env var if no header
    # Derivation: "cloud-outage-topology" → rsplit("-", 1)[0] → "cloud-outage" → "-telemetry"
    # "topology" (no hyphens) → falls back to COSMOS_NOSQL_DATABASE env var

# --- Startup validation ---
BACKEND_REQUIRED_VARS = {
    GraphBackendType.COSMOSDB: ("COSMOS_GREMLIN_ENDPOINT", "COSMOS_GREMLIN_PRIMARY_KEY"),
    GraphBackendType.MOCK: (),
}
TELEMETRY_REQUIRED_VARS = ("COSMOS_NOSQL_ENDPOINT", "COSMOS_NOSQL_DATABASE")
```

### `graph-query-api/backends/` — Per-Graph Client Cache

```python
# --- Protocol (all backends must implement) ---
class GraphBackend(Protocol):
    async def execute_query(self, query: str, **kwargs) -> dict:
        """Returns {columns: [{name, type}], data: [dict]}"""
    async def get_topology(self, query=None, vertex_labels=None) -> dict:
        """Returns {nodes: [{id, label, properties}], edges: [{id, source, target, label, properties}]}"""
    def close(self) -> None: ...

# --- Cache ---
_backend_cache: dict[str, GraphBackend] = {}  # Protected by threading.Lock
# Cache key format: "{backend_type}:{graph_name}" (e.g., "cosmosdb:telco-noc-topology")
# Mock backend: shared singleton with key "__mock__"

def get_backend_for_context(ctx: ScenarioContext) -> GraphBackend:
    # Thread-safe cached lookup/create

def get_backend_for_graph(graph_name: str, backend_type: GraphBackendType) -> GraphBackend:
    # Direct cache lookup/create (used by upload endpoints)

async def close_all_backends():
    # Called during app lifespan shutdown — iterates and closes all cached backends
    # Uses inspect.isawaitable() to dynamically check if backend.close() returns
    # an awaitable and awaits it if so.
```

**graph-query-api has its own SSE log system** (separate from the API’s `logs.py`):
- Custom `_SSELogHandler` installed in `main.py`, filters only `graph-query-api.*` loggers
- Ring buffer: `deque(maxlen=100)`, subscriber queues: `maxsize=500`
- Exposed at `GET /api/logs` on port 8100 (but shadowed by nginx routing `/api/*` → :8000)

### `graph-query-api/backends/cosmosdb.py` — CosmosDBGremlinBackend

```python
class CosmosDBGremlinBackend:
    def __init__(self, graph_name: str | None = None):
        self._graph_name = graph_name or COSMOS_GREMLIN_GRAPH  # from env var
        self._client = None  # Lazy-init, protected by threading.Lock
        # Connection: wss://{COSMOS_GREMLIN_ENDPOINT}:443/
        # Username: /dbs/{COSMOS_GREMLIN_DATABASE}/colls/{self._graph_name}
        # Password: COSMOS_GREMLIN_PRIMARY_KEY
        # Serializer: GraphSONSerializersV2d0()

    async def execute_query(self, query):
        # Wraps _submit_query via asyncio.to_thread
        # Returns normalised {columns, data}

    async def get_topology(self, query=None, vertex_labels=None):
        # query param is reserved but NOT supported — raises ValueError if used
        # Runs vertex + edge Gremlin queries in PARALLEL via asyncio.gather
        # Optional vertex_labels filtering: adds hasLabel(...) to both V and E queries
        # Edge query: bothE().where(otherV().hasLabel(...))

    def _normalise_results(self, raw):  # NOTE: actually a module-level function, not a method
        # Handles 3 shapes:
        # 1. List of dicts → _flatten_valuemap (T.id→id, T.label→label, unwrap single-lists)
        # 2. List of scalars → wrap in {value: x}
        # 3. Fallback → stringify

    def _submit_query(self, query, max_retries=3):
        # Retries: 429 (throttle), 408 (timeout) → exponential backoff 2^attempt sec
        # WSServerHandshakeError (401) → immediate raise with helpful message
        # Connection errors → close client, set None, reconnect on next attempt
```

**KNOWN BUG — Edge topology query f-string**: In `get_topology()`, the filtered
edge query has an f-string continuation bug:
```python
e_query = (
    f"g.V().hasLabel({label_csv}).bothE()"         # f-string ✓ — interpolated
    ".where(otherV().hasLabel({label_csv}))"        # NOT f-string — {label_csv} is LITERAL
    ".project('id','label','source','target','properties')"
    ".by(id).by(label).by(outV().id()).by(inV().id()).by(valueMap())"
)
```
The `.where()` line sends the literal string `{label_csv}` to Gremlin. This causes
a Gremlin syntax error when `vertex_labels` filtering is used. Fix: add `f` prefix
to the second string segment.

**Telemetry query stripping**: `router_telemetry.py` strips Cosmos system properties
(`_rid`, `_self`, `_etag`, `_attachments`, `_ts`) from query results before returning
them to agents. This means agents never see internal Cosmos metadata.

**Telemetry client caching**: `router_telemetry.py` caches its own `CosmosClient`
with endpoint change detection — if `COSMOS_NOSQL_ENDPOINT` changes between calls,
it closes the old client and creates a new one. Protected by `threading.Lock()`.

### `graph-query-api/router_ingest.py` — Upload + Listing Endpoints

**IMPORTANT CODE ORGANIZATION:**
- Lines ~1-120: imports, helpers (`_extract_tar`, `_gremlin_client`, `_gremlin_submit`, `_read_csv`, `_ensure_gremlin_graph`)
- Lines ~120-600: **OLD commented-out monolithic upload code** (DEAD CODE — should be removed)
- Lines ~600-760: `GET /query/scenarios`, `DELETE /query/scenario/{name}`, `GET /query/indexes`
- Lines ~760-1329: **ACTIVE per-type upload endpoints** (`/upload/graph`, `/upload/telemetry`, `/upload/runbooks`, `/upload/tickets`, `/upload/prompts`)

**Two separate Gremlin retry implementations**:
- `backends/cosmosdb.py` `_submit_query()` — used by query/topology endpoints, handles `WSServerHandshakeError`, reconnects on generic errors
- `router_ingest.py` `_gremlin_submit()` — used by upload endpoints, simpler (no reconnect logic, just retries)

**Inconsistent tarball extraction**: Only `/upload/graph` and `/upload/telemetry`
use the shared `_extract_tar()` helper. The other 3 upload endpoints
(`/upload/runbooks`, `/upload/tickets`, `/upload/prompts`) each do their own
`tarfile.open()` + `extractall()` + `os.walk()` inline.

The `GET /query/scenarios` endpoint:
- Tries ARM listing first (`CosmosDBManagementClient` with fresh credential in `asyncio.to_thread`)
- Falls back to Gremlin key-auth count query on default graph
- Can be slow (~5-10s for ARM discovery)

The `GET /query/indexes` endpoint:
- Lists AI Search indexes via `SearchIndexClient`
- Groups by type: `"runbooks"` (name contains "runbook"), `"tickets"` (name contains "ticket"), `"other"`
- Returns `{indexes: [{name, type, document_count, fields}]}`

### `graph-query-api/router_prompts.py` — Prompts CRUD

Database: Cosmos NoSQL (separate from telemetry). Per-scenario database named `{scenario}-prompts`.
Container: `prompts` with partition key `/agent`.

**Container creation**: `_get_prompts_container(scenario)`:
1. Checks `_containers` cache (module-level `dict[str, object]`)
2. Derives account name from `COSMOS_NOSQL_ENDPOINT` (strips `https://`, splits on `.`)
3. ARM phase: `CosmosDBManagementClient` creates database `{scenario}-prompts` + container `prompts`
4. Data plane: `CosmosClient(url, credential=get_credential())` for actual operations
5. Caches the container client

**Document schema**:
```json
{
  "id": "{scenario}__{name}__v{version}",
  "agent": "orchestrator",
  "scenario": "telco-noc",
  "name": "foundry_orchestrator_agent",
  "version": 1,
  "content": "# Orchestrator System Prompt\n...",
  "description": "",
  "tags": [],
  "is_active": true,
  "deleted": false,
  "created_at": "2026-02-15T10:30:00Z",
  "created_by": "ui-upload"
}
```

**ASYNC VIOLATION WARNING**: `get_prompt`, `create_prompt`, `update_prompt`,
and `delete_prompt` make synchronous `container.read_item()`, `container.upsert_item()`,
and `container.query_items()` calls directly in `async def` handlers WITHOUT wrapping
in `asyncio.to_thread()`. This violates the Critical Pattern #1 rule. Only `list_prompts`
and `list_prompt_scenarios` correctly use `asyncio.to_thread()`. These sync calls
block the event loop for the duration of each Cosmos round-trip (~50-200ms each).

**Versioning**: On `POST /query/prompts`, queries existing versions for `(agent, scenario, name)` ordered by `version DESC`. Auto-increments. Deactivates all previous versions (`is_active=False`).

**Sorting**: Cosmos NoSQL requires a composite index for multi-field ORDER BY,
but the container is created without one. Sorting is done **Python-side** after
fetching: `sort(key=lambda x: (agent, scenario, -version))`.

**Listing**: Without `scenario` param → slow path iterating ALL `{scenario}-prompts` databases. With `scenario` → fast path querying single database.

`_list_prompt_databases()`: Lists all SQL databases via ARM, filters names ending with `-prompts`, strips suffix.

### `graph-query-api/router_scenarios.py` — Scenario Metadata CRUD

Stores scenario metadata in a dedicated Cosmos NoSQL database: `scenarios` / `scenarios`.
Each document tracks a complete scenario's name, display name, description, and resource
bindings. This is a **registry/catalog** — it does NOT store the actual data, only
references to graphs, indexes, and databases.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/query/scenarios/saved` | List all saved scenarios (ORDER BY `updated_at` DESC) |
| POST | `/query/scenarios/save` | Upsert scenario metadata after uploads complete |
| DELETE | `/query/scenarios/saved/{name}` | Delete metadata record only (underlying data preserved) |

**Container creation**: `_get_scenarios_container(ensure_created=True)`:
1. Same ARM two-phase pattern as `router_prompts._get_prompts_container()`
2. Database: `scenarios`, container: `scenarios`, PK: `/id`
3. Lazily cached in module-level `_scenarios_container` variable
4. Uses fresh `DefaultAzureCredential()` inside thread for ARM calls

**Name validation** (shared between endpoint and Pydantic validator):
- Regex: `^[a-z0-9](?!.*--)[a-z0-9-]{0,48}[a-z0-9]$`
- No consecutive hyphens (`--`) — Azure Blob container names forbid them
- Must not end with reserved suffixes: `-topology`, `-telemetry`, `-prompts`, `-runbooks`, `-tickets`
- Min 2 chars, max 50 chars
- Enforced both frontend (input validation) and backend (API + Pydantic `field_validator`)

**Document schema** (matches `SavedScenario` TypeScript interface):
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
    "graph": { "status": "complete", "timestamp": "...", "vertices": 42, "edges": 68 },
    "telemetry": { "status": "complete", "timestamp": "...", "containers": 2 },
    "runbooks": { "status": "complete", "timestamp": "...", "index": "cloud-outage-runbooks-index" },
    "tickets": { "status": "complete", "timestamp": "...", "index": "cloud-outage-tickets-index" },
    "prompts": { "status": "complete", "timestamp": "...", "prompt_count": 6 }
  }
}
```

**Save behavior**: On `POST /query/scenarios/save`, preserves `created_at` from existing
document if one exists (reads before writing). Auto-derives `display_name` from name
if not provided (`name.replace("-", " ").title()`). Resource bindings are deterministically
derived from the scenario name. Upsert is last-writer-wins (safe for low concurrency).

**Delete behavior**: Deletes only the metadata document. Underlying Azure resources
(graph data, search indexes, telemetry databases, blob containers) are left intact.
Future enhancement may add `?delete_data=true` parameter for full cleanup.

**Error handling**: `list_saved_scenarios` returns `{"scenarios": [], "error": "..."}` on
failure (non-fatal — app works without saved scenarios). Save and delete raise `HTTPException`
on validation or conflict errors.

### `api/app/orchestrator.py` — Agent Bridge

- `is_configured()`: checks `agent_ids.json` exists + `PROJECT_ENDPOINT` + `AI_FOUNDRY_PROJECT_NAME` set + orchestrator ID present in parsed JSON
- `_get_project_client()`: builds endpoint as `{PROJECT_ENDPOINT.rstrip('/')}/api/projects/{AI_FOUNDRY_PROJECT_NAME}`
- `load_agents_from_file()`: reads `agent_ids.json`, returns list of `{name, id, status}` dicts
- `run_orchestrator(alert_text)`: async generator yielding SSE events via `asyncio.Queue` bridge from sync `AgentEventHandler` running in a daemon thread

**Lazy Azure imports**: All `azure.*` packages are imported inside functions
(not at module level). This lets the app start even without them installed,
though it will fail at runtime when called.

**SSEEventHandler callback mapping**:
- `on_thread_run(run)`: detects `completed` (captures token usage from `run.usage.total_tokens`) and `failed` (captures error code + message). Defensively handles both object attributes (`getattr`) and dict access (`.get()`) to cover SDK version variations.
- `on_run_step(step)`: on `in_progress` emits `step_thinking`; on `completed`+`tool_calls` extracts `connected_agent` details (name, arguments, output) and emits `step_start` + `step_complete`; on `failed`+`tool_calls` logs full error detail and emits failed step
- `on_message_delta(delta)`: accumulates `response_text` from streaming deltas
- `on_error(data)`: emits `error` event

**Event ordering quirk**: Both `step_start` AND `step_complete` are emitted
back-to-back in the `completed` handler — NOT separated by time. The `step_thinking`
event (emitted on `in_progress`) is the real "in-progress" indicator.

**Tool call parsing**: For `connected_agent` type, extracts `agent_name` from `ca.name`
or looks up `ca.agent_id` in `agent_names`. Truncation: query at 500 chars, response at 2000 chars.
Also handles `azure_ai_search` type (sets `agent_name = "AzureAISearch"`).

**Thread-safe queue bridge**: `_put(event, data)` uses `asyncio.run_coroutine_threadsafe(queue.put(...), loop)`.

### `api/app/routers/config.py` — Agent Provisioning Endpoint

**sys.path manipulation**: Adds both `PROJECT_ROOT/scripts` and `PROJECT_ROOT/../scripts` to handle local dev vs container paths. Uses `sys.path.insert(0, ...)` — checks which exists first and adds only that one.

**Dual `load_dotenv`**: Both `main.py` and `orchestrator.py` call `load_dotenv()`
with different relative paths — both resolve to the same `azure_config.env`.

**Prompt resolution order** (in `POST /api/config/apply`):
1. `req.prompts` (explicit content dict, if provided)
2. Cosmos lookup via `urllib.request` to `http://127.0.0.1:8100/query/prompts?scenario={prompt_scenario}` (localhost loopback to graph-query-api)
3. Fallback defaults: `{"orchestrator": "You are an investigation orchestrator.", ...}`

**Search connection ID construction** (constant: `AI_SEARCH_CONNECTION_NAME = "aisearch-connection"`):
```python
search_conn_id = (
    f"/subscriptions/{sub_id}/resourceGroups/{rg}"
    f"/providers/Microsoft.CognitiveServices"
    f"/accounts/{foundry}/projects/{project_name}"
    f"/connections/aisearch-connection"
)
```

### `api/app/routers/logs.py` — Log Broadcasting

- Custom `_SSELogHandler(logging.Handler)` installed on root logger
- Filter: only loggers starting with `app`, `azure`, `uvicorn`
- `_broadcast()`: fan-out to all subscriber queues via `_event_loop.call_soon_threadsafe()`
- `_log_buffer: deque(maxlen=100)`: last 100 records replayed to new SSE connections
- Multiple concurrent clients supported — each gets own `asyncio.Queue(maxsize=500)`

### `graph-query-api/search_indexer.py` — AI Search Pipeline

`create_search_index(index_name, container_name, on_progress)`:

Creates a 4-component indexer pipeline:
1. **Data source**: `SearchIndexerDataSourceConnection` → blob container with managed identity
2. **Index**: `SearchIndex` with fields: `parent_id` (filterable), `chunk_id` (key), `chunk` (searchable), `title` (searchable, filterable), `vector` (float32, HNSW, dimensions from `EMBEDDING_DIMENSIONS`)
3. **Skillset**: `SplitSkill` (pages, 2000 chars, 500 overlap) → `AzureOpenAIEmbeddingSkill`
4. **Indexer**: Polls until status is `success` or `error` (5s intervals, max 60 iterations = 5 min)

Config from env vars: `AI_SEARCH_NAME`, `STORAGE_ACCOUNT_NAME`, `AI_FOUNDRY_NAME`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`.

**Storage connection**: Uses managed-identity `ResourceId` format (not key-based):
```
ResourceId=/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Storage/storageAccounts/{account}/;
```

**OpenAI endpoint**: Derived from `AI_FOUNDRY_NAME`: `https://{foundry_name}.openai.azure.com`

---

## Frontend Architecture

### Provider Tree & Layout

```
<React.StrictMode>
  <ScenarioProvider>                    ← Global context (scenario + provisioning state)
    <App>                               ← useInvestigation() hook
      ├── <Header>                      ← Fixed 48px top bar
      │   ├── <ScenarioChip>            ← Flyout dropdown: scenario switching + "+ New Scenario"
      │   ├── <HealthDot label="API">   ← Polls /health every 15s
      │   ├── Dynamic agent status      ← "5 Agents ✓" / "Provisioning..." / "Not configured"
      │   └── <SettingsModal>           ← useScenarios(), useScenarioContext()
      ├── <ProvisioningBanner>          ← Non-blocking 28px banner during agent provisioning
      ├── <MetricsBar>                  ← Vertically resizable panel (default 30%)
      │   ├── <GraphTopologyViewer>     ← useTopology(), owns overlay state
      │   │   ├── <GraphToolbar>
      │   │   ├── <GraphCanvas>         ← ForceGraph2D wrapper (forwardRef)
      │   │   ├── <GraphTooltip>        ← Hover tooltip (framer-motion)
      │   │   └── <GraphContextMenu>    ← Right-click menu
      │   └── <LogStream url="/api/logs">   ← EventSource SSE
      ├── <InvestigationPanel>
      │   ├── <AlertInput>              ← Textarea + submit button
      │   ├── <AgentTimeline>
      │   │   ├── <StepCard> (×n)
      │   │   └── <ThinkingDots>
      │   └── <ErrorBanner>
      ├── <DiagnosisPanel>              ← ReactMarkdown rendering
      └── <AddScenarioModal>            ← Opened from ScenarioChip or SettingsModal
```

Layout uses `react-resizable-panels` with vertical orientation: MetricsBar (30%) | InvestigationPanel + DiagnosisPanel (70% side-by-side).

### ScenarioContext (React Context)

```typescript
// Discriminated union for provisioning status tracking
type ProvisioningStatus =
  | { state: 'idle' }
  | { state: 'provisioning'; step: string; scenarioName: string }
  | { state: 'done'; scenarioName: string }
  | { state: 'error'; error: string; scenarioName: string };

interface ScenarioState {
  activeScenario: string | null;    // Saved scenario name, or null for custom/manual mode
  activeGraph: string;              // e.g. "telco-noc-topology" (default: "topology")
  activeRunbooksIndex: string;      // default: "runbooks-index"
  activeTicketsIndex: string;       // default: "tickets-index"
  activePromptSet: string;          // Prompt scenario name (default: "")
  provisioningStatus: ProvisioningStatus; // Agent provisioning state
  setActiveScenario(name: string | null): void; // Auto-derives all bindings when non-null
  setActiveGraph(g: string): void;
  setActiveRunbooksIndex(i: string): void;
  setActiveTicketsIndex(i: string): void;
  setActivePromptSet(name: string): void;
  setProvisioningStatus(status: ProvisioningStatus): void;
  getQueryHeaders(): Record<string, string>;  // { "X-Graph": activeGraph }
}
```

**Auto-derivation logic** — when `setActiveScenario(name)` is called with non-null:
- `activeGraph = "{name}-topology"`
- `activeRunbooksIndex = "{name}-runbooks-index"`
- `activeTicketsIndex = "{name}-tickets-index"`
- `activePromptSet = "{name}"`
- When called with `null` (custom mode): existing individual bindings are left as-is

**localStorage persistence**: `activeScenario` is persisted to and restored from
`localStorage` on mount. On page refresh, all bindings are re-derived from the
persisted scenario name. This does NOT re-trigger agent provisioning — agents are
long-lived in AI Foundry. It only restores frontend state so `X-Graph` headers
and UI indicators are correct.

`getQueryHeaders()` is memoized on `activeGraph`. It's consumed by `useInvestigation` and `useTopology`.

**Critical**: Only `activeGraph` generates an HTTP header (`X-Graph`). `activeRunbooksIndex` and `activeTicketsIndex` are NOT sent as headers — they're only passed in the `POST /api/config/apply` body.

**ProvisioningStatus** is defined and exported from `ScenarioContext.tsx` (co-located
with `ScenarioState` to avoid circular dependencies). It is a discriminated union type
for better TypeScript narrowing than a flat interface.

### TypeScript Types (`types/index.ts`)

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
  resources: {
    graph: string;                // "cloud-outage-topology"
    telemetry_database: string;   // "cloud-outage-telemetry"
    runbooks_index: string;       // "cloud-outage-runbooks-index"
    tickets_index: string;        // "cloud-outage-tickets-index"
    prompts_database: string;     // "cloud-outage-prompts"
  };
  upload_status: Record<string, {
    status: string;
    timestamp: string;
    [key: string]: unknown;       // vertices, edges, containers, etc.
  }>;
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

### Hooks

| Hook | Returns | Key Behaviors |
|------|---------|---------------|
| `useInvestigation()` | `{alert, setAlert, steps, thinking, finalMessage, errorMessage, running, runStarted, runMeta, submitAlert}` | Aborts prior SSE stream; 5min auto-abort timeout; uses refs for step counter (closure capture issue); injects `X-Graph` header |
| `useTopology()` | `{data, loading, error, refetch}` | Auto-refetches when `getQueryHeaders` changes (activeGraph change triggers `useEffect`); aborts prior in-flight request |
| `useScenarios()` | `{scenarios, indexes, savedScenarios, loading, error, fetchScenarios, fetchIndexes, fetchSavedScenarios, saveScenario, deleteSavedScenario, selectScenario}` | `fetchScenarios()` → GET `/query/scenarios`; `fetchIndexes()` → GET `/query/indexes` (failure non-fatal); `fetchSavedScenarios()` → GET `/query/scenarios/saved`; `selectScenario(name)` → auto-provisions agents via `consumeSSE` + updates `provisioningStatus` |

**`selectScenario(name)` flow** (in `useScenarios`):
1. Calls `setActiveScenario(name)` → auto-derives all bindings
2. Sets `provisioningStatus` to `{ state: 'provisioning', step: 'Starting...', scenarioName: name }`
3. POSTs to `/api/config/apply` with `{graph, runbooks_index, tickets_index, prompt_scenario}`
4. Consumes SSE stream via shared `consumeSSE()` utility from `utils/sseStream.ts`
5. Updates `provisioningStatus.step` on each progress event
6. On complete: sets `provisioningStatus` to `{ state: 'done', scenarioName: name }`
7. On error: sets `provisioningStatus` to `{ state: 'error', error: msg, scenarioName: name }`
8. After 3 seconds of 'done', auto-resets to `{ state: 'idle' }`

**Note:** Uses native `fetch()` + `ReadableStream` via `consumeSSE()` — NOT `@microsoft/fetch-event-source`. This is deviation D-1 from the SCENARIOHANDLING plan. Native fetch works correctly with POST + SSE and aligns with the shared utility pattern.

### All Frontend API Calls

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
| `/api/config/apply` | POST | `Content-Type: application/json` | "Provision Agents" button or `selectScenario()` auto-provision | `SettingsModal` / `useScenarios` |
| `/health` | GET | — | Every 15s polling | `HealthDot` |
| `/api/logs` | GET (EventSource) | — | On mount | `LogStream` |

**Note on AddScenarioModal uploads:** When triggered from AddScenarioModal, each upload
appends `?scenario_name=X` to the URL to override the tarball's `scenario.yaml` name.
Uses the shared `uploadWithSSE()` utility from `utils/sseStream.ts`.

### SettingsModal — 3 Tabs

**Scenarios tab (new — first tab):**
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
- Each is self-contained: drag-drop → upload → SSE progress bar → done/error state machine
- For ad-hoc individual uploads outside the scenario workflow

**Modal behavior:** Closes on Escape keypress and backdrop click (except during active
upload/provisioning). Uses `aria-modal="true"` and `role="dialog"` attributes.

### Graph Viewer Architecture

`GraphTopologyViewer` owns all overlay state and delegates rendering:

| Component | Role |
|-----------|------|
| `GraphCanvas` | `forwardRef` wrapper around `react-force-graph-2d`. Custom canvas rendering for nodes (colored circles + labels) and edges (mid-point labels). Exposes `zoomToFit()` via `useImperativeHandle`. |
| `GraphToolbar` | Label filter chips, node search input, node/edge counts, zoom-to-fit + refresh buttons |
| `GraphTooltip` | Fixed-position tooltip on hover. Uses `framer-motion`. Handles `source`/`target` as both string (before hydration) and object (after). |
| `GraphContextMenu` | Right-click menu: change display field (pick any property as label), change color (12-color palette). Persisted to `localStorage` keys `graph-display-fields` and `graph-colors`. |
| `graphConstants.ts` | `NODE_COLORS` and `NODE_SIZES` maps keyed by vertex label |

### Frontend Patterns & Gotchas

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

8. **ScenarioContext has localStorage persistence** for `activeScenario`: scenario selection survives browser refresh. All bindings are re-derived from the persisted scenario name on mount. Other individual bindings (`activeGraph`, etc.) are NOT independently persisted — they're derived.

9. **UploadBox `onComplete` gap** — After uploading prompts, the Prompt Set dropdown is NOT auto-refreshed. User must close/reopen the modal. Graph upload triggers `fetchScenarios()`, Runbooks/Tickets trigger `fetchIndexes()`, but Prompts and Telemetry trigger nothing.

10. **UploadBox completion detection is heuristic**: `if ('scenario' in d || 'index' in d || 'database' in d || 'graph' in d)`. Fragile if backend response structure changes.

11. **Vite dev proxy has 5 entries**, not 3: `/api/alert` → :8000 (SSE configured), `/api/logs` → :8000 (SSE configured), `/api` → :8000 (plain), `/health` → :8000, `/query` → :8100 (SSE configured). The SSE-configured entries add `cache-control: no-cache` and `x-accel-buffering: no` headers — without these, SSE streams are buffered during local dev.

12. **`useInvestigation` stale closure bug** — `getQueryHeaders` is NOT in the `submitAlert` `useCallback` dependency array. If user switches `activeGraph` without changing alert text, the OLD `X-Graph` header is sent.

13. **Shared SSE utility pattern** (`utils/sseStream.ts`): Two exports:
    - `consumeSSE(response, handlers, signal?)` — Low-level: takes a `Response`, reads `ReadableStream`, parses `data:` lines, dispatches to `onProgress`/`onComplete`/`onError` handlers
    - `uploadWithSSE(url, formData, handlers, signal?)` — High-level: wraps `fetch` + `consumeSSE` for form upload endpoints
    - Completion detection uses heuristic field-checking (`scenario`, `index`, `graph`, `prompts_stored` keys in parsed JSON) because backend SSE streams use `data:` lines only, not `event:` type markers (deviation D-5)

14. **AddScenarioModal auto-slot detection**: `detectSlot(filename)` parses the last hyphen-separated segment before `.tar.gz` to match file to upload slot. E.g., `cloud-outage-graph.tar.gz` → slot `graph`, scenarioName `cloud-outage`. Auto-fills scenario name input if empty. Multi-file drop assigns all matching files in one gesture.

15. **ProvisioningBanner lifecycle**: Appears during provisioning, shows current step from SSE stream, auto-dismisses 3s after completion with green flash. On error, banner turns red and stays until manually dismissed. Workspace remains interactive during provisioning — only "Submit Alert" is disabled.

16. **ScenarioChip flyout dropdown**: Shows saved scenarios + "(Custom)" option. Selecting triggers `selectScenario()` which auto-provisions. Small spinner inside chip during provisioning. "+ New Scenario" link at bottom opens AddScenarioModal.

---

## Data Schema & Generation

### Scenario Data Pack Structure

```
scenarios/{scenario-name}/
├── scenario.yaml                   # Scenario manifest (see schema below)
├── graph_schema.yaml               # Gremlin ingestion manifest
├── scripts/
│   ├── generate_all.sh             # Orchestrates data generation
│   ├── generate_topology.py        # Entity CSV generation
│   ├── generate_routing.py         # MPLS/BGP data
│   ├── generate_telemetry.py       # Time-series CSV generation
│   └── generate_tickets.py         # Incident ticket generation
└── data/
    ├── entities/                   # Graph vertex/edge CSVs (Dim*.csv, Fact*.csv)
    ├── telemetry/                  # Time-series CSVs (AlertStream.csv, LinkTelemetry.csv)
    ├── knowledge/
    │   ├── runbooks/               # Markdown runbooks → AI Search
    │   └── tickets/                # Plain text tickets → AI Search
    └── prompts/                    # Agent prompt fragments
        ├── foundry_orchestrator_agent.md
        ├── foundry_telemetry_agent_v2.md
        ├── foundry_runbook_kb_agent.md
        ├── foundry_historical_ticket_agent.md
        ├── alert_storm.md          # Default demo alert text
        └── graph_explorer/         # Composed into single prompt
            ├── core_instructions.md
            ├── core_schema.md
            ├── language_gremlin.md
            └── language_mock.md
```

### `scenario.yaml` Schema

```yaml
name: telco-noc                     # Used to derive graph/database names
display_name: "Telecom NOC"
description: "..."
version: "1.0"
domain: telecommunications

paths:
  entities: data/entities
  graph_schema: graph_schema.yaml
  telemetry: data/telemetry
  runbooks: data/knowledge/runbooks
  tickets: data/knowledge/tickets
  prompts: data/prompts
  default_alert: data/prompts/alert_storm.md

cosmos:
  gremlin:
    database: networkgraph           # Shared (not scenario-prefixed)
    graph: topology                  # Suffixed: "{name}-topology"
  nosql:
    database: telemetry              # Suffixed: "{name}-telemetry"
    containers:
      - name: AlertStream
        partition_key: /alert_id
        csv_file: AlertStream.csv
        id_field: alert_id
        numeric_fields: [severity]
      - name: LinkTelemetry
        partition_key: /link_id
        csv_file: LinkTelemetry.csv
        id_field: telemetry_id
        numeric_fields: [utilization_pct, latency_ms, packet_loss_pct, ...]

search_indexes:
  - name: runbooks-index             # Suffixed: "{name}-runbooks-index"
    container: runbooks
    source: data/knowledge/runbooks
  - name: tickets-index
    container: tickets
    source: data/knowledge/tickets

graph_styles:
  node_types:
    CoreRouter: {color: "#E74C3C", size: 12, icon: router}
    AggSwitch: {color: "#3498DB", size: 10, icon: switch}
    # ...

telemetry_baselines:
  link_telemetry:
    - metric: utilization_pct
      normal: {min: 10, max: 55}
      degraded: {min: 56, max: 80}
      down: {min: 81, max: 100}
  alert_stream:
    - metric: severity
      normal: {value: 1}
      anomalous: {min: 3, max: 5}
```

### `graph_schema.yaml` Format

Declarative Gremlin ingestion manifest — fully generic, no code changes for new datasets.

```yaml
data_dir: data/entities

vertices:
  - label: CoreRouter
    csv_file: DimCoreRouter.csv
    id_column: router_id
    partition_key: CoreRouter       # Static partition key value
    properties:
      - router_id
      - router_name
      - city
      - status

edges:
  - label: connects_to
    csv_file: DimTransportLink.csv
    source:
      label: CoreRouter
      property: router_id
      column: source_router_id      # CSV column for lookup
    target:
      label: CoreRouter
      property: router_id
      column: target_router_id
    properties:
      - column: link_id             # CSV column value
      - value: active               # Static literal
    filter:                          # Optional row filter
      column: link_type
      value: core
      negate: false                   # Optional (default false). If true, includes rows
                                      # where column != value (invert filter).
```

**Telemetry upload ID fallback**: When neither `id_field` is configured in
`scenario.yaml` nor an `id` column exists in the CSV, the upload generates
document IDs from the first two CSV columns: `f"{row[col0]}-{row[col1]}"`.

**Graph explorer prompt recursive fallback**: Upload first checks
`prompts_dir/graph_explorer/`, then falls back to `tmppath.rglob("graph_explorer")`
recursive search if the subdirectory isn't at the expected location.

### Tarball Generation (`data/generate_all.sh`)

Creates **5 separate tarballs per scenario** (not one monolithic archive):

| Tarball | Contents |
|---------|----------|
| `{scenario}-graph.tar.gz` | `scenario.yaml` + `graph_schema.yaml` + `data/entities/` |
| `{scenario}-telemetry.tar.gz` | `scenario.yaml` + `data/telemetry/` |
| `{scenario}-runbooks.tar.gz` | `scenario.yaml` + `data/knowledge/runbooks/` |
| `{scenario}-tickets.tar.gz` | `scenario.yaml` + `data/knowledge/tickets/` |
| `{scenario}-prompts.tar.gz` | `scenario.yaml` + `data/prompts/` (includes `graph_explorer/` subdir) |

Every tarball includes `scenario.yaml` so the upload handler can resolve the scenario name independently.

Workflow: `./data/generate_all.sh [scenario-name]` — iterates scenario dirs, runs each scenario's `scripts/generate_all.sh`, then creates tarballs.

---

## Infrastructure (Bicep)

### `infra/main.bicep` — Subscription-Scoped

**Scope**: `subscription` (creates resource group named `rg-{environmentName}`)

**Key Parameters**:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `environmentName` | (required) | Prefix for all resources |
| `location` | (required) | Azure region |
| `principalId` | — | User principal for role assignments |
| `gptCapacity` | 300 | In 1K TPM units |
| `graphBackend` | `"cosmosdb"` | `@allowed(['cosmosdb'])` — only `cosmosdb` at Bicep level; `mock` is a runtime-only env var override, never a Bicep parameter |
| `devIpAddress` | — | For local Cosmos firewall rules |

**Modules deployed** (9 total):

| Module | Purpose | Conditional? |
|--------|---------|--------------|
| `vnet` | VNet with infrastructure + private endpoint subnets | No |
| `search` | AI Search service | No |
| `storage` | Storage account (blob containers) | No |
| `cosmosGremlin` | Cosmos DB Gremlin account | If `graphBackend == 'cosmosdb'` |
| `aiFoundry` | AI Foundry hub + project | No |
| `containerAppsEnv` | Container Apps Environment (VNet-integrated) | No |
| `app` | Unified container app (port 80, 1-3 replicas, 1 CPU / 2Gi) | No |
| `roles` | All RBAC role assignments | No |
| `cosmosPrivateEndpoints` | Private endpoints for both Cosmos accounts | If `graphBackend == 'cosmosdb'` |

**CRITICAL**: Cosmos DB uses **TWO separate accounts** — one for Gremlin (graph data), one for NoSQL (telemetry + prompts). The NoSQL account is named `{gremlin-account}-nosql`.

**Env vars passed to Container App** (from Bicep):
```
PROJECT_ENDPOINT, AI_FOUNDRY_PROJECT_NAME, MODEL_DEPLOYMENT_NAME=gpt-4.1,
CORS_ORIGINS=*, AGENT_IDS_PATH=/app/scripts/agent_ids.json, GRAPH_BACKEND,
COSMOS_GREMLIN_ENDPOINT, COSMOS_GREMLIN_DATABASE=networkgraph,
COSMOS_GREMLIN_GRAPH=topology, COSMOS_GREMLIN_PRIMARY_KEY (secret ref),
COSMOS_NOSQL_ENDPOINT, COSMOS_NOSQL_DATABASE,
AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP,
AI_SEARCH_NAME, STORAGE_ACCOUNT_NAME, AI_FOUNDRY_NAME,
EMBEDDING_MODEL=text-embedding-3-small, EMBEDDING_DIMENSIONS=1536
```

**Bicep outputs** (consumed by `postprovision.sh`):
`AZURE_RESOURCE_GROUP`, `APP_URI`, `APP_PRINCIPAL_ID`, `GRAPH_QUERY_API_URI` (= `APP_URI`), `COSMOS_GREMLIN_ENDPOINT`, `COSMOS_NOSQL_ENDPOINT`, etc.

### Resource Naming Convention

Uses deterministic hash token: `toLower(uniqueString(subscription().id, environmentName, location))` — consistent across deployments, globally unique.

### Bicep Patterns

**`readEnvironmentVariable()` for config**: Bicep parameter files can read environment variables, avoiding hardcoded values:
```bicepparam
param cosmosGremlinDatabase = readEnvironmentVariable('COSMOS_GREMLIN_DATABASE', 'networkgraph')
```
Combined with `preprovision.sh` syncing values from `azure_config.env` to `azd env`, this creates a single-source-of-truth config pattern.

**Conditional module deployment**: Use boolean parameters to skip expensive modules during iterative development:
```bicep
param deployCosmosGremlin bool

module cosmos 'modules/cosmos.bicep' = if (deployCosmosGremlin) {
  name: 'cosmos'
  scope: rg
  params: { ... }
}

// Downstream modules that depend on cosmos output:
module privateEndpoints 'modules/private-endpoints.bicep' = if (deployCosmosGremlin) {
  name: 'privateEndpoints'
  scope: rg
  params: {
    cosmosAccountId: deployCosmosGremlin ? cosmos.outputs.accountId : ''
  }
}
```

---

## Dockerfile & Container Build

**Multi-stage build (2 stages):**

### Stage 1: Frontend Build
```dockerfile
FROM node:20-alpine AS frontend-build
# npm ci && npm run build → React artifacts in /build/dist
```

### Stage 2: Python + nginx
```dockerfile
FROM python:3.11-slim
# Installs: nginx, supervisor, uv (from ghcr.io/astral-sh/uv:latest)

# IMPORTANT: Both pyproject.toml AND uv.lock files are copied.
# `uv sync --frozen` requires uv.lock to exist.
# If uv.lock is missing, the build fails.

# graph-query-api at /app/graph-query-api
#   uv sync --frozen --no-dev --no-install-project
#   Copies: *.py, backends/, openapi/

# api at /app/api
#   uv sync --frozen --no-dev --no-install-project
#   Copies: app/

# Scripts at /app/scripts
#   Copies: scenario_loader.py, agent_provisioner.py

# Data at /app/data/scenarios (YAML only — .md prompts excluded by .dockerignore)

# Frontend static → /usr/share/nginx/html
# ENV AGENT_IDS_PATH=/app/scripts/agent_ids.json
# EXPOSE 80
# CMD: supervisord
```

**Path structure in container**:
```
/app/
├── api/                    # API service
│   ├── app/                # FastAPI app package
│   └── .venv/              # uv-managed virtualenv
├── graph-query-api/        # Query service
│   ├── backends/
│   ├── openapi/
│   └── .venv/
├── scripts/                # Shared scripts
│   ├── agent_provisioner.py
│   ├── scenario_loader.py
│   └── agent_ids.json      # Written at runtime by provisioning
└── data/scenarios/          # YAML manifests only
```

---

## RBAC Roles (Container App Managed Identity)

| Role | Scope | Purpose |
|------|-------|---------|
| Cognitive Services OpenAI User | Foundry | Invoke GPT models |
| Cognitive Services Contributor | Foundry | Manage agents |
| Azure AI Developer | Resource group | Agent invocation |
| Cognitive Services User | Foundry | Broad data-plane |
| Cosmos DB Built-in Data Contributor | NoSQL account | Query/upsert telemetry + prompts (data plane) |
| DocumentDB Account Contributor | Gremlin account | Create graphs via ARM (management plane) |
| DocumentDB Account Contributor | NoSQL account | Create databases/containers via ARM |
| Storage Blob Data Contributor | Storage account | Upload runbooks/tickets to blob |
| Search Service Contributor | AI Search | Create indexes/indexers |
| Search Index Data Contributor | AI Search | Read/write index data |

All defined in `infra/modules/roles.bicep`.

**Key distinction**: Cosmos DB has **separate RBAC systems** for management plane (ARM roles like `DocumentDB Account Contributor`) vs data plane (`Cosmos DB Built-in Data Contributor` — GUID `00000000-0000-0000-0000-000000000002`). The data contributor role does NOT include database/container creation — that's why upload endpoints use the two-phase ARM + data-plane pattern.

---

## Deployment

### `deploy.sh` — 5 Steps (no data loading, no agent provisioning)

| Step | What |
|------|------|
| 0 | Prerequisites check (Python, uv, Node, az, azd); auto-installs uv and node 20 |
| 1 | Azure environment selection (creates or selects `azd` environment, sets subscription) |
| 2 | Configure azure_config.env (writes template with placeholders) |
| 3 | `azd up` (runs preprovision → Bicep infra → container deploy → postprovision) |
| 6 | Health check (`curl -sf {APP_URI}/health` with retries) |
| 7 | Local dev servers (optional) |

Steps 4, 5, old-7 (search indexes, Cosmos data, agent provisioning) were removed.
All data + agent operations happen through the UI.

**Flags**: `--skip-infra`, `--skip-local`, `--env NAME`, `--location LOC`, `--yes`

**Dead flags** (parse but do nothing, steps removed): `--skip-index`, `--skip-data`, `--skip-agents`.

**Default location**: `swedencentral`.

**Health check**: 5 retries, 15s between attempts.

**BUG — Step 7 (local services)**: The automated start only launches API (:8000) and
frontend (:5173) but does NOT start graph-query-api (:8100). All `/query/*` requests
fail in automated local mode. The `--skip-local` manual instructions correctly
mention all 3 services.

### azd Lifecycle Hooks

**`hooks/preprovision.sh`**:
- Syncs selected vars from `azure_config.env` → `azd env` so Bicep's `readEnvironmentVariable()` can access them

**`hooks/postprovision.sh`**:
- Does NOT upload any blob data (removed in V8)
- Writes `azure_config.env` with Bicep outputs (subscription, RG, endpoints)
- **Fetches Cosmos Gremlin primary key** via `az cosmosdb keys list`
- **Derives Gremlin endpoint** from account name: `{account}.gremlin.cosmos.azure.com`
- **Queries separate NoSQL account** (`{account}-nosql`) for NoSQL endpoint
- Contains a dead `upload_with_retry` function (6 attempts, 30s wait) — defined but never called
- `DEFAULT_SCENARIO` and `LOADED_SCENARIOS` vars synced in preprovision.sh are vestigial — not defined in azure_config.env template

**Config bidirectional flow**:
```
azure_config.env → preprovision → azd env → Bicep params
                                                    ↓
azure_config.env ← postprovision ← Bicep outputs
```

### Post-Deployment Workflow

**Option A — Scenario-based (recommended):**
1. `./data/generate_all.sh [scenario]` → creates 5 per-type tarballs
2. Open app → click "+New Scenario" in Header chip or ⚙ Settings → Scenarios tab
3. Name the scenario → drag-drop all 5 tarballs (auto-detected by filename) → Save
4. Scenario auto-provisions agents and loads topology — ready to investigate

**Option B — Manual/Custom (ad-hoc uploads):**
1. `./data/generate_all.sh [scenario]` → creates 5 per-type tarballs
2. Open app → ⚙ Settings → Upload tab → upload each tarball (graph first recommended)
3. Data Sources tab → select graph, indexes, prompt set
4. Click "Load Topology" → verifies graph data loads in viewer
5. Click "Provision Agents" → creates 5 agents with selected prompts and data bindings

### Code-Only Redeployment

For code changes without infra changes: `azd deploy app` (rebuilds container, ~60-90s).
Uses `remoteBuild: true` in `azure.yaml` — Docker images built in ACR, not locally.
This avoids cross-platform issues (e.g., building on ARM Mac for Linux amd64):

```yaml
# azure.yaml
services:
  app:
    host: containerapp
    docker:
      path: ./Dockerfile
      remoteBuild: true
```

| Change Type | Command | Time |
|-------------|---------|------|
| Python code, OpenAPI specs, static files | `azd deploy app` | ~60-90s |
| Bicep infrastructure (new resources, env vars, RBAC) | `azd up` | ~5-10min |
| New env var in container | `azd up` (env vars are in Bicep) | ~5-10min |
| Frontend-only / Dockerfile changes | `azd deploy app` | ~60-90s |

**After code-only deploy:** If you changed agent provisioning logic or OpenAPI specs,
re-provision agents through the UI (⚙ → Provision Agents) — old agents in Foundry
still have old tool specs baked in.

---

## Error Resilience

### Layer 1: Errors as 200 + Error Payload (OpenApiTool Compatibility)

Graph and telemetry endpoints catch ALL exceptions and return HTTP 200 with an `error` field. This is **required** because Foundry's `OpenApiTool` treats HTTP 4xx/5xx as fatal tool errors — the sub-agent run fails, the `ConnectedAgentTool` returns failure to the orchestrator, and the LLM never sees the error. By returning 200 + error text, the agent reads the error and self-corrects (e.g., fixes Gremlin syntax, adjusts container name).

```python
except Exception as e:
    return GraphQueryResponse(error=f"Graph query error: {e}. Read the error, fix the query, and retry.")
```

### Layer 2: Orchestrator Run Retry

`MAX_RUN_ATTEMPTS = 2`. On failure or no-response:
- Posts `[SYSTEM]` recovery message to thread with error details
- Tells orchestrator to retry with simpler queries or skip failing data sources
- Falls back to `messages.list()` to extract response text if streaming missed it

### Layer 3: Per-Event Timeout

`EVENT_TIMEOUT = 120` seconds. If no SSE event received for 2 minutes, emits stuck error and breaks. Frontend has separate 5-minute total timeout.

### Layer 4: Graceful Degradation (Prompt Rule)

Orchestrator prompt instructs: "If a sub-agent fails, continue with remaining agents and produce a partial report."

---

## Critical Patterns & Lessons

### 1. async/await + Azure SDK — `asyncio.to_thread()` Requirement

**All Azure SDK calls MUST be in `asyncio.to_thread()`**. The `DefaultAzureCredential`, `gremlinpython` WebSocket client, `CosmosClient`, and ARM management clients all internally use event loops that conflict with FastAPI's async loop. Every upload endpoint wraps its entire SDK chain in a sync function called via `to_thread`.

### 2. Credential Isolation in Threads

**IMPORTANT:** The ARM calls in `router_prompts.py` and `router_ingest.py` create
a **fresh `DefaultAzureCredential()`** inside the thread function — do NOT reuse the shared `get_credential()` from `config.py`, as it may have been initialized in the async context. The shared credential is only safe for use in the main thread or when called consistently from the same context.

### 3. Cosmos DB — Two-Phase Pattern

The built-in data contributor role (`00000000-0000-0000-0000-000000000002`) does NOT include database/container creation permissions. Upload endpoints use:
1. **ARM** (`azure-mgmt-cosmosdb`) for database/container/graph creation — requires `DocumentDB Account Contributor` role
2. **Data plane** (`CosmosClient` or Gremlin) for data operations — requires `Cosmos DB Built-in Data Contributor` role (or key auth for Gremlin)

### 4. Cosmos Gremlin — Key Auth Only

The Gremlin wire protocol (WSS) does **not support Azure AD / Managed Identity**. Must use primary key auth. This is a Cosmos DB limitation, not a code choice. NoSQL/SQL API supports both.

### 5. ConnectedAgentTool — Server-Side Execution

Sub-agents using `ConnectedAgentTool` run **server-side inside Foundry**. They cannot execute client-side callbacks. This means `FunctionTool` does NOT work — use `OpenApiTool` (HTTP endpoint) instead.

| Tool Type | Execution | Works with ConnectedAgentTool? |
|-----------|-----------|-------------------------------|
| `FunctionTool` | Client-side callback | **No** — no client process to call back to |
| `OpenApiTool` | Server-side REST call | **Yes** — Foundry calls the HTTP endpoint directly |
| `AzureAISearchTool` | Server-side | **Yes** — Foundry has native integration |
| `BingGroundingTool` | Server-side | **Yes** |
| `CodeInterpreterTool` | Server-side sandbox | **Yes** |

**Lesson:** If a sub-agent needs to access a database or custom service, you must expose it as an HTTP API and use `OpenApiTool`. There is no way to run arbitrary Python callbacks from a ConnectedAgentTool sub-agent.

### 6. OpenApiTool — HTTP Errors Are Fatal

Foundry's `OpenApiTool` treats HTTP 4xx/5xx as fatal. The LLM never sees the error message. Solution: return HTTP 200 with error in the response body + instructional description in the OpenAPI spec.

### 7. Azure Policy Overrides Bicep

Bicep only sets the *initial* state. Azure Policy evaluates continuously and can override properties (e.g., flipping `publicNetworkAccess` to `Disabled`). Always verify deployed state with `az resource show`.

### 8. Private Endpoints Pattern

When any Azure service needs VNet connectivity, the standard pattern requires **3 resources per endpoint**:
1. **Private Endpoint** — NIC attached to subnet, linked to target resource with API-specific `groupId`
2. **Private DNS Zone** — resolves service FQDN to private IP (e.g., `privatelink.documents.azure.com`)
3. **DNS Zone Group** — attaches DNS zone to endpoint for automatic A-record registration

A **VNet Link** connects the Private DNS Zone to the VNet so DNS resolution works from within.

Cosmos DB needs **separate endpoints per API**:

| Cosmos DB API | groupId | Private DNS Zone |
|---------------|---------|------------------|
| NoSQL (SQL) | `Sql` | `privatelink.documents.azure.com` |
| Gremlin | `Gremlin` | `privatelink.gremlin.cosmos.azure.com` |
| MongoDB | `MongoDB` | `privatelink.mongo.cosmos.azure.com` |
| Cassandra | `Cassandra` | `privatelink.cassandra.cosmos.azure.com` |
| Table | `Table` | `privatelink.table.cosmos.azure.com` |

Full DNS zone mapping for all Azure services: [Private endpoint DNS zone values](https://learn.microsoft.com/azure/private-link/private-endpoint-dns)

**Keep Public Access Enabled During Provisioning:** If provisioning scripts run from your dev machine (outside VNet), keep `publicNetworkAccess: 'Enabled'` in Bicep. The private endpoint provides a parallel path — it doesn't require disabling public access. If policy later disables the public path, VNet-connected services still work; only external scripts break.

### 9. Container Apps VNet + External Ingress

Must use `internal: false` in VNet config for the Container App because AI Foundry's `OpenApiTool` calls the app from **outside** the VNet. This preserves the public FQDN while routing outbound traffic through VNet + private endpoints.

**Subnet sizing:**

| Environment Type | Minimum Subnet | API Version |
|-----------------|----------------|-------------|
| Consumption-only (legacy) | `/23` (512 addresses) | `2023-05-01` |
| Workload profiles | `/27` (32 addresses) | `2023-05-01` and later |

Consumption-only requires delegation to `Microsoft.App/environments`. Workload profiles are more subnet-efficient.

**Container Apps Environment VNet config is immutable after creation.** Cannot add VNet to existing CAE. Recovery: `azd down && azd up` (full teardown + reprovision), or manually delete just the CAE resource then `azd provision && azd deploy`.

### 10. Two Cosmos Accounts

The system uses **two separate Cosmos DB accounts**:
- `{name}` — Gremlin API (graph data, key auth)
- `{name}-nosql` — NoSQL/SQL API (telemetry + prompts, RBAC auth)

Each needs its own private endpoint (with different `groupId` values).

### 11. Cosmos DB Document ID Restrictions

Cosmos DB NoSQL rejects document IDs containing `/`, `\`, `?`, or `#`. Use `__` (double underscore) as the segment separator:

```python
# BAD — Cosmos rejects this
doc_id = f"{scenario}/{prompt_name}/v{version}"

# GOOD
doc_id = f"{scenario}__{prompt_name}__v{version}"
# e.g. "telco-noc__orchestrator__v1"
```

Also broken: FastAPI path parameters — an ID containing `/` is interpreted as multiple URL segments and never matches the route. The `__` separator avoids both issues.

**Files affected:** `router_prompts.py` (create_prompt), `router_ingest.py` (upload_prompts). Code that parses IDs back uses `_parse_scenario_from_id()` splitting on `__`.

### 12. Per-Scenario Cosmos Databases — Naming Convention

All scenario data follows a per-scenario naming pattern. Do NOT use a shared database for prompts:

| Data Type | Database Name | Container | Partition Key |
|-----------|--------------|-----------|---------------|
| Graph | `networkgraph` (shared) | `{scenario}-topology` | N/A (graph) |
| Telemetry | `{scenario}-telemetry` | `AlertStream`, `LinkTelemetry` | `/EntityId` |
| Prompts | `{scenario}-prompts` | `prompts` | `/agent` |
| Scenario Registry | `scenarios` (shared) | `scenarios` | `/id` |

To discover which scenarios have prompts, list all databases via ARM and filter names ending in `-prompts`. Strip the suffix to get the scenario name.

To discover saved scenarios, query `scenarios/scenarios` with cross-partition query.

### 13. ARM Creation Calls Block the Event Loop — Split Read vs Write

Cosmos ARM management plane calls (`begin_create_update_sql_database().result()`) block for 10-30 seconds. If these run on every container access (including reads), FastAPI's event loop is blocked and downstream requests timeout.

**How this manifests:** Agent provisioning calls `GET /query/prompts` to fetch prompts. If `_get_prompts_container()` triggers ARM creation on every access, the response takes 30+ seconds. The caller (`config.py`) has a timeout via `urllib.request.urlopen(..., timeout=30)`. The request times out, no prompts are returned, and agents get placeholder defaults like `"You are a graph explorer agent."`

**Fix:** Split the container accessor:
```python
def _get_prompts_container(scenario: str, *, ensure_created: bool = False):
    # ensure_created=False (default): Data-plane client only. Fast. For reads.
    # ensure_created=True: ARM create db/container first. Slow. For writes/uploads.
```

- **Read paths** (list, get, scenarios) → `ensure_created=False`
- **Write paths** (upload, create) → `ensure_created=True`

### 14. Avoid N+1 HTTP Requests Between Co-Located Services

When API (:8000) fetches data from graph-query-api (:8100) inside the same container, each HTTP request has overhead. An N+1 pattern (1 list + N detail requests) multiplies timeout risk.

**Fix:** Use `include_content` query parameter on list endpoints:
```python
url = f"http://127.0.0.1:8100/query/prompts?scenario={sc}&include_content=true"
```

This returns everything in a single request. Also set `timeout=30` (not 10) for internal service calls that hit Cosmos.

### 15. OpenAPI Tools MUST Include X-Graph Header for Per-Scenario Routing

When agents call `/query/graph` or `/query/telemetry` via `OpenApiTool`, Foundry's server-side HTTP client sends the request. If the OpenAPI spec doesn't define an `X-Graph` header parameter, the agent can't send it. The graph-query-api falls back to the default graph from `COSMOS_GREMLIN_GRAPH` env var (typically just `topology`), not the scenario-specific graph. Queries return empty results.

**Fix:** Add `X-Graph` header to the OpenAPI spec with a single-value `enum` substituted at provisioning:
```yaml
parameters:
  - name: X-Graph
    in: header
    required: true
    schema:
      type: string
      enum: ["{graph_name}"]  # Replaced at provisioning time — single-value enum CONSTRAINS the LLM
```

**CRITICAL — Use `enum`, NOT `default`:** LLM agents ignore `default` values (they're advisory hints). The LLM will see a parameter named `X-Graph`, infer it needs a graph name, and choose a plausible but wrong value like `"topology"`. A single-value `enum` constrains the LLM to exactly one valid value — it has no choice but to send the correct graph name. This applies to ANY OpenAPI parameter consumed by an LLM agent that MUST have a specific value (routing headers, API keys, fixed config values).

The provisioner replaces `{graph_name}` with the actual graph name (e.g., `telco-noc-topology`) via `raw.replace("{graph_name}", graph_name)`.

**Implication:** Agents are provisioned for a **specific** scenario. If the user switches scenarios, they must re-provision agents to rebind the tool to the new graph name.

### 16. Container App Env Vars vs azure_config.env — Two Parallel Config Paths

The container **never reads** `azure_config.env`. There are two parallel paths:

```
azure_config.env (local)           Container App env vars
├── Written by: postprovision.sh   ├── Set by: infra/main.bicep env:[]
├── Used by:                       ├── Used by:
│   - Local dev servers            │   - API (os.environ)
│   - preprovision.sh hook         │   - graph-query-api
│   - Local scripts                │   - agent_provisioner.py
└── NOT in Docker image            └── Injected by Azure at start
```

To add a new config variable:
1. Add to `infra/main.bicep` in the container app `env:` array
2. Add to `hooks/postprovision.sh` to populate `azure_config.env`
3. Read in Python via `os.getenv("VAR_NAME")`

Do NOT `COPY azure_config.env` in the Dockerfile. Do NOT `source azure_config.env` in supervisord.

**Exception — `GRAPH_QUERY_API_URI`:** Not set in `main.bicep` (circular reference — URL unknown until after deployment). Falls back to `CONTAINER_APP_HOSTNAME` (auto-set by Azure on every Container App):
```python
graph_query_uri = os.getenv("GRAPH_QUERY_API_URI", "")
if not graph_query_uri:
    hostname = os.getenv("CONTAINER_APP_HOSTNAME", "")
    if hostname:
        graph_query_uri = f"https://{hostname}"
```

### 17. Code-Only Redeployment Decision Tree

| Change Type | Command | Time |
|-------------|---------|------|
| Python code, OpenAPI specs, static files | `azd deploy app` | ~60-90s |
| Bicep infrastructure (new resources, env vars, RBAC) | `azd up` | ~5-10min |
| New env var in container | `azd up` (env vars are in Bicep) | ~5-10min |
| Frontend-only changes | `azd deploy app` | ~60-90s |
| Dockerfile changes | `azd deploy app` | ~60-90s |

**After code-only deploy:** If you changed agent provisioning logic or OpenAPI specs, you must also re-provision agents through the UI (⚙ → Provision Agents) because old agents in Foundry still have old tool specs baked in.

### 18. Cosmos NoSQL RBAC — Both Roles Required

**Both** roles must be assigned to the Container App's managed identity:
- `DocumentDB Account Contributor` on both Cosmos accounts (management plane — ARM create db/container)
- `Cosmos DB Built-in Data Contributor` SQL role on the NoSQL account (data plane — upsert/query)

Cosmos DB NoSQL has its **own RBAC system** separate from ARM:

| Role | GUID | Scope |
|------|------|-------|
| Cosmos DB Built-in Data Reader | `00000000-0000-0000-0000-000000000001` | Data plane read |
| Cosmos DB Built-in Data Contributor | `00000000-0000-0000-0000-000000000002` | Data plane read/write |

These are assigned via `Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments` (NOT `Microsoft.Authorization/roleAssignments`). The ARM role `DocumentDB Account Contributor` controls management plane only.

**Critical:** Create a **fresh** `DefaultAzureCredential()` inside the `asyncio.to_thread()` sync function for ARM calls. Do NOT reuse a credential instance created in the async event loop context — it may have an incompatible transport.

### 19. OpenAPI Tool Headers — Use `enum`, Not `default`

When Foundry's `OpenApiTool` sends HTTP requests on behalf of an agent, the LLM decides parameter values. A `default` value is only a hint — the LLM can and does ignore it, choosing plausible but wrong values (e.g., `X-Graph: topology` instead of `X-Graph: telco-noc-topology`).

**Fix:** Use a single-value `enum` to constrain the LLM:
```yaml
# BAD — LLM ignores default
schema:
  type: string
  default: "telco-noc-topology"

# GOOD — LLM has no choice
schema:
  type: string
  enum: ["telco-noc-topology"]
```

In template form: `enum: ["{graph_name}"]`. The provisioner substitutes the actual value.

**Rule:** When an OpenAPI parameter consumed by an LLM agent MUST have a specific value, use `enum` with a single entry — never `default`. `default` is advisory; `enum` is a constraint. Applies to routing headers, API keys, fixed config values — any parameter where the LLM should not be making a choice.

### 20. Debugging Azure Connectivity Issues

**Diagnostic checklist** when a service returns 403 or connection refused:

1. **Check actual deployed network settings** (not what Bicep says):
   ```bash
   az cosmosdb show -n <name> -g <rg> --query "publicNetworkAccess"
   az cosmosdb show -n <name> -g <rg> --query "ipRules"
   ```

2. **Check for Azure Policy overrides:**
   ```bash
   az monitor activity-log list --resource-group <rg> \
     --query "[?authorization.action=='Microsoft.DocumentDB/databaseAccounts/write'].{caller:caller, time:eventTimestamp, status:status.value}" \
     --output table
   ```

3. **Check RBAC assignments** (for AAD-authed services):
   ```bash
   az role assignment list --scope <resource-id> --output table
   ```

4. **Check private endpoint connection status:**
   ```bash
   az network private-endpoint-connection list --id <resource-id> --output table
   # Status should be "Approved"
   ```

5. **Check DNS resolution from within the VNet:**
   ```bash
   # From a Container App console or VM in the VNet:
   nslookup <account>.documents.azure.com
   # Should resolve to 10.x.x.x (private IP), not a public IP
   ```

**`az cosmosdb update` PreconditionFailed:** Usually means another operation is in progress (wait and retry), a policy is actively enforcing state, or the account has a resource lock. Check activity log to identify the conflicting operation.

### 21. General Deployment Principles

1. **Verify deployed state, not intended state.** Bicep is declarative but not authoritative — policies, manual edits, and drift happen.
2. **Defense in depth for networking.** Private endpoints are the most robust path. Public access + IP rules is fragile (IPs change, policies override).
3. **Design APIs for LLM consumers.** If an agent calls your API, errors must be in the response body (not HTTP status codes), and error messages must contain enough context for the LLM to self-correct.
4. **Understand where your code runs.** Server-side agent tools can't call back to your process. Container Apps in a VNet route outbound through the VNet. Bicep runs at deployment time, but policies run continuously.
5. **Use a single config file.** A dotenv file synced bidirectionally via azd hooks prevents config drift across Bicep, scripts, and runtime.
6. **Immutable infrastructure choices.** Some settings (VNet on CAE, Cosmos DB partition keys) can't be changed after creation. Know which ones before deploying.
7. **Test with `azd deploy` before `azd up`.** Code-only redeployment is 10× faster than full infra provisioning. Structure your workflow to iterate on code separately from infra.

### 22. Two Separate Log Broadcasting Systems

API (:8000) and graph-query-api (:8100) each have their own SSE log endpoint at
`GET /api/logs` with **independent** ring buffers, subscriber queues, and filters:
- API: captures `app.*`, `azure.*`, `uvicorn.*` loggers
- graph-query-api: captures only `graph-query-api.*` loggers

nginx routes `/api/logs` to port 8000 (API), so the graph-query-api's log stream
is only reachable directly at `:8100/api/logs` (useful for local debugging).

### 23. No Authentication on Any Endpoint

Neither the API nor graph-query-api implements authentication or authorization.
All endpoints are publicly accessible when exposed via Container App with external
ingress. Security relies on the Container App's network configuration.

---

## Known Issues & Gotchas

### Dead Code in router_ingest.py
Lines ~120-600 contain OLD commented-out monolithic upload code + old list_scenarios.
Active per-type upload endpoints start after ~line 760. Should be removed in cleanup.

### Edge Topology f-String Bug (cosmosdb.py)
The filtered edge query in `get_topology()` has an f-string continuation bug:
the `.where(otherV().hasLabel({label_csv}))` line is NOT an f-string, so `{label_csv}`
is passed as a literal. Vertex-label-filtered topology requests will fail with a
Gremlin syntax error on the cosmosdb backend. Fix: add `f` prefix to the second
string segment.

### Prompts CRUD Blocks Event Loop
`get_prompt`, `create_prompt`, `update_prompt`, `delete_prompt` in `router_prompts.py`
make synchronous Cosmos SDK calls directly in `async def` handlers without
`asyncio.to_thread()`. Only `list_prompts` and `list_prompt_scenarios` are correct.

### deploy.sh Step 7 Missing graph-query-api
Automated local mode starts API (:8000) and frontend (:5173) but NOT graph-query-api
(:8100). All `/query/*` requests fail. Manual instructions are correct.

### Dead Code in Frontend
- `AlertChart` and `MetricCard` exist but are not imported by any component

### `useInvestigation` Stale Closure
`getQueryHeaders` is not in `submitAlert`'s `useCallback` dep array. If user switches
`activeGraph` without editing alert text, the old `X-Graph` header is sent.

### Agent Provisioning Dependencies
- `GRAPH_QUERY_API_URI` must point to the Container App's public URL (set in `azure_config.env` by postprovision.sh as `APP_URI`)
- Without it, GraphExplorer and Telemetry agents are created WITHOUT tools
- `agent_provisioner.py` is at `/app/scripts/` in the container; `config.py` adds both `PROJECT_ROOT/scripts` and `PROJECT_ROOT/../scripts` to sys.path
- OpenAPI specs at `/app/graph-query-api/openapi/{cosmosdb|mock}.yaml`

### Graph Listing Can Be Slow
`GET /query/scenarios` tries ARM listing first (~5-10s for `CosmosDBManagementClient` discovery), falls back to Gremlin key-auth count query on default graph.

### TopologyRequest.query Is Unsupported
`TopologyRequest.query` parameter is reserved but **raises ValueError** if used. Only `vertex_labels` filtering is supported.

### Prompt Listing Without Scenario Is Slow
`GET /query/prompts` without `?scenario=X` iterates ALL `{scenario}-prompts` databases via ARM discovery — can be slow with many scenarios.

### Prompt Content Is Immutable Per Version
`PUT /query/prompts/{id}` updates metadata only (description, tags, is_active). To change content, create a new version via `POST /query/prompts` (auto-increments version, deactivates previous).

### Frontend Unused Components
`AlertChart` and `MetricCard` exist in `src/components/` but are not imported by any parent component.

### Container Apps Environment VNet Immutability
Cannot add VNet integration to an existing CAE. Must delete + recreate: `azd down && azd up`.

### Cosmos DB Public Access Policy Override
Azure Policy may silently flip `publicNetworkAccess` to `Disabled` post-deployment. Private endpoints provide a parallel path that works regardless.

### Scenario Selection Auto-Provisioning Timing
When user selects a scenario from the ScenarioChip dropdown, topology loads instantly
(via `X-Graph` header change → `useTopology` auto-refetch) but agent provisioning
takes ~30s. During this window, submitting an alert uses old agent bindings (agents
still pointing to the previous scenario's OpenAPI specs and search indexes).
The "Submit Alert" button should be disabled during provisioning.

### Scenario Registry ARM Creation on First Access
`_get_scenarios_container(ensure_created=True)` triggers ARM database + container
creation on the first `GET /query/scenarios/saved` call. This blocks for ~20-30s.
Subsequent calls use the cached container client. Consider separating the creation
to the `POST /query/scenarios/save` path and adding `ensure_created=False` for reads
(same pattern as prompts — see Critical Pattern #13).

### Telemetry Database Derivation Coupling
The telemetry database name is derived in **two different places** with **two different
algorithms** that must produce the same result:
1. **Upload time** (`router_ingest.py`): `f"{scenario_name}-{manifest_suffix}"`
2. **Query time** (`config.py`): `graph_name.rsplit("-", 1)[0] + "-telemetry"`

These agree **only when** the suffix values in `scenario.yaml` are the defaults
(`topology`, `telemetry`). When `scenario_name` override is provided, upload
endpoints now force hardcoded suffixes to maintain consistency. See SCENARIOHANDLING.md
"Telemetry Database Derivation Coupling" section for full analysis.

---

## Configuration Reference

All config lives in `azure_config.env`. Key variables:

| Variable | Set by | Used by |
|----------|--------|---------|
| `AZURE_SUBSCRIPTION_ID` | postprovision | ARM calls, agent provisioner |
| `AZURE_RESOURCE_GROUP` | postprovision | ARM calls |
| `PROJECT_ENDPOINT` | postprovision / Bicep | Agent provisioner, orchestrator |
| `AI_FOUNDRY_PROJECT_NAME` | postprovision / Bicep | Agent provisioner, orchestrator |
| `AI_FOUNDRY_NAME` | postprovision / Bicep | Search connection ID |
| `MODEL_DEPLOYMENT_NAME` | user (default: gpt-4.1) | Agent model |
| `GRAPH_BACKEND` | user (default: cosmosdb) | Backend selector (cosmosdb / mock) |
| `COSMOS_GREMLIN_ENDPOINT` | postprovision | Gremlin WSS connection |
| `COSMOS_GREMLIN_PRIMARY_KEY` | postprovision (`az cosmosdb keys list`) | Gremlin key auth |
| `COSMOS_GREMLIN_DATABASE` | Bicep (default: networkgraph) | Gremlin db (shared across scenarios) |
| `COSMOS_GREMLIN_GRAPH` | Bicep (default: topology) | Fallback graph if no X-Graph header |
| `COSMOS_NOSQL_ENDPOINT` | postprovision (from `{account}-nosql`) | Telemetry + prompts |
| `COSMOS_NOSQL_DATABASE` | Bicep (default: telemetry) | Fallback telemetry db |
| `AI_SEARCH_NAME` | Bicep | Search indexer, index listing |
| `STORAGE_ACCOUNT_NAME` | Bicep | Blob upload |
| `APP_URI` / `GRAPH_QUERY_API_URI` | postprovision | Agent OpenAPI tool base URL |
| `EMBEDDING_MODEL` | Bicep (default: text-embedding-3-small) | Search vectorizer |
| `EMBEDDING_DIMENSIONS` | Bicep (default: 1536) | Vector field dimensions |
| `CORS_ORIGINS` | Bicep (default: *) / user (local: http://localhost:5173) | CORS allowed origins |

**Note**: graph-query-api defaults `CORS_ORIGINS` to `http://localhost:5173,http://localhost:3000` (two origins) when the env var is not set.
| `AGENT_IDS_PATH` | Bicep (default: /app/scripts/agent_ids.json) | Path to provisioned agent IDs |
| `CONTAINER_APP_HOSTNAME` | runtime (if set) | Fallback for `GRAPH_QUERY_API_URI` |

### Local Development

```bash
# Terminal 1: graph-query-api
cd graph-query-api && source ../azure_config.env && GRAPH_BACKEND=mock uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload

# Terminal 2: API
cd api && source ../azure_config.env && uv run uvicorn app.main:app --reload --port 8000

# Terminal 3: Frontend (auto-proxies /api→:8000, /query→:8100)
cd frontend && npm run dev
```

---

## Quick Reference: Where to Fix Things

| Problem | File(s) to check |
|---------|-----------------|
| Upload fails with event loop error | Wrap ALL SDK calls in `asyncio.to_thread()` — see `router_ingest.py` |
| Upload fails with auth/forbidden | Check RBAC in `infra/modules/roles.bicep`, `azd up` to re-apply |
| NoSQL create_database forbidden | Need ARM two-phase: create via `azure-mgmt-cosmosdb`, then data plane |
| Gremlin 401 WSServerHandshakeError | Check `COSMOS_GREMLIN_PRIMARY_KEY` in `azure_config.env` |
| Gremlin 429 throttling | Retry logic in `cosmosdb.py._submit_query()` handles this; increase RU/s |
| Graph not in dropdown | `GET /query/scenarios` in `router_ingest.py` (~line 607) |
| Topology viewer empty | `X-Graph` header in `useTopology.ts`, `ScenarioContext` state |
| Agent provisioning fails | `api/app/routers/config.py`, `scripts/agent_provisioner.py` |
| Agents created without prompts | Upload prompts tarball, check `GET /query/prompts/scenarios` |
| Agents created without tools | Check `GRAPH_QUERY_API_URI` env var = Container App public URL |
| Container build fails | `.dockerignore`, `Dockerfile` COPY paths |
| Search index not created | `AI_SEARCH_NAME` env var, RBAC roles, `search_indexer.py` |
| Health check HTML splash | Container still deploying; wait for revision |
| `No module named agent_provisioner` | `sys.path` in `config.py` — check both `scripts/` paths |
| Investigation stuck >2min | `EVENT_TIMEOUT` in `orchestrator.py`; check sub-agent tool errors |
| SSE stream not reaching frontend | nginx `proxy_buffering off` in `nginx.conf`; check timeouts |
| Prompt upload "illegal chars" | Doc ID has `/`—use `__` separator. See `router_prompts.py`, `router_ingest.py` |
| Cosmos policy override | Check `az cosmosdb show --query publicNetworkAccess`; use private endpoints |
| VNet connectivity issues | Check private endpoint status + DNS resolution from within VNet |
| Prompts listing slow | Use `?scenario=X` filter to avoid iterating all databases |
| Agent queries return empty results | OpenAPI spec `X-Graph` header using `default` instead of `enum`. Check `openapi/cosmosdb.yaml`, use single-value `enum` |
| Topology viewer crashes on label filter | f-string bug in `cosmosdb.py` `get_topology()` edge query. Add `f` prefix. |
| Agents get placeholder prompts | `_get_prompts_container` ensure_created=True on reads blocks event loop; check timeout |
| Config var not reaching container | Add to `infra/main.bicep` `env:[]`, NOT to `azure_config.env` in Dockerfile |
| `GRAPH_QUERY_API_URI` empty in container | Falls back to `CONTAINER_APP_HOSTNAME`. Check `agent_provisioner.py` |
| Prompt CRUD slow / blocks other requests | Sync Cosmos calls in async handlers. Wrap in `asyncio.to_thread()` |
| Local dev `/query/*` fails after `deploy.sh` step 7 | Step 7 doesn't start graph-query-api. Start manually on :8100 |
| Prompt dropdown not refreshed after upload | UploadBox for prompts has no `onComplete` callback. Close/reopen modal |
| Scenario context lost on page refresh | Fixed: `activeScenario` persisted to `localStorage`, bindings auto-derived on mount |
| New scenario data pack | Follow `scenarios/telco-noc/` structure; create `scenario.yaml` + `graph_schema.yaml` |
| Saved scenario not appearing | Check `GET /query/scenarios/saved`; may be first-call ARM delay for `scenarios` db |
| Scenario selection not provisioning | Check `selectScenario()` in `useScenarios.ts`; verify `/api/config/apply` is reachable |
| ScenarioChip shows wrong scenario | Check `activeScenario` in `localStorage`; clear with `localStorage.removeItem('activeScenario')` |
| AddScenarioModal files not auto-detected | Filename must match `{name}-{slot}.tar.gz` pattern; `detectSlot()` in `AddScenarioModal.tsx` |
| Scenario name rejected by backend | Name validation: `^[a-z0-9](?!.*--)[a-z0-9-]{0,48}[a-z0-9]$`; no reserved suffixes |
| Telemetry queries return empty after rename | Upload override forces `-telemetry` suffix; check `config.py` derivation matches |
| Provisioning banner stuck | Check `provisioningStatus` state in `ScenarioContext`; 3s auto-dismiss timer may not fire if error |
| Cosmos 403 after successful deploy | Azure Policy override. Run `az cosmosdb show --query publicNetworkAccess`. See Lesson #20 diagnostic checklist |
| Need to debug VNet DNS issues | Run `nslookup <account>.documents.azure.com` from within VNet. Should resolve to `10.x.x.x`. See Lesson #20 |
| LLM agent sends wrong header value | OpenAPI spec uses `default` — change to single-value `enum`. See Lessons #15 and #19 |
| CAE needs VNet but already deployed | VNet is immutable on CAE. Must `azd down && azd up`. See Lesson #9 |
| Sub-agent tool not executing | `FunctionTool` doesn't work with `ConnectedAgentTool`. Must use `OpenApiTool`. See Lesson #5 |

---

## Scenario Management

> **Full specification:** `documentation/SCENARIOHANDLING.md` (1403 lines)  
> **Status:** Phases 1-3 Complete, Phase 4 Partial

### Overview

Scenarios are first-class objects in the system. A **scenario** bundles together:
- A Gremlin graph (`{name}-topology`)
- Telemetry databases (`{name}-telemetry`)
- Runbook search indexes (`{name}-runbooks-index`)
- Ticket search indexes (`{name}-tickets-index`)
- Prompts (`{name}-prompts`)
- A metadata record in Cosmos NoSQL (`scenarios/scenarios`)

Previously, users had to manually upload 5 tarballs, select each data source from
individual dropdowns, and provision agents — 6+ manual steps with no "scenario"
concept. Now users can create, save, switch, and delete complete scenarios from the UI.

### User Flow

1. **Create:** Click "+New Scenario" → name + 5 file slots → Save → sequential upload → metadata saved
2. **Switch:** Click scenario in Header chip dropdown → auto-binds all data sources → auto-provisions agents
3. **Delete:** ⋮ menu on scenario card → confirmation → deletes metadata only (data preserved)

### Architecture

```
┌─────────────┐    ┌──────────────────────────────────┐    ┌─────────────────────┐
│ ScenarioChip│───▶│ useScenarios.selectScenario()     │───▶│POST /api/config/apply│
│  (Header)   │    │ setActiveScenario() → auto-derive │    │ (SSE provisioning)  │
└─────────────┘    └──────────────────────────────────┘    └─────────────────────┘
       │                      │                                     │
       │            ┌─────────▼───────────┐               ┌────────▼──────────┐
       │            │ ScenarioContext      │               │ ProvisioningBanner│
       │            │ activeScenario       │               │ (28px feedback)   │
       │            │ activeGraph → X-Graph│               └───────────────────┘
       │            │ provisioningStatus   │
       │            │ localStorage persist │
       │            └─────────────────────┘
       │
┌──────▼──────────┐    ┌───────────────────────────────┐
│ AddScenarioModal│───▶│ POST /query/upload/* ×5        │
│ (5 file slots)  │    │ (with ?scenario_name= override)│
│ detectSlot()    │    │ ↓                              │
│ auto-detect     │    │ POST /query/scenarios/save     │
└─────────────────┘    └───────────────────────────────┘
```

### Key Files Added/Modified

| File | Type | Purpose |
|------|------|---------|
| `graph-query-api/router_scenarios.py` | **New** (272 lines) | Scenario CRUD endpoints + `_get_scenarios_container()` |
| `frontend/src/utils/sseStream.ts` | **New** (143 lines) | Shared `consumeSSE()` + `uploadWithSSE()` utilities |
| `frontend/src/components/AddScenarioModal.tsx` | **New** (621 lines) | Multi-slot file upload with auto-detect |
| `frontend/src/components/ScenarioChip.tsx` | **New** (154 lines) | Header scenario selector chip + flyout |
| `frontend/src/components/ProvisioningBanner.tsx` | **New** (102 lines) | Non-blocking provisioning feedback banner |
| `frontend/src/context/ScenarioContext.tsx` | **Modified** (~105 lines) | Added `activeScenario`, `activePromptSet`, `provisioningStatus`, localStorage |
| `frontend/src/types/index.ts` | **Modified** (~55 lines) | Added `SavedScenario`, `SlotKey`, `SlotStatus`, `ScenarioUploadSlot` |
| `frontend/src/hooks/useScenarios.ts` | **Modified** (~180 lines) | Added scenario CRUD + selection; removed dead `uploadScenario()` code |
| `frontend/src/components/SettingsModal.tsx` | **Modified** (~745 lines) | 3-tab layout, scenario cards, read-only Data Sources when active |
| `frontend/src/components/Header.tsx` | **Modified** | Added ScenarioChip + ProvisioningBanner + dynamic agent status |
| `graph-query-api/main.py` | **Modified** | Mounted `router_scenarios` (6th router) |
| `graph-query-api/router_ingest.py` | **Modified** | Added `scenario_name` param to all 5 upload endpoints |

### Cosmos DB "scenarios" Registry

| Property | Value |
|----------|-------|
| Account | Same NoSQL account (`{name}-nosql`) |
| Database | `scenarios` |
| Container | `scenarios` |
| Partition Key | `/id` (scenario name) |
| Throughput | Default (minimal — low volume) |

The database + container are created on first use (same ARM two-phase pattern).
No new env vars required — uses existing `COSMOS_NOSQL_ENDPOINT`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`.

### Scenario Name Validation

Names must match: `^[a-z0-9](?!.*--)[a-z0-9-]{0,48}[a-z0-9]$`
- Lowercase alphanumeric + hyphens only
- No consecutive hyphens (Azure Blob container name restriction)
- 2-50 chars
- Must not end with reserved suffixes: `-topology`, `-telemetry`, `-prompts`, `-runbooks`, `-tickets`
- Enforced in both frontend (input validation) and backend (Pydantic `field_validator` + endpoint validation)

### Implementation Deviations (from SCENARIOHANDLING.md plan)

| # | Plan Said | Implementation | Rationale |
|---|-----------|---------------|----------|
| D-1 | `@microsoft/fetch-event-source` for SSE | Native `fetch()` + `consumeSSE()` | Plan's UX-11 specifies extracting existing native pattern; works correctly with POST + SSE |
| D-2 | `selectScenario` calls all 5 individual setters | Calls only `setActiveScenario(name)` | Auto-derives all 4 bindings; individual calls redundant |
| D-3 | Rename `scenario` param to `scenario_name` | Kept both; `scenario_name` takes priority | Backwards compatibility with existing scripts |
| D-4 | `ProvisioningStatus` in `types/index.ts` | Defined in `ScenarioContext.tsx` | Co-locating avoids circular dependency |
| D-5 | SSE `event:` type markers | Heuristic field-checking | Backend SSE uses `data:` lines only, not `event:` markers |

### Phase 4 Remaining Work

| Item | Status |
|------|--------|
| Override confirmation with detailed metadata (vertex count, prompt count) | 🔶 Basic only |
| Delete with framer-motion exit animation | 🔶 Inline confirmation; no animation |
| Backend `first_time: true` signal for upload performance warning | 🔶 Static warning only |
| Partial upload recovery (retry individual failed uploads) | ⬜ Not done |
| Focus trapping for accessibility | ⬜ Not done |
| Error toasts with auto-dismiss | ⬜ Errors display inline |
| Empty state illustrations | ⬜ Text only |

---

## SDK Versions

| Package | Version | Notes |
|---------|---------|-------|
| `azure-ai-agents` | `1.2.0b6` | OpenApiTool, ConnectedAgentTool, AzureAISearchTool |
| `azure-ai-projects` | `>=1.0.0,<2.0.0` | AIProjectClient |
| `azure-cosmos` | `>=4.9.0` | NoSQL queries + upserts |
| `azure-mgmt-cosmosdb` | `>=9.0.0` | ARM database/graph creation |
| `azure-storage-blob` | `>=12.19.0` | Blob uploads |
| `azure-search-documents` | `>=11.6.0` | Search indexer pipelines |
| `gremlinpython` | `>=3.7.0` | Cosmos Gremlin data-plane (key auth only) |
| `fastapi` | `>=0.115` | ASGI framework |
| `sse-starlette` | `>=1.6` | SSE streaming |
| `react` | 18.x | UI framework |
| `react-force-graph-2d` | ^1.29.1 | Graph visualization (canvas-based) |
| `@microsoft/fetch-event-source` | ^2.0.1 | POST-based SSE client |
| `framer-motion` | ^11.12.0 | Animation (tooltips) |
| `react-markdown` | ^10.1.0 | Diagnosis panel rendering |
| `react-resizable-panels` | ^4.6.2 | Layout panels |
| `tailwindcss` | ^3.4.15 | Styling |
| `clsx` | ^2.1.1 | Conditional CSS class composition |
| `@tailwindcss/typography` | ^0.5.19 | Prose markdown styling |
| `vite` | ^5.4.11 | Build tool |
| `typescript` | ^5.6.3 | Type checking |
| `python-multipart` | (in graph-query-api) | Required for file uploads |
| `pyyaml` | >=6.0 | scenario.yaml parsing |

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| `documentation/SCENARIOHANDLING.md` | Scenario management feature spec — UX design, backend schema, implementation phases, deviations |
| `documentation/azure_deployment_lessons.md` | Detailed Azure deployment lessons (Private Endpoints, Policy, VNet, Bicep patterns) |
| `documentation/CUSTOM_SKILLS.md` | Custom skills documentation (neo4j, cosmosdb gremlin, etc.) |
| `documentation/v11modularagentworkflows.md` | V11 modular agent workflows |
| `documentation/v8codesimplificationandrefactor.md` | V8 code simplification and refactor notes |
| `documentation/v10fabricintegration.md` | V10 Fabric integration plans |
| `documentation/deprecated/` | 16 historical docs (TASKS, BUGSTOFIX, SCENARIO, older versions) — kept for reference |