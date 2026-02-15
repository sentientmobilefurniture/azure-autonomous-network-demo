# Ticket Format & Graph Schema Format

## Ticket `.txt` Format

Historical incident tickets are indexed into Azure AI Search for RAG retrieval.
Each ticket is a plain `.txt` file with structured fields that the search indexer
parses. The agent uses these during investigation to find precedent incidents.

### File Naming

```
{TICKET_ID}.txt
```

Example: `INC-2025-08-14-0042.txt`

Ticket IDs follow the pattern: `INC-{YYYY}-{MM}-{DD}-{NNNN}`

### Required Fields

```
Incident: INC-2025-08-14-0042
Title: Fibre cut SYD-MEL corridor - contractor damage
Severity: P1
Root Cause: LINK-SYD-MEL-FIBRE-01
Root Cause Type: FIBRE_CUT
Created: 2025-08-14T03:22:15Z
Resolved: 2025-08-14T09:22:15Z
SLA Breached: No

Description:
Third-party contractor struck fibre conduit during road works on Hume Highway.
Complete loss of light on LINK-SYD-MEL-FIBRE-01. 1,847 downstream alerts generated.

Detection Method:
Automated alert storm detection

Resolution:
Traffic rerouted to LINK-SYD-MEL-FIBRE-02 within 45 seconds. Physical repair
completed in 6 hours by field team.

Customer Impact:
- VPN-ACME-CORP
- VPN-BIGBANK
- BB-BUNDLE-SYD-NORTH

Services Affected: 3
Alerts Generated: 1847
Alerts Suppressed: 1846
Time to Detect: 8 seconds
Time to Reroute: 45 seconds
Time to Resolve: 360 minutes

Lessons Learned:
Alternate path FIBRE-02 had sufficient capacity (38% utilisation). Consider
pre-provisioned automatic failover for enterprise VPN customers.
```

### Generation Pattern

```python
def generate_tickets() -> list[dict]:
    return [
        {
            "ticket_id": "INC-2025-08-14-0042",
            "title": "Fibre cut SYD-MEL corridor - contractor damage",
            "severity": "P1",
            "root_cause": "LINK-SYD-MEL-FIBRE-01",    # ← Must match entity ID
            "root_cause_type": "FIBRE_CUT",
            "description": "...",
            "detection_method": "Automated alert storm detection",
            "resolution": "...",
            "customer_impact": ["VPN-ACME-CORP", "VPN-BIGBANK"],  # ← Must match entity IDs
            "services_affected": 2,
            "alerts_generated": 1847,
            "alerts_suppressed": 1846,
            "time_to_detect_seconds": 8,
            "time_to_reroute_seconds": 45,
            "time_to_resolve_minutes": 360,
            "sla_breached": False,
            "created_at": "2025-08-14T03:22:15Z",
            "resolved_at": "2025-08-14T09:22:15Z",
            "lessons_learned": "..."
        },
        # ... 8-12 total tickets
    ]
```

### Entity ID Cross-References

Every ticket must reference real entity IDs:

| Field | References |
|-------|-----------|
| `root_cause` | A vertex ID from any `Dim*.csv` |
| `customer_impact` | Service IDs from `DimService.csv` (or equivalent) |
| `root_cause_type` | Should align with `AlertType` values used in `AlertStream.csv` |

### Ticket Diversity Guidelines

Cover a variety of root cause types across your 8–12 tickets:

| Category | Examples (telco) | Examples (cloud) |
|----------|-----------------|------------------|
| Physical failure | `FIBRE_CUT`, `AMPLIFIER_FAILURE` | `DISK_FAILURE`, `NIC_FAILURE` |
| Hardware degradation | `HARDWARE_DEGRADATION` | `MEMORY_ECC_ERROR` |
| Software bug | `SOFTWARE_BUG` | `KERNEL_PANIC`, `OOM_KILL` |
| Misconfiguration | `MISCONFIGURATION` | `SECURITY_GROUP_MISCONFIGURATION` |
| Capacity | `CAPACITY_EXHAUSTION` | `CPU_THROTTLE`, `DISK_FULL` |
| External | `POWER_FAILURE` | `COOLING_FAILURE`, `POWER_FAILURE` |
| Planned | `PLANNED_MAINTENANCE` | `ROLLING_UPDATE` |
| Customer-side | `SERVICE_MISCONFIGURATION` | `DNS_MISCONFIGURATION` |

