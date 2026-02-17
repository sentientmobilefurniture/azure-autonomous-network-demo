# Complete API Surface

## API Service (`:8000`)

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| POST | `/api/alert` | SSE stream | Submit alert text → orchestrator investigation |
| GET | `/api/agents` | JSON | List provisioned agents (from `agent_ids.json` or stubs) |
| POST | `/api/config/apply` | SSE stream | Re-provision agents (config-driven from scenario.yaml, or legacy 5-agent fallback) |
| GET | `/api/config/current` | JSON | Current active configuration state |
| GET | `/api/config/resources` | JSON | Resource graph for visualization (agents → tools → data sources → infra) |
| GET | `/api/logs` | SSE stream | Real-time log broadcast (fan-out to all clients) |
| POST | `/api/fabric/provision` | SSE stream | Full Fabric provisioning pipeline (Lakehouse + Eventhouse + Ontology) |
| POST | `/api/fabric/provision/lakehouse` | SSE stream | Create/find Fabric Lakehouse |
| POST | `/api/fabric/provision/eventhouse` | SSE stream | Create/find Fabric Eventhouse |
| POST | `/api/fabric/provision/ontology` | SSE stream | Create/find Fabric Ontology |
| GET | `/api/fabric/status` | JSON | Check Fabric provisioned resource status |
| GET | `/health` | JSON `{"status": "ok", "service": "autonomous-network-noc-api"}` | Health check |

## graph-query-api Service (`:8100`)

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| POST | `/query/graph` | JSON | Gremlin query (per-scenario via `X-Graph` header) |
| POST | `/query/telemetry` | JSON | Cosmos SQL query (per-scenario via `X-Graph` header) |
| POST | `/query/topology` | JSON | Graph topology for visualization (via `X-Graph` header) |
| GET | `/query/scenarios` | JSON | List loaded graphs (ARM discovery + fallback Gremlin) |
| DELETE | `/query/scenario/{graph_name}` | JSON | Drop all vertices/edges from a graph |
| GET | `/query/indexes` | JSON | List AI Search indexes (typed: runbooks/tickets/other) |
| GET | `/query/logs` | SSE stream | graph-query-api log stream (`graph-query-api.*` loggers). Reachable via nginx `/query/*` → :8100 routing |
| POST | `/query/upload/graph` | SSE stream | Upload graph tarball → Cosmos Gremlin |
| POST | `/query/upload/telemetry` | SSE stream | Upload telemetry tarball → Cosmos NoSQL |
| POST | `/query/upload/runbooks` | SSE stream | Upload runbooks tarball → Blob + AI Search |
| POST | `/query/upload/tickets` | SSE stream | Upload tickets tarball → Blob + AI Search |
| POST | `/query/upload/prompts` | SSE stream | Upload prompts tarball → Cosmos NoSQL |
| GET | `/query/scenario/config` | JSON | Fetch parsed scenario config from config store |
| GET | `/health` | JSON `{"status":"ok", "service":"graph-query-api", "version":"0.5.0", "graph_backend":"cosmosdb"}` | Health check (includes version + backend type) |
| GET | `/query/prompts` | JSON | List prompts (filter: `?agent=X&scenario=Y`) |
| GET | `/query/prompts/scenarios` | JSON | List distinct scenario names with prompt counts |
| GET | `/query/prompts/{prompt_id}` | JSON | Get specific prompt (requires `?agent=X` for partition key) |
| POST | `/query/prompts` | JSON | Create new prompt (auto-versions) |
| PUT | `/query/prompts/{prompt_id}` | JSON | Update metadata only (content is immutable per version) |
| DELETE | `/query/prompts/{prompt_id}` | JSON | Soft-delete (`deleted=True`, `is_active=False`) |
| GET | `/query/scenarios/saved` | JSON | List all saved scenario records from Cosmos |
| POST | `/query/scenarios/save` | JSON | Upsert scenario metadata document after uploads |
| DELETE | `/query/scenarios/saved/{name}` | JSON | Delete scenario metadata (preserves underlying data) |
| GET | `/query/interactions` | JSON | List past interactions (filter: `?scenario=X&limit=N`) |
| POST | `/query/interactions` | JSON | Save a completed interaction |
| GET | `/query/interactions/{interaction_id}` | JSON | Get a specific interaction |
| DELETE | `/query/interactions/{interaction_id}` | JSON | Delete a specific interaction |
| GET | `/query/fabric/ontologies` | JSON | List Fabric ontologies in workspace |
| GET | `/query/fabric/ontologies/{id}/models` | JSON | List graph models under a Fabric ontology |
| GET | `/query/fabric/eventhouses` | JSON | List Fabric Eventhouses |
| GET | `/query/fabric/kql-databases` | JSON | List KQL databases |
| GET | `/query/fabric/lakehouses` | JSON | List Fabric Lakehouses |
| GET | `/query/fabric/health` | JSON | Check Fabric API connectivity |

## Request/Response Models (`graph-query-api/models.py`)

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
