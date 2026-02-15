# V8: Data Management Plane — Browser-Based Scenario Upload

## Summary

V8 moves Cosmos DB data loading from the deployment script (`deploy.sh`) into
the running application itself. Users upload scenario data as `.tar.gz` archives
via the UI Settings page. The Container App — which is inside the VNet with
private endpoint access to Cosmos DB — ingests the data directly. This
eliminates the firewall/public-network-access problems that plagued the
previous direct-from-dev-machine ingestion path.

## What Changed

### Before (V7 and earlier)

```
Developer machine                              Azure
┌──────────────────┐                     ┌─────────────┐
│ deploy.sh        │ ──WSS/HTTPS──────▶  │ Cosmos DB   │
│ • Detect dev IP  │    (public net)     │ (Gremlin +  │
│ • Open firewall  │    ⚠ fragile       │  NoSQL)     │
│ • Load vertices  │                     │             │
│ • Load edges     │                     │             │
│ • Load telemetry │                     └─────────────┘
└──────────────────┘
Problems:
• IP changes break access
• VPN blocks WSS on 443
• Azure Policy toggles publicNetworkAccess off
• Corporate proxies interfere
• ~100 lines of firewall dance code in deploy.sh
```

### After (V8)

```
Browser                   Container App (VNet)         Azure
┌──────────┐        ┌──────────────────────┐    ┌─────────────┐
│ Settings │ ──▶    │ POST /query/scenario │ ─▶ │ Cosmos DB   │
│ ⚙ Upload │ tar.gz │      /upload         │    │ (Gremlin +  │
│          │        │                      │    │  NoSQL)     │
│ Progress │ ◀─SSE─ │ • Extract archive    │    │             │
│ bar      │        │ • Create graph (ARM) │    │ Private     │
│          │        │ • Load vertices      │    │ endpoints   │
└──────────┘        │ • Load edges         │    └─────────────┘
                    │ • Load telemetry     │
                    └──────────────────────┘
Benefits:
✓ No firewall configuration needed
✓ No public network access required
✓ Uses private endpoints (VNet → Cosmos)
✓ Self-service — upload from the browser
✓ Works from any network (only needs HTTPS to the app)
✓ SSE progress streaming for real-time feedback
```

## Architecture

### New Endpoints (graph-query-api, port 8100)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/query/scenario/upload` | POST | Upload a `.tar.gz` scenario archive; returns SSE progress stream |
| `/query/scenarios` | GET | List all loaded scenarios (queries Cosmos for available graphs via ARM) |
| `/query/scenario/{graph_name}` | DELETE | Drop all data from a scenario's graph |

### Upload Flow

```
1. User clicks ⚙ in the header → Settings modal opens
2. User drags a scenario .tar.gz file onto the upload area
3. Frontend POSTs the file to /query/scenario/upload
4. graph-query-api:
   a. Extracts the archive to a temp directory
   b. Reads scenario.yaml and graph_schema.yaml
   c. Creates the Gremlin graph via ARM API (DocumentDB Account Contributor role)
   d. Drops existing data in the graph (if present)
   e. Loads all vertices from Dim*.csv files via Gremlin addV()
   f. Loads all edges from Fact*.csv files via Gremlin addE()
   g. Creates the NoSQL database + containers
   h. Upserts telemetry rows from CSV files
   i. Sends SSE progress events throughout (step name, detail, percentage)
5. Frontend shows a progress bar with step-by-step detail
6. On completion, the scenario appears in the loaded scenarios list
```

### SSE Progress Events

The upload endpoint streams events during ingestion:

```
event: progress
data: {"step": "parsing", "detail": "Scenario: Cloud Outage (cloud-outage)", "pct": 10}

event: progress
data: {"step": "graph", "detail": "Loading Host (10 vertices)...", "pct": 35}

event: progress
data: {"step": "telemetry", "detail": "Upserting 4453 docs into AlertStream...", "pct": 80}

event: complete
data: {"scenario": "cloud-outage", "graph": "cloud-outage-topology", "vertices": 57, "edges": 42}
```

On error:
```
event: error
data: {"error": "wss://...connection refused"}
```

### Scenario Archive Format

The `.tar.gz` must contain (at the archive root or one level down):

```
<scenario-name>/
├── scenario.yaml          # Required — scenario manifest
├── graph_schema.yaml      # Required — graph ontology
└── data/
    ├── entities/          # Required — Dim*.csv vertices + Fact*.csv edges
    ├── telemetry/         # Optional — AlertStream.csv + metrics CSVs
    ├── knowledge/         # Optional — runbooks/ and tickets/ for AI Search
    └── prompts/           # Optional — agent prompt fragments
```

Create a tarball from an existing scenario:
```bash
tar czf cloud-outage.tar.gz -C data/scenarios cloud-outage
```

## Files Changed

### New Files

| File | Purpose |
|------|---------|
| `graph-query-api/router_ingest.py` | Upload endpoint, Gremlin/NoSQL ingestion logic, scenario listing, scenario deletion |
| `frontend/src/components/SettingsModal.tsx` | Settings modal with loaded scenarios list + drag-and-drop upload |
| `frontend/src/hooks/useScenarios.ts` | Hook for scenario listing, upload with SSE progress, error handling |

### Modified Files

| File | Change |
|------|--------|
| `graph-query-api/pyproject.toml` | Added `python-multipart`, `pyyaml`, `azure-mgmt-cosmosdb`, `sse-starlette` |
| `graph-query-api/main.py` | Mounted `router_ingest` |
| `nginx.conf` | Added `client_max_body_size 100m`, SSE support on `/query/` routes |
| `frontend/vite.config.ts` | SSE support for `/query` dev proxy |
| `frontend/src/components/Header.tsx` | Added ⚙ settings button, renamed to "AI Incident Investigator", wired SettingsModal |
| `infra/modules/roles.bicep` | Added `DocumentDB Account Contributor` role for Container App MI on Gremlin account |
| `infra/main.bicep` | Passes `cosmosGremlinAccountName` to roles module; adds `AZURE_SUBSCRIPTION_ID` and `AZURE_RESOURCE_GROUP` env vars to Container App |
| `deploy.sh` | Replaced Steps 5/5b (direct Cosmos loading + firewall code) with UI upload instructions |
| `hooks/postprovision.sh` | Updated telemetry/network blob upload comments (now optional backup) |

## RBAC Requirements

