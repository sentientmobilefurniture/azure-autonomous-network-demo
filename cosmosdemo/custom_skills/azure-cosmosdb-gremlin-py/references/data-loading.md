# Data Loading — Network Topology into Cosmos DB Gremlin

Load the autonomous network demo's CSV-based topology data into an Azure Cosmos
DB for Apache Gremlin graph using the `gremlinpython` SDK.

---

## Graph Schema (Network Topology)

### Vertex Labels & Properties

| Label | Count | Partition Key | Key Properties |
|-------|-------|---------------|----------------|
| `CoreRouter` | 3 | `router` | RouterId, City, Region, Vendor, Model |
| `AggSwitch` | 6 | `switch` | SwitchId, City, Region, Vendor, Model |
| `BaseStation` | 8 | `basestation` | StationId, City, Type (4G/5G), Sector |
| `TransportLink` | 10 | `link` | LinkId, SourceId, TargetId, Bandwidth, Technology |
| `MPLSPath` | 5 | `path` | PathId, Label, IngressRouter, EgressRouter |
| `Service` | 10 | `service` | ServiceId, ServiceName, SLA_Tier, Priority |
| `SLAPolicy` | 5 | `policy` | PolicyId, Tier, MaxLatency, MinAvailability |
| `BGPSession` | 3 | `session` | SessionId, PeerAS, LocalAS, State |

**Total**: ~50 vertices, ~80 edges

### Edge Labels

| Label | From → To | Properties |
|-------|-----------|------------|
| `routes_via` | CoreRouter → AggSwitch | bandwidth, latency_ms |
| `aggregates` | AggSwitch → BaseStation | port, vlan |
| `carries` | TransportLink → Service | priority |
| `follows` | Service → MPLSPath | — |
| `bound_by` | Service → SLAPolicy | — |
| `depends_on` | Service → Service | dependency_strength |
| `peers_with` | CoreRouter → CoreRouter | via BGPSession |
| `monitors` | BGPSession → CoreRouter | — |

---

## Loading Strategy

### Option A: Parameterized Queries via Python (Recommended)

Use the `gremlinpython` client to load vertices and edges from CSV files. This
approach is portable, auditable, and works with any Cosmos DB Gremlin endpoint.

```python
import csv
from gremlin_python.driver import client, serializer
import os


def get_client():
    return client.Client(
        url=f"wss://{os.environ['COSMOS_GREMLIN_ENDPOINT']}:443/",
        traversal_source="g",
        username=f"/dbs/{os.environ['COSMOS_GREMLIN_DATABASE']}/colls/{os.environ['COSMOS_GREMLIN_GRAPH']}",
        password=os.environ["COSMOS_GREMLIN_PRIMARY_KEY"],
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )


def load_vertices_from_csv(
    gremlin_client: client.Client,
    csv_path: str,
    label: str,
    partition_key: str,
    id_field: str,
    property_fields: list[str],
):
    """Load vertices from a CSV file into the Cosmos DB Gremlin graph."""
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Build property chain dynamically
            prop_parts = [
                f".property('{field}', {field}_val)" for field in property_fields
            ]
            query = (
                "g.addV(label_val)"
                ".property('id', id_val)"
                ".property('partitionKey', pk_val)"
                + "".join(prop_parts)
            )
            bindings = {
                "label_val": label,
                "id_val": row[id_field],
                "pk_val": partition_key,
            }
            for field in property_fields:
                bindings[f"{field}_val"] = row[field]

            gremlin_client.submit(message=query, bindings=bindings).all().result()
            print(f"  Loaded {label}: {row[id_field]}")


def load_edges_from_csv(
    gremlin_client: client.Client,
    csv_path: str,
    edge_label: str,
    source_label: str,
    source_id_field: str,
    target_label: str,
    target_id_field: str,
    property_fields: list[str] | None = None,
):
    """Load edges from a CSV file into the Cosmos DB Gremlin graph."""
    property_fields = property_fields or []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prop_parts = [
                f".property('{field}', {field}_val)" for field in property_fields
            ]
            query = (
                f"g.V().has('{source_label}', '{source_id_field}', src_id)"
                f".addE(edge_label)"
                f".to(g.V().has('{target_label}', '{target_id_field}', dst_id))"
                + "".join(prop_parts)
            )
            bindings = {
                "src_id": row[source_id_field],
                "edge_label": edge_label,
                "dst_id": row[target_id_field],
            }
            for field in property_fields:
                bindings[f"{field}_val"] = row[field]

            gremlin_client.submit(message=query, bindings=bindings).all().result()
            print(f"  Loaded edge: {row[source_id_field]} -[{edge_label}]-> {row[target_id_field]}")
```

