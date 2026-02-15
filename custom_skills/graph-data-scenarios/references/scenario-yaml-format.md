# Scenario YAML Format — `scenario.yaml`

## Purpose

`scenario.yaml` is the master manifest for a scenario. The deploy scripts,
API provisioner, agent provisioner, and frontend all read this file to configure
Cosmos DB databases/containers, AI Search indexes, agent definitions, and graph
visualization styles.

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
# Use cases & example questions (surfaced in Scenario Info tab)
# ---------------------------------------------------------------------------

use_cases:
  - "Use case description 1"
  - "Use case description 2"
  - "Use case description 3"

example_questions:
  - "What caused the alert storm on ...?"
  - "Which services are affected by ...?"
  - "Show me the correlation between ... and ..."

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
# Data sources — defines all Azure resources this scenario needs
# ---------------------------------------------------------------------------

data_sources:
  graph:
    connector: "cosmosdb-gremlin"
    config:
      database: "networkgraph"
      graph: "<scenario-name>-topology"        # e.g. telco-noc-topology
      partition_key: "/partitionKey"
    schema_file: "graph_schema.yaml"

  telemetry:
    connector: "cosmosdb-nosql"
    config:
      database: "telemetry"
      container_prefix: "<scenario-name>"       # e.g. telco-noc
      containers:
        - name: AlertStream                     # REQUIRED — every scenario needs this
          partition_key: /SourceNodeType
          csv_file: AlertStream.csv
          id_field: AlertId
          numeric_fields: [<Metric1>, <Metric2>, <Metric3>, <Metric4>]
        - name: <DomainMetrics>                 # Domain-specific second telemetry CSV
          partition_key: /<ComponentIdColumn>
          csv_file: <DomainMetrics>.csv
          id_field: <MetricId>                  # null for composite keys
          numeric_fields: [<Metric1>, <Metric2>, <Metric3>, <Metric4>]

  search_indexes:
    runbooks:
      index_name: "<scenario-name>-runbooks-index"
      source: "data/knowledge/runbooks"
      blob_container: "runbooks"
    tickets:
      index_name: "<scenario-name>-tickets-index"
      source: "data/knowledge/tickets"
      blob_container: "tickets"

# ---------------------------------------------------------------------------
# Agents — defines AI agent topology for this scenario
# ---------------------------------------------------------------------------

agents:
  - name: "GraphExplorerAgent"
    role: "graph_explorer"
    model: "gpt-4.1"
    instructions_file: "prompts/graph_explorer/"   # Directory → composed from fragments
    compose_with_connector: true                   # Inject graph-specific context
    tools:
      - type: "openapi"
        spec_template: "graph"
        keep_path: "/query/graph"

  - name: "TelemetryAgent"
    role: "telemetry"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_telemetry_agent_v2.md"
    tools:
      - type: "openapi"
        spec_template: "telemetry"
        keep_path: "/query/telemetry"

  - name: "RunbookKBAgent"
    role: "runbook"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_runbook_kb_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "runbooks"

  - name: "HistoricalTicketAgent"
    role: "ticket"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_historical_ticket_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "tickets"

  - name: "Orchestrator"
    role: "orchestrator"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_orchestrator_agent.md"
    is_orchestrator: true
    connected_agents:
      - "GraphExplorerAgent"
      - "TelemetryAgent"
      - "RunbookKBAgent"
      - "HistoricalTicketAgent"

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
  <domain_metrics>:                # snake_case of the domain metrics container name
    - metric: <MetricName>
      normal: "<range description>"
      degraded: "<threshold description>"
      down: "<failure description>"
  alert_stream:
    - metric: <MetricName>
      normal: "<range description>"
      anomalous: "<threshold description>"