The Container App's managed identity needs `DocumentDB Account Contributor`
on the Cosmos Gremlin account to create new graphs via the ARM management
plane. This role is assigned by `roles.bicep` using the built-in role ID
`5bd9cd88-fe45-4216-938b-f97437e15450`.

The existing `Cosmos DB Built-in Data Contributor` role on the NoSQL account
(already assigned) handles telemetry upserts.

Gremlin data-plane operations (addV, addE, drop) use key-based auth
(`COSMOS_GREMLIN_PRIMARY_KEY`), which is passed as a Container App secret.

## deploy.sh Changes

### Removed (~150 lines)

- Step 5: Direct Cosmos Gremlin loading from dev machine
  - IP detection (`curl ifconfig.me`)
  - `_open_cosmos_firewall()` function
  - `az cosmosdb update --public-network-access ENABLED`
  - `uv run python scripts/cosmos/provision_cosmos_gremlin.py`
  - Firewall error handling and retry instructions
- Step 5b: Direct Cosmos NoSQL telemetry loading
  - `uv run python scripts/cosmos/provision_cosmos_telemetry.py`
  - RBAC and throttling error handling

### Replaced With

Step 5 now prints instructions for using the UI upload:
```
━━━ Step 5: Cosmos DB graph + telemetry data ━━━

ℹ  Graph and telemetry data is now loaded via the UI Settings page.
ℹ  This eliminates the need for direct Cosmos DB access, firewall
ℹ  configuration, and public network access from dev machines.

ℹ  How to load data:
   1. Open the app at <app-url>
   2. Click the ⚙ settings icon in the header
   3. Upload a scenario .tar.gz file
   4. The Container App loads data directly into Cosmos DB

✓  Data loading moved to UI — no Cosmos firewall dance needed!
```

### Still Present

- Steps 0–3: Infrastructure provisioning (unchanged)
- Step 4: Search index creation (still needed — AI Search indexers are separate)
- Steps 6–8: App health check, agent provisioning, local services (unchanged)

## Backwards Compatibility

- The provisioning scripts (`provision_cosmos_gremlin.py`, `provision_cosmos_telemetry.py`)
  are **not deleted**. They still work for manual CLI-based ingestion when needed.
- The `--skip-data` flag remains functional (now a no-op since the step is purely informational).
- The `--from-blob` telemetry ingestion path is preserved. Blob uploads in `postprovision.sh`
  still run for runbooks/tickets (AI Search) and optionally for telemetry/network (backup).

## Future Considerations

### AI Search Index Creation via UI

The AI Search indexers (`create_runbook_indexer.py`, `create_tickets_indexer.py`)
still run from `deploy.sh` Step 4. In a future iteration, these could also be
triggered from the UI after a scenario upload, since the uploaded archive
contains both `knowledge/runbooks/` and `knowledge/tickets/` files.

### Fabric Graph DB

The upload architecture is backend-agnostic. The `router_ingest.py` currently
targets Cosmos Gremlin + NoSQL, but the same upload flow could route to a
Fabric Graph DB backend by:
1. Adding a `GRAPH_BACKEND=fabric` case in the ingestion logic
2. Using the Fabric SDK to create ontologies and load entities
3. The frontend upload UX remains unchanged

### Scenario Deletion

The `DELETE /query/scenario/{graph_name}` endpoint currently drops graph data
but doesn't clean up the NoSQL telemetry database. Full cleanup would require
deleting the database via ARM or dropping all documents in each container.

---

## Phase 2: Agent Configuration Plane

### Problem

Phase 1 (above) handles **data ingestion** but leaves three critical gaps:

1. **No data source selection** — agents are hard-wired at provisioning time to
   one graph, one runbooks index, one tickets index. Users can upload multiple
   scenarios but can't tell agents which data to use.
2. **No prompt management** — prompts are `.md` files baked into the repo. Adding
   or editing a prompt requires a code commit and redeployment.
3. **No runtime agent reconfiguration** — changing any agent's prompt or data
   source requires running `provision_agents.py` from the CLI.

### Target State

A Settings page with two tabs:

```
┌─────────────────────────────────────────────────────────────────┐
│ Settings                                                     ✕  │
├─────────────────────────────────────────────────────────────────┤
│  [Data Sources]  [Agent Config]  [Upload]                       │
│                                                                 │
│  ◄ currently showing: Data Sources ►                           │
│                                                                 │
│  Each agent is independently bound to its data source.         │
│  Changes take ~30s to apply (agents are re-provisioned).       │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ GraphExplorer Agent                                       │ │
│  │   Graph:       [cloud-outage-topology              ▼]     │ │
│  │   (telemetry DB auto-derived: cloud-outage-telemetry)     │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ Telemetry Agent                                           │ │
│  │   Database:    [cloud-outage-telemetry              ▼]     │ │
│  │   (derived from graph selection above — same Cosmos DB)   │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ RunbookKB Agent                                           │ │
│  │   Search Index: [telco-noc-runbooks-index           ▼]     │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ HistoricalTicket Agent                                    │ │
│  │   Search Index: [cloud-outage-tickets-index         ▼]     │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│               [Apply Changes]  (re-provisions agents)           │
└─────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────┐
│ Settings                                                     ✕  │
├─────────────────────────────────────────────────────────────────┤
│  [Data Sources]  [Agent Config]  [Upload]                       │
│                                                                 │
│  ◄ currently showing: Agent Config ►                           │
│                                                                 │
│  Assign prompts to each agent from the Prompts Library.        │
│  Prompts are stored in Cosmos DB and can be edited inline.     │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Orchestrator                                              │ │
│  │   Prompt: [telco-noc/orchestrator                   ▼]    │ │
│  │   [Preview] [Edit]                                        │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ GraphExplorer                                             │ │
│  │   Prompt: [cloud-outage/graph_explorer              ▼]    │ │
│  │   [Preview] [Edit]                                        │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ Telemetry                                                 │ │
│  │   Prompt: [cloud-outage/telemetry_agent             ▼]    │ │
│  │   [Preview] [Edit]                                        │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ RunbookKB                                                 │ │
│  │   Prompt: [shared/runbook_core                      ▼]    │ │
│  │   [Preview] [Edit]                                        │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ HistoricalTicket                                          │ │
│  │   Prompt: [shared/ticket_core                       ▼]    │ │
│  │   [Preview] [Edit]                                        │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  PROMPTS LIBRARY                                                │
│  ┌──────────────────────┬──────────────────┬──────────────┐    │
│  │ Name                 │ Scenario         │ Agent        │    │
│  ├──────────────────────┼──────────────────┼──────────────┤    │
│  │ orchestrator         │ telco-noc        │ Orchestrator │    │
│  │ orchestrator         │ cloud-outage     │ Orchestrator │    │
│  │ graph_explorer       │ telco-noc        │ GraphExplorer│    │
│  │ graph_explorer       │ cloud-outage     │ GraphExplorer│    │
│  │ telemetry_agent      │ telco-noc        │ Telemetry    │    │
│  │ runbook_core         │ shared           │ RunbookKB    │    │
│  │ ticket_core          │ shared           │ Ticket       │    │
│  └──────────────────────┴──────────────────┴──────────────┘    │
│  [Upload Prompts (.tar.gz)]  [+ New Prompt]                     │
│                                                                 │
│               [Apply Changes]  (re-provisions agents)           │
└─────────────────────────────────────────────────────────────────┘
```

