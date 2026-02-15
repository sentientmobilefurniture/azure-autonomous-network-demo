# V9 — Config-Driven Multi-Agent Orchestration

## Why This Comes First

Before adding Fabric or any new backend, the platform needs to be genericized. Right now data schemas, agent tools/instructions, graph ingestion, and the provisioner all have hardcoded assumptions tied to the telco-noc scenario. If we add Fabric on top of that, we'd have to retrofit genericization around two hardcoded backends instead of one. Do the abstraction first, then new backends slot in cleanly.

## Core Idea

A single config file (YAML or similar) fully describes a deployment — the agents, their data sources, the storage backends, the query languages, the prompts, the inter-agent connections, and the UI bindings. The platform reads this config and wires everything together automatically. The current telco-noc scenario becomes just one config file that happens to use cosmosdb-gremlin + specific prompts. A new scenario = a new config file + data, zero code changes.

## The Flow

### 1. Data Exists Somewhere

- User either manually generates data for a scenario, or gets an LLM to do it. The platform doesn't generate it.
- Data can live in CosmosDB, Blob Storage, or (later) Fabric.
- Data also includes prompts (system prompts, runbooks, etc.).

### 2. Named Connectors / Adapters

- Each backend gets a named adapter: e.g. `cosmosdb-gremlin`, `blob-json`, `fabric-kql`, `ai-search`, etc.
- These are format+target-location specific — they know how to read/write/query their backend.
- They are referred to by name in the config file.
- When an agent is assigned a data source using connector X, it automatically gets:
  - The right query language injected into its system prompt (Gremlin, KQL, SQL, etc.)
  - The schema/ontology/metadata for that specific dataset
  - The correct API endpoints / connection details

### 3. Agent Definitions in Config

- Each agent is declared with:
  - Name and model
  - Instructions / system prompt (which may reference prompt files stored as data)
  - Which data sources it uses (by connector name + specific dataset/container/table)
  - Which other agents it connects to (for multi-agent handoffs)
  - Any scenario-specific metadata
- Because an agent is assigned to specific data, it also receives that data's metadata — ontology, table structure, index fields, graph schema, whatever applies.

### 4. Platform Handles the Wiring

- Reads the config → provisions agents in Azure AI Foundry
- Binds the right tools (OpenAPI specs, code interpreter, etc.)
- Sets up inter-agent connections (ConnectedAgentTool)
- Routes graph/topology/telemetry data to the correct UI components
- Injects query language guidance + schema metadata into agent prompts automatically

### 5. Config Is Persisted

- Stored somewhere accessible at runtime (Blob, CosmosDB, local file, etc.)
- The app can reconstruct the full topology without re-provisioning
- When you provision agents or retrieve a graph topology, the app ensures the right data goes to the right agent and the right UI element

## What This Means Architecturally

- `graph-query-api` becomes a thin router that delegates to the right adapter based on config
- `agent_provisioner.py` becomes a generic engine that reads agent specs from config
- The frontend reads topology/metadata from config rather than hardcoded routes
- Every scenario-specific hardcoding gets removed
- The current telco-noc scenario is just one example config

## Config Schema — Key Sections (Draft)

```yaml
scenario:
  name: "telco-noc"
  description: "Telecom NOC monitoring and incident response"

data_sources:
  - name: "network-graph"
    connector: "cosmosdb-gremlin"
    config:
      database: "..."
      container: "..."
    schema:
      # ontology / vertex-edge types / properties
    metadata:
      query_language: "gremlin"
      # anything the agent needs to know about querying this source

  - name: "runbooks"
    connector: "blob-json"
    config:
      container: "..."
      path_prefix: "..."

  - name: "telemetry"
    connector: "ai-search"
    config:
      index_name: "..."
    metadata:
      query_language: "odata"
      fields: [...]

agents:
  - name: "noc-orchestrator"
    model: "gpt-4o"
    instructions_file: "prompts/orchestrator.md"
    data_sources: ["network-graph", "runbooks"]
    connected_agents: ["graph-analyst", "telemetry-analyst"]

  - name: "graph-analyst"
    model: "gpt-4o"
    instructions_file: "prompts/graph-analyst.md"
    data_sources: ["network-graph"]
    tools:
      - type: "openapi"
        spec: "openapi/graph.yaml"

  - name: "telemetry-analyst"
    model: "gpt-4o"
    instructions_file: "prompts/telemetry-analyst.md"
    data_sources: ["telemetry"]
    tools:
      - type: "openapi"
        spec: "openapi/telemetry.yaml"
```

## Hard Parts / Considerations

1. **Config schema expressiveness** — needs to be powerful enough to capture all wiring without becoming its own programming language. Keep it declarative.

2. **Adapter abstraction** — each backend has very different query patterns (Gremlin traversals vs KQL vs SQL vs REST). The adapter interface needs to be generic enough to cover all of them while still being useful.

3. **Prompt templating** — injecting schema metadata + query language guidance dynamically into agent system prompts. Need a templating approach (Jinja2, string interpolation, etc.) that composes base instructions + connector-specific guidance + dataset-specific metadata.

4. **UI rendering** — the frontend must be able to render arbitrary topologies, not just the current telco-noc layout. Force-graph is already flexible, but the sidebar, panels, and data display need to be config-aware.

5. **OpenAPI spec generation** — if each connector exposes different query endpoints, the OpenAPI specs given to agents may need to be generated or templated per data source, not hand-written per scenario.

