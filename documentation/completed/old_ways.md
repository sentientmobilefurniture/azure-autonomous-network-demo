# The Old Ways: Hardcoded Scenario & Script-Provisioned Demo

> **Implementation Plan — v13**
> The UI is an **investigation playground** and **observability surface** — showcasing a single excellent scenario end-to-end. All scenario design, data provisioning, and agent provisioning are handled by external CLI scripts. The UI contains **zero** platform management, scenario management, or provisioning capabilities.

---

## 1. Executive Summary

The current system is a **multi-scenario, UI-driven, runtime-configurable platform** where users upload tarballs, switch scenarios, and provision Fabric resources through the web UI. Cosmos DB stores scenarios, configs, prompts, upload job status, and Fabric connections. This is the fabricdemo architecture — the cosmosdemo follows a similar pattern but uses Cosmos Gremlin for graph queries and Cosmos NoSQL for telemetry instead of Fabric.

We are returning to **The Old Ways**: A hardcoded demo specialized for a single domain (telco-noc), provisioned entirely by CLI scripts at deploy time, where the UI is purely an **investigation playground** and **observability surface** — not a platform administration tool. Cosmos DB will be used **only for interactions** (investigation history).

This is a significant simplification that touches ~40 files across the stack.

### What We Keep (Stable Core)

The investigation and observability capabilities are the product — everything else is scaffolding:

| Capability | Components | Status |
|-----------|------------|--------|
| **Multi-agent investigation** | `orchestrator.py`, SSE event protocol, `useInvestigation.ts`, `AlertInput`, `InvestigationPanel` | **Stable — preserve exactly** |
| **Agent topology display** | `AgentBar`, `AgentCard`, `/api/agents`, `agent_ids.py` (mtime-cached) | **Stable** |
| **Real-time log streaming** | `LogBroadcaster`, dual SSE streams (general + data-ops), `LogStream`, `TabbedLogStream`, `TerminalPanel` | **Stable** |
| **Graph topology visualization** | `GraphTopologyViewer`, `GraphCanvas`, force-graph-2d, `useTopology`, `useNodeColor`, `usePausableSimulation` | **Stable** |
| **Resource/agent-flow graph** | `ResourceVisualizer`, `ResourceCanvas`, `_build_resource_graph()` | **Stable** (needs config fetch path change) |
| **Data source health monitoring** | `DataSourceBar`, `DataSourceCard`, `router_health.py` | **Stable** (needs config fetch path change) |
| **Interaction history** | `InteractionSidebar`, `useInteractions`, `router_interactions.py`, Cosmos `interactions/interactions` | **Stable** |
| **Diagnosis rendering** | `DiagnosisPanel`, markdown rendering, copy button, run metadata | **Stable** |
| **Stub/fallback mode** | When agents aren't provisioned, API returns simulated responses | **Stable — essential for dev** |

---

## 2. Architectural Principles

| Principle | Description |
|-----------|-------------|
| **Single scenario, hardcoded** | `telco-noc` is the only scenario. No switching, no CRUD, no dynamic discovery. |
| **Script-provisioned** | All data (Fabric Lakehouse, Eventhouse, Ontology, Cosmos telemetry, AI Search indexes, AI Foundry agents) are provisioned by running Python scripts at deploy time. |
| **Cosmos = interactions only** | Cosmos DB NoSQL stores investigation history. No scenarios, configs, prompts, upload jobs, or Fabric connections in Cosmos. |
| **No tarballs** | Data lives as raw CSV/MD/TXT files in the repo. Scripts read them directly. |
| **Fabric connection via env vars** | `FABRIC_WORKSPACE_ID` + `FABRIC_GRAPH_MODEL_ID` + `EVENTHOUSE_QUERY_URI` + `FABRIC_KQL_DB_NAME` are set in `azure_config.env` by provisioning scripts. No runtime connection management. |
| **Prompts from disk** | Agent prompts are read from `data/scenarios/telco-noc/data/prompts/` at provisioning time. Not stored in Cosmos. |
| **Observability preserved** | All runtime observability surfaces (log streaming, health checks, agent bar, data source bar, resource graph) remain fully functional. |
| **SSE event protocol frozen** | The orchestrator's SSE event names (`run_start`, `step_thinking`, `step_start`, `step_complete`, `message`, `run_complete`, `error`) are a contract with the frontend — not to be changed. |

---

## 3. What Gets Removed

### 3.1 Frontend — Files to Delete (12 files)

| File | Reason |
|------|--------|
| `src/components/ScenarioChip.tsx` | No scenario switching |
| `src/components/ScenarioManagerModal.tsx` | No scenario CRUD |
| `src/components/AddScenarioModal.tsx` | No tarball uploads |
| `src/components/ScenarioInfoPanel.tsx` | Hardcode info if needed |
| `src/components/ScenarioStatusPanel.tsx` | No upload jobs |
| `src/components/EmptyState.tsx` | Always has a scenario |
| `src/components/ProvisioningBanner.tsx` | No runtime provisioning |
| `src/components/FabricConnectionPanel.tsx` | Connection via env vars |
| `src/hooks/useScenarios.ts` | No scenario state |
| `src/hooks/useScenarioUpload.ts` | No uploads |
| `src/hooks/useFabricDiscovery.ts` | No runtime Fabric discovery |
| `src/utils/triggerProvisioning.ts` | No runtime agent provisioning |

### 3.2 Frontend — Files to Simplify

| File | Changes |
|------|---------|
| `src/context/ScenarioContext.tsx` | **Delete.** All consumers switch to importing from `src/config.ts` (§4.6). No `savedScenarios`, no `refreshScenarios`, no localStorage persistence, no provisioning status. |
| `src/components/Header.tsx` | Remove `ScenarioChip`, `FabricConnectionPanel`, `UploadStatusBadge` (import + rendering + state). Keep title, ServiceHealthSummary, AgentBar, DataSourceBar. |
| `src/App.tsx` | Remove `AddScenarioModal`, `EmptyState` guards, `info` tab, `addModalOpen` state, scenario change effects, `useScenarios` hook usage. The `investigate` tab renders directly without scenario guards. Scenario description and example questions are available from `config.ts` if needed inline. |
| `src/types/index.ts` | Remove `SavedScenario`, `SlotKey`, `ScenarioUploadSlot`, `FabricItem` types. Keep `Interaction`, `Step`, etc. |
| `src/utils/sseStream.ts` | **Keep** — used by `useInvestigation.ts` for alert SSE streaming (via `@microsoft/fetch-event-source`). Also used by `triggerProvisioning.ts` (deleted), but the investigation flow depends on it. |
| `src/hooks/useInteractions.ts` | Simplify: remove scenario parameter from queries, use hardcoded scenario name `"telco-noc"` as partition key. |
| `src/hooks/useTopology.ts` | Simplify: remove `getQueryHeaders()` dependency. Stop sending `X-Graph` header entirely — the backend now returns a fixed context regardless (§12.4). |
| `src/hooks/useNodeColor.ts` | **Keep logic, update source** — 3-tier priority (userOverride → scenarioNodeColors → autoColor) is preserved. After `ScenarioContext` is deleted, source `scenarioNodeColors` from `config.ts` (§4.6) instead. If absent, auto-color fallback handles it. |
| `src/hooks/useResourceGraph.ts` | Simplify: remove `X-Scenario` header and `provisioningStatus` re-fetch trigger. Fetch once on mount. |
| `src/components/graph/*` (6 files) | **Keep unchanged** — `GraphCanvas`, `GraphToolbar`, `GraphTooltip`, `GraphContextMenu`, `ColorWheelPopover`, `graphConstants.ts` are all scenario-agnostic (take data as props). |
| `src/components/resource/*` (4 files) | **Keep unchanged** — `ResourceCanvas`, `ResourceToolbar`, `ResourceTooltip`, `resourceConstants.ts` are scenario-agnostic. |

### 3.3 API (`api/app/`) — Files to Delete (2 files)

| File | Reason |
|------|--------|
| `routers/upload_jobs.py` | No tarball uploads |
| `routers/fabric_provision.py` | Fabric provisioned by scripts, not API |

