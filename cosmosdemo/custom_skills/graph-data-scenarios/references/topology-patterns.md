# Topology & Routing Script Patterns

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

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "entities")


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
    # ... call in dependency order (parents before children) ...
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
```

## Entity ID Conventions

IDs are the **glue** between all data components. They must be:

1. **Globally unique** across all entity types within a scenario
2. **Human-readable** — an operator looking at an alert should understand the ID
3. **Consistent** — same format within each entity type
4. **Deterministic** — no randomization, same IDs every run

### ID Format: `{TYPE_PREFIX}-{LOCATION}-{QUALIFIER}-{SEQUENCE}`

Examples across all three reference scenarios:

**Telco-NOC:**

| Entity Type | ID Pattern | Examples |
|-------------|-----------|----------|
| CoreRouter | `CORE-{CITY}-{NN}` | `CORE-SYD-01`, `CORE-MEL-01` |
| TransportLink | `LINK-{SRC}-{DST}-{TYPE}-{NN}` | `LINK-SYD-MEL-FIBRE-01` |
| AggSwitch | `AGG-{CITY}-{AREA}-{NN}` | `AGG-SYD-NORTH-01` |
| BaseStation | `GNB-{CITY}-{NNNN}` | `GNB-SYD-2041` |
| BGPSession | `BGP-{PEER_A}-{PEER_B}-{NN}` | `BGP-SYD-MEL-01` |
| MPLSPath | `MPLS-PATH-{SRC}-{DST}-{TYPE}` | `MPLS-PATH-SYD-MEL-PRIMARY` |
| Service | `{SVC_TYPE}-{QUALIFIER}` | `VPN-ACME-CORP`, `BB-BUNDLE-SYD-NORTH`, `MOB-5G-SYD-2041` |
| SLAPolicy | `SLA-{CUSTOMER}-{TIER}` | `SLA-ACME-GOLD` |

**Cloud-Outage:**

| Entity Type | ID Pattern | Examples |
|-------------|-----------|----------|
| Region | `REGION-{NAME}` | `REGION-US-EAST`, `REGION-EU-WEST` |
| AvailabilityZone | `AZ-{REGION}-{LETTER}` | `AZ-US-EAST-A`, `AZ-US-EAST-B` |
| Rack | `RACK-{AZ}-{NN}` | `RACK-US-EAST-A-01` |
| Host | `HOST-{AZ_SHORT}-{RACK}-{NN}` | `HOST-USE-A-01-01` |
| VirtualMachine | `VM-{HOST_SHORT}-{NNNN}` | `VM-USE-A-01-01-0001` |
| LoadBalancer | `LB-{REGION}-{TYPE}-{NN}` | `LB-US-EAST-WEB-01` |
| Service | `SVC-{NAME}` | `SVC-WEB-FRONTEND`, `SVC-PAYMENT-API` |
| SLAPolicy | `SLA-{SERVICE}-{TIER}` | `SLA-WEB-FRONTEND-GOLD` |

**Customer-Recommendation:**

| Entity Type | ID Pattern | Examples |
|-------------|-----------|----------|
| CustomerSegment | `SEG-{NAME}` | `SEG-VIP`, `SEG-NEW`, `SEG-CASUAL` |
| Customer | `CUST-{NNNN}` | `CUST-0001`, `CUST-0015` |
| ProductCategory | `CAT-{NAME}` | `CAT-ELECTRONICS`, `CAT-FASHION` |
| Product | `PROD-{NNNN}` | `PROD-0001`, `PROD-0042` |
| Campaign | `CAMP-{NAME}` | `CAMP-SUMMER-SALE`, `CAMP-VIP-EXCLUSIVE` |
| Supplier | `SUP-{NAME}` | `SUP-TECHCORP`, `SUP-FASHIONHUB` |

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

## Cloud Example — Complete Topology Generator

```python
"""
Generate static topology CSV files for cloud datacenter entity tables.
Outputs 8 CSV files: DimRegion, DimAvailabilityZone, DimRack, DimHost,
DimVirtualMachine, DimLoadBalancer, DimService, DimSLAPolicy.
"""
import csv
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "entities")

def write_csv(filename: str, headers: list[str], rows: list[list]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"  ✓ {filename} ({len(rows)} rows)")

