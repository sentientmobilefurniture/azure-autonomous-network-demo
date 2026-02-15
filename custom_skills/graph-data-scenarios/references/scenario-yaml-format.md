# Scenario YAML Format — `scenario.yaml`

## Purpose

`scenario.yaml` is the master manifest for a scenario. The deploy scripts,
API provisioner, and frontend all read this file to configure Cosmos DB
databases/containers, AI Search indexes, and graph visualization styles.

## Required Sections

```yaml
# ============================================================================
# Scenario Manifest — <Display Name>
# ============================================================================

name: <scenario-name>              # Kebab-case, used to prefix Cosmos resources
display_name: "<Human Description>"
description: >
  Multi-line description of the scenario incident and what the AI investigates.
version: "1.0"
domain: <domain>                   # e.g. telecommunications, cloud-infrastructure, e-commerce

# ---------------------------------------------------------------------------
# Data layout — paths relative to this file's parent directory
# ---------------------------------------------------------------------------

paths:
  entities: data/entities
  graph_schema: graph_schema.yaml
  telemetry: data/telemetry
  runbooks: data/knowledge/runbooks
  tickets: data/knowledge/tickets
  prompts: data/prompts
  default_alert: data/prompts/alert_storm.md

# ---------------------------------------------------------------------------
# Cosmos DB mapping
# ---------------------------------------------------------------------------

cosmos:
  gremlin:
    database: networkgraph           # Shared database name
    graph: topology                  # Deploy script prefixes: <name>-topology
  nosql:
    database: telemetry              # Deploy script prefixes: <name>-telemetry
    containers:
      - name: AlertStream            # REQUIRED — every scenario needs this
        partition_key: /SourceNodeType
        csv_file: AlertStream.csv
        id_field: AlertId
        numeric_fields: [<Metric1>, <Metric2>, <Metric3>, <Metric4>]
      - name: <DomainMetrics>        # Domain-specific second telemetry CSV
        partition_key: /<ComponentIdColumn>
        csv_file: <DomainMetrics>.csv
        id_field: <MetricId>         # null for composite keys (component + timestamp)
        numeric_fields: [<Metric1>, <Metric2>, <Metric3>, <Metric4>]

# ---------------------------------------------------------------------------
# AI Search indexes
# ---------------------------------------------------------------------------

search_indexes:
  - name: runbooks-index
    container: runbooks
    source: data/knowledge/runbooks
  - name: tickets-index
    container: tickets
    source: data/knowledge/tickets

# ---------------------------------------------------------------------------
# Graph visualisation hints (frontend node styling)
# ---------------------------------------------------------------------------

graph_styles:
  node_types:
    <EntityType1>: { color: "#hex", size: <number>, icon: "<icon_name>" }
    <EntityType2>: { color: "#hex", size: <number>, icon: "<icon_name>" }
    # ... one entry per vertex type from graph_schema.yaml

# ---------------------------------------------------------------------------
# Telemetry baselines (used to generate prompt sections)
# ---------------------------------------------------------------------------

telemetry_baselines:
  <domain_metrics>:
    - metric: <MetricName>
      normal: "<range description>"
      degraded: "<threshold description>"
      down: "<failure description>"
  alert_stream:
    - metric: <MetricName>
      normal: "<range description>"
      anomalous: "<threshold description>"
```

## Complete Examples

### Telco-NOC

```yaml
name: telco-noc
display_name: "Australian Telco NOC — Fibre Cut Incident"
description: >
  A fibre cut on the Sydney-Melbourne corridor triggers a cascading alert
  storm affecting enterprise VPNs, broadband, and mobile services. The AI
  investigates root cause, blast radius, and remediation.
version: "1.0"
domain: telecommunications

paths:
  entities: data/entities
  graph_schema: graph_schema.yaml
  telemetry: data/telemetry
  runbooks: data/knowledge/runbooks
  tickets: data/knowledge/tickets
  prompts: data/prompts
  default_alert: data/prompts/alert_storm.md

cosmos:
  gremlin:
    database: networkgraph
    graph: topology                  # → telco-noc-topology at deploy
  nosql:
    database: telemetry              # → telco-noc-telemetry at deploy
    containers:
      - name: AlertStream
        partition_key: /SourceNodeType
        csv_file: AlertStream.csv
        id_field: AlertId
        numeric_fields: [OpticalPowerDbm, BitErrorRate, CPUUtilPct, PacketLossPct]
      - name: LinkTelemetry
        partition_key: /LinkId
        csv_file: LinkTelemetry.csv
        id_field: null               # composite: LinkId + Timestamp
        numeric_fields: [UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs]

search_indexes:
  - name: runbooks-index
    container: runbooks
    source: data/knowledge/runbooks
  - name: tickets-index
    container: tickets
    source: data/knowledge/tickets

graph_styles:
  node_types:
    CoreRouter:    { color: "#60a5fa", size: 28, icon: "router" }
    AggSwitch:     { color: "#34d399", size: 22, icon: "switch" }
    BaseStation:   { color: "#a78bfa", size: 18, icon: "antenna" }
    TransportLink: { color: "#f97316", size: 16, icon: "link" }
    MPLSPath:      { color: "#fbbf24", size: 14, icon: "path" }
    Service:       { color: "#f472b6", size: 20, icon: "service" }
    SLAPolicy:     { color: "#94a3b8", size: 12, icon: "policy" }
    BGPSession:    { color: "#22d3ee", size: 14, icon: "session" }

telemetry_baselines:
  link_telemetry:
    - metric: LatencyMs
      normal: "2–15 ms"
      degraded: "> 50 ms"
      down: "9999 ms"
    - metric: OpticalPowerDbm
      normal: "-8 to -12 dBm"
      degraded: "< -20 dBm"
      down: "< -30 dBm"
    - metric: BitErrorRate
      normal: "< 1e-9"
      degraded: "> 1e-6"
      down: "≈ 1"
    - metric: UtilizationPct
      normal: "20–70%"
      degraded: "> 80%"
      down: "0% (with other down indicators)"
  alert_stream:
    - metric: PacketLossPct
      normal: "< 1%"
      anomalous: "> 2%"
    - metric: CPUUtilPct
      normal: "< 70%"
      anomalous: "> 85%"
```

