# V3 Graph Architecture: Neo4j Integration Plan

## Motivation

Fabric GraphModel on F8 SKU cannot sustain 3 concurrent agent GQL calls without
capacity exhaustion. The F8 crashed and auto-paused during a demo run. Scaling to
F16+ costs significantly more and doesn't address the real opportunity: **live
graph manipulation in the UI** — adding/removing nodes, triggering faults,
visualizing topology changes in real time — which Fabric GraphModel doesn't
support at all (it's a read-only query surface over Lakehouse tables).

Neo4j Community Edition is free, runs in a Docker container, supports read AND
write via Cypher (which is nearly identical to GQL/ISO), has mature visualization
libraries, and handles concurrent queries from a single container without breaking
a sweat.

### Positioning

> "In production you'd use Microsoft Fabric for petabyte-scale telemetry and
> graph analytics. For this demo we use Neo4j to show real-time graph
> manipulation and interactive visualization — the kind of thing that makes
> a graph database tangible."

This is not anti-Fabric. It's complementary. The demo still uses Fabric
Eventhouse for KQL telemetry queries. The graph portion moves to Neo4j because
it unlocks capabilities that Fabric can't provide today (mutations, subscriptions,
interactive viz).

---

## Current Architecture (V2)

```
Foundry Agent (GraphExplorerAgent)
  └─ OpenApiTool → POST graph-query-api/query/graph
                      └─ GQL → Fabric GraphModel REST API
                                 └─ Read-only query over Lakehouse CSVs
```

Key constraints of V2:
- **Read-only**: Cannot modify the graph at runtime
- **Capacity-bound**: F8 SKU shares CUs across all Fabric workloads
- **No visualization**: Graph data is returned as JSON rows, no spatial layout
- **No subscriptions**: No way to push graph changes to the UI
- **Cold start**: GraphModel needs to warm up after idle periods

---

## Proposed Architecture (V3)

```
                                    ┌──────────────────────────────────┐
                                    │  Neo4j Container App             │
                                    │  (Community Edition, Bolt 7687)  │
                                    │  Volume: /data (persistent)      │
                                    └──────────┬─────┬─────────────────┘
                                               │     │
                          Bolt (neo4j driver)  │     │  HTTP 7474 (browser)
                                               │     │
     ┌─────────────────────────────────────────┘     └──────── (optional: Neo4j Browser)
     │
     ▼
┌────────────────────┐
│  graph-query-api   │  ← renamed from graph-query-api
│  Container App     │     (or: graph-query-api with graph backend swap)
│  POST /query/graph │
│  POST /query/telem │  ← still hits Fabric Eventhouse (no change)
│  POST /graph/mutate│  ← NEW: write operations
│  GET  /graph/viz   │  ← NEW: full topology for visualization
│  WS   /graph/live  │  ← NEW: WebSocket for real-time updates (stretch)
└─────────┬──────────┘
          │
          │ OpenApiTool (same pattern as V2)
          ▼
  Foundry Agents (unchanged)
```

### What changes, what stays

| Component | V2 (Fabric) | V3 (Neo4j) | Change? |
|-----------|-------------|------------|---------|
| **TelemetryAgent** | OpenApiTool → /query/telemetry → Kusto SDK | Same | **No change** |
| **RunbookKBAgent** | AzureAISearchTool | Same | **No change** |
| **HistoricalTicketAgent** | AzureAISearchTool | Same | **No change** |
| **GraphExplorerAgent** | OpenApiTool → /query/graph → Fabric GQL | OpenApiTool → /query/graph → Neo4j Cypher | **Backend swap only** |
| **Orchestrator** | ConnectedAgentTool to 4 sub-agents | Same | **No change** |
| **graph-query-api** | FastAPI + Fabric REST API | FastAPI + neo4j Python driver | **Backend swap** |
| **OpenAPI spec** | GQL semantics in description | Cypher semantics in description | **Spec update** |
| **Data loading** | CSVs → Fabric Lakehouse → Ontology | CSVs → Cypher CREATE/MERGE | **New script** |
| **Frontend** | No graph viz | React Flow live topology | **New feature** |

### The critical insight: the API contract doesn't change

The agents don't know or care whether `/query/graph` talks to Fabric or Neo4j.
They send a query string and get back `{columns, data}`. The OpenAPI spec can
stay almost identical — just update the `description` field to say "Cypher" instead
of "GQL" and update the query examples.

This means:
- `provision_agents.py` works with minimal changes (spec description updates)
- `agent_ids.json` stays the same (agents aren't recreated unless prompts change)
- The orchestrator, backend API, and SSE streaming are completely untouched

---

## Implementation Plan

### Phase 1: Neo4j Container App (Core Swap)

**Goal**: Replace Fabric GraphModel with Neo4j as the graph backend. No new
features — just swap the data source and verify agents still work.

#### 1.1 Deploy Neo4j as a Container App

Neo4j Community Edition Docker image: `neo4j:2026.01-community` (free, no license).

**Option A: Dedicated Container App (recommended)**

Deploy Neo4j as a separate Container App in the same managed environment.
Advantages: independent scaling, persistent volume, Bolt port exposure.

```
# Bicep: modules/neo4j.bicep
resource neo4j 'Microsoft.App/containerApps@2024-03-01' = {
  properties: {
    template: {
      containers: [{
        name: 'neo4j'
        image: 'neo4j:2026.01-community'
        env: [
          { name: 'NEO4J_AUTH', value: 'neo4j/${neo4jPassword}' }
          { name: 'NEO4J_PLUGINS', value: '["apoc"]' }
        ]
        resources: { cpu: 1, memory: '2Gi' }
        volumeMounts: [{ volumeName: 'neo4j-data', mountPath: '/data' }]
      }]
      volumes: [{ name: 'neo4j-data', storageType: 'AzureFile', storageName: '...' }]
    }
    configuration: {
      ingress: {
        external: false  // internal only — graph-query-api talks to it
        targetPort: 7687  // Bolt protocol
      }
    }
  }
}
```

Considerations:
- **Persistent storage**: Azure Files volume mount for `/data` (graph survives restarts)
- **Internal ingress**: Only `graph-query-api` needs to reach Neo4j (Bolt 7687)
- **No public exposure**: Security — Neo4j Browser (7474) only exposed in dev
- **APOC plugin**: Useful for path algorithms, data loading, export

**Option B: Sidecar in graph-query-api Container App**

Run Neo4j as a sidecar container alongside the FastAPI app. Simpler but couples
the lifecycle and shares resources (CPU/memory).

**Recommendation**: Option A. Keep Neo4j independent. It has different resource
needs (memory for page cache) and different lifecycle (data persists across
code deploys).

#### 1.2 Adapt graph-query-api

Replace the Fabric GQL execution path with Neo4j's Python driver:

```python
# Before (V2 — Fabric)
import httpx
result = await client.post(fabric_url, json={"query": gql_query})

# After (V3 — Neo4j)
from neo4j import AsyncGraphDatabase

async with driver.session(database="neo4j") as session:
    result = await session.run(cypher_query)
    records = [record.data() async for record in result]
```

Key changes in `main.py`:

| Area | V2 | V3 |
|------|----|----|
| Import | `httpx` | `neo4j` (async driver) |
| Connection | `DefaultAzureCredential` → Fabric REST | `AsyncGraphDatabase.driver(bolt_uri, auth=(...))` |
| Query execution | HTTP POST → GQL | Bolt session → Cypher |
| Response shape | Already `{columns, data}` | Transform `Record.data()` → same shape |
| Auth | Managed identity (OAuth token) | Username/password (from env var / Key Vault) |
| Retry logic | 429 rate-limit retry | Not needed (Neo4j handles concurrency) |

Dependencies change:
```toml
# pyproject.toml — remove requests, add neo4j
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "httpx>=0.28.0",              # still needed for health checks etc
    "neo4j>=5.26.0",              # Neo4j async Python driver
    "azure-identity>=1.19.0",    # still needed for Kusto (telemetry)
    "azure-kusto-data>=4.6.0",   # telemetry endpoint unchanged
]
```

**Interface contract preservation**: The response format `{columns, data}` stays
identical. Agents see no difference:

```python
# V2 return from Fabric
{"columns": [{"name": "RouterId", "type": "string"}], "data": [{"RouterId": "CORE-SYD-01"}]}

# V3 return from Neo4j (same shape)
{"columns": [{"name": "RouterId", "type": "string"}], "data": [{"RouterId": "CORE-SYD-01"}]}
```

#### 1.3 Query language mapping: GQL → Cypher

The graph agents' prompts currently instruct them to write GQL. GQL (ISO/IEC
39075) is heavily Cypher-derived, so the mapping is nearly 1:1:

| GQL (current) | Cypher (Neo4j) | Notes |
|---------------|----------------|-------|
| `MATCH (r:CoreRouter)` | `MATCH (r:CoreRouter)` | Identical |
| `WHERE r.RouterId = "X"` | `WHERE r.RouterId = "X"` | Identical |
| `RETURN r.RouterId, r.City` | `RETURN r.RouterId, r.City` | Identical |
| `(a)-[:routes_via]->(b)` | `(a)-[:routes_via]->(b)` | Identical |
| `LIMIT 10` | `LIMIT 10` | Identical |

Differences that matter:
- GQL uses `GRAPH` clause for graph selection — not needed in Neo4j (one DB)
- GQL has some ISO syntax sugar not in Cypher — unlikely in our simple queries
- Neo4j supports `OPTIONAL MATCH`, `CREATE`, `MERGE`, `DELETE` — GQL doesn't

**Action**: Update `GraphExplorerAgent` system prompt to say "Cypher" instead of
"GQL" and add examples of write operations for V3 Phase 2.

#### 1.4 Data loading script

New script: `scripts/provision_neo4j.py`

Load the same CSVs into Neo4j that currently go into Fabric Lakehouse:

```python
from neo4j import GraphDatabase

def load_graph(driver):
    with driver.session() as session:
        # Nodes
        session.run("""
            LOAD CSV WITH HEADERS FROM 'file:///DimCoreRouter.csv' AS row
            CREATE (r:CoreRouter {
                RouterId: row.RouterId, City: row.City,
                Region: row.Region, Vendor: row.Vendor, Model: row.Model
            })
        """)
        # ... repeat for all Dim* tables

        # Relationships from Fact tables
        session.run("""
            LOAD CSV WITH HEADERS FROM 'file:///FactServiceDependency.csv' AS row
            MATCH (s:Service {ServiceId: row.ServiceId})
            MATCH (d {ServiceId: row.DependsOnId})  // polymorphic
            CREATE (s)-[:DEPENDS_ON {strength: row.DependencyStrength}]->(d)
        """)
```