6. **Migration path** — the current telco-noc scenario should keep working throughout this refactor. Build the generic layer, then migrate telco-noc to use it as the first "config-driven" scenario.

## Sequencing

1. **Audit** — catalog every hardcoded assumption, every scenario-specific reference, every place that needs to become config-driven
2. **Design the config schema** — nail down the YAML structure
3. **Build adapter abstraction** — define the interface, implement cosmosdb-gremlin as first adapter
4. **Generic agent provisioner** — reads agent specs from config, provisions in Foundry
5. **Generic graph-query-api** — thin router delegating to adapters
6. **Prompt templating** — auto-inject query language + schema into agent prompts
7. **Frontend genericization** — config-aware rendering
8. **Migrate telco-noc** — rewrite current scenario as a config file, verify everything works
9. **Add new backends** — Fabric, Neo4j, etc. become new adapters + config options

---

## Codebase Audit — Layer by Layer

### Layer 1: graph-query-api (Port 8100)

The data-plane micro-service. All `/query/*` routes. This is the most complex layer.

#### Files
- `main.py` — FastAPI app, mounts 7 routers, SSE log streaming
- `config.py` — env var loading, `GraphBackendType` enum, `ScenarioContext` dataclass
- `models.py` — Pydantic models for requests/responses (graph, telemetry, topology, interactions)
- `backends/__init__.py` — `GraphBackend` Protocol, factory `get_backend()`, per-graph cache
- `backends/cosmosdb.py` — CosmosDB Gremlin backend (304 lines)
- `backends/mock.py` — Mock backend for offline demos
- `cosmos_helpers.py` — Singleton CosmosClient, ARM container creation, container cache
- `router_graph.py` — `POST /query/graph` — dispatches to GraphBackend
- `router_topology.py` — `POST /query/topology` — returns nodes/edges for force-graph UI
- `router_telemetry.py` — `POST /query/telemetry` — Cosmos SQL against NoSQL containers
- `router_ingest.py` — **872 lines** — uploads graph, telemetry, runbooks, tickets, prompts as tarballs
- `router_prompts.py` — CRUD for agent prompts in Cosmos NoSQL (289 lines)
- `router_scenarios.py` — CRUD for scenario metadata in Cosmos NoSQL
- `router_interactions.py` — Save/list/get/delete investigation records
- `search_indexer.py` — Creates AI Search indexes from blob containers
- `sse_helpers.py` — SSE progress helper for uploads
- `openapi/cosmosdb.yaml` — OpenAPI spec template (Gremlin-specific descriptions)
- `openapi/mock.yaml` — OpenAPI spec template (mock-specific descriptions)

#### What's Already Generic ✅
- **GraphBackend Protocol** — `backends/__init__.py` defines a clean interface with `execute_query()`, `get_topology()`, `close()`. CosmosDB and Mock implement it.
- **Per-graph backend cache** — `get_backend_for_context(ctx)` routes to the right backend instance per scenario.
- **ScenarioContext** — `config.py` derives per-request routing from `X-Graph` header (graph name, telemetry DB, prompts container, telemetry prefix). This is already scenario-aware.
- **graph_schema.yaml driven ingestion** — `router_ingest.py` reads vertex/edge definitions from YAML and loads generically. No entity-type hardcoding in the loader itself.
- **scenario.yaml manifest** — Each scenario has a manifest with paths, cosmos config, search indexes, graph styles. The ingest router reads this.

#### What's Hardcoded / Needs Genericization 🔴
1. **`GraphBackendType` enum** is `cosmosdb | mock` only. Adding Fabric requires extending this, OR better: removing the enum entirely and using string-based adapter names loaded from config.
2. **Backend factory** (`get_backend()`, `get_backend_for_graph()`) — dispatches via if/elif. Should become registry-based or plugin-based.
3. **`BACKEND_REQUIRED_VARS`** in config.py — maps backend type to required env vars. Hardcoded per backend.
4. **`router_telemetry.py`** — entirely Cosmos SQL-specific. Hardcodes `CosmosClient`, `query_items()`. A Fabric backend would need KQL instead. This router would need to dispatch to a telemetry adapter.
5. **`router_ingest.py`** — massively hardcoded to Cosmos:
   - Graph upload calls `_gremlin_client()`, `_gremlin_submit()` directly
   - Telemetry upload calls `get_cosmos_client()`, `upsert_item()` directly
   - Knowledge files upload to Azure Blob + AI Search directly
   - `_ensure_gremlin_graph()` uses ARM API specific to Cosmos Gremlin
   - `_ensure_nosql_containers()` uses ARM API specific to Cosmos NoSQL
   - `PROMPT_AGENT_MAP` hardcodes agent filename → role mapping
6. **OpenAPI specs** — `openapi/cosmosdb.yaml` contains Gremlin-specific descriptions ("Execute a Gremlin query..."). A Fabric backend would need KQL-specific descriptions. These should be generated/templated per connector.
7. **`OPENAPI_SPEC_MAP`** in `agent_provisioner.py` — maps `cosmosdb → cosmosdb.yaml`, `mock → mock.yaml`. No Fabric entry.
8. **`cosmos_helpers.py`** — all Cosmos-specific. ARM container creation, CosmosClient singleton. Fabric would have its own helpers.
9. **Telemetry container prefixing** — `{prefix}-AlertStream` pattern is hardcoded in both `router_telemetry.py` and `ScenarioContext`.
10. **Prompts database** — hardcoded to Cosmos NoSQL `prompts` DB. The prompt CRUD is Cosmos-specific.

