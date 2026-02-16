# Fabric Integration Plan

## Objective 

Add Fabric Ontology as an alternative graph backend to cosmosDB with gremlin
Fabric will be manually provisioned by user, who only has to provide necessary IDs and such.
Requirements:
1. Manually provide a Fabric workspace ID 
2. Read all available ontologies and provide as a list for graph explorer agent 
3. Select the desired ontology 
4. Read all available eventhouses and provide as a list for telemetry agent.
5. Query graph to retrieve topology and display it using the graph visualizer module 
6. Graph Explorer and Graph telemetry agent will be bound with Fabric data connection - So a connection to the fabric workspace must be created
7. In Data sources settings menu... Have a checkbox. Add a first tab basically to choose which backend will be used. To choose whether using a cosmosDB backend or fabric backend. Clicking it will grey out the cosmosDB tabs and ungrey the fabric tab. In total there are four tabs now.
8. Agents will be able to query the fabric ontology freely. 

Likely, most of the relevant information will be present in /home/hanchoong/projects/autonomous-network-demo/fabric_implementation_references

## Groundwork 

### Current Architecture (Truth from Codebase)

**Three-service unified container architecture:**
- **API** (`:8000`) — 4 routers: `alert`, `agents`, `config`, `logs`. Agent orchestration via Azure AI Foundry SDK (`azure-ai-agents==1.2.0b6`). `POST /api/config/apply` provisions 5 agents via `AgentProvisioner`.
- **graph-query-api** (`:8100`) — 7 routers: `graph`, `telemetry`, `topology`, `ingest`, `prompts`, `scenarios`, `interactions`. Backend abstraction layer via `GraphBackend` Protocol. Per-request graph routing via `X-Graph` header → `ScenarioContext`.
- **Frontend** (React/Vite) — 3-zone layout. `SettingsModal.tsx` (744 lines) has 3 tabs: Scenarios, Data Sources, Upload. `ScenarioContext.tsx` (110 lines) manages active bindings. `useScenarios.ts` (179 lines) handles discovery + provisioning.

**Backend abstraction (`graph-query-api/backends/`):**
- `GraphBackend` Protocol — requires `execute_query()`, `get_topology()`, `close()`
- `GraphBackendType` enum — currently only `COSMOSDB` and `MOCK`
- `get_backend_for_context(ctx: ScenarioContext)` — per-request graph routing with thread-safe cache
- `close_all_backends()` — shutdown cleanup

**Config (`graph-query-api/config.py`):**
- `ScenarioContext` dataclass — `graph_name`, `gremlin_database`, `telemetry_database`, `backend_type`
- `get_scenario_context()` — FastAPI dependency resolving `X-Graph` header → context
- Lazy `get_credential()` — cached `DefaultAzureCredential`
- `BACKEND_REQUIRED_VARS` — per-backend startup validation

**Agent provisioning (`scripts/agent_provisioner.py`):**
- `OPENAPI_SPEC_MAP` — maps `"cosmosdb"` and `"mock"` to YAML files in `graph-query-api/openapi/`
- Creates 5 agents: GraphExplorer (OpenApiTool), Telemetry (OpenApiTool), Runbook (AzureAISearchTool), Ticket (AzureAISearchTool), Orchestrator (ConnectedAgentTool)
- **No `"fabric"` entry** in `OPENAPI_SPEC_MAP`

**Frontend SettingsModal data sources (current):**
- Two modes: **Scenario-derived** (read-only, from `activeScenario` name convention) and **Custom** (dropdown selectors for graph, indexes, prompts)
- Naming convention: scenario `"foo"` → graph `"foo-topology"`, telemetry `"foo-telemetry"`, runbooks `"foo-runbooks-index"`, tickets `"foo-tickets-index"`
- Provisioning POSTs to `/api/config/apply` with bindings, consumes SSE

---

### Reference Implementation Analysis (`fabric_implementation_references/`)

The reference is an **earlier, simpler fork** of the project that added Fabric support but **predates** multi-scenario routing, topology endpoints, upload/ingest system, prompts CRUD, and scenario management. Key findings:

