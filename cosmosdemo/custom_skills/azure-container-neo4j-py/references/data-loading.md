# Neo4j Data Loading — Reference Guide

## Loading Strategies

| Strategy | Best For | Requires Container Access? |
|----------|----------|---------------------------|
| `driver.execute_query()` with `UNWIND` | Small-medium datasets (<10k rows) | No — runs via Bolt |
| `session.execute_write()` with batching | Medium datasets with retry needs | No — runs via Bolt |
| `LOAD CSV` | Large datasets from mounted files | Yes — CSVs in `/import` |
| `neo4j-admin database import` | Initial bulk load (millions) | Yes — CLI access |

For demo-sized graphs (50–200 nodes), **parameterised `UNWIND` via the driver**
is the simplest and most portable approach.

---

## Parameterised Loading (Recommended for Demos)

### Load Nodes from CSV via Python Driver

```python
import csv
import os
from neo4j import GraphDatabase

URI = os.environ["NEO4J_BOLT_URI"]
AUTH = (os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
DB = os.getenv("NEO4J_DATABASE", "neo4j")


def load_csv_as_nodes(driver, csv_path: str, label: str, primary_key: str):
    """Load a CSV file as Neo4j nodes with the given label."""
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print(f"  Skipping {csv_path} — empty")
        return

    # Build SET clause dynamically from CSV headers
    props = [k for k in rows[0].keys() if k != primary_key]
    set_clause = ", ".join(f"n.{k} = row.{k}" for k in props)

    query = (
        f"UNWIND $rows AS row "
        f"MERGE (n:{label} {{{primary_key}: row.{primary_key}}}) "
        f"SET {set_clause}"
    )

    driver.execute_query(query, rows=rows, database_=DB)
    print(f"  Loaded {len(rows)} {label} nodes")


with GraphDatabase.driver(URI, auth=AUTH) as driver:
    driver.verify_connectivity()

    load_csv_as_nodes(driver, "data/lakehouse/DimCoreRouter.csv", "CoreRouter", "RouterId")
    load_csv_as_nodes(driver, "data/lakehouse/DimAggSwitch.csv", "AggSwitch", "SwitchId")
    load_csv_as_nodes(driver, "data/lakehouse/DimBaseStation.csv", "BaseStation", "StationId")
    load_csv_as_nodes(driver, "data/lakehouse/DimTransportLink.csv", "TransportLink", "LinkId")
    load_csv_as_nodes(driver, "data/lakehouse/DimMPLSPath.csv", "MPLSPath", "PathId")
    load_csv_as_nodes(driver, "data/lakehouse/DimService.csv", "Service", "ServiceId")
    load_csv_as_nodes(driver, "data/lakehouse/DimSLAPolicy.csv", "SLAPolicy", "SLAPolicyId")
    load_csv_as_nodes(driver, "data/lakehouse/DimBGPSession.csv", "BGPSession", "SessionId")
```

### Load Relationships from Foreign Keys