### 3.4 API — Files to Simplify

| File | Changes |
|------|---------|
| `routers/config.py` | **Delete `POST /api/config/apply` entirely** — it triggers agent provisioning from the UI, which directly contradicts "no platform management in UI." **Keep** `GET /api/config/current` (reads from `agent_ids.json` or env-var fallbacks, self-contained) and `GET /api/config/resources` (rewrite to use hardcoded config dict instead of fetching from `/query/scenario/config`). Remove SSE provisioning flow, prompt fetching from Cosmos, dynamic agent binding. |
| `main.py` | Remove router imports/mounts for `upload_jobs`, `fabric_provision`. |

### 3.5 Graph Query API — Files to Delete (9 files)

| File | Reason |
|------|--------|
| `router_scenarios.py` | No scenario CRUD |
| `router_prompts.py` | No Cosmos prompt store |
| `router_docs.py` | Only used for upload-job persistence |
| `router_fabric_discovery.py` | No runtime Fabric discovery |
| `router_fabric_connections.py` | No runtime connection management |
| `config_store.py` | No dynamic scenario configs in Cosmos |
| `config_validator.py` | No config validation needed |
| `ingest/manifest.py` | No tarball processing |
| `ingest/prompt_ingest.py` | No prompt uploads |

### 3.6 Graph Query API — Files to Simplify

| File | Changes |
|------|---------|
| `config.py` | Remove `ScenarioContext` dynamic resolution. Remove `config_store` dependency. Hardcode: `graph_name = "telco-noc-topology"`, `backend_type = os.getenv("GRAPH_BACKEND", "fabric-gql")`, `fabric_workspace_id/graph_model_id/eventhouse_query_uri/kql_db_name` from env vars. `get_scenario_context()` returns a fixed context — no `X-Graph` header parsing, no config store lookup. |
| `router_graph.py` | Remove `X-Graph` header dependency. Use hardcoded context. |
| `router_telemetry.py` | Remove `X-Graph` header dependency. Use hardcoded context. |
| `router_topology.py` | Remove `X-Graph` header dependency. Use hardcoded graph name. |
| `router_interactions.py` | Hardcode `scenario = "telco-noc"` as default. Keep functionality. |
| `router_health.py` | Change `scenario` query parameter from required (`Query(...)`) to optional with default `"telco-noc"`. Replace `fetch_scenario_config()` call (from deleted `config_store.py`) with hardcoded `DATA_SOURCES` dict (see §12.1). |
| `main.py` | Remove router imports/mounts for scenarios, prompts, docs, fabric_discovery, fabric_connections, and ingest routers that are deleted. Keep inline SSE log-streaming endpoints (`GET /query/logs`, `GET /query/logs/data-ops`) unchanged. |
| `ingest/__init__.py` | **Delete.** The entire `ingest/` package is replaced by standalone provisioning scripts (§4.1). |
| `ingest/graph_ingest.py` | **Delete** — graph data loaded by `provision_lakehouse.py` + `provision_ontology.py`. |
| `ingest/telemetry_ingest.py` | Delete — already a stub, telemetry loaded by `provision_eventhouse.py` or `provision_cosmos_telemetry.py`. |
| `ingest/knowledge_ingest.py` | **Delete** — runbooks/tickets indexed by `provision_search_index.py` script. |

### 3.7 Cosmos DB Containers to Stop Using

| Database | Container | Current Use | After |
|----------|-----------|-------------|-------|
| `scenarios` | `scenarios` | Scenario metadata | **Delete** |
| `scenarios` | `configs` | Parsed scenario.yaml | **Delete** |
| `scenarios` | `upload-jobs` | Background job status | **Delete** |
| `scenarios` | `fabric-connections` | Fabric workspace connections | **Delete** |
| `prompts` | `{scenario_name}` | Per-scenario agent prompts | **Delete** |
| `interactions` | `interactions` | Investigation history | **Keep** |

### 3.8 Data — Files to Delete

| Item | Reason |
|------|--------|
| All `.tar.gz` files in `data/scenarios/*/` | No tarballs |
| `data/generate_all.sh` (the tarball generator) | No tarballs |
| `data/validate_scenario.py` | No multi-scenario validation |

### 3.9 Other Removals

| Item | Reason |
|------|--------|
| `custom_skills/graph-data-scenarios/` | No scenario generation needed |
| Multi-scenario support in `scripts/agent_provisioner.py` | Simplify to single hardcoded scenario |

---

## 4. What Gets Added / Updated

### 4.1 Provisioning Scripts (`scripts/`)

The new scripts directory adapts the reference implementation from `fabric_implementation_references/scripts/fabric/` into a clean, ordered provisioning pipeline. Each script is standalone and idempotent.

#### Script Inventory

| # | Script | Purpose | Source / Basis |
|---|--------|---------|----------------|
| 1 | `scripts/fabric/_config.py` | Shared Fabric API config, auth, env helpers | Port from `fabric_implementation_references/scripts/fabric/_config.py` |
| 2 | `scripts/fabric/provision_lakehouse.py` | Create workspace → attach capacity → create Lakehouse → upload CSVs → load delta tables | Port from reference `provision_lakehouse.py` |
| 3 | `scripts/fabric/provision_eventhouse.py` | Create Eventhouse → KQL tables → ingest telemetry CSVs | Port from reference `provision_eventhouse.py` |
| 4 | `scripts/fabric/provision_ontology.py` | Create Ontology + Graph Model with entity types, relationships, bindings | Port from reference `provision_ontology.py` |
| 5 | `scripts/fabric/populate_fabric_config.py` | Auto-discover Fabric resource IDs → write to `azure_config.env` | Port from reference `populate_fabric_config.py` |
| 6 | `scripts/fabric/assign_fabric_role.py` | Grant Container App MI `Contributor` on Fabric workspace | Port from reference `assign_fabric_role.py` |
| 7 | `scripts/fabric/collect_fabric_agents.py` | Interactive discovery of Fabric Data Agent artifact IDs | Port from reference `collect_fabric_agents.py` |
| 8 | `scripts/provision_cosmos.py` | **NEW (generalized)**. Provisions Cosmos DB NoSQL: create database, create containers with partition keys, bulk-load CSV data. Generalizes `create_cosmos_telemetry.py` to work with any container/CSV/partition key config. For the telco-noc demo, loads `AlertStream` and `LinkTelemetry` into Cosmos NoSQL. |
| 9 | `scripts/provision_search_index.py` | **NEW (generalized)**. Creates AI Search pipeline: data source → index (with vector search) → skillset (chunking + embedding) → indexer. Generalizes `create_runbook_indexer.py` to accept config for index name, blob container, embedding model, etc. For the telco-noc demo, creates `runbooks-index` and `tickets-index`. |
| 10 | `scripts/provision_agents.py` | Provisions all 5 AI Foundry agents. Simplify from current `agent_provisioner.py` — remove multi-backend logic, hardcode to `fabric-gql`. Read prompts from disk. | Adapt from current `scripts/agent_provisioner.py` / reference `provision_agents.py` |

#### Script Design Principles

- **Config via `azure_config.env`**: Each script reads from and writes back to this file.
- **Idempotent**: Find-then-create pattern. Safe to re-run.
- **DefaultAzureCredential everywhere**: No keys, no secrets.
- **Console output with status indicators**: `✓` success, `✗` failure, `⚠` warning.
- **Data paths relative to repo**: Scripts reference `data/scenarios/telco-noc/data/` directly. No tarballs.
- **Generalized for script reuse** (not runtime dynamism): `provision_cosmos.py` and `provision_search_index.py` are parameterized — they work for any container/index config, not just telemetry or runbooks. This makes them reusable by operators if the domain changes. The app itself remains hardcoded to telco-noc.

### 4.2 `provision_cosmos.py` — Generalized Cosmos Provisioner

Extends the pattern from `create_cosmos_telemetry.py`:

