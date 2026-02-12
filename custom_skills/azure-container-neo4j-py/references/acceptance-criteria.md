# Neo4j on Azure Container Apps — Acceptance Criteria

**SDK**: `neo4j`
**Version**: `>=6.1.0`
**Repository**: https://github.com/neo4j/neo4j-python-driver
**Docker Image**: `neo4j:2026.01.4-community`
**Purpose**: Skill testing acceptance criteria for validating generated code correctness

---

## 1. Correct Import Patterns

### 1.1 Driver Imports

#### ✅ CORRECT: Sync Driver
```python
from neo4j import GraphDatabase
```

#### ✅ CORRECT: Async Driver
```python
from neo4j import AsyncGraphDatabase
```

#### ✅ CORRECT: Routing Control
```python
from neo4j import GraphDatabase, RoutingControl
```

#### ✅ CORRECT: Auth Helpers
```python
from neo4j import GraphDatabase, basic_auth, bearer_auth, kerberos_auth
```

### 1.2 Anti-Patterns (ERRORS)

#### ❌ INCORRECT: Using deprecated package name
```python
# WRONG — neo4j-driver is deprecated since 6.0.0, no further updates
pip install neo4j-driver  # DO NOT USE
from neo4j_driver import GraphDatabase  # DOES NOT EXIST
```

#### ❌ INCORRECT: Importing from wrong module
```python
# WRONG — there is no neo4j.driver submodule
from neo4j.driver import GraphDatabase

# WRONG — AsyncGraphDatabase is in the main neo4j module, NOT in neo4j.aio
from neo4j.aio import AsyncGraphDatabase
```

#### ❌ INCORRECT: Old driver API patterns
```python
# WRONG — driver() doesn't take `database` parameter; use session(database=...) instead
driver = GraphDatabase.driver(URI, auth=AUTH, database="neo4j")
```

---

## 2. Driver Creation Patterns

### 2.1 ✅ CORRECT: Context Manager (Recommended)
```python
from neo4j import GraphDatabase

with GraphDatabase.driver(URI, auth=AUTH) as driver:
    driver.verify_connectivity()
    # ... use driver
# driver is automatically closed
```

### 2.2 ✅ CORRECT: Async Context Manager
```python
from neo4j import AsyncGraphDatabase

async with AsyncGraphDatabase.driver(URI, auth=AUTH) as driver:
    await driver.verify_connectivity()
    # ... use driver
# driver is automatically closed
```

### 2.3 ✅ CORRECT: Explicit Close
```python
driver = GraphDatabase.driver(URI, auth=AUTH)
# ... use driver
driver.close()
```

### 2.4 ✅ CORRECT: FastAPI Lifespan (Singleton Pattern)
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from neo4j import AsyncGraphDatabase

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.neo4j_driver = AsyncGraphDatabase.driver(URI, auth=AUTH)
    await app.state.neo4j_driver.verify_connectivity()
    yield
    await app.state.neo4j_driver.close()

app = FastAPI(lifespan=lifespan)
```

### 2.5 Anti-Patterns

#### ❌ INCORRECT: Creating driver per request
```python
# WRONG — driver should be a singleton; creating per request wastes connections
@app.get("/data")
async def get_data():
    driver = AsyncGraphDatabase.driver(URI, auth=AUTH)  # ← new driver per request!
    async with driver.session(database="neo4j") as session:
        result = await session.run("MATCH (n) RETURN n LIMIT 10")
        records = [record.data() async for record in result]
    await driver.close()
    return records
```

#### ❌ INCORRECT: Never closing the driver
```python
# WRONG — driver must be closed to release connections
driver = GraphDatabase.driver(URI, auth=AUTH)
# ... use driver in application
# BUG: driver.close() never called → connection leak
```

---

## 3. Authentication Patterns

### 3.1 ✅ CORRECT: Basic Auth with Tuple
```python
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
```

### 3.2 ✅ CORRECT: Basic Auth from Environment Variables
```python
import os