#### Key Observation
The **graph backend** (query + topology) already has a decent abstraction. The bigger problem is that **telemetry**, **ingestion**, **prompts**, and **scenario CRUD** are all tightly coupled to Cosmos NoSQL. These need adapter abstractions too — or at minimum, the current Cosmos implementation needs to be wrapped so a Fabric implementation can slot in.

---

### Layer 2: API Backend (Port 8000)

The orchestrator/agent-facing API. All `/api/*` routes.

#### Files
- `api/app/main.py` — FastAPI app, mounts 4 routers
- `api/app/orchestrator.py` — **501 lines** — bridges Foundry agent streaming to SSE
- `api/app/routers/alert.py` — `POST /api/alert` — submits alert, returns SSE stream
- `api/app/routers/agents.py` — `GET /api/agents` — lists agents from `agent_ids.json`
- `api/app/routers/config.py` — `POST /api/config/apply` + `GET /api/config/current` — re-provisions agents
- `api/app/routers/logs.py` — `GET /api/logs` — SSE log streaming

#### What's Already Generic ✅
- **`orchestrator.py`** — runs ANY orchestrator agent by ID. Reads agent_ids.json, resolves names. No scenario-specific logic in the streaming bridge.
- **`alert.py`** — passes text to orchestrator, returns SSE. Scenario-agnostic.
- **`agents.py`** — reads agent_ids.json. Scenario-agnostic (though stub names are telco-specific).

#### What's Hardcoded / Needs Genericization 🔴
1. **`config.py` `/api/config/apply`** — hardcodes exactly 5 agent types (`orchestrator`, `graph_explorer`, `telemetry`, `runbook`, `ticket`). Default prompts are hardcoded. The provisioning call assumes this exact agent structure.
2. **Stub agent names** in `agents.py` — `["Orchestrator", "GraphExplorerAgent", "TelemetryAgent", "RunbookKBAgent", "HistoricalTicketAgent"]`. These are telco-NOC-specific role names.
3. **Config state** — `_current_config` tracks `graph`, `runbooks_index`, `tickets_index`. This assumes exactly these data sources exist.
4. **Prompt fetching in config.py** — calls `http://127.0.0.1:8100/query/prompts?scenario=X` and maps by agent name. The mapping assumes fixed agent roles.
5. **Search connection ID** — hardcoded path pattern `aisearch-connection`.

#### Key Observation
The API layer is relatively thin and mostly generic. The main issue is `config.py` which assumes a fixed 5-agent topology. Making the agent set configurable is the core change needed here.

---

### Layer 3: Agent Provisioner (scripts/)

Creates Azure AI Foundry agents with tools and inter-agent connections.

#### Files
- `scripts/agent_provisioner.py` — **282 lines** — `AgentProvisioner` class
- `scripts/provision_agents.py` — CLI wrapper, loads prompts from disk

#### What's Hardcoded / Needs Genericization 🔴
1. **`AGENT_NAMES`** — `["GraphExplorerAgent", "TelemetryAgent", "RunbookKBAgent", "HistoricalTicketAgent", "Orchestrator"]`. Fixed 5-agent structure.
2. **`OPENAPI_SPEC_MAP`** — `cosmosdb → cosmosdb.yaml`, `mock → mock.yaml`. No extensibility.
3. **`GRAPH_TOOL_DESCRIPTIONS`** — backend-specific descriptions. Hardcoded per backend.
4. **`provision_all()`** — creates exactly 4 sub-agents + 1 orchestrator in a hardcoded sequence:
   - GraphExplorer → OpenAPI tool (graph query)
   - Telemetry → OpenAPI tool (telemetry query)
   - RunbookKB → AzureAISearchTool (runbooks index)
   - HistoricalTicket → AzureAISearchTool (tickets index)
   - Orchestrator → ConnectedAgentTool to all 4 above
5. **`provision_agents.py`** — loads prompts from fixed filenames: `foundry_orchestrator_agent.md`, `foundry_telemetry_agent_v2.md`, etc.
6. **`_load_graph_explorer_prompt()`** — composes from `core_instructions.md`, `core_schema.md`, `language_gremlin.md`. The composition pattern is hardcoded.

#### Key Observation
This is the most rigidly structured layer. The entire concept of "5 agents with these specific roles and tools" needs to become declarative. A config file should define N agents, each with their tools (OpenAPI, AzureAISearch, CodeInterpreter, ConnectedAgent), and the provisioner should create them generically.

---

### Layer 4: Data Layer (data/scenarios/)

#### Structure per scenario (telco-noc)
```
data/scenarios/telco-noc/
├── scenario.yaml          # manifest: name, description, cosmos config, paths, graph_styles
├── graph_schema.yaml      # vertex/edge definitions for Gremlin ingestion
├── data/
│   ├── entities/          # CSV files for graph vertices (DimCoreRouter.csv, etc.)
│   ├── telemetry/         # AlertStream.csv, LinkTelemetry.csv
│   ├── knowledge/
│   │   ├── runbooks/      # .md files → Blob + AI Search
│   │   └── tickets/       # .txt files → Blob + AI Search
│   └── prompts/           # Agent prompt .md files
│       └── graph_explorer/ # Composable prompt fragments
└── scripts/               # Generation scripts (not used at runtime)
```

