```skill
---
name: graph-data-scenarios
description: >
  Generate complete data scenarios for the autonomous-network-demo graph
  platform. Guides an AI agent to produce topology CSVs, junction tables,
  telemetry streams, incident tickets, graph_schema.yaml, scenario.yaml,
  prompt fragments, and runbooks that conform to the platform's convention
  contract and work with the existing ingestion pipeline out of the box.
---

# graph-data-scenarios — Generate Graph Data Scenarios

A reference skill for **generating complete data scenarios** for the autonomous
network demo platform. This skill teaches an AI agent how to author Python data
generation scripts that produce all artefacts required by the platform's
convention contract — no loader code changes needed for new domains.

## When to Use

Use this skill when:
- Creating a **new scenario** for any domain (telco, cloud, e-commerce, power grid, etc.)
- Modifying an existing scenario's topology, telemetry, tickets, or prompts
- Debugging why generated data doesn't load into Cosmos Gremlin / NoSQL / AI Search
- Understanding the relationship between CSVs, graph_schema.yaml, prompts, and scenario.yaml

## Canonical Reference Implementation

The **telco-noc** scenario in `data/scenarios/telco-noc/` is the single
production-tested reference. All patterns, formats, and conventions in this
skill are derived from it. When in doubt, inspect the telco-noc files directly.

Additional **illustrative examples** for cloud and e-commerce domains appear in
the reference docs to show how patterns adapt across domains — these are
documentation-only and don't exist as deployed scenarios.

## Output Structure

A complete scenario lives under `data/scenarios/<scenario-name>/`:

```
data/scenarios/<scenario-name>/
├── scenario.yaml                    # Scenario manifest (master config)
├── graph_schema.yaml                # Graph ontology (Gremlin loader reads this)
├── scripts/                         # Data generation scripts
│   ├── generate_all.sh              # Runner: calls all generators in order
│   ├── generate_topology.py         # Vertex dimension CSVs
│   ├── generate_routing.py          # Junction/edge Fact CSVs
│   ├── generate_telemetry.py        # AlertStream + domain metrics
│   └── generate_tickets.py          # Historical incident .txt files
└── data/                            # Generated output
    ├── entities/                    # Graph vertex + edge CSVs
    │   ├── Dim*.csv                 # One per vertex type (dimension/entity)
    │   └── Fact*.csv                # One per junction table (relationship)
    ├── telemetry/                   # Time-series CSVs for Cosmos NoSQL
    │   ├── AlertStream.csv          # Alert events (REQUIRED for every scenario)
    │   └── <DomainMetrics>.csv      # Additional telemetry
    ├── knowledge/
    │   ├── runbooks/                # Operational procedures (.md) → AI Search
    │   └── tickets/                 # Historical incidents (.txt) → AI Search
    └── prompts/                     # Scenario-specific prompt fragments
        ├── foundry_orchestrator_agent.md
        ├── foundry_telemetry_agent_v2.md
        ├── foundry_runbook_kb_agent.md
        ├── foundry_historical_ticket_agent.md
        ├── alert_storm.md           # Default alert CSV for demo kickoff
        └── graph_explorer/
            ├── core_schema.md       # Full entity schema with all instances
            ├── core_instructions.md # Gremlin traversal patterns + X-Graph rule
            ├── description.md       # Agent description for Foundry registration
            ├── language_gremlin.md  # Gremlin query examples
            └── language_mock.md     # Natural language examples for mock mode
