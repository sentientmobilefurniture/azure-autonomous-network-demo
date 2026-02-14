---
name: graph-data-scenarios
description: Generate complete data scenarios for the autonomous-network-demo graph platform. Guides an AI agent to produce topology CSVs, junction tables, telemetry streams, incident tickets, a graph_schema.yaml manifest, and prompt fragments that conform to the platform's convention contract and just work with the existing ingestion pipeline.
---

# graph-data-scenarios — Generate Graph Data Scenarios

A reference skill for **generating complete data scenarios** for the autonomous
network demo platform. Instead of generic scaffolding or templating tools, this
skill teaches an AI agent how to author data generation scripts that produce
all artefacts required by the platform's convention contract.

## When to Use

Use this skill when:
- Creating a **new scenario** (e.g. `cloud-outage`, `power-grid`)
- Modifying an existing scenario's topology, telemetry, or tickets
- Debugging why generated data doesn't load into Cosmos Gremlin / NoSQL / AI Search
- Understanding the relationship between CSVs, graph_schema.yaml, and prompts

## Reference Implementation

The `telco-noc` scenario in `data/scripts/` is the canonical reference:

| Script | Output | Purpose |
|--------|--------|---------|
| `generate_topology_data.py` | 8 entity CSVs → `data/network/` | Vertices: routers, switches, base stations, links, BGP sessions, MPLS paths, services, SLA policies |
| `generate_routing_data.py` | 2 junction CSVs → `data/network/` | Edges: MPLS path hops, service dependencies |
| `generate_alert_stream.py` | 2 telemetry CSVs → `data/telemetry/` | AlertStream (~5k rows: 54h baseline + 90s cascade), LinkTelemetry (~8.6k rows: 72h 5-min samples) |
| `generate_tickets.py` | 10 `.txt` files → `data/tickets/` | Historical incident tickets for AI Search RAG |

Supporting manifest:
- `data/graph_schema.yaml` — 266-line declarative schema defining 8 vertex types, 11 edge types, CSV file mappings, and property definitions

## Output Structure

A complete scenario produces this file tree:

```
data/scenarios/<scenario-name>/data/
├── entities/                     # Vertex + edge CSVs
│   ├── Dim*.csv                  # One per vertex type (Dim = dimension/entity)
│   └── Fact*.csv                 # One per junction/edge table (Fact = relationship)
├── graph_schema.yaml             # Graph ontology manifest
├── telemetry/                    # Time-series CSVs for Cosmos NoSQL
│   ├── AlertStream.csv           # Alert events (required)
│   └── <OtherMetrics>.csv        # Additional telemetry containers
├── knowledge/
│   ├── runbooks/                 # Operational procedures (.md) for AI Search
│   └── tickets/                  # Historical incidents (.txt) for AI Search
└── prompts/                      # Scenario-specific prompt fragments
    ├── orchestrator.md
    ├── graph_explorer/
    │   ├── core_schema.md        # Auto-generated from graph_schema.yaml
    │   └── core_instructions.md
    ├── telemetry_agent.md
    ├── runbook_agent.md
    ├── ticket_agent.md
    └── default_alert.md
```

## Convention Contract

For generated data to "just work" with the platform, these invariants **must**
hold. See `references/convention-contract.md` for the full specification.

### Critical Rules

1. **Entity IDs are globally unique strings** — every ID referenced in edges,
   telemetry, and tickets must match a vertex ID in the entity CSVs exactly.
2. **CSV file naming**: `Dim*.csv` for vertices, `Fact*.csv` for junction tables.
3. **graph_schema.yaml** must declare every vertex and edge type, map each to
   its CSV file, and list every property column.
4. **Telemetry rows must have NO nulls** in numeric columns — the downstream
   anomaly detector rejects rows with missing values. Use normal-range defaults.
5. **Ticket `.txt` files** use a specific human-readable format with structured
   fields (see `references/ticket-format.md`).

## How to Generate a New Scenario

### Step 1: Design the Domain Ontology

Define the entity types, relationships, and a realistic incident:

```
Domain:       Cloud datacenter
Entities:     Region, AvailabilityZone, Rack, Host, VirtualMachine, LoadBalancer, Service, SLA
Relationships: Region→has_zone→AZ, AZ→has_rack→Rack, Rack→hosts→Host, Host→runs→VM, ...
Incident:     Cooling failure in AZ causes host cascade shutdown
```

### Step 2: Write Topology Generator (`generate_topology.py`)

See `references/topology-patterns.md` for the exact script structure.

Key patterns:
- One function per entity type, each calling a shared `write_csv()` helper
- Entity IDs follow a readable convention: `{TYPE}-{LOCATION}-{SEQUENCE}`
- All data is inline (hardcoded rows, not randomized) for reproducibility
- Foreign key columns reference IDs from other entity tables

### Step 3: Write Routing/Junction Generator (`generate_routing.py`)

Produces `Fact*.csv` files that encode graph edges:
- Junction tables map M:N relationships between entities
- Every row references IDs that exist in the entity CSVs
- Include a `HopOrder` or `DependencyStrength` column for traversal context

### Step 4: Write Alert Stream Generator (`generate_telemetry.py`)

See `references/telemetry-patterns.md` for the exact structure.

Key patterns:
- **Baseline period**: Hours of sporadic low-severity noise (~1 alert/min)
- **Incident cascade**: Root cause → BGP/routing → CPU → packet loss → service degradation → flapping
- **Timeline fidelity**: Events propagate with realistic delays (seconds between tiers)
- **Full telemetry snapshot per row**: ALL numeric columns populated, even if the alert is about only one metric
- **Entity ID lists**: Constants at top of file listing impacted nodes per tier, cross-referencing topology entity IDs
- **Link telemetry**: Separate CSV with 5-min samples per link, baseline + anomaly at incident time

### Step 5: Write Ticket Generator (`generate_tickets.py`)

See `references/ticket-format.md` for the required output format.

Key patterns:
- 8–12 historical incidents covering diverse root cause types
- Each ticket references entity IDs from the topology (root cause, impacted services)
- Tickets span several months before the "current" incident
- Include lessons_learned that reference the ontology and suggest improvements

### Step 6: Write `graph_schema.yaml`

See `references/graph-schema-format.md` for the exact YAML structure.

This file is the **single source of truth** for the graph:
- Vertices: label, csv_file, id_column, partition_key, properties
- Edges: label, csv_file, source/target vertex lookup, properties, optional filter
- The generic Cosmos Gremlin loader reads this manifest — no code changes needed

### Step 7: Write Prompt Fragments

These connect the data to the AI agents:
- `orchestrator.md` — telemetry baseline ranges, alert types, investigation flow
- `graph_explorer/core_instructions.md` — Gremlin traversal patterns using this scenario's edge labels
- `telemetry_agent.md` — Cosmos NoSQL container schemas, partition keys, value ranges
- `default_alert.md` — a realistic alert message that kicks off the demo investigation

## References

Detailed patterns, formats, and examples are in the `references/` directory:

| File | Contents |
|------|----------|
| `convention-contract.md` | The full convention contract with all invariants |
| `topology-patterns.md` | Topology + routing script structure, ID conventions, CSV format |
| `telemetry-patterns.md` | Alert cascade timeline, baseline generation, link telemetry, no-null rule |
| `ticket-format.md` | Ticket `.txt` format, structured fields, entity ID cross-references |
| `graph-schema-format.md` | Complete `graph_schema.yaml` specification with vertex/edge examples |
