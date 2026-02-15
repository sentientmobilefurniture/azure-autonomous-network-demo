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

The `telco-noc` scenario in `data/scenarios/telco-noc/` is the canonical reference:

| Script | Output | Purpose |
|--------|--------|----------|
| `scripts/generate_topology.py` | 8 entity CSVs → `data/entities/` | Vertices: routers, switches, base stations, links, BGP sessions, MPLS paths, services, SLA policies |
| `scripts/generate_routing.py` | 2 junction CSVs → `data/entities/` | Edges: MPLS path hops, service dependencies |
| `scripts/generate_telemetry.py` | 2 telemetry CSVs → `data/telemetry/` | AlertStream (~5k rows: 54h baseline + 90s cascade), LinkTelemetry (~8.6k rows: 72h 5-min samples) |
| `scripts/generate_tickets.py` | 10 `.txt` files → `data/knowledge/tickets/` | Historical incident tickets for AI Search RAG |

Two additional scenarios (`cloud-outage`, `customer-recommendation`) demonstrate
non-telco domains: cloud infrastructure and e-commerce.

Supporting manifests:
- `graph_schema.yaml` — at scenario root, declarative schema defining vertex types, edge types, CSV file mappings
- `scenario.yaml` — scenario manifest with Cosmos mapping, search indexes, graph styles, telemetry baselines

## Output Structure

A complete scenario lives under `data/scenarios/<scenario-name>/` and produces:

```
data/scenarios/<scenario-name>/
├── scenario.yaml                 # Scenario manifest (metadata + cosmos/search config)
├── graph_schema.yaml             # Graph ontology manifest (at scenario root)
├── scripts/                      # Data generation scripts
│   ├── generate_topology.py
│   ├── generate_routing.py
│   ├── generate_telemetry.py
│   └── generate_tickets.py
└── data/                         # Generated output (entities/telemetry gitignored)
    ├── entities/                  # Vertex + edge CSVs
│   ├── Dim*.csv                  # One per vertex type (Dim = dimension/entity)
│   └── Fact*.csv                 # One per junction/edge table (Fact = relationship)
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
- `foundry_orchestrator_agent.md` — investigation flow, telemetry baselines, alert types, sub-agent descriptions, scenario context with graph name
- `foundry_telemetry_agent_v2.md` — Cosmos NoSQL container schemas, partition keys, value ranges, X-Graph header rule
- `graph_explorer/core_instructions.md` — Gremlin traversal patterns using this scenario's edge labels, X-Graph header rule
- `graph_explorer/core_schema.md` — full entity schema with all instances and relationships
- `graph_explorer/description.md` — agent description for Foundry registration
- `graph_explorer/language_gremlin.md` — Gremlin query examples for this scenario's relationships
- `graph_explorer/language_mock.md` — natural language examples for mock mode
- `foundry_runbook_kb_agent.md` — runbook agent prompt with domain-specific runbook descriptions
- `foundry_historical_ticket_agent.md` — ticket agent prompt with domain-specific ticket descriptions
- `default_alert.md` — a realistic alert CSV that kicks off the demo investigation

**CRITICAL: X-Graph Header Rule.** Three prompts MUST contain explicit instructions
telling the agent to include the `X-Graph` header with the concrete scenario graph
name. This is because the Azure AI Foundry OpenApiTool does NOT reliably enforce
`default` or `enum` values from OpenAPI specs — the LLM controls the parameter
value and often ignores schema constraints. The defense-in-depth approach uses
BOTH an OpenAPI `enum` constraint AND a prompt-level CRITICAL RULE.

Files requiring the X-Graph rule:
1. `foundry_orchestrator_agent.md` — "Scenario Context" section stating the active graph name
2. `foundry_telemetry_agent_v2.md` — CRITICAL RULE #7: "Always include the X-Graph header with value `<scenario>-topology`"
3. `graph_explorer/core_instructions.md` — CRITICAL RULE #6: "Always include the X-Graph header with value `<scenario>-topology`"

The graph name follows the pattern `<scenario-name>-topology` (e.g., `telco-noc-topology`,
`cloud-outage-topology`, `customer-recommendation-topology`). The telemetry database
is derived at runtime: `rsplit("-", 1)[0]` + `-telemetry` (e.g., `telco-noc-telemetry`).

**Scenario prompts must use concrete values, not placeholders.** The scenario-specific
prompts (in `data/scenarios/<name>/data/prompts/`) are uploaded to Cosmos DB and used
by the API provisioner, which does NOT perform placeholder substitution. Use the actual
graph name (e.g., `cloud-outage-topology`), not `{graph_name}`.

## References

Detailed patterns, formats, and examples are in the `references/` directory:

| File | Contents |
|------|----------|
| `convention-contract.md` | The full convention contract with all invariants |
| `topology-patterns.md` | Topology + routing script structure, ID conventions, CSV format |
| `telemetry-patterns.md` | Alert cascade timeline, baseline generation, link telemetry, no-null rule |
| `ticket-format.md` | Ticket `.txt` format, structured fields, entity ID cross-references |
| `graph-schema-format.md` | Complete `graph_schema.yaml` specification with vertex/edge examples |
