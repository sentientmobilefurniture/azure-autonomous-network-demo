# Data Schema & Generation

## Scenario Data Pack Structure

```
scenarios/{scenario-name}/
├── scenario.yaml                   # Scenario manifest (see schema below)
├── graph_schema.yaml               # Gremlin ingestion manifest
├── scripts/
│   ├── generate_all.sh             # Orchestrates data generation
│   ├── generate_topology.py        # Entity CSV generation
│   ├── generate_routing.py         # MPLS/BGP data
│   ├── generate_telemetry.py       # Time-series CSV generation
│   └── generate_tickets.py         # Incident ticket generation
└── data/
    ├── entities/                   # Graph vertex/edge CSVs (Dim*.csv, Fact*.csv)
    ├── telemetry/                  # Time-series CSVs (AlertStream.csv, LinkTelemetry.csv)
    ├── knowledge/
    │   ├── runbooks/               # Markdown runbooks → AI Search
    │   └── tickets/                # Plain text tickets → AI Search
    └── prompts/                    # Agent prompt fragments
        ├── foundry_orchestrator_agent.md
        ├── foundry_telemetry_agent_v2.md
        ├── foundry_runbook_kb_agent.md
        ├── foundry_historical_ticket_agent.md
        ├── alert_storm.md          # Default demo alert text
        └── graph_explorer/         # Composed into single prompt
            ├── core_instructions.md
            ├── core_schema.md
            ├── language_gremlin.md
            └── language_mock.md
```

## `scenario.yaml` Schema

> **NOTE:** The schema below is an **illustrative composite example** showing all
> possible fields. Actual scenario files may differ in field values. For instance,
> the real `telco-noc` scenario uses `partition_key: /SourceNodeType` (not `/alert_id`),
> `id_field: AlertId` (Pascal case), and `telemetry_baselines` as descriptive strings
> (e.g., `normal: \"2–15 ms\"`) rather than structured objects. The general structure
> and field names are stable; the values are scenario-specific.

```yaml
name: telco-noc                     # Used to derive graph/database names
display_name: "Telecom NOC"
description: "..."
version: "1.0"
domain: telecommunications

use_cases:                          # Human-readable scenario use cases (displayed in Scenario Info panel)
  - "Monitor fibre degradation in metro rings"
  - "Investigate MPLS path failures"
  - "Correlate BGP flaps with physical layer events"

example_questions:                  # Clickable example prompts (injected into alert input)
  - "What is the root cause of the fibre cut?"
  - "Which customers are affected by the outage?"

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
    database: networkgraph           # Shared (not scenario-prefixed)
    graph: topology                  # Suffixed: "{name}-topology"
  nosql:
    database: telemetry              # Suffixed: "{name}-telemetry"
    containers:
      - name: AlertStream
        partition_key: /alert_id
        csv_file: AlertStream.csv
        id_field: alert_id
        numeric_fields: [severity]
      - name: LinkTelemetry
        partition_key: /link_id
        csv_file: LinkTelemetry.csv
        id_field: telemetry_id
        numeric_fields: [utilization_pct, latency_ms, packet_loss_pct, ...]

search_indexes:
  - name: runbooks-index             # Suffixed: "{name}-runbooks-index"
    container: runbooks
    source: data/knowledge/runbooks
  - name: tickets-index
    container: tickets
    source: data/knowledge/tickets

graph_styles:
  node_types:
    CoreRouter: {color: "#E74C3C", size: 12, icon: router}
    AggSwitch: {color: "#3498DB", size: 10, icon: switch}
    # ...

telemetry_baselines:
  link_telemetry:
    - metric: utilization_pct
      normal: {min: 10, max: 55}
      degraded: {min: 56, max: 80}
      down: {min: 81, max: 100}
  alert_stream:
    - metric: severity
      normal: {value: 1}
      anomalous: {min: 3, max: 5}
```

## `graph_schema.yaml` Format

Declarative Gremlin ingestion manifest — fully generic, no code changes for new datasets.

```yaml
data_dir: data/entities

vertices:
  - label: CoreRouter
    csv_file: DimCoreRouter.csv
    id_column: router_id
    partition_key: CoreRouter       # Static partition key value
    properties:
      - router_id
      - router_name
      - city
      - status

edges:
  - label: connects_to
    csv_file: DimTransportLink.csv
    source:
      label: CoreRouter
      property: router_id
      column: source_router_id      # CSV column for lookup
    target:
      label: CoreRouter
      property: router_id
      column: target_router_id
    properties:
      - column: link_id             # CSV column value
      - value: active               # Static literal
    filter:                          # Optional row filter
      column: link_type
      value: core
      negate: false                   # Optional (default false). If true, includes rows
                                      # where column != value (invert filter).
```

**Telemetry upload ID fallback**: When neither `id_field` is configured in
`scenario.yaml` nor an `id` column exists in the CSV, the upload generates
document IDs from the first two CSV columns: `f"{row[col0]}-{row[col1]}"`.

**Graph explorer prompt recursive fallback**: Upload first checks
`prompts_dir/graph_explorer/`, then falls back to `tmppath.rglob("graph_explorer")`
recursive search if the subdirectory isn't at the expected location.

## Tarball Generation (`data/generate_all.sh`)

Creates **5 separate tarballs per scenario** (not one monolithic archive):

| Tarball | Contents |
|---------|----------|
| `{scenario}-graph.tar.gz` | `scenario.yaml` + `graph_schema.yaml` + `data/entities/` |
| `{scenario}-telemetry.tar.gz` | `scenario.yaml` + `data/telemetry/` |
| `{scenario}-runbooks.tar.gz` | `scenario.yaml` + `data/knowledge/runbooks/` |
| `{scenario}-tickets.tar.gz` | `scenario.yaml` + `data/knowledge/tickets/` |
| `{scenario}-prompts.tar.gz` | `scenario.yaml` + `data/prompts/` (includes `graph_explorer/` subdir) |

Every tarball includes `scenario.yaml` so the upload handler can resolve the scenario name independently.

Workflow: `./data/generate_all.sh [scenario-name]` — iterates scenario dirs, runs each scenario's `scripts/generate_all.sh`, then creates tarballs.