#### What's Already Generic ✅
- **`scenario.yaml`** — already declarative: name, display_name, description, paths, cosmos config, search indexes, graph_styles, use_cases, example_questions.
- **`graph_schema.yaml`** — fully generic vertex/edge loader. Any entity types work. No telco-specific code in the loader.
- **Tarball upload** — each data type (graph, telemetry, runbooks, tickets, prompts) uploads separately as `.tar.gz`. The upload router reads `scenario.yaml` to resolve names.

#### What's Hardcoded / Needs Genericization 🔴
1. **`scenario.yaml` cosmos section** — assumes `gremlin.database`, `gremlin.graph`, `nosql.database`, `nosql.containers`. A Fabric scenario would need `kusto.cluster`, `kusto.database`, `kusto.tables` instead.
2. **`graph_schema.yaml`** — Gremlin-specific concept (vertices, edges, addV/addE). A Fabric equivalent would be table definitions. The ingest logic in `router_ingest.py` is entirely Gremlin.
3. **Prompt filenames** — `PROMPT_AGENT_MAP` in `router_ingest.py` hardcodes the mapping: `foundry_orchestrator_agent.md → orchestrator`, etc. New agent roles would need new entries.
4. **GraphExplorer prompt composition** — hardcodes looking for `graph_explorer/core_instructions.md`, `core_schema.md`, `language_gremlin.md`.
5. **CSV-based ingestion** — telemetry assumes CSV → Cosmos NoSQL `upsert_item()`. A Fabric backend might need CSV → KQL `.ingest inline`.

#### Key Observation
The data layer is actually the best organized. `scenario.yaml` and `graph_schema.yaml` are already close to what a generic config system needs. The main gap is making `scenario.yaml` backend-agnostic — supporting multiple data store types, not just CosmosDB Gremlin + NoSQL.

---

### Layer 5: Frontend (React + TypeScript)

#### Key Files
- `context/ScenarioContext.tsx` — global state for active scenario, graph, indexes, styles
- `hooks/useTopology.ts` — fetches topology from `/query/topology`
- `hooks/useNodeColor.ts` — resolves node colors (user override → scenario → hardcoded → auto)
- `hooks/useInvestigation.ts` — submits alerts, handles SSE streaming
- `hooks/useScenarios.ts` — manages scenario list from `/query/scenarios/saved`
- `hooks/useInteractions.ts` — interaction history CRUD
- `components/graph/graphConstants.ts` — **hardcoded** NODE_COLORS and NODE_SIZES
- `components/GraphTopologyViewer.tsx` — force-graph rendering
- `components/SettingsModal.tsx` — data source/prompt configuration UI
- `components/AddScenarioModal.tsx` — scenario upload UI
- `types/index.ts` — TypeScript types for SavedScenario, StepEvent, Interaction

#### What's Already Generic ✅
- **`ScenarioContext`** — already derives bindings from scenario name (`{name}-topology`, `{name}-runbooks-index`, etc.)
- **`useTopology`** — fetches from `/query/topology` with `X-Graph` header. Scenario-agnostic.
- **`useNodeColor`** — fallback chain: user override → scenario-driven → hardcoded → auto-hash. The auto-hash means NEW label types get colors automatically.
- **`SavedScenario` type** — supports arbitrary `resources`, `graph_styles`, `use_cases`, `example_questions`.
- **Force-graph rendering** — renders arbitrary node/edge topologies. Not scenario-specific.

#### What's Hardcoded / Needs Genericization 🔴
1. **`graphConstants.ts`** — hardcoded `NODE_COLORS` and `NODE_SIZES` for `CoreRouter`, `AggSwitch`, `BaseStation`, `TransportLink`, `MPLSPath`, `Service`, `SLAPolicy`, `BGPSession`. These are telco-specific labels.
2. **`SettingsModal`** — likely assumes specific data source types (graph, runbooks, tickets).
3. **Agent stub names** — `_STUB_AGENTS` in `alert.py` references telco agent names.
4. **Resource derivation** — `ScenarioContext` hardcodes the pattern `{name}-topology`, `{name}-runbooks-index`, `{name}-tickets-index`. This assumes every scenario has exactly these resources.

#### Key Observation
The frontend is surprisingly well-prepared. The force-graph renders any topology, `useNodeColor` auto-assigns colors for unknown labels, and `ScenarioContext` already manages per-scenario state. The main changes are: (a) remove hardcoded `graphConstants.ts` defaults (or keep as fallback), (b) make `SettingsModal` data-source-aware from config, (c) make resource derivation configurable rather than pattern-based.

---

### Layer 6: Config & Deployment

#### Files
- `azure_config.env.template` — environment variables (all scenarios share one config)
- `Dockerfile` — single container: nginx + API + graph-query-api
- `supervisord.conf` — runs nginx, API, graph-query-api
- `nginx.conf` — routes `/api/*` → :8000, `/query/*` → :8100, `/` → React SPA
- `azure.yaml` — Azure Developer CLI config
- `deploy.sh` — deployment helper
- `infra/` — Bicep templates for Azure resources

#### What's Already Generic ✅
- **Container architecture** — 3-service single container is scenario-agnostic.
- **nginx routing** — path-based, no scenario-specific routes.
- **Bicep** — creates shared Cosmos DBs (`networkgraph`, `telemetry`, `prompts`, `scenarios`, `interactions`), AI Search, Storage. Shared resources, not per-scenario.

