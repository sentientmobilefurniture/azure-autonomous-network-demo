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
  → ScenarioContext(graph_name="telco-noc-topology",
                    telemetry_database="telco-noc-telemetry")
  → get_backend_for_context(ctx) → cached CosmosDBGremlinBackend per graph
```

Telemetry database derivation: `graph_name.rsplit("-", 1)[0]` → strip last `-*` segment → append `-telemetry`. Falls back to `COSMOS_NOSQL_DATABASE` env var if graph name has no hyphens.

## Prompt Upload — GraphExplorer Composition

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

**Note**: `graph_explorer` is NOT in `PROMPT_AGENT_MAP` — it's handled separately
by composing from the `graph_explorer/` subdirectory in the upload logic.

## Agent Provisioning

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

## AgentProvisioner — What It Creates

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

## Investigation Flow

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