def generate_regions() -> None:
    headers = ["RegionId", "RegionName", "Country", "Provider"]
    rows = [
        ["REGION-US-EAST", "US East", "United States", "CloudCorp"],
        ["REGION-US-WEST", "US West", "United States", "CloudCorp"],
        ["REGION-EU-WEST", "EU West", "Ireland", "CloudCorp"],
    ]
    write_csv("DimRegion.csv", headers, rows)

def generate_availability_zones() -> None:
    headers = ["AZId", "AZName", "RegionId", "CoolingSystem", "PowerFeedCount"]
    rows = [
        ["AZ-US-EAST-A", "US-East-AZ-A", "REGION-US-EAST", "CRAC-UNIT-A1", 2],
        ["AZ-US-EAST-B", "US-East-AZ-B", "REGION-US-EAST", "CRAC-UNIT-B1", 2],
        ["AZ-US-WEST-A", "US-West-AZ-A", "REGION-US-WEST", "CRAC-UNIT-A1", 2],
        ["AZ-EU-WEST-A", "EU-West-AZ-A", "REGION-EU-WEST", "CRAC-UNIT-A1", 2],
    ]
    write_csv("DimAvailabilityZone.csv", headers, rows)

# ... generate_racks(), generate_hosts(), generate_vms(), etc.
# Each follows the same pattern: headers → hardcoded rows → write_csv()

def main() -> None:
    print("Generating cloud topology data...")
    generate_regions()
    generate_availability_zones()
    generate_racks()
    generate_hosts()
    generate_virtual_machines()
    generate_load_balancers()
    generate_services()
    generate_sla_policies()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")

if __name__ == "__main__":
    main()
```

## Routing / Junction Tables

Junction tables (`Fact*.csv`) encode M:N relationships.

### Path Hops Pattern (ordered traversal)

```python
def generate_mpls_path_hops() -> None:
    headers = ["PathId", "HopOrder", "NodeId", "NodeType"]
    rows = [
        # Path: Router → Link → Router
        ["MPLS-PATH-SYD-MEL-PRIMARY", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-MEL-PRIMARY", 2, "LINK-SYD-MEL-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-MEL-PRIMARY", 3, "CORE-MEL-01", "CoreRouter"],
    ]
    write_csv("FactMPLSPathHops.csv", headers, rows)
```

The `NodeType` column enables `filter` clauses in `graph_schema.yaml`.

### Dependency Pattern (typed relationships)

```python
def generate_service_dependencies() -> None:
    headers = ["ServiceId", "DependsOnId", "DependsOnType", "DependencyStrength"]
    rows = [
        # Services depend on different entity types
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-SECONDARY", "MPLSPath", "SECONDARY"],
        ["BB-BUNDLE-SYD-NORTH", "AGG-SYD-NORTH-01", "AggSwitch", "PRIMARY"],
        ["MOB-5G-SYD-2041", "GNB-SYD-2041", "BaseStation", "PRIMARY"],
    ]
    write_csv("FactServiceDependency.csv", headers, rows)
```

The `DependsOnType` column is used by `graph_schema.yaml` to create separate
edge definitions per target type (each with its own `filter` clause).

### LB-to-VM Routing Pattern (load balancer backends)

```python
def generate_lb_backends() -> None:
    headers = ["LBId", "BackendId", "BackendType", "Weight", "HealthStatus"]
    rows = [
        ["LB-US-EAST-WEB-01", "VM-USE-A-01-01-0001", "VirtualMachine", 1, "Healthy"],
        ["LB-US-EAST-WEB-01", "VM-USE-A-02-01-0002", "VirtualMachine", 1, "Healthy"],
        ["LB-US-EAST-WEB-01", "VM-USE-B-01-01-0004", "VirtualMachine", 1, "Healthy"],
    ]
    write_csv("FactLBBackend.csv", headers, rows)
```

## Scale Guidelines

Keep data small enough to visualize but rich enough to investigate:

| Data type | Reference (telco-noc) | Guideline |
|-----------|----------------------|-----------|
| Core entities (routers/regions) | 3 | 3–8 top-level entities |
| Mid-tier entities (switches/racks) | 6 | 2–3× core count |
| Leaf entities (base stations/VMs) | 8 | 1.5–3× mid-tier count |
| Services | 10 | ~10 covering 2–3 service types |
| Transport/connections | 10 | Enough to show redundancy + failure paths |
| Junction table rows | ~30 | Cover key dependency chains |

Total vertex count: **30–60 nodes** — meaningful graph without cluttering the canvas.