---

### Phase 2A: Agent Data Source Bindings

#### Architecture

Each of the 4 sub-agents has an independent data source binding:

| Agent | Data Source Type | Selection Source | Runtime Effect |
|-------|-----------------|------------------|----------------|
| **GraphExplorer** | Cosmos Gremlin graph | `GET /query/scenarios` | graph-query-api routes `/query/graph` and `/query/topology` to the selected graph |
| **Telemetry** | Cosmos NoSQL database | Auto-derived from graph selection | graph-query-api routes `/query/telemetry` to `{scenario}-telemetry` database |
| **RunbookKB** | AI Search index | `GET /query/indexes` (new endpoint) | Agent re-provisioned with `AzureAISearchTool` pointing to selected index |
| **HistoricalTicket** | AI Search index | `GET /query/indexes` (new endpoint) | Agent re-provisioned with `AzureAISearchTool` pointing to selected index |

#### Data Flow: Applying Changes

```
Frontend                    API (port 8000)               graph-query-api (8100)
    │                           │                              │
    │ POST /api/config          │                              │
    │  /datasources             │                              │
    │ {                         │                              │
    │   graph: "cloud-outage-   │                              │
    │          topology",       │                              │
    │   runbooks_index: "telco- │                              │
    │          noc-runbooks-    │                              │
    │          index",          │                              │
    │   tickets_index: "cloud-  │                              │
    │          outage-tickets-  │                              │
    │          index"           │                              │
    │ }                         │                              │
    │ ─────────────────────────>│                              │
    │                           │  1. Store in memory          │
    │                           │  2. Re-provision RunbookKB   │
    │                           │     with new index name      │
    │                           │  3. Re-provision TicketAgent │
    │                           │     with new index name      │
    │                           │  4. Update agent_ids.json    │
    │                           │                              │
    │ SSE progress stream       │                              │
    │ <─────────────────────────│                              │
    │                           │                              │
    │ (subsequent requests)     │                              │
    │ X-Graph: cloud-outage-    │                              │
    │          topology         │                              │
    │ ──────────────────────────┼─────────────────────────────>│
    │                           │   graph-query-api reads      │
    │                           │   X-Graph header to route    │
    │                           │   Gremlin + telemetry queries│
```

#### Graph Selection Propagation (No Re-Provisioning Needed)

The GraphExplorer and Telemetry agents don't need re-provisioning when the
graph changes — they call OpenAPI tool endpoints on graph-query-api, which can
read the target graph from a request header. The key insight:

1. **Frontend** stores `activeGraph` in React state.
2. **Frontend** sends `X-Graph: {activeGraph}` header on all `/query/*` requests.
3. **graph-query-api** reads the header in a FastAPI dependency and creates/reuses
   a Gremlin client targeting that graph.
4. **Telemetry database** is derived from the graph name:
   `cloud-outage-topology` → `cloud-outage-telemetry`.

This means graph switching is **instant** — no re-provisioning, no waiting.

Only RunbookKB and HistoricalTicket require re-provisioning because their
`AzureAISearchTool` index name is baked into the Foundry agent at creation time.

#### New Endpoints

| Service | Endpoint | Method | Purpose |
|---------|----------|--------|---------|
| graph-query-api | `/query/indexes` | GET | List AI Search indexes (calls ARM) |
| graph-query-api | `/query/scenarios` | GET | List Gremlin graphs (already exists) |
| API | `/api/config/datasources` | POST | Apply data source bindings → re-provision search agents |
| API | `/api/config/datasources` | GET | Return current data source bindings |

#### Implementation Tasks

- [ ] **graph-query-api**: Add `GET /query/indexes` endpoint (list AI Search indexes via `azure-search-documents` SDK `SearchIndexClient.list_indexes()`)
- [ ] **graph-query-api**: Add `X-Graph` header support — FastAPI dependency that extracts graph name and overrides graph-query-api's Gremlin client target
- [ ] **graph-query-api**: Refactor `CosmosDBGremlinBackend` to accept graph name as parameter (not module-level config). Create backend factory with per-graph client cache.
- [ ] **graph-query-api**: Derive telemetry database from graph name (`{graph_name.rsplit('-', 1)[0]}-telemetry`)
- [ ] **API**: Extract `provision_agents.py` agent creation functions into an importable module (remove argparse `__main__` coupling)
- [ ] **API**: Add `POST /api/config/datasources` endpoint that:
  1. Accepts `{graph, runbooks_index, tickets_index}`
  2. Re-provisions RunbookKB and HistoricalTicket agents with new index names
  3. Updates in-memory agent registry (not just `agent_ids.json`)
  4. Returns SSE progress during re-provisioning (~30s)
- [ ] **API**: Add mutex/lock around re-provisioning to prevent concurrent switches
- [ ] **API**: Add `GET /api/config/datasources` to return current bindings
- [ ] **Frontend**: Add "Data Sources" tab to Settings modal with 4 dropdowns
- [ ] **Frontend**: Store `activeGraph` in React context, propagate via `X-Graph` header on all `/query/*` fetch calls
- [ ] **Frontend**: "Apply Changes" button triggers `POST /api/config/datasources` and shows progress
- [ ] **API pyproject.toml**: Add `azure-search-documents` dependency (needed for index listing, if proxied through API instead of graph-query-api)

---

### Phase 2B: Prompts Database (Cosmos NoSQL)

#### Why a Database?

Currently prompts are `.md` files on disk at `data/scenarios/*/data/prompts/`.
This has three problems:

1. **Editing requires a code commit** — you can't tune a prompt without SSH
   access or a redeployment.