driver = GraphDatabase.driver(
    os.environ["NEO4J_BOLT_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)
```

### 3.3 Anti-Patterns

#### ❌ INCORRECT: Hardcoded credentials
```python
# WRONG — credentials should come from env vars, Key Vault, or config
driver = GraphDatabase.driver("bolt://prod-server:7687", auth=("neo4j", "s3cretP@ss"))
```

#### ❌ INCORRECT: Passing auth as a dict
```python
# WRONG — auth takes a tuple (username, password), not a dict
driver = GraphDatabase.driver(URI, auth={"username": "neo4j", "password": "pass"})
```

---

## 4. Query Execution Patterns

### 4.1 ✅ CORRECT: execute_query() with Parameters (Preferred)
```python
records, summary, keys = driver.execute_query(
    "MATCH (r:Router {id: $id}) RETURN r.city AS city",
    id="CORE-SYD-01",
    database_="neo4j",
)
```

### 4.2 ✅ CORRECT: execute_query() with Routing Control
```python
from neo4j import RoutingControl

# Read
records, _, _ = driver.execute_query(
    "MATCH (r:Router) RETURN r.id",
    database_="neo4j",
    routing_=RoutingControl.READ,
)

# Write (default, but explicit is clearer)
records, _, _ = driver.execute_query(
    "CREATE (r:Router {id: $id})",
    id="NEW-01",
    database_="neo4j",
    routing_=RoutingControl.WRITE,
)
```

### 4.3 ✅ CORRECT: Session with execute_read/execute_write
```python
def get_router(tx, router_id):
    result = tx.run(
        "MATCH (r:Router {id: $id}) RETURN r.city AS city",
        id=router_id,
    )
    return [record.data() for record in result]

with driver.session(database="neo4j") as session:
    data = session.execute_read(get_router, "CORE-SYD-01")
```

### 4.4 ✅ CORRECT: Async Session Query
```python
async with driver.session(database="neo4j") as session:
    result = await session.run(
        "MATCH (r:Router) RETURN r.id AS id",
    )
    records = [record.data() async for record in result]
```

### 4.5 Anti-Patterns

#### ❌ INCORRECT: String interpolation in queries (INJECTION RISK)
```python
# WRONG — Cypher injection vulnerability!
router_id = user_input
result = session.run(f"MATCH (r:Router {{id: '{router_id}'}}) RETURN r")

# WRONG — same issue with format()
result = session.run("MATCH (r:Router {{id: '{}'}}) RETURN r".format(router_id))

# CORRECT — use parameterised queries
result = session.run("MATCH (r:Router {id: $id}) RETURN r", id=router_id)
```

#### ❌ INCORRECT: Forgetting database_ parameter
```python
# WRONG — in Neo4j 5+/2026+, omitting database_ uses the default database,
# which may not be "neo4j" if the server is configured differently.
# Always be explicit.
records, _, _ = driver.execute_query("MATCH (n) RETURN count(n)")
# ↑ Missing database_="neo4j"
```

#### ❌ INCORRECT: Using session.run() for writes without transaction
```python
# WRONG — session.run() in auto-commit mode doesn't retry on transient errors.
# Use execute_write() for important writes.
with driver.session(database="neo4j") as session:
    session.run("CREATE (r:Router {id: $id})", id="NEW-01")  # no retry!

# CORRECT — execute_write handles retries
def create_router(tx, router_id):
    tx.run("CREATE (r:Router {id: $id})", id=router_id)

with driver.session(database="neo4j") as session:
    session.execute_write(create_router, "NEW-01")
```

---

## 5. Docker / Container Configuration

### 5.1 ✅ CORRECT: Neo4j Docker Run
```bash
docker run \
    --name neo4j \
    --publish 7474:7474 \
    --publish 7687:7687 \
    --env NEO4J_AUTH=neo4j/your_password \
    --env NEO4J_PLUGINS='["apoc"]' \
    --volume neo4j-data:/data \
    --detach \
    neo4j:2026.01.4-community
```

### 5.2 ✅ CORRECT: Environment Variable Naming
```bash
# Config: server.memory.pagecache.size → NEO4J_server_memory_pagecache_size
NEO4J_server_memory_pagecache_size=512M

# Config: server.memory.heap.max_size → NEO4J_server_memory_heap_max__size
# Note: underscore in original config becomes DOUBLE underscore
NEO4J_server_memory_heap_max__size=512M
```

### 5.3 Anti-Patterns

#### ❌ INCORRECT: Using :latest tag
```bash
# WRONG — unpredictable; may break on image updates
docker run neo4j:latest
docker run neo4j:community

# CORRECT — pin to specific version
docker run neo4j:2026.01.4-community
```

#### ❌ INCORRECT: No persistent volume
```bash
# WRONG — data is lost when container stops
docker run --publish 7474:7474 --publish 7687:7687 neo4j:2026.01.4-community

# CORRECT — mount /data
docker run --volume neo4j-data:/data --publish 7474:7474 --publish 7687:7687 neo4j:2026.01.4-community
```

#### ❌ INCORRECT: Wrong env var for plugins
```bash
# WRONG — must be JSON array, not comma-separated
NEO4J_PLUGINS="apoc,gds"

# WRONG — must be JSON list syntax
NEO4J_PLUGINS="apoc"

# CORRECT
NEO4J_PLUGINS='["apoc"]'
```

#### ❌ INCORRECT: Single underscore for config with underscores
```bash
# WRONG — max_size has an underscore, so it needs DOUBLE underscore
NEO4J_server_memory_heap_max_size=512M

# CORRECT
NEO4J_server_memory_heap_max__size=512M
```

---

## 6. Azure Container Apps — Bicep

### 6.1 ✅ CORRECT: Internal-Only Ingress for Neo4j
```bicep
configuration: {
  ingress: {
    external: false        // internal — only accessible within managed environment
    targetPort: 7687       // Bolt protocol
    transport: 'tcp'
  }
}
```

### 6.2 ✅ CORRECT: Single Replica (Community Edition)
```bicep
scale: {
  minReplicas: 1
  maxReplicas: 1   // Community Edition is single-instance only
}
```

### 6.3 ✅ CORRECT: Azure Files Volume for Persistence
```bicep
template: {
  containers: [{
    // ...
    volumeMounts: [{ volumeName: 'neo4j-data', mountPath: '/data' }]
  }]
  volumes: [{
    name: 'neo4j-data'
    storageType: 'AzureFile'
    storageName: 'neo4jdata'
  }]
}
```

### 6.4 Anti-Patterns

#### ❌ INCORRECT: External ingress exposing Neo4j publicly
```bicep
// WRONG — Neo4j should not be publicly accessible
configuration: {
  ingress: {
    external: true         // ← security risk!
    targetPort: 7687
  }
}
```

#### ❌ INCORRECT: Multiple replicas with Community Edition
```bicep
// WRONG — Neo4j Community Edition does not support clustering
scale: {
  minReplicas: 1
  maxReplicas: 3   // ← Community Edition is single-instance only!
}
```

#### ❌ INCORRECT: No volume — ephemeral data
```bicep
// WRONG — no volume mount means data loss on container restart
template: {
  containers: [{
    name: 'neo4j'
    image: 'neo4j:2026.01.4-community'
    // ← missing volumeMounts!
  }]
  // ← missing volumes!
}
```

---

## 7. Result Handling

### 7.1 ✅ CORRECT: Accessing Records
```python
records, summary, keys = driver.execute_query(
    "MATCH (r:Router) RETURN r.id AS id, r.city AS city",
    database_="neo4j",
)

for record in records:
    record["id"]      # access by key
    record.data()     # as dict: {"id": "...", "city": "..."}
```

### 7.2 ✅ CORRECT: Accessing Summary Counters
```python
summary = driver.execute_query(
    "CREATE (r:Router {id: $id})", id="NEW-01", database_="neo4j"
).summary

print(summary.counters.nodes_created)           # int
print(summary.counters.relationships_created)    # int
print(summary.counters.properties_set)           # int
print(summary.result_available_after)            # milliseconds
```

### 7.3 Anti-Patterns

#### ❌ INCORRECT: Consuming result outside session
```python
# WRONG — result is tied to the session; accessing after close raises error
with driver.session(database="neo4j") as session:
    result = session.run("MATCH (r:Router) RETURN r.id")

# BUG: session is closed, result can no longer be consumed
for record in result:  # ← ResultConsumedError!
    print(record)

# CORRECT — consume within the session
with driver.session(database="neo4j") as session:
    result = session.run("MATCH (r:Router) RETURN r.id")
    records = list(result)  # consume immediately
```

---

## 8. Testing Patterns

### 8.1 ✅ CORRECT: Pytest Fixture with Driver
```python
import pytest
from neo4j import GraphDatabase

@pytest.fixture(scope="session")
def neo4j_driver():
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "testpass"))
    driver.verify_connectivity()
    yield driver
    driver.close()

@pytest.fixture(autouse=True)
def clean_db(neo4j_driver):
    """Clear database before each test."""
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n", database_="neo4j")
    yield
```

### 8.2 ✅ CORRECT: Async Pytest Fixture
```python
import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase

@pytest_asyncio.fixture(scope="session")
async def neo4j_driver():
    driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "testpass"))
    await driver.verify_connectivity()
    yield driver
    await driver.close()
```

### 8.3 Anti-Patterns

#### ❌ INCORRECT: Not cleaning up between tests
```python
# WRONG — tests pollute each other's data
def test_create_router(neo4j_driver):
    neo4j_driver.execute_query(
        "CREATE (r:Router {id: 'TEST-01'})", database_="neo4j"
    )

def test_count_routers(neo4j_driver):
    records, _, _ = neo4j_driver.execute_query(
        "MATCH (r:Router) RETURN count(r) AS count", database_="neo4j"
    )
    assert records[0]["count"] == 0  # ← FAILS because test_create_router left data!
```