### Full Loading Script

```python
def load_network_topology():
    """Load complete network topology into Cosmos DB Gremlin."""
    c = get_client()

    try:
        # 1. Clear existing data (dev only!)
        print("Clearing existing graph data...")
        c.submit("g.V().drop()").all().result()

        # 2. Load dimension vertices
        print("Loading CoreRouters...")
        load_vertices_from_csv(
            c, "data/lakehouse/DimCoreRouter.csv",
            label="CoreRouter", partition_key="router", id_field="RouterId",
            property_fields=["RouterId", "City", "Region", "Vendor", "Model"],
        )

        print("Loading AggSwitches...")
        load_vertices_from_csv(
            c, "data/lakehouse/DimAggSwitch.csv",
            label="AggSwitch", partition_key="switch", id_field="SwitchId",
            property_fields=["SwitchId", "City", "Region", "Vendor", "Model"],
        )

        print("Loading BaseStations...")
        load_vertices_from_csv(
            c, "data/lakehouse/DimBaseStation.csv",
            label="BaseStation", partition_key="basestation", id_field="StationId",
            property_fields=["StationId", "City", "Type", "Sector"],
        )

        print("Loading Services...")
        load_vertices_from_csv(
            c, "data/lakehouse/DimService.csv",
            label="Service", partition_key="service", id_field="ServiceId",
            property_fields=["ServiceId", "ServiceName", "SLA_Tier", "Priority"],
        )

        print("Loading TransportLinks...")
        load_vertices_from_csv(
            c, "data/lakehouse/DimTransportLink.csv",
            label="TransportLink", partition_key="link", id_field="LinkId",
            property_fields=["LinkId", "SourceId", "TargetId", "Bandwidth", "Technology"],
        )

        print("Loading MPLSPaths...")
        load_vertices_from_csv(
            c, "data/lakehouse/DimMPLSPath.csv",
            label="MPLSPath", partition_key="path", id_field="PathId",
            property_fields=["PathId", "Label", "IngressRouter", "EgressRouter"],
        )

        print("Loading SLAPolicies...")
        load_vertices_from_csv(
            c, "data/lakehouse/DimSLAPolicy.csv",
            label="SLAPolicy", partition_key="policy", id_field="PolicyId",
            property_fields=["PolicyId", "Tier", "MaxLatency", "MinAvailability"],
        )

        print("Loading BGPSessions...")
        load_vertices_from_csv(
            c, "data/lakehouse/DimBGPSession.csv",
            label="BGPSession", partition_key="session", id_field="SessionId",
            property_fields=["SessionId", "PeerAS", "LocalAS", "State"],
        )

        # 3. Load relationship edges
        print("Loading routes_via edges...")
        load_edges_from_csv(
            c, "data/lakehouse/FactRouterSwitchLink.csv",
            edge_label="routes_via",
            source_label="CoreRouter", source_id_field="RouterId",
            target_label="AggSwitch", target_id_field="SwitchId",
            property_fields=["Bandwidth", "Latency_ms"],
        )

        print("Loading aggregates edges...")
        load_edges_from_csv(
            c, "data/lakehouse/FactSwitchStationLink.csv",
            edge_label="aggregates",
            source_label="AggSwitch", source_id_field="SwitchId",
            target_label="BaseStation", target_id_field="StationId",
        )

        print("Loading service dependency edges...")
        load_edges_from_csv(
            c, "data/lakehouse/FactServiceDependency.csv",
            edge_label="depends_on",
            source_label="Service", source_id_field="ServiceId",
            target_label="Service", target_id_field="DependsOnId",
            property_fields=["DependencyStrength"],
        )

        print("Loading SLA binding edges...")
        load_edges_from_csv(
            c, "data/lakehouse/FactServiceSLA.csv",
            edge_label="bound_by",
            source_label="Service", source_id_field="ServiceId",
            target_label="SLAPolicy", target_id_field="PolicyId",
        )

        # 4. Verify
        print("\nVerification:")
        vertex_counts = c.submit("g.V().groupCount().by(label)").all().result()
        print(f"  Vertices by label: {vertex_counts}")
        edge_counts = c.submit("g.E().groupCount().by(label)").all().result()
        print(f"  Edges by label: {edge_counts}")
        total_v = c.submit("g.V().count()").all().result()
        total_e = c.submit("g.E().count()").all().result()
        print(f"  Total: {total_v[0]} vertices, {total_e[0]} edges")

    finally:
        c.close()


if __name__ == "__main__":
    load_network_topology()
```