#### What's Hardcoded / Needs Genericization 🔴
1. **`azure_config.env.template`** — has `DEFAULT_SCENARIO=telco-noc` and `LOADED_SCENARIOS=telco-noc`. These should become runtime config.
2. **`COSMOS_GREMLIN_GRAPH=topology`** — default graph name. Should come from scenario config.
3. **`RUNBOOKS_INDEX_NAME=runbooks-index`**, **`TICKETS_INDEX_NAME=tickets-index`** — default index names. Should come from scenario config.

#### Key Observation
Deployment layer is mostly clean. The few hardcoded defaults in `.env.template` are minor — they're only used as fallbacks when no scenario is selected.

---

## Summary: What Must Change (Priority Order)

### Must Change (Blockers for Genericization)
1. **Agent provisioner** — from hardcoded 5 agents to config-driven N agents with arbitrary tools
2. **Telemetry router** — from Cosmos SQL-only to adapter-dispatched
3. **Ingest router** — from Cosmos Gremlin-only to adapter-dispatched ingestion
4. **OpenAPI specs** — from static per-backend YAML to generated/templated per connector+scenario
5. **Backend enum** — from `cosmosdb | mock` to extensible registry
6. **Config apply endpoint** — from hardcoded 5-agent provisioning to config-driven

### Should Change (Clean but Not Blocking)
7. **`graphConstants.ts`** — remove hardcoded telco colors/sizes (keep auto-assign)
8. **Prompt filename mapping** — from hardcoded `PROMPT_AGENT_MAP` to config-driven
9. **ScenarioContext resource derivation** — from pattern-based to config-specified
10. **Stub agents** — remove telco-specific stub names

### Already Good (Minimal or No Change)
- GraphBackend Protocol + factory
- ScenarioContext multi-graph support
- scenario.yaml / graph_schema.yaml structure
- Force-graph topology rendering
- Orchestrator SSE bridge
- nginx / Dockerfile / supervisord architecture
---

## Codebase Investigation — Concrete Details for Implementation

> This section captures exact code shapes, interface contracts, and parameters
> discovered during codebase audit. Intent: remove guesswork from implementation.

### 1. Exact GraphBackend Protocol (Current Interface)

From `graph-query-api/backends/__init__.py`:

```python
@runtime_checkable
class GraphBackend(Protocol):
    async def execute_query(self, query: str, **kwargs) -> dict:
        """Returns {columns: [{name, type}], data: [dict]}"""
        ...

    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Returns {nodes: [{id, label, properties}], edges: [{id, source, target, label, properties}]}"""
        ...

    def close(self) -> None: ...
```

**V9 implication:** This Protocol is query-language-agnostic already — `execute_query(query: str)` accepts any string. The adapter decides how to interpret it (Gremlin, KQL, SQL, etc.). No change needed to the Protocol itself. The `**kwargs` allows passing extra parameters per-backend.

**Gap:** The telemetry query path does NOT use `GraphBackend`. It's a separate code path directly in `router_telemetry.py` calling `_execute_cosmos_sql()`. For V9, telemetry needs its own adapter protocol or the existing `GraphBackend` needs a telemetry method, or a separate `TelemetryBackend` protocol.

### 2. Backend Factory & Cache (Exact Dispatch Pattern)

From `graph-query-api/backends/__init__.py`:

```python
_backend_cache: dict[str, GraphBackend] = {}
_backend_lock = threading.Lock()

def get_backend_for_context(ctx: ScenarioContext) -> GraphBackend:
    if ctx.backend_type == GraphBackendType.MOCK:
        return get_backend_for_graph("__mock__", ctx.backend_type)
    return get_backend_for_graph(ctx.graph_name, ctx.backend_type)

def get_backend_for_graph(graph_name, backend_type=None) -> GraphBackend:
    bt = backend_type or GRAPH_BACKEND
    cache_key = f"{bt.value}:{graph_name}"
    with _backend_lock:
        if cache_key not in _backend_cache:
            if bt == GraphBackendType.COSMOSDB:
                from .cosmosdb import CosmosDBGremlinBackend
                _backend_cache[cache_key] = CosmosDBGremlinBackend(graph_name=graph_name)
            elif bt == GraphBackendType.MOCK:
                from .mock import MockGraphBackend
                _backend_cache[cache_key] = MockGraphBackend()
            else:
                raise ValueError(...)
```

**V9 plan:** Replace `if/elif` dispatch with a registry pattern. Each adapter registers itself by name. The factory looks up by string key from config.

### 3. ScenarioContext — Full Current Shape

From `graph-query-api/config.py`:

```python
@dataclass
class ScenarioContext:
    graph_name: str                  # "cloud-outage-topology"
    gremlin_database: str            # "networkgraph" (shared)
    telemetry_database: str          # "telemetry" (shared)
    telemetry_container_prefix: str  # "cloud-outage"
    prompts_database: str            # "prompts" (shared)
    prompts_container: str           # "cloud-outage"
    backend_type: GraphBackendType
```

**V9 implication:** This dataclass needs extension. A config-driven scenario would add:
- `connector_name: str` — which adapter to use (replaces `backend_type` enum)
- Per-connector config dict (connection strings, database names, etc.)
- Currently, derivation is hardcoded: `graph_name.rsplit("-", 1)[0]` → prefix. Config should make this explicit.