**What exists in the reference:**
1. `GraphBackendType.FABRIC` enum value in `config.py`
2. Fabric config vars: `FABRIC_API`, `FABRIC_SCOPE`, `WORKSPACE_ID`, `GRAPH_MODEL_ID`
3. `get_backend()` factory with `fabric` branch importing `FabricGraphBackend` from `.fabric`
4. Full provisioning pipeline in `scripts/fabric/`: `_config.py`, `provision_lakehouse.py` (308 lines), `provision_eventhouse.py` (469 lines), `provision_ontology.py` (935 lines), `populate_fabric_config.py`, `assign_fabric_role.py`, `collect_fabric_agents.py`
5. `azure_config.env.template` with 30+ Fabric-specific env vars (workspace ID, lakehouse ID, eventhouse ID, ontology ID, graph model ID, KQL DB details, data agent IDs, Fabric connection names)

**What does NOT exist in the reference (never got implemented):**
- `backends/fabric.py` — **does not exist** (only `__init__.py` in backends/)
- OpenAPI spec for Fabric backend — **openapi/ folder is empty**
- No `get_topology()` in the `GraphBackend` protocol (simpler version)
- No `ScenarioContext` / per-request routing
- No topology, ingest, prompts, or scenarios routers

**Architecture gaps between reference and current codebase:**

| Aspect | Current Codebase | Reference | Integration Gap |
|--------|-----------------|-----------|-----------------|
| `GraphBackend` Protocol | `execute_query()` + `get_topology()` + `close()` | `execute_query()` + `close()` only | Fabric backend must implement `get_topology()` |
| Multi-graph routing | `ScenarioContext` + `X-Graph` header → cached backends | Singleton `get_backend()` | Fabric backend must support per-request context |
| Config credential | Lazy `get_credential()` | Eager module-level `credential` | Stick with lazy pattern |
| NoSQL default DB | `"telemetry"` | `"telemetrydb"` | Normalize to `"telemetry"` |
| Backend cache | Thread-safe `_backend_cache` with `get_backend_for_context()` | No cache | Fabric backends must work with existing cache |
| Agent provisioner | `OPENAPI_SPEC_MAP` with `cosmosdb`/`mock` | N/A | Need `fabric` entry or alternative tool approach |

---

### Fabric Technology Stack (from reference scripts and SDK)

**Fabric REST API (`https://api.fabric.microsoft.com/v1`):**
- Auth: `DefaultAzureCredential` → `get_token("https://api.fabric.microsoft.com/.default")`
- Long-running operations: `202 Accepted` → poll `GET /v1/operations/{id}` until `Succeeded`
- Workspace: `GET/POST /v1/workspaces`, role assignments via `/workspaces/{id}/roleAssignments`
- Lakehouse: `GET/POST /v1/workspaces/{id}/lakehouses`, table load via `/lakehouses/{id}/tables/{t}/load`
- Eventhouse: `GET/POST /v1/workspaces/{id}/eventhouses`, KQL databases via `/kqlDatabases`
- Ontology: `GET/POST /v1/workspaces/{id}/ontologies`, definition updates via `/ontologies/{id}/updateDefinition`
- Items: `GET /v1/workspaces/{id}/items` — generic item listing (filter by type)

**OneLake data plane:**
- URL: `https://onelake.dfs.fabric.microsoft.com`
- Client: `azure-storage-file-datalake` → `DataLakeServiceClient`
- Path convention: `{lakehouse_name}.Lakehouse/Files/{table}.csv`
- Already in root `pyproject.toml`: `azure-storage-file-datalake>=12.18.0`

**KQL/Kusto data plane (for Eventhouse):**
- Query URI: `https://<id>.z<n>.kusto.fabric.microsoft.com`
- Ingest URI: `https://ingest-<id>.z<n>.kusto.fabric.microsoft.com`
- Uses `azure-kusto-data` + `azure-kusto-ingest` SDKs
- Management commands: `.create-merge table`, `.create-or-alter table ... ingestion csv mapping`

**Fabric Graph Model:**
- Auto-created when ontology is created/updated
- Ontology defines entity types (8), relationship types (7), data bindings (Lakehouse tables), time-series bindings (Eventhouse tables)
- Graph Model ID stored as `FABRIC_GRAPH_MODEL_ID` — needed for GQL queries