```python
def load_fk_relationships(
    driver,
    source_label: str,
    source_key: str,
    target_label: str,
    target_key: str,
    rel_type: str,
    csv_path: str,
    fk_column: str,
):
    """Create relationships from a foreign key column within a Dim CSV."""
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    pairs = [
        {"source_id": row[source_key], "target_id": row[fk_column]}
        for row in rows
        if row.get(fk_column)
    ]

    if not pairs:
        return

    query = (
        f"UNWIND $pairs AS pair "
        f"MATCH (s:{source_label} {{{source_key}: pair.source_id}}) "
        f"MATCH (t:{target_label} {{{target_key}: pair.target_id}}) "
        f"MERGE (s)-[:{rel_type}]->(t)"
    )

    driver.execute_query(query, pairs=pairs, database_=DB)
    print(f"  Created {len(pairs)} {rel_type} relationships")


with GraphDatabase.driver(URI, auth=AUTH) as driver:
    # AggSwitch -[:UPLINKS_TO]-> CoreRouter
    load_fk_relationships(
        driver, "AggSwitch", "SwitchId", "CoreRouter", "RouterId",
        "UPLINKS_TO", "data/lakehouse/DimAggSwitch.csv", "UplinkRouterId",
    )

    # BaseStation -[:CONNECTS_TO]-> AggSwitch
    load_fk_relationships(
        driver, "BaseStation", "StationId", "AggSwitch", "SwitchId",
        "CONNECTS_TO", "data/lakehouse/DimBaseStation.csv", "AggSwitchId",
    )

    # TransportLink -[:CONNECTS]-> CoreRouter (source)
    load_fk_relationships(
        driver, "TransportLink", "LinkId", "CoreRouter", "RouterId",
        "CONNECTS", "data/lakehouse/DimTransportLink.csv", "SourceRouterId",
    )

    # TransportLink -[:CONNECTS]-> CoreRouter (target)
    load_fk_relationships(
        driver, "TransportLink", "LinkId", "CoreRouter", "RouterId",
        "CONNECTS", "data/lakehouse/DimTransportLink.csv", "TargetRouterId",
    )

    # SLAPolicy -[:GOVERNS]-> Service
    load_fk_relationships(
        driver, "SLAPolicy", "SLAPolicyId", "Service", "ServiceId",
        "GOVERNS", "data/lakehouse/DimSLAPolicy.csv", "ServiceId",
    )

    # BGPSession -[:PEERS_WITH]-> CoreRouter (PeerA)
    load_fk_relationships(
        driver, "BGPSession", "SessionId", "CoreRouter", "RouterId",
        "PEERS_WITH", "data/lakehouse/DimBGPSession.csv", "PeerARouterId",
    )

    # BGPSession -[:PEERS_WITH]-> CoreRouter (PeerB)
    load_fk_relationships(
        driver, "BGPSession", "SessionId", "CoreRouter", "RouterId",
        "PEERS_WITH", "data/lakehouse/DimBGPSession.csv", "PeerBRouterId",
    )
```

### Load Relationships from Fact Tables

```python
def load_fact_relationships(
    driver,
    csv_path: str,
    source_label: str,
    source_key_col: str,
    target_label: str,
    target_key_col: str,
    rel_type: str,
    rel_properties: list[str] | None = None,
):
    """Create relationships from a Fact CSV with optional properties."""
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return

    rel_props = ""
    if rel_properties:
        props = ", ".join(f"{p}: row.{p}" for p in rel_properties)
        rel_props = f" {{{props}}}"

    query = (
        f"UNWIND $rows AS row "
        f"MATCH (s:{source_label} {{{source_key_col.split('.')[0] if '.' in source_key_col else 'id'}: row.source_id}}) "
        f"MATCH (t:{target_label} {{id: row.target_id}}) "
        f"MERGE (s)-[:{rel_type}{rel_props}]->(t)"
    )

    # Normalise column names
    data = [
        {"source_id": row[source_key_col], "target_id": row[target_key_col], **row}
        for row in rows
    ]

    driver.execute_query(query, rows=data, database_=DB)
    print(f"  Created {len(data)} {rel_type} relationships from {csv_path}")
```

---

## Indexes and Constraints

Create indexes BEFORE loading data for better MERGE performance:

```python
def create_indexes(driver):
    """Create uniqueness constraints (which also create indexes) for all entity types."""
    constraints = [
        ("CoreRouter", "RouterId"),
        ("AggSwitch", "SwitchId"),
        ("BaseStation", "StationId"),
        ("TransportLink", "LinkId"),
        ("MPLSPath", "PathId"),
        ("Service", "ServiceId"),
        ("SLAPolicy", "SLAPolicyId"),
        ("BGPSession", "SessionId"),
    ]

    for label, key in constraints:
        driver.execute_query(
            f"CREATE CONSTRAINT {label.lower()}_{key.lower()} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE",
            database_=DB,
        )
        print(f"  Constraint: {label}.{key}")


with GraphDatabase.driver(URI, auth=AUTH) as driver:
    create_indexes(driver)
```

