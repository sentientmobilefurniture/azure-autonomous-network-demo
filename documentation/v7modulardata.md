# V7: Modular Data — Multi-Scenario Architecture Plan

## Goal

Decouple the application from the current hardcoded "Australian Telco NOC" dataset
so that **multiple scenarios** can coexist. A user selects a scenario (e.g.
"telco-fibre-cut", "cloud-datacenter-outage", "power-grid-fault") and the entire
stack — data generation, graph schema, prompts, telemetry, runbooks, tickets,
alert storms, and agent configuration — resolves to that scenario's data.

The application becomes a **scenario-agnostic incident investigation platform**.
New scenarios are created by authoring a data pack — no code changes required.

### Core Ambition: Multi-Scenario Runtime

Multiple scenarios are **deployed and loaded simultaneously**. The frontend
provides a dropdown selector so the user can switch between scenarios (e.g.
"Australian Telco NOC" → "Cloud DC Outage") without redeployment. This is a
**first-class design goal**, not a stretch target — every phase is designed
with multi-scenario coexistence in mind:

- All Cosmos DB, AI Search, and Blob Storage resources use **scenario-prefixed
  naming** from the start (no retrofit needed)
- The deployment pipeline accepts a list of scenarios to provision
- The graph-query-api routes requests to the correct scenario's data stores
- Agent prompts are re-composed on scenario switch
- The frontend adapts its UI (node styles, default alerts, domain labels)
  dynamically based on the selected scenario

---

## Current State — What's Coupled

Every layer of the stack currently has hardcoded references to the Australian
telco network scenario. Here's the full inventory:

### 1. Data Generation (`data/scripts/`)

| File | Coupling |
|------|----------|
| `generate_topology_data.py` | Hardcoded entity tables: `DimCoreRouter` (SYD/MEL/BNE), `DimTransportLink`, `DimAggSwitch`, `DimBaseStation`, `DimBGPSession`, `DimMPLSPath`, `DimService`, `DimSLAPolicy` — all with inline row data |
| `generate_routing_data.py` | Hardcoded junction tables: `FactMPLSPathHops`, `FactServiceDependency` — inline row data referencing entity IDs |
| `generate_alert_stream.py` | 409 lines of hardcoded alert cascade logic — incident timeline, entity ID lists (`IMPACTED_SYD_ROUTERS`, `REROUTE_LINKS`), baseline noise parameters, telemetry value ranges |
| `generate_tickets.py` | 10 hardcoded incident tickets with entity IDs, service names, resolution details |

**Output paths:** All scripts write to sibling directories (`../network/`, `../telemetry/`, `../tickets/`).

### 2. Graph Schema (`data/graph_schema.yaml`)

- `data_dir: data/network` — hardcoded path
- 8 vertex types and 11 edge definitions that define the telco ontology (CoreRouter, AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession)
- The ingestion script (`provision_cosmos_gremlin.py`) is already generic — it reads any YAML manifest. This is the **one piece that's already decoupled**.

### 3. Agent Prompts (`data/prompts/`)

| File | Coupling |
|------|----------|
| `foundry_orchestrator_agent.md` | References specific entity types, example IDs (`LINK-SYD-MEL-FIBRE-01`, `VPN-ACME-CORP`), telemetry baselines (optical power, BER, CPU, packet loss ranges), container names (`AlertStream`, `LinkTelemetry`) |
| `graph_explorer/core_schema.md` | 227-line full schema dump — all entity types, all properties, all instances with values, all relationships. This is the telco ontology embedded in the prompt. |
| `graph_explorer/core_instructions.md` | References "telecommunications network" and entity types but is relatively generic |
| `graph_explorer/language_gremlin.md` | Gremlin query patterns — generic (query language, not data) |
| `graph_explorer/language_mock.md` | Mock backend query patterns — generic (query language, not data) |
| `foundry_telemetry_agent_v2.md` | Container schemas (`AlertStream`, `LinkTelemetry`) with property names, types, value ranges |
| `foundry_historical_ticket_agent.md` | Likely references ticket format specifics |
| `foundry_runbook_kb_agent.md` | Likely references runbook format specifics |
| `alert_storm.md` | Pre-baked 20-row CSV alert storm — the default demo input |

### 4. Deployment & Ingestion

| Component | Coupling |
|-----------|----------|
| `postprovision.sh` | Uploads from `data/runbooks/`, `data/tickets/`, `data/telemetry/`, `data/network/` — all hardcoded paths |
| `deploy_app.sh` | Calls `provision_cosmos_gremlin.py` and `provision_cosmos_telemetry.py` — references `data/graph_schema.yaml` |
| `create_runbook_indexer.py` | Index name `runbooks-index`, container `runbooks` — but these come from env vars |
| `create_tickets_indexer.py` | Index name `tickets-index`, container `tickets` — but these come from env vars |

### 5. Telemetry Backend (`graph-query-api/`)

| Component | Coupling |
|-----------|----------|
| `router_telemetry.py` | `VALID_CONTAINERS = {"AlertStream", "LinkTelemetry"}` — hardcoded container names |
| `backends/mock.py` | 200+ lines of hardcoded mock data (routers, links, switches, services, topology nodes/edges) |
| `config.py` | Database names: `networkgraph`, `topology`, `telemetrydb` — from env vars with hardcoded defaults |

### 6. Frontend

| Component | Coupling |
|-----------|----------|
| `useInvestigation.ts` | `DEFAULT_ALERT` is a hardcoded VPN-ACME-CORP alert string |
| `graphConstants.ts` | `NODE_COLORS` and `NODE_SIZES` are `Record<string, string/number>` keyed to 8 telco entity types (`CoreRouter`, `AggSwitch`, `BaseStation`, `TransportLink`, `MPLSPath`, `Service`, `SLAPolicy`, `BGPSession`). Unknown labels fall back to grey/#6B7280 and size 6 — functional but visually indistinct for new scenarios |

### 7. App Branding & Identity

| Component | Coupling |
|-----------|----------|
| `Header.tsx` | Title hardcoded to `"Autonomous Network NOC"`, subtitle `"Multi-agent diagnosis"` |
| `GraphToolbar.tsx` | Panel title hardcoded to `"◆ Network Topology"` |
| `index.html` | `<title>` hardcoded to `"Autonomous Network NOC"` |
| `graph-query-api/openapi/cosmosdb.yaml` | API description references "telecommunications network topology", example queries use telco entity IDs |

---

## Genericity Audit — Will Arbitrary Datasets Work?

Full layer-by-layer assessment of what's already generic vs what needs work.
The **convention contract** (what any dataset must provide) is defined at the end.

### Layer 1: Graph-Query-API — Already Generic

| Component | Generic? | Notes |
|-----------|----------|-------|
| `router_graph.py` | YES | Pure pass-through: receives a Gremlin string, executes it, returns `{columns, data}`. No entity assumptions. |
| `router_topology.py` | YES | Delegates to `backend.get_topology()` which builds `g.V()...project('id','label','properties')` + `g.E()...` dynamically. Supports optional `vertex_labels` filter. No hardcoded labels. |
| `backends/cosmosdb.py` | YES | `execute_query()` runs arbitrary Gremlin, `get_topology()` uses generic traversals. Result normalisation (`_normalise_results`, `_flatten_valuemap`) is type-agnostic. |
| `backends/mock.py` | NO | 200+ lines of hardcoded telco topology. **Must be replaced** with CSV-driven loading (Phase 4.2 in plan). |
| `models.py` | PARTIAL | `TopologyNode.label: str`, `TopologyNode.properties: dict[str, Any]` — fully generic. Comment says "(CoreRouter, AggSwitch, etc.)" but that's just documentation, not code. However, `TelemetryQueryRequest.container_name` defaults to `"AlertStream"` — after a scenario switch the default could point to a nonexistent container (see M8). |
| `config.py` | YES | Database/graph names from env vars. Defaults: database `networkgraph`, graph `topology`, NoSQL database `telemetrydb`. These become scenario-prefixed in v7. |
| `router_telemetry.py` | PARTIAL | The SQL execution engine (`_execute_cosmos_sql`) is fully generic — any Cosmos SQL against any container. But `VALID_CONTAINERS` is hardcoded to `{"AlertStream", "LinkTelemetry"}`. |
| `openapi/cosmosdb.yaml` | NO | `description` references telco entities, `enum: ["AlertStream", "LinkTelemetry"]` is hardcoded, example queries use telco IDs. **Must be scenario-generated.** |

**Verdict:** The query execution engine is already data-agnostic. The coupling is in the OpenAPI spec (what the LLM sees as tool documentation) and the mock backend.

### Layer 2: Agent Prompts — The Most Coupled Layer

This is where domain knowledge lives. The LLM agents rely entirely on prompt
instructions to know what entities exist, what queries to write, and how to
interpret results.

| Prompt File | Generic? | What's Coupled |
|-------------|----------|----------------|
| `orchestrator_agent.md` | PARTIAL | **Investigation methodology is generic** (Flow A: infra→impact, Flow B: alert storm→root cause). But: telemetry baselines table is telco-specific (OpticalPowerDbm, BitErrorRate, etc.), agent descriptions reference telco entities ("routers, links, switches…"), example queries use telco IDs. |
| `graph_explorer/core_instructions.md` | PARTIAL | The investigation patterns (forward dependency, reverse dependency, alternate path discovery) are **generic graph traversal patterns**. But: "What you can answer" section lists telco concepts (routers, MPLS paths, SLA policies, BGP). "Use exact entity IDs with correct casing" is generic. |
| `graph_explorer/core_schema.md` | NO | 227-line full dump of 8 telco entity types with all instances and properties. **Must be auto-generated** from `graph_schema.yaml` + CSVs per Phase 3.2. |
| `graph_explorer/language_gremlin.md` | YES | Pure Gremlin query patterns — `g.V().hasLabel()`, `valueMap(true)`, etc. Language-level, not data-level. Works for any label. |
| `telemetry_agent_v2.md` | PARTIAL | The SQL query methodology is generic ("use `FROM c`", "use `TOP N ... ORDER BY`"). But: container schemas (`AlertStream` properties, `LinkTelemetry` properties) are telco-specific. |
| `runbook_kb_agent.md` | YES | Searches an AI Search index. Generic — "search operational runbooks for procedures". Works with any knowledge base content. |
| `ticket_agent.md` | YES | Searches an AI Search index. Generic — "search historical incident tickets". Works with any ticket content. |

**Key insight:** The agent *architecture* is generic. The LLM receives a query
tool and a prompt describing the schema. If we swap the prompt to describe
"Region → Rack → Host → VM" instead of "CoreRouter → AggSwitch → BaseStation",
the same agent will write correct Gremlin/SQL for the new schema. The
investigation methodology (trace dependencies, confirm with telemetry, check
runbooks, find precedents) is domain-agnostic.