**FabricTool (Azure AI Agents SDK):**
- `from azure.ai.agents.models import FabricTool`
- Connection-based: `FabricTool(connection_id=fabric_connection_name)`
- Opaque — no OpenAPI spec needed (unlike `OpenApiTool`)
- Requires a Microsoft Fabric connection registered in AI Foundry project
- **Key decision point**: For agents running as `ConnectedAgentTool` sub-agents (server-side), `FabricTool` may work natively since it's also server-side (unlike `FunctionTool` which requires client-side callbacks). However, the current architecture uses `OpenApiTool` for graph/telemetry precisely because `FunctionTool` doesn't work in sub-agents. Need to validate whether `FabricTool` works inside `ConnectedAgentTool` sub-agents.

---

### Requirements Decomposition (from Objective)

| Req # | Requirement | Affected Files | Complexity |
|-------|-------------|---------------|------------|
| 1 | Manually provide Fabric workspace ID | `azure_config.env`, `config.py`, SettingsModal | Low |
| 2 | Read all available ontologies from Fabric workspace | New API endpoint (graph-query-api), Fabric REST calls | Medium |
| 3 | Select desired ontology | SettingsModal dropdown, config plumbing | Medium |
| 4 | Read all available eventhouses for telemetry agent | New API endpoint, Fabric REST calls | Medium |
| 5 | Query graph topology from Fabric and display | `backends/fabric.py` implementing `GraphBackend` Protocol | High |
| 6 | Graph Explorer + Telemetry agents bound with Fabric connection | Agent provisioner changes — `FabricTool` or Fabric-specific `OpenApiTool` | High |
| 7 | Backend toggle (CosmosDB vs Fabric) in Settings UI, 4 tabs total | SettingsModal.tsx restructure, config.py, new tab UI | Medium |
| 8 | Agents can query Fabric ontology freely | End-to-end: backend + OpenAPI spec + agent tool config | High |

---

### Key Design Decisions to Resolve

1. **Agent tool strategy: `FabricTool` vs `OpenApiTool` proxy**
   - Current approach uses `OpenApiTool` → `graph-query-api` (proxy) → Cosmos Gremlin. This works because `ConnectedAgentTool` sub-agents run server-side and can make REST calls.
   - **Option A: Keep `OpenApiTool` proxy pattern** — `graph-query-api` gets `backends/fabric.py` that translates Gremlin-like or GQL queries to Fabric REST API. Agents use same OpenAPI spec. Requires a new `openapi/fabric.yaml` spec.
   - **Option B: Use `FabricTool` directly** — Simpler agent config, no proxy needed for graph queries. But: (a) does `FabricTool` work in `ConnectedAgentTool` sub-agents? (b) graph-query-api still needed for topology visualization. (c) Two different query paths — one for agents, one for UI.
   - **Option C: Hybrid** — `FabricTool` for agents + `graph-query-api` Fabric backend for UI topology/visualization. More complex but potentially better UX.
   - **Recommended: Option A** — maintains architectural consistency, single query path, proven pattern.

2. **Fabric Graph Query Language: GQL or Gremlin?**
   - The reference `__init__.py` documents GQL for Fabric. Fabric GraphModel supports GQL natively via REST API.
   - If Option A (proxy), `backends/fabric.py` needs to accept GQL queries and call Fabric REST GraphQL endpoint.
   - Agent prompts for Fabric would need to use GQL instead of Gremlin. Different `language_gremlin.md` → `language_gql.md` in prompt composition.

3. **Telemetry backend: Fabric Eventhouse/KQL vs existing Cosmos NoSQL?**
   - Current telemetry uses Cosmos SQL against NoSQL containers. Eventhouse uses KQL.
   - Need to decide: (a) Fabric mode uses Eventhouse for telemetry (KQL queries), or (b) Fabric mode still uses Cosmos NoSQL for telemetry.
   - Reference has separate provisioning for both Lakehouse (graph) and Eventhouse (telemetry).

4. **Scenario context with Fabric**
   - Current multi-scenario system relies on graph name convention (`X-Graph: foo-topology` → `foo-telemetry`).
   - Fabric backend doesn't have this convention — ontologies and eventhouses are identified by workspace + item IDs.
   - Need new routing: `ScenarioContext` should carry Fabric workspace ID + ontology ID + graph model ID instead of (or in addition to) graph name.