```
Usage: python scripts/provision_cosmos.py [--no-clear] [--from-blob]

Config (from azure_config.env):
  COSMOS_NOSQL_ENDPOINT    — Cosmos account endpoint
  COSMOS_NOSQL_DATABASE    — Target database name (default: telemetrydb)

Hardcoded for telco-noc:
  Container definitions:
    - AlertStream:    partition=/SourceNodeType, csv=data/scenarios/telco-noc/data/telemetry/AlertStream.csv
    - LinkTelemetry:  partition=/LinkId,         csv=data/scenarios/telco-noc/data/telemetry/LinkTelemetry.csv
```

Key features:
- Async bulk upsert with semaphore concurrency control (50 parallel)
- Progress reporting (batch size 500)
- Type coercion for numeric fields  
- Optional `--from-blob` to read CSVs from Azure Blob Storage
- Optional `--no-clear` to skip clearing existing data
- Creates database + containers if they don't exist

### 4.3 `provision_search_index.py` — Generalized Search Index Provisioner

Extends the pattern from `create_runbook_indexer.py`:

```
Usage: python scripts/provision_search_index.py [--upload-files]

Config (from azure_config.env):
  AI_SEARCH_NAME           — AI Search service name
  STORAGE_ACCOUNT_NAME     — Storage account for blob data source
  EMBEDDING_MODEL          — e.g. text-embedding-3-small
  EMBEDDING_DIMENSIONS     — e.g. 1536
  AI_FOUNDRY_NAME          — AI Foundry for vectorizer

Hardcoded for telco-noc:
  Index definitions:
    - runbooks-index:  container=runbooks,  files=data/scenarios/telco-noc/data/knowledge/runbooks/*.md
    - tickets-index:   container=tickets,   files=data/scenarios/telco-noc/data/knowledge/tickets/*.txt
```

Key features:
- Creates blob data source (connection via ARM resource ID)
- Creates index with HNSW vector search profile + Azure OpenAI vectorizer
- Creates skillset with SplitSkill (chunking) + AzureOpenAIEmbeddingSkill
- Creates indexer with index projections
- `--upload-files` flag: uploads local files to blob containers before indexing
- Polls indexer status until complete
- Idempotent: deletes and recreates if index already exists

### 4.4 Deploy Script Updates (`deploy.sh`)

The current deploy.sh has steps 0–4, 6–7 (step 5 was removed; 8–9 never existed). It also has vestigial CLI flags (`--skip-index`, `--skip-data`, `--skip-agents`) that are parsed but never checked in the script body. The summary block still prints tarball/upload instructions referring to the "UI Settings page."

Updates needed:
1. **Remove vestigial flags**: Delete `--skip-index`, `--skip-data`, `--skip-agents` from the argument parser.
2. **Remove tarball/upload instructions**: Delete the summary block text about `tar czf telco-noc.tar.gz` and "upload via UI Settings page."
3. **Remove header comment**: Delete "Scenario-specific resources are created at runtime when a scenario is uploaded via the UI Settings page."
4. **Add provisioning steps** (optional, gated by flags):

```
Step 0: Prerequisites (unchanged)
Step 1: Environment setup (unchanged)
Step 2: Config generation (unchanged)
Step 3: azd up — infra provision (unchanged)
Step 4: Fabric RBAC (unchanged — assign_fabric_role.py)
Step 5: NEW — Fabric Provisioning (optional, --provision-fabric flag)
  5a: provision_lakehouse.py
  5b: provision_eventhouse.py
  5c: provision_ontology.py
  5d: populate_fabric_config.py
Step 6: NEW — Data Provisioning (optional, --provision-data flag)
  6a: provision_cosmos.py (telemetry to Cosmos NoSQL)
  6b: provision_search_index.py --upload-files (runbooks + tickets)
Step 7: NEW — Agent Provisioning (optional, --provision-agents flag)
  7a: provision_agents.py
Step 8: Health check (was step 6)
Step 9: Local dev (was step 7)
```

New flags: `--provision-fabric`, `--provision-data`, `--provision-agents`, `--provision-all`.

**Note:** The current step 4 (Fabric workspace RBAC) already uses `az account get-access-token --resource https://api.fabric.microsoft.com` and POSTs role assignments via REST. This logic stays but should reference `assign_fabric_role.py` for consistency.

### 4.5 Post-Provision Hook Updates (`hooks/postprovision.sh`)

Update to:
1. **Remove dead code**: Delete the `upload_with_retry()` function (~40 lines) which exists but is never called.
2. **Remove "UI Settings page" comment**: Delete "Skipping blob uploads — data is loaded via UI Settings page."
3. Upload runbooks and tickets to blob storage (restore from reference)
4. Populate `azure_config.env` with all Fabric IDs discovered by provisioning scripts
5. Optionally run `provision_search_index.py` and `provision_agents.py`
6. **Fix `GRAPH_QUERY_API_PRINCIPAL_ID`**: Either add this var to postprovision output (set to `APP_PRINCIPAL_ID`) or remove it from the template — currently the template has it but postprovision doesn’t write it.

### 4.5b Pre-Provision Hook Updates (`hooks/preprovision.sh`)

1. **Remove** `DEFAULT_SCENARIO` and `LOADED_SCENARIOS` from the azd env sync. These vars are synced to azd env but never consumed by any Bicep parameter — they are dead variables.
2. Keep syncing `AZURE_LOCATION`, `GPT_CAPACITY_1K_TPM`, `GRAPH_BACKEND`, `AZURE_PRINCIPAL_ID`.

### 4.6 Frontend — New Hardcoded Config

Replace `ScenarioContext` with a simple config module:

```typescript
// src/config.ts
export const SCENARIO = {
  name: "telco-noc",
  displayName: "Australian Telco NOC",
  graph: "telco-noc-topology",
  runbooksIndex: "telco-noc-runbooks-index",
  ticketsIndex: "telco-noc-tickets-index",
  graphStyles: {
    nodeColors: { CoreRouter: "#3b82f6", AggSwitch: "#8b5cf6", ... },
    nodeSizes: { CoreRouter: 8, AggSwitch: 6, ... },
    nodeIcons: { CoreRouter: "router", ... },
  },
  description: "AI-powered NOC investigator for an Australian telecommunications provider...",
  exampleQuestions: [
    "There is a fibre cut on the Sydney-Melbourne corridor. What services are affected?",
    ...
  ],
};
```

### 4.7 Frontend — Simplified Header

The header becomes:
- **Left**: Brand icon + "AI Incident Investigator" + domain badge ("Telco NOC")
- **Right**: `ServiceHealthSummary` only
- **Sub-bars**: `AgentBar`, `DataSourceBar` (keep — shows live agent/data source status)
- **Removed**: ScenarioChip, Fabric button, UploadStatusBadge, FabricConnectionPanel, ProvisioningBanner

### 4.8 Frontend — Simplified App Shell

- Remove `info` tab (or inline scenario info into the main view)
- Remove empty state guards — the app always has a scenario
- Remove `AddScenarioModal`
- The `investigate` tab renders directly (no scenario checks)
- `resources` tab can stay (shows agent topology graph)

### 4.9 Graph Query API — Simplified Config

```python
# config.py — simplified
GRAPH_BACKEND = os.getenv("GRAPH_BACKEND", "fabric-gql")
FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID")
FABRIC_GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID")
EVENTHOUSE_QUERY_URI = os.getenv("EVENTHOUSE_QUERY_URI")
FABRIC_KQL_DB_NAME = os.getenv("FABRIC_KQL_DB_NAME")
DEFAULT_GRAPH = "telco-noc-topology"

@dataclass
class ScenarioContext:
    graph_name: str = DEFAULT_GRAPH
    backend_type: str = GRAPH_BACKEND
    fabric_workspace_id: str = FABRIC_WORKSPACE_ID
    fabric_graph_model_id: str = FABRIC_GRAPH_MODEL_ID

def get_scenario_context():
    return ScenarioContext()  # Always returns the same hardcoded context
```

### 4.10 Stores — Simplify

The `stores/` package remains for Cosmos interaction storage:
- `cosmos_nosql.py` — keep, used by `router_interactions.py`
- `mock_store.py` — keep for local dev/testing
- Remove any scenario/config/prompt store logic

---

## 5. What Stays Unchanged