### Layer 3: Investigation Flow (orchestrator.py) — Already Generic

| Component | Generic? | Notes |
|-----------|----------|-------|
| `orchestrator.py` | YES | Pure plumbing: loads agent IDs from `agent_ids.json`, creates a thread, streams SSE events. No entity types, no domain logic. |
| `api/app/routers/alert.py` | YES | Generic alert POST handler — receives text, passes to orchestrator. |
| `agent_ids.json` | YES |  Maps agent names to IDs. No domain content. |
| Investigation flow (Flow A / Flow B) | YES | The flows are in the orchestrator *prompt*, not in code. The code just streams whatever the LLM decides to do. |

**Verdict:** The backend Python/TypeScript code is already scenario-agnostic.
The domain coupling is 100% in the prompt layer and the OpenAPI tool descriptions.

### Layer 4: Frontend Graph Visualizer — ~90% Generic

(Detailed in Phase 4.4 above.) Summary: `GraphCanvas`, `GraphTooltip`, `useTopology`
are fully generic. Only `graphConstants.ts` has hardcoded entity-type styling.

### The Convention Contract

For **any** dataset to work with this stack, it must provide:

```
1. Graph data (CSVs):
   - Vertex CSV files with an ID column matching the graph schema
   - Edge CSV files with source/target ID columns
   - A graph_schema.yaml manifest listing vertices, edges, properties, CSV files

2. Telemetry data (CSVs):
   - One or more container CSVs (analogous to AlertStream/LinkTelemetry)
   - Each with a partition key, ID field, and typed columns
   - Defined in scenario.yaml under cosmos.nosql.containers

3. Knowledge data:
   - Runbook .md files (indexed in AI Search)
   - Historical ticket .txt files (indexed in AI Search)

4. Prompt fragments:
   - orchestrator.md — telemetry baselines for THIS domain
   - graph_explorer/core_schema.md — auto-generated from graph_schema.yaml
   - telemetry_agent.md — container schemas with property names and ranges
   - default_alert.md — a demo alert input for this scenario

5. Scenario manifest (scenario.yaml):
   - Cosmos mapping (database names, container definitions)
   - Search index names and blob container names
   - Graph visualisation styles (node colours, sizes per entity type)
   - Telemetry baselines (metric names, normal/degraded/down ranges)
```

As long as a dataset provides these artefacts following the manifest contract,
the entire stack — graph queries, telemetry queries, agent investigation,
knowledge retrieval, and graph visualisation — works without code changes.

---

## Target Architecture

### Directory Structure

```
data/
├── scenarios/
│   ├── telco-noc/                        # Current scenario, relocated
│   │   ├── scenario.yaml                 # Scenario manifest (metadata + pointers)
│   │   ├── generator/                    # Data generation scripts
│   │   │   ├── generate_topology.py      # Produces entities/ CSVs
│   │   │   ├── generate_routing.py       # Produces entities/ junction tables
│   │   │   ├── generate_telemetry.py     # Produces telemetry/ CSVs
│   │   │   └── generate_tickets.py       # Produces knowledge/tickets/ files
│   │   └── data/                         # Generated output (gitignored)
│   │       ├── entities/                 # Vertex + edge CSVs
│   │       │   ├── DimCoreRouter.csv
│   │       │   ├── DimTransportLink.csv
│   │       │   ├── ...
│   │       │   ├── FactMPLSPathHops.csv
│   │       │   └── FactServiceDependency.csv
│   │       ├── graph_schema.yaml         # Graph ontology (vertices + edges)
│   │       ├── telemetry/                # Alert + link telemetry CSVs
│   │       │   ├── AlertStream.csv
│   │       │   └── LinkTelemetry.csv
│   │       ├── knowledge/                # RAG-indexed documents
│   │       │   ├── runbooks/             # Operational procedures (.md)
│   │       │   └── tickets/              # Historical incidents (.txt)
│   │       └── prompts/                  # Scenario-specific prompt fragments
│   │           ├── orchestrator.md        # Investigation flow + telemetry baselines
│   │           ├── graph_explorer/        # Schema, instructions, query examples
│   │           ├── telemetry_agent.md     # Container schemas + value ranges
│   │           ├── runbook_agent.md
│   │           ├── ticket_agent.md
│   │           └── default_alert.md      # Default demo alert storm input
│   │
│   ├── cloud-outage/                     # Future scenario
│   │   ├── scenario.yaml
│   │   ├── generator/
│   │   └── data/
│   │
│   └── power-grid/                       # Future scenario
│       ├── scenario.yaml
│       ├── generator/
│       └── data/
│
└── scenario_template/                    # Scaffolding for new scenarios
    ├── scenario.yaml.template
    ├── generator/
    │   ├── generate_topology.py.template
    │   ├── generate_routing.py.template
    │   ├── generate_telemetry.py.template
    │   └── generate_tickets.py.template
    └── data/
        ├── graph_schema.yaml.template
        └── prompts/
            ├── orchestrator.md.template
            ├── graph_explorer/
            │   ├── core_instructions.md.template
            │   ├── core_schema.md.template
            │   └── language_gremlin.md.template
            ├── telemetry_agent.md.template
            ├── runbook_agent.md.template
            ├── ticket_agent.md.template
            └── default_alert.md.template
```

### Scenario Manifest (`scenario.yaml`)

Each scenario is fully described by a single manifest file:

```yaml
# ============================================================================
# Scenario Manifest — Telco NOC (Fibre Cut)
# ============================================================================

name: telco-noc
display_name: "Australian Telco NOC — Fibre Cut Incident"
description: >
  A fibre cut on the Sydney-Melbourne corridor triggers a cascading alert
  storm affecting enterprise VPNs, broadband, and mobile services. The AI
  investigates root cause, blast radius, and remediation.
version: "1.0"
domain: telecommunications

# ---------------------------------------------------------------------------
# Data layout — paths relative to this file's parent directory
# ---------------------------------------------------------------------------

paths:
  entities: data/entities              # CSV files for graph vertices + edges
  graph_schema: data/graph_schema.yaml # Gremlin ingestion manifest
  telemetry: data/telemetry            # AlertStream.csv, LinkTelemetry.csv
  runbooks: data/knowledge/runbooks    # .md files → AI Search
  tickets: data/knowledge/tickets      # .txt files → AI Search
  prompts: data/prompts                # Agent prompt fragments
  default_alert: data/prompts/default_alert.md  # Default demo input

# ---------------------------------------------------------------------------
# Cosmos DB mapping (names are scenario-prefixed at deploy time)
# ---------------------------------------------------------------------------

cosmos:
  gremlin:
    database: networkgraph            # shared database
    graph: topology                   # deploy script prefixes: telco-noc-topology
  nosql:
    database: telemetrydb             # deploy script prefixes: telco-noc-telemetrydb
    containers:
      - name: AlertStream
        partition_key: /SourceNodeType
        csv_file: AlertStream.csv
        id_field: AlertId
        numeric_fields: [OpticalPowerDbm, BitErrorRate, CPUUtilPct, PacketLossPct]
      - name: LinkTelemetry
        partition_key: /LinkId
        csv_file: LinkTelemetry.csv
        id_field: null  # composite: LinkId + Timestamp
        numeric_fields: [UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs]

# ---------------------------------------------------------------------------
# AI Search indexes
# ---------------------------------------------------------------------------

search_indexes:
  - name: runbooks-index
    container: runbooks          # blob storage container name
    source: data/knowledge/runbooks
  - name: tickets-index
    container: tickets
    source: data/knowledge/tickets

# ---------------------------------------------------------------------------
# Graph visualisation hints (frontend node styling)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Telemetry baselines (used to generate prompt sections)
# ---------------------------------------------------------------------------

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

---

## Implementation Plan

### Phase 1: Scenario Loader + Directory Restructure

**Goal:** Create the `ScenarioLoader` utility and relocate the current dataset
into `data/scenarios/telco-noc/` without breaking anything.

#### 1.1 Create `ScenarioLoader` Python module

Location: `scripts/scenario_loader.py`

```python
class ScenarioLoader:
    """Resolves all paths and config for a named scenario."""

    def __init__(self, scenario_name: str, scenarios_root: Path = None):
        self.name = scenario_name
        self.root = (scenarios_root or SCENARIOS_DIR) / scenario_name
        self.manifest = yaml.safe_load((self.root / "scenario.yaml").read_text())

    @property
    def entities_dir(self) -> Path: ...
    @property
    def graph_schema(self) -> Path: ...
    @property
    def telemetry_dir(self) -> Path: ...
    @property
    def runbooks_dir(self) -> Path: ...
    @property
    def tickets_dir(self) -> Path: ...
    @property
    def prompts_dir(self) -> Path: ...
    @property
    def default_alert(self) -> str: ...
    @property
    def cosmos_config(self) -> dict: ...
    @property
    def search_indexes(self) -> list[dict]: ...
    @property
    def graph_styles(self) -> dict: ...
    @property
    def telemetry_baselines(self) -> dict: ...

    @classmethod
    def list_scenarios(cls, scenarios_root: Path = None) -> list[dict]: ...
