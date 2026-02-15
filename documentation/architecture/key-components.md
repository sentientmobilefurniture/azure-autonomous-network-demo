# Key Components Detail

## `graph-query-api/config.py` — ScenarioContext & Shared Resources

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
    # Returns cached DefaultAzureCredential instance.
    # IMPORTANT (doc-only note — NOT in code comments): Do NOT use this in
    # asyncio.to_thread() sync functions. Create a fresh DefaultAzureCredential()
    # inside the thread function instead — the shared instance may have an
    # incompatible transport if initialized in the async context.

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

## `graph-query-api/cosmos_helpers.py` — Centralised Cosmos Client & Container Init

Added in the V8 refactor to eliminate duplicated ARM boilerplate across routers.

```python
# --- Cached data-plane CosmosClient singleton ---
_cosmos_client: CosmosClient | None = None
def get_cosmos_client() -> CosmosClient: ...
def close_cosmos_client() -> None: ...

# --- Cached ARM CosmosDBManagementClient singleton ---
_mgmt_client = None
def get_mgmt_client(): ...

# --- Container cache with optional ARM creation ---
_container_cache: dict[tuple[str, str], ContainerProxy] = {}
def get_or_create_container(
    db_name: str,
    container_name: str,
    partition_key_path: str,
    *,
    ensure_created: bool = False,   # False=fast read path, True=ARM create first
) -> ContainerProxy: ...
```

**Consumer pattern** — each router defines a thin domain-specific wrapper:
```python
# In router_prompts.py:
def _get_prompts_container(scenario, *, ensure_created=False):
    return get_or_create_container(f"{scenario}-prompts", "prompts", "/agent",
                                   ensure_created=ensure_created)

# In router_scenarios.py:
def _get_scenarios_container(*, ensure_created=True):
    return get_or_create_container("scenarios", "scenarios", "/id",
                                   ensure_created=ensure_created)
```

## `graph-query-api/sse_helpers.py` — SSE Upload Lifecycle Helper

Added in the V8 refactor to eliminate 5× copy-pasted SSE dispatch scaffolds.

```python
class SSEProgress:
    """Thin wrapper around asyncio.Queue for SSE upload progress."""
    def emit(self, step: str, detail: str, pct: int) -> None: ...
    def complete(self, result: dict) -> None: ...
    def error(self, msg: str) -> None: ...
    def done(self) -> None: ...

def sse_upload_response(
    work_fn: Callable[[SSEProgress], Coroutine],
    error_label: str = "upload",
) -> EventSourceResponse:
    """Standard SSE lifecycle: run work_fn, stream progress/complete/error."""
```

All 5 upload endpoints in `router_ingest.py` use this pattern.

## `graph-query-api/backends/` — Per-Graph Client Cache

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