| Component | Reason |
|-----------|--------|
| `router_interactions.py` | Interactions are still stored in Cosmos (the one valid Cosmos use case) |
| `router_graph.py` | Still dispatches graph queries (just with fixed context) |
| `router_telemetry.py` | Still dispatches KQL queries (just with fixed context) |
| `router_topology.py` | Still returns graph visualization data (just with fixed graph name) |
| `backends/fabric.py` | Fabric GQL backend unchanged |
| `backends/fabric_kql.py` | Fabric KQL backend unchanged |
| `backends/mock.py` | Mock backend unchanged (for local dev) |
| `routers/alert.py` | Alert submission + orchestrator invocation unchanged |
| `routers/agents.py` | Agent listing unchanged |
| `routers/logs.py` | SSE log streaming unchanged |
| `orchestrator.py` | Agent orchestration unchanged |
| `agent_ids.py` | Agent ID persistence unchanged |
| Infrastructure (Bicep) | Same resources provisioned — VNet, AI Foundry, AI Search, Storage, Cosmos, Container Apps |
| `InvestigationPanel`, `DiagnosisPanel`, etc. | Core investigation UI unchanged |
| `InteractionSidebar`, `useInteractions` | Interaction history UI unchanged |
| `GraphTopologyViewer` | Graph visualization unchanged |
| `MetricsBar`, `LogStream`, `TabbedLogStream` | Telemetry/log UI unchanged |
| `custom_skills/azure-container-neo4j-py` | Reference material, unchanged |
| `custom_skills/react-force-graph-2d` | Reference material, unchanged |
| Data generation scripts (`data/scenarios/telco-noc/scripts/`) | Keep for re-generating data if needed |

---

## 6. File-Level Change Summary

### 6.1 Files to Delete (~25 files)

```
# Frontend (12)
frontend/src/components/ScenarioChip.tsx
frontend/src/components/ScenarioManagerModal.tsx
frontend/src/components/AddScenarioModal.tsx
frontend/src/components/ScenarioInfoPanel.tsx
frontend/src/components/ScenarioStatusPanel.tsx
frontend/src/components/EmptyState.tsx
frontend/src/components/ProvisioningBanner.tsx
frontend/src/components/FabricConnectionPanel.tsx
frontend/src/hooks/useScenarios.ts
frontend/src/hooks/useScenarioUpload.ts
frontend/src/hooks/useFabricDiscovery.ts
frontend/src/utils/triggerProvisioning.ts

# API (2)
api/app/routers/upload_jobs.py
api/app/routers/fabric_provision.py

# Graph Query API (9+)
graph-query-api/router_scenarios.py
graph-query-api/router_prompts.py
graph-query-api/router_docs.py
graph-query-api/router_fabric_discovery.py
graph-query-api/router_fabric_connections.py
graph-query-api/config_store.py
graph-query-api/config_validator.py
graph-query-api/ingest/manifest.py
graph-query-api/ingest/prompt_ingest.py
graph-query-api/ingest/graph_ingest.py        # If fully replaced by scripts
graph-query-api/ingest/telemetry_ingest.py     # Already a stub
graph-query-api/ingest/knowledge_ingest.py     # If fully replaced by scripts

# Data
data/generate_all.sh                           # Tarball generator
data/validate_scenario.py                      # Multi-scenario validator
data/scenarios/telco-noc/*.tar.gz              # All tarballs (5 files)
data/scenarios/telco-backbone/                 # Remove non-primary scenarios
data/scenarios/telco-noc-fabric/               # Remove non-primary scenarios
data/scenarios/hello-world/                    # Remove non-primary scenarios

# Custom skills
custom_skills/graph-data-scenarios/            # No scenario generation
```

### 6.2 Files to Modify (~20 files)

```
# Frontend
frontend/src/App.tsx                           # Remove scenario guards, modals, info tab
frontend/src/components/Header.tsx             # Strip scenario/fabric/upload UI (ScenarioChip, FabricConnectionPanel, UploadStatusBadge, ProvisioningBanner, ScenarioStatusPanel)
frontend/src/context/ScenarioContext.tsx        # Replace with hardcoded config (or delete + new file)
frontend/src/types/index.ts                    # Remove scenario types
frontend/src/hooks/useInteractions.ts          # Hardcode scenario name

# API
api/app/main.py                                # Remove deleted router imports (upload_jobs, fabric_provision)
api/app/routers/config.py                      # Delete POST /apply, keep GET /current + /resources with hardcoded config

# Graph Query API
graph-query-api/main.py                        # Remove deleted router imports (~6 routers + ingest). Keep inline /query/logs SSE endpoints.
graph-query-api/config.py                      # Simplify to hardcoded context
graph-query-api/router_graph.py                # Remove X-Graph header dependency
graph-query-api/router_telemetry.py            # Remove X-Graph header dependency
graph-query-api/router_topology.py             # Remove X-Graph header dependency
graph-query-api/router_interactions.py         # Hardcode scenario partition
graph-query-api/router_health.py               # Scenario param → optional default "telco-noc", replace config_store fetch with hardcoded DATA_SOURCES

# Container/Deploy
Dockerfile                                     # Remove COPY graph-query-api/ingest/ and COPY data/scenarios/
nginx.conf                                     # Clean up client_max_body_size upload comment
deploy.sh                                      # Add provisioning steps, remove vestigial flags + tarball instructions
hooks/postprovision.sh                         # Remove dead upload_with_retry(), add data upload + provisioning
hooks/preprovision.sh                          # Remove DEFAULT_SCENARIO/LOADED_SCENARIOS syncing
azure_config.env.template                      # Clean up, fix GRAPH_QUERY_API_PRINCIPAL_ID, add Fabric fields, remove "UI Settings page" comment
```

### 6.3 Files to Add (~12 files)

```
# Provisioning scripts
scripts/fabric/_config.py                      # Port from reference
scripts/fabric/provision_lakehouse.py          # Port from reference
scripts/fabric/provision_eventhouse.py         # Port from reference
scripts/fabric/provision_ontology.py           # Port from reference
scripts/fabric/populate_fabric_config.py       # Port from reference
scripts/fabric/assign_fabric_role.py           # Port from reference
scripts/fabric/collect_fabric_agents.py        # Port from reference
scripts/provision_cosmos.py                    # NEW generalized Cosmos provisioner
scripts/provision_search_index.py              # NEW generalized search index provisioner

# Prompts
data/scenarios/telco-noc/data/prompts/graph_explorer/language_gql.md  # NEW GQL syntax guide

# Frontend
frontend/src/config.ts                         # NEW hardcoded scenario config
```

---

## 7. Implementation Order

The implementation should proceed in phases to avoid breaking the app entirely during the transition.

### Phase 1: Add Provisioning Scripts (non-breaking)

1. Port `scripts/fabric/` directory from reference (7 files: `_config.py`, `provision_lakehouse.py`, `provision_eventhouse.py`, `provision_ontology.py`, `populate_fabric_config.py`, `assign_fabric_role.py`, `collect_fabric_agents.py`)
2. Create `scripts/provision_cosmos.py` — generalized from `create_cosmos_telemetry.py`
3. Create `scripts/provision_search_index.py` — generalized from `create_runbook_indexer.py`
4. Simplify `scripts/provision_agents.py` — remove multi-backend, hardcode to `fabric-gql`, read prompts from disk. Keep `provision_all()` path; delete `provision_from_config()` (§12.7).
5. Create `data/scenarios/telco-noc/data/prompts/graph_explorer/language_gql.md` — ISO GQL / Fabric GQL syntax guide for the GraphExplorer agent (gap identified in §15).
6. Test each script independently

### Phase 2: Strip Scenario Management from Graph Query API

> **Precondition:** Phase 1 complete (scripts exist as fallback provisioning path)
> **App state after:** Graph-query-api is simplified. Frontend health/data-source components still work because hidden dependencies are fixed in this phase.