---

## Graph Reset (Clear All Data)

```python
def reset_graph(driver):
    """Delete all nodes and relationships. Use before reloading."""
    summary = driver.execute_query(
        "MATCH (n) DETACH DELETE n",
        database_=DB,
    ).summary
    print(
        f"  Deleted {summary.counters.nodes_deleted} nodes, "
        f"{summary.counters.relationships_deleted} relationships"
    )
```

---

## Loading via LOAD CSV (File-Based)

If CSV files are mounted to the Neo4j container's `/import` directory:

```python
# Mount: --volume ./data/lakehouse:/var/lib/neo4j/import

driver.execute_query(
    """
    LOAD CSV WITH HEADERS FROM 'file:///DimCoreRouter.csv' AS row
    MERGE (r:CoreRouter {RouterId: row.RouterId})
    SET r.City = row.City,
        r.Region = row.Region,
        r.Vendor = row.Vendor,
        r.Model = row.Model
    """,
    database_="neo4j",
)
```

### Caveats with LOAD CSV

1. **File location**: CSV must be in `/var/lib/neo4j/import` (the Neo4j default
   `server.directories.import` path).
2. **All values are strings**: `LOAD CSV` returns all values as strings. Use
   `toInteger()`, `toFloat()`, `toBoolean()` for type conversion:
   ```cypher
   SET r.CapacityGbps = toInteger(row.CapacityGbps)
   ```
3. **No headers?**: Without `WITH HEADERS`, access columns by index: `row[0]`.
4. **Large files**: Use `USING PERIODIC COMMIT 1000` before `LOAD CSV` to batch
   commits (reduces memory pressure).

---

## Verification Queries

After loading, verify the graph:

```python
def verify_graph(driver):
    """Print node and relationship counts by type."""
    # Node counts
    records, _, _ = driver.execute_query(
        "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY label",
        database_=DB,
    )
    print("Nodes:")
    for r in records:
        print(f"  {r['label']}: {r['count']}")

    # Relationship counts
    records, _, _ = driver.execute_query(
        "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY type",
        database_=DB,
    )
    print("Relationships:")
    for r in records:
        print(f"  {r['type']}: {r['count']}")


with GraphDatabase.driver(URI, auth=AUTH) as driver:
    verify_graph(driver)
```

Expected output for the network demo:
```
Nodes:
  AggSwitch: 6
  BaseStation: 8
  BGPSession: 3
  CoreRouter: 3
  MPLSPath: 5
  SLAPolicy: 5
  Service: 10
  TransportLink: 10
Relationships:
  CONNECTS: 20
  CONNECTS_TO: 8
  DEPENDS_ON: ~15
  GOVERNS: 5
  HAS_HOP: ~15
  PEERS_WITH: 6
  UPLINKS_TO: 6
```

---

## Best Practices

1. **Always `MERGE`, never `CREATE`** for idempotent loading — re-running the
   script should be safe.

2. **Create constraints first** — uniqueness constraints also create indexes,
   making `MERGE` lookups O(log n) instead of O(n).

3. **Use `UNWIND` for batch loading** — single `UNWIND $rows` query is much
   faster than looping with individual `CREATE` calls.

4. **Load nodes before relationships** — relationships reference existing nodes
   via `MATCH`, so nodes must exist first.

5. **Use `execute_write()` for transactional loading** — provides automatic
   retry on transient errors (deadlocks, leader changes).

6. **Type-cast CSV values** — CSV values are strings. Convert numeric properties:
   ```python
   rows = [
       {**row, "CapacityGbps": int(row["CapacityGbps"])}
       for row in csv.DictReader(f)
   ]
   ```