5. **Frontend toggle architecture**
   - v9 requirement: "Have a checkbox in Data Sources settings to choose CosmosDB or Fabric backend. 4 tabs total."
   - Tab structure: **Tab 1** = Backend Selector (CosmosDB/Fabric toggle), **Tab 2** = CosmosDB settings (greyed if Fabric), **Tab 3** = Fabric settings (greyed if CosmosDB), **Tab 4** = one of existing tabs (Scenarios/Upload).
   - OR: Keep 3 tabs but add backend selector at top of Data Sources tab, conditionally rendering different controls.

---

### Files That Will Need Changes

**Backend (graph-query-api):**
- `config.py` — add `FABRIC` to `GraphBackendType`, add Fabric env vars, extend `ScenarioContext` for Fabric routing
- `backends/__init__.py` — add `fabric` branch to `get_backend()`, `get_backend_for_context()`, `get_backend_for_graph()`
- `backends/fabric.py` — **NEW** — implement `GraphBackend` Protocol for Fabric GQL
- `models.py` — potentially extend `GraphQueryRequest` with Fabric-specific fields
- `main.py` — update lifespan checks for Fabric backend vars
- `router_graph.py` — may need Fabric-specific query passthrough
- `router_topology.py` — Fabric topology via GQL
- `router_telemetry.py` — Fabric Eventhouse/KQL support (if using Eventhouse)
- `openapi/fabric.yaml` — **NEW** — OpenAPI spec for Fabric backend mode

**Backend (API):**
- `routers/config.py` — support Fabric backend in provisioning flow
- `scripts/agent_provisioner.py` — add `"fabric"` to `OPENAPI_SPEC_MAP` or switch to `FabricTool`

**Frontend:**
- `SettingsModal.tsx` — backend toggle, Fabric settings tab, ontology/eventhouse dropdowns
- `context/ScenarioContext.tsx` — Fabric state (workspace ID, ontology ID, graph model ID)
- `hooks/useScenarios.ts` — Fabric ontology discovery
- New hook: `useFabric.ts` — Fabric-specific state and API calls (ontology listing, eventhouse listing)

**Configuration:**
- `azure_config.env.template` — add Fabric env vars
- `config.py` — Fabric env var loading

**New backend API endpoints needed (graph-query-api):**
- `GET /query/fabric/ontologies` — list available ontologies in a workspace
- `GET /query/fabric/eventhouses` — list available eventhouses in a workspace
- Or a single `GET /query/fabric/discover` endpoint returning both

**New scripts (from reference, to adapt):**
- `scripts/fabric/` — provisioning pipeline (lakehouse, eventhouse, ontology, config population)

---

### Reference Materials Inventory

| Material | Location | Status |
|----------|----------|--------|
| Fabric provisioning scripts | `fabric_implementation_references/scripts/fabric/` | Complete (6 scripts, well-documented) |
| Fabric env var template | `fabric_implementation_references/azure_config.env.template` | Complete (30+ Fabric vars) |
| Fabric backends `__init__.py` | `fabric_implementation_references/graph-query-api/backends/__init__.py` | Has factory, missing `fabric.py` |
| Fabric config.py | `fabric_implementation_references/graph-query-api/config.py` | Good reference, needs ScenarioContext merge |
| Fabric copilot-instructions | `fabric_implementation_references/copilot-instructions.md` | Architecture context, FabricTool rationale |
| Azure AI SDK - FabricTool | `~/references/skills/.github/skills/azure-ai-projects-py/references/tools.md` | Import reference, minimal usage docs |
| Azure AI SDK - Connections | `~/references/skills/.github/skills/azure-ai-projects-py/references/connections.md` | Connection listing/discovery patterns |
| Provision ontology script | `fabric_implementation_references/scripts/fabric/provision_ontology.py` (935 lines) | Complete ontology definition with 8 entity types, 7 relationships, bindings |
| Provision lakehouse script | `fabric_implementation_references/scripts/fabric/provision_lakehouse.py` (308 lines) | OneLake upload, delta table creation |
| Provision eventhouse script | `fabric_implementation_references/scripts/fabric/provision_eventhouse.py` (469 lines) | KQL table creation, Kusto ingestion |
| Current ARCHITECTURE.md | `documentation/ARCHITECTURE.md` (2486 lines) | Fabric Integration (Future) section at line 2420 |

## Implementation plan