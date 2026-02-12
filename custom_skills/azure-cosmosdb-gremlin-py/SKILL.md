```skill
---
name: azure-cosmosdb-gremlin-py
description: |
  Build graph database solutions with Azure Cosmos DB for Apache Gremlin and Python.
  Covers Bicep IaC provisioning, gremlinpython SDK (sync), Gremlin traversal queries,
  partition key strategies, data loading, FastAPI integration, and the Fabric Graph
  migration path. Triggers: "Cosmos DB Gremlin", "graph database Azure", "Gremlin API",
  "Apache TinkerPop", "gremlinpython", "property graph", "graph traversal",
  "Cosmos Gremlin Python", "network topology graph".
package: gremlinpython
---

# Azure Cosmos DB for Apache Gremlin — Python SDK & Deployment Skill

Build and query property graph databases using Azure Cosmos DB for Apache Gremlin,
the `gremlinpython` SDK, and Bicep infrastructure-as-code.

## Verified Versions (February 2026)

| Component | Version | Notes |
|-----------|---------|-------|
| gremlinpython | `3.8.0` | PyPI — Apache TinkerPop Gremlin-Python |
| Azure Cosmos DB | Gremlin API | Serverless or provisioned throughput |
| Cosmos DB Bicep type | `Microsoft.DocumentDB/databaseAccounts` | With `EnableGremlin` capability |
| Graph Bicep type | `Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs` | API version `2024-11-15` |
| Serializer | `GraphSONSerializersV2d0` | Required for Cosmos DB compatibility |
| Python | `>=3.10` | Tested on 3.12+ |
| Connection protocol | WebSocket (WSS) | Port 443, TLS required |

---

## Installation

```bash
pip install gremlinpython
# or with uv
uv add gremlinpython
```

> **Note**: The package is `gremlinpython` (one word). The import namespace is
> `gremlin_python`.

---

## Environment Variables

```bash
# Connection
COSMOS_GREMLIN_ENDPOINT=<account-name>.gremlin.cosmos.azure.com
COSMOS_GREMLIN_PRIMARY_KEY=<primary-key>
COSMOS_GREMLIN_DATABASE=networkgraph
COSMOS_GREMLIN_GRAPH=topology

# Derived (used in connection string)
# URL: wss://<endpoint>:443/
# Username: /dbs/<database>/colls/<graph>
```

---

## Authentication

### Primary Key (Default for Gremlin wire protocol)

Azure Cosmos DB for Apache Gremlin uses key-based auth over the Gremlin wire
protocol (WebSocket). Unlike the NoSQL API, `DefaultAzureCredential` is **not
supported** for the Gremlin wire protocol — use the account primary key.

```python
from gremlin_python.driver import client, serializer
import os

gremlin_client = client.Client(
    url=f"wss://{os.environ['COSMOS_GREMLIN_ENDPOINT']}:443/",
    traversal_source="g",
    username=f"/dbs/{os.environ['COSMOS_GREMLIN_DATABASE']}/colls/{os.environ['COSMOS_GREMLIN_GRAPH']}",
    password=os.environ["COSMOS_GREMLIN_PRIMARY_KEY"],
    message_serializer=serializer.GraphSONSerializersV2d0(),
)
```

> **Security**: Store the primary key in Azure Key Vault and inject via
> Container App secrets or `@Microsoft.KeyVault(...)` references. Never
> commit keys to source control.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Router                          │
│  POST /query/graph   — Gremlin traversals (read)               │
│  POST /graph/mutate  — Write operations (addV, addE, drop)     │
│  GET  /graph/viz     — Full topology for visualization         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                     Gremlin Client Module                      │
│  - Singleton client.Client initialisation                      │
│  - GraphSONSerializersV2d0 (required for Cosmos DB)            │
│  - Key from env / Key Vault                                    │
│  - Submit queries via client.submit()                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │  WSS (port 443, TLS)
┌──────────────────────────────▼──────────────────────────────────┐
│              Azure Cosmos DB for Apache Gremlin                │
│  - Fully managed, serverless or provisioned RU/s               │
│  - Automatic indexing on all properties                        │
│  - Global distribution, multi-region writes                    │
│  - Partition key: /category (configurable per domain)          │
└─────────────────────────────────────────────────────────────────┘
```

### Strategic Positioning

> **Why Cosmos DB Gremlin, not Neo4j?**
>
> 1. **Microsoft-native PaaS** — no containers to manage, auto-scale, SLA-backed
> 2. **Sales motion alignment** — "Azure all the way down", no OSS container to explain
> 3. **Fabric transition path** — Cosmos DB Gremlin → Graph in Microsoft Fabric is a
>    documented migration path. When Fabric Graph matures, the data model ports directly.
> 4. **Security & compliance** — RBAC, encryption at rest/transit, private endpoints
> 5. **Elastic scalability** — billions of vertices/edges, automatic partitioning

---

## Quick Start

### 1. Client Module Setup

Create a singleton Gremlin client with proper serialization:

```python
# db/gremlin.py
from gremlin_python.driver import client, serializer
import os

_gremlin_client = None


def get_gremlin_client() -> client.Client:
    """Get or create singleton Gremlin client for Cosmos DB."""
    global _gremlin_client
    if _gremlin_client is None:
        endpoint = os.environ["COSMOS_GREMLIN_ENDPOINT"]
        database = os.environ["COSMOS_GREMLIN_DATABASE"]
        graph = os.environ["COSMOS_GREMLIN_GRAPH"]
        key = os.environ["COSMOS_GREMLIN_PRIMARY_KEY"]

        _gremlin_client = client.Client(
            url=f"wss://{endpoint}:443/",
            traversal_source="g",
            username=f"/dbs/{database}/colls/{graph}",
            password=key,
            message_serializer=serializer.GraphSONSerializersV2d0(),
        )
    return _gremlin_client


def close_gremlin_client():
    """Close the Gremlin client connection."""
    global _gremlin_client
    if _gremlin_client is not None:
        _gremlin_client.close()
        _gremlin_client = None
```

### 2. FastAPI Lifespan Integration

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from db.gremlin import get_gremlin_client, close_gremlin_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm the client
    get_gremlin_client()
    yield
    # Shutdown: clean close
    close_gremlin_client()


app = FastAPI(lifespan=lifespan)
```

### 3. Executing Queries

```python
from db.gremlin import get_gremlin_client


def run_gremlin(query: str, bindings: dict | None = None) -> list[dict]:
    """Execute a Gremlin query and return results as list of dicts."""
    gremlin_client = get_gremlin_client()
    callback = gremlin_client.submit(
        message=query,
        bindings=bindings or {},
    )
    results = callback.all().result()
    return results
```

### 4. Query Patterns (Network Topology Domain)

#### Add a Vertex

```python
run_gremlin(
    "g.addV(label_val)"
    ".property('id', id_val)"
    ".property('partitionKey', pk_val)"
    ".property('RouterId', router_id)"
    ".property('City', city)"
    ".property('Region', region)",
    bindings={
        "label_val": "CoreRouter",
        "id_val": "CORE-SYD-01",
        "pk_val": "router",
        "router_id": "CORE-SYD-01",
        "city": "Sydney",
        "region": "APAC",
    },
)
```

> **Critical**: Always include the partition key property. Cosmos DB Gremlin
> requires a partition key on every vertex. Use parameterized bindings —
> never concatenate strings into Gremlin queries.

#### Read a Vertex by Partition Key + ID

```python
# Cosmos DB Gremlin point-read uses [partitionKey, id] composite
result = run_gremlin(
    "g.V([pk, id_val])",
    bindings={"pk": "router", "id_val": "CORE-SYD-01"},
)
```

#### Read a Single Result (`.one()`)

For point reads where exactly one result is expected, use `.one()` instead of
`.all().result()` to get a single dict directly:

```python
def run_gremlin_one(query: str, bindings: dict | None = None) -> dict:
    """Execute a Gremlin query and return a single result."""
    gremlin_client = get_gremlin_client()
    return gremlin_client.submit(
        message=query,
        bindings=bindings or {},
    ).one()

# Usage — returns a single vertex dict, not a list
router = run_gremlin_one(
    "g.V([pk, id_val])",
    bindings={"pk": "router", "id_val": "CORE-SYD-01"},
)
```

#### Traverse Relationships

```python
# Find all base stations connected to an aggregation switch
result = run_gremlin(
    "g.V().hasLabel('AggSwitch')"
    ".has('SwitchId', switch_id)"
    ".out('aggregates')"
    ".hasLabel('BaseStation')"
    ".valueMap(true)",
    bindings={"switch_id": "AGG-SYD-01"},
)
```

#### Find Path Between Two Nodes

```python
# Find shortest path between two routers
result = run_gremlin(
    "g.V().has('CoreRouter', 'RouterId', src)"
    ".repeat(both().simplePath()).until(has('RouterId', dst))"
    ".path()"
    ".limit(1)",
    bindings={"src": "CORE-SYD-01", "dst": "CORE-MEL-01"},
)
```

#### Add an Edge

```python
run_gremlin(
    "g.V().has('CoreRouter', 'RouterId', src_id)"
    ".addE('routes_via')"
    ".to(g.V().has('AggSwitch', 'SwitchId', dst_id))"
    ".property('bandwidth', bw)"
    ".property('latency_ms', lat)",
    bindings={
        "src_id": "CORE-SYD-01",
        "dst_id": "AGG-SYD-01",
        "bw": "100Gbps",
        "lat": 2,
    },
)
```

#### Delete a Vertex (Cascade Edges)

```python
# Drop a base station and all its incident edges
run_gremlin(
    "g.V().has('BaseStation', 'StationId', station_id).drop()",
    bindings={"station_id": "BS-SYD-N-01"},
)
```

#### Count Vertices by Label

```python
result = run_gremlin("g.V().groupCount().by(label)")
# Returns: [{'CoreRouter': 3, 'AggSwitch': 6, 'BaseStation': 8, ...}]
```

#### Full Topology for Visualization

```python
# Get all vertices and edges for frontend graph rendering
vertices = run_gremlin("g.V().valueMap(true).by(unfold())")
edges = run_gremlin("g.E().project('id','label','source','target','properties')"
                    ".by(id).by(label).by(outV().id()).by(inV().id()).by(valueMap())")
```

---

## Gremlin vs Cypher Quick Reference

For teams migrating from Neo4j/Cypher, here's a translation table:

| Operation | Cypher (Neo4j) | Gremlin (Cosmos DB) |
|-----------|----------------|---------------------|
| Find vertex | `MATCH (r:CoreRouter) RETURN r` | `g.V().hasLabel('CoreRouter')` |
| Filter | `WHERE r.City = 'Sydney'` | `.has('City', 'Sydney')` |
| Traverse out | `(r)-[:routes_via]->(s)` | `.out('routes_via')` |
| Traverse in | `(r)<-[:routes_via]-(s)` | `.in('routes_via')` |
| Return properties | `RETURN r.RouterId, r.City` | `.values('RouterId', 'City')` |
| Return map | `RETURN r {.*}` | `.valueMap(true)` |
| Create vertex | `CREATE (r:CoreRouter {id: 'X'})` | `g.addV('CoreRouter').property('id','X')` |
| Create edge | `CREATE (a)-[:routes_via]->(b)` | `g.V(a).addE('routes_via').to(g.V(b))` |
| Delete | `DETACH DELETE r` | `g.V(r).drop()` |
| Path | `MATCH p = shortestPath(...)` | `.repeat(both().simplePath()).until(...)` |
| Count by label | `MATCH (n) RETURN labels(n), count(*)` | `g.V().groupCount().by(label)` |
| Limit | `LIMIT 10` | `.limit(10)` |

---

## Partition Key Strategy

Azure Cosmos DB requires a partition key for every container (graph). Choose
based on your query patterns:

### Option A: Entity Type Partition (Recommended for Demo)

```
Partition key path: /partitionKey
Values: "router", "switch", "basestation", "service", "link", "path", "policy", "session"
```

**Pros**: Simple, small number of partitions, cross-partition queries acceptable
for ~50 nodes. **Cons**: Hot partitions possible at scale.

### Option B: Region-Based Partition

```
Partition key path: /region
Values: "APAC-SYD", "APAC-MEL", "APAC-BRI"
```

**Pros**: Locality-aware queries are single-partition. **Cons**: Services span
regions, requiring cross-partition traversals.

### Cross-Partition Query Warning

Gremlin traversals that touch vertices in different partitions are
**cross-partition** and cost more RU/s. For the demo scale (~50 nodes, ~80 edges),
this is negligible. At production scale, design partition keys to keep related
vertices co-located.

---

## Cosmos DB Gremlin Limitations & Gotchas

| Limitation | Detail |
|-----------|---------|
| **No lambdas** | Cosmos DB does not support Gremlin lambda steps (`map{...}`, `filter{...}`) |
| **No `profile()`** | Use Azure Monitor / Diagnostic Settings instead |
| **No `subgraph()`** | Extract subgraphs via application-side logic |
| **Partition key required** | Every vertex must include the partition key property |
| **String IDs preferred** | Cosmos DB auto-generates `id` if omitted; prefer explicit string IDs |
| **No Gremlin bytecode** | Cosmos DB only supports string-based Gremlin. Use `client.submit()`, not `GraphTraversalSource` |
| **GraphSON v2 only** | Must use `GraphSONSerializersV2d0` — v3 is not supported |
| **Max 20 RU per query default** | Increase via `x-ms-cosmos-page-size` header or portal settings |

---

## Best Practices

### Query Construction

- **Always use parameterized bindings** — prevents injection and enables query caching
- **Avoid `g.V()` without filters** — scan all vertices, high cost
- **Use `.has(label, key, value)`** — combines `hasLabel()` and `has()` for efficiency
- **Limit result sets** — always add `.limit(N)` for exploratory queries
- **Single-partition reads** — use `g.V([partitionKey, id])` for point reads

### Connection Management

- **Singleton client** — create one `client.Client` per process lifetime
- **Close on shutdown** — call `client.close()` in FastAPI lifespan
- **Handle transient failures** — Cosmos DB may return 429 (rate limit); retry with backoff

### Data Modelling

- **Vertices for entities** — CoreRouter, AggSwitch, BaseStation, Service, etc.
- **Edges for relationships** — routes_via, aggregates, depends_on, monitors
- **Properties on edges** — bandwidth, latency_ms, weight, dependency_strength
- **Keep vertices lightweight** — store bulk telemetry in Eventhouse, not on graph properties

---

## Fabric Transition Path

Azure Cosmos DB for Apache Gremlin provides a documented migration path to
**Graph in Microsoft Fabric** (currently in preview):

1. **Today**: Use Cosmos DB Gremlin for OLTP graph operations (read/write, interactive demo)
2. **Migration**: Export graph data via Cosmos DB change feed → Fabric Lakehouse
3. **Tomorrow**: Query the same graph model via Fabric Graph (GQL/ISO syntax)
4. **Benefit**: No data model redesign — vertices and edges map directly to Fabric Graph tables

> "Start with Cosmos DB Gremlin for the live demo. When Fabric Graph is GA,
> migrate the graph data via change feed mirroring — same schema, same queries
> (GQL ≈ Gremlin), fully Microsoft-native."

This is explicitly mentioned in the [Cosmos DB Gremlin docs](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/overview):
> *"Are you looking to implement an OLAP graph or migrate an existing Apache
> Gremlin application? Consider Graph in Microsoft Fabric."*

---

## Troubleshooting & Diagnostic Queries

Azure Cosmos DB for Apache Gremlin exposes diagnostic logs via Azure Monitor.
Enable **Diagnostic Settings** on the Cosmos DB account and send logs to a
Log Analytics workspace (resource-specific mode recommended).

Reference: [Diagnostic queries for Gremlin](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/diagnostic-queries?tabs=resource-specific)

### Enable Diagnostics (Azure CLI)

```bash
az monitor diagnostic-settings create \
  --name "gremlin-diagnostics" \
  --resource "$COSMOS_ACCOUNT_RESOURCE_ID" \
  --workspace "$LOG_ANALYTICS_WORKSPACE_ID" \
  --logs '[{"category": "GremlinRequests", "enabled": true},{"category": "PartitionKeyRUConsumption", "enabled": true}]'
```

### KQL: Top 10 RU-Consuming Queries

```kql
CDBGremlinRequests
| where TimeGenerated >= ago(1h)
| project PIICommandText, ActivityId, DatabaseName, CollectionName, RequestCharge, TimeGenerated
| order by RequestCharge desc
| take 10
```

### KQL: Throttled Requests (429s)

```kql
CDBGremlinRequests
| where StatusCode == 429
| project PIICommandText, ActivityId, DatabaseName, CollectionName, OperationName, TimeGenerated
| order by TimeGenerated desc
```

### KQL: Large Response Payloads

```kql
CDBGremlinRequests
| summarize max(ResponseLength) by PIICommandText
| order by max_ResponseLength desc
```

### KQL: RU Consumption by Physical Partition

```kql
CDBPartitionKeyRUConsumption
| where TimeGenerated >= ago(1d)
| summarize sum(todouble(RequestCharge)) by toint(PartitionKeyRangeId)
| render columnchart
```

### KQL: RU Consumption by Logical Partition Key

```kql
CDBPartitionKeyRUConsumption
| where TimeGenerated >= ago(1d)
| summarize sum(todouble(RequestCharge)) by PartitionKey, PartitionKeyRangeId
| render columnchart
```

### Common Python-Side Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `GremlinServerError: 429` | Rate limit exceeded | Retry with exponential backoff; increase RU/s |
| `GremlinServerError: 408` | Request timeout | Simplify query; add `.limit()`; reduce traversal depth |
| `WebSocketBadStatusException: 401` | Auth failure | Check primary key, endpoint, username path |
| `GraphSON v3 unsupported` | Wrong serializer | Use `GraphSONSerializersV2d0()`, not `V3d0` |
| `Missing partition key` | Vertex without `/partitionKey` | Always include `.property('partitionKey', value)` on `addV()` |
| `Cross-partition query` (high RU) | Traversal spans partitions | Acceptable at demo scale; redesign partition key at production scale |

---

## Reference Files

| File | When to Read |
|------|--------------|
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | Verifying correct imports, auth, query patterns, and Bicep structure |
| [references/data-loading.md](references/data-loading.md) | Loading network topology CSVs into Cosmos DB Gremlin graph |
| [references/bicep-provisioning.md](references/bicep-provisioning.md) | Bicep modules for provisioning Cosmos DB Gremlin account, database, graph |
```
