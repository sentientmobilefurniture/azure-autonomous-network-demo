# Data Flow

## Upload Flow (5 independent paths)

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

## Upload Endpoint Internal Pattern

All upload endpoints use the shared `sse_upload_response()` from `sse_helpers.py`
and accept an optional `scenario_name` query parameter that **overrides** the name
from `scenario.yaml`:

```python
from sse_helpers import SSEProgress, sse_upload_response

@router.post("/upload/{type}")
async def upload_type(file: UploadFile, scenario_name: str | None = Query(default=None)):
    content = await file.read()
    async def work(progress: SSEProgress):
        def _load():               # ← ALL Azure SDK calls happen here (sync)
            # Extract tarball → temp dir
            # Read scenario.yaml for scenario name
            # If scenario_name param provided, OVERRIDE manifest name
            name = scenario_name or manifest["name"]
            # ARM phase (create resources) → Data plane (upsert data)
            progress.emit("phase", "message", 50)
        await asyncio.to_thread(_load)  # ← Critical: must use to_thread
        progress.complete({"scenario": name, ...})  # ← Completion event
    return sse_upload_response(work, error_label="type upload")
```

**Upload endpoint `scenario_name` parameter status:**

| Endpoint | `scenario_name` param | Override behavior |
|----------|----------------------|-------------------|
| `POST /query/upload/graph` | `scenario_name: str \| None = Query(default=None)` | Overrides `scenario.yaml` name; rewrites all resource names via `_rewrite_manifest_prefix()` |
| `POST /query/upload/telemetry` | `scenario_name: str \| None = Query(default=None)` | Overrides `scenario.yaml` name; rewrites all resource names via `_rewrite_manifest_prefix()` |
| `POST /query/upload/runbooks` | `scenario_name: str \| None = Query(default=None)` + legacy `scenario: str = "default"` | `scenario_name` takes priority over `scenario.yaml` over legacy `scenario` param |
| `POST /query/upload/tickets` | `scenario_name: str \| None = Query(default=None)` + legacy `scenario: str = "default"` | Same as runbooks |
| `POST /query/upload/prompts` | `scenario_name: str \| None = Query(default=None)` | Overrides `scenario.yaml` name |

**Manifest prefix rewriting when `scenario_name` is used:** When the override is
provided and differs from the manifest's `name`, both `upload_graph` and
`upload_telemetry` call `_rewrite_manifest_prefix(manifest, scenario_name)` which
rewrites all resource names in the parsed manifest to use the new name:

- **Graph:** `telco-noc-topology` → `telco-noc2-topology` (prefix replacement)
- **Telemetry prefix:** `telco-noc` → `telco-noc2` (container_prefix field)
- **Search indexes:** `telco-noc-runbooks-index` → `telco-noc2-runbooks-index`
- **Manifest name:** Updated to `scenario_name` value

The rewritten manifest is also what gets persisted to `config_store` (if agents
section is present), so query-time config lookups return consistent resource names.
Without this rewriting, the graph would use config values (e.g., `telco-noc-topology`)
while telemetry containers would use the override prefix (`telco-noc2-AlertStream`),
causing query-time lookup failures when `get_scenario_context()` derives the
telemetry prefix from the graph name.

## Manifest Normalization (`_normalize_manifest()`)

`scenario.yaml` supports two formats. `_normalize_manifest()` converts v1.0→v2.0:

| v1.0 (legacy) | v2.0 (current) |
|---|---|
| `cosmos.gremlin.database`, `cosmos.gremlin.graph` | `data_sources.graph.config.database`, `.graph` |
| `cosmos.nosql.database`, `cosmos.nosql.containers[]` | `data_sources.telemetry.config.database`, `.containers[]` |
| `search_indexes[]` (list of objects) | `data_sources.search_indexes` (dict keyed by container name) |

If `data_sources` already exists, returns the manifest as-is. Old-format graph names
that lack the scenario prefix are auto-prefixed (e.g., `topology` → `telco-noc-topology`).

## Manifest Prefix Rewriting (`_rewrite_manifest_prefix()`)