### Lessons Learned

Each ticket's `lessons_learned` field should:
1. Reference specific entity IDs or entity types from the topology
2. Suggest improvements (monitoring, redundancy, process)
3. Occasionally suggest ontology changes ("add X property to Y entity")

These lessons are surfaced by the ticket agent during investigation, providing
the AI with historical context for similar incidents.

---

## `graph_schema.yaml` Format

The graph schema manifest is the **single source of truth** for the Cosmos
Gremlin graph. The generic loader (`scripts/cosmos/provision_cosmos_gremlin.py`)
reads this file and creates all vertices and edges — no code changes needed
for new scenarios.

### Top-Level Structure

```yaml
# Directory containing CSV files (relative to project root)
data_dir: data/network

vertices:
  - label: <VertexLabel>
    ...

edges:
  - label: <EdgeLabel>
    ...
```

### Vertex Definition

```yaml
vertices:
  - label: CoreRouter                  # Gremlin vertex label
    csv_file: DimCoreRouter.csv        # CSV filename inside data_dir
    id_column: RouterId                # Column whose value → vertex 'id' property
    partition_key: router              # Static value for 'partitionKey' property
    properties:                        # Columns to add as vertex properties
      - RouterId                       # id_column is always included
      - City
      - Region
      - Vendor
      - Model
```

Rules:
- `label` must be unique across all vertex types
- `csv_file` must exist in `data_dir`
- `id_column` must be one of the `properties`
- `partition_key` is a static string (not a column name) — used for Cosmos partitioning
- `properties` lists CSV column names to store as vertex properties

### Edge Definition

```yaml
edges:
  - label: connects_to                 # Gremlin edge label
    csv_file: DimTransportLink.csv     # CSV to iterate
    source:                            # How to find the source vertex
      label: TransportLink             # Vertex label to match
      property: LinkId                 # Vertex property for has() lookup
      column: LinkId                   # CSV column with the lookup value
    target:                            # How to find the target vertex
      label: CoreRouter
      property: RouterId
      column: SourceRouterId           # CSV column with FK lookup value
    properties:                        # Optional edge properties
      - name: direction                # Gremlin property name
        value: source                  # Static literal value
    filter:                            # Optional — only process matching rows
      column: NodeType
      value: TransportLink
```

Rules:
- `source.label` and `target.label` must match a vertex definition's `label`
- `source.column` and `target.column` must be CSV column names
- `properties` can use `column` (CSV value) or `value` (static literal), not both
- `filter` restricts which CSV rows create edges (e.g. create `routes_via` edges
  only for rows where `NodeType == "TransportLink"`)

### Bidirectional Edges

For components that connect at both endpoints (e.g. a transport link connects
to both a source router and a target router), define **two edge entries**:

```yaml
  - label: connects_to
    csv_file: DimTransportLink.csv
    source: { label: TransportLink, property: LinkId, column: LinkId }
    target: { label: CoreRouter, property: RouterId, column: SourceRouterId }
    properties: [{ name: direction, value: source }]

  - label: connects_to
    csv_file: DimTransportLink.csv
    source: { label: TransportLink, property: LinkId, column: LinkId }
    target: { label: CoreRouter, property: RouterId, column: TargetRouterId }
    properties: [{ name: direction, value: target }]
```

### Filtered Edges (Junction Tables)

When a junction table encodes edges to multiple target types, use `filter` to
create separate edge definitions per target type:

```yaml
  # Service depends_on MPLSPath
  - label: depends_on
    csv_file: FactServiceDependency.csv
    filter: { column: DependsOnType, value: MPLSPath }
    source: { label: Service, property: ServiceId, column: ServiceId }
    target: { label: MPLSPath, property: PathId, column: DependsOnId }

  # Service depends_on AggSwitch
  - label: depends_on
    csv_file: FactServiceDependency.csv
    filter: { column: DependsOnType, value: AggSwitch }
    source: { label: Service, property: ServiceId, column: ServiceId }
    target: { label: AggSwitch, property: SwitchId, column: DependsOnId }
```

### Complete Example (Telco-NOC)

The reference schema defines:
- **8 vertex types**: CoreRouter, AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession
- **11 edge definitions**: connects_to (×2), aggregates_to, backhauls_via, routes_via, depends_on (×3), governed_by, peers_over (×2)

See `data/graph_schema.yaml` (266 lines) for the full implementation.
