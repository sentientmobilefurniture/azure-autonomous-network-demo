# Graph Schema Format — `graph_schema.yaml`

## Purpose

`graph_schema.yaml` is the **single source of truth** for the Cosmos DB Gremlin
graph. The generic loader reads this manifest to:

1. Create vertices from CSV files (one `addV()` per CSV row)
2. Create edges from CSV files (one `addE()` per CSV row, with optional filtering)
3. Attach properties to vertices and edges

No loader code changes are needed for new scenarios — only a new YAML file.

## Top-Level Structure

```yaml
# Directory containing CSV files (relative to this schema file's directory)
data_dir: data/entities

vertices:
  - label: <EntityType>
    ...

edges:
  - label: <EdgeLabel>
    ...
```

## Vertex Definition

```yaml
vertices:
  - label: CoreRouter                  # Gremlin vertex label (unique across all types)
    csv_file: DimCoreRouter.csv        # CSV filename inside data_dir
    id_column: RouterId                # Column whose value → vertex 'id' property
    partition_key: router              # Static string for 'partitionKey' property
    properties:                        # CSV columns to store as vertex properties
      - RouterId                       # id_column is always included
      - City
      - Region
      - Vendor
      - Model
```

**Rules:**
- `label` must be unique — no two vertex definitions share the same label
- `csv_file` must exist in `data_dir`
- `id_column` must be listed in `properties`
- `partition_key` is a short static string, NOT a column name (e.g. `router`, `host`, `service`)
- All CSV columns needed for graph queries/display must be in `properties`

## Edge Definition

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

**Rules:**
- `source.label` and `target.label` must match existing vertex `label` values
- `source.column` and `target.column` must be CSV column names
- `properties` entries use either `column` (CSV value) OR `value` (static literal), never both
- `filter` restricts which rows create edges

## Bidirectional Edges

Components connecting at both endpoints need **two edge entries**:

```yaml
  # TransportLink → source router
  - label: connects_to
    csv_file: DimTransportLink.csv
    source: { label: TransportLink, property: LinkId, column: LinkId }
    target: { label: CoreRouter, property: RouterId, column: SourceRouterId }
    properties: [{ name: direction, value: source }]

  # TransportLink → target router
  - label: connects_to
    csv_file: DimTransportLink.csv
    source: { label: TransportLink, property: LinkId, column: LinkId }
    target: { label: CoreRouter, property: RouterId, column: TargetRouterId }
    properties: [{ name: direction, value: target }]
```

## Filtered Edges (Junction Tables)

When a junction table encodes edges to multiple target types, use `filter`
to create separate edge definitions per target type:

```yaml
  # Service depends_on MPLSPath
  - label: depends_on
    csv_file: FactServiceDependency.csv
    filter: { column: DependsOnType, value: MPLSPath }
    source: { label: Service, property: ServiceId, column: ServiceId }
    target: { label: MPLSPath, property: PathId, column: DependsOnId }
    properties: [{ name: DependencyStrength, column: DependencyStrength }]

  # Service depends_on AggSwitch
  - label: depends_on
    csv_file: FactServiceDependency.csv
    filter: { column: DependsOnType, value: AggSwitch }
    source: { label: Service, property: ServiceId, column: ServiceId }
    target: { label: AggSwitch, property: SwitchId, column: DependsOnId }
    properties: [{ name: DependencyStrength, column: DependencyStrength }]

  # Service depends_on BaseStation
  - label: depends_on
    csv_file: FactServiceDependency.csv
    filter: { column: DependsOnType, value: BaseStation }
    source: { label: Service, property: ServiceId, column: ServiceId }
    target: { label: BaseStation, property: StationId, column: DependsOnId }
    properties: [{ name: DependencyStrength, column: DependencyStrength }]
```

## Edge Count Guide

```
edge_definitions ≈ 1.2 × vertex_types + bidirectional_pairs + filtered_variants
```

Reference counts:

| Scenario | Vertex types | Edge definitions |
|----------|-------------|------------------|
| telco-noc | 8 | 11 (2 bidirectional connects_to, 3 filtered depends_on) |
| cloud-outage | 8 | 9–14 (2 filtered depends_on) |
| customer-recommendation | 8 | 14 (2 filtered depends_on, 1 filtered subcategory_of) |

## Vertex Checklist

- [ ] Every entity type in topology CSVs has a vertex definition
- [ ] `csv_file` exists in `data_dir`
- [ ] `id_column` is listed in `properties`
- [ ] `partition_key` is a short static string
- [ ] All CSV columns used in queries/display are in `properties`
- [ ] `label` is unique across all vertex definitions