When the user provides a `scenario_name` override that differs from the manifest's
`name` field, `_rewrite_manifest_prefix(manifest, new_name)` rewrites all resource
names in the manifest so that graph, telemetry, search, and saved config all share
a consistent prefix. This is called by both `upload_graph` and `upload_telemetry`
before any resources are created or configs are saved.

The function:
1. Updates `manifest["name"]` to the new name
2. Rewrites `data_sources.graph.config.graph` (e.g., `telco-noc-topology` → `telco-noc2-topology`)
3. Rewrites `data_sources.telemetry.config.container_prefix`
4. Rewrites `data_sources.search_indexes.*.index_name` (prefix replacement)

## Tarball Extraction

`_extract_tar(content, tmppath)`:
- Opens `tarfile.open(fileobj=BytesIO(content), mode="r:gz")`
- Uses `filter="data"` (Python 3.12+ safe extraction)
- Searches for `scenario.yaml` at root then one subdirectory level deep
- Returns the directory containing `scenario.yaml`

## Two-Phase ARM + Data-Plane Pattern

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

## Gremlin Retry Logic

`CosmosDBGremlinBackend._submit_query(query, max_retries=3)`:
- Retries on HTTP 429 (throttling) or 408 (timeout) with exponential backoff (`2^attempt` seconds)
- On `WSServerHandshakeError` (401): raises immediately with helpful error message
- On generic connection error: closes client, sets `self._client = None`, reconnects on next attempt
- All retries wrapped in explicit exception handling per attempt

## Per-Request Graph Routing

Every `/query/*` request can target a different graph via the `X-Graph` header:

```
Frontend → X-Graph: telco-noc-topology → graph-query-api reads header
  → get_scenario_context() (async, V11)
    → Derives scenario prefix: "telco-noc"
    → Looks up config_store for "telco-noc" config
    → Reads data_sources.graph.connector → maps via CONNECTOR_TO_BACKEND
    → Falls back to GRAPH_BACKEND env var if no stored config
  → ScenarioContext(graph_name="telco-noc-topology",
                    telemetry_database="telemetry",
                    telemetry_container_prefix="telco-noc",
                    backend_type="cosmosdb")
  → get_backend_for_context(ctx) → cached CosmosDBGremlinBackend per graph
```

**Fabric path** (V11): For a Fabric-backed scenario:
```
Frontend → X-Graph: telco-noc-fabric-topology → graph-query-api
  → get_scenario_context()
    → config_store lookup → connector="fabric-gql" → backend_type="fabric-gql"
  → ScenarioContext(backend_type="fabric-gql")
  → get_backend_for_context(ctx) → cached FabricGQLBackend
    → POST to Fabric REST API (executeQuery with GQL)
```

Telemetry database: shared `telemetry` database. Container prefix derived from graph name:
`graph_name.rsplit("-", 1)[0]` → strip last `-*` segment → use as container prefix.
Falls back to `COSMOS_NOSQL_DATABASE` env var if graph name has no hyphens.

## Prompt Upload — GraphExplorer Composition

The GraphExplorer agent prompt is special — it's **composed from 3 files**:
- `graph_explorer/core_instructions.md`
- `graph_explorer/core_schema.md`
- `graph_explorer/language_{connector}.md` (connector-specific)

Joined with `\n\n---\n\n` separator.

The language file is selected based on the graph connector type from `scenario.yaml`:
- `connector: "cosmosdb-gremlin"` → `language_gremlin.md` (via `connector.split("-")[-1]`)
- `connector: "fabric-gql"` → `language_gql.md` (via `connector.split("-")[-1]`)
- `connector: "mock"` → `language_mock.md`

**V11 addition**: `language_gql.md` provides ISO GQL query examples (MATCH/RETURN
syntax, relationship traversals, multi-hop patterns) and critical rules
(e.g., "Never use LOWER()" — GQL is case-sensitive).