### 4. Agent Provisioner — Exact Hardcoded Structure

From `scripts/agent_provisioner.py`:

```python
AGENT_NAMES = [
    "GraphExplorerAgent", "TelemetryAgent", "RunbookKBAgent",
    "HistoricalTicketAgent", "Orchestrator",
]

OPENAPI_SPEC_MAP = {
    "cosmosdb": OPENAPI_DIR / "cosmosdb.yaml",
    "mock": OPENAPI_DIR / "mock.yaml",
}

GRAPH_TOOL_DESCRIPTIONS = {
    "cosmosdb": "Execute a Gremlin query against Azure Cosmos DB...",
    "mock": "Query the topology graph (offline mock mode).",
}
```

`provision_all()` signature (what a config-driven provisioner must replace):

```python
def provision_all(
    self,
    model: str,                    # "gpt-4.1"
    prompts: dict[str, str],       # {agent_key: prompt_content}
    graph_query_api_uri: str,      # base URL for OpenAPI tools
    graph_backend: str,            # "cosmosdb" or "mock"
    graph_name: str,               # "telco-noc-topology" (X-Graph value)
    runbooks_index: str,           # AI Search index name
    tickets_index: str,            # AI Search index name
    search_connection_id: str,     # Foundry connection ID for AI Search
    force: bool = True,
    on_progress: callable | None = None,
) -> dict:
```

**Exact tool types available in Foundry SDK:**
- `OpenApiTool(name, spec, description, auth)` — needs OpenAPI YAML spec dict
- `AzureAISearchTool(index_connection_id, index_name, query_type, top_k)` — needs Foundry connection ID
- `ConnectedAgentTool(id, name, description)` — needs agent IDs from sub-agents

**V9 plan:** Config declares agents as list of dicts. Each agent declares its tools by type. The provisioner iterates the list, creates matching SDK tool objects, then wires orchestrator → sub-agents via ConnectedAgentTool.

### 5. OpenAPI Spec — Exact Template Mechanism

From `graph-query-api/openapi/cosmosdb.yaml`:

```yaml
servers:
  - url: "{base_url}"                   # replaced at runtime
paths:
  /query/graph:
    post:
      parameters:
        - name: X-Graph
          in: header
          schema:
            enum: ["{graph_name}"]      # replaced at runtime
      requestBody:
        schema:
          properties:
            query:
              type: string
              description: |
                A Gremlin traversal query string...
```

**Key details for V9:**
- `{base_url}` replacement: `raw.replace("{base_url}", graph_query_api_uri.rstrip("/"))`
- `{graph_name}` replacement: `raw.replace("{graph_name}", graph_name)`
- `_load_openapi_spec()` has a `keep_path` parameter for prefix-filtering paths
- The **description fields** are Gremlin-specific (mentions `addV`, `has()`, vertex labels)
- The telemetry spec hardcodes `container_name` enum to `["AlertStream", "LinkTelemetry"]`

**V9 gap:** For a new backend (Fabric/KQL), need entirely different:
- Query language description text
- Container/table name enums
- Query syntax examples
These must come from config, not static YAML. Options: (a) Jinja2-templated YAML, (b) programmatic spec generation, (c) per-connector spec templates with config-driven variable injection.

### 6. Telemetry Router — Exact Cosmos SQL Coupling

From `graph-query-api/router_telemetry.py`:

```python
container_name = f"{ctx.telemetry_container_prefix}-{req.container_name}"
# Then directly calls:
client = get_cosmos_client()
database = client.get_database_client(db_name)
container = database.get_container_client(container_name)
items = list(container.query_items(query=query, enable_cross_partition_query=True))
```

**V9 gap:** This is a completely separate code path from `GraphBackend`. No adapter abstraction exists for telemetry queries. A `TelemetryBackend` protocol is needed, mirroring `GraphBackend`:

```python
class TelemetryBackend(Protocol):
    async def execute_query(self, query: str, container_name: str, **kwargs) -> dict:
        """Returns {columns: [...], rows: [...]}"""
        ...
```

### 7. Ingest Router — Exact Backend-Specific Code

`router_ingest.py` (872 lines) has 5 distinct upload paths, each tightly coupled:

| Upload | Backend Coupling |
|--------|-----------------|
| Graph | `_gremlin_client()`, `_gremlin_submit()`, `_ensure_gremlin_graph()` — all Gremlin-specific |
| Telemetry | `get_cosmos_client()`, `container.upsert_item()` — Cosmos NoSQL-specific |
| Runbooks | `BlobServiceClient` + `search_indexer.create_search_index()` — Blob+Search-specific |
| Tickets | Same as Runbooks |
| Prompts | `_get_prompts_container()`, `container.upsert_item()` — Cosmos NoSQL-specific |

**V9 gap:** Ingestion needs adapter abstraction. Each connector must provide:
- `ingest_graph(schema, data_dir, progress)` — knows how to load graph data
- `ingest_telemetry(containers_config, data_dir, progress)` — knows how to load telemetry
- Infrastructure setup (ARM calls, Gremlin graph creation, etc.) is also backend-specific

The knowledge file uploads (runbooks/tickets) are actually backend-agnostic already — they go to Blob + AI Search regardless of graph backend. These can stay as-is.

### 8. Prompt Composition — Exact Hardcoded Patterns

From `router_ingest.py`:

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