**graph-query-api has its own SSE log system** (separate from the API's `logs.py`):
- Custom `_SSELogHandler` installed in `main.py`, filters only `graph-query-api.*` loggers
- Ring buffer: `deque(maxlen=100)`, subscriber queues: `maxsize=500`
- Exposed at `GET /query/logs` on port 8100 (routed via nginx `/query/*` → :8100; previously `/api/logs` was shadowed, renamed in V8 refactor)

## `graph-query-api/backends/cosmosdb.py` — CosmosDBGremlinBackend

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

**Telemetry client**: `router_telemetry.py` uses `cosmos_helpers.get_cosmos_client()`
for its `CosmosClient` singleton (migrated from a separate per-module singleton
in the V8 refactor). Also imports `close_cosmos_client` for shutdown cleanup.

## `graph-query-api/router_ingest.py` — Upload + Listing Endpoints

**IMPORTANT CODE ORGANIZATION (post-V8 refactor, ~871 lines):**
- Lines ~1-30: imports (includes `SSEProgress`, `sse_upload_response` from `sse_helpers`, `get_cosmos_client` from `cosmos_helpers`)
- Lines ~30-100: helpers (`_gremlin_client`, `_gremlin_submit`, `_read_csv`, `_ensure_gremlin_graph`, `_extract_tar`, `_resolve_scenario_name`)
- Lines ~100-200: listing endpoints (`GET /query/scenarios`, `DELETE /query/scenario/{name}`, `GET /query/indexes`)
- Lines ~200-560: per-type upload endpoints (`upload_graph`, `upload_telemetry`)
- Lines ~560-700: shared `_upload_knowledge_files()` helper + `upload_runbooks`/`upload_tickets` endpoints
- Lines ~700-871: `upload_prompts` endpoint

**Scenario metadata extraction** (added in minorQOL): During graph upload, after parsing
`scenario.yaml`, the handler extracts `scenario_metadata` dict containing `display_name`,
`description`, `use_cases`, `example_questions`, `graph_styles`, and `domain` from the
manifest. This metadata is included in the SSE `complete` event payload alongside the
standard graph upload results (vertex/edge counts), allowing the frontend to capture
scenario metadata without a separate API call.

All 5 upload endpoints use `sse_upload_response()` from `sse_helpers.py` instead of
inline SSE dispatch scaffolds. Runbooks and tickets share `_upload_knowledge_files()`
parameterised by file type (`.md` vs `.txt`) and type label.

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

## `graph-query-api/router_prompts.py` — Prompts CRUD

Database: Cosmos NoSQL (separate from telemetry). Per-scenario database named `{scenario}-prompts`.
Container: `prompts` with partition key `/agent`.

**Container creation**: `_get_prompts_container(scenario, *, ensure_created=False)`:
1. Delegates to `cosmos_helpers.get_or_create_container()` with db `{scenario}-prompts`, container `prompts`, PK `/agent`
2. Container client cached by `cosmos_helpers._container_cache`

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

## `graph-query-api/router_scenarios.py` — Scenario Metadata CRUD

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

**Container creation**: `_get_scenarios_container(*, ensure_created=True)`:
1. Delegates to `cosmos_helpers.get_or_create_container()` with db `scenarios`, container `scenarios`, PK `/id`
2. Container client cached by `cosmos_helpers._container_cache`

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
  },
  "use_cases": ["Monitor fibre degradation in metro rings", "..."],
  "example_questions": ["What is the root cause of the outage?", "..."],
  "graph_styles": {
    "node_types": {
      "CoreRouter": { "color": "#E74C3C", "size": 12 },
      "AggSwitch": { "color": "#3498DB", "size": 10 }
    }
  },
  "domain": "telecommunications"
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

## `graph-query-api/router_interactions.py` — Interaction History CRUD

Stores past investigation interactions in a dedicated Cosmos NoSQL database: `interactions` / `interactions`.
Partition key: `/scenario`. Each document captures the alert query, agent steps, final diagnosis,
timing, and scenario context so users can browse and replay past investigations.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/query/interactions` | List past interactions (optional `?scenario=X&limit=N` filter) |
| POST | `/query/interactions` | Save a completed interaction |
| GET | `/query/interactions/{interaction_id}` | Get a specific interaction |
| DELETE | `/query/interactions/{interaction_id}` | Delete a specific interaction |

**Container creation**: Uses `cosmos_helpers.get_or_create_container()` with
database `interactions`, container `interactions`, partition key `/scenario`.

**Frontend integration**: `useInteractions` hook auto-saves when an investigation completes
(detects `running` transitioning from `true` → `false` with a non-empty `finalMessage`).
`InteractionSidebar` renders a collapsible right sidebar showing saved interactions as
cards with relative timestamps, scenario badges, and query previews.

## `api/app/orchestrator.py` — Agent Bridge

- `is_configured()`: checks `agent_ids.json` exists + `PROJECT_ENDPOINT` + `AI_FOUNDRY_PROJECT_NAME` set + orchestrator ID present in parsed JSON
- `_get_project_client()`: builds endpoint as `{PROJECT_ENDPOINT.rstrip('/')}/api/projects/{AI_FOUNDRY_PROJECT_NAME}`
- `load_agents_from_file()`: reads `agent_ids.json`, returns list of `{name, id, status}` dicts
- `run_orchestrator(alert_text)`: async generator yielding SSE events via `asyncio.Queue` bridge from sync `AgentEventHandler` running in a daemon thread

**agent_ids.json caching** (V8 refactor): Uses mtime-based cache — `_agent_ids_mtime`
tracks the file's `st_mtime` and only re-reads/parses when the file changes on disk.
This avoids disk I/O on every `/api/alert` request while automatically refreshing
when agents are re-provisioned.

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

## `api/app/routers/config.py` — Agent Provisioning Endpoint

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

## `api/app/routers/logs.py` — Log Broadcasting

- Custom `_SSELogHandler(logging.Handler)` installed on root logger
- Filter: only loggers starting with `app`, `azure`, `uvicorn`
- `_broadcast()`: fan-out to all subscriber queues via `_event_loop.call_soon_threadsafe()`
- `_log_buffer: deque(maxlen=100)`: last 100 records replayed to new SSE connections
- Multiple concurrent clients supported — each gets own `asyncio.Queue(maxsize=500)`

## `graph-query-api/search_indexer.py` — AI Search Pipeline

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