## Edge Checklist

- [ ] Every relationship in the domain has an edge definition
- [ ] `source.label` and `target.label` match existing vertex labels
- [ ] `source.column` and `target.column` are real CSV column names
- [ ] Bidirectional connections have two separate edge entries
- [ ] Junction tables with multiple target types use `filter` per type
- [ ] Edge `properties` use either `column` or `value`, never both

## Complete Cloud Example

```yaml
data_dir: data/entities

vertices:
  - label: Region
    csv_file: DimRegion.csv
    id_column: RegionId
    partition_key: region
    properties: [RegionId, RegionName, Country, Provider]

  - label: AvailabilityZone
    csv_file: DimAvailabilityZone.csv
    id_column: AZId
    partition_key: az
    properties: [AZId, AZName, RegionId, CoolingSystem, PowerFeedCount]

  - label: Rack
    csv_file: DimRack.csv
    id_column: RackId
    partition_key: rack
    properties: [RackId, RackPosition, AZId, MaxPowerKW, CoolingZone]

  - label: Host
    csv_file: DimHost.csv
    id_column: HostId
    partition_key: host
    properties: [HostId, Hostname, RackId, CPUCores, MemoryGB, Vendor]

  - label: VirtualMachine
    csv_file: DimVirtualMachine.csv
    id_column: VMId
    partition_key: vm
    properties: [VMId, VMName, HostId, ServiceId, vCPUs, MemoryGB, OSType]

  - label: LoadBalancer
    csv_file: DimLoadBalancer.csv
    id_column: LBId
    partition_key: lb
    properties: [LBId, LBName, LBType, RegionId, Algorithm, HealthCheckPath]

  - label: Service
    csv_file: DimService.csv
    id_column: ServiceId
    partition_key: service
    properties: [ServiceId, ServiceName, ServiceType, Tier, Owner]

  - label: SLAPolicy
    csv_file: DimSLAPolicy.csv
    id_column: SLAId
    partition_key: sla
    properties: [SLAId, SLAName, ServiceId, UptimePct, MaxLatencyMs, RPOMinutes]

edges:
  # Region → has_zone → AvailabilityZone
  - label: has_zone
    csv_file: DimAvailabilityZone.csv
    source: { label: Region, property: RegionId, column: RegionId }
    target: { label: AvailabilityZone, property: AZId, column: AZId }

  # AvailabilityZone → has_rack → Rack
  - label: has_rack
    csv_file: DimRack.csv
    source: { label: AvailabilityZone, property: AZId, column: AZId }
    target: { label: Rack, property: RackId, column: RackId }

  # Rack → hosts_server → Host
  - label: hosts_server
    csv_file: DimHost.csv
    source: { label: Rack, property: RackId, column: RackId }
    target: { label: Host, property: HostId, column: HostId }

  # Host → runs → VirtualMachine
  - label: runs
    csv_file: DimVirtualMachine.csv
    source: { label: Host, property: HostId, column: HostId }
    target: { label: VirtualMachine, property: VMId, column: VMId }

  # VirtualMachine → serves → Service
  - label: serves
    csv_file: DimVirtualMachine.csv
    source: { label: VirtualMachine, property: VMId, column: VMId }
    target: { label: Service, property: ServiceId, column: ServiceId }

  # LoadBalancer → lb_in_region → Region
  - label: lb_in_region
    csv_file: DimLoadBalancer.csv
    source: { label: LoadBalancer, property: LBId, column: LBId }
    target: { label: Region, property: RegionId, column: RegionId }

  # SLAPolicy → governs → Service
  - label: governs
    csv_file: DimSLAPolicy.csv
    source: { label: SLAPolicy, property: SLAId, column: SLAId }
    target: { label: Service, property: ServiceId, column: ServiceId }

  # Service depends_on Service (via junction table)
  - label: depends_on
    csv_file: FactServiceDependency.csv
    filter: { column: DependsOnType, value: Service }
    source: { label: Service, property: ServiceId, column: ServiceId }
    target: { label: Service, property: ServiceId, column: DependsOnId }
    properties: [{ name: strength, column: DependencyStrength }]

  # Service depends_on LoadBalancer (via junction table)
  - label: depends_on
    csv_file: FactServiceDependency.csv
    filter: { column: DependsOnType, value: LoadBalancer }
    source: { label: Service, property: ServiceId, column: ServiceId }
    target: { label: LoadBalancer, property: LBId, column: DependsOnId }
    properties: [{ name: strength, column: DependencyStrength }]
```