```

## Section-by-Section Reference

### `name` (required)

Kebab-case string used for Cosmos resource prefixing at deploy time:
- Graph: `<name>-topology` (e.g. `telco-noc-topology`)
- Telemetry DB: `<name>-telemetry` (derived at runtime via `rsplit("-", 1)[0]`)
- Containers: `<name>-<ContainerName>` (e.g. `telco-noc-AlertStream`)
- Indexes: `<name>-runbooks-index`, `<name>-tickets-index`

### `use_cases` and `example_questions` (required)

Displayed in the UI's Scenario Info tab. Provide 3–6 of each.
`use_cases` describe what the scenario demonstrates.
`example_questions` give users starting points for investigation.

### `paths` (required)

All paths are relative to the directory containing `scenario.yaml`.
The standard layout is always:

```yaml
paths:
  entities: data/entities
  graph_schema: graph_schema.yaml
  telemetry: data/telemetry
  runbooks: data/knowledge/runbooks
  tickets: data/knowledge/tickets
  prompts: data/prompts
  default_alert: data/prompts/alert_storm.md
```

### `data_sources` (required)

Defines the Azure backend resources the scenario needs.

**`data_sources.graph`** — Cosmos DB Gremlin graph:
- `connector`: always `"cosmosdb-gremlin"`
- `config.database`: `"networkgraph"` (shared across scenarios)
- `config.graph`: `"<name>-topology"` — must match what prompts reference
- `config.partition_key`: `"/partitionKey"` (standard)
- `schema_file`: path to `graph_schema.yaml`

**`data_sources.telemetry`** — Cosmos DB NoSQL containers:
- `connector`: always `"cosmosdb-nosql"`
- `config.database`: `"telemetry"` (shared)
- `config.container_prefix`: `"<name>"` (used for container naming)
- `config.containers`: list of container definitions:
  - `name`: container base name (e.g. `AlertStream`)
  - `partition_key`: must start with `/` (Cosmos convention)
  - `csv_file`: corresponding CSV in `data/telemetry/`
  - `id_field`: column for document ID (or `null` for composite keys)
  - `numeric_fields`: ALL numeric columns — used by anomaly detector

**`data_sources.search_indexes`** — Azure AI Search indexes:
- `runbooks.index_name`: `"<name>-runbooks-index"`
- `tickets.index_name`: `"<name>-tickets-index"`
- `source`: relative path to source data
- `blob_container`: Blob Storage container name

### `agents` (required)

Defines the AI agent topology. Every scenario uses the same 5-agent structure:

| Agent | Role | Tools | Notes |
|-------|------|-------|-------|
| GraphExplorerAgent | `graph_explorer` | OpenAPI (graph) | `compose_with_connector: true` |
| TelemetryAgent | `telemetry` | OpenAPI (telemetry) | |
| RunbookKBAgent | `runbook` | AI Search | |
| HistoricalTicketAgent | `ticket` | AI Search | |
| Orchestrator | `orchestrator` | Connected agents | `is_orchestrator: true` |

Agent `instructions_file` can be:
- A **file path** (e.g. `prompts/foundry_telemetry_agent_v2.md`) — used as-is
- A **directory path** (e.g. `prompts/graph_explorer/`) — composed from fragments within

### `graph_styles` (required)

Frontend node styling. One entry per vertex type from `graph_schema.yaml`:

```yaml
graph_styles:
  node_types:
    CoreRouter:    { color: "#38BDF8", size: 28, icon: "router" }
    TransportLink: { color: "#3B82F6", size: 16, icon: "link" }
```

- `color`: hex color string
- `size`: node diameter in pixels
- `icon`: icon name (available: `router`, `switch`, `antenna`, `link`, `path`,
  `service`, `policy`, `session`, `server`, `vm`, `loadbalancer`, `globe`,
  `zone`, `rack`, `users`, `user`, `folder`, `box`, `megaphone`, `truck`,
  `warehouse`)

### `telemetry_baselines` (required)

Human-readable metric ranges used in generated prompts. One section per
telemetry container (snake_case):

```yaml
telemetry_baselines:
  link_telemetry:           # matches container name "LinkTelemetry" in snake_case
    - metric: LatencyMs
      normal: "2–15 ms"
      degraded: "> 50 ms"
      down: "9999 ms"
  alert_stream:
    - metric: CPUUtilPct
      normal: "< 70%"
      anomalous: "> 85%"