Other agent prompts map 1:1 via `PROMPT_AGENT_MAP` (legacy hardcoded lookup) or
via `_build_prompt_agent_map_from_config()` (config-driven — maps `agents[].instructions_file`
basename to `agents[].role`). Config-driven mapping takes priority when `agents:`
section exists in the scenario config. Legacy map is kept for backward compatibility:
```python
# Legacy hardcoded prompt-to-agent mapping (backward compatibility).
# Config-driven scenarios use the agents[].instructions_file field instead.
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

## Agent Provisioning

Agents are provisioned via `POST /api/config/apply` which:
1. Receives `{graph, runbooks_index, tickets_index, prompt_scenario}` from frontend
2. Calls `GET http://127.0.0.1:8100/query/prompts?scenario={prefix}&include_content=true` (localhost loopback via `urllib.request`, timeout 30s) to fetch prompts
3. Falls back to minimal placeholder prompts if Cosmos has no prompts for that scenario
4. Imports `AgentProvisioner` from `scripts/agent_provisioner.py` via `sys.path` manipulation
5. **Config-driven path (preferred):** If scenario config in Cosmos has an `agents:` section,
   calls `provisioner.provision_from_config(config, ...)` which:
   - Phase 1: Creates sub-agents (non-orchestrators) with tools built from config
   - Phase 2: Creates orchestrators with `ConnectedAgentTool` referencing created sub-agents
   - Tool building: `openapi` type → loads template YAML from `openapi/templates/`, injects
     connector-specific vars ({base_url}, {graph_name}, {query_language_description}, etc.);
     `azure_ai_search` type → resolves `index_key` from `data_sources.search_indexes`
6. **Legacy fallback:** If no `agents:` section, calls `provisioner.provision_all()`
   (hardcoded 5-agent: GraphExplorer, Telemetry, RunbookKB, HistoricalTicket, Orchestrator)
7. Stores result in memory (`_current_config` protected by `threading.Lock()`) + writes `agent_ids.json`
8. Streams SSE progress events back to frontend

## AgentProvisioner — What It Creates

**Config-driven mode** (`provision_from_config()`): Creates N agents as defined in
`scenario.yaml`'s `agents:` section. Each agent specifies its `name`, `model`, `role`,
`tools[]`, and optionally `connected_agents[]` (for orchestrators). The provisioner
reads OpenAPI spec templates from `openapi/templates/{spec_template}.yaml` and injects
connector-specific variables (`CONNECTOR_OPENAPI_VARS` per backend type: cosmosdb, mock, fabric).

**Legacy mode** (`provision_all()`): Creates 5 hardcoded agents:

| # | Agent | Tool Type | Tool Config |
|---|-------|-----------|-------------|
| 1 | GraphExplorerAgent | `OpenApiTool` | Spec filtered to `/query/graph` only, anonymous auth |
| 2 | TelemetryAgent | `OpenApiTool` | Spec filtered to `/query/telemetry` only, anonymous auth |
| 3 | RunbookKBAgent | `AzureAISearchTool` | `query_type=SEMANTIC`, `top_k=5` |
| 4 | HistoricalTicketAgent | `AzureAISearchTool` | Same pattern as RunbookKB |
| 5 | Orchestrator | `ConnectedAgentTool` (×4) | References all 4 sub-agents by ID |

**OpenAPI spec templates** (`openapi/templates/`): Templates use placeholders like
`{base_url}`, `{graph_name}`, `{query_language_description}`, `{telemetry_database}`,
`{container_prefix}`. At provisioning time, the provisioner does `raw.replace()`
to inject the actual values for the current scenario + graph backend combination.

**Legacy OpenAPI spec loading**: Falls back to `graph-query-api/openapi/{cosmosdb|mock}.yaml`
when not using config-driven provisioning.

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

## Investigation Flow

```
User pastes alert → POST /api/alert {text: "..."}
  → orchestrator.py checks is_configured() (agent_ids.json + env vars)
  → If not configured: returns stub SSE events (fake steps + stub message)
  → If configured:
      → Creates thread + run via azure-ai-agents SDK
      → SSEEventHandler bridges sync callbacks → async queue → SSE stream
      → Orchestrator delegates to sub-agents via ConnectedAgentTool:
          (agents are defined by scenario.yaml config — example for telco-noc:)
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