```

## How to Generate a New Scenario (Step-by-Step)

### Step 1: Design the Domain Ontology

Define ~8 entity types, their relationships, and a realistic incident that
cascades through the graph. Target ~30–60 total vertices.

**You need three things:**

1. **Entity types** (~8): organized in parent→child hierarchy
2. **Relationships**: FK columns in child tables + junction tables for M:N
3. **Incident narrative**: a root cause that cascades through 4–6 tiers

```
Domain:       Cloud datacenter
Entities:     Region, AvailabilityZone, Rack, Host, VirtualMachine, LoadBalancer, Service, SLAPolicy
Relationships: Region→has_zone→AZ, AZ→has_rack→Rack, Rack→hosts_server→Host, Host→runs→VM, ...
Incident:     CRAC cooling failure in AZ causes cascading thermal host shutdowns
```

**Cross-domain entity patterns:**

| Domain | Root entities (~3) | Mid-tier entities (~3) | Leaf entities (~2) | Incident type |
|--------|-------------------|----------------------|-------------------|---------------|
| Telco | CoreRouter, TransportLink, BGPSession | AggSwitch, MPLSPath, BaseStation | Service, SLAPolicy | Fibre cut cascade |
| Cloud | Region, AvailabilityZone, Rack | Host, VirtualMachine, LoadBalancer | Service, SLAPolicy | Cooling failure |
| E-commerce | CustomerSegment, ProductCategory, Campaign | Customer, Product, Supplier | Warehouse, SLAPolicy | Model bias |
| Power grid | Substation, Transformer, Busbar | Generator, Feeder, LoadPoint | Consumer, SLAPolicy | Transformer trip |

### Step 2: Write Topology Generator (`scripts/generate_topology.py`)

See `references/topology-patterns.md` for the exact script structure with full code.

**Key rules:**
- One function per entity type, each calling a shared `write_csv()` helper
- **All data is inline (hardcoded rows, NOT randomized)** for reproducibility
- Entity IDs follow: `{TYPE_PREFIX}-{LOCATION}-{SEQUENCE}` (e.g. `CORE-SYD-01`)
- Foreign key columns reference IDs from parent entity tables
- Functions called in dependency order: parents before children
- `OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "entities")`
- Output files: `Dim<EntityType>.csv` — one per entity type

### Step 3: Write Routing/Junction Generator (`scripts/generate_routing.py`)

Produces `Fact*.csv` files encoding graph edges that can't be expressed by
a single FK:

- **Path hops pattern**: ordered traversal — `PathId, HopOrder, NodeId, NodeType`
- **Dependency pattern**: typed relationships — `ServiceId, DependsOnId, DependsOnType, DependencyStrength`
- Every row references IDs that exist in the `Dim*.csv` files
- `NodeType`/`DependsOnType` columns enable `filter` clauses in `graph_schema.yaml`

### Step 4: Write `graph_schema.yaml`

See `references/graph-schema-format.md` for the exact YAML specification.

**Key rules:**
- `data_dir: data/entities` (relative to schema file)
- **Vertices**: label, csv_file, id_column, partition_key, properties
- **Edges**: label, csv_file, source/target vertex lookup, optional properties, optional filter
- Bidirectional connections → **two edge entries** (e.g. TransportLink connects_to SourceRouter + TargetRouter)
- Junction tables with multiple target types → **one entry per type with filter**
- Expected count: ~`1.2 × vertex_count + bidirectional_pairs + filtered_variants` edge definitions

### Step 5: Write Telemetry Generator (`scripts/generate_telemetry.py`)

See `references/telemetry-patterns.md` for the exact cascade timeline and code.

**Key rules:**
- **AlertStream.csv** (required): ~5,000 rows = ~3,000 baseline over 54h + ~2,000 cascade over 90s
- **No-null rule**: ALL numeric columns must be populated in EVERY row
- **Baseline period**: 54h of low-severity noise before incident (provides anomaly baseline)
- **Cascade timeline**: root cause → protocol loss → propagation → service degradation
- **Second telemetry CSV**: per-component time-series (e.g. LinkTelemetry.csv, HostMetrics.csv)
- `random.seed(42)` for reproducibility; sort alerts by timestamp
- Entity ID constants at top of file must match topology CSVs exactly

### Step 6: Write Ticket Generator (`scripts/generate_tickets.py`)

See `references/ticket-format.md` for the required output format.

**Key rules:**
- 8–12 incidents covering diverse root cause types
- Each ticket references entity IDs from topology (`root_cause`, `customer_impact`)
- Specific text format with structured fields (see reference)
- Tickets span several months before the "current" incident

### Step 7: Write Runbooks

Create 4–6 operational procedure markdown files in `data/knowledge/runbooks/`.
These are indexed into AI Search for RAG retrieval during investigation.

Each runbook should cover a specific procedure type relevant to the domain:
- Root cause investigation (e.g. `fibre_cut_runbook.md`)
- Protocol recovery (e.g. `bgp_peer_loss_runbook.md`)
- Alert triage (e.g. `alert_storm_triage_guide.md`)
- Traffic engineering (e.g. `traffic_engineering_reroute.md`)
- Customer communication (e.g. `customer_communication_template.md`)

### Step 8: Write `scenario.yaml`

See `references/scenario-yaml-format.md` for the complete specification.

**`scenario.yaml` is the master manifest.** It defines:
- Scenario metadata (`name`, `display_name`, `description`, `domain`)
- Use cases and example questions (shown in the UI's Scenario Info tab)
- Data layout (`paths` — relative to scenario dir)
- Data sources with connector types (`data_sources` — graph, telemetry, search)
- Agent definitions (`agents` — models, roles, tools, connections)
- Graph visualization styles (`graph_styles` — per-vertex-type colors)
- Telemetry baselines (`telemetry_baselines` — normal/degraded/down ranges)

### Step 9: Write Prompt Fragments

See `references/prompt-fragments.md` for the complete list and X-Graph header rule.

**CRITICAL: X-Graph Header Rule.** Three prompts MUST contain explicit instructions
telling the agent to include the `X-Graph` header with `{graph_name}` (the
placeholder that will be substituted at runtime). This is because Azure AI
Foundry's `OpenApiTool` does NOT reliably enforce `default`/`enum` values
from OpenAPI specs.

Files requiring the X-Graph rule:
1. `foundry_orchestrator_agent.md` — Scenario Context section
2. `foundry_telemetry_agent_v2.md` — CRITICAL RULE #7
3. `graph_explorer/core_instructions.md` — CRITICAL RULE #6

**Use `{graph_name}` and `{scenario_prefix}` placeholders** in prompt files.
The API config router substitutes these at runtime:
- `{graph_name}` → e.g. `telco-noc-topology`
- `{scenario_prefix}` → e.g. `telco-noc`

### Step 10: Write `scripts/generate_all.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Generating <scenario-name> scenario data ==="
python3 "$SCRIPT_DIR/generate_topology.py"
python3 "$SCRIPT_DIR/generate_routing.py"
python3 "$SCRIPT_DIR/generate_telemetry.py"
python3 "$SCRIPT_DIR/generate_tickets.py"
echo "=== Done ==="
```

### Step 11: Validate

Run the validation script to catch cross-reference errors:

```bash
python3 data/validate_scenario.py <scenario-name>
# e.g.: python3 data/validate_scenario.py telco-noc
```

Or check manually using the checklist in `references/convention-contract.md`.

## Convention Contract Summary

For generated data to "just work" with the platform, these invariants **must** hold.
See `references/convention-contract.md` for the full specification.

### Critical Rules

1. **Entity IDs are globally unique strings** — every ID referenced in edges,
   telemetry, and tickets must match a vertex ID in the entity CSVs exactly.
2. **CSV file naming**: `Dim*.csv` for vertices, `Fact*.csv` for junction tables.
3. **graph_schema.yaml** must declare every vertex and edge type, map each to
   its CSV file, and list every property column (see `references/graph-schema-format.md`).
4. **Telemetry rows must have NO nulls** in numeric columns — the downstream
   anomaly detector rejects rows with missing values. Use normal-range defaults.
5. **Ticket `.txt` files** use a specific human-readable format with structured
   fields (see `references/ticket-format.md`).
6. **scenario.yaml** defines data sources, agents, graph styles, and telemetry
   baselines (see `references/scenario-yaml-format.md`).
7. **Prompt fragments use `{graph_name}` and `{scenario_prefix}` placeholders** —
   the API config router substitutes them at runtime.

### Naming Conventions

| Concept | Example | Derivation |
|---------|---------|-----------|
| Scenario name | `telco-noc` | Kebab-case, user-chosen |
| Graph name | `telco-noc-topology` | `${name}-topology` |
| Telemetry DB | `telco-noc-telemetry` | `${name}-telemetry` (derived at runtime via `rsplit("-", 1)[0]`) |
| Containers | `telco-noc-AlertStream` | `${prefix}-${container_name}` |
| Runbooks index | `telco-noc-runbooks-index` | `${name}-runbooks-index` |
| Tickets index | `telco-noc-tickets-index` | `${name}-tickets-index` |

## References

Detailed patterns, formats, and examples are in the `references/` directory:

| File | Contents |
|------|----------|
| `convention-contract.md` | Full convention contract — all invariants |
| `topology-patterns.md` | Topology + routing script structure, ID conventions, CSV format, scale guidelines |
| `telemetry-patterns.md` | Alert cascade timeline, baseline generation, no-null rule, per-component metrics |
| `ticket-format.md` | Ticket `.txt` format, structured fields, entity ID cross-references, diversity guidelines |
| `graph-schema-format.md` | Complete `graph_schema.yaml` specification — vertices, edges, filters, bidirectional |
| `scenario-yaml-format.md` | Complete `scenario.yaml` specification — data sources, agents, styles, baselines |
| `prompt-fragments.md` | Prompt file list, X-Graph header rule, concrete value requirements |
| `complete-examples.md` | Full annotated scripts from the telco-noc reference scenario |
```