```

## Complete Example — Telco-NOC

This is the actual production `scenario.yaml` from the canonical reference:

```yaml
name: telco-noc
display_name: "Australian Telco NOC — Fibre Cut Incident"
description: >
  A fibre cut on the Sydney-Melbourne corridor triggers a cascading alert
  storm affecting enterprise VPNs, broadband, and mobile services. The AI
  investigates root cause, blast radius, and remediation.
version: "2.0"
domain: telecommunications

use_cases:
  - "Fibre cut incident investigation and root cause correlation"
  - "MPLS path failover analysis and traffic rerouting assessment"
  - "Enterprise service impact mapping across BGP sessions"
  - "Alert storm triage and deduplication across transport links"
  - "SLA breach risk assessment for affected customers"

example_questions:
  - "What caused the alert storm on the Sydney-Melbourne corridor?"
  - "Which enterprise services are affected by the fibre cut?"
  - "How are MPLS paths rerouting around the failed transport link?"
  - "What BGP sessions are down and what's their blast radius?"
  - "Which SLA policies are at risk of being breached?"
  - "Show me the correlation between optical power drops and service degradation"

paths:
  entities: data/entities
  graph_schema: graph_schema.yaml
  telemetry: data/telemetry
  runbooks: data/knowledge/runbooks
  tickets: data/knowledge/tickets
  prompts: data/prompts
  default_alert: data/prompts/alert_storm.md

data_sources:
  graph:
    connector: "cosmosdb-gremlin"
    config:
      database: "networkgraph"
      graph: "telco-noc-topology"
      partition_key: "/partitionKey"
    schema_file: "graph_schema.yaml"

  telemetry:
    connector: "cosmosdb-nosql"
    config:
      database: "telemetry"
      container_prefix: "telco-noc"
      containers:
        - name: AlertStream
          partition_key: /SourceNodeType
          csv_file: AlertStream.csv
          id_field: AlertId
          numeric_fields: [OpticalPowerDbm, BitErrorRate, CPUUtilPct, PacketLossPct]
        - name: LinkTelemetry
          partition_key: /LinkId
          csv_file: LinkTelemetry.csv
          id_field: null
          numeric_fields: [UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs]

  search_indexes:
    runbooks:
      index_name: "telco-noc-runbooks-index"
      source: "data/knowledge/runbooks"
      blob_container: "runbooks"
    tickets:
      index_name: "telco-noc-tickets-index"
      source: "data/knowledge/tickets"
      blob_container: "tickets"

agents:
  - name: "GraphExplorerAgent"
    role: "graph_explorer"
    model: "gpt-4.1"
    instructions_file: "prompts/graph_explorer/"
    compose_with_connector: true
    tools:
      - type: "openapi"
        spec_template: "graph"
        keep_path: "/query/graph"

  - name: "TelemetryAgent"
    role: "telemetry"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_telemetry_agent_v2.md"
    tools:
      - type: "openapi"
        spec_template: "telemetry"
        keep_path: "/query/telemetry"

  - name: "RunbookKBAgent"
    role: "runbook"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_runbook_kb_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "runbooks"

  - name: "HistoricalTicketAgent"
    role: "ticket"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_historical_ticket_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "tickets"

  - name: "Orchestrator"
    role: "orchestrator"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_orchestrator_agent.md"
    is_orchestrator: true
    connected_agents:
      - "GraphExplorerAgent"
      - "TelemetryAgent"
      - "RunbookKBAgent"
      - "HistoricalTicketAgent"