2. **No versioning** — overwriting a file loses the previous version.
3. **No runtime switching** — the agent is provisioned with whatever prompt was
   on disk at provisioning time. To try a different prompt, you re-provision.

A Cosmos NoSQL prompts collection solves all three:
- **CRUD from the UI** — edit prompts in a text area, save to Cosmos
- **Version history** — each save creates a new version document
- **Runtime selection** — pick which prompt version each agent uses

#### Data Model

**Container:** `prompts` in the existing NoSQL telemetry account (or a new 
`platform-config` database — see design decision below).

**Partition key:** `/agent` (agent name: `orchestrator`, `graph_explorer`,
`telemetry`, `runbook`, `ticket`)

**Document schema:**

```json
{
  "id": "cloud-outage/orchestrator/v3",
  "agent": "orchestrator",
  "scenario": "cloud-outage",
  "name": "orchestrator",
  "version": 3,
  "content": "# Orchestrator System Prompt\n\nYou are an AI ...",
  "description": "Cloud outage orchestrator with thermal cascade focus",
  "created_at": "2026-02-15T10:30:00Z",
  "created_by": "ui-upload",
  "is_active": true,
  "tags": ["cloud", "thermal", "orchestrator"]
}
```

**Document ID format:** `{scenario}/{name}/v{version}`

**Key design decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | New `platform-config` database (not per-scenario telemetry DB) | Prompts are cross-scenario — shouldn't be deleted when a scenario's telemetry DB is dropped |
| Partition key | `/agent` | Queries are always "list all prompts for agent X" |
| Versioning | Immutable version documents | Never overwrite — create `v{n+1}`. `is_active` flag marks the current version |
| Content format | Raw markdown string | Same format as current `.md` files — no structural change to what agents receive |

#### GraphExplorer Prompt Composition

The GraphExplorer agent has a unique prompt structure — it's assembled from
3 files (core_instructions + core_schema + language_{backend}). This means
the prompts DB needs to either:

**Option A: Store the composed result** — the UI shows a "compose" button that
reads the 3 parts and saves the merged result as a single prompt document.
Editing the final composed prompt is straightforward. Recomposition happens
when the schema changes.

**Option B: Store the parts separately** — 3 documents per scenario for
GraphExplorer (`core_instructions`, `core_schema`, `language_gremlin`),
composed at provisioning time. More flexible but more complex UI.

**Recommendation: Option A.** Store the composed result. The schema prompt
(core_schema.md) is auto-generated from `graph_schema.yaml` anyway — it's not
hand-edited. So the useful unit of editing is the final composed prompt.
The Upload flow auto-composes when a scenario is uploaded; the Edit flow lets
users modify the result.

#### Prompt Upload Flow (from Scenario .tar.gz)

When a scenario is uploaded (Phase 1 upload endpoint), prompts from the archive
are automatically stored in Cosmos:

```
Upload .tar.gz
  → ... (existing graph + telemetry ingestion) ...
  → Read data/prompts/*.md from archive
  → For each prompt file:
    1. Determine agent mapping:
       foundry_orchestrator_agent.md → agent: "orchestrator"
       graph_explorer/              → agent: "graph_explorer" (composed)
       foundry_telemetry_agent_v2.md → agent: "telemetry"
       foundry_runbook_kb_agent.md  → agent: "runbook"
       foundry_historical_ticket_agent.md → agent: "ticket"
       alert_storm.md              → agent: "default_alert" (special)
    2. Check if this prompt already exists in Cosmos (same scenario + name)
    3. If exists, increment version number
    4. Upsert document to prompts container
  → Return prompt IDs in upload result
```

#### Prompt CRUD Endpoints

| Service | Endpoint | Method | Purpose |
|---------|----------|--------|---------|
| graph-query-api | `/query/prompts` | GET | List all prompts (optional filter by `?agent=orchestrator&scenario=cloud-outage`) |
| graph-query-api | `/query/prompts/{id}` | GET | Get a specific prompt document (includes content) |
| graph-query-api | `/query/prompts` | POST | Create a new prompt (or new version of existing) |
| graph-query-api | `/query/prompts/{id}` | PUT | Update prompt metadata (tags, is_active) — content is immutable per version |
| graph-query-api | `/query/prompts/{id}` | DELETE | Soft-delete a prompt version |

#### Implementation Tasks

- [ ] **graph-query-api**: Create `router_prompts.py` with CRUD endpoints
- [ ] **graph-query-api**: Create `platform-config` database + `prompts` container on first access (`create_database_if_not_exists` + `create_container_if_not_exists`)
- [ ] **router_ingest.py**: Add prompt extraction and storage after graph/telemetry ingestion
- [ ] **router_ingest.py**: Map prompt filenames to agent names (both old `foundry_*` names and new canonical names)
- [ ] **router_ingest.py**: Auto-compose GraphExplorer prompt from `graph_explorer/` directory files
- [ ] **Frontend**: Add "Agent Config" tab to Settings modal
- [ ] **Frontend**: Per-agent prompt dropdown (filtered by agent name)
- [ ] **Frontend**: "Preview" button → read-only modal showing prompt content
- [ ] **Frontend**: "Edit" button → text editor modal, save creates new version
- [ ] **Frontend**: "Upload Prompts" button → upload a .tar.gz of prompt .md files
- [ ] **Frontend**: "+ New Prompt" button → blank editor
- [ ] **Frontend**: Prompts library table with filtering

---

### Phase 2C: Unified Apply Flow

When the user clicks "Apply Changes" (on either tab), the system:

```
1. Frontend sends POST /api/config/apply
   {
     "datasources": {
       "graph": "cloud-outage-topology",
       "runbooks_index": "telco-noc-runbooks-index",
       "tickets_index": "cloud-outage-tickets-index"
     },
     "prompts": {
       "orchestrator": "cloud-outage/orchestrator/v3",
       "graph_explorer": "cloud-outage/graph_explorer/v2",
       "telemetry": "cloud-outage/telemetry_agent/v1",
       "runbook": "shared/runbook_core/v1",
       "ticket": "shared/ticket_core/v1"
     }
   }

2. API (port 8000):
   a. Fetch prompt content from Cosmos for each agent
   b. Re-provision all 5 agents with:
      - Selected prompts (from Cosmos, not from disk)
      - Selected index names (for RunbookKB + HistoricalTicket)
      - Selected OpenAPI spec base URL (unchanged)
   c. Update agent_ids.json
   d. Update in-memory agent registry
   e. Store current config in Cosmos (platform-config/active-config)
   f. Stream SSE progress

3. Frontend:
   a. Update X-Graph header for subsequent requests
   b. Show confirmation with new agent IDs
   c. Reset investigation state (clean slate for new config)
```

