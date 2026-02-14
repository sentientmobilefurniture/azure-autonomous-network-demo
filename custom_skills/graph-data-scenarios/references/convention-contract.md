# Convention Contract — Data Scenario Requirements

Everything a scenario must provide for the platform to ingest, query, visualise,
and investigate it without code changes.

## 1. Graph Data (CSVs)

### Vertex CSVs (`Dim*.csv`)

- One CSV per entity type (e.g. `DimCoreRouter.csv`, `DimHost.csv`)
- First row is a header with column names
- Must include an **ID column** whose values are globally unique strings
- ID convention: `{TYPE_PREFIX}-{LOCATION}-{SEQUENCE}` (e.g. `CORE-SYD-01`, `HOST-AZ1-RACK3-01`)
- IDs are referenced by edges, telemetry, and tickets — spelling must match exactly
- All rows are inline/deterministic — no randomization in topology data
- Output directory: `data/entities/` (or `data/network/` in the current flat layout)

### Junction/Edge CSVs (`Fact*.csv`)

- Encode M:N relationships between entities
- Every ID in source/target columns **must** exist in a corresponding `Dim*.csv`
- Include contextual columns like `HopOrder`, `DependencyStrength`, `NodeType`
- Used by `graph_schema.yaml` edge definitions with optional `filter` clauses

### `graph_schema.yaml`

- **Required** — the generic Cosmos Gremlin loader reads this manifest exclusively
- Must declare every vertex type with: `label`, `csv_file`, `id_column`, `partition_key`, `properties`
- Must declare every edge type with: `label`, `csv_file`, `source`/`target` vertex lookup, optional `properties`, optional `filter`
- `data_dir` must point to the directory containing the CSVs (relative to project root)
- See `graph-schema-format.md` for the complete YAML specification

## 2. Telemetry Data (CSVs)

### AlertStream CSV (required)

| Column | Type | Notes |
|--------|------|-------|
| AlertId | string | Unique per row: `ALT-{YYYYMMDD}-{NNNNNN}` |
| Timestamp | string | ISO 8601 with milliseconds: `YYYY-MM-DDTHH:MM:SS.mmmZ` |
| SourceNodeId | string | Must match an entity ID from vertex CSVs |
| SourceNodeType | string | Must match a vertex label from `graph_schema.yaml` |
| AlertType | string | Domain-specific (e.g. `LINK_DOWN`, `COOLING_FAILURE`) |
| Severity | string | `CRITICAL` / `MAJOR` / `WARNING` / `MINOR` |
| Description | string | Human-readable alert text |
| *metric columns* | float | **ALL numeric columns must be populated — no nulls** |

**The no-null rule is critical.** Every telemetry row captures a full snapshot
of the node at that instant (like an SNMP poll returning all OIDs). The
downstream anomaly detector rejects rows with null values. If an alert is
about CPU, still include normal-range values for optical power, packet loss, etc.

### Additional telemetry CSVs

- One CSV per logical telemetry container (e.g. `LinkTelemetry.csv`)
- Each maps to a Cosmos NoSQL container defined in `scenario.yaml`
- Must include a partition key column and an ID column
- Time-series format: regular interval samples (e.g. 5-min) with baseline + anomaly

## 3. Knowledge Data

### Runbooks (`knowledge/runbooks/*.md`)

- Markdown files describing operational procedures
- Indexed into Azure AI Search for RAG retrieval
- Should reference entity types and domain concepts from the scenario

### Tickets (`knowledge/tickets/*.txt`)

- Plain text files, one per historical incident
- Specific structured format — see `ticket-format.md`
- Must reference entity IDs from the topology
- 8–12 tickets covering diverse root cause types
- Span several months before the "current" incident

## 4. Prompt Fragments (`prompts/`)

| File | Purpose |
|------|---------|
| `orchestrator.md` | Investigation flow, telemetry baselines, alert types for this domain |
| `graph_explorer/core_schema.md` | Auto-generated from `graph_schema.yaml` — entity types and properties |
| `graph_explorer/core_instructions.md` | Gremlin traversal patterns using this scenario's edge labels |
| `telemetry_agent.md` | Cosmos NoSQL container schemas, partition keys, column types, value ranges |
| `runbook_agent.md` | AI Search index name, query patterns for this domain's runbooks |
| `ticket_agent.md` | AI Search index name, query patterns for this domain's tickets |
| `default_alert.md` | A realistic alert message that kicks off the demo investigation |

### Optional custom instructions (zero-cost if unused)

| File | Purpose |
|------|---------|
| `orchestrator_custom.md` | Extra investigation hints, domain heuristics |
| `graph_explorer/custom_instructions.md` | Traversal recipes, entity tips |
| `telemetry_custom.md` | Metric interpretation guidance |
| `runbook_custom.md` | Domain-specific search hints |
| `ticket_custom.md` | Domain-specific search hints |

If present, appended to the corresponding agent's composed prompt. If absent,
silently skipped.

## 5. Scenario Manifest (`scenario.yaml`)

Declares all external resource mappings:

```yaml
name: cloud-outage
display_name: "Cloud Datacenter Outage — Cooling Cascade"
domain: cloud-infrastructure

cosmos:
  gremlin:
    database: networkgraph
    graph: cloud-outage-topology
  nosql:
    database: cloud-outage-telemetry
    containers:
      - name: AlertStream
        partition_key: /SourceNodeId
        id_field: AlertId
      - name: HostMetrics
        partition_key: /HostId
        id_field: MetricId

search:
  indexes:
    - name: cloud-outage-runbooks-index
      source_container: cloud-outage-runbooks
    - name: cloud-outage-tickets-index
      source_container: cloud-outage-tickets

graph_styles:
  Region:      { color: "#ef4444", size: 16 }
  Host:        { color: "#3b82f6", size: 10 }
  # ... one entry per vertex type
```

## 6. Cross-Reference Integrity

The single most common failure mode is **ID mismatch**. Before considering a
scenario complete, verify:

- [ ] Every `SourceNodeId` in AlertStream.csv exists as a vertex ID in some `Dim*.csv`
- [ ] Every `SourceNodeType` in AlertStream.csv matches a vertex `label` in `graph_schema.yaml`
- [ ] Every ID in `Fact*.csv` source/target columns exists in the corresponding `Dim*.csv`
- [ ] Every entity ID in ticket files (root_cause, customer_impact) exists in `Dim*.csv`
- [ ] Every `csv_file` referenced in `graph_schema.yaml` actually exists
- [ ] Every column listed in `graph_schema.yaml` `properties` exists in the CSV header
- [ ] Every telemetry container in `scenario.yaml` has a corresponding CSV file
