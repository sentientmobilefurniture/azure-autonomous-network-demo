# Acceptance Criteria — Azure Cosmos DB for Apache Gremlin (Python)

Use these patterns to verify correct implementation when working with Azure
Cosmos DB Gremlin and the `gremlinpython` SDK.

---

## 1. Imports

✅ Correct imports:
```python
from gremlin_python.driver import client, serializer
```

❌ Wrong — importing `Graph` or `traversal` for Cosmos DB (unsupported bytecode):
```python
from gremlin_python.structure.graph import Graph
from gremlin_python.process.anonymous_traversal import traversal
```

❌ Wrong — using GraphSON v3 serializer:
```python
message_serializer=serializer.GraphSONSerializersV3d0()
```

✅ Correct serializer for Cosmos DB:
```python
message_serializer=serializer.GraphSONSerializersV2d0()
```

---

## 2. Client Initialization

✅ Correct — WebSocket URL with port 443, proper username format:
```python
gremlin_client = client.Client(
    url=f"wss://{endpoint}:443/",
    traversal_source="g",
    username=f"/dbs/{database}/colls/{graph}",
    password=primary_key,
    message_serializer=serializer.GraphSONSerializersV2d0(),
)
```

❌ Wrong — using Bolt protocol (that's Neo4j):
```python
client.Client(url="bolt://localhost:7687", ...)
```

❌ Wrong — missing `message_serializer` (defaults to incompatible version):
```python
client.Client(url=f"wss://{endpoint}:443/", traversal_source="g", ...)
```

❌ Wrong — username without `/dbs/` prefix:
```python
username="mydb/mygraph"  # Must be /dbs/mydb/colls/mygraph
```

---

## 3. Query Execution

✅ Correct — string-based query with parameterized bindings:
```python
result = gremlin_client.submit(
    message="g.V().hasLabel(label_val).has('City', city_val).valueMap(true)",
    bindings={"label_val": "CoreRouter", "city_val": "Sydney"},
).all().result()
```

❌ Wrong — string concatenation (injection risk, no query caching):
```python
result = gremlin_client.submit(
    f"g.V().hasLabel('CoreRouter').has('City', '{city}')"
).all().result()
```

❌ Wrong — using bytecode traversal (not supported by Cosmos DB):
```python
g = traversal().with_remote(connection)
g.V().has_label('CoreRouter').to_list()  # Will fail against Cosmos DB
```

---

## 4. Partition Key Handling

✅ Correct — always include partition key property on vertex creation:
```python
gremlin_client.submit(
    "g.addV(label_val).property('id', id_val).property('partitionKey', pk_val)"
    ".property('RouterId', router_id)",
    bindings={
        "label_val": "CoreRouter",
        "id_val": "CORE-SYD-01",
        "pk_val": "router",
        "router_id": "CORE-SYD-01",
    },
).all().result()
```

❌ Wrong — creating vertex without partition key:
```python
# This will fail with 400 Bad Request
gremlin_client.submit(
    "g.addV('CoreRouter').property('id', 'CORE-SYD-01').property('RouterId', 'CORE-SYD-01')"
).all().result()
```

✅ Correct — point read with composite [partitionKey, id]:
```python
gremlin_client.submit(
    "g.V([pk, id_val])",
    bindings={"pk": "router", "id_val": "CORE-SYD-01"},
).all().result()
```

❌ Wrong — point read without partition key (triggers expensive fan-out):
```python
gremlin_client.submit("g.V('CORE-SYD-01')").all().result()
```

---

## 5. Edge Creation

✅ Correct — edge between two vertices using property lookups:
```python
gremlin_client.submit(
    "g.V().has('CoreRouter', 'RouterId', src)"
    ".addE('routes_via')"
    ".to(g.V().has('AggSwitch', 'SwitchId', dst))"
    ".property('bandwidth', bw)",
    bindings={"src": "CORE-SYD-01", "dst": "AGG-SYD-01", "bw": "100Gbps"},
).all().result()
```

❌ Wrong — using `from()` step (limited support in Cosmos DB):
```python
# Prefer .addE().to() over .addE().from()
g.V(src).addE('routes_via').from(g.V(dst))
```

---

## 6. Result Handling

✅ Correct — `.all().result()` for full result set:
```python
results = gremlin_client.submit("g.V().hasLabel('CoreRouter').valueMap(true)").all().result()
for vertex in results:
    print(vertex)
```

✅ Correct — `.one()` for single result:
```python
vertex = gremlin_client.submit(
    "g.V([pk, id_val])",
    bindings={"pk": "router", "id_val": "CORE-SYD-01"},
).one()
```

❌ Wrong — not calling `.result()` (returns a Future, not data):
```python
results = gremlin_client.submit("g.V()").all()  # This is a Future!
```

---

## 7. Cosmos DB-Specific Gremlin Constraints

✅ Correct — using supported steps only:
```python
# These Gremlin steps are supported by Cosmos DB:
"g.V().hasLabel('X').out('Y').has('Z', val).valueMap(true).limit(10)"
"g.V().hasLabel('X').outE('Y').inV().path()"
"g.V().groupCount().by(label)"
"g.addV('X').property('id', id).property('partitionKey', pk)"
"g.V().has('X', 'id', val).drop()"
```

❌ Wrong — using unsupported lambda steps:
```python
# Cosmos DB does NOT support lambda steps
"g.V().map{it.get().value('name')}"
"g.V().filter{it.get().label() == 'person'}"
```

❌ Wrong — using unsupported steps:
```python
"g.V().profile()"    # Not supported — use Azure Monitor
"g.V().subgraph('s')" # Not supported
"g.V().tree()"        # Not supported
```

---

## 8. Bicep Provisioning

✅ Correct — Cosmos DB account with `EnableGremlin` capability:
```bicep
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: accountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      { name: 'EnableGremlin' }
    ]
    locations: [
      { locationName: location, failoverPriority: 0 }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
  }
}
```

❌ Wrong — missing `EnableGremlin` capability (creates NoSQL account):
```bicep
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: accountName
  properties: {
    databaseAccountOfferType: 'Standard'
    // Missing capabilities: [{ name: 'EnableGremlin' }]
  }
}
```

✅ Correct — Gremlin graph with partition key:
```bicep
resource graph 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs@2024-11-15' = {
  name: graphName
  parent: database
  properties: {
    resource: {
      id: graphName
      partitionKey: {
        paths: ['/partitionKey']
        kind: 'Hash'
      }
    }
  }
}
```

❌ Wrong — using `sqlDatabases/containers` resource type for Gremlin:
```bicep
// This is for NoSQL API, not Gremlin API
resource container 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = { ... }
```

---

## 9. Connection Lifecycle

✅ Correct — singleton client, closed on shutdown:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    get_gremlin_client()  # warm
    yield
    close_gremlin_client()  # clean close
```

❌ Wrong — creating a new client per request:
```python
@app.get("/query")
async def query():
    c = client.Client(url=..., ...)  # Expensive! Creates new WebSocket
    result = c.submit("g.V()").all().result()
    c.close()
    return result
```

---

## 10. Error Handling

✅ Correct — catching Gremlin errors with status codes:
```python
from gremlin_python.driver.protocol import GremlinServerError

try:
    result = gremlin_client.submit("g.V('nonexistent')").all().result()
except GremlinServerError as e:
    if "404" in str(e) or "ResourceNotFound" in str(e):
        return None
    if "429" in str(e) or "RequestRateTooLarge" in str(e):
        # Retry with backoff
        await asyncio.sleep(1)
    raise
```

❌ Wrong — catching bare exceptions and swallowing errors:
```python
try:
    result = gremlin_client.submit(query).all().result()
except:
    pass  # Silently swallows rate limiting, auth failures, etc.
```