#### Re-Provisioning Implementation

`provision_agents.py` is currently a CLI script. Its agent creation functions
must be extracted into an importable module:

```python
# scripts/agent_provisioner.py (new — extracted from provision_agents.py)

class AgentProvisioner:
    """Runtime agent provisioning — importable from the API server."""

    def __init__(self, project_endpoint: str, project_name: str):
        self.client = AgentsClient(endpoint=..., credential=...)

    async def provision_all(
        self,
        model: str,
        prompts: dict[str, str],          # agent_name → prompt content
        graph_query_uri: str,             # OpenAPI tool base URL
        graph_backend: str,               # "cosmosdb" | "mock"
        runbooks_index: str,              # AI Search index name
        tickets_index: str,               # AI Search index name
        search_connection_id: str,        # AI Foundry connection ID
        progress_callback: Callable | None = None,
    ) -> dict:
        """Provision all 5 agents and return agent_ids structure."""
        ...

    async def provision_search_agents_only(
        self,
        model: str,
        runbooks_prompt: str,
        tickets_prompt: str,
        runbooks_index: str,
        tickets_index: str,
        search_connection_id: str,
        existing_agent_ids: dict,         # Preserve graph/telemetry/orchestrator
        progress_callback: Callable | None = None,
    ) -> dict:
        """Re-provision only RunbookKB + HistoricalTicket (for index switch)."""
        ...
```

The existing `provision_agents.py` CLI becomes a thin wrapper that calls
`AgentProvisioner.provision_all()`.

The API's `POST /api/config/apply` endpoint imports `AgentProvisioner` and
calls the appropriate method.

#### Concurrency Safety

- A `threading.Lock` guards the re-provisioning operation.
- While re-provisioning is in progress, new investigation requests get a
  `503 Switching Configuration` response.
- The lock is held for ~30 seconds (agent creation time).
- The frontend shows a loading state and blocks new alerts during the switch.

---

### Phase 2D: Knowledge Base Indexing from Upload

#### Problem

Currently `deploy.sh` Step 4 runs `create_runbook_indexer.py` and
`create_tickets_indexer.py` from the CLI. This requires developer machine
access and the correct env vars.

#### Solution

The scenario upload endpoint (Phase 1) is extended to also:

1. Upload `knowledge/runbooks/*.md` to blob container `{scenario}-runbooks`
2. Upload `knowledge/tickets/*.txt` to blob container `{scenario}-tickets`
3. Create AI Search data sources, indexes, skillsets, and indexers
4. Poll until indexing completes
5. Return the created index names in the upload result

#### Data Flow

```
Upload .tar.gz
  → ... (graph + telemetry + prompts) ...
  → Upload knowledge/runbooks/*.md to blob "{scenario}-runbooks"     (NEW)
  → Upload knowledge/tickets/*.txt to blob "{scenario}-tickets"      (NEW)
  → Create AI Search indexer pipeline for runbooks                   (NEW)
  → Create AI Search indexer pipeline for tickets                    (NEW)
  → Poll indexers until complete (~60-120s)                          (NEW)
  → Return {
      scenario, graph, telemetry_db,
      vertices, edges,
      runbooks_index: "{scenario}-runbooks-index",     (NEW)
      tickets_index: "{scenario}-tickets-index",       (NEW)
      prompts: [...]                                   (NEW)
    }
```

#### Dependencies Required

| Package | Purpose | Already in graph-query-api? |
|---------|---------|--------------------------|
| `azure-storage-blob` | Upload files to blob containers | **No** — must add |
| `azure-search-documents` | Create data sources, indexes, skillsets, indexers | **No** — must add |

#### AI Search Indexer Logic

Extracted from `scripts/_indexer_common.py` (232 lines). The core logic creates:

1. **Data source** — `SearchIndexerDataSourceConnection` (type `azureblob`,
   managed identity resource-ID connection string)
2. **Index** — 5 fields: `chunk_id` (key), `parent_id`, `chunk` (searchable),
   `title` (filterable), `vector` (HNSW + Azure OpenAI vectorizer)
3. **Skillset** — `SplitSkill` (2000-char pages, 500-char overlap) +
   `AzureOpenAIEmbeddingSkill` (vectorizes each chunk)
4. **Indexer** — ties data source → skillset → index, runs immediately

The key adaptation for running inside the Container App:
- Auth: `DefaultAzureCredential` (managed identity) — already works
- RBAC: Container App MI already has `Search Service Contributor` +
  `Search Index Data Contributor` + `Storage Blob Data Contributor`
- Env vars: `AI_SEARCH_NAME`, `STORAGE_ACCOUNT_NAME`, `AI_FOUNDRY_NAME`,
  `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP` — need to be passed to
  the Container App (some already are, some need adding to main.bicep)

#### Additional Env Vars for Container App (main.bicep)

```bicep
{ name: 'AI_SEARCH_NAME', value: search.outputs.name }
{ name: 'STORAGE_ACCOUNT_NAME', value: storage.outputs.name }
{ name: 'AI_FOUNDRY_NAME', value: aiFoundry.outputs.foundryName }
{ name: 'EMBEDDING_MODEL', value: 'text-embedding-3-small' }
{ name: 'EMBEDDING_DIMENSIONS', value: '1536' }
```

#### Implementation Tasks

