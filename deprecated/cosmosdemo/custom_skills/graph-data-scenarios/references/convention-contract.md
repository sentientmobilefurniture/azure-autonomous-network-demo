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
- Output directory: `data/entities/` (inside the scenario's `data/` subdirectory)

### Junction/Edge CSVs (`Fact*.csv`)

- Encode M:N relationships between entities
- Every ID in source/target columns **must** exist in a corresponding `Dim*.csv`
- Include contextual columns like `HopOrder`, `DependencyStrength`, `NodeType`
- Used by `graph_schema.yaml` edge definitions with optional `filter` clauses

### `graph_schema.yaml`

- **Required** — the generic Cosmos Gremlin loader reads this manifest exclusively
- Must declare every vertex type with: `label`, `csv_file`, `id_column`, `partition_key`, `properties`
- Must declare every edge type with: `label`, `csv_file`, `source`/`target` vertex lookup, optional `properties`, optional `filter`
- `data_dir` must point to the directory containing the CSVs (relative to schema file)
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
downstream anomaly detector rejects rows with null values.

Domain-specific metric columns:

| Domain | Metric Columns |
|--------|----------------|
| Telco | `OpticalPowerDbm`, `BitErrorRate`, `CPUUtilPct`, `PacketLossPct` |
| Cloud | `TemperatureCelsius`, `CPUUtilPct`, `MemoryUtilPct`, `DiskIOPS` |
| E-commerce | `ClickRatePct`, `ConversionRatePct`, `ReturnRatePct`, `AvgOrderValueUSD` |

### Additional telemetry CSVs

- One CSV per logical telemetry container (e.g. `LinkTelemetry.csv`, `HostMetrics.csv`)
- Each maps to a Cosmos NoSQL container defined in `scenario.yaml`
- Must include a partition key column and an ID column (or composite key)
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
| `foundry_orchestrator_agent.md` | Investigation flow, telemetry baselines, alert types, sub-agent descriptions, **Scenario Context with graph name** |
| `foundry_telemetry_agent_v2.md` | Cosmos NoSQL container schemas, partition keys, column types, value ranges, **X-Graph CRITICAL RULE** |
| `foundry_runbook_kb_agent.md` | Domain-specific runbook descriptions |
| `foundry_historical_ticket_agent.md` | Domain-specific ticket descriptions |
| `graph_explorer/core_schema.md` | Full entity schema — all instances and relationships |
| `graph_explorer/core_instructions.md` | Gremlin traversal patterns using this scenario's edge labels, **X-Graph CRITICAL RULE** |
| `graph_explorer/description.md` | Agent description for Foundry registration |
| `graph_explorer/language_gremlin.md` | Gremlin query examples for this scenario |
| `graph_explorer/language_mock.md` | Natural language examples for mock mode |
| `alert_storm.md` | A realistic alert CSV that kicks off the demo investigation |

### X-Graph Header Rule (CRITICAL)

Three prompt files **must** contain explicit instructions telling the LLM agent
to include the `X-Graph` HTTP header with the concrete scenario graph name when
calling graph or telemetry API tools:

| File | Section | Example text |
|------|---------|--------------|
| `foundry_orchestrator_agent.md` | Scenario Context | "The current active scenario graph is `{graph_name}`." |
| `foundry_telemetry_agent_v2.md` | CRITICAL RULE #7 | "Always include the X-Graph header with the value `{graph_name}`." |
| `graph_explorer/core_instructions.md` | CRITICAL RULE #6 | "Always include the X-Graph header with the value `{graph_name}`." |

**Graph name convention:** `<scenario-name>-topology` (e.g., `telco-noc-topology`,
`cloud-outage-topology`).

**Telemetry DB derivation:** At runtime, `rsplit("-", 1)[0]` + `-telemetry`
(e.g., `cloud-outage-topology` → `cloud-outage-telemetry`).

**Use `{graph_name}` and `{scenario_prefix}` placeholders** in prompt files.
The API config router substitutes them at runtime:
- `{graph_name}` → e.g. `telco-noc-topology`
- `{scenario_prefix}` → e.g. `telco-noc`

### Optional custom instructions (appended if present, silently skipped if absent)

| File | Purpose |
|------|---------|
| `orchestrator_custom.md` | Extra investigation hints, domain heuristics |
| `graph_explorer/custom_instructions.md` | Traversal recipes, entity tips |
| `telemetry_custom.md` | Metric interpretation guidance |
| `runbook_custom.md` | Domain-specific search hints |
| `ticket_custom.md` | Domain-specific search hints |

## 5. Scenario Manifest (`scenario.yaml`)

Declares all external resource mappings, agent definitions, and UI metadata.
See `scenario-yaml-format.md` for complete spec.

Required sections:
- `name`, `display_name`, `description`, `version`, `domain`
- `use_cases` — what the scenario demonstrates (shown in UI)
- `example_questions` — starting points for investigation (shown in UI)
- `paths` — relative paths to entities, graph_schema, telemetry, runbooks, tickets, prompts
- `data_sources.graph` — Cosmos Gremlin connector config (database, graph name)
- `data_sources.telemetry` — Cosmos NoSQL connector config (database, containers with
  name, partition_key, csv_file, id_field, numeric_fields)
- `data_sources.search_indexes` — AI Search index definitions (runbooks, tickets)
- `agents` — 5-agent topology (GraphExplorer, Telemetry, Runbook, Ticket, Orchestrator)
- `graph_styles` — per-vertex-type color, size, icon
- `telemetry_baselines` — normal/degraded/down ranges per metric

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
- [ ] All three X-Graph prompt files reference the correct `<scenario>-topology` name