### Cloud-Outage

```yaml
name: cloud-outage
display_name: "Cloud Datacenter Outage — Cooling Cascade"
description: >
  A CRAC unit failure in US-East Availability Zone A triggers cascading
  thermal shutdowns across 5 hosts. VMs become unreachable, services degrade,
  and load balancers fail over to AZ-B.
version: "1.0"
domain: cloud-infrastructure

cosmos:
  gremlin:
    database: networkgraph
    graph: topology                  # → cloud-outage-topology
  nosql:
    database: telemetry              # → cloud-outage-telemetry
    containers:
      - name: AlertStream
        partition_key: /SourceNodeType
        csv_file: AlertStream.csv
        id_field: AlertId
        numeric_fields: [TemperatureCelsius, CPUUtilPct, MemoryUtilPct, DiskIOPS]
      - name: HostMetrics
        partition_key: /HostId
        csv_file: HostMetrics.csv
        id_field: MetricId
        numeric_fields: [CPUUtilPct, MemoryUtilPct, TemperatureCelsius, DiskIOPS]

graph_styles:
  node_types:
    Region:           { color: "#ef4444", size: 30, icon: "globe" }
    AvailabilityZone: { color: "#f97316", size: 26, icon: "zone" }
    Rack:             { color: "#eab308", size: 18, icon: "rack" }
    Host:             { color: "#3b82f6", size: 20, icon: "server" }
    VirtualMachine:   { color: "#8b5cf6", size: 14, icon: "vm" }
    LoadBalancer:     { color: "#06b6d4", size: 22, icon: "loadbalancer" }
    Service:          { color: "#22c55e", size: 20, icon: "service" }
    SLAPolicy:        { color: "#94a3b8", size: 12, icon: "policy" }

telemetry_baselines:
  host_metrics:
    - metric: TemperatureCelsius
      normal: "22–28°C"
      degraded: "> 35°C"
      down: "> 85°C (thermal shutdown)"
    - metric: CPUUtilPct
      normal: "15–45%"
      degraded: "> 80%"
      down: "0% (host shutdown)"
    - metric: MemoryUtilPct
      normal: "30–60%"
      degraded: "> 85%"
      down: "0% (host shutdown)"
    - metric: DiskIOPS
      normal: "200–800"
      degraded: "> 2000"
      down: "0 (host shutdown)"
```

### Customer-Recommendation

```yaml
name: customer-recommendation
display_name: "Customer Recommendation Engine — Model Bias Incident"
description: >
  A recommendation model update introduces a price-insensitivity bias,
  surfacing high-value products ($1000+) to budget-conscious customer
  segments. Return rates spike to 25%, conversion crashes.
version: "1.0"
domain: e-commerce

cosmos:
  gremlin:
    database: networkgraph
    graph: topology                  # → customer-recommendation-topology
  nosql:
    database: telemetry              # → customer-recommendation-telemetry
    containers:
      - name: AlertStream
        partition_key: /SourceNodeType
        csv_file: AlertStream.csv
        id_field: AlertId
        numeric_fields: [ClickRatePct, ConversionRatePct, ReturnRatePct, AvgOrderValueUSD]
      - name: RecommendationMetrics
        partition_key: /SegmentId
        csv_file: RecommendationMetrics.csv
        id_field: MetricId
        numeric_fields: [ClickRatePct, ConversionRatePct, ReturnRatePct, AvgOrderValueUSD]

graph_styles:
  node_types:
    CustomerSegment:  { color: "#ef4444", size: 28, icon: "users" }
    Customer:         { color: "#f97316", size: 14, icon: "user" }
    ProductCategory:  { color: "#eab308", size: 22, icon: "folder" }
    Product:          { color: "#22c55e", size: 16, icon: "box" }
    Campaign:         { color: "#3b82f6", size: 20, icon: "megaphone" }
    Supplier:         { color: "#8b5cf6", size: 18, icon: "truck" }
    Warehouse:        { color: "#06b6d4", size: 20, icon: "warehouse" }
    SLAPolicy:        { color: "#94a3b8", size: 12, icon: "policy" }
```

## Key Rules

1. **`name` is used for Cosmos resource prefixing** — at deploy time, the graph
   becomes `<name>-topology` and the telemetry DB becomes `<name>-telemetry`
2. **`numeric_fields` must list ALL numeric columns** — these are used by the
   anomaly detector to identify which columns to analyze
3. **`partition_key` must start with `/`** — Cosmos DB convention
4. **`graph_styles.node_types` must match vertex labels** from `graph_schema.yaml`
5. **`telemetry_baselines`** are used to generate prompt sections — define
   human-readable normal/degraded/down ranges for each metric
6. **All paths are relative** to the scenario directory (where `scenario.yaml` lives)