- [ ] **graph-query-api pyproject.toml**: Add `azure-storage-blob`, `azure-search-documents`
- [ ] **graph-query-api**: Create `indexer_service.py` — extracted/adapted from `_indexer_common.py`, async-compatible, creates the full indexer pipeline
- [ ] **router_ingest.py**: After graph+telemetry+prompts, upload runbooks/tickets to blob and create search indexes
- [ ] **router_ingest.py**: Add SSE progress events for blob upload + indexing steps
- [ ] **router_ingest.py**: Poll indexer status and report document counts in completion event
- [ ] **main.bicep**: Add `AI_SEARCH_NAME`, `STORAGE_ACCOUNT_NAME`, `AI_FOUNDRY_NAME`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` env vars to Container App
- [ ] **deploy.sh Step 4**: Replace with informational message (like Step 5) — indexing now happens during scenario upload

---

### Phase 2 Summary: What Gets Built

| Component | Phase | New Files | Modified Files |
|-----------|-------|-----------|----------------|
| Data source dropdowns | 2A | — | Settings modal, Header |
| `GET /query/indexes` | 2A | — | `router_ingest.py` |
| `X-Graph` header support | 2A | — | `router_graph.py`, `router_telemetry.py`, `router_topology.py`, `config.py` |
| `POST /api/config/datasources` | 2A | `api/app/routers/config.py` | `api/app/main.py` |
| Agent provisioner module | 2A+2C | `scripts/agent_provisioner.py` | `provision_agents.py` (becomes thin wrapper) |
| Prompts CRUD | 2B | `graph-query-api/router_prompts.py` | `graph-query-api/main.py` |
| Prompts in Cosmos | 2B | — | `router_ingest.py` (prompt extraction) |
| Agent Config tab | 2B | — | Settings modal |
| Unified apply flow | 2C | — | `api/app/routers/config.py` |
| Blob upload from archive | 2D | — | `router_ingest.py` |
| AI Search indexer service | 2D | `graph-query-api/indexer_service.py` | `router_ingest.py`, `main.bicep` |

### Phase 2 Effort Estimates

| Sub-phase | Effort | Risk |
|-----------|--------|------|
| 2A: Data source bindings | 4-6 hours | Medium — Gremlin client refactor needs care |
| 2B: Prompts database | 3-4 hours | Low — straightforward CRUD |
| 2C: Unified apply flow | 3-4 hours | Medium — agent provisioner extraction, concurrency |
| 2D: Knowledge indexing | 4-5 hours | Medium — AI Search SDK integration, indexer polling |
| **Total** | **14-19 hours** | |

### Phase 2 Dependency Order

```
2A (data source bindings)
  └─ 2B (prompts DB)        ← can start in parallel with 2A
       └─ 2C (unified apply) ← depends on both 2A + 2B
  └─ 2D (knowledge indexing) ← can start in parallel with 2B
```

Minimum viable path: **2A + 2D → 2C** (data source switching + full upload
pipeline, without prompt editing). Prompts (2B) can be added incrementally.

---

## Phase 2 File Impact Analysis

Every file in the project that needs modification, deprecation, or monitoring.

### Files to Deprecate → `deprecated/`

These files become fully redundant after Phase 2 and should be moved to
`deprecated/` with a one-line explanation of what replaced them.

| File | Reason | Replacement |
|------|--------|-------------|
| `scripts/create_runbook_indexer.py` | Index creation moves to UI upload endpoint | `graph-query-api/services/search_indexer.py` |
| `scripts/create_tickets_indexer.py` | Same as above | Same |
| `scripts/_indexer_common.py` | Logic migrated to graph-query-api | `graph-query-api/services/search_indexer.py` |
| `scripts/cosmos/provision_cosmos_gremlin.py` | Graph loading moved to UI upload (Phase 1) | `graph-query-api/router_ingest.py` |
| `scripts/cosmos/provision_cosmos_telemetry.py` | Telemetry loading moved to UI upload (Phase 1) | `graph-query-api/router_ingest.py` |
| `data/shared_prompts/` | Prompt composition concept moves to Cosmos prompt store | Cosmos `platform-config.prompts` container |

**Deprecation command:**
```bash
mkdir -p deprecated/scripts/cosmos
git mv scripts/create_runbook_indexer.py deprecated/scripts/
git mv scripts/create_tickets_indexer.py deprecated/scripts/
git mv scripts/_indexer_common.py deprecated/scripts/
git mv scripts/cosmos/provision_cosmos_gremlin.py deprecated/scripts/cosmos/
git mv scripts/cosmos/provision_cosmos_telemetry.py deprecated/scripts/cosmos/
git mv data/shared_prompts/ deprecated/
```

### Files to Trim (remove redundant sections)

#### `deploy.sh`

| Step | Current | After Phase 2 |
|------|---------|---------------|
| Step 0: Prereqs | Check tools installed | **Keep** |
| Step 1: Environment | azd environment setup | **Keep** |
| Step 2: Config | Generate azure_config.env | **Keep** |
| Step 3: Infrastructure | `azd up` | **Keep** |
| Step 4: Search indexes | `create_runbook_indexer.py` + `create_tickets_indexer.py` | **Replace** with informational message (indexes created on scenario upload) |
| Step 5: Cosmos data | Already informational (Phase 1) | **Keep** as-is |
| Step 6: Health check | Verify Container App health | **Keep** |
| Step 7: Agents | `provision_agents.py --force` + redeploy | **Replace**: initial agents provisioned on first config apply from UI. Step 7b (redeploy for agent_ids.json) becomes unnecessary when agent IDs are stored in Cosmos |
| Step 7b: Redeploy | `azd deploy` to bake agent_ids.json | **Remove**: agent config is in Cosmos, not a baked file |
| Step 8: Local dev | Start local services | **Keep** |

**Net effect:** deploy.sh goes from 913 lines to ~500 lines. Steps 4, 7, 7b
become informational (like Step 5). The message directs users to the UI
Settings page for data upload + agent configuration.

#### `hooks/postprovision.sh`

| Section | Current | After Phase 2 |
|---------|---------|---------------|
| 1. Upload runbooks to blob | `upload_with_retry "runbooks"` | **Remove** — uploads happen on scenario upload via UI |
| 2. Upload tickets to blob | `upload_with_retry "tickets"` | **Remove** |
| 2b. Upload telemetry + network CSVs | `upload_with_retry "telemetry-data"` / `"network-data"` | **Remove** |
| 3. Populate azure_config.env | Write Bicep outputs to config file | **Keep** |
| 4. Write Cosmos credentials | Fetch keys, write to config | **Keep** |

**Net effect:** ~30 lines of blob upload code removed. Config population stays.

### Files to Refactor (significant changes)

#### `graph-query-api/config.py`

**Problem:** All config is module-level constants read at import time.

**Change:** Add a `ScenarioContext` dataclass and a FastAPI dependency that
resolves per-request context from headers:

```python
@dataclass
class ScenarioContext:
    """Per-request scenario routing context, resolved from X-Graph header."""
    graph_name: str           # e.g. "cloud-outage-topology"
    gremlin_database: str     # e.g. "networkgraph" (shared)
    telemetry_database: str   # e.g. "cloud-outage-telemetry" (derived)
    backend_type: GraphBackendType