GraphExplorer is composed from 3 hardcoded files:
```
graph_explorer/core_instructions.md
graph_explorer/core_schema.md
graph_explorer/language_gremlin.md
```
Joined with `\n\n---\n\n`.

**Actual prompt files in telco-noc:**
```
data/prompts/
├── alert_storm.md
├── foundry_historical_ticket_agent.md
├── foundry_orchestrator_agent.md
├── foundry_runbook_kb_agent.md
├── foundry_telemetry_agent_v2.md
└── graph_explorer/
    ├── core_instructions.md
    ├── core_schema.md
    ├── description.md         # NOT used in composition
    ├── language_gremlin.md
    └── language_mock.md       # NOT used in composition
```

**V9 gap:** The prompt ↔ agent mapping must come from config, not a hardcoded dict. Config should declare:
- Per agent: which prompt file(s) to use
- Whether prompt is composed from fragments or single file
- Which language file to use based on connector type (e.g., `language_gremlin.md` vs `language_kql.md`)
- Placeholder substitution patterns (`{graph_name}`, `{scenario_prefix}`)

The existing `description.md` and `language_mock.md` in graph_explorer/ are already evidence of a composition pattern that could be config-driven.

### 9. Config Apply Endpoint — Exact Hardcoded Defaults

From `api/app/routers/config.py`:

```python
defaults = {
    "orchestrator": "You are an investigation orchestrator.",
    "graph_explorer": "You are a graph explorer agent.",
    "telemetry": "You are a telemetry analysis agent.",
    "runbook": "You are a runbook knowledge base agent.",
    "ticket": "You are a historical ticket search agent.",
}
```

The endpoint hardcodes:
- Prompt fetching from `http://127.0.0.1:8100/query/prompts?scenario={prefix}`
- Placeholder substitution: `{graph_name}` and `{scenario_prefix}`
- Search connection ID path: `aisearch-connection` (hardcoded name)
- `"All 5 agents re-provisioned"` log message

**V9 plan:** This endpoint reads agent definitions from config instead of hardcoding 5 agents.

### 10. Frontend ScenarioContext — Exact Derivation Pattern

From `frontend/src/context/ScenarioContext.tsx`:

```typescript
const deriveGraph = (name: string | null) => name ? `${name}-topology` : 'topology';
const deriveRunbooks = (name: string | null) => name ? `${name}-runbooks-index` : 'runbooks-index';
const deriveTickets = (name: string | null) => name ? `${name}-tickets-index` : 'tickets-index';
const derivePrompts = (name: string | null) => name ?? '';
```

And on `setActiveScenario`:
```typescript
setActiveGraph(`${name}-topology`);
setActiveRunbooksIndex(`${name}-runbooks-index`);
setActiveTicketsIndex(`${name}-tickets-index`);
setActivePromptSet(name);
```

**V9 gap:** These derivation functions assume exactly 3 resource types (graph, runbooks, tickets). It also assumes naming conventions (`-topology`, `-runbooks-index`, `-tickets-index`). With config-driven scenarios, the `SavedScenario` type already has a `resources` field that stores exact names:

```typescript
resources: {
    graph: string;
    telemetry_database: string;
    telemetry_container_prefix?: string;
    runbooks_index: string;
    tickets_index: string;
    prompts_database: string;
    prompts_container?: string;
};
```

**V9 plan:** Instead of deriving from conventions, load `resources` from the saved scenario record and use exact names. The derivation functions become fallbacks for scenarios created before V9.

### 11. Frontend graphConstants.ts — Exact Telco-Specific Values

```typescript
export const NODE_COLORS: Record<string, string> = {
  CoreRouter: '#38BDF8', AggSwitch: '#FB923C', BaseStation: '#A78BFA',
  TransportLink: '#3B82F6', MPLSPath: '#C084FC', Service: '#CA8A04',
  SLAPolicy: '#FB7185', BGPSession: '#F472B6',
};
export const NODE_SIZES: Record<string, number> = {
  CoreRouter: 10, AggSwitch: 7, BaseStation: 5, TransportLink: 7,
  MPLSPath: 6, Service: 8, SLAPolicy: 6, BGPSession: 5,
};
```

These are used as last-resort fallback in `useNodeColor.ts` (resolution chain: user override → scenario styles → hardcoded → auto-hash). The auto-hash already handles unknown labels.

**V9 plan:** Keep the fallback chain but empty the hardcoded maps. Scenario-driven styles (`graph_styles` in `scenario.yaml` / `SavedScenario`) already propagate through `ScenarioContext.scenarioNodeColors`. The hardcoded values only matter for backward compatibility with the telco-noc scenario when no `graph_styles` are loaded.

### 12. Stub Agents — Exact Hardcoded Names

From `api/app/routers/alert.py`:

```python
agents = ["TelemetryAgent", "GraphExplorerAgent", "RunbookKBAgent", "HistoricalTicketAgent"]
```

And from `api/app/routers/agents.py`, agent listing returns these stubs when no `agent_ids.json` exists.

**V9 plan:** Stub mode should either read agent names from config, or return a generic "not provisioned" response without scenario-specific names.

### 13. scenario.yaml cosmos section — Exact Structure

```yaml
cosmos:
  gremlin:
    database: networkgraph
    graph: topology
  nosql:
    database: telemetry
    containers:
      - name: AlertStream
        partition_key: /SourceNodeType
        csv_file: AlertStream.csv
        id_field: AlertId
        numeric_fields: [OpticalPowerDbm, BitErrorRate, CPUUtilPct, PacketLossPct]
      - name: LinkTelemetry
        partition_key: /LinkId
        csv_file: LinkTelemetry.csv
        id_field: null
        numeric_fields: [UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs]
```

