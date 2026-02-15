# Topology & Routing Script Patterns

Extracted from the reference implementation in `data/scripts/generate_topology_data.py`
and `data/scripts/generate_routing_data.py`.

## Script Structure

Every topology generator follows this exact pattern:

```python
"""
Generate static topology CSV files for <domain> entity tables.

Outputs N CSV files:
  - Dim<EntityType1>.csv
  - Dim<EntityType2>.csv
  - ...
"""

import csv
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "<output_subdir>")


def write_csv(filename: str, headers: list[str], rows: list[list]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"  ✓ {filename} ({len(rows)} rows)")


def generate_<entity_type>() -> None:
    headers = ["<IdColumn>", "<Prop1>", "<Prop2>", ...]
    rows = [
        ["<ID-PREFIX>-<LOCATION>-<SEQ>", "value1", "value2", ...],
        ...
    ]
    write_csv("Dim<EntityType>.csv", headers, rows)


# ... one function per entity type ...


def main() -> None:
    print("Generating topology data ...")
    generate_<entity_type_1>()
    generate_<entity_type_2>()
    # ... in dependency order ...
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
```

## Entity ID Conventions

IDs are the **glue** between all components. They must be:

1. **Globally unique** across all entity types within a scenario
2. **Human-readable** — an operator looking at an alert should understand what the ID refers to
3. **Consistent** — the same ID format within each entity type
4. **Deterministic** — no randomization, same IDs every run

### ID Format: `{TYPE_PREFIX}-{LOCATION}-{QUALIFIER}-{SEQUENCE}`

Examples from the telco-noc reference:

| Entity Type | ID Pattern | Examples |
|-------------|-----------|----------|
| CoreRouter | `CORE-{CITY}-{NN}` | `CORE-SYD-01`, `CORE-MEL-01` |
| TransportLink | `LINK-{SRC}-{DST}-{TYPE}-{NN}` | `LINK-SYD-MEL-FIBRE-01` |
| AggSwitch | `AGG-{CITY}-{AREA}-{NN}` | `AGG-SYD-NORTH-01` |
| BaseStation | `GNB-{CITY}-{NNNN}` | `GNB-SYD-2041` |
| BGPSession | `BGP-{PEER_A}-{PEER_B}-{NN}` | `BGP-SYD-MEL-01` |
| MPLSPath | `MPLS-PATH-{SRC}-{DST}-{TYPE}` | `MPLS-PATH-SYD-MEL-PRIMARY` |
| Service | `{SVC_TYPE}-{QUALIFIER}` | `VPN-ACME-CORP`, `BB-BUNDLE-SYD-NORTH` |
| SLAPolicy | `SLA-{CUSTOMER}-{TIER}` | `SLA-ACME-GOLD` |

### Designing IDs for a New Domain

For a cloud datacenter scenario:

| Entity Type | Suggested Pattern | Examples |
|-------------|-------------------|----------|
| Region | `REGION-{NAME}` | `REGION-US-EAST` |
| AvailabilityZone | `AZ-{REGION}-{LETTER}` | `AZ-US-EAST-A` |
| Rack | `RACK-{AZ}-{NN}` | `RACK-US-EAST-A-01` |
| Host | `HOST-{RACK}-{NN}` | `HOST-US-EAST-A-01-03` |
| VirtualMachine | `VM-{HOST}-{NNNN}` | `VM-US-EAST-A-01-03-0001` |

The key principle: **IDs encode the hierarchy**, making graph traversals and
alert triage intuitive.

## Foreign Key Columns

Entities reference their parents via foreign key columns:

```python
def generate_agg_switches() -> None:
    headers = ["SwitchId", "City", "UplinkRouterId"]  # ← UplinkRouterId is FK
    rows = [
        ["AGG-SYD-NORTH-01", "Sydney", "CORE-SYD-01"],  # FK → DimCoreRouter
        ...
    ]
```

The `graph_schema.yaml` uses these FK columns to create edges:

```yaml
edges:
  - label: aggregates_to
    csv_file: DimAggSwitch.csv
    source:
      label: AggSwitch
      property: SwitchId
      column: SwitchId
    target:
      label: CoreRouter
      property: RouterId
      column: UplinkRouterId     # ← FK column becomes edge lookup
```

## Routing / Junction Tables

Junction tables (`Fact*.csv`) encode M:N relationships that can't be captured
by a single FK column:

### Path Hops Pattern (ordered traversal)

```python
def generate_mpls_path_hops() -> None:
    headers = ["PathId", "HopOrder", "NodeId", "NodeType"]
    rows = [
        # Path traverses: Router → Link → Router
        ["MPLS-PATH-SYD-MEL-PRIMARY", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-MEL-PRIMARY", 2, "LINK-SYD-MEL-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-MEL-PRIMARY", 3, "CORE-MEL-01", "CoreRouter"],
    ]
```

The `NodeType` column enables `filter` clauses in `graph_schema.yaml` to create
typed edges (e.g. only create `routes_via` edges to `TransportLink` nodes).

### Dependency Pattern (typed relationships)

```python
def generate_service_dependencies() -> None:
    headers = ["ServiceId", "DependsOnId", "DependsOnType", "DependencyStrength"]
    rows = [
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-SECONDARY", "MPLSPath", "SECONDARY"],
        ["BB-BUNDLE-SYD-NORTH", "AGG-SYD-NORTH-01", "AggSwitch", "PRIMARY"],
    ]
```

The `DependsOnType` column is used by `graph_schema.yaml` to create separate
edge definitions per target type (each with its own `filter` clause).

## Scale Guidelines

For a demo scenario, keep data small enough to visualize but rich enough to
investigate:

| Data type | Reference (telco-noc) | Guideline |
|-----------|----------------------|-----------|
| Core entities (routers/hosts) | 3 | 3–8 top-level entities |
| Mid-tier entities (switches/racks) | 6 | 2–3× core count |
| Leaf entities (base stations/VMs) | 8 | 1.5–3× mid-tier count |
| Services | 10 | ~10 covering 2–3 service types |
| Transport links / connections | 10 | Enough to show redundancy + failure paths |
| Junction table rows | ~30 | Cover key dependency chains |

Total vertex count: **30–60 nodes** — enough for a meaningful graph visualization
without cluttering the canvas.