1. Simplify `config.py` — hardcoded `ScenarioContext`, no config store
2. Delete `config_store.py`, `config_validator.py`
3. Delete `router_scenarios.py`, `router_prompts.py`, `router_docs.py`, `router_fabric_discovery.py`, `router_fabric_connections.py`
4. Delete `ingest/` package entirely
5. Update `main.py` — remove deleted router imports/mounts (scenarios, prompts, docs, fabric_discovery, fabric_connections, ingest). **Keep** inline `/query/logs` and `/query/logs/data-ops` SSE endpoints.
6. Simplify `router_graph.py`, `router_telemetry.py`, `router_topology.py` — remove `X-Graph` header dependency
7. Simplify `router_interactions.py` — hardcode scenario name
8. **Fix §12.1**: Update `router_health.py` — replace `fetch_scenario_config()` with hardcoded `DATA_SOURCES` dict. Change `scenario` param from required to optional with default `"telco-noc"`.
9. **Dockerfile**: Remove `COPY graph-query-api/ingest/ ./ingest/` line (ingest package deleted)

### Phase 3: Strip Scenario Management from API

> **Precondition:** Phase 2 complete (graph-query-api endpoints are stable)
> **App state after:** API is simplified. No provisioning endpoint in the app.

1. Delete `routers/upload_jobs.py`, `routers/fabric_provision.py`
2. **Delete `POST /api/config/apply`** from `routers/config.py` — this is the runtime provisioning endpoint that contradicts "no platform management in UI." Keep `GET /api/config/current` (reads `agent_ids.json`, self-contained) and `GET /api/config/resources`.
3. **Fix §12.2**: Rewrite `GET /api/config/resources` — replace `_fetch_from_graph_api("/query/scenario/config")` call with a hardcoded config dict (since `router_scenarios.py` no longer exists). `_build_resource_graph()` is a pure function and needs no changes.
4. Update `main.py` — remove deleted router imports/mounts for `upload_jobs`, `fabric_provision`

### Phase 4: Strip Scenario Management from Frontend

> **Precondition:** Phases 2+3 complete (backend endpoints are stable)
> **App state after:** UI is a pure investigation playground. No scenario management anywhere.

1. Create `src/config.ts` with hardcoded scenario constants
2. Delete 12 scenario-related component/hook/util files
3. Rewrite `Header.tsx` — remove `ScenarioChip`, `FabricConnectionPanel`, `UploadStatusBadge`, `ProvisioningBanner`, `ScenarioStatusPanel` imports + rendering. Keep title, `ServiceHealthSummary`, `ServiceHealthPopover`, `AgentBar`, `DataSourceBar`.
4. Rewrite `App.tsx` — remove EmptyState guards, AddScenarioModal, info tab, scenario effects
5. Delete `ScenarioContext.tsx`. All consumers now import from `config.ts` (§4.6). Update `useNodeColor.ts` to source `scenarioNodeColors` from `config.ts`.
6. Simplify `useInteractions.ts` — hardcode scenario
7. Clean up `types/index.ts` — remove scenario types

### Phase 5: Clean Up Data, Config & Infrastructure

> **Precondition:** Phases 2–4 complete (app is fully simplified)
> **This phase is non-breaking — cleanup only.**