graph_styles:
  node_types:
    CoreRouter:    { color: "#38BDF8", size: 28, icon: "router" }
    AggSwitch:     { color: "#FB923C", size: 22, icon: "switch" }
    BaseStation:   { color: "#A78BFA", size: 18, icon: "antenna" }
    TransportLink: { color: "#3B82F6", size: 16, icon: "link" }
    MPLSPath:      { color: "#C084FC", size: 14, icon: "path" }
    Service:       { color: "#CA8A04", size: 20, icon: "service" }
    SLAPolicy:     { color: "#FB7185", size: 12, icon: "policy" }
    BGPSession:    { color: "#F472B6", size: 14, icon: "session" }

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
    - metric: OpticalPowerDbm
      normal: "-8 to -12 dBm"
      anomalous: "< -20 dBm"
    - metric: BitErrorRate
      normal: "< 1e-9"
      anomalous: "> 1e-6"
```

## Illustrative Example — Cloud-Outage

Shows how the same structure adapts to a different domain (documentation-only):

```yaml
name: cloud-outage
display_name: "Cloud Datacenter Outage — Cooling Cascade"
description: >
  A CRAC unit failure in US-East Availability Zone A triggers cascading
  thermal shutdowns across 5 hosts. VMs become unreachable, services degrade,
  and load balancers fail over to AZ-B.
version: "1.0"
domain: cloud-infrastructure

use_cases:
  - "Cooling failure investigation and thermal cascade analysis"
  - "VM availability impact assessment across availability zones"
  - "Load balancer failover validation and traffic redistribution"
  - "SLA breach risk assessment for affected services"

example_questions:
  - "What caused the thermal shutdowns in AZ-US-EAST-A?"
  - "Which VMs are affected and what services do they run?"
  - "How did the load balancers respond to the AZ failure?"
  - "Which SLA policies are at risk of breach?"

paths:
  entities: data/entities
  graph_schema: graph_schema.yaml
  telemetry: data/telemetry
  runbooks: data/knowledge/runbooks
  tickets: data/knowledge/tickets
  prompts: data/prompts
  default_alert: data/prompts/alert_storm.md

data_sources:
  graph:
    connector: "cosmosdb-gremlin"
    config:
      database: "networkgraph"
      graph: "cloud-outage-topology"
      partition_key: "/partitionKey"
    schema_file: "graph_schema.yaml"

  telemetry:
    connector: "cosmosdb-nosql"
    config:
      database: "telemetry"
      container_prefix: "cloud-outage"
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

  search_indexes:
    runbooks:
      index_name: "cloud-outage-runbooks-index"
      source: "data/knowledge/runbooks"
      blob_container: "runbooks"
    tickets:
      index_name: "cloud-outage-tickets-index"
      source: "data/knowledge/tickets"
      blob_container: "tickets"

agents:
  - name: "GraphExplorerAgent"
    role: "graph_explorer"
    model: "gpt-4.1"
    instructions_file: "prompts/graph_explorer/"
    compose_with_connector: true
    tools:
      - type: "openapi"
        spec_template: "graph"
        keep_path: "/query/graph"

  - name: "TelemetryAgent"
    role: "telemetry"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_telemetry_agent_v2.md"
    tools:
      - type: "openapi"
        spec_template: "telemetry"
        keep_path: "/query/telemetry"

  - name: "RunbookKBAgent"
    role: "runbook"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_runbook_kb_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "runbooks"

  - name: "HistoricalTicketAgent"
    role: "ticket"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_historical_ticket_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "tickets"

  - name: "Orchestrator"
    role: "orchestrator"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_orchestrator_agent.md"
    is_orchestrator: true
    connected_agents:
      - "GraphExplorerAgent"
      - "TelemetryAgent"
      - "RunbookKBAgent"
      - "HistoricalTicketAgent"

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
  alert_stream:
    - metric: TemperatureCelsius
      normal: "22–28°C"
      anomalous: "> 35°C"
    - metric: CPUUtilPct
      normal: "< 70%"
      anomalous: "> 85%"
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
7. **Agent structure is fixed** — always 5 agents with the same roles; only
   instructions and tool configs change per scenario
8. **`data_sources.graph.config.graph`** must match the graph name used in
   X-Graph header prompts (e.g. `telco-noc-topology`)