---

## Option B: Inline Data (No CSV Files)

For demos or testing, load topology data directly with hardcoded Gremlin:

```python
def load_inline_topology(c):
    """Load a minimal network topology without CSV files."""

    # Core Routers
    for router in [
        {"id": "CORE-SYD-01", "city": "Sydney", "region": "APAC"},
        {"id": "CORE-MEL-01", "city": "Melbourne", "region": "APAC"},
        {"id": "CORE-BRI-01", "city": "Brisbane", "region": "APAC"},
    ]:
        c.submit(
            "g.addV('CoreRouter')"
            ".property('id', id_val).property('partitionKey', 'router')"
            ".property('RouterId', id_val).property('City', city).property('Region', region)",
            bindings={"id_val": router["id"], "city": router["city"], "region": router["region"]},
        ).all().result()

    # Aggregation Switches (2 per router)
    for switch in [
        {"id": "AGG-SYD-01", "city": "Sydney", "router": "CORE-SYD-01"},
        {"id": "AGG-SYD-02", "city": "Sydney", "router": "CORE-SYD-01"},
        {"id": "AGG-MEL-01", "city": "Melbourne", "router": "CORE-MEL-01"},
        {"id": "AGG-MEL-02", "city": "Melbourne", "router": "CORE-MEL-01"},
        {"id": "AGG-BRI-01", "city": "Brisbane", "router": "CORE-BRI-01"},
        {"id": "AGG-BRI-02", "city": "Brisbane", "router": "CORE-BRI-01"},
    ]:
        c.submit(
            "g.addV('AggSwitch')"
            ".property('id', id_val).property('partitionKey', 'switch')"
            ".property('SwitchId', id_val).property('City', city)",
            bindings={"id_val": switch["id"], "city": switch["city"]},
        ).all().result()
        # Edge: router -> switch
        c.submit(
            "g.V().has('CoreRouter', 'RouterId', router_id)"
            ".addE('routes_via')"
            ".to(g.V().has('AggSwitch', 'SwitchId', switch_id))"
            ".property('bandwidth', '100Gbps')",
            bindings={"router_id": switch["router"], "switch_id": switch["id"]},
        ).all().result()
```

---

## Verification Queries

After loading, run these queries to validate the graph:

```python
# Total vertex count
c.submit("g.V().count()").all().result()
# Expected: [~50]

# Vertices by label
c.submit("g.V().groupCount().by(label)").all().result()
# Expected: [{'CoreRouter': 3, 'AggSwitch': 6, 'BaseStation': 8, ...}]

# Edge count
c.submit("g.E().count()").all().result()
# Expected: [~80]

# Edges by label
c.submit("g.E().groupCount().by(label)").all().result()

# Sample traversal: routers and their switches
c.submit(
    "g.V().hasLabel('CoreRouter').project('router','switches')"
    ".by('RouterId').by(out('routes_via').values('SwitchId').fold())"
).all().result()

# Connectivity check: every switch has a parent router
orphans = c.submit(
    "g.V().hasLabel('AggSwitch').not(__.in('routes_via')).values('SwitchId')"
).all().result()
assert len(orphans) == 0, f"Orphan switches found: {orphans}"
```

---

## Performance Considerations

| Consideration | Recommendation |
|---------------|----------------|
| **Batch size** | Submit vertices individually (Cosmos DB Gremlin doesn't support multi-statement batches) |
| **RU budgeting** | Each `addV` ≈ 10-15 RU, each `addE` ≈ 10-20 RU. Budget ~2000 RU for full topology load |
| **Rate limiting** | If you get 429 errors, add `time.sleep(0.1)` between submits or increase provisioned RU/s |
| **Idempotency** | Use `g.V().has(label, idField, id).fold().coalesce(unfold(), addV(label).property(...))` for upserts |
| **Ordering** | Load all vertices before edges (edges reference existing vertices) |
