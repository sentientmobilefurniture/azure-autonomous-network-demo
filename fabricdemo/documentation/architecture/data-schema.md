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
            ├── language_gremlin.md  # Gremlin traversals (cosmosdb-gremlin)
            ├── language_gql.md      # ISO GQL MATCH/RETURN (fabric-gql) — V11
            └── language_mock.md     # Mock backend queries
```

## `scenario.yaml` Schema (v2.0)

> **NOTE:** The schema below is based on the actual `telco-noc/scenario.yaml`.
> Field values are scenario-specific; the structure and field names are stable.
> A `_normalize_manifest()` function in `router_ingest.py` converts v1.0
> format (with `cosmos:` + `search_indexes:` list) to v2.0 format on the fly.

```yaml
name: telco-noc                     # Used to derive graph/database names
display_name: "Telecom NOC"
description: "..."
version: "2.0"
domain: telecommunications

use_cases:                          # Human-readable scenario use cases (displayed in Scenario Info panel)
  - "Monitor fibre degradation in metro rings"
  - "Investigate MPLS path failures"

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

# ---------------------------------------------------------------------------
# Data sources — defines all Azure resources this scenario needs
# ---------------------------------------------------------------------------

data_sources:
  graph:
    connector: "cosmosdb-gremlin"       # Backend connector type
    config:
      database: "networkgraph"          # Shared (not scenario-prefixed)
      graph: "telco-noc-topology"       # Scenario-prefixed graph name
      partition_key: "/partitionKey"
    schema_file: "graph_schema.yaml"

  telemetry:
    connector: "cosmosdb-nosql"
    config:
      database: "telemetry"             # Shared DB (pre-created by Bicep)
      container_prefix: "telco-noc"     # Prefix for per-scenario containers
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

  search_indexes:                       # Dict (not list!) keyed by logical name
    runbooks:
      index_name: "telco-noc-runbooks-index"
      source: "data/knowledge/runbooks"
      blob_container: "runbooks"
    tickets:
      index_name: "telco-noc-tickets-index"
      source: "data/knowledge/tickets"
      blob_container: "tickets"

# ---------------------------------------------------------------------------
# Agents — defines the complete agent topology for this scenario
# ---------------------------------------------------------------------------

agents:
  - name: "GraphExplorerAgent"
    role: "graph_explorer"
    model: "gpt-4.1"
    instructions_file: "prompts/graph_explorer/"   # Directory → composed prompt
    compose_with_connector: true                    # Append connector-specific schema
    tools:
      - type: "openapi"
        spec_template: "graph"                     # → openapi/templates/graph.yaml
        keep_path: "/query/graph"                  # Filter spec to this path only

  - name: "TelemetryAgent"
    role: "telemetry"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_telemetry_agent_v2.md"
    tools:
      - type: "openapi"
        spec_template: "telemetry"                 # → openapi/templates/telemetry.yaml
        keep_path: "/query/telemetry"

  - name: "RunbookKBAgent"
    role: "runbook"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_runbook_kb_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "runbooks"                      # → data_sources.search_indexes["runbooks"]

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
    connected_agents:                              # References other agents by name
      - "GraphExplorerAgent"
      - "TelemetryAgent"
      - "RunbookKBAgent"
      - "HistoricalTicketAgent"

graph_styles:
  node_types:
    CoreRouter: {color: "#38BDF8", size: 28, icon: router}
    AggSwitch: {color: "#FB923C", size: 22, icon: switch}
    # ...

telemetry_baselines:
  link_telemetry:
    - metric: LatencyMs
      normal: "2–15 ms"
      degraded: "> 50 ms"
      down: "9999 ms"
  alert_stream:
    - metric: PacketLossPct
      normal: "< 1%"
      anomalous: "> 2%"
```

### Fabric Scenario Manifest (V11)

Fabric scenarios use `connector: "fabric-gql"` on the graph data source and omit
Gremlin-specific fields (`schema_file`, `partition_key`). The graph config instead
specifies Fabric workspace and graph model identifiers:

```yaml
data_sources:
  graph:
    connector: "fabric-gql"             # Uses FabricGQLBackend
    config:
      workspace_id: "${FABRIC_WORKSPACE_ID}"   # From env or UI
      graph_model_id: "${FABRIC_GRAPH_MODEL_ID}"
    # No schema_file — Fabric Ontology manages schema

  telemetry:
    connector: "cosmosdb-nosql"          # Telemetry can still use Cosmos
    config:
      database: "telemetry"
      container_prefix: "telco-noc-fabric"
      containers:
        - name: AlertStream
          # ... same structure as Cosmos scenarios
```

The connector string drives backend selection via `CONNECTOR_TO_BACKEND` in `config.py`:
`"fabric-gql"` → `"fabric-gql"` registry key → `FabricGQLBackend`. The language file
for `GraphExplorerAgent` is selected by `connector.split("-")[-1]` → `"gql"` →
`language_gql.md` — no code changes to `router_ingest.py` prompt composition.

### Key Differences: v1.0 → v2.0

| Aspect | v1.0 (legacy) | v2.0 (current) |
|--------|---------------|----------------|
| Graph config | `cosmos.gremlin.database`, `cosmos.gremlin.graph` | `data_sources.graph.config.database`, `.graph` |
| Telemetry config | `cosmos.nosql.database`, `cosmos.nosql.containers[]` | `data_sources.telemetry.config.database`, `.container_prefix`, `.containers[]` |
| Search indexes | `search_indexes:` (list of objects) | `data_sources.search_indexes:` (dict keyed by logical name) |
| Agent definitions | Not in manifest — hardcoded in provisioner | `agents:` section with full topology |
| Connector type | Implicit (always cosmosdb) | Explicit `connector:` field per data source |
| Telemetry DB | Per-scenario DB (`{name}-telemetry`) | Shared `telemetry` DB with per-scenario container prefix |
| Prompts DB | Per-scenario DB (`{name}-prompts`) | Shared `prompts` DB with per-scenario container |

## `graph_schema.yaml` Format

> **NOTE:** `graph_schema.yaml` is specific to the CosmosDB-Gremlin backend. Fabric scenarios
> do NOT use this file — graph data is managed via Fabric Ontology (created through the
> Fabric provision pipeline or Fabric Studio). The `data_sources.graph.schema_file` field
> is omitted in Fabric scenario manifests.

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