def get_scenario_context(
    x_graph: str = Header(default=None),
) -> ScenarioContext:
    graph = x_graph or COSMOS_GREMLIN_GRAPH  # env var fallback
    scenario_prefix = graph.rsplit("-", 1)[0] if "-" in graph else graph
    return ScenarioContext(
        graph_name=graph,
        gremlin_database=COSMOS_GREMLIN_DATABASE,
        telemetry_database=f"{scenario_prefix}-telemetry",
        backend_type=GRAPH_BACKEND,
    )
```

#### `graph-query-api/backends/cosmosdb.py`

**Problem:** Singleton Gremlin client hardwired to one graph.

**Change:** Backend factory with per-graph client cache:

```python
_clients: dict[str, CosmosDBGremlinBackend] = {}
_clients_lock = threading.Lock()

def get_backend_for_graph(graph_name: str) -> CosmosDBGremlinBackend:
    with _clients_lock:
        if graph_name not in _clients:
            _clients[graph_name] = CosmosDBGremlinBackend(
                endpoint=COSMOS_GREMLIN_ENDPOINT,
                key=COSMOS_GREMLIN_PRIMARY_KEY,
                database=COSMOS_GREMLIN_DATABASE,
                graph=graph_name,
            )
        return _clients[graph_name]
```

#### `graph-query-api/router_graph.py`

**Problem:** Uses `get_graph_backend()` singleton.

**Change:** Accept `ScenarioContext` via FastAPI `Depends()`:

```python
@router.post("/query/graph")
async def query_graph(
    request: GraphQueryRequest,
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    backend = get_backend_for_graph(ctx.graph_name)
    ...
```

#### `graph-query-api/router_telemetry.py`

**Problem:** `VALID_CONTAINERS` hardcoded; database from module constant.

**Change:** Accept `ScenarioContext`, use `ctx.telemetry_database`:

```python
@router.post("/query/telemetry")
async def query_telemetry(
    request: TelemetryQueryRequest,
    ctx: ScenarioContext = Depends(get_scenario_context),
):
    # No VALID_CONTAINERS check — trust the agent's query
    # or discover containers from Cosmos at runtime
    result = await _execute_cosmos_sql(
        request.query,
        request.container_name,
        cosmos_database=ctx.telemetry_database,  # scenario-specific
    )
    ...
```

#### `graph-query-api/router_topology.py`

**Problem:** Same singleton backend as router_graph.

**Change:** Same — `Depends(get_scenario_context)` → `get_backend_for_graph()`.

#### `api/app/orchestrator.py`

**Problem:** Reads agent IDs from `agent_ids.json` on disk.

**Change:**
1. Add Cosmos-backed agent config reader
2. `is_configured()` checks Cosmos for agent records
3. `_load_orchestrator_id()` reads from Cosmos
4. In-memory cache with a `_config_version` counter that bumps on reconfigure
5. Falls back to `agent_ids.json` if Cosmos is unavailable (backwards compat)

```python
_agent_config: dict | None = None
_config_version: int = 0

async def load_agent_config() -> dict:
    """Load active agent config from Cosmos (or fallback to file)."""
    global _agent_config
    if _agent_config is not None:
        return _agent_config
    try:
        # Try Cosmos first
        config = await _read_config_from_cosmos()
        _agent_config = config
        return config
    except Exception:
        # Fallback to file
        return _load_from_file()

async def update_agent_config(new_config: dict):
    """Called after re-provisioning — updates in-memory cache."""
    global _agent_config, _config_version
    _agent_config = new_config
    _config_version += 1
    await _write_config_to_cosmos(new_config)
```

#### `api/app/routers/agents.py`

**Change:** Add config endpoints:

```python
@router.post("/api/config/apply")
async def apply_config(config: ConfigRequest):
    """Apply new data source + prompt bindings → re-provision agents."""
    ...

@router.get("/api/config/datasources")
async def get_datasources():
    """Return current data source bindings."""
    ...
```

#### `scripts/provision_agents.py`

**Change:** Extract core logic into importable module:

```
scripts/provision_agents.py           → thin CLI wrapper (kept for manual use)
scripts/agent_provisioner.py (NEW)    → AgentProvisioner class (importable)
  └─ create_graph_explorer_agent()
  └─ create_telemetry_agent()
  └─ create_runbook_kb_agent()
  └─ create_historical_ticket_agent()
  └─ create_orchestrator()
  └─ provision_all()
  └─ provision_search_agents_only()
```

The API's `/api/config/apply` imports `AgentProvisioner` and calls it.

### Frontend Files to Modify

| File | Change |
|------|--------|
| `Header.tsx` | Dynamic agent count from `GET /api/agents`; active scenario indicator |
| `SettingsModal.tsx` | Expand to 3 tabs: Data Sources, Agent Config, Upload |
| `useScenarios.ts` | Add `fetchIndexes()`, per-agent data source state, `applyConfig()` |
| `useInvestigation.ts` | Add `X-Graph` header from shared scenario context |
| `useTopology.ts` | Add `X-Graph` header from shared scenario context |
| `App.tsx` | Wrap in `ScenarioProvider` context that holds active graph + indexes |

**New files:**

| File | Purpose |
|------|---------|
| `src/context/ScenarioContext.tsx` | React context: `activeGraph`, `activeRunbooksIndex`, `activeTicketsIndex`, `activePrompts` |
| `src/hooks/usePrompts.ts` | CRUD hook for Cosmos prompt store |
| `src/components/DataSourcesTab.tsx` | Per-agent data source dropdowns |
| `src/components/AgentConfigTab.tsx` | Per-agent prompt selection + editor |
| `src/components/PromptEditor.tsx` | Markdown editor for prompt content |

### Infrastructure (Bicep) Changes

#### `infra/main.bicep` — new env vars for Container App

```bicep
// Add to container app env array:
{ name: 'AI_SEARCH_NAME', value: search.outputs.name }
{ name: 'STORAGE_ACCOUNT_NAME', value: storage.outputs.name }
{ name: 'AI_FOUNDRY_NAME', value: aiFoundry.outputs.foundryName }
{ name: 'EMBEDDING_MODEL', value: 'text-embedding-3-small' }
{ name: 'EMBEDDING_DIMENSIONS', value: '1536' }
```

These are needed by the new search indexer service in graph-query-api.
`AZURE_SUBSCRIPTION_ID` and `AZURE_RESOURCE_GROUP` were already added in
Phase 1.

#### `infra/main.bicep` — remove agent_ids.json baking

```bicep
// REMOVE: no longer needed if agent config is in Cosmos
{ name: 'AGENT_IDS_PATH', value: '/app/scripts/agent_ids.json' }
```

Replace with:
```bicep
{ name: 'AGENT_CONFIG_DATABASE', value: 'platform-config' }
{ name: 'AGENT_CONFIG_CONTAINER', value: 'agent-config' }
```

#### No new Bicep resources needed

- Cosmos NoSQL accounts already exist (Gremlin account + NoSQL account)
- The `platform-config` database and its containers (`prompts`, `agent-config`)
  are created on first access via `create_database_if_not_exists()`
- AI Search, Storage, and AI Foundry already provisioned
- All necessary RBAC roles already assigned

---

## Phase 2 Implementation Checklist (Ordered)

### Phase 2A: Data Source Bindings

Backend:
- [ ] Add `ScenarioContext` dataclass + `get_scenario_context` FastAPI dependency to `config.py`
- [ ] Refactor `CosmosDBGremlinBackend` to accept graph name as constructor param
- [ ] Create `get_backend_for_graph()` factory with per-graph client cache
- [ ] Update `router_graph.py` to accept `ScenarioContext` via `Depends()`
- [ ] Update `router_topology.py` to accept `ScenarioContext` via `Depends()`
- [ ] Update `router_telemetry.py` to accept `ScenarioContext`, use `ctx.telemetry_database`, remove hardcoded `VALID_CONTAINERS`
- [ ] Add `GET /query/indexes` endpoint to `router_ingest.py` (list AI Search indexes)
- [ ] Add `GET /api/config/datasources` endpoint to API
- [ ] Add `POST /api/config/datasources` endpoint to API (stores binding + triggers search agent re-provisioning)

Frontend:
- [ ] Create `ScenarioContext.tsx` provider with `activeGraph`, `activeRunbooksIndex`, `activeTicketsIndex`
- [ ] Wrap `App.tsx` in `ScenarioProvider`
- [ ] Update `useInvestigation.ts` to send `X-Graph` header
- [ ] Update `useTopology.ts` to send `X-Graph` header
- [ ] Create `DataSourcesTab.tsx` with 4 per-agent dropdowns
- [ ] Wire "Apply Changes" to `POST /api/config/datasources`

### Phase 2B: Prompts Database

Backend:
- [ ] Create `graph-query-api/router_prompts.py` with CRUD endpoints
- [ ] Create `platform-config` database + `prompts` container on first access
- [ ] Update `router_ingest.py` to extract + store prompts from uploaded archives
- [ ] Map prompt filenames to agent names (both old `foundry_*` and new canonical names)
- [ ] Auto-compose GraphExplorer prompt from `graph_explorer/` directory files

Frontend:
- [ ] Create `AgentConfigTab.tsx` with per-agent prompt dropdown
- [ ] Create `PromptEditor.tsx` with preview + edit modes
- [ ] Create `usePrompts.ts` hook for CRUD operations
- [ ] Add "Upload Prompts" button to Agent Config tab
- [ ] Add "+ New Prompt" button

### Phase 2C: Unified Apply Flow

Backend:
- [ ] Extract `provision_agents.py` logic into `scripts/agent_provisioner.py` (importable class)
- [ ] Refactor `provision_agents.py` CLI to be thin wrapper
- [ ] Add `POST /api/config/apply` endpoint that:
  - Fetches prompt content from Cosmos
  - Calls `AgentProvisioner.provision_all()` with selected prompts + indexes
  - Updates agent IDs in Cosmos `platform-config.agent-config`
  - Updates in-memory cache via `update_agent_config()`
  - Returns SSE progress stream
- [ ] Add `threading.Lock` around re-provisioning + 503 response while switching
- [ ] Refactor `orchestrator.py` to read agent config from Cosmos (fallback to file)
- [ ] Update `api/app/routers/agents.py` to reflect live config from Cosmos

Infrastructure:
- [ ] Add `AGENT_CONFIG_DATABASE` + `AGENT_CONFIG_CONTAINER` env vars to `main.bicep`
- [ ] Remove `AGENT_IDS_PATH` env var from `main.bicep`

### Phase 2D: Knowledge Indexing from Upload

Backend:
- [ ] Add `azure-storage-blob`, `azure-search-documents` to `graph-query-api/pyproject.toml`
- [ ] Create `graph-query-api/services/search_indexer.py` — adapted from `_indexer_common.py`
- [ ] Update `router_ingest.py` to upload `knowledge/runbooks/*.md` to blob `{scenario}-runbooks`
- [ ] Update `router_ingest.py` to upload `knowledge/tickets/*.txt` to blob `{scenario}-tickets`
- [ ] Update `router_ingest.py` to create AI Search indexer pipelines after blob upload
- [ ] Add SSE progress events for blob upload + indexer polling steps
- [ ] Return index names in upload completion event
- [ ] Add `AI_SEARCH_NAME`, `STORAGE_ACCOUNT_NAME`, `AI_FOUNDRY_NAME`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` env vars to `main.bicep`

### Phase 2E: Cleanup & Deprecation

- [ ] Move deprecated files:
  ```bash
  mkdir -p deprecated/scripts/cosmos
  git mv scripts/create_runbook_indexer.py deprecated/scripts/
  git mv scripts/create_tickets_indexer.py deprecated/scripts/
  git mv scripts/_indexer_common.py deprecated/scripts/
  git mv scripts/cosmos/provision_cosmos_gremlin.py deprecated/scripts/cosmos/
  git mv scripts/cosmos/provision_cosmos_telemetry.py deprecated/scripts/cosmos/
  git mv data/shared_prompts/ deprecated/
  ```
- [ ] Update `deploy.sh`:
  - Step 4 → informational message (indexes created on scenario upload)
  - Step 7 → informational message (agents configured via UI Settings)
  - Remove Step 7b (container redeploy for agent_ids.json)
- [ ] Update `hooks/postprovision.sh`:
  - Remove blob upload sections 1, 2, 2b
  - Keep config population (sections 3-5)
- [ ] Update `Dockerfile`:
  - Remove `COPY scripts/agent_ids.json*` (agent config in Cosmos)
  - Add `COPY graph-query-api/services/ /app/graph-query-api/services/` (if separate dir)
- [ ] Update `README.md` and `ARCHITECTURE.md` to reflect Phase 2 changes
- [ ] Remove backwards-compat symlinks (`data/prompts`, `data/network`, etc.)
  if no longer needed after Cosmos-backed prompts + UI-only data loading
- [ ] Run full integration test: fresh deploy → UI upload → configure agents → investigate
