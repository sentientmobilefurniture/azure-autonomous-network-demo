# NUKECOSMOS — Strip CosmosDB Graph & Telemetry

> **Goal:** Remove all CosmosDB graph (Gremlin) and telemetry (NoSQL SQL-query) code paths.  
> Graph and telemetry queries go **exclusively** to Fabric (GQL for graph, Eventhouse/KQL for telemetry).  
> CosmosDB is retained **only** for: saving interactions, scenario metadata, prompts, config store, and docs (upload-jobs).

---

## Table of Contents

1. [Guiding Principles](#1-guiding-principles)
2. [What Stays (CosmosDB NoSQL — Metadata)](#2-what-stays)
3. [Phase 1 — Delete Files](#3-phase-1--delete-files)
4. [Phase 2 — Backend & Config Changes](#4-phase-2--backend--config-changes)
5. [Phase 3 — Router & Ingest Changes](#5-phase-3--router--ingest-changes)
6. [Phase 4 — Infrastructure (Bicep)](#6-phase-4--infrastructure-bicep)
7. [Phase 5 — Frontend Changes](#7-phase-5--frontend-changes)
8. [Phase 6 — Scripts & Agent Provisioning](#8-phase-6--scripts--agent-provisioning)
9. [Phase 7 — Dependencies & Cleanup](#9-phase-7--dependencies--cleanup)
10. [Environment Variable Changes](#10-environment-variable-changes)
11. [Verification Checklist](#11-verification-checklist)
12. [Risk & Rollback](#12-risk--rollback)

---

## 1. Guiding Principles

| Principle | Detail |
|-----------|--------|
| **Fabric-only for data queries** | All graph traversal → Fabric GQL. All telemetry queries → Fabric Eventhouse KQL. No exceptions. |
| **CosmosDB = document store only** | Interactions, scenarios, prompts, config, docs — pure CRUD on NoSQL containers. No SQL SELECT queries exposed to agents. |
| **No dual-path code** | Remove every `if cosmosdb … else fabric` branch. There is one path: Fabric. |
| **Backend abstraction stays** | Keep `GraphBackend` protocol and registry; just remove the `cosmosdb` registration. `fabric-gql` becomes the sole real backend (plus `mock` for testing). |

---

## 2. What Stays

These files use CosmosDB NoSQL as a **document store** (not for graph or telemetry queries) and are **unchanged**:

| File | Purpose |
|------|---------|
| `graph-query-api/cosmos_helpers.py` | Singleton `CosmosClient`, `get_or_create_container()` — shared infra for all metadata stores |
| `graph-query-api/stores/cosmos_nosql.py` | `CosmosDocumentStore` — async CRUD wrapper |
| `graph-query-api/stores/__init__.py` | `DocumentStore` protocol + registry |
| `graph-query-api/router_interactions.py` | Interaction CRUD (`interactions/interactions`) |
| `graph-query-api/router_prompts.py` | Prompt CRUD (`prompts/{scenario}`) |
| `graph-query-api/config_store.py` | Scenario config persistence (`scenarios/configs`) |
| `graph-query-api/router_docs.py` | Generic doc CRUD (`upload-jobs`, etc.) |
| `graph-query-api/router_topology.py` | Backend-agnostic — calls `get_backend_for_context()`, already works with Fabric |

---

## 3. Phase 1 — Delete Files

### 3.1 Files to delete outright

| File | Reason |
|------|--------|
| `graph-query-api/backends/cosmosdb.py` | Entire `CosmosDBGremlinBackend` — Gremlin WSS client, query submission, retry, topology, ingest via ARM. ~501 lines. |
| `graph-query-api/gremlin_helpers.py` | `create_gremlin_client()`, `gremlin_submit_with_retry()` — Gremlin driver helpers. |
| `graph-query-api/ingest/scenarios.py` | `list_cosmos_scenarios()`, `delete_cosmos_graph()` — ARM-based Gremlin graph management. Replaced by Fabric scenario discovery. |
| `graph-query-api/ingest/arm_helpers.py` | `ensure_nosql_container_via_arm()` — ARM provisioning for telemetry containers. Fabric doesn't need this. |
| `graph-query-api/openapi/cosmosdb.yaml` | OpenAPI spec for Gremlin graph + Cosmos SQL telemetry endpoints. Replaced by Fabric OpenAPI spec. |
| `custom_skills/azure-cosmosdb-gremlin-py/` | Entire directory — reference material for Cosmos Gremlin skill, no longer relevant. |

### 3.2 Commands

```bash
cd /home/hanchoong/projects/autonomous-network-demo-fabric
rm graph-query-api/backends/cosmosdb.py
rm graph-query-api/gremlin_helpers.py
rm graph-query-api/ingest/scenarios.py
rm graph-query-api/ingest/arm_helpers.py
rm graph-query-api/openapi/cosmosdb.yaml
rm -rf custom_skills/azure-cosmosdb-gremlin-py/
```

---

## 4. Phase 2 — Backend & Config Changes

### 4.1 `graph-query-api/backends/__init__.py`

**Remove** the CosmosDB auto-registration block (lines ~156–161):

```python
# DELETE this block:
try:
    from .cosmosdb import CosmosDBGremlinBackend
    register_backend("cosmosdb", CosmosDBGremlinBackend)
except ImportError:
    import logging
    logging.getLogger("graph-query-api").warning(
        "CosmosDBGremlinBackend not available (missing gremlin_python?)"
    )
```

**Update** the `execute_query` docstring — remove the `cosmosdb: Gremlin` line. Keep only:
```
- fabric-gql: GQL queries against Fabric GraphQL API
- mock:       natural language or predefined keys
```

### 4.2 `graph-query-api/adapters/cosmos_config.py`

**Remove** the entire Gremlin settings section and `COSMOS_REQUIRED_VARS`:

```python
# DELETE:
COSMOS_GREMLIN_ENDPOINT = os.getenv("COSMOS_GREMLIN_ENDPOINT", "")
COSMOS_GREMLIN_PRIMARY_KEY = os.getenv("COSMOS_GREMLIN_PRIMARY_KEY", "")
COSMOS_GREMLIN_DATABASE = os.getenv("COSMOS_GREMLIN_DATABASE", "networkgraph")
COSMOS_GREMLIN_GRAPH = os.getenv("COSMOS_GREMLIN_GRAPH", "topology")

COSMOS_REQUIRED_VARS: tuple[str, ...] = (
    "COSMOS_GREMLIN_ENDPOINT", "COSMOS_GREMLIN_PRIMARY_KEY",
)
```

**Keep** only:
```python
COSMOS_NOSQL_ENDPOINT = os.getenv("COSMOS_NOSQL_ENDPOINT", "")
COSMOS_NOSQL_DATABASE = os.getenv("COSMOS_NOSQL_DATABASE", "telemetry")
```

> **Note:** `COSMOS_NOSQL_DATABASE` default `"telemetry"` was used for telemetry containers.
> After this change it's only used by metadata stores that specify their own database names.
> Consider renaming to `"metadata"` or removing the default if stores always provide explicit DB names.

### 4.3 `graph-query-api/config.py`

#### 4.3.1 Remove Gremlin imports

```python
# DELETE:
from adapters.cosmos_config import COSMOS_GREMLIN_DATABASE, COSMOS_GREMLIN_GRAPH
```

#### 4.3.2 Change default backend

```python
# BEFORE:
GRAPH_BACKEND: str = os.getenv("GRAPH_BACKEND", "cosmosdb").lower()

# AFTER:
GRAPH_BACKEND: str = os.getenv("GRAPH_BACKEND", "fabric-gql").lower()
```

#### 4.3.3 Update `ScenarioContext`

- Remove `graph_database` field (was `COSMOS_GREMLIN_DATABASE` — only relevant for Gremlin).
- Remove `telemetry_database` and `telemetry_container_prefix` fields (Cosmos telemetry path gone).
- Remove `telemetry_backend_type` field — it's always `"fabric-kql"` now (no branching needed).
- Keep `fabric_workspace_id`, `fabric_graph_model_id`, `fabric_eventhouse_id`.

#### 4.3.4 Update `CONNECTOR_TO_BACKEND`

```python
# BEFORE:
CONNECTOR_TO_BACKEND: dict[str, str] = {
    "cosmosdb-gremlin": "cosmosdb",
    "fabric-gql": "fabric-gql",
    "mock": "mock",
}

# AFTER:
CONNECTOR_TO_BACKEND: dict[str, str] = {
    "fabric-gql": "fabric-gql",
    "mock": "mock",
}
```

#### 4.3.5 Remove `TELEMETRY_CONNECTOR_MAP`

```python
# DELETE entirely — telemetry is always KQL now
TELEMETRY_CONNECTOR_MAP: dict[str, str] = { ... }
```

#### 4.3.6 Update `get_scenario_context()`

- Default `x_graph` fallback: change from `COSMOS_GREMLIN_GRAPH` to a sensible Fabric default (e.g. `os.getenv("DEFAULT_SCENARIO", "telco-noc")`)
- Remove `telemetry_backend_type` resolution logic
- Remove `graph_database=COSMOS_GREMLIN_DATABASE` from the return

#### 4.3.7 Update `BACKEND_REQUIRED_VARS`

```python
# BEFORE:
BACKEND_REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "cosmosdb": ("COSMOS_GREMLIN_ENDPOINT", "COSMOS_GREMLIN_PRIMARY_KEY"),
    "fabric-gql": ("FABRIC_WORKSPACE_ID", "FABRIC_GRAPH_MODEL_ID"),
    "mock": (),
}

# AFTER:
BACKEND_REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "fabric-gql": ("FABRIC_WORKSPACE_ID", "FABRIC_GRAPH_MODEL_ID"),
    "mock": (),
}
```

#### 4.3.8 Remove `TELEMETRY_REQUIRED_VARS`

```python
# DELETE:
TELEMETRY_REQUIRED_VARS: tuple[str, ...] = (
    "COSMOS_NOSQL_ENDPOINT", "COSMOS_NOSQL_DATABASE",
)
```

---

## 5. Phase 3 — Router & Ingest Changes

### 5.1 `graph-query-api/router_telemetry.py` — Gut Cosmos SQL path

**Current state:** Dual-path — checks `ctx.telemetry_backend_type` and routes to either Cosmos NoSQL or Fabric KQL.

**Target:** KQL-only. The entire router becomes a thin wrapper around `FabricKQLBackend`.

- Remove the `close_telemetry_backend()` function (was closing `CosmosClient`).
- Remove `_transform_telemetry_results()` helper (Cosmos-specific post-processing).
- Remove import of `COSMOS_NOSQL_ENDPOINT`.
- Remove import of `get_document_store` (was for Cosmos telemetry queries).
- Remove the Cosmos NoSQL code path (lines ~88–127 in current file).
- Keep only the `_query_fabric_kql()` path and make it the default.
- Update endpoint description to reference KQL, not Cosmos SQL.

### 5.2 `graph-query-api/router_graph.py` — Minor text update

- Update description text: remove mentions of "Cosmos DB Gremlin". Replace with "Fabric GQL or mock".
- Code is already backend-agnostic via `get_backend_for_context()` — no logic changes.

### 5.3 `graph-query-api/router_health.py` — Update defaults

- Change default connector from `"cosmosdb-gremlin"` → `"fabric-gql"`.
- Change default telemetry connector from `"cosmosdb-nosql"` → `"fabric-kql"`.

### 5.4 `graph-query-api/router_scenarios.py` — Update defaults

- Change any default `connector` value from `"cosmosdb-gremlin"` → `"fabric-gql"`.
- Remove references to Cosmos Gremlin graph names in scenario creation logic.

### 5.5 `graph-query-api/ingest/graph_ingest.py`

- Remove import of `COSMOS_GREMLIN_DATABASE`.
- Remove Cosmos-specific fallback paths. The `GraphBackend.ingest()` call is already abstract — just ensure it routes to Fabric.

### 5.6 `graph-query-api/ingest/telemetry_ingest.py`

- **Remove** the Cosmos NoSQL upload path entirely (uploading CSVs to Cosmos containers).
- Replace with Fabric Eventhouse ingest pathway, or mark as Fabric-only stub.

### 5.7 `graph-query-api/ingest/prompt_ingest.py`

- Update `_detect_connector()` default from `"cosmosdb-gremlin"` → `"fabric-gql"`.

### 5.8 `graph-query-api/main.py`

#### 5.8.1 Remove Gremlin pre-warm block

Delete the entire pre-warm section (~lines 82–103):
```python
# DELETE:
keepalive_tasks: list[asyncio.Task] = []
try:
    from router_scenarios import _get_store
    from backends import get_backend_for_graph
    ...
    logger.info("Pre-warmed %d Gremlin backend(s)", len(keepalive_tasks))
except Exception as e:
    logger.warning("Skipping Gremlin pre-warm ...")
```

And the keepalive cancel block:
```python
# DELETE:
for task in keepalive_tasks:
    task.cancel()
```

#### 5.8.2 Remove `TELEMETRY_REQUIRED_VARS` check

Delete lines ~72–77:
```python
# DELETE:
missing_telemetry = [v for v in TELEMETRY_REQUIRED_VARS if not os.getenv(v)]
if missing_telemetry:
    logger.warning(...)
```

Update import: remove `TELEMETRY_REQUIRED_VARS` from `config`.

#### 5.8.3 Remove `close_telemetry_backend` import and call

```python
# BEFORE:
from router_telemetry import router as telemetry_router, close_telemetry_backend
# AFTER:
from router_telemetry import router as telemetry_router
```

Remove `close_telemetry_backend()` from shutdown.

#### 5.8.4 Update docstrings

Replace:
```
POST /query/graph — Execute a graph query (Gremlin or mock via GRAPH_BACKEND)
POST /query/telemetry — Execute a SQL query against Cosmos DB NoSQL telemetry containers
```
With:
```
POST /query/graph — Execute a graph query (GQL via Fabric or mock)
POST /query/telemetry — Execute a KQL query against Fabric Eventhouse
```

---

## 6. Phase 4 — Infrastructure (Bicep)

### 6.1 `infra/main.bicep`

- Remove `deployCosmosGremlin` variable and conditional.
- Remove `module cosmosGremlin 'modules/cosmos-gremlin.bicep'` deployment.
- Remove env vars: `COSMOS_GREMLIN_ENDPOINT`, `COSMOS_GREMLIN_DATABASE`, `COSMOS_GREMLIN_GRAPH`, `COSMOS_GREMLIN_PRIMARY_KEY`.
- Change `param graphBackend` default to `'fabric-gql'` (or remove the param entirely — there's no choice anymore).
- **Keep** the Cosmos NoSQL account deployment for metadata stores (interactions, scenarios, prompts).
- **Keep** env vars: `COSMOS_NOSQL_ENDPOINT`.
- Add default Fabric env vars if not present: `FABRIC_WORKSPACE_ID`, `FABRIC_GRAPH_MODEL_ID`.

### 6.2 `infra/main.bicepparam`

- Change `param graphBackend = 'cosmosdb'` → `'fabric-gql'` (or remove).

### 6.3 `infra/modules/cosmos-gremlin.bicep`

- **Rename** to `cosmos-nosql-metadata.bicep` (or similar).
- **Remove** the Gremlin account, database, and graph resources.
- **Keep** the NoSQL account with databases: `scenarios`, `interactions`, `prompts`, `platform-config`.
- Remove telemetry NoSQL database/containers if they were provisioned here.

### 6.4 `infra/modules/cosmos-private-endpoints.bicep`

- Remove Gremlin private endpoint.
- Keep NoSQL private endpoint.

### 6.5 `infra/modules/roles.bicep`

- **Keep** — still needed for data-plane RBAC on the NoSQL account.

---

## 7. Phase 5 — Frontend Changes

### 7.1 `frontend/src/components/AddScenarioModal.tsx`

- Remove `'cosmosdb-gremlin'` from backend selector.
- Default to `'fabric-gql'`.
- Remove the CosmosDB backend option UI entirely.

### 7.2 `frontend/src/components/EmptyState.tsx`

- Remove the "Upload Cosmos Scenario" / "CosmosDB + Blob" onboarding card.
- Keep only the Fabric onboarding path.

### 7.3 `frontend/src/components/ScenarioChip.tsx`

- Remove `'Cosmos'` badge rendering.
- All scenarios show as `'Fabric'`.

### 7.4 `frontend/src/components/ScenarioManagerModal.tsx`

- Remove `'Cosmos'` badge/label.

### 7.5 `frontend/src/types/index.ts`

- Remove `'cosmos-account'` and `'cosmos-database'` from `ResourceNodeType`.
- Update `graph_connector` comment to remove `"cosmosdb-gremlin"`.

### 7.6 `frontend/src/components/resource/ResourceCanvas.tsx`

- Remove rendering logic for `cosmos-account` and `cosmos-database` node types.

### 7.7 `frontend/src/components/resource/resourceConstants.ts`

- Remove color/size/label entries for `cosmos-account` and `cosmos-database`.

### 7.8 `frontend/src/components/ResourceVisualizer.tsx`

- Remove `'cosmos-account'` from `INFRA_TYPES` set.

### 7.9 `frontend/src/context/ScenarioContext.tsx`

- Update comments: change "Cosmos" references to "backend" or "API".
- Remove "Gremlin" references in comments.

---

## 8. Phase 6 — Scripts & Agent Provisioning

### 8.1 `scripts/agent_provisioner.py`

- Remove `"cosmosdb"` from `OPENAPI_SPEC_MAP` (line ~40: `"cosmosdb": OPENAPI_DIR / "cosmosdb.yaml"`).
- Remove `"cosmosdb"` tool descriptions (Gremlin query tool, Cosmos SQL telemetry tool).
- Remove `"cosmosdb"` graph query description.
- Keep `"fabric-gql"` and `"fabric-kql"` paths.

### 8.2 `scripts/provision_agents.py`

- Remove `"cosmosdb": "language_gremlin.md"` from `LANGUAGE_FILE_MAP`.
- Change default `graph_backend` from `"cosmosdb"` to `"fabric-gql"`.
- Remove `COSMOS_GREMLIN_GRAPH` env var read.

### 8.3 `scripts/testing_scripts/test_graph_query_api.py`

- Update test queries from Gremlin to GQL.
- Update test descriptions.

### 8.4 `data/scenarios/` — Scenario data files

- Remove `language_gremlin.md` prompt files from any scenario directories.
- Remove Gremlin-specific content from `graph_schema.yaml` files.
- Ensure all scenario configs default to `fabric-gql` / `fabric-kql` connectors.

---

## 9. Phase 7 — Dependencies & Cleanup

### 9.1 `graph-query-api/pyproject.toml`

**Remove:**
```toml
"gremlinpython>=3.7.0",
```

**Evaluate keeping:**
```toml
"azure-mgmt-cosmosdb>=9.0.0",
```
> `azure-mgmt-cosmosdb` is still used by `cosmos_helpers.py` → `get_mgmt_client()` → `get_or_create_container()` for ARM-based container creation of metadata stores. **Keep it** unless metadata container creation is moved to Bicep-only (then it can go).

### 9.2 Lock file

```bash
cd graph-query-api && uv lock
```

### 9.3 `azure_config.env` / `azure_config.env.template`

Remove:
```
COSMOS_GREMLIN_ENDPOINT=...
COSMOS_GREMLIN_PRIMARY_KEY=...
COSMOS_GREMLIN_DATABASE=...
COSMOS_GREMLIN_GRAPH=...
GRAPH_BACKEND=cosmosdb
```

Keep:
```
COSMOS_NOSQL_ENDPOINT=...
```

Add (if missing):
```
GRAPH_BACKEND=fabric-gql
FABRIC_WORKSPACE_ID=...
FABRIC_GRAPH_MODEL_ID=...
FABRIC_EVENTHOUSE_ID=...
```

### 9.4 Grep sweep

```bash
# Final verification — should return 0 hits outside documentation/NUKECOSMOS.md:
grep -rn "gremlin\|COSMOS_GREMLIN\|cosmosdb-gremlin\|CosmosDBGremlinBackend" \
  --include="*.py" --include="*.ts" --include="*.tsx" --include="*.bicep" --include="*.yaml" --include="*.toml" \
  . | grep -v NUKECOSMOS | grep -v __pycache__ | grep -v .venv
```

---

## 10. Environment Variable Changes

### Removed

| Variable | Was Used For |
|----------|-------------|
| `COSMOS_GREMLIN_ENDPOINT` | Gremlin WSS endpoint |
| `COSMOS_GREMLIN_PRIMARY_KEY` | Gremlin auth |
| `COSMOS_GREMLIN_DATABASE` | Gremlin DB name (`networkgraph`) |
| `COSMOS_GREMLIN_GRAPH` | Default Gremlin graph (`topology`) |

### Kept

| Variable | Used For |
|----------|---------|
| `COSMOS_NOSQL_ENDPOINT` | Metadata stores (interactions, scenarios, prompts, config, docs) |
| `AZURE_SUBSCRIPTION_ID` | ARM management client for container creation |
| `AZURE_RESOURCE_GROUP` | ARM management client |

### Defaults Changed

| Variable | Old Default | New Default |
|----------|-------------|-------------|
| `GRAPH_BACKEND` | `cosmosdb` | `fabric-gql` |

### Required for Fabric (ensure set)

| Variable | Purpose |
|----------|---------|
| `FABRIC_WORKSPACE_ID` | Fabric GQL + KQL workspace |
| `FABRIC_GRAPH_MODEL_ID` | Fabric GQL graph model |
| `FABRIC_EVENTHOUSE_ID` | Fabric Eventhouse for telemetry |

---

## 11. Verification Checklist

After all changes, verify:

- [ ] `grep -rn "gremlin" --include="*.py" .` returns 0 hits (outside docs)
- [ ] `grep -rn "CosmosDBGremlinBackend" .` returns 0 hits
- [ ] `grep -rn "cosmosdb-gremlin" --include="*.py" --include="*.ts" --include="*.tsx" .` returns 0 hits
- [ ] `grep -rn "COSMOS_GREMLIN" --include="*.py" --include="*.env" --include="*.bicep" .` returns 0 hits
- [ ] `python -c "from backends import _backend_registry; assert 'cosmosdb' not in _backend_registry"`
- [ ] `GRAPH_BACKEND=fabric-gql uvicorn main:app` starts without import errors
- [ ] `POST /query/graph` routes to `FabricGQLBackend`
- [ ] `POST /query/telemetry` routes to `FabricKQLBackend` (no Cosmos fallback)
- [ ] `POST /query/scenarios` (list) returns scenarios without Gremlin references
- [ ] `POST /ingest/scenario` ingests to Fabric, not Cosmos Gremlin
- [ ] `GET /health` reports `fabric-gql` as backend
- [ ] Frontend `AddScenarioModal` shows no CosmosDB option
- [ ] Frontend `EmptyState` shows no "CosmosDB + Blob" card
- [ ] Bicep deploys NoSQL-only Cosmos (no Gremlin account)
- [ ] Interactions CRUD still works (save, list, get, delete)
- [ ] Prompt CRUD still works
- [ ] Config store still works

---

## 12. Risk & Rollback

| Risk | Mitigation |
|------|-----------|
| `cosmos_helpers.py` uses `azure-mgmt-cosmosdb` for ARM container creation | Keep `azure-mgmt-cosmosdb` dependency. Metadata stores still need auto-provisioning. |
| Telemetry ingest has no Fabric pathway yet | Implement Fabric Eventhouse ingest before removing Cosmos telemetry ingest, OR stub it with a clear error message. |
| Scenarios saved with `"cosmosdb-gremlin"` connector in Cosmos | Write a one-time migration script to update existing scenario docs: set `connector` to `"fabric-gql"` and `telemetry_connector` to `"fabric-kql"`. |
| Frontend references `'cosmosdb-gremlin'` in saved state / localStorage | Clear localStorage on version bump, or handle unknown connector gracefully (default to `fabric-gql`). |
| `ingest/graph_ingest.py` calls `backend.ingest()` which must work with Fabric | Verify `FabricGQLBackend.ingest()` is implemented. If not, implement before removing Cosmos. |

### Rollback

The `autonomous-network-demo` (non-fabric) project remains untouched as a working reference if needed. The `backup/` directory also holds a known-good state.

---

## Execution Order

```
Phase 1  →  Delete files (clean break, surfaces import errors immediately)
Phase 2  →  Backend & config (fix imports, change defaults)
Phase 3  →  Routers & ingest (remove dual-path logic)
Phase 4  →  Infrastructure (Bicep — can be done in parallel with Phase 3)
Phase 5  →  Frontend (can be done in parallel with Phases 3–4)
Phase 6  →  Scripts & agent provisioning
Phase 7  →  Dependencies, env cleanup, final grep sweep
```

**Estimated file count:** 5 deleted, ~35 modified, 1 new file (Fabric OpenAPI spec).

---

## 13. AUDIT — Gaps Found (2026-02-17)

> End-to-end trace of every graph, telemetry, and ingest flow against the plan.  
> Items below are **MISSING from Phases 1–7** and must be added before execution.

### 13.1 BLOCKERS — Will crash the app if not fixed

#### B1. `ingest/__init__.py` imports deleted `scenarios.py`

[ingest/\_\_init\_\_.py](graph-query-api/ingest/__init__.py) line 17:
```python
from .scenarios import router as _scenarios_router
```
Deleting `ingest/scenarios.py` in Phase 1 will **crash the entire ingest package** — all ingest
endpoints (graph, telemetry, knowledge, prompt) fail to load.

**Fix:** Remove the import and `router.include_router(_scenarios_router)` line. If scenario
list/delete endpoints are still needed, rewrite them against the config store (CosmosDB NoSQL
metadata) or Fabric workspace item listing — they must not use Gremlin.

#### B2. `ingest/telemetry_ingest.py` imports deleted `arm_helpers.py`

[ingest/telemetry\_ingest.py](graph-query-api/ingest/telemetry_ingest.py) line 17:
```python
from .arm_helpers import _ensure_nosql_containers
```
Deleting `ingest/arm_helpers.py` in Phase 1 will **break telemetry ingest import**, cascading
to the ingest package crash from B1.

**Fix:** Must remove this import at the same time as deleting `arm_helpers.py`. The Cosmos
telemetry upload path is being gutted anyway (§5.6), so the import and all callers go.

### 13.2 MAJOR GAPS — Files entirely missing from the plan

#### M1. `api/app/routers/config.py` — Not mentioned anywhere

This file in the **API service** (not graph-query-api) has significant Cosmos graph/telemetry logic:

| Line | Reference | Impact |
|------|-----------|--------|
| L82 | `os.getenv("COSMOS_GREMLIN_GRAPH", "topology")` | Reads deleted env var |
| L246 | `os.getenv("GRAPH_BACKEND", "cosmosdb")` | Defaults to removed backend |
| L418 | `"cosmosdb_gremlin": "datasource"` | Datasource type mapping for resource viz |
| L419 | `"cosmosdb_nosql": "datasource"` | Telemetry datasource type |
| L425-455 | `if ds_type == "cosmosdb_gremlin"` branches | Edge creation for Cosmos nodes |
| L473-476 | `"infra-cosmos-g"`, `"Cosmos DB (Gremlin)"` infra nodes | Resource visualizer hardcoded Cosmos nodes |
| L123,183,190,198,214,235 | "Cosmos" in comments/progress messages | Cosmetic but should reference "backend" |

**Action → Add to Phase 3 as §5.9:**
- Change `GRAPH_BACKEND` default to `"fabric-gql"`
- Remove `COSMOS_GREMLIN_GRAPH` env read (use scenario config or Fabric default)
- Remove `"cosmosdb_gremlin"` and `"cosmosdb_nosql"` datasource type mappings
- Remove Cosmos infrastructure nodes from resource visualizer
- Update progress/comment text

#### M2. `deploy.sh` — Not mentioned anywhere

28+ Cosmos/Gremlin references. This is the primary deployment script:

| Lines | Reference |
|-------|-----------|
| L339 | `USE_ENV="noc-cosmosdb"` |
| L364 | `step "Step 2: Configuring for Cosmos DB backend"` |
| L389-390 | `GRAPH_BACKEND=cosmosdb` hardcoded |
| L395-398 | Config header: "Cosmos DB Flow" |
| L425-430 | `COSMOS_GREMLIN_ENDPOINT`, `COSMOS_GREMLIN_PRIMARY_KEY` env var blocks |

**Action → Add to Phase 6 as §8.5:**
- Change `GRAPH_BACKEND` to `fabric-gql`
- Remove all `COSMOS_GREMLIN_*` env vars
- Remove Cosmos DB backend step/flow text
- Keep `COSMOS_NOSQL_ENDPOINT` for metadata

#### M3. `hooks/postprovision.sh` — Not mentioned anywhere

Auto-populates Cosmos credentials after `azd up`:

| Lines | Reference |
|-------|-----------|
| L84-85 | `AZD_COSMOS_GREMLIN_ENDPOINT`, `AZD_COSMOS_GREMLIN_ACCOUNT_NAME` |
| L102-104 | `PREV_GRAPH_BACKEND="${GRAPH_BACKEND:-cosmosdb}"`, `PREV_COSMOS_GREMLIN_DB` |
| L146 | `# Options: "cosmosdb" (Gremlin → ...)` |

**Action → Add to Phase 6 as §8.6:**
- Remove Gremlin credential auto-population
- Change `GRAPH_BACKEND` default to `"fabric-gql"`
- Keep NoSQL endpoint auto-population for metadata

#### M4. No Fabric OpenAPI spec exists

[graph-query-api/openapi/](graph-query-api/openapi/) contains only `cosmosdb.yaml` and `mock.yaml`.
The plan says `cosmosdb.yaml` is "Replaced by Fabric OpenAPI spec" but **no `fabric-gql.yaml`
or `fabric.yaml` exists**. Agent provisioning needs an OpenAPI spec to register graph + telemetry
tools with Azure AI Foundry agents.

**Action → Add to Phase 2 as §4.4:**
- Create `graph-query-api/openapi/fabric-gql.yaml` — OpenAPI spec for the `/query/graph`,
  `/query/telemetry`, and `/query/topology` endpoints using Fabric GQL and KQL.
- Update `scripts/agent_provisioner.py` to point `"fabric-gql"` at this new spec.

#### M5. `ingest/manifest.py` — Not mentioned anywhere

[ingest/manifest.py](graph-query-api/ingest/manifest.py) lines 43–65 contain old-format manifest
compat code that maps `cosmos["gremlin"]` → `"cosmosdb-gremlin"` and `cosmos["nosql"]` →
`"cosmosdb-nosql"` connectors.

**Action → Add to Phase 3 as §5.5.1:**
- Remove the `cosmos` key parsing branch entirely
- Old-format manifests with `cosmos:` blocks should be unsupported after this change
- Keep only the `data_sources:` format with `fabric-gql` / `fabric-kql` connectors

### 13.3 MODERATE GAPS — Additional frontend files

#### F1. `frontend/src/components/DataSourceCard.tsx` (line 15-16)

```tsx
'cosmosdb-gremlin': 'CosmosDB Gremlin',
'cosmosdb-nosql': 'CosmosDB NoSQL',
```

**Action → Add to Phase 5 as §7.10:** Remove these label mappings. Replace with Fabric labels only.

#### F2. `frontend/src/hooks/useScenarioUpload.ts` (lines 28, 129)

```tsx
selectedBackend: 'cosmosdb-gremlin' | 'fabric-gql';
const telemetryBackend = selectedBackend === 'fabric-gql' ? 'fabric-kql' : 'cosmosdb-nosql';
```

**Action → Add to Phase 5 as §7.11:** Remove `'cosmosdb-gremlin'` from union type. Hardcode
`telemetryBackend` to `'fabric-kql'`.

#### F3. `frontend/src/components/resource/ResourceToolbar.tsx` (line 8)

Contains `'cosmos-account'` in filter list.

**Action → Add to Phase 5 as §7.12:** Remove `'cosmos-account'` from toolbar filter.

### 13.4 MODERATE GAPS — Infrastructure & deployment

#### I1. `infra/modules/roles.bicep` — Gremlin RBAC needs removal (not just "keep")

The plan says "KEEP" but [roles.bicep](infra/modules/roles.bicep) lines 32-33, 268-277 contain
Gremlin-specific RBAC:
```bicep
param cosmosGremlinAccountName string = ''
resource cosmosGremlinAccount ...
resource containerAppGremlinContributor ...
```

**Action → Update Phase 4 §6.5:** Remove `cosmosGremlinAccountName` param and the
`containerAppGremlinContributor` role assignment. Keep the NoSQL account RBAC.

#### I2. `infra/main.json` — Compiled ARM template

Not explicitly mentioned. Must be regenerated (`az bicep build`) or deleted after Bicep changes.

**Action → Add to Phase 4 §6.6:** `az bicep build -f infra/main.bicep --outfile infra/main.json` or delete if not used.

#### I3. `.azure/*/` environment configs (7 directories)

Each `azd` environment has `.env` files with `COSMOS_GREMLIN_*` and `GRAPH_BACKEND=cosmosdb`.

**Action → Add to Phase 7 §9.3.1:**
```bash
find .azure -name ".env" -exec sed -i '/COSMOS_GREMLIN/d' {} \;
find .azure -name ".env" -exec sed -i 's/GRAPH_BACKEND=cosmosdb/GRAPH_BACKEND=fabric-gql/' {} \;
```

#### I4. `azure_config_trash.env` — Contains real Cosmos keys

**Action → Add to Phase 7 §9.3.2:** Delete this file entirely — it's a security risk with real keys.

### 13.5 LOW GAPS — Comments, docs, reference material

| File | Reference | Action |
|------|-----------|--------|
| `backends/fabric.py` docstring | "CosmosDBGremlinBackend" (2x) | Clean up comments |
| Root `pyproject.toml` | `gremlinpython>=3.7.0` dep | Remove (§9.1 only covers graph-query-api toml) |
| `Dockerfile` line 5 | "Gremlin/telemetry queries" comment | Update comment |
| `README.md` | Gremlin in architecture table, tree, env var table | Update |
| `.github/copilot-instructions.md` | "Cosmos DB Gremlin", `gremlinpython`, provisioning steps | Update |
| `custom_skills/react-force-graph-2d/references/backend-integration.md` | `COSMOS_GREMLIN_ENDPOINT`, `COSMOS_GREMLIN_KEY` | Update reference doc |
| `fabric_implementation_references/` | Historical Cosmos references (many files) | Leave as-is (reference archive) |
| Documentation files in `documentation/` | Various arch docs with Cosmos references | Update as encountered |

### 13.6 CRITICAL IMPLEMENTATION GAP — Telemetry ingest has no Fabric pathway

The **query** side is ready: `router_telemetry.py` dispatches to `FabricKQLBackend` when
`ctx.telemetry_backend_type == "fabric-kql"` — this works.

But the **ingest** side (`ingest/telemetry_ingest.py`) is **100% Cosmos NoSQL**:
- Uses `get_cosmos_client()` directly
- Writes CSV rows to CosmosDB NoSQL containers
- No Fabric Eventhouse ingest pathway exists

**Options (choose one before executing the plan):**

1. **Implement Eventhouse ingest** — Use `azure-kusto-ingest` SDK to stream CSV data into Eventhouse
   tables via Kusto streaming ingestion or queued ingestion.
2. **Lakehouse CSV upload** — Upload CSVs to a Fabric Lakehouse via OneLake API, then create
   KQL database shortcuts to expose the data in Eventhouse.
3. **Stub with error** — Replace the upload handler with a clear error:
   `"Telemetry ingest requires Fabric Eventhouse — upload via Lakehouse pipeline"`.

**Recommendation:** Option 3 for initial cut (unblocks the stripping), then implement Option 1
or 2 as a follow-up.

### 13.7 Revised file counts

| Category | Original estimate | Revised |
|----------|------------------|---------|
| Files to delete | 5 files + 1 dir | 6 files + 1 dir (add `azure_config_trash.env`) |
| Files to modify | ~25 | **~38** |
| Files to create | 0 | **1** (`openapi/fabric-gql.yaml`) |

### 13.8 Updated execution order

```
Phase 1  →  Delete files (BUT: fix ingest/__init__.py and telemetry_ingest.py imports FIRST)
Phase 2  →  Backend & config + create Fabric OpenAPI spec (§4.4)
Phase 3  →  Routers & ingest + api/app/routers/config.py (§5.9) + manifest.py (§5.5.1)
Phase 4  →  Infrastructure: Bicep + roles.bicep Gremlin RBAC + main.json regen
Phase 5  →  Frontend: original 9 files + DataSourceCard, useScenarioUpload, ResourceToolbar
Phase 6  →  Scripts + deploy.sh (§8.5) + hooks/postprovision.sh (§8.6)
Phase 7  →  Dependencies (both pyproject.toml files) + .azure/ envs + trash env + docs
```