```

The loader reads `scenario.yaml` and provides typed accessors to every path
and config block. All downstream scripts import this instead of hardcoding paths.

#### 1.2 Relocate current data to `data/scenarios/telco-noc/`

Move current files into the new directory structure:

```
Current                              → New
data/network/*.csv                   → data/scenarios/telco-noc/data/entities/*.csv
data/graph_schema.yaml               → data/scenarios/telco-noc/data/graph_schema.yaml
data/telemetry/*.csv                 → data/scenarios/telco-noc/data/telemetry/*.csv
data/runbooks/*.md                   → data/scenarios/telco-noc/data/knowledge/runbooks/*.md
data/tickets/*.txt                   → data/scenarios/telco-noc/data/knowledge/tickets/*.txt
data/prompts/foundry_orchestrator_agent.md    → data/scenarios/telco-noc/data/prompts/orchestrator.md
data/prompts/graph_explorer/         → data/scenarios/telco-noc/data/prompts/graph_explorer/
data/prompts/foundry_telemetry_agent_v2.md    → data/scenarios/telco-noc/data/prompts/telemetry_agent.md
data/prompts/foundry_runbook_kb_agent.md      → data/scenarios/telco-noc/data/prompts/runbook_agent.md
data/prompts/foundry_historical_ticket_agent.md → data/scenarios/telco-noc/data/prompts/ticket_agent.md
data/prompts/alert_storm.md          → data/scenarios/telco-noc/data/prompts/default_alert.md
data/prompts/graph_explorer/description.md  → data/scenarios/telco-noc/data/prompts/graph_explorer/description.md
data/prompts/graph_explorer/language_mock.md → data/scenarios/telco-noc/data/prompts/graph_explorer/language_mock.md
data/scripts/generate_topology_data.py   → data/scenarios/telco-noc/generator/generate_topology.py
data/scripts/generate_routing_data.py    → data/scenarios/telco-noc/generator/generate_routing.py
data/scripts/generate_alert_stream.py    → data/scenarios/telco-noc/generator/generate_telemetry.py
data/scripts/generate_tickets.py         → data/scenarios/telco-noc/generator/generate_tickets.py
```

**Backwards compatibility:** Create symlinks at old locations pointing to new
ones so nothing breaks during the transition. Remove symlinks once all consumers
are updated.

#### 1.3 Write `data/scenarios/telco-noc/scenario.yaml`

As specified in the Target Architecture section above.

#### 1.4 Add scenario env vars to azure_config.env

```bash
# Default scenario shown on UI load
DEFAULT_SCENARIO=telco-noc

# Comma-separated list of scenarios to deploy/load into Cosmos + AI Search.
# Use "all" to deploy every scenario in data/scenarios/.
LOADED_SCENARIOS=telco-noc
```

Template, env file, and azd env sync all need these variables. `DEFAULT_SCENARIO`
determines the frontend's initial state; `LOADED_SCENARIOS` determines what
data is ingested into Cosmos DB, AI Search, and Blob Storage.

**Tasks:**
- [ ] Create `scripts/scenario_loader.py` with `ScenarioLoader` class
- [ ] Create `data/scenarios/telco-noc/` directory structure
- [ ] Move all data files into new structure (use git mv for history)
- [ ] Write `scenario.yaml` for telco-noc
- [ ] Add `DEFAULT_SCENARIO` + `LOADED_SCENARIOS` to `azure_config.env.template`
- [ ] Create backwards-compat symlinks at old locations
- [ ] Test that existing `deploy_app.sh` still works with symlinks

---

### Phase 2: Blob-First Ingestion Architecture

**Goal:** Move all data ingestion to a **Blob → Container App → Cosmos** pattern.
Scenario CSVs are uploaded to Blob Storage (easy, no firewall issues), then the
Container App — which is inside the VNet with private endpoint access to Cosmos
— reads from blob and ingests into Cosmos DB. This eliminates the current pain
point of needing direct public network access from a dev machine to Cosmos.

#### 2.0 Why Blob-First?

The current flow runs `provision_cosmos_gremlin.py` and
`provision_cosmos_telemetry.py` from a developer's machine (or CI), connecting
directly to Cosmos over the public endpoint. This is fragile because:

1. **Firewall gates it** — Cosmos Gremlin is behind `ipRules` + private
   endpoints. Your IP changes, corporate VPN blocks WSS on 443, Azure policy
   toggles `publicNetworkAccess` off, etc.
2. **Private endpoints mean the Container App can reach Cosmos, but external
   clients can't** — so the only reliable ingestion path is from inside the VNet.
3. **`postprovision.sh` already uploads all data to blob** — runbooks, tickets,
   telemetry CSVs, network CSVs. The blob upload path uses RBAC (`--auth-mode login`)
   and is highly reliable.
4. **`provision_cosmos_telemetry.py` already has `--from-blob` support** —
   `_load_csv_blob()` downloads CSVs from the `telemetry-data` blob container.
   Only the Gremlin script is missing this.

The new flow:

```
Generate CSVs        Upload to Blob       Container App ingests
(local / CI)    →    (postprovision.sh) →  (inside VNet, private endpoints)
                     Easy, RBAC auth       Reliable, no firewall issues
```

#### 2.1 Refactor ingestion scripts into importable modules

The current scripts (`provision_cosmos_gremlin.py`, `provision_cosmos_telemetry.py`)
are CLI-only (argparse + `__main__`). They cannot be called from a running
FastAPI server. Refactor into importable functions:

```python
# scripts/cosmos/ingest_gremlin.py (new — extracted from provision_cosmos_gremlin.py)

async def ingest_gremlin_from_blob(
    scenario_name: str,
    storage_account: str,
    blob_container: str,       # e.g. "telco-noc-network-data"
    cosmos_endpoint: str,
    cosmos_key: str,
    database: str,             # "networkgraph"
    graph: str,                # "telco-noc-topology"
    schema_blob: str,          # "graph_schema.yaml" within the blob container
    clear_first: bool = True,
) -> dict:  # returns {vertices: int, edges: int}
    ...

# scripts/cosmos/ingest_telemetry.py (refactored from provision_cosmos_telemetry.py)

async def ingest_telemetry_from_blob(
    scenario_name: str,
    storage_account: str,
    blob_container: str,       # e.g. "telco-noc-telemetry-data"
    cosmos_endpoint: str,
    database: str,             # "telco-noc-telemetry"
    containers: list[dict],    # from scenario.yaml cosmos.nosql.containers
    clear_first: bool = True,
) -> dict:  # returns {container_name: doc_count, ...}
    ...
```

Keep the CLI wrappers (`provision_cosmos_gremlin.py`, etc.) as thin entry
points that call these functions — backwards compatibility for manual use.

#### 2.2 Add `--from-blob` support to Gremlin ingestion

The telemetry script already has `_load_csv_blob()`. Add the same pattern to
the Gremlin script:

```python
async def _load_csv_blob(credential, storage_account: str,
                          blob_container: str, csv_file: str) -> list[dict]:
    """Download a CSV from Azure Blob Storage and parse it."""
    from azure.storage.blob.aio import BlobServiceClient
    blob_url = f"https://{storage_account}.blob.core.windows.net"
    async with BlobServiceClient(blob_url, credential=credential) as bsc:
        blob = bsc.get_blob_client(blob_container, csv_file)
        stream = await blob.download_blob()
        content = await stream.readall()
        return list(csv.DictReader(io.StringIO(content.decode("utf-8"))))
```

Also upload `graph_schema.yaml` to the blob container alongside the CSVs so
the Container App can read the schema manifest without filesystem access.

#### 2.3 Create Cosmos resources dynamically (graphs + NoSQL databases)

Cosmos Gremlin graphs and NoSQL databases/containers must exist before data
can be ingested. Currently Bicep creates exactly one graph (`topology`) and
one NoSQL database (`telemetry`). For multi-scenario, additional resources
are needed.

**Approach: Azure CLI in `postprovision.sh`** (simplest, avoids Bicep loops):

```bash
for SCENARIO in $(echo "$LOADED_SCENARIOS" | tr ',' ' '); do
  GRAPH_NAME="${SCENARIO}-topology"
  NOSQL_DB="${SCENARIO}-telemetry"

  # Create Gremlin graph if it doesn't exist
  az cosmosdb gremlin graph create \
    --account-name "$COSMOS_GREMLIN_ACCOUNT_NAME" \
    --database-name networkgraph \
    --name "$GRAPH_NAME" \
    --partition-key-path /partitionKey \
    --max-throughput 1000 \
    --resource-group "$AZURE_RESOURCE_GROUP" 2>/dev/null || true

  # Create NoSQL database if it doesn't exist
  az cosmosdb sql database create \
    --account-name "${COSMOS_GREMLIN_ACCOUNT_NAME}-nosql" \
    --name "$NOSQL_DB" \
    --resource-group "$AZURE_RESOURCE_GROUP" 2>/dev/null || true
done
```

NoSQL containers (`AlertStream`, `LinkTelemetry`) continue to be created at
ingestion time via `create_container_if_not_exists` — this already works.

#### 2.4 Update `postprovision.sh` for scenario-aware blob uploads

Currently uploads from `data/runbooks/`, `data/tickets/`, etc. Changes:
- Read `LOADED_SCENARIOS` from env (comma-separated list or "all")
- Iterate over each scenario and upload its data to scenario-prefixed containers:

```bash
for SCENARIO in $(echo "$LOADED_SCENARIOS" | tr ',' ' '); do
  SCENARIO_DIR="data/scenarios/$SCENARIO"

  # Upload graph data (CSVs + schema manifest)
  upload_with_retry "${SCENARIO}-network-data" "$SCENARIO_DIR/data/entities"
  az storage blob upload \
    --account-name "$STORAGE_ACCOUNT" \
    --container-name "${SCENARIO}-network-data" \
    --file "$SCENARIO_DIR/data/graph_schema.yaml" \
    --name "graph_schema.yaml" \
    --auth-mode login --overwrite

  # Upload telemetry CSVs
  upload_with_retry "${SCENARIO}-telemetry-data" "$SCENARIO_DIR/data/telemetry"

  # Upload knowledge base documents
  upload_with_retry "${SCENARIO}-runbooks" "$SCENARIO_DIR/data/knowledge/runbooks"
  upload_with_retry "${SCENARIO}-tickets" "$SCENARIO_DIR/data/knowledge/tickets"

  # Create Cosmos resources (graphs + databases) via CLI
  # ... (see 2.3 above)
done
```

#### 2.5 Add Container App ingestion endpoint

Add `POST /api/scenario/{name}/ingest` to the main API (port 8000). This
endpoint runs inside the VNet and has private endpoint access to Cosmos:

```python
@router.post("/api/scenario/{scenario_name}/ingest")
async def ingest_scenario(scenario_name: str, background_tasks: BackgroundTasks):
    """Ingest a scenario's data from blob storage into Cosmos DB.

    Reads CSVs from scenario-prefixed blob containers and loads them
    into the scenario's Cosmos DB graph + telemetry databases.
    """
    # Validate scenario exists in LOADED_SCENARIOS
    # Start async ingestion:
    #   1. ingest_gremlin_from_blob() — read from {scenario}-network-data blob
    #   2. ingest_telemetry_from_blob() — read from {scenario}-telemetry-data blob
    # Return immediately with a task ID for polling
    background_tasks.add_task(_run_ingestion, scenario_name)
    return {"status": "started", "scenario": scenario_name}

@router.get("/api/scenario/{scenario_name}/ingest/status")
async def ingest_status(scenario_name: str):
    """Check ingestion progress."""
    return {"status": "...", "vertices": ..., "edges": ..., "telemetry_docs": ...}
```

This endpoint is called by `postprovision.sh` after blob uploads complete:
```bash
# After uploading blobs, trigger ingestion for each scenario
for SCENARIO in $(echo "$LOADED_SCENARIOS" | tr ',' ' '); do
  echo "Triggering ingestion for $SCENARIO..."
  curl -s -X POST "$APP_URI/api/scenario/$SCENARIO/ingest"
done
```

#### 2.6 Self-initialisation on startup (optional, recommended)

The Container App can detect empty Cosmos containers on startup and
auto-ingest from blob:

```python
# Use the modern FastAPI lifespan pattern (on_event("startup") is deprecated)
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """If the default scenario's graph is empty, ingest from blob."""
    scenario = os.getenv("DEFAULT_SCENARIO", "telco-noc")
    if await _graph_is_empty(scenario):
        logger.info(f"Empty graph for {scenario} — auto-ingesting from blob")
        await _run_ingestion(scenario)
    yield  # app runs

app = FastAPI(lifespan=lifespan)
```

This makes fresh deployments fully zero-touch: `azd up` → Bicep provisions
resources → `postprovision.sh` uploads to blob → Container App starts →
auto-ingests from blob → ready. No manual ingestion step needed.

#### 2.7 Update AI Search indexer scripts

Currently use env vars for index name and container name. Changes:
- Read from `ScenarioLoader.search_indexes` manifest entries
- Index names **must** be scenario-prefixed (e.g. `telco-noc-runbooks-index`)
  to allow multiple scenarios' indexes to coexist in the same AI Search service
- Blob containers must also be scenario-prefixed (e.g. `telco-noc-runbooks`)
- Iterate over all `LOADED_SCENARIOS` — create indexes for each

#### 2.8 Update `deploy_app.sh` / `deploy.sh`

- Add `--scenarios NAME[,NAME...]` flag (default: `telco-noc`)
- Support `--scenarios all` to deploy every scenario in `data/scenarios/`
- Set `DEFAULT_SCENARIO` and `LOADED_SCENARIOS` in env file
- Pass scenario list to `postprovision.sh` for blob uploads
- After app is deployed, trigger ingestion endpoint for each scenario

#### 2.9 Add `gremlinpython` to graph-query-api / api dependencies

Currently `gremlinpython` is only in the root `pyproject.toml`. If the API
service runs Gremlin ingestion, add it to `api/pyproject.toml`. Alternatively,
keep ingestion modules in a shared `lib/` package.

**Tasks:**
- [ ] Refactor `provision_cosmos_gremlin.py` into importable `ingest_gremlin_from_blob()`
- [ ] Refactor `provision_cosmos_telemetry.py` into importable `ingest_telemetry_from_blob()`
- [ ] Add `--from-blob` support to Gremlin ingestion (download CSVs + schema from blob)
- [ ] Upload `graph_schema.yaml` to blob alongside CSVs in `postprovision.sh`
- [ ] Add Cosmos resource creation (graphs + databases) via Azure CLI in `postprovision.sh`
- [ ] Add `POST /api/scenario/{name}/ingest` endpoint to main API
- [ ] Add `GET /api/scenario/{name}/ingest/status` polling endpoint
- [ ] Implement startup self-initialisation (auto-ingest if graph empty)
- [ ] Update `postprovision.sh` to iterate `LOADED_SCENARIOS` for blob uploads
- [ ] Update `_indexer_common.py` / indexer scripts for scenario-aware paths
- [ ] Add `--scenarios` flag (multi-value) to `deploy_app.sh`
- [ ] Add `gremlinpython` to `api/pyproject.toml` (or shared lib)
- [ ] Test full deployment pipeline with `telco-noc` scenario
- [ ] Test deployment with two scenarios loaded simultaneously

---

### Phase 3: Decouple Agent Prompts

**Goal:** Agent prompts are assembled from scenario-specific fragments, not
hardcoded markdown files.

#### 3.1 Prompt Composition Strategy

The orchestrator prompt has three layers of coupling:
1. **Domain-agnostic** — investigation methodology, agent delegation rules,
   situation report format. These are **shared** across all scenarios.
2. **Domain-specific** — entity type names, telemetry baselines, example queries.
   These come from the **scenario manifest** or the scenario's prompt fragments.
3. **Graph-backend-specific** — Gremlin vs mock query language. Already handled
   by the `GRAPH_BACKEND` system.

**Approach:** Split each prompt into a **core template** (shared) and
**scenario fragment** (from `scenario.yaml` or the scenario's `prompts/` dir):

```
Orchestrator prompt = 
    shared/orchestrator_core.md           (methodology, report format)
  + scenario/prompts/orchestrator.md      (entity types, example IDs, baselines)

GraphExplorer prompt =
    shared/graph_explorer_core.md         (role, rules)
  + scenario/prompts/graph_explorer/schema.md    (full ontology)
  + graph_backend/language_{backend}.md   (query language)

Telemetry prompt =
    shared/telemetry_core.md              (role, SQL rules)
  + scenario/prompts/telemetry_agent.md   (container schemas, value ranges)
```

#### 3.2 Auto-generate schema prompt from graph_schema.yaml

Instead of manually maintaining a 227-line `core_schema.md`, generate it from
the graph schema manifest + CSV headers:

```python
def generate_schema_prompt(scenario: ScenarioLoader) -> str:
    """Read graph_schema.yaml + CSV headers → markdown schema prompt."""
    schema = yaml.safe_load(scenario.graph_schema.read_text())
    sections = []
    for vertex in schema["vertices"]:
        # Read CSV to get sample data and column types
        csv_path = scenario.entities_dir / vertex["csv_file"]
        rows = list(csv.DictReader(open(csv_path)))
        section = f"### {vertex['label']} ({len(rows)} instances)\n\n"
        section += "| Column | Example |\n|---|---|\n"
        for prop in vertex["properties"]:
            example = rows[0].get(prop, "") if rows else ""
            section += f"| **{prop}** | `{example}` |\n"
        sections.append(section)
    # ... similar for edges
    return "\n\n".join(sections)
```

This means adding a new scenario only requires writing the CSVs and
`graph_schema.yaml` — the prompt is built automatically.

#### 3.3 Auto-generate telemetry prompt from scenario manifest

Container schemas, property names, and value ranges are already in
`scenario.yaml` under `cosmos.nosql.containers` and `telemetry_baselines`.
Generate the telemetry agent prompt section from these.

#### 3.4 Auto-generate OpenAPI tool specs from scenario manifest

The OpenAPI YAML files (`graph-query-api/openapi/cosmosdb.yaml`) are what the
LLM *sees* as tool documentation. Currently they have hardcoded telco entity
names, example queries with telco IDs, and `enum: ["AlertStream", "LinkTelemetry"]`.

Generate these per-scenario from `scenario.yaml`:
- `/query/graph` description: list entity types from `graph_schema.yaml` vertex labels
- `/query/graph` example query: construct from first vertex type + first instance ID
- `/query/telemetry` `container_name` enum: from `cosmos.nosql.containers[].name`
- `/query/telemetry` description: list container names and doc counts

```python
def generate_openapi_spec(scenario: ScenarioLoader, backend: str) -> dict:
    """Generate the OpenAPI spec for agent tools from scenario manifest."""
    schema = yaml.safe_load(scenario.graph_schema.read_text())
    vertex_labels = [v["label"] for v in schema["vertices"]]
    containers = [c["name"] for c in scenario.cosmos_config["nosql"]["containers"]]
    first_vertex = schema["vertices"][0]
    example_id = # read first row of first CSV
    # ... build spec dict
```

This ensures the LLM knows the correct entity types, property names, and
container names for whatever scenario is active.

#### 3.5 Update `provision_agents.py`

- Load the active scenario via `ScenarioLoader`
- Compose prompts using shared templates + scenario fragments
- Replace hardcoded `PROMPTS_DIR` with scenario-aware path resolution
- Generate scenario-specific OpenAPI specs and pass to agent creation

#### 3.6 Multi-Scenario Agent Strategy

When multiple scenarios are loaded, agents need scenario context. Three options:

| Strategy | Latency | Complexity | Demo UX |
|----------|---------|------------|---------|
| **A. Pre-provision per scenario** | Instant switch | High — N×5 agents, naming convention needed | Best — seamless |
| **B. Re-provision on switch** | ~30s per switch | Low — reuse existing provisioning | Acceptable — loading spinner |
| **C. Single generic agent set + runtime context** | Instant | Medium — prompts must be scenario-parameterised at call time | Good — if prompts work |

**Recommended: Option B** (re-provision on switch) for v7. It reuses the
existing provisioning logic, avoids agent naming complexity, and 30s is
acceptable for a demo scenario switch. The `/api/scenario/switch` endpoint
triggers re-provisioning in the background and returns when ready.

If demo polish requires instant switching later, upgrade to Option A by
pre-provisioning agent sets for all `LOADED_SCENARIOS` during deployment
(naming: `telco-noc-orchestrator`, `cloud-outage-orchestrator`, etc.) and
storing the agent ID map per scenario in `agent_ids.json`.

**Tasks:**
- [ ] Create `data/shared_prompts/` with domain-agnostic prompt templates
- [ ] Build prompt composition logic in `provision_agents.py` or a new `prompt_builder.py`
- [ ] Create schema prompt auto-generator from `graph_schema.yaml` + CSVs
- [ ] Create telemetry prompt auto-generator from `scenario.yaml`
- [ ] Create OpenAPI spec generator from scenario manifest (entity types, container names)
- [ ] Extract domain-agnostic sections from current orchestrator prompt
- [ ] Update `provision_agents.py` to use composed prompts + generated OpenAPI specs
- [ ] Implement scenario-switch agent re-provisioning (Option B)
- [ ] Test agent provisioning + full investigation with generated prompts
- [ ] Test scenario switch — verify prompts regenerate correctly

---

### Phase 4: Decouple Graph-Query-API + Frontend

**Goal:** The graph-query-api and frontend adapt to any scenario's entity types
without code changes.

#### 4.1 Dynamic telemetry containers (`router_telemetry.py`)

Replace `VALID_CONTAINERS = {"AlertStream", "LinkTelemetry"}` with scenario-aware
routing. The graph-query-api needs to know which Cosmos database and containers
to query based on the active scenario:

```python
# graph-query-api receives the active scenario name from the frontend
# (via header, query param, or session) and resolves the correct database.
#
# Cosmos NoSQL databases are scenario-prefixed:
#   telco-noc-telemetrydb / cloud-outage-telemetrydb
#
# Container names remain the same within each database (AlertStream, LinkTelemetry)
# since the database itself provides namespace isolation.

def get_telemetry_db(scenario_name: str) -> str:
    return f"{scenario_name}-telemetrydb"

def get_valid_containers(scenario_name: str) -> set[str]:
    """Load valid container names from the scenario manifest."""
    loader = ScenarioLoader(scenario_name)
    return {c["name"] for c in loader.cosmos_config["nosql"]["containers"]}
```

Similarly, the Gremlin backend routes to the correct graph:
- `telco-noc` → graph `telco-noc-topology` in database `networkgraph`
- `cloud-outage` → graph `cloud-outage-topology` in database `networkgraph`

#### 4.2 Dynamic mock backend

The mock backend has 200+ lines of hardcoded topology data. Options:
1. **Read from CSVs at startup** — `backends/mock.py` loads from the active
   scenario's `entities/` directory and builds `_TOPOLOGY_NODES` / `_TOPOLOGY_EDGES`
   dynamically.
2. **Generate mock data file** — the scenario's generator scripts produce a
   `mock_topology.json` file; mock backend loads it.

Option 1 is cleaner — the mock backend becomes truly data-agnostic.

#### 4.3 Frontend scenario API

Add a `/api/scenario` endpoint that returns:
```json
{
  "name": "telco-noc",
  "display_name": "Australian Telco NOC — Fibre Cut Incident",
  "default_alert": "14:31:14.259 CRITICAL VPN-ACME-CORP ...",
  "graph_styles": { ... },
  "domain": "telecommunications"
}
```

The frontend reads this at startup and:
- Sets `DEFAULT_ALERT` from the server instead of hardcoding it
- Reads `graph_styles` to configure node colours/sizes in `graphConstants.ts`
- Shows the scenario name in the UI header

#### 4.4 Graph Visualizer Genericity

The V6 graph topology viewer is **mostly generic already** — good news.
Here's the audit:

| Component | Status | Notes |
|-----------|--------|-------|
| `GraphCanvas.tsx` | ✅ Generic | Uses `node.label` to look up colour/size from dictionaries. Falls back to grey + size 6 for unknown types. Renders any `properties` dict |  
| `GraphTooltip.tsx` | ✅ Generic | Iterates `node.properties` and `edge.properties` dynamically. Shows `node.label` as type badge. No hardcoded entity names |
| `GraphToolbar.tsx` | ⚠️ Mostly generic | Filter chips are dynamically built from `availableLabels` (from API). But panel title is hardcoded `"◆ Network Topology"` — should come from scenario |
| `useTopology.ts` | ✅ Generic | TypeScript interfaces are label-agnostic: `label: string`, `properties: Record<string, unknown>`. No entity type assumptions |
| `graphConstants.ts` | ❌ Hardcoded | `NODE_COLORS` and `NODE_SIZES` are keyed to 8 telco types. **Must be replaced with server-driven config** from `/api/scenario` → `graph_styles` |

**Required changes for arbitrary datasets:**

1. **Replace `graphConstants.ts` imports with scenario-driven state.** On scenario
   load, the frontend fetches `graph_styles` from `/api/scenario` and builds
   `nodeColors` and `nodeSizes` maps. `GraphCanvas`, `GraphToolbar`, and
   `GraphTooltip` read from React context or a store instead of importing
   `graphConstants.ts` directly.

2. **Generate sensible defaults for unknown labels.** If a scenario's
   `graph_styles` doesn't cover all labels returned by the API, auto-assign
   colours from a palette (e.g. d3-categorical) and default sizes by node
   degree.

3. **Panel title from scenario.** Replace `"◆ Network Topology"` with
   `"◆ {scenario.display_name} Topology"` or just `"◆ Graph Topology"`.

#### 4.5 App Branding

**Replace hardcoded app identity with scenario-driven branding:**

- `Header.tsx`: Title becomes a generic name (e.g. `"AI Incident Investigator"`)
  with the scenario's `display_name` shown as a subtitle or in the scenario
  dropdown. Alternatively, keep a fixed platform name and show scenario context.
- `GraphToolbar.tsx`: Panel title becomes `"◆ Topology"` (domain-agnostic) or
  reads from scenario config.
- `index.html` `<title>`: Set dynamically via `document.title` on scenario load
  (e.g. `"AI Investigator — Australian Telco NOC"`).

#### 4.6 Scenario selector in frontend (core feature)

Add a dropdown (top bar or sidebar) that lists all loaded scenarios:
```
GET /api/scenarios → [
  { "name": "telco-noc", "display_name": "Australian Telco NOC", "domain": "telecommunications" },
  { "name": "cloud-outage", "display_name": "Cloud DC Outage", "domain": "cloud" }
]
```

Selecting a scenario:
1. Calls `POST /api/scenario/switch` with the chosen scenario name
2. Backend triggers agent re-provisioning (~30s) with scenario-specific prompts
3. Backend updates its active scenario context (Cosmos routing, search indexes)
4. Frontend shows a brief loading state, then refreshes:
   - Node styles update to the new scenario's `graph_styles`
   - Default alert updates to the new scenario's `default_alert.md`
   - Graph topology reloads from the new scenario's Cosmos graph
   - UI header shows the new scenario's `display_name`
5. Investigation state resets — new scenario, clean slate

The default scenario on page load is `DEFAULT_SCENARIO` from the server config.

**Tasks:**
- [ ] Make `VALID_CONTAINERS` dynamic in `router_telemetry.py`
- [ ] Refactor `backends/mock.py` to load from CSVs dynamically
- [ ] Add `/api/scenario`, `/api/scenarios`, and `/api/scenario/switch` endpoints
- [ ] Implement scenario-aware Cosmos DB routing in graph-query-api
- [ ] Update frontend to fetch scenario config at startup
- [ ] Replace hardcoded `DEFAULT_ALERT` with server-fetched value
- [ ] Replace `graphConstants.ts` with scenario-driven node styling (from `/api/scenario` → `graph_styles`)
- [ ] Add auto-assign colour palette fallback for unlisted node types
- [ ] Make `graphConstants.ts` read node styles from scenario config
- [ ] Replace hardcoded app title in `Header.tsx` with generic platform name + scenario context
- [ ] Replace hardcoded toolbar title in `GraphToolbar.tsx` with scenario-driven title
- [ ] Set `document.title` dynamically on scenario load
- [ ] Add scenario selector UI (dropdown or sidebar)

---

### Phase 5: Data Generator Framework

**Goal:** New scenarios can be created by copying the template and editing
configuration — no Python code knowledge needed for simple scenarios.

#### 5.1 Generator contract

Each scenario's `generator/` directory contains Python scripts that:
1. Read configuration from the scenario's `scenario.yaml` (or use their own
   config files)
2. Write output to `../data/` (the scenario's data directory)
3. Follow a standard interface:

```python
# Every generator script must expose a main() function
def main(output_dir: Path, config: dict) -> None:
    """Generate data files into output_dir."""
    ...
```

#### 5.2 Universal generator runner

Create `scripts/generate_scenario_data.py`:

```bash
# Generate all data for a scenario
uv run python scripts/generate_scenario_data.py --scenario telco-noc

# Generate only topology
uv run python scripts/generate_scenario_data.py --scenario telco-noc --only topology
```

This script:
1. Loads `scenario.yaml`
2. Discovers generator scripts in `generator/`
3. Runs them in order (topology → routing → telemetry → tickets)
4. Validates output (CSVs exist, schema matches, etc.)

#### 5.3 Scenario template scaffolding

Create `data/scenario_template/` with:
- `scenario.yaml.template` — annotated template with all configurable fields
- `generator/*.py.template` — skeleton generators with inline documentation
- `data/prompts/*.md.template` — prompt templates with `{{PLACEHOLDER}}` markers
- `data/graph_schema.yaml.template` — annotated graph schema skeleton

Add a scaffolding command:

```bash
# Create a new scenario from the template
uv run python scripts/create_scenario.py --name cloud-outage --domain cloud

# Creates data/scenarios/cloud-outage/ with all template files populated
```

#### 5.4 Scenario validation

Create `scripts/validate_scenario.py` that checks:
- `scenario.yaml` exists and parses
- All paths in manifest point to existing files/directories
- CSV files match the graph schema (column names, referenced entity IDs)
- Prompt files exist for all required agents
- Telemetry CSV columns match container definitions
- No orphaned entity IDs in edges/telemetry

**Tasks:**
- [ ] Define generator contract and interface
- [ ] Create `scripts/generate_scenario_data.py` runner
- [ ] Refactor current generators to follow the contract
- [ ] Create `data/scenario_template/` with all template files
- [ ] Create `scripts/create_scenario.py` scaffolding command
- [ ] Create `scripts/validate_scenario.py` validation tool
- [ ] Document the scenario creation workflow

---

### Phase 6: Multi-Scenario Integration Testing & Second Scenario

**Goal:** Validate multi-scenario coexistence end-to-end by deploying two
scenarios simultaneously and testing the full switch flow.

The namespace isolation strategy is built into Phases 2–4. This phase creates
the second scenario and validates everything works together.

#### 6.1 Data isolation (implemented in Phases 2–4, validated here)

| Service | Isolation approach | Implemented in |
|---------|-------------------|----------------|
| Cosmos Gremlin | Scenario-prefixed graph: `telco-noc-topology` / `cloud-outage-topology` | Phase 2.3 |
| Cosmos NoSQL | Scenario-prefixed database: `telco-noc-telemetry` / `cloud-outage-telemetry` | Phase 2.3 |
| AI Search | Scenario-prefixed indexes: `telco-noc-runbooks-index` / `cloud-outage-runbooks-index` | Phase 2.7 |
| Blob Storage | Scenario-prefixed containers: `telco-noc-runbooks` / `cloud-outage-runbooks` | Phase 2.4 |
| Agent prompts | Re-provisioned on scenario switch | Phase 3.5 |

#### 6.2 Create second scenario (cloud-outage)

Using the Phase 5 generator framework + scenario template, create
`data/scenarios/cloud-outage/` as the validation scenario (see "Second Scenario
Candidate" section below for details).

#### 6.3 End-to-end integration test

1. Deploy with `--scenarios telco-noc,cloud-outage`
2. Verify both scenarios' data exists in Cosmos/Search/Blob
3. Start the app — default scenario loads correctly
4. Switch to second scenario via UI dropdown
5. Verify graph topology updates, agents respond with correct domain context
6. Run a full investigation in each scenario
7. Switch back and forth — no data leakage across scenarios

#### 6.4 Performance & UX polish

- Measure scenario switch latency (agent re-provisioning time)
- Add loading indicator during switch
- If re-provisioning is too slow for demo UX, upgrade to pre-provisioned
  agent sets (Option A from Phase 3.5)

**Tasks:**
- [ ] Build the `cloud-outage` scenario using the generator framework
- [ ] Deploy with `--scenarios telco-noc,cloud-outage`
- [ ] Verify data isolation — no cross-scenario data leakage
- [ ] Test scenario switch via UI dropdown end-to-end
- [ ] Run full investigation in both scenarios
- [ ] Measure and optimise switch latency

---

## Migration Path (Zero Downtime)

1. **Phase 1** — Restructure + symlinks. `deploy_app.sh` still works because
   symlinks point to new locations. No behaviour change.
2. **Phase 2** — Blob-first ingestion. Data flows Blob → Container App → Cosmos,
   bypassing firewall issues. `DEFAULT_SCENARIO` defaults to `telco-noc`,
   `LOADED_SCENARIOS` defaults to `telco-noc`, so existing deployments work
   unchanged. All resource names are now scenario-prefixed
   (e.g. `telco-noc-topology`, `telco-noc-telemetry`) — this is a naming change
   from the current un-prefixed names, so a fresh deployment of data stores is
   needed. The Container App auto-ingests from blob on startup if Cosmos is empty.
3. **Phase 3** — Prompt decomposition. Current prompts are split but produce
   identical output when reassembled. Test with diff.
4. **Phase 4** — Frontend/API updates. New endpoints are additive; existing ones
   unchanged. Scenario selector dropdown added.
5. **Phase 5** — Generator framework is new tooling, doesn't affect existing flow.
6. **Phase 6** — Integration test with two scenarios loaded simultaneously.
   Validates that all earlier phases support multi-scenario correctly.

At every phase, the existing `telco-noc` scenario must produce **identical**
agent behaviour and investigation output. Regression test: run the default
alert storm and diff the situation report structure.

---

## Effort Estimates

| Phase | Effort | Risk |
|-------|--------|------|
| Phase 1: Restructure + ScenarioLoader | 3-4 hours | Low — file moves + symlinks |
| Phase 2: Blob-first ingestion + endpoints | 6-8 hours | Medium — refactor scripts into importable modules, add ingestion endpoint, blob-first pipeline |
| Phase 3: Prompt decomposition + switch strategy | 5-7 hours | Medium — prompt quality must not degrade; agent re-provisioning logic |
| Phase 4: API + frontend (scenario routing + selector) | 4-5 hours | Medium — Cosmos routing + scenario switch UX |
| Phase 5: Generator framework | 4-6 hours | Low — new tooling |
| Phase 6: Integration test + second scenario | 4-6 hours | Medium — end-to-end validation |
| **Total** | **26-37 hours** | |

---

## Second Scenario Candidate: Cloud Datacenter Outage

To validate the framework, create a second scenario with a different domain:

**Domain:** Cloud infrastructure (AWS/Azure-style)  
**Topology:** Regions → Availability Zones → Racks → Hosts → VMs → Services  
**Incident:** Cooling failure in AZ causes host cascade shutdown  
**Entity types:** Region, AvailabilityZone, Rack, Host, VirtualMachine, LoadBalancer, Service, SLA  
**Telemetry:** TemperatureCelsius, CPUUtilPct, MemoryUtilPct, DiskIOPS, NetworkThroughputMbps  
**Alert types:** COOLING_FAILURE, THERMAL_SHUTDOWN, VM_UNREACHABLE, SERVICE_DEGRADATION, FAILOVER_TRIGGERED

This scenario validates that:
- The graph schema manifest supports completely different entity types
- Prompts are correctly generated from schema + baselines
- The UI adapts its node colours/icons to non-telco entity types
- Alert investigation flow works without telco-specific assumptions

---

## Key Design Decisions

### Q: Should generators write CSVs or JSON?
**A: CSV.** The existing graph schema ingestion (`provision_cosmos_gremlin.py`)
reads CSVs. The telemetry ingestion reads CSVs. AI Search processes documents
individually. CSV keeps the pipeline consistent and human-readable.

### Q: How should data be ingested into Cosmos DB?
**A: Blob → Container App → Cosmos (not direct from dev machine).**
Scenario CSVs are generated locally (or in CI), uploaded to Blob Storage via
`postprovision.sh` (RBAC auth, highly reliable), then ingested into Cosmos by
the Container App which is inside the VNet with private endpoint access. This
eliminates firewall/public-network issues that plague the current direct
ingestion from dev machines.

The flow:
```
Generate CSVs → Upload to Blob Storage → Container App reads blob → Writes to Cosmos
  (local/CI)     (postprovision.sh)        (inside VNet, private endpoints)
```

The Container App exposes `POST /api/scenario/{name}/ingest` which:
1. Downloads CSVs from scenario-prefixed blob containers
2. Ingests graph data into Cosmos Gremlin (via `gremlinpython`)
3. Ingests telemetry data into Cosmos NoSQL (via `azure-cosmos`)
4. Reports progress via a polling endpoint

Optionally, the app self-initialises on startup: if the default scenario's
graph is empty, it auto-ingests from blob — making fresh deployments fully
zero-touch after `azd up`.

The telemetry script already supports `--from-blob` (`_load_csv_blob()`). The
Gremlin script needs the same treatment (Phase 2.2).

### Q: Should prompts be fully auto-generated or hand-authored?
**A: Hybrid.** The graph schema prompt (227 lines) should be auto-generated —
it's mechanical and error-prone to maintain by hand. The orchestrator's
investigation methodology is hand-authored (domain expertise matters). The
scenario manifest provides the bridge — structured data that feeds both
auto-generation and hand-authored sections.

### Q: One Cosmos DB database per scenario or shared database?
**A: Scenario-prefixed naming from the start.** Gremlin uses a shared database
(`networkgraph`) with scenario-prefixed graph names (`telco-noc-topology`,
`cloud-outage-topology`). NoSQL uses scenario-prefixed databases
(`telco-noc-telemetry`, `cloud-outage-telemetry`). This avoids any
Phase 6 retrofit and ensures multi-scenario data isolation is built-in.

### Q: How does the frontend know which entity types to style?
**A: From `scenario.yaml` → `/api/scenario` endpoint.** The `graph_styles` block
in the manifest defines colours and sizes per entity type. The frontend reads
this at startup instead of hardcoding in `graphConstants.ts`.

### Q: What about the `alert_storm.md` default input?
**A: Each scenario provides its own `default_alert.md`.** The frontend fetches
this via `/api/scenario` and uses it as the `DEFAULT_ALERT` placeholder.
Users can still type custom alerts.

### Q: How do agents handle scenario switching?
**A: Re-provision on switch (Option B).** When the user selects a different
scenario from the dropdown, the backend re-provisions the 5 Foundry agents with
prompts composed from the new scenario's fragments. This takes ~30 seconds —
acceptable for a demo where scenario switching is infrequent. The frontend shows
a loading state during the switch. If instant switching becomes necessary,
upgrade to pre-provisioned agent sets (Option A) — provision 5 agents per loaded
scenario during deployment, store separate `agent_ids.json` entries per scenario.

### Q: What should the app be called?
**A: Use a generic platform name.** The app title should be domain-agnostic
since it now hosts multiple scenarios. Options:
- **"AI Incident Investigator"** — descriptive, scenario-neutral
- **"Autonomous Operations Centre"** — broader than "Network NOC"
- Keep a fixed platform name in the header; show the active scenario's
  `display_name` in the scenario dropdown or as a subtitle.
The `<title>` tag updates dynamically: `"AI Investigator — Australian Telco NOC"`.

### Q: Will the graph visualizer work with arbitrary entity types?
**A: Yes, with minor changes.** The V6 graph viewer is already nearly generic —
`GraphCanvas`, `GraphTooltip`, and `useTopology` use dynamic `label` + `properties`
with no hardcoded entity names. The two blockers are:
1. `graphConstants.ts` has hardcoded colour/size maps for 8 telco types →
   **replace with server-driven config** from `scenario.yaml` → `/api/scenario`.
2. Unknown labels fall back to grey (functional but ugly) → **add a categorical
   colour palette** (e.g. d3-scheme-category10) as auto-fallback.
The force-directed layout (react-force-graph-2d) is topology-agnostic — it works
on any graph structure without entity-specific tuning.

---

## Implementation Audit — Gotchas, Risks & Missing Details

> _This section was produced by cross-referencing every claim in the plan
> against the actual codebase. Issues are ranked **Critical** (will break the
> build/deploy), **High** (will cause bugs in production), **Medium** (will
> create friction or tech debt), or **Low** (cosmetic or minor)._

---

### CRITICAL Issues

#### C1. Cosmos Gremlin graphs cannot be created via the data plane

The plan says "deploy script prefixes: `telco-noc-topology`" and shows the
ingestion script writing data to scenario-prefixed graphs. But **Cosmos DB
Gremlin containers (graphs) can only be created through the management plane**
(Bicep, ARM, Azure CLI, or `azure-mgmt-cosmosdb` SDK) — the `gremlinpython`
library only supports data operations.

Currently, Bicep creates exactly one graph resource:

```bicep
// infra/modules/cosmos-gremlin.bicep
resource graph ... {
  name: graphName  // param default: 'topology'
}
```

**Impact:** The plan does not address how additional scenario-prefixed graphs
are created. Without this, multi-scenario graph data cannot be deployed.

**Fix (resolved in Phase 2.3):** The revised Phase 2 uses Azure CLI calls in
`postprovision.sh` to create scenario-prefixed graphs and NoSQL databases
dynamically:
```bash
az cosmosdb gremlin graph create --name telco-noc-topology ...
az cosmosdb sql database create --name telco-noc-telemetry ...
```
This runs after Bicep creates the base accounts and before blob data is
uploaded. The Container App's managed identity (or the deployer's CLI
credentials) has sufficient permissions for control-plane resource creation.

#### C2. `graph_schema.yaml` `data_dir` path will break after relocation

Currently:
```yaml
# data/graph_schema.yaml
data_dir: data/network       # resolved as PROJECT_ROOT / "data/network"
```

`provision_cosmos_gremlin.py` resolves this as `PROJECT_ROOT / schema["data_dir"]`
(line 296). After the Phase 1
relocation, the file moves to `data/scenarios/telco-noc/data/graph_schema.yaml`
and the CSVs move to `data/scenarios/telco-noc/data/entities/`. But the `data_dir`
would need to become `data/scenarios/telco-noc/data/entities` (project-root-relative)
— an ugly, brittle path.

**Fix:** Update `provision_cosmos_gremlin.py` to resolve `data_dir` **relative
to the schema file**, not to `PROJECT_ROOT`:
```python
schema_dir = schema_path.parent
data_dir = schema_dir / schema["data_dir"]  # e.g. schema_dir / "entities"
```
Then each scenario's `graph_schema.yaml` uses `data_dir: entities` (a clean
relative path). Add this to the Phase 2.1 tasks and ensure backwards
compatibility with the old absolute-style path during the symlink transition.

#### C3. Docker container lacks scenario data for runtime resolution

The Dockerfile copies `api/`, `graph-query-api/`, `frontend/dist`, and
`scripts/agent_ids.json`. It does **not** copy `data/` or `scripts/scenario_loader.py`.

Phase 4.1 shows the `graph-query-api` calling `ScenarioLoader(scenario_name)`
at runtime to discover valid containers and database names. This will fail
inside the Docker container because neither the `ScenarioLoader` module nor
`scenario.yaml` files are present.

**Fix:** Choose one approach:
1. **Bake scenario manifests into the image** — add to Dockerfile:
   ```dockerfile
   COPY data/scenarios/*/scenario.yaml /app/data/scenarios/
   COPY scripts/scenario_loader.py /app/scripts/
   ```
2. **Serve scenario config via the main API** — the main API (port 8000) loads
   scenario manifests and exposes an internal endpoint
   (`/internal/scenario-config?name=telco-noc`) that `graph-query-api` calls.
   This avoids shared filesystem dependencies but adds an inter-service call.
3. **Pass all scenario config as env vars** — flatten the scenario config into
   env vars at deploy time. This limits flexibility but avoids filesystem issues.

**Recommendation:** Option 1 for simplicity. Add a Dockerfile task to
Phase 1 or Phase 4. Note that the Blob-first ingestion architecture (Phase 2)
reduces this concern — the scenario manifests are also uploaded to blob storage,
so the Container App can download `scenario.yaml` from blob at runtime as an
alternative to baking it into the image.

#### C4. Bicep passes hardcoded Cosmos env vars to Container App

main.bicep lines 172–176:
```bicep
{ name: 'COSMOS_GREMLIN_DATABASE', value: 'networkgraph' }
{ name: 'COSMOS_GREMLIN_GRAPH', value: 'topology' }
```

These are **literal strings**, not from the Bicep `databaseName`/`graphName`
parameters. With scenario-prefixed naming:

- The Container App env vars would still say `topology`, but the actual graphs
  are named `telco-noc-topology`, `cloud-outage-topology`.
- The `graph-query-api` `config.py` reads these at import time as the
  **default** graph — so all requests would go to the non-existent `topology`
  graph.

**Fix:** Either:
1. Update Bicep to reference outputs: `value: cosmosGremlin.outputs.gremlinGraphName`
   (but this only gives one graph name — doesn't help multi-scenario).
2. **Set `COSMOS_GREMLIN_GRAPH` to the default scenario's graph name** and have
   the graph-query-api override it dynamically per-request based on the
   scenario header. The env var becomes a fallback, not the sole source of truth.
3. Pass `DEFAULT_SCENARIO` as an env var and have the app derive graph names
   from it.

This must be addressed in Phase 4 when implementing scenario-aware routing.

---

### HIGH-Priority Issues

#### H1. `graph-query-api` config is singleton — cannot route to multiple graphs

`config.py` reads env vars at **module import time**:
```python
COSMOS_GREMLIN_GRAPH = os.getenv("COSMOS_GREMLIN_GRAPH", "topology")
```

`backends/cosmosdb.py` creates a single Gremlin WSS connection hard-wired to
`/dbs/{DATABASE}/colls/{GRAPH}` (cosmosdb.py lines 51–60).
The singleton `_backend` in `router_graph.py` is initialised once.

For multi-scenario, the graph-query-api needs to either:
- Maintain a **pool of Gremlin clients** (one per scenario graph)
- **Re-create the client** on scenario switch (expensive, ~2s reconnect)
- Use a **single database with all data but partition-key-isolated** (against
  the plan's design)

**Fix:** Add to Phase 4.1:
1. Refactor `CosmosDBGremlinBackend` to accept `graph_name` as a constructor
   parameter instead of reading from module-level config.
2. Create a backend factory that caches backends per scenario name:
   ```python
   _backends: dict[str, CosmosDBGremlinBackend] = {}
   def get_backend_for_scenario(scenario: str) -> CosmosDBGremlinBackend:
       if scenario not in _backends:
           _backends[scenario] = CosmosDBGremlinBackend(graph=f"{scenario}-topology")
       return _backends[scenario]
   ```
3. The router reads the active scenario from a request header
   (`X-Scenario: telco-noc`) or a session/FastAPI dependency.

Similarly for telemetry: `router_telemetry.py` creates a Cosmos NoSQL client
with a single database reference. The same factory pattern is needed.

#### H2. `ScenarioLoader` cannot be imported by `graph-query-api`

`ScenarioLoader` lives at `scripts/scenario_loader.py`. But `scripts/` has no
`__init__.py` and is not a Python package. More importantly, `graph-query-api`
is a **separate service** with its own `pyproject.toml` and `uv.lock` — it
cannot import from `scripts/` without `sys.path` hacks.

**Fix:** Choose one:
1. **Make `scenario_loader` a proper package** — move it to a shared location
   (e.g., `lib/scenario_loader/`) with its own `pyproject.toml` and add it as
   a path dependency in both `api/pyproject.toml` and
   `graph-query-api/pyproject.toml`.
2. **Duplicate a lightweight config reader** in `graph-query-api` — a 20-line
   YAML reader that only needs `scenario.yaml`, not the full `ScenarioLoader`.
3. **Serve scenario config via API** (see C3 option 2) — avoid the import issue
   entirely.

#### H3. Agent re-provisioning (Option B) lacks error handling and concurrency safety

The plan says "the `/api/scenario/switch` endpoint triggers re-provisioning in
the background and returns when ready." But:

- `provision_agents.py` is a **CLI script** (500 lines with `argparse`). It's
  not designed to be called as a library function from a running FastAPI server.
- During re-provisioning (~30s), the old agent IDs in `agent_ids.json` are
  stale. If a user sends an alert during this window, `orchestrator.py` will
  use the old agent IDs, which may have been deleted or point to the wrong
  scenario's prompts.
- Writing `agent_ids.json` from the web server process while `orchestrator.py`
  reads it concurrently is a **race condition** (file could be partially
  written).

**Fix:** Add to Phase 3.8:
1. Extract provisioning logic from `provision_agents.py` into an importable
   module (e.g., `scripts/agent_provisioner.py` with a `provision(config)` function).
2. Use an **in-memory agent registry** instead of `agent_ids.json` for runtime
   switching. The file is still written for persistence/restart recovery, but
   the running server reads from memory.
3. Add a mutex/lock around the switch operation. While switching:
   - Block new investigation requests (return 503 with "Switching scenario")
   - Complete the re-provisioning
   - Atomically update the in-memory registry
   - Unblock requests

#### H4. NoSQL database name mismatch between Python defaults and Bicep

| Source | Database name |
|--------|---------------|
| Python default (`provision_cosmos_telemetry.py` L50) | `"telemetrydb"` |
| Python default (`graph-query-api/config.py` L36) | `"telemetrydb"` |
| Bicep hardcoded var (`cosmos-gremlin.bicep` L107) | `"telemetry"` |
| Runtime (from `postprovision.sh` → `azure_config.env`) | `"telemetry"` (from Bicep output) |

If anyone runs the Python scripts **without sourcing `azure_config.env`**, they
default to `"telemetrydb"` while the actual database is `"telemetry"`. This
silent mismatch could cause data to be ingested into the wrong database or
queries to fail with unhelpful errors.

The plan compounds this by proposing `telco-noc-telemetrydb` as the
scenario-prefixed name — following the Python default pattern rather than the
Bicep pattern.

**Fix:**
1. Align the defaults: change Python defaults to `"telemetry"` to match Bicep.
2. Document the canonical name as `telemetry` and use
   `telco-noc-telemetry` (not `telco-noc-telemetrydb`) for scenario-prefixed names.
3. Better yet: make the Bicep `telemetryDbName` a parameter (not a var) so it
   flows through `postprovision.sh` → env vars → Python consistently.

#### H5. Cosmos Gremlin partition key convention is non-obvious

The current graph uses a **static partition key** per vertex type: every
`CoreRouter` vertex has `partitionKey: "router"`, every `AggSwitch` has
`partitionKey: "switch"`, etc. This convention is embedded in:
- [graph_schema.yaml](data/graph_schema.yaml) (`partition_key: router`)
- [cosmos-gremlin.bicep](infra/modules/cosmos-gremlin.bicep) (`partitionKeyPath: '/partitionKey'`)
- [provision_cosmos_gremlin.py](scripts/cosmos/provision_cosmos_gremlin.py) (builds `.property('partitionKey', pk_val)`)

**The partition key path (`/partitionKey`) is immutable after graph creation.**
If a new scenario uses the same shared database `networkgraph` but a different
graph (e.g. `cloud-outage-topology`), that new graph must also use
`/partitionKey` as its partition key path — the Bicep or CLI command that
creates it must specify this.

This isn't a bug per se, but it's an **undocumented contract** that a scenario
author could easily violate. The scenario manifest (`scenario.yaml`) doesn't
include a `partition_key_path` field, so there's no enforcement.

**Fix:** Add to the Convention Contract:
- "All Gremlin graphs use `/partitionKey` as the partition key path."
- Add validation to `validate_scenario.py` (Phase 5.4) to check this.

---

### MEDIUM-Priority Issues

#### M1. `graph_schema.yaml` does not move cleanly under the scenario `data/` dir

The plan puts `graph_schema.yaml` inside the scenario's `data/` directory
alongside `entities/`, `telemetry/`, etc. But the plan also says generators
write output to `../data/` — which means `generate_topology.py` (in
`generator/`) writes to `data/entities/`. This is fine structurally, but:

- The `data/` directory is proposed as **gitignored** (the plan says "Generated
  output (gitignored)"). But `graph_schema.yaml` is hand-authored and must
  be committed. It shouldn't live inside a gitignored directory.

**Fix:** Move `graph_schema.yaml` up one level to the scenario root:
```
data/scenarios/telco-noc/
├── scenario.yaml
├── graph_schema.yaml        ← here, not inside data/
├── generator/
└── data/                    ← gitignored generated output
```
Or only gitignore `data/entities/` and `data/telemetry/` (the generated CSVs)
rather than the entire `data/` directory.

#### M2. Prompt file relocation breaks `provision_agents.py` during symlink transition

`provision_agents.py` loads prompts via hardcoded filenames (line 44):
```python
PROMPTS_DIR = PROJECT_ROOT / "data" / "prompts"
load_prompt("foundry_orchestrator_agent.md")
load_prompt("foundry_telemetry_agent_v2.md")
```

The plan renames these files during Phase 1:
- `foundry_orchestrator_agent.md` → `orchestrator.md`
- `foundry_telemetry_agent_v2.md` → `telemetry_agent.md`

Symlinks would need to be created at the **filename level** (not just the
directory level) for backwards compatibility:
```
data/prompts/foundry_orchestrator_agent.md → data/scenarios/telco-noc/data/prompts/orchestrator.md
```

The plan mentions directory-level symlinks but doesn't specify file-level
symlinks for renamed files.

**Fix:** Either:
1. Keep original filenames during Phase 1 and only rename in Phase 3 when
   `provision_agents.py` is updated.
2. Create explicit file-level symlinks for each renamed file.
Option 1 is cleaner — avoids a confusing symlink web.

#### M3. Search index + blob container scenario-prefixing creates N resources per scenario

Each scenario creates:
- 2 AI Search indexes (`{scenario}-runbooks-index`, `{scenario}-tickets-index`)
- 4+ blob containers (`{scenario}-runbooks`, `{scenario}-tickets`,
  `{scenario}-telemetry-data`, `{scenario}-network-data`)

Azure AI Search has a limit of **15 indexes** per service on the Basic tier
(50 on Standard S1). With 2 indexes per scenario, you're limited to 7 scenarios
on Basic or 25 on Standard S1.

Blob containers have a soft limit of 500 per storage account (not a concern).

**Fix:** Document the AI Search tier constraint and consider whether the search
service SKU needs upgrading for scale. Add to deployment prerequisites.

#### M4. `preprovision.sh` does not sync new env vars

`preprovision.sh` syncs specific vars to `azd env`:
```bash
azd env set AZURE_LOCATION "$AZURE_LOCATION"
azd env set GPT_CAPACITY_1K_TPM "$GPT_CAPACITY_1K_TPM"
azd env set GRAPH_BACKEND "$GRAPH_BACKEND"
```

The plan adds `DEFAULT_SCENARIO` and `LOADED_SCENARIOS` to `azure_config.env`
but doesn't mention updating `preprovision.sh` to sync them. If these vars
are needed by Bicep (e.g., to create scenario-prefixed graphs), they must be
synced.

**Fix:** Add to Phase 1.4 tasks:
- Update `preprovision.sh` to sync `DEFAULT_SCENARIO` and `LOADED_SCENARIOS`.

#### M5. Bicep infrastructure needs multi-graph and multi-database loop support

For multi-scenario deployment, Bicep needs to create:
- Multiple Gremlin graphs in the shared `networkgraph` database
- Multiple NoSQL databases (one per scenario)
- Multiple blob containers (per scenario)

Currently, Bicep creates exactly one of each. All three modules (`cosmos-gremlin.bicep`,
`storage.bicep`) need loop constructs.

**Fix (resolved in Phase 2.3):** Dynamic Cosmos resource creation is handled
via Azure CLI in `postprovision.sh` — `az cosmosdb gremlin graph create` and
`az cosmosdb sql database create` for each scenario. Blob containers are
created implicitly by `az storage blob upload-batch` (which creates the
container if it doesn't exist). This avoids complex Bicep refactoring while
keeping Bicep responsible for the base accounts/databases.

#### M6. `provision_agents.py` uses `os.environ["RUNBOOKS_INDEX_NAME"]` with no default

Lines 111–112:
```python
"runbooks_index": os.environ["RUNBOOKS_INDEX_NAME"],
"tickets_index": os.environ["TICKETS_INDEX_NAME"],
```

These will `KeyError` if not set. When scenario-prefixing index names, the env
var values must be updated per-scenario. If `provision_agents.py` is called
during a scenario switch (Phase 3.8), these env vars must be set
programmatically — but `os.environ` is process-wide state. Setting them in one
thread could leak to another.

**Fix:** Pass index names as function arguments (not env vars) when calling
provisioning logic from the web server. Keep env var reading only in the CLI
entry point.

#### M7. Multi-scenario NoSQL: separate databases vs shared database with separate containers

The plan uses **separate databases** per scenario (`telco-noc-telemetrydb`,
`cloud-outage-telemetrydb`). This works but is heavyweight:
- Cosmos DB has a soft limit of 25 databases per account.
- Each database has its own throughput allocation (cost).
- The `create_database_if_not_exists` call adds latency to the deploy loop.

An alternative is a **shared database with scenario-prefixed containers**
(`telco-noc-AlertStream`, `cloud-outage-AlertStream`). This keeps all
telemetry in one database, simplifies provisioning, and avoids the database
limit.

**Fix:** Evaluate the trade-off and document the decision. If the plan keeps
separate databases, add a note about the 25-database soft limit and the cost
implications.

#### M8. `models.py` default `container_name = "AlertStream"` could cause cross-scenario leaks

If the LLM omits `container_name` in a telemetry query, the default
`"AlertStream"` is used. After a scenario switch, the default might not exist
in the new scenario's database (or worse, it might be a leftover from a
different scenario if container names are reused).

**Fix:** Either:
1. Make `container_name` required (no default) in `TelemetryQueryRequest`.
2. Set the default dynamically based on the active scenario.
Option 1 is safer — forces the agent to always specify the container.

---

### LOW-Priority Issues

#### L1. `Header.tsx` hardcodes "5 Agents"

The agent count is not fetched from the API. If a scenario has a different
number of sub-agents, this would be stale.

**Fix:** Fetch from `GET /api/agents` and display `agents.length` instead.

#### L2. `GraphTooltip.tsx` imports `NODE_COLORS` directly

`GraphTooltip` uses `NODE_COLORS[node.label]` for tooltip colour dots. When
`graphConstants.ts` is replaced with scenario-driven state (Phase 4.4), this
import also needs updating — it's not listed in the plan's required changes.

**Fix:** Add to Phase 4.4 task list: "Update `GraphTooltip.tsx` to read node
colours from scenario-driven state instead of importing `NODE_COLORS`."

#### L3. `alert.py` and `agents.py` stubs have hardcoded agent names

The stub responses in `alert.py` (L46) and `agents.py` (L14-19) reference
telco-specific agent names like `"TelemetryAgent"`, `"GraphExplorerAgent"`.
These only appear in unconfigured/stub mode, but they should still match
whatever the platform calls its agents.

**Fix:** Make stub agent names match the generic platform branding. Low
priority since stubs are only for local dev without provisioned agents.

#### L4. `description.md` and `language_mock.md` not listed in the relocation table

`data/prompts/graph_explorer/description.md` and
`data/prompts/graph_explorer/language_mock.md` exist but aren't mentioned in
the Phase 1.2 file relocation mapping. `description.md` is used by
`provision_agents.py` to set the agent's `description` field. `language_mock.md`
is the mock-backend counterpart to `language_gremlin.md`.

**Fix:** Add both to the relocation table:
```
data/prompts/graph_explorer/description.md   → data/scenarios/telco-noc/data/prompts/graph_explorer/description.md
data/prompts/graph_explorer/language_mock.md → data/scenarios/telco-noc/data/prompts/graph_explorer/language_mock.md
```

> **Note:** These have been added to the Phase 1.2 relocation table.

#### L5. `ScenarioLoader.list_scenarios()` signature inconsistency

The pseudocode shows `def list_scenarios(cls, ...)` with a `cls` parameter
(classmethod style) but it's defined as a regular instance method. Minor, but
should be clarified as either `@classmethod` or `@staticmethod`.

#### L6. Phase 2.6 uses deprecated FastAPI `on_event("startup")`

`@app.on_event("startup")` is deprecated since FastAPI 0.93. The codebase's
`api/app/main.py` does not use any startup handler currently, so this is an
opportunity to use the modern `lifespan` async context manager pattern.
The code sample in Phase 2.6 has been updated to use `lifespan`.

#### L7. Phase 4.3 `default_alert` returns content, not path

The `/api/scenario` endpoint example shows `default_alert` as a string of the
actual alert text, but `scenario.yaml` defines it as a file path
(`data/prompts/default_alert.md`). The `ScenarioLoader.default_alert` property
must read the file and return its contents, not the path. This is implicit in
the pseudocode but should be made explicit in the convention contract and API
documentation.

---

### Structural Observations (Not Bugs)

#### S1. The two-service architecture adds scenario-routing complexity

The frontend calls **two independent backend services** (API on 8000,
graph-query-api on 8100) via Vite proxy / nginx. Scenario context must be
propagated to **both** services. The plan's scenario switch endpoint is on the
API (port 8000), but the graph-query-api (port 8100) also needs to know the
active scenario to route Cosmos queries.

Options:
- **Scenario header** — frontend sends `X-Scenario: telco-noc` on all requests
  to both services. Simple, stateless.
- **Shared state** — API notifies graph-query-api of scenario changes via an
  internal endpoint or shared env/file. More complex.

The plan should explicitly specify the propagation mechanism.

#### S2. Agent OpenAPI specs reference `{base_url}` — generation must preserve this

`provision_agents.py` substitutes `{base_url}` in the OpenAPI YAML with
`GRAPH_QUERY_API_URI`. When Phase 3.4 generates OpenAPI specs dynamically, this
substitution logic must be preserved. The generated spec should use
`{base_url}` as a placeholder, not a hardcoded URL.

#### S3. ~~The `--from-blob` telemetry ingestion mode needs scenario-aware blob paths~~

**Resolved by Phase 2 redesign.** The Blob-first ingestion architecture makes
`--from-blob` the *primary* ingestion path, not an alternative. All ingestion
functions accept `blob_container` as a parameter (scenario-prefixed, e.g.
`telco-noc-telemetry-data`), so scenario-aware blob paths are built-in.

---

### Recommended Phase Ordering Adjustments

1. **Do NOT rename prompt files in Phase 1.** Keep original filenames and only
   rename them in Phase 3 when `provision_agents.py` is updated. This avoids
   the file-level symlink complexity described in M2.

2. **Phase 2 now creates Cosmos resources via Azure CLI** in `postprovision.sh`
   (Phase 2.3), so Bicep doesn't need multi-graph loop support. This is
   simpler and more flexible for dynamic scenario lists.

3. **Address Docker/container changes early** (C3). The Dockerfile update should
   be part of Phase 1, not deferred to Phase 4. The Blob-first ingestion
   architecture (Phase 2) reduces this concern — scenario manifests can be
   downloaded from blob at runtime instead of baked into the image.

4. **Consider Phase 3 Option A** (pre-provisioned agents) more seriously. The
   30s re-provisioning window in Option B introduces race conditions (H3) and
   a poor demo UX. Pre-provisioning 5 agents × 2 scenarios = 10 total agents
   is not expensive and eliminates an entire class of runtime issues. The
   naming convention is straightforward (`{scenario}-{agent_name}`) and
   `agent_ids.json` already supports nested structure.