1. Delete all `.tar.gz` files from `data/scenarios/`
2. Delete `data/generate_all.sh`, `data/validate_scenario.py`
3. Delete non-primary scenarios (`telco-backbone`, `telco-noc-fabric`, `hello-world`)
4. Delete `custom_skills/graph-data-scenarios/`
5. **azure_config.env.template**: Remove "UI Settings page" comment. Fix `GRAPH_QUERY_API_PRINCIPAL_ID` (align with postprovision's `APP_PRINCIPAL_ID`). Add full Fabric provisioning vars (uncomment). Remove commented-out vars that scripts now handle.
6. **deploy.sh**: Add provisioning steps 5–7. Remove vestigial `--skip-index`/`--skip-data`/`--skip-agents` flags. Remove summary block tarball/upload instructions. Update header comments.
7. **hooks/postprovision.sh**: Remove dead `upload_with_retry()` function. Restore data upload logic. Remove "UI Settings page" comment.
8. **hooks/preprovision.sh**: Remove `DEFAULT_SCENARIO` and `LOADED_SCENARIOS` syncing (dead vars — no Bicep parameter consumes them).
9. **Dockerfile**: Remove `COPY data/scenarios/ /app/data/scenarios/` line (config hardcoded in Python, prompts read at provisioning time not runtime).
10. **nginx.conf**: Update `client_max_body_size` comment (no more scenario uploads; 100m may be excessive, but keep for future flexibility).
11. **.dockerignore**: Clean up `data/scenarios/*/data/*` exclusion patterns if the `COPY data/scenarios/` line is removed.
12. **Bicep/Infra** (see §16):
    - `cosmos-gremlin.bicep` → Rename to `cosmos-nosql.bicep`. Remove the **Gremlin account entirely** (fabricdemo doesn't use Cosmos Gremlin — it uses Fabric GQL). Remove `telemetry`, `scenarios`, `prompts` databases from the NoSQL account. Keep only `interactions` database with `interactions` container.
    - `main.bicep` → Update module reference from `cosmos-gremlin.bicep` to `cosmos-nosql.bicep`. **Note:** `defaultScenario` and `loadedScenarios` parameters do NOT exist in `main.bicep` despite `preprovision.sh` syncing them — no Bicep changes needed for these.

### Phase 6: Test & Validate

1. Run full provisioning pipeline (scripts) against a fresh Azure environment
2. Verify the frontend renders without scenario management UI
3. Verify graph queries work with hardcoded config
4. Verify telemetry queries work
5. Verify interactions are saved/loaded from Cosmos
6. Verify agent orchestration works end-to-end
7. Run `azd up` from scratch and verify postprovision hooks work

---

## 8. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking changes during transition | Phase implementation — each phase is independently deployable |
| Loss of multi-scenario capability | This is intentional. The old approach is simpler and more reliable for demos. If needed again, git history preserves everything. |
| Fabric provisioning script failures | Scripts are idempotent with find-then-create logic. Can be re-run safely. |
| Cosmos data migration | No migration needed — we're removing Cosmos usage for scenarios/prompts/configs, not migrating data. Interactions container stays as-is. |
| Frontend breaks during component deletion | Delete components bottom-up: hooks/utils first, then components, then context/types. Fix imports at each step. |

---

## 9. Success Criteria

- [ ] `deploy.sh --provision-all` provisions everything from scratch (Fabric + Cosmos + Search + Agents)
- [ ] Frontend loads without any scenario management UI
- [ ] Submitting an alert triggers full multi-agent investigation
- [ ] Graph topology renders correctly from Fabric GQL
- [ ] Telemetry queries return data from Fabric Eventhouse
- [ ] Interactions are saved to and loaded from Cosmos DB
- [ ] No references to tarballs, scenario switching, or dynamic provisioning remain in the codebase
- [ ] `azure_config.env.template` documents all required configuration
- [ ] README is updated to reflect the new provisioning workflow

---

## 10. Dependency Map

```
deploy.sh
  └─→ azd up (infra/main.bicep)
       └─→ postprovision.sh
            ├─→ Upload runbooks/tickets to blob
            └─→ Populate azure_config.env

scripts/fabric/provision_lakehouse.py    ─→ Workspace + Lakehouse + delta tables
scripts/fabric/provision_eventhouse.py   ─→ Eventhouse + KQL tables + telemetry
scripts/fabric/provision_ontology.py     ─→ Ontology + Graph Model
scripts/fabric/populate_fabric_config.py ─→ Auto-discover IDs → azure_config.env
scripts/fabric/assign_fabric_role.py     ─→ RBAC for Container App MI
scripts/provision_cosmos.py              ─→ Cosmos NoSQL containers + telemetry data
scripts/provision_search_index.py        ─→ AI Search indexes (runbooks + tickets)
scripts/provision_agents.py              ─→ 5 AI Foundry agents

Runtime:
  Container App
    ├─→ nginx (:80)
    ├─→ API (:8000)
    │    ├─→ /api/alert          → orchestrator → AI Foundry agents
    │    ├─→ /api/agents         → agent_ids.json
    │    └─→ /api/logs           → SSE log stream
    └─→ graph-query-api (:8100)
         ├─→ /query/graph        → Fabric GQL (hardcoded workspace/graph model)
         ├─→ /query/telemetry    → Fabric KQL (hardcoded eventhouse)
         ├─→ /query/topology     → Fabric GQL (hardcoded graph name)
         └─→ /query/interactions → Cosmos NoSQL (interactions DB)
```

---

## 11. Cosmos DB Final State

**Before (2 accounts, 4+ databases):**

The `cosmos-gremlin.bicep` module creates **two Cosmos DB accounts**:

```
Gremlin account ({name}):
  networkgraph/                — database (no containers created in Bicep; graphs created at runtime)

NoSQL account ({name}-nosql):
  telemetry/                   — database (containers created at runtime)
  scenarios/scenarios          — scenario metadata (pk: /id)
  scenarios/configs             — parsed scenario.yaml (pk: /scenario_name)
  prompts/{scenario}           — per-scenario agent prompts (containers created at runtime)
  interactions/interactions     — investigation history (pk: /scenario, TTL 90d)
```

**After (1 account, 1 database, 1 container):**
```
NoSQL account ({name}-nosql):
  interactions/interactions     — investigation history (pk: /scenario, TTL 90d)
```

**Changes:**
- Delete the Gremlin account entirely (fabricdemo uses Fabric GQL, not Cosmos Gremlin)
- Delete `telemetry`, `scenarios`, `prompts` databases from the NoSQL account
- Rename `cosmos-gremlin.bicep` to `cosmos-nosql.bicep`

---

## 12. Hidden Dependencies & Cross-Cutting Concerns

These are non-obvious couplings discovered during deep research that must be addressed carefully.

### 12.1 Health Endpoint (`/query/health/sources`) — Scenario Config Dependency

`router_health.py` currently calls `fetch_scenario_config(scenario)` from `config_store.py` (Cosmos) to discover which data sources to probe. With `config_store.py` deleted, the health endpoint needs an alternative config source.

**Solution:** Hardcode the data source definitions in `router_health.py` itself (or in `config.py`):
```python
DATA_SOURCES = {
    "graph": {"connector": "fabric-gql", "resource_name": "telco-noc-topology"},
    "telemetry": {"connector": "fabric-kql", "resource_name": "NetworkTelemetryEH"},
    "search_indexes": {
        "runbooks": {"index_name": "runbooks-index"},
        "tickets": {"index_name": "tickets-index"},
    }
}
```
The probing logic (Graph ping, KQL ping, Search REST check) stays unchanged.

### 12.2 Resource Graph Endpoint (`/api/config/resources`) — Config Fetch Chain

`GET /api/config/resources` fetches scenario config from `GET /query/scenario/config?scenario=<name>`, then builds the resource graph via `_build_resource_graph(config, scenario_name)`. The fetch target (`router_scenarios.py`) will be deleted.

**Solution:** Hardcode the config dict in `routers/config.py` and have `_build_resource_graph()` read it directly. No new endpoint needed.

`_build_resource_graph()` is a pure function — it takes a dict of data sources, agents, and infra nodes and produces a graph. No changes needed to the function itself.

### 12.3 Prompt Template Variables — `{graph_name}` and `{scenario_prefix}`

Three prompt files contain template variables that the agent provisioner injects at provisioning time:
- `foundry_orchestrator_agent.md` → `{graph_name}`, `{scenario_prefix}`
- `foundry_telemetry_agent_v2.md` → `{graph_name}`, `{scenario_prefix}`
- `graph_explorer/core_instructions.md` → `{graph_name}`

These variables control the `X-Graph` header that sub-agents inject into queries. Even in single-scenario mode, the provisioner must still substitute them (e.g., `{graph_name}` → `telco-noc-topology`, `{scenario_prefix}` → `telco-noc`).

**Action:** Keep the template substitution in `provision_agents.py`. The prompts stay on disk with placeholders. Provisioner hardcodes the values.

### 12.4 X-Graph Header — No Longer Needed for Backend Routing

With hardcoded config, the backend resolves the graph model via env vars (`FABRIC_WORKSPACE_ID`, `FABRIC_GRAPH_MODEL_ID`), not via the `X-Graph` header. The routers no longer parse or depend on this header — `get_scenario_context()` returns a fixed context unconditionally.

The agents will still send `X-Graph` in their tool calls (it's baked into their OpenAPI spec templates at provisioning time), but the backend ignores it. Frontend hooks (e.g., `useTopology.ts`) should **stop sending the header** — it serves no purpose.

**Action:** Simplify `get_scenario_context()` to return a fixed context with no header parsing. Remove `X-Graph` header extraction from `router_graph.py`, `router_telemetry.py`, and `router_topology.py`. Agents still send it (harmless); frontend stops sending it.

### 12.5 Dockerfile — `COPY data/scenarios/` Line

The current Dockerfile copies `data/scenarios/` into the container image. This was used for runtime scenario resolution. With hardcoded config, this COPY is no longer needed for runtime — but the `scenario.yaml` is referenced by `_build_resource_graph()` if we go with option (b) above.

**Solution:** If config is hardcoded in Python, remove the `COPY data/scenarios/` line from the Dockerfile. The only data that needs to be in the container is `agent_ids.json` (already copied).

### 12.6 OpenAPI Spec Templates — Stable, Parametric-Only Dependency

The `graph-query-api/openapi/templates/` directory (`graph.yaml`, `telemetry.yaml`) and `_load_openapi_spec()` in `agent_provisioner.py` are scenario-agnostic — they take `graph_backend`, `graph_name`, and `base_url` as parameters. No changes needed. The provisioner just calls them with hardcoded values instead of config-derived values.

### 12.7 `agent_provisioner.py` — Two Provisioning Paths

The current `AgentProvisioner` has two paths:
- `provision_all()` — legacy hardcoded 5-agent structure
- `provision_from_config()` — config-driven from `scenario.yaml`

**Action:** Keep `provision_all()` (it's the "old way"). Delete `provision_from_config()` and all config-driven complexity. The simplified provisioner reads prompts from disk, substitutes `{graph_name}`/`{scenario_prefix}`, and creates exactly 5 agents.

### 12.8 `sseStream.ts` — Dual Usage

`sseStream.ts` is used by both `triggerProvisioning.ts` (to be deleted) and `useInvestigation.ts` (to be kept). It's also used by `useFabricDiscovery.ts` (to be deleted). The file itself is a generic SSE utility and should be kept.

### 12.9 Cosmos helpers — Shared Utility

`graph-query-api/cosmos_helpers.py` (if it exists) or the `get_or_create_container()` pattern in `stores/cosmos_nosql.py` is used by multiple routers. After cleanup, only `router_interactions.py` needs it. The `DocumentStore` protocol and `CosmosDocumentStore` implementation should be kept for the interactions use case.

### 12.10 `ServiceHealthSummary` and `ServiceHealthPopover`

These components poll backend health endpoints and display connectivity status in the header. They fetch from `/query/health/sources` (scenario-dependent as noted above) and `/health` (scenario-independent). After fixing the health endpoint config source (12.1), these components work unchanged.

---

## 13. Cosmosdemo Comparison & Learnings

The cosmosdemo is essentially the **same architecture** as fabricdemo but uses Cosmos DB Gremlin for graph queries and Cosmos DB NoSQL for telemetry (instead of Fabric). It has the full scenario management stack (upload, CRUD, multi-graph routing, config-driven provisioning).

### What cosmosdemo confirms about the simplification

| Observation | Implication |
|-------------|------------|
| Both demos share the same multi-agent orchestration core (SSE event protocol, retry logic, stub fallback) | The investigation flow is backend-agnostic — decoupled from graph/telemetry data sources |
| Both have identical frontend component sets (ScenarioChip, AddScenarioModal, etc.) | Deleting scenario UI from fabricdemo doesn't affect cosmosdemo — they are independent codebases |
| Cosmosdemo uses `COSMOS_GREMLIN_PRIMARY_KEY` (key-based auth for Gremlin) while fabricdemo uses `DefaultAzureCredential` everywhere | Fabricdemo's auth model is cleaner — no keys/secrets needed after managed identity RBAC |
| Cosmosdemo provisions 2 separate Cosmos accounts (Gremlin + NoSQL) in Bicep | Fabricdemo needs only 1 Cosmos NoSQL account (for interactions). Simpler infra. |
| Both share the `DocumentStore` protocol abstraction | The stores layer is well-designed and reusable — keep it for interactions |
| Cosmosdemo's Gremlin backend has connection pooling, retry on 429/408, keepalive loops | Fabricdemo's Fabric GQL backend has similar retry logic (5 attempts, exponential backoff on 429). Both are production-grade. |

### What NOT to adopt from cosmosdemo

- Multi-graph routing via `X-Graph` header → **removing** (simplifying to fixed context)
- Config-driven agent provisioning → **removing** (returning to hardcoded agent structure)
- Tarball-based data ingestion → **removing** (returning to script-based provisioning)
- Cosmos-backed scenario/prompt storage → **removing** (Cosmos for interactions only)

### What to preserve from the shared patterns

- **Unified container pattern** (nginx + 2 uvicorn + supervisord) — proven stable in both demos
- **SSE streaming bridge** (sync SDK thread → async queue → SSE events) — identical in both
- **Agent ID mtime caching** — both use `agent_ids.py` with mtime-based hot-reload
- **Stub/fallback response** — both generate realistic-looking stubs when agents aren't provisioned
- **Log broadcasting** — both use separate `LogBroadcaster` instances for general vs. data-ops logs
- **Force-graph-2d** for topology + resource visualizations — identical components

---

## 14. Observability Surface Inventory

These are the runtime observability features that make the demo valuable as a **playground**. All must be preserved:

| Surface | What it shows | Frontend | Backend | Status |
|---------|---------------|----------|---------|--------|
| **Agent Bar** | Provisioned agents (name, model, tools, connected agents) | `AgentBar` → `AgentCard` | `GET /api/agents` → `agent_ids.py` | **Unchanged** |
| **Data Source Bar** | Live health of each data source (graph, telemetry, search) | `DataSourceBar` → `DataSourceCard` | `GET /query/health/sources` | **Needs config source fix** |
| **Service Health** | Aggregate backend health (green/yellow/red) | `ServiceHealthSummary` → `ServiceHealthPopover` | `GET /health`, `GET /query/health/sources` | **Needs config source fix** |
| **Log Stream** | Real-time backend logs (color-coded by level, 200-line buffer) | `LogStream` → `TabbedLogStream` → `TerminalPanel` | `GET /api/logs` (SSE) | **Unchanged** |
| **Investigation Timeline** | Step-by-step agent execution progress (which agent, what tool, result) | `AgentTimeline` → `StepCard` | `POST /api/alert` (SSE events) | **Unchanged** |
| **Diagnosis Panel** | Final markdown-rendered diagnosis with metadata | `DiagnosisPanel` | Final `message` SSE event | **Unchanged** |
| **Graph Topology Viewer** | Interactive force-directed network graph | `GraphTopologyViewer` → `GraphCanvas` | `POST /query/topology` | **Needs header simplification** |
| **Resource Visualizer** | Agent → tool → data source → infra flow graph | `ResourceVisualizer` → `ResourceCanvas` | `GET /api/config/resources` | **Needs config source fix** |
| **Interaction History** | Past investigations (replay, compare) | `InteractionSidebar` | `GET/POST/DELETE /query/interactions` | **Unchanged** |
| **Metrics Bar** | Graph topology display area with resize observer | `MetricsBar` → `GraphTopologyViewer` | — | **Unchanged** |

---

## 15. Prompt Architecture (Preserved As-Is)

The prompt library is battle-tested and domain-specific. All 10 files remain in `data/scenarios/telco-noc/data/prompts/`:

| File | Agent | Template Vars | Purpose |
|------|-------|---------------|---------|
| `foundry_orchestrator_agent.md` | Orchestrator | `{graph_name}`, `{scenario_prefix}` | Master prompt: investigation flows A (forward) and B (backward), situation report format, specialist descriptions, telemetry baselines, 8 rules |
| `foundry_telemetry_agent_v2.md` | TelemetryAgent | `{graph_name}`, `{scenario_prefix}` | Cosmos SQL query guide for AlertStream + LinkTelemetry, schema tables, 5 example queries, X-Graph routing |
| `foundry_runbook_kb_agent.md` | RunbookKBAgent | — | AI Search query guide for 5 runbooks, response rules |
| `foundry_historical_ticket_agent.md` | HistoricalTicketAgent | — | AI Search query guide for ~10 historical tickets, structured findings format |
| `alert_storm.md` | (sample input) | — | CSV batch of ~20 SERVICE_DEGRADATION alerts — the default investigation trigger |
| `graph_explorer/description.md` | GraphExplorerAgent | — | Foundry agent description field |
| `graph_explorer/core_instructions.md` | GraphExplorerAgent | `{graph_name}` | Core role + 6 critical rules + scope definition |
| `graph_explorer/core_schema.md` | GraphExplorerAgent | — | Complete ontology (8 entity types, 7 relationships, all instance data) — 227 lines |
| `graph_explorer/language_gremlin.md` | GraphExplorerAgent | — | Gremlin syntax guide + multi-hop patterns (for cosmosdb backend) |
| `graph_explorer/language_mock.md` | GraphExplorerAgent | — | Mock backend guidance (natural language queries) |

**Note:** A `language_gql.md` file (for ISO GQL / Fabric backend) is not present yet. The provisioner currently handles GQL-specific descriptions via `CONNECTOR_OPENAPI_VARS["fabric"]` in `agent_provisioner.py`, but a dedicated prompt fragment may be needed for the simplified system. This is a **gap to fill** during Phase 1.

---

## 16. Infrastructure Simplification

### Current Bicep modules (fabricdemo)

| Module | Resource | After Simplification |
|--------|----------|---------------------|
| `vnet.bicep` | VNet + subnets | **Keep** |
| `ai-foundry.bicep` | AI Foundry + project + GPT-4.1 | **Keep** |
| `search.bicep` | Azure AI Search | **Keep** |
| `storage.bicep` | Storage Account | **Keep** |
| `cosmos-gremlin.bicep` | Cosmos DB NoSQL (misnamed; actually NoSQL for metadata) | **Keep but simplify** — only needs `interactions` database |
| `container-apps-environment.bicep` | Container Apps Environment + ACR | **Keep** |
| `container-app.bicep` | Unified Container App | **Keep** |
| `roles.bicep` | RBAC role assignments | **Keep** |
| `cosmos-private-endpoints.bicep` | Private endpoints | **Keep** |

### Bicep changes needed

1. **`cosmos-gremlin.bicep`** → Rename to `cosmos-nosql.bicep`. **Remove the Gremlin account entirely** — fabricdemo uses Fabric GQL, not Cosmos Gremlin. In the NoSQL account, remove pre-creation of `telemetry`, `scenarios`, `prompts` databases. Only create `interactions` database with `interactions` container (partition key `/scenario`, composite index on `/scenario` + `/created_at` desc, TTL 90 days).
2. **`main.bicep`** → Update module reference from `cosmos-gremlin.bicep` to `cosmos-nosql.bicep`. Remove the `databaseName` parameter passed to the Cosmos module if it references `networkgraph`. **Note:** `defaultScenario` and `loadedScenarios` parameters do **not** exist in `main.bicep` (despite `preprovision.sh` syncing them to azd env) — no Bicep parameter changes needed.
3. **`container-app.bicep`** → No changes needed. This module accepts `env` as a pass-through array parameter — it does not define scenario-related env vars inline. Env vars are set by the caller (`main.bicep`), which passes Fabric-related vars (`FABRIC_WORKSPACE_ID`, `FABRIC_GRAPH_MODEL_ID`, `EVENTHOUSE_QUERY_URI`, `FABRIC_KQL_DB_NAME`) from its own parameters. These already exist.

### Cosmosdemo vs Fabricdemo infra comparison

| Aspect | Cosmosdemo | Fabricdemo (after) |
|--------|-----------|-------------------|
| Cosmos accounts | 2 (Gremlin + NoSQL) | 1 (NoSQL only) |
| Cosmos databases | ~4 (graph, telemetry, scenarios, prompts) | 1 (interactions) |
| Fabric resources | None | Provisioned by scripts (not Bicep) |
| Container App env vars | ~25 (includes Gremlin keys as secrets) | ~15 (no keys — managed identity only) |

---

## 17. Audit Log

> Post-hoc verification of the plan against actual codebase state. All discrepancies found have been corrected inline in the relevant sections above.

### 17.1 Intention Verification

The plan was audited against three core intentions:

| Intention | Status | Evidence |
|-----------|--------|----------|
| **Single excellent scenario showcase** | ✅ Aligned | All multi-scenario CRUD, scenario switching, tarball uploads, and dynamic provisioning are removed. The `telco-noc` scenario is hardcoded everywhere. |
| **UI = observability + exploration + chat only** | ✅ Aligned (after fix) | `POST /api/config/apply` (runtime provisioning from UI) was ambiguously handled — now explicitly deleted (§3.4). All 10 observability surfaces preserved (§14). Header stripped to: title + ServiceHealthSummary + AgentBar + DataSourceBar. |
| **External scripts handle all provisioning** | ✅ Aligned | 10 scripts in Phase 1. No runtime provisioning endpoints remain in the app. `deploy.sh` updated with optional `--provision-*` flags. |

### 17.2 Factual Corrections Made

| Section | Original Claim | Actual State | Correction |
|---------|---------------|--------------|------------|
| §11 | "5 databases, ~8+ containers" | 2 Cosmos accounts (Gremlin + NoSQL), 4 databases (`networkgraph`, `telemetry`, `scenarios`, `prompts`, `interactions`) | Fixed — accurate account/database inventory. Gremlin account must be removed entirely. |
| §16 | "`main.bicep` — Remove `defaultScenario`, `loadedScenarios` parameters if they exist" | These parameters **do not exist** in `main.bicep`. `preprovision.sh` syncs them to azd env but no Bicep parameter consumes them. | Fixed — noted as dead vars. No Bicep changes needed. |
| §16 | "`container-app.bicep` — Remove env vars `DEFAULT_SCENARIO`, `LOADED_SCENARIOS`" | `container-app.bicep` accepts `env` as a pass-through array. It does not define any env vars inline. | Fixed — no container-app.bicep changes needed. |
| §3.4 | "Either: (a) remove entirely, or (b) keep simplified GET" | `POST /api/config/apply` triggers runtime agent provisioning from UI. `GET /current` is self-contained. `GET /resources` needs config source fix. | Fixed — explicitly DELETE `/apply`, KEEP `/current` and `/resources`. |
| §4.4 | Proposed steps as if current numbering starts at 0–9 | Current deploy.sh has steps 0,1,2,3,4,6,7 (step 5 removed; 8–9 nonexistent). Vestigial flags exist. Summary prints tarball instructions. | Fixed — acknowledged current gaps, added cleanup items. |

### 17.3 Missing Actions Added

| Category | Item | Added To |
|----------|------|----------|
| **Dockerfile** | Remove `COPY graph-query-api/ingest/ ./ingest/` (ingest package deleted) | Phase 2 step 9, §6.2 |
| **Dockerfile** | Remove `COPY data/scenarios/ /app/data/scenarios/` (config hardcoded) | Phase 5 step 9, §6.2 |
| **deploy.sh** | Remove vestigial `--skip-index`/`--skip-data`/`--skip-agents` flags | Phase 5 step 6, §4.4 |
| **deploy.sh** | Remove tarball/upload summary instructions | Phase 5 step 6, §4.4 |
| **postprovision.sh** | Remove dead `upload_with_retry()` function (~40 lines, never called) | Phase 5 step 7, §4.5 |
| **preprovision.sh** | Remove `DEFAULT_SCENARIO`/`LOADED_SCENARIOS` syncing (dead vars) | Phase 5 step 8, §4.5b |
| **nginx.conf** | Clean up `client_max_body_size 100m` upload comment | Phase 5 step 10, §6.2 |
| **azure_config.env.template** | Fix `GRAPH_QUERY_API_PRINCIPAL_ID` vs `APP_PRINCIPAL_ID` mismatch; remove "UI Settings page" comment | Phase 5 step 5, §4.5 |
| **router_health.py** | Change `scenario` query param from required (`Query(...)`) to optional with default `"telco-noc"` | Phase 2 step 8, §3.6 |
| **graph-query-api/main.py** | Keep inline SSE log-streaming endpoints (`/query/logs`, `/query/logs/data-ops`) | Phase 2 step 5 note |
| **Bicep** | Remove Gremlin account entirely (fabricdemo never uses it) | Phase 5 step 12, §16 |

### 17.4 Hidden Dependency Phase Mapping

| Hidden Dep (§12) | Description | Resolved In |
|------------------|-------------|-------------|
| §12.1 Health endpoint | `router_health.py` → `config_store.py` dependency | **Phase 2 step 8** |
| §12.2 Resource graph | `GET /api/config/resources` → `/query/scenario/config` dependency | **Phase 3 step 3** |
| §12.3 Prompt template vars | `{graph_name}`, `{scenario_prefix}` substitution | **Phase 1 step 4** (provision_agents.py hardcodes values) |
| §12.4 X-Graph header | Agents send it via OpenAPI specs; backend ignores it; frontend stops sending it | **Phase 2 step 6** (get_scenario_context returns fixed context, header parsing removed) |
| §12.5 Dockerfile scenarios COPY | `COPY data/scenarios/` no longer needed | **Phase 5 step 9** |
| §12.6 OpenAPI templates | Scenario-agnostic, parametric-only | **No action needed** |
| §12.7 agent_provisioner.py paths | Two provisioning paths | **Phase 1 step 4** (keep `provision_all()`, delete `provision_from_config()`) |
| §12.8 sseStream.ts dual usage | Used by investigation (keep) and provisioning (deleted) | **Phase 4** (file kept, dead import gone with triggerProvisioning.ts) |
| §12.9 Cosmos helpers | DocumentStore for interactions | **Phase 2 step 7** (keep for interactions, remove scenario uses) |
| §12.10 ServiceHealthSummary | Depends on health endpoint | **Phase 2 step 8** (health endpoint fixed) |

### 17.5 Phase Dependency Chain

```
Phase 1 (add scripts)     — purely additive, no breakage
    ↓
Phase 2 (graph-query-api) — removes 9+ files, fixes health endpoint
    ↓                        § Frontend health/data-source components still work
Phase 3 (API)             — removes 2 files + 1 endpoint, fixes resource graph
    ↓                        § Frontend investigation + resource views still work
Phase 4 (frontend)        — removes 12 files, adds config.ts
    ↓                        § UI is now a pure playground
Phase 5 (cleanup)         — non-breaking: data, config, infra, Dockerfile, deploy.sh
    ↓
Phase 6 (test)            — end-to-end validation
```

Each phase boundary leaves the app in a working (or at least startable) state. The critical ordering constraint is: **Phase 2 before Phase 3** (API's `/resources` depends on graph-query-api changes being done first) and **Phases 2+3 before Phase 4** (frontend depends on backend endpoints being stable).

### 17.6 Remaining Gaps

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **`stores/` package cleanup** | `stores/__init__.py` auto-registers `CosmosDocumentStore` and has `get_document_store()` factory. After cleanup, only `router_interactions.py` uses it. | No code changes needed — factory pattern is fine with single consumer. Clean up if desired. |
| **Two `/health` endpoints in graph-query-api** | `main.py` inline `GET /health` (liveness) + `router_health.py` `GET /query/health/sources` (deep probe). Both serve different purposes. | Keep both — no conflict. Document the distinction: `/health` = liveness, `/query/health/sources` = data source probing. |
| **Cosmos `upload-jobs` container** | Listed in §3.7 ("Stop Using") but not visible in Bicep (created at runtime). Data may exist. | No Bicep change needed. Container will stop being written to. Can be manually deleted from Azure Portal. |