Alternatively, use the neo4j Python driver's `execute_query()` to load via
parameterized Cypher (more portable than `LOAD CSV` which requires file access).

#### 1.5 Config changes

New env vars in `azure_config.env`:

```bash
# --- Neo4j (V3 graph backend) ---
NEO4J_BOLT_URI=bolt://neo4j-container:7687      # internal Container App DNS
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<from-key-vault-or-env>
GRAPH_BACKEND=neo4j                              # or "fabric" — feature flag
```

The `GRAPH_BACKEND` flag allows dual-mode: graph-query-api checks this at
startup and configures either the Fabric GQL path or the Neo4j Cypher path.
This is the cleanest way to avoid a hard fork while transitioning.

#### 1.6 Bicep changes

```
infra/modules/neo4j.bicep               # NEW: Neo4j Container App
infra/modules/azure-files-share.bicep   # NEW: persistent volume for Neo4j /data
infra/main.bicep                        # Add neo4j module, output NEO4J_BOLT_URI
```

---

### Phase 2: Graph Mutations (Interactive Demo)

**Goal**: Allow the UI to modify the graph in real time — add/remove nodes,
simulate faults, trigger cascading failures.

#### 2.1 New API endpoints

Add to graph-query-api:

```
POST /graph/mutate     — Execute a write Cypher query (CREATE/MERGE/DELETE)
GET  /graph/topology   — Return full graph as nodes+edges for visualization
POST /graph/reset      — Reload graph from CSVs (reset to clean state)
POST /graph/fault      — Inject a predefined fault scenario
```

The `/graph/topology` endpoint returns data shaped for React Flow:

```json
{
  "nodes": [
    {"id": "CORE-SYD-01", "type": "CoreRouter", "data": {"City": "Sydney", ...}, "position": {"x": 100, "y": 200}},
    ...
  ],
  "edges": [
    {"id": "e1", "source": "CORE-SYD-01", "target": "CORE-MEL-01", "type": "TransportLink", "data": {"CapacityGbps": 100}},
    ...
  ]
}
```

#### 2.2 Fault injection scenarios

Predefined scenarios stored as Cypher templates:

```yaml
# data/fault-scenarios.yaml
scenarios:
  - id: link_down
    name: "Transport Link Failure"
    description: "Simulate a fibre cut between two cities"
    params: [link_id]
    cypher: |
      MATCH (l:TransportLink {LinkId: $link_id})
      SET l.Status = 'DOWN', l.DownSince = datetime()

  - id: router_overload
    name: "Core Router Overload"
    params: [router_id]
    cypher: |
      MATCH (r:CoreRouter {RouterId: $router_id})
      SET r.Status = 'DEGRADED', r.CPUPercent = 98

  - id: bgp_flap
    name: "BGP Session Flap"
    params: [session_id]
    cypher: |
      MATCH (b:BGPSession {SessionId: $session_id})
      SET b.Status = 'FLAPPING', b.FlapCount = b.FlapCount + 1
```

The UI renders these as a dropdown/palette. Clicking one injects the fault into
Neo4j, then triggers the alert → orchestrator → agent pipeline to diagnose it.

#### 2.3 React Flow visualization

Using `@xyflow/react` (per `react-flow-node-ts` skill reference):

```tsx
import { ReactFlow, Node, Edge, useNodesState, useEdgesState } from '@xyflow/react';

// Custom node types for each entity
const nodeTypes = {
  CoreRouter: CoreRouterNode,
  TransportLink: TransportLinkNode,
  Service: ServiceNode,
  // ...
};
```

Layout: Use `dagre` or `elkjs` for automatic hierarchical layout of the network
topology. Each node type gets a distinct visual treatment (icon, color, shape).

Status updates: When an agent identifies a faulty component, the UI can highlight
that node in the graph (red border, pulse animation).

---

### Phase 3: Real-Time Updates (Stretch Goal)

**Goal**: Push graph state changes to the UI without polling.

Options:
1. **WebSocket on graph-query-api** — FastAPI WebSocket endpoint, push on mutation
2. **Azure Web PubSub** — Managed WebSocket service (skills reference available
   for both Python and TypeScript SDKs)
3. **SSE on /graph/live** — Simpler than WebSocket, reuse existing SSE infra

Recommendation: Start with **SSE** (we already have the infrastructure). If
bi-directional communication is needed later, upgrade to Web PubSub.

---

## Dual-Mode Strategy: Keeping Fabric Support

The cleanest way to avoid a hard fork is a **backend strategy pattern** in
graph-query-api. This section provides the detailed design for dual-mode
operation, including code separation, prompt composition, and caveats.

### Backend Strategy Pattern

```python
# backends/base.py

from typing import Protocol

class GraphBackend(Protocol):
    """Interface for graph query execution. Both Neo4j and Fabric implement this."""

    async def query(self, query_string: str, params: dict | None = None) -> dict:
        """Execute a read query. Returns {columns: [...], data: [...]}."""
        ...

    async def mutate(self, query_string: str, params: dict | None = None) -> dict:
        """Execute a write query. Neo4j only; Fabric raises 501."""
        ...

    async def topology(self) -> dict:
        """Return full graph as {nodes: [...], edges: [...]}. Neo4j only."""
        ...

    async def health(self) -> dict:
        """Check backend connectivity."""
        ...
```

```python
# backends/neo4j.py

from neo4j import AsyncGraphDatabase

class Neo4jBackend:
    def __init__(self, bolt_uri: str, username: str, password: str):
        self._driver = AsyncGraphDatabase.driver(bolt_uri, auth=(username, password))

    async def query(self, query_string: str, params: dict | None = None) -> dict:
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(query_string, params or {})
            records = [record.data() async for record in result]
            columns = list(records[0].keys()) if records else []
            return {
                "columns": [{"name": c, "type": "string"} for c in columns],
                "data": records,
            }

    async def mutate(self, query_string: str, params: dict | None = None) -> dict:
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(query_string, params or {})
            summary = await result.consume()
            return {
                "nodes_created": summary.counters.nodes_created,
                "relationships_created": summary.counters.relationships_created,
                "properties_set": summary.counters.properties_set,
            }

    async def topology(self) -> dict:
        """Return the full graph as nodes + edges for React Flow visualization."""
        async with self._driver.session(database="neo4j") as session:
            # Fetch all nodes
            node_result = await session.run(
                "MATCH (n) RETURN labels(n)[0] AS type, properties(n) AS props, elementId(n) AS id"
            )
            nodes = []
            async for record in node_result:
                data = record.data()
                nodes.append({
                    "id": data["props"].get(self._primary_key(data["type"]), data["id"]),
                    "type": data["type"],
                    "data": data["props"],
                })

            # Fetch all relationships
            edge_result = await session.run(
                "MATCH (a)-[r]->(b) RETURN type(r) AS type, properties(a) AS source_props, "
                "labels(a)[0] AS source_type, properties(b) AS target_props, labels(b)[0] AS target_type, "
                "properties(r) AS rel_props"
            )
            edges = []
            async for record in edge_result:
                data = record.data()
                edges.append({
                    "source": data["source_props"].get(self._primary_key(data["source_type"])),
                    "target": data["target_props"].get(self._primary_key(data["target_type"])),
                    "type": data["type"],
                    "data": data["rel_props"],
                })
            return {"nodes": nodes, "edges": edges}

    async def health(self) -> dict:
        try:
            await self._driver.verify_connectivity()
            return {"status": "ok", "backend": "neo4j"}
        except Exception as e:
            return {"status": "error", "backend": "neo4j", "detail": str(e)}

    @staticmethod
    def _primary_key(label: str) -> str:
        """Map Neo4j label to its primary key property name."""
        return {
            "CoreRouter": "RouterId", "AggSwitch": "SwitchId",
            "BaseStation": "StationId", "TransportLink": "LinkId",
            "MPLSPath": "PathId", "Service": "ServiceId",
            "SLAPolicy": "SLAPolicyId", "BGPSession": "SessionId",
        }.get(label, "id")
```

```python
# backends/fabric.py

from fastapi import HTTPException

class FabricBackend:
    def __init__(self, credential, workspace_id: str, graph_model_id: str):
        self._credential = credential
        self._workspace_id = workspace_id
        self._graph_model_id = graph_model_id
        # httpx.AsyncClient for GQL, same as current main.py

    async def query(self, query_string: str, params: dict | None = None) -> dict:
        # Current GQL execution path (httpx → Fabric REST API)
        ...

    async def mutate(self, query_string: str, params: dict | None = None) -> dict:
        raise HTTPException(501, "Fabric GraphModel is read-only — mutations require Neo4j backend")

    async def topology(self) -> dict:
        raise HTTPException(501, "Topology visualization not supported on Fabric backend")

    async def health(self) -> dict:
        # Token acquisition + Fabric API health check
        ...
```

```python
# main.py (startup — backend selection)

from backends.neo4j import Neo4jBackend
from backends.fabric import FabricBackend

@asynccontextmanager
async def lifespan(app: FastAPI):
    backend_type = os.getenv("GRAPH_BACKEND", "fabric")
    if backend_type == "neo4j":
        app.state.graph = Neo4jBackend(
            bolt_uri=os.environ["NEO4J_BOLT_URI"],
            username=os.environ["NEO4J_USERNAME"],
            password=os.environ["NEO4J_PASSWORD"],
        )
    else:
        app.state.graph = FabricBackend(
            credential=DefaultAzureCredential(),
            workspace_id=os.environ["FABRIC_WORKSPACE_ID"],
            graph_model_id=os.environ["FABRIC_GRAPH_MODEL_ID"],
        )
    # Telemetry (KQL) client is always Fabric Eventhouse — unaffected
    app.state.kusto = KustoClient(...)
    yield

@app.post("/query/graph")
async def query_graph(request: Request, body: QueryRequest):
    return await request.app.state.graph.query(body.query)
```

### Code Separation Architecture

The current `graph-query-api/` is a single `main.py` monolith. Dual-mode
requires clean separation:

```
graph-query-api/                   (consider renaming to graph-query-api/)
├── main.py                         # FastAPI app, routes, lifespan — GENERIC
├── config.py                       # Env var loading, backend selection logic
├── models.py                       # Pydantic: QueryRequest, QueryResponse, TopologyResponse
├── backends/
│   ├── __init__.py                 # re-exports GraphBackend protocol
│   ├── base.py                     # GraphBackend Protocol definition
│   ├── neo4j.py                    # Neo4jBackend implementation
│   └── fabric.py                   # FabricBackend implementation
├── telemetry/
│   ├── __init__.py
│   └── kusto.py                    # KQL execution (always Fabric Eventhouse)
├── openapi.yaml                    # Shared spec — query endpoint descriptions
├── pyproject.toml
├── Dockerfile
└── uv.lock
```

**Separation rules:**
- `backends/` contains ONLY graph-backend-specific code. No framework imports (FastAPI, Pydantic) except in type hints.
- `telemetry/` is always Fabric Eventhouse. It never touches the graph backend.
- `main.py` imports from `backends/` and `telemetry/` but never contains backend-specific logic.
- `config.py` reads env vars and returns typed config objects. No I/O.
- `models.py` defines Pydantic request/response models used by routes.

**What goes where:**

| Concern | File | Notes |
|---------|------|-------|
| `AsyncGraphDatabase.driver()` | `backends/neo4j.py` | Only imports `neo4j` package |
| `httpx.AsyncClient` for Fabric GQL | `backends/fabric.py` | Only imports `httpx`, `azure-identity` |
| `KustoClient` for KQL | `telemetry/kusto.py` | Always Fabric Eventhouse |
| Route definitions (`@app.post`) | `main.py` | Delegates to `app.state.graph` |
| `GRAPH_BACKEND` env var reading | `config.py` | Returns enum, not backend instance |
| Response shape validation | `models.py` | Shared across backends |

### Prompt Composition: OntologyCore + LanguageCore

The GraphExplorerAgent's system prompt is currently a single 300+ line document
containing both domain knowledge (entity types, relationships, instances) and
query language instructions (GQL syntax, examples, critical rules). For dual-mode,
we split this into two composable layers:

#### Why Split?

The entity model is identical regardless of backend:
- "CoreRouter has properties RouterId, City, Region, Vendor, Model" — true for both Fabric and Neo4j
- "TransportLink connects two CoreRouters" — true for both
- "Service depends on MPLSPath, AggSwitch, or BaseStation" — true for both

The query language differs (slightly):
- GQL: `MATCH (r:CoreRouter) WHERE r.RouterId = "CORE-SYD-01" RETURN r.City`
- Cypher: `MATCH (r:CoreRouter) WHERE r.RouterId = "CORE-SYD-01" RETURN r.City`
- (These are actually identical for simple queries — but the critical rules,
  error patterns, and advanced syntax diverge)

#### File Structure

```
data/prompts/
├── ontology_core.md                      # Entity types, properties, instances, relationships
├── language_gql.md                       # GQL query patterns, syntax rules, examples
├── language_cypher.md                    # Cypher query patterns, syntax rules, examples
├── foundry_graph_explorer_agent.md       # Role paragraph + agent description (header/footer)
├── foundry_orchestrator_agent.md         # Unchanged — backend-agnostic
├── foundry_telemetry_agent_v2.md         # Unchanged
├── foundry_runbook_kb_agent.md           # Unchanged
├── foundry_historical_ticket_agent.md    # Unchanged
└── alert_storm.md                        # Unchanged
```

#### What Goes in OntologyCore

Everything that describes **what the network looks like** — backend-agnostic:

```markdown
# OntologyCore — Network Topology Schema

## Entity Types — Full Schema

### CoreRouter (3 instances)
Backbone routers at city level. Each city has one core router.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **RouterId** | String | **Primary key.** | `CORE-SYD-01` |
| City | String | City where the router is located. | `Sydney` |
...

### TransportLink (10 instances)
...

## Relationships

| Source | Relationship | Target | Meaning |
|--------|-------------|--------|---------|
| TransportLink | connects | CoreRouter | Physical fibre connects two routers |
| AggSwitch | aggregates_to | CoreRouter | Switch uplinks to a backbone router |
...

## All Entity Instances
(Full tables of all instances — same as current prompt)

## Semantic Rules
1. **Always ask for ALL affected entities.** When tracing blast radius...
2. **If a query returns an error, read the error message and fix the query.**
3. **Use exact entity IDs with correct casing.** IDs are uppercase with hyphens.
```

#### What Goes in LanguageCore (GQL variant)

Everything about **how to write queries** in GQL:

```markdown
# LanguageCore — GQL (Graph Query Language)

## Query Syntax

You construct GQL queries using ISO GQL syntax. The tool `query_graph` executes
your query against the graph.

## Critical Syntax Rules

1. **Never wrap filter values in LOWER()**. Entity IDs are case-sensitive.
2. **Use MATCH-WHERE-RETURN pattern**: `MATCH (n:Label) WHERE n.Prop = "val" RETURN n.Prop`
3. **Relationship traversal**: `(a)-[:REL_TYPE]->(b)`

## Single-Hop Examples
MATCH (r:CoreRouter) WHERE r.City = "Sydney" RETURN r.RouterId, r.Vendor, r.Model

## 2-Hop Blast Radius
MATCH (t:TransportLink {LinkId: "LINK-SYD-MEL-FIBRE-01"})<-[:routes_via]-(p:MPLSPath)<-[:depends_on]-(s:Service)
RETURN p.PathId, s.ServiceId, s.CustomerName

## 3-Hop with SLA Exposure
...
```

#### What Goes in LanguageCore (Cypher variant)

```markdown
# LanguageCore — Cypher (Neo4j)

## Query Syntax

You construct Cypher queries to read and write the graph. The tool `query_graph`
executes your query against Neo4j.

## Critical Syntax Rules

1. **Case-sensitive property matching**: `WHERE n.RouterId = "CORE-SYD-01"` (exact match)
2. **MATCH-WHERE-RETURN pattern**: Same as GQL
3. **Relationship traversal**: `(a)-[:REL_TYPE]->(b)` — identical to GQL
4. **OPTIONAL MATCH**: Use when a relationship might not exist
5. **Write operations**: `CREATE`, `MERGE`, `SET`, `DELETE` — available in Neo4j

## Single-Hop Examples
MATCH (r:CoreRouter) WHERE r.City = "Sydney" RETURN r.RouterId, r.Vendor, r.Model

## 2-Hop Blast Radius
MATCH (t:TransportLink {LinkId: "LINK-SYD-MEL-FIBRE-01"})<-[:ROUTES_VIA]-(p:MPLSPath)<-[:DEPENDS_ON]-(s:Service)
RETURN p.PathId, s.ServiceId, s.CustomerName

## Write Operations (Phase 2)
// Mark a link as down
MATCH (t:TransportLink {LinkId: $link_id})
SET t.Status = "DOWN", t.DownSince = datetime()
RETURN t.LinkId, t.Status

## 3-Hop with SLA Exposure
...
```

#### Composition at Provisioning Time

The `provision_agents.py` script composes the full prompt:

```python
# In provision_agents.py

GRAPH_BACKEND = os.getenv("GRAPH_BACKEND", "fabric")
language_file = "language_cypher.md" if GRAPH_BACKEND == "neo4j" else "language_gql.md"

ontology = (PROMPTS_DIR / "ontology_core.md").read_text()
language = (PROMPTS_DIR / language_file).read_text()
header = (PROMPTS_DIR / "foundry_graph_explorer_agent.md").read_text()

# Compose: header (role description) + ontology (schema) + language (syntax)
graph_explorer_prompt = f"{header}\n\n{ontology}\n\n{language}"

# Create or update the agent with the composed prompt
agents_client.agents.create_agent(
    model=MODEL_ID,
    name="GraphExplorerAgent",
    instructions=graph_explorer_prompt,
    ...
)
```

#### Evaluation: Does this split make sense?

**Yes, strongly recommended.** The analysis of the current prompt reveals a
clean, natural boundary:

| Current Section | Destination | Rationale |
|----------------|-------------|-----------|
| Role description ("You are a network topology...") | `foundry_graph_explorer_agent.md` | Agent identity, backend-agnostic |
| How you work ("construct a GQL query...") | `language_*.md` | Language-specific instruction |
| Critical rules 1-3 (LOWER(), casing, patterns) | `language_*.md` | Syntax-specific rules |
| Critical rules 4-5 (retry on error, all entities) | `ontology_core.md` | Behavior rules, backend-agnostic |
| Entity Types — Full Schema (all 8 types) | `ontology_core.md` | Pure domain knowledge |
| All instances tables | `ontology_core.md` | Data, not syntax |
| Relationships — schema and meaning | `ontology_core.md` | Domain semantics |
| Relationship GQL examples | `language_gql.md` | Query syntax examples |
| Common Multi-Hop Query Patterns | `language_*.md` | Syntax-specific examples |
| Foundry Agent Description | `foundry_graph_explorer_agent.md` | Agent metadata |

**The split creates exactly ONE file that changes between backends**:
`language_gql.md` → `language_cypher.md`. Everything else stays constant.

**Trade-off: maintenance burden**. When adding a new entity type:
1. Add to `ontology_core.md` (once)
2. Add query examples to BOTH `language_gql.md` AND `language_cypher.md`

This is slightly more work than a single file, but it makes the change set
explicit. You KNOW what needs updating. With a monolithic prompt, it's easy
to update the schema but forget to update the GQL examples for the new entity.

**Future extensibility**: If a third backend appears (e.g., CosmosDB Gremlin,
Amazon Neptune SPARQL), you add a single `language_gremlin.md` file. The
ontology and agent identity are reused unchanged.

### Caveats and Risks

#### 1. Prompt size growth

The current GraphExplorerAgent prompt is ~300 lines. With composition, the
resulting prompt is the same size (header ~20 lines + ontology ~200 lines +
language ~100 lines ≈ 320 lines). No meaningful growth. But: if the ontology
gets larger (more entity types, more instances), the composed prompt grows
linearly. Monitor total token count.

#### 2. Agent must be re-provisioned on backend switch

The GraphExplorerAgent's system prompt is set at creation time. You cannot
hot-swap the prompt at runtime. Switching from Fabric to Neo4j requires:
1. Change `GRAPH_BACKEND=neo4j` in env
2. Re-run `provision_agents.py` (which will `create_or_update` the agent
   with the new composed prompt)
3. The orchestrator's ConnectedAgentTool reference stays the same (same agent ID)

This means you cannot run both backends simultaneously with the same agent set.
If simultaneous dual-mode is needed, you'd need two GraphExplorerAgent instances
and swap the orchestrator's ConnectedAgentTool reference — doable but adds
complexity.

#### 3. GQL ≈ Cypher but not identical

For our simple ontology queries, GQL and Cypher are 95%+ identical. But:

| Feature | GQL (ISO) | Cypher (Neo4j) | Relevance |
|---------|-----------|----------------|-----------|
| Graph selection | `GRAPH myGraph MATCH...` | Not needed (single DB) | Low — we don't use it |
| OPTIONAL MATCH | Not in standard | Supported | Medium — useful for blast radius |
| CREATE/MERGE/SET/DELETE | Not supported | Full support | High — Phase 2 mutations |
| Path functions | `ALL_SHORTEST_PATHS` | `shortestPath()`, APOC | Medium — path analysis |
| Relationship labels | lowercase convention | UPPER_SNAKE_CASE convention | Low — style choice |

The LanguageCore files should document these differences explicitly so the LLM
doesn't accidentally use a GQL-only or Cypher-only feature in the wrong context.

#### 4. Testing both paths

Both backends must be tested against the same set of expected queries. A test
matrix:

```
test_graph_queries.py
  ├── test_single_hop_router_lookup          # must pass on both backends
  ├── test_2hop_blast_radius                 # must pass on both
  ├── test_3hop_sla_exposure                 # must pass on both
  ├── test_mutation_link_down                # Neo4j only (Fabric raises 501)
  ├── test_topology_full_graph               # Neo4j only (Fabric raises 501)
  └── test_health_check                      # must pass on both
```

Use `pytest.mark.parametrize` or a fixture that creates both backends:

```python
@pytest.fixture(params=["neo4j", "fabric"])
def backend(request):
    if request.param == "neo4j":
        return Neo4jBackend(...)
    else:
        return FabricBackend(...)
```

#### 5. Relationship type naming convention

GQL prompts currently use `lowercase_snake_case` for relationship types
(`routes_via`, `depends_on`). Neo4j convention is `UPPER_SNAKE_CASE`
(`ROUTES_VIA`, `DEPENDS_ON`). Decision needed:

- **Option A**: Keep `lowercase_snake_case` in Neo4j (works fine, just unconventional)
- **Option B**: Use `UPPER_SNAKE_CASE` in Neo4j and update the LanguageCore examples

**Recommendation**: Option B. Follow Neo4j convention. The LanguageCore files
already separate the examples, so the naming difference is contained. The
ontology_core.md uses semantic names (no syntax), so it's unaffected.

#### 6. Dual-mode maintenance burden

The honest question: **is it worth maintaining both backends?**

**For the demo**: Probably not. Neo4j is the clear winner for interactive demo
purposes. Fabric support could be archived as a documented option without active
maintenance.

**For production credibility**: Yes. Being able to say "this runs on Fabric in
production and Neo4j for demo" is valuable positioning. The strategy pattern
keeps it cheap.

**Recommendation**: Build both backends during Phase 1. Run the demo on Neo4j.
Don't invest in keeping the Fabric path actively tested unless there's a
production deployment scenario. If Fabric is needed again, the code is there —
just needs testing.

This keeps the door open for switching back to Fabric if/when Fabric gets write
support or higher capacity SKUs become available. The telemetry path (KQL/Kusto)
is completely unaffected — it always goes to Fabric Eventhouse regardless.

---

## Data Model: CSV → Neo4j Node/Relationship Mapping

### Current CSV entities

| CSV File | Neo4j Label | Properties | Count |
|----------|-------------|------------|-------|
| DimCoreRouter.csv | `:CoreRouter` | RouterId, City, Region, Vendor, Model | 3 |
| DimAggSwitch.csv | `:AggSwitch` | SwitchId, City, UplinkRouterId | 6 |
| DimBaseStation.csv | `:BaseStation` | StationId, StationType, AggSwitchId, City | 8 |
| DimTransportLink.csv | `:TransportLink` | LinkId, LinkType, CapacityGbps, SourceRouterId, TargetRouterId | 10 |
| DimMPLSPath.csv | `:MPLSPath` | PathId, PathType | 5 |
| DimService.csv | `:Service` | ServiceId, ServiceType, CustomerName, CustomerCount, ActiveUsers | 10 |
| DimSLAPolicy.csv | `:SLAPolicy` | SLAPolicyId, ServiceId, AvailabilityPct, MaxLatencyMs, PenaltyPerHourUSD, Tier | 5 |
| DimBGPSession.csv | `:BGPSession` | SessionId, PeerARouterId, PeerBRouterId, ASNumberA, ASNumberB | 3 |

### Relationships (from Fact tables + foreign keys)

| Source | Relationship | Target | From |
|--------|-------------|--------|------|
| TransportLink | `:CONNECTS` | CoreRouter (source) | DimTransportLink.SourceRouterId |
| TransportLink | `:CONNECTS` | CoreRouter (target) | DimTransportLink.TargetRouterId |
| AggSwitch | `:UPLINKS_TO` | CoreRouter | DimAggSwitch.UplinkRouterId |
| BaseStation | `:CONNECTS_TO` | AggSwitch | DimBaseStation.AggSwitchId |
| Service | `:DEPENDS_ON` | * (polymorphic) | FactServiceDependency |
| MPLSPath | `:HAS_HOP` | * (ordered) | FactMPLSPathHops |
| SLAPolicy | `:GOVERNS` | Service | DimSLAPolicy.ServiceId |
| BGPSession | `:PEERS_WITH` | CoreRouter (A) | DimBGPSession.PeerARouterId |
| BGPSession | `:PEERS_WITH` | CoreRouter (B) | DimBGPSession.PeerBRouterId |

**Total**: ~50 nodes, ~80 relationships. Trivial for Neo4j.

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Neo4j license concern (MS seller optics) | Medium | Community Edition is fully free; position as "demo complement to Fabric" |
| Graph data drift between Fabric and Neo4j | Low | Same source CSVs; provision script loads both |
| Neo4j container memory usage | Low | 2Gi sufficient for 50-node graph |
| Auth model difference (managed identity → password) | Low | Store password in Key Vault, reference via env var |
| Agent prompt changes (GQL → Cypher) | Low | 95% identical syntax; update system prompts |
| Dual-mode maintenance burden | Medium | Strategy pattern isolates backends; can deprecate Fabric path later |

---

## Skills Reference Mapping

Relevant skills from `/home/hanchoong/references/skills/.github/skills/`:

| Skill | Usage in V3 |
|-------|-------------|
| `react-flow-node-ts` | **Graph visualization** — custom node types for routers, links, services |
| `fastapi-router-py` | **API design** — new endpoints for /graph/mutate, /graph/topology |
| `azure-ai-projects-py` (tools.md) | **OpenApiTool** — agents call Neo4j via same pattern |
| `azure-cosmos-db-py` | **Service layer pattern** — reusable for Neo4j service class |
| `pydantic-models-py` | **Data models** — graph node/edge types as Pydantic models |
| `zustand-store-ts` | **Frontend state** — graph topology state management |
| `frontend-ui-dark-ts` | **Styling** — dark theme for graph dashboard |
| `azure-containerregistry-py` | **ACR** — push Neo4j image if customized |
| `azure-identity-py` | **Auth** — managed identity for Kusto (telemetry still on Fabric) |
| `azure-web-pubsub-ts/py` | **Real-time** — Phase 3 WebSocket push (stretch) |

---

## Implementation Sequence

```
Phase 1 — Core Swap (1-2 days)
  ├─ 1. Create modules/neo4j.bicep + Azure Files volume
  ├─ 2. Add neo4j Python driver to graph-query-api
  ├─ 3. Implement GraphBackend strategy pattern (Neo4j + Fabric)
  ├─ 4. Write provision_neo4j.py (load CSVs into Neo4j)
  ├─ 5. Update GraphExplorerAgent prompt (GQL → Cypher)
  ├─ 6. Update openapi.yaml spec description
  ├─ 7. Test: submit alert → agents query Neo4j → diagnosis works
  └─ 8. Config: GRAPH_BACKEND=neo4j in azure_config.env

Phase 2 — Interactive Demo (2-3 days)
  ├─ 1. Add /graph/topology, /graph/mutate, /graph/reset endpoints
  ├─ 2. Add /graph/fault with predefined scenarios
  ├─ 3. Build React Flow topology panel in frontend
  ├─ 4. Custom node types (CoreRouter, TransportLink, Service, etc.)
  ├─ 5. Fault injection UI (click node → trigger scenario → auto-alert)
  ├─ 6. Status highlighting (agent identifies fault → node turns red)
  └─ 7. Reset button (reload clean graph from CSVs)

Phase 3 — Real-Time (1 day, stretch)
  ├─ 1. SSE endpoint /graph/live for topology change events
  ├─ 2. Frontend subscribes on mount, updates React Flow state
  └─ 3. (Optional) Upgrade to Azure Web PubSub for bi-directional
```

---

## Open Questions

1. **Neo4j in Container Apps persistence**: Azure Files volume mounts on
   Container Apps have known latency issues. Is this acceptable for a demo
   graph of 50 nodes? (Almost certainly yes.) Alternative: use Azure Managed
   Disk or accept ephemeral data with fast reload from CSVs.

2. **Dual-mode or hard switch?** The strategy pattern keeps both backends alive.
   Is it worth the maintenance, or should we just commit to Neo4j for the demo
   and leave Fabric as a documented option?

3. **Agent prompt versioning**: If we switch prompts from GQL to Cypher, the
   same agents can't be used with both backends simultaneously. Might need
   separate agent sets, or a single set with "query language" as a runtime
   parameter.

4. **Neo4j Browser exposure**: Do we want to expose Neo4j's built-in browser
   (port 7474) during demos? It's impressive but adds attack surface. Could
   restrict to local dev only.

5. **Graph layout persistence**: Should node positions be stored in Neo4j
   (as position properties) or managed client-side (localStorage/Zustand)?
   Stored positions are shareable; client positions are simpler.