**V9 plan:** Replace `cosmos:` section with a `data_stores:` section that supports multiple backends:

```yaml
data_stores:
  graph:
    connector: cosmosdb-gremlin
    config:
      database: networkgraph
      graph: topology
  telemetry:
    connector: cosmosdb-nosql
    config:
      database: telemetry
      containers: [...]
```

### 14. Shared Databases — Bicep-Created Pre-Existing Resources

Key architectural constraint from ARCHITECTURE.md: some databases are **shared** and pre-created by Bicep:
- `networkgraph` — shared Gremlin database (all scenarios share this)
- `telemetry` — shared NoSQL database (per-scenario containers within it)
- `prompts` — shared NoSQL database (per-scenario containers within it)
- `scenarios` — shared NoSQL database for scenario metadata
- `interactions` — shared NoSQL database for interaction history

**V9 implication:** The adapter abstraction must respect this pattern. ARM calls only create containers/graphs within shared databases — they don't create databases. If a new backend (Fabric) has different resource creation patterns, the adapter must handle that transparently.

### 15. Search Indexer — Exact Pipeline Structure

From `graph-query-api/search_indexer.py`:

Creates: `data source → index (with vector field + HNSW) → skillset (chunk + embed) → indexer`

Uses:
- `AzureOpenAIEmbeddingSkill` — requires `AI_FOUNDRY_NAME` for vectorizer endpoint
- `SearchIndexerIndexProjection` — chunk projection
- Polls indexer status until complete

**V9 implication:** The search pipeline is backend-agnostic (it operates on Blob → AI Search regardless of graph backend). No adapter changes needed for knowledge files. However, the AI Search connection name (`aisearch-connection`) used by agent tools is hardcoded in the provisioner and must come from config.

### 16. Environment Variables — Complete List for V9 Config

Variables currently scattered across config files that a V9 config should consolidate:

| Variable | Used By | Current Default |
|----------|---------|-----------------|
| `GRAPH_BACKEND` | config.py | `"cosmosdb"` |
| `COSMOS_GREMLIN_ENDPOINT` | config.py, router_ingest.py | `""` |
| `COSMOS_GREMLIN_PRIMARY_KEY` | config.py, router_ingest.py | `""` |
| `COSMOS_GREMLIN_DATABASE` | config.py, router_ingest.py | `"networkgraph"` |
| `COSMOS_GREMLIN_GRAPH` | config.py | `"topology"` |
| `COSMOS_NOSQL_ENDPOINT` | config.py, router_telemetry.py, router_prompts.py | `""` |
| `COSMOS_NOSQL_DATABASE` | config.py | `"telemetry"` |
| `AI_SEARCH_NAME` | config.py, router_ingest.py | `""` |
| `STORAGE_ACCOUNT_NAME` | router_ingest.py | `""` |
| `PROJECT_ENDPOINT` | api config.py | `""` |
| `AI_FOUNDRY_PROJECT_NAME` | api config.py | `""` |
| `AI_FOUNDRY_NAME` | api config.py, search_indexer.py | `""` |
| `MODEL_DEPLOYMENT_NAME` | api config.py | `"gpt-4.1"` |
| `GRAPH_QUERY_API_URI` | api config.py | `""` |
| `CONTAINER_APP_HOSTNAME` | api config.py | `""` |
| `AZURE_SUBSCRIPTION_ID` | router_ingest.py, api config.py | `""` |
| `AZURE_RESOURCE_GROUP` | router_ingest.py, api config.py | `""` |
| `DEFAULT_SCENARIO` | azure_config.env.template | `"telco-noc"` |

**V9 plan:** Env vars remain for cloud/infra settings. Per-scenario settings move to config YAML. Backend connection details can either stay as env vars (shared across scenarios) or be per-connector in config.

### 17. Open Questions for Implementation

1. **Where does the V9 config file live at runtime?** Options:
   - In the `scenarios/` database in Cosmos (alongside scenario metadata)
   - As a YAML file in Blob Storage
   - Embedded as an extended `scenario.yaml` within each data pack
   - The existing `scenario.yaml` already covers data layout + graph styles + cosmos config — is extending it sufficient, or do we need a separate platform-level config?

2. **Adapter registration mechanism**: pip-installable plugins? Simple Python module discovery? A `connectors/` directory with `__init__.py` that auto-registers?

3. **Should telemetry and graph share one adapter, or be separate?** Currently they use different databases and different query languages (Gremlin vs Cosmos SQL). A single "cosmosdb" adapter handling both, or separate `cosmosdb-gremlin` + `cosmosdb-nosql` adapters?

4. **OpenAPI spec generation vs templating**: Generate specs programmatically from adapter metadata (query language, available containers/tables, field descriptions), or use Jinja2-templated YAML files per connector?

5. **Migration strategy for telco-noc prompts**: The `graph_explorer/` composition pattern works well. Should all agents support composition from fragments, or only agents that need connector-specific language sections?

6. **Prompt placeholder expansion**: Currently `{graph_name}` and `{scenario_prefix}`. Need to define the full set of placeholders that config-driven prompts can use, and when expansion happens (upload time vs provisioning time vs both, as currently).