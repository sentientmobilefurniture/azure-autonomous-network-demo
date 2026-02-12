```skill
---
name: azure-container-neo4j-py
description: |
  Deploy and manage Neo4j Community Edition as an Azure Container App with Python.
  Covers Bicep IaC for Container Apps, persistent Azure Files volumes, Neo4j Python
  driver (sync + async), Cypher queries, data loading, and health monitoring.
  Triggers: "neo4j", "graph database", "Neo4j Container App", "Cypher", "Bolt protocol",
  "neo4j Python driver", "graph deployment Azure", "Neo4j Docker Azure".
package: neo4j
---

# Neo4j on Azure Container Apps — Python SDK & Deployment Skill

Deploy Neo4j Community Edition as a containerised graph database on Azure Container
Apps, and interact with it using the official Neo4j Python driver.

## Verified Versions (February 2026)

| Component | Version | Notes |
|-----------|---------|-------|
| Neo4j Docker image | `neo4j:2026.01.4-community` | Free Community Edition, debian:trixie-slim base |
| Neo4j Python driver | `neo4j>=6.1.0` | PyPI package `neo4j` (NOT `neo4j-driver`, which is deprecated) |
| Bolt protocol port | `7687` | Primary driver communication |
| HTTP/Browser port | `7474` | Neo4j Browser UI (dev only) |
| Azure Container Apps API | `2024-03-01` | Bicep resource type `Microsoft.App/containerApps` |
| Python | `>=3.10` | Driver supports 3.10 – 3.14 |

---

## Installation

```bash
pip install neo4j
# or with uv
uv add neo4j
```

### Optional: Rust extensions for better performance

```bash
pip install neo4j-rust-ext
```

> **Note**: The old package name `neo4j-driver` is deprecated since 6.0.0 and
> receives no further updates. Always use `neo4j`.

---

## Environment Variables

```bash
# Connection
NEO4J_BOLT_URI=bolt://localhost:7687        # or neo4j://localhost:7687 for routing
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>              # minimum 8 characters
NEO4J_DATABASE=neo4j                        # default database name

# Azure Container App (for Bicep/deployment)
NEO4J_CONTAINER_APP_NAME=neo4j
NEO4J_IMAGE=neo4j:2026.01.4-community
NEO4J_CPU=1.0
NEO4J_MEMORY=2Gi
```

---

## Authentication

### Basic Authentication (Default)

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "your_password"),
)
driver.verify_connectivity()
```

### No Authentication (Dev/Testing Only)

```python
from neo4j import GraphDatabase

# Requires NEO4J_AUTH=none on the container
driver = GraphDatabase.driver("bolt://localhost:7687")
```

---

## Quick Start — Sync Driver

```python
import os
from neo4j import GraphDatabase, RoutingControl

URI = os.environ["NEO4J_BOLT_URI"]
AUTH = (os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

with GraphDatabase.driver(URI, auth=AUTH) as driver:
    driver.verify_connectivity()

    # Write
    driver.execute_query(
        "CREATE (r:Router {id: $id, city: $city})",
        id="CORE-SYD-01", city="Sydney",
        database_=DATABASE,
    )

    # Read
    records, summary, keys = driver.execute_query(
        "MATCH (r:Router) RETURN r.id AS id, r.city AS city",
        database_=DATABASE,
        routing_=RoutingControl.READ,
    )
    for record in records:
        print(record.data())  # {"id": "CORE-SYD-01", "city": "Sydney"}
```

---

## Async Driver

```python
import os
import asyncio
from neo4j import AsyncGraphDatabase

URI = os.environ["NEO4J_BOLT_URI"]
AUTH = (os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


async def main():
    async with AsyncGraphDatabase.driver(URI, auth=AUTH) as driver:
        await driver.verify_connectivity()

        # Write
        await driver.execute_query(
            "CREATE (r:Router {id: $id, city: $city})",
            id="CORE-SYD-01", city="Sydney",
            database_=DATABASE,
        )

        # Read
        records, summary, keys = await driver.execute_query(
            "MATCH (r:Router) RETURN r.id AS id, r.city AS city",
            database_=DATABASE,
        )
        for record in records:
            print(record.data())


asyncio.run(main())
```

---

## Session-Based Queries (Fine-Grained Control)

Use sessions when you need explicit transaction control:

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(URI, auth=AUTH)

# Read session
with driver.session(database="neo4j") as session:
    result = session.run(
        "MATCH (r:Router)-[:CONNECTS]->(s:Router) "
        "RETURN r.id AS source, s.id AS target"
    )
    for record in result:
        print(f"{record['source']} -> {record['target']}")

# Write session (explicit transaction)
with driver.session(database="neo4j") as session:
    with session.begin_transaction() as tx:
        tx.run("CREATE (r:Router {id: $id})", id="CORE-MEL-01")
        tx.run(
            "MATCH (a:Router {id: $a}), (b:Router {id: $b}) "
            "CREATE (a)-[:CONNECTS {capacity: $cap}]->(b)",
            a="CORE-SYD-01", b="CORE-MEL-01", cap=100,
        )
        tx.commit()

driver.close()
```

### Async Session

```python
from neo4j import AsyncGraphDatabase

driver = AsyncGraphDatabase.driver(URI, auth=AUTH)

async with driver.session(database="neo4j") as session:
    result = await session.run(
        "MATCH (r:Router) RETURN r.id AS id LIMIT 10"
    )
    records = [record.data() async for record in result]

await driver.close()
```

---

## Data Loading (Cypher)

### From Parameterised Queries

```python
from neo4j import GraphDatabase
import csv

driver = GraphDatabase.driver(URI, auth=AUTH)

def load_routers(tx, rows):
    tx.run(
        "UNWIND $rows AS row "
        "MERGE (r:CoreRouter {RouterId: row.RouterId}) "
        "SET r.City = row.City, r.Region = row.Region, "
        "    r.Vendor = row.Vendor, r.Model = row.Model",
        rows=rows,
    )

with open("DimCoreRouter.csv") as f:
    rows = list(csv.DictReader(f))

with driver.session(database="neo4j") as session:
    session.execute_write(load_routers, rows)

driver.close()
```

### From LOAD CSV (files mounted to /import)

```python
driver.execute_query(
    """
    LOAD CSV WITH HEADERS FROM 'file:///DimCoreRouter.csv' AS row
    CREATE (r:CoreRouter {
        RouterId: row.RouterId,
        City: row.City,
        Region: row.Region,
        Vendor: row.Vendor,
        Model: row.Model
    })
    """,
    database_="neo4j",
)
```

> **Note**: `LOAD CSV` with `file:///` requires the CSV to be in the container's
> `/var/lib/neo4j/import` directory. Mount a volume to `/import` for this.

---

## Common Cypher Patterns

### Create Nodes and Relationships

```cypher
// Create nodes
CREATE (r:CoreRouter {RouterId: "CORE-SYD-01", City: "Sydney"})

// Create relationship
MATCH (a:CoreRouter {RouterId: "CORE-SYD-01"})
MATCH (b:CoreRouter {RouterId: "CORE-MEL-01"})
CREATE (a)-[:CONNECTS {CapacityGbps: 100}]->(b)

// Upsert with MERGE
MERGE (r:CoreRouter {RouterId: "CORE-SYD-01"})
SET r.City = "Sydney", r.Status = "ACTIVE"
```

### Read Patterns

```cypher
// Single-hop lookup
MATCH (r:CoreRouter {City: "Sydney"})
RETURN r.RouterId, r.Vendor, r.Model

// Multi-hop traversal (blast radius)
MATCH (t:TransportLink {LinkId: "LINK-SYD-MEL"})<-[:ROUTES_VIA]-(p:MPLSPath)<-[:DEPENDS_ON]-(s:Service)
RETURN p.PathId, s.ServiceId, s.CustomerName

// Shortest path
MATCH path = shortestPath(
    (a:CoreRouter {RouterId: "CORE-SYD-01"})-[*]-(b:CoreRouter {RouterId: "CORE-PER-01"})
)
RETURN [n IN nodes(path) | labels(n)[0] + ": " + coalesce(n.RouterId, n.LinkId, "")] AS hops

// Full topology (for visualization)
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN labels(n)[0] AS sourceType, properties(n) AS sourceProps,
       type(r) AS relType, properties(r) AS relProps,
       labels(m)[0] AS targetType, properties(m) AS targetProps
```

### Write / Mutate

```cypher
// Set status
MATCH (t:TransportLink {LinkId: $linkId})
SET t.Status = "DOWN", t.DownSince = datetime()
RETURN t.LinkId, t.Status

// Delete relationship
MATCH (a)-[r:CONNECTS]->(b) WHERE r.LinkId = $linkId
DELETE r

// Delete node and all relationships
MATCH (r:CoreRouter {RouterId: $routerId})
DETACH DELETE r

// Clear entire graph (reset)
MATCH (n) DETACH DELETE n
```

---

## Health Check

```python
from neo4j import GraphDatabase

def check_neo4j_health(uri: str, auth: tuple[str, str]) -> dict:
    """Check Neo4j connectivity and return status."""
    try:
        driver = GraphDatabase.driver(uri, auth=auth)
        driver.verify_connectivity()
        # Get server info
        info = driver.get_server_info()
        driver.close()
        return {
            "status": "ok",
            "server": info.agent,
            "address": f"{info.address[0]}:{info.address[1]}",
            "protocol_version": f"{info.protocol_version[0]}.{info.protocol_version[1]}",
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}
```

### Async Health Check

```python
from neo4j import AsyncGraphDatabase

async def check_neo4j_health(uri: str, auth: tuple[str, str]) -> dict:
    try:
        driver = AsyncGraphDatabase.driver(uri, auth=auth)
        await driver.verify_connectivity()
        info = await driver.get_server_info()
        await driver.close()
        return {
            "status": "ok",
            "server": info.agent,
            "address": f"{info.address[0]}:{info.address[1]}",
            "protocol_version": f"{info.protocol_version[0]}.{info.protocol_version[1]}",
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}
```

---

## FastAPI Integration

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from neo4j import AsyncGraphDatabase
from pydantic import BaseModel
import os

URI = os.environ["NEO4J_BOLT_URI"]
AUTH = (os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create driver
    app.state.neo4j_driver = AsyncGraphDatabase.driver(URI, auth=AUTH)
    await app.state.neo4j_driver.verify_connectivity()
    yield
    # Shutdown: close driver
    await app.state.neo4j_driver.close()


app = FastAPI(lifespan=lifespan)


class QueryRequest(BaseModel):
    query: str
    params: dict | None = None


class QueryResponse(BaseModel):
    columns: list[dict]
    data: list[dict]


@app.get("/health")
async def health(request: Request):
    try:
        await request.app.state.neo4j_driver.verify_connectivity()
        return {"status": "ok", "backend": "neo4j"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/query/graph", response_model=QueryResponse)
async def query_graph(request: Request, body: QueryRequest):
    driver = request.app.state.neo4j_driver
    async with driver.session(database=DATABASE) as session:
        result = await session.run(body.query, body.params or {})
        records = [record.data() async for record in result]
        columns = list(records[0].keys()) if records else []
        return QueryResponse(
            columns=[{"name": c, "type": "string"} for c in columns],
            data=records,
        )
```

---

## Docker — Local Development

### Run Neo4j with Docker

```bash
docker run \
    --name neo4j-dev \
    --restart always \
    --publish 7474:7474 \
    --publish 7687:7687 \
    --env NEO4J_AUTH=neo4j/your_password \
    --env NEO4J_PLUGINS='["apoc"]' \
    --volume neo4j-data:/data \
    --volume neo4j-logs:/logs \
    --detach \
    neo4j:2026.01.4-community
```

### Docker Compose

```yaml
# docker-compose.yml
services:
  neo4j:
    image: neo4j:2026.01.4-community
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/your_password
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_server_memory_pagecache_size: 512M
      NEO4J_server_memory_heap_max__size: 512M
    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs
      - ./data/csv:/var/lib/neo4j/import  # for LOAD CSV
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:7474 || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 30s

volumes:
  neo4j-data:
  neo4j-logs:
```

### Neo4j Docker Mount Points

| Path | Access | Purpose |
|------|--------|---------|
| `/data` | read/write | Database files — **mount for persistence** |
| `/logs` | read/write | Log files |
| `/conf` | read | Custom configuration files |
| `/plugins` | read | Plugin JARs |
| `/import` | read | CSV files for `LOAD CSV` |
| `/licenses` | read | License files (Enterprise only) |

### Neo4j Docker Environment Variables

| Variable | Example | Purpose |
|----------|---------|---------|
| `NEO4J_AUTH` | `neo4j/password` or `none` | Initial auth credentials |
| `NEO4J_PLUGINS` | `'["apoc"]'` | Auto-download plugins on startup |
| `NEO4J_server_memory_pagecache_size` | `512M` | Page cache size |
| `NEO4J_server_memory_heap_max__size` | `512M` | Max JVM heap |
| `NEO4J_server_default__listen__address` | `0.0.0.0` | Listen on all interfaces |

> **Config naming**: Prefix with `NEO4J_`, replace `.` with `_`, replace `_` with `__`.
> Example: `server.memory.heap.max_size` → `NEO4J_server_memory_heap_max__size`

### Available Plugins (Community Edition)

| Plugin key | Purpose |
|------------|---------|
| `apoc` | APOC Core — utility procedures (path expansion, data conversion, etc.) |
| `apoc-extended` | APOC Extended — additional procedures |
| `genai` | GenAI integration procedures |
| `n10s` | Neosemantics — RDF/OWL integration |

> **Note**: `graph-data-science` and `bloom` require Enterprise Edition.

---

## Azure Container Apps — Bicep Deployment

### Neo4j Container App Module

```bicep
// infra/modules/neo4j.bicep

@description('Name of the Container Apps managed environment')
param managedEnvironmentId string

@description('Azure Files storage account name for persistent volume')
param storageAccountName string

@description('Azure Files share name for Neo4j /data')
param shareName string = 'neo4j-data'

@description('Storage account access key')
@secure()
param storageAccountKey string

@description('Neo4j initial password')
@secure()
param neo4jPassword string

@description('Location for resources')
param location string = resourceGroup().location

@description('Neo4j container image')
param neo4jImage string = 'neo4j:2026.01.4-community'

@description('CPU cores for Neo4j container')
param cpu string = '1.0'

@description('Memory for Neo4j container')
param memory string = '2Gi'

// --- Storage link on the managed environment ---
resource managedEnvironmentStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  name: '${split(managedEnvironmentId, '/')[8]}/neo4jdata'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: shareName
      accessMode: 'ReadWrite'
    }
  }
}

// --- Neo4j Container App ---
resource neo4j 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'neo4j'
  location: location
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false          // internal only — graph-query-api connects via Bolt
        targetPort: 7687         // Bolt protocol
        transport: 'tcp'
      }
    }
    template: {
      containers: [
        {
          name: 'neo4j'
          image: neo4jImage
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'NEO4J_AUTH', value: 'neo4j/${neo4jPassword}' }
            { name: 'NEO4J_PLUGINS', value: '["apoc"]' }
            { name: 'NEO4J_server_memory_pagecache_size', value: '512M' }
            { name: 'NEO4J_server_memory_heap_max__size', value: '512M' }
            { name: 'NEO4J_server_default__listen__address', value: '0.0.0.0' }
          ]
          volumeMounts: [
            { volumeName: 'neo4j-data', mountPath: '/data' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                port: 7474
                path: '/'
              }
              initialDelaySeconds: 30
              periodSeconds: 15
            }
            {
              type: 'Readiness'
              tcpSocket: {
                port: 7687
              }
              initialDelaySeconds: 20
              periodSeconds: 10
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'neo4j-data'
          storageType: 'AzureFile'
          storageName: managedEnvironmentStorage.name
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1   // Neo4j Community is single-instance
      }
    }
  }
}

@description('Internal FQDN for the Neo4j Container App')
output neo4jFqdn string = neo4j.properties.configuration.ingress.fqdn

@description('Bolt URI for connecting to Neo4j from other Container Apps')
output neo4jBoltUri string = 'bolt://${neo4j.properties.configuration.ingress.fqdn}:7687'
```

### Azure Files Share Module

```bicep
// infra/modules/azure-files-share.bicep

param storageAccountName string
param location string = resourceGroup().location
param shareName string = 'neo4j-data'
param shareQuotaGb int = 5

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: shareName
  properties: {
    shareQuota: shareQuotaGb
  }
}

output storageAccountName string = storageAccount.name
output storageAccountKey string = storageAccount.listKeys().keys[0].value
output shareName string = share.name
```

### Wire into main.bicep

```bicep
// In infra/main.bicep — add these module references

module neo4jStorage 'modules/azure-files-share.bicep' = {
  name: 'neo4j-storage'
  params: {
    storageAccountName: '${abbrs.storageStorageAccounts}neo4j${resourceToken}'
    location: location
    shareName: 'neo4j-data'
  }
}

module neo4j 'modules/neo4j.bicep' = {
  name: 'neo4j'
  params: {
    managedEnvironmentId: containerAppsEnvironment.outputs.id
    storageAccountName: neo4jStorage.outputs.storageAccountName
    storageAccountKey: neo4jStorage.outputs.storageAccountKey
    shareName: neo4jStorage.outputs.shareName
    neo4jPassword: neo4jPassword   // from Key Vault or parameter
    location: location
  }
}

output NEO4J_BOLT_URI string = neo4j.outputs.neo4jBoltUri
```

---

## Driver Configuration Reference

### Connection Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_connection_pool_size` | 100 | Maximum connections in the pool |
| `connection_acquisition_timeout` | 60s | Timeout waiting for a connection from the pool |
| `max_transaction_retry_time` | 30s | Max time for retrying a transaction |
| `connection_timeout` | 30s | Timeout for establishing a TCP connection |
| `encrypted` | `False` | Enable TLS (use `neo4j+s://` scheme instead) |
| `trusted_certificates` | System | Custom CA certificates |

### URI Schemes

| Scheme | Encrypted | Certificates | Use Case |
|--------|-----------|-------------|----------|
| `bolt://` | No | — | Single instance, local dev |
| `bolt+s://` | Yes | CA-signed only | Single instance, production |
| `bolt+ssc://` | Yes | CA + self-signed | Single instance, self-signed TLS |
| `neo4j://` | No | — | Cluster with routing |
| `neo4j+s://` | Yes | CA-signed only | Cluster, production (Aura) |
| `neo4j+ssc://` | Yes | CA + self-signed | Cluster, self-signed TLS |

> For Azure Container Apps (internal), use `bolt://` since traffic stays within
> the managed environment's VNET.

---

## Result Handling

```python
# execute_query returns (records, summary, keys)
records, summary, keys = driver.execute_query(
    "MATCH (r:Router) RETURN r.id AS id, r.city AS city",
    database_="neo4j",
)

# Access records
for record in records:
    record["id"]          # by key
    record.data()         # as dict: {"id": "...", "city": "..."}
    record.values()       # as list: ["...", "..."]

# Access summary
summary.counters.nodes_created
summary.counters.relationships_created
summary.counters.properties_set
summary.counters.nodes_deleted
summary.result_available_after  # milliseconds
```

---

## Best Practices

1. **Use `execute_query()` for simple operations** — it handles sessions,
   transactions, and retries automatically. Only drop to `session.run()` when you
   need explicit transaction control or streaming large result sets.

2. **Always use parameterised queries** — never concatenate user input into
   Cypher strings. Use `$param` placeholders and pass values as keyword
   arguments or a `params` dict.

3. **Create the driver once, share globally** — the driver is thread-safe and
   manages its own connection pool. In FastAPI, create it in the `lifespan` and
   store on `app.state`.

4. **Close the driver on shutdown** — call `driver.close()` (or use `with`/
   `async with`) to release connections cleanly.

5. **Use `MERGE` instead of `CREATE` for idempotency** — especially in data
   loading scripts that might be re-run. `MERGE` creates only if not exists.

6. **Pin Neo4j image to a specific version** — use `neo4j:2026.01.4-community`,
   not `:latest` or `:community`, to ensure reproducible deployments.

7. **Mount `/data` for persistence** — without a volume mount, all graph data
   is lost when the container restarts.

8. **Set memory explicitly** — configure `NEO4J_server_memory_pagecache_size`
   and `NEO4J_server_memory_heap_max__size` to avoid OOM. For a 50-node demo
   graph, 512M each is generous.

9. **Use indexes for lookup properties** — create a uniqueness constraint or
   index on your primary key properties for faster `MATCH` queries:
   ```cypher
   CREATE CONSTRAINT router_id IF NOT EXISTS
   FOR (r:CoreRouter) REQUIRE r.RouterId IS UNIQUE
   ```

10. **Keep Neo4j internal in Container Apps** — set `ingress.external: false`.
    Only the graph-query-api Container App should communicate with Neo4j via Bolt.

---

## Reference Files

| File | When to Read |
|------|-------------|
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | Validating generated code correctness — import patterns, anti-patterns, auth |
| [references/deployment.md](references/deployment.md) | Azure Container Apps deployment details, Bicep patterns, persistent storage |
| [references/data-loading.md](references/data-loading.md) | Loading CSV data into Neo4j, indexes, constraints, bulk operations |
```
