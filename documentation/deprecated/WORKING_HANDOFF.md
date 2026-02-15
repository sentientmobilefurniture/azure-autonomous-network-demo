# Working Handoff — Bug Fix Session

> **Date:** 2025-07-18
> **Session scope:** Fix bugs 1–4 from BUGSTOFIX.md + deployment + documentation
> **Environment:** Azure-deployed only (no local deployment)

---

## 1. What Was Done

### Bugs Fixed (all code-only — no infra changes)

| # | Bug | Root Cause | Fix | Files Changed |
|---|-----|-----------|-----|---------------|
| 1 | Prompt upload fails: "Id contains illegal chars" | Cosmos NoSQL rejects `/` in document IDs. ID format was `scenario/name/v1` | Changed delimiter to `__` → `scenario__name__v1` | `router_prompts.py`, `router_ingest.py` |
| 2 | Prompt table named `platform-config` instead of `SCENARIONAME-prompts` | Hardcoded shared database name | Per-scenario databases: `{scenario}-prompts` with `_db_name_for_scenario()` | `router_prompts.py`, `router_ingest.py` |
| 3 | Agents initialized without prompts | **Three sub-causes** — see below | Multiple fixes | `router_prompts.py`, `config.py`, `agent_provisioner.py` |
| 4 | Graph topology empty via agents (g.V() returns nothing) | OpenAPI specs had no `X-Graph` header → agents hit default `topology` graph instead of `telco-noc-topology` | Added `X-Graph` header param to both OpenAPI specs with `{graph_name}` placeholder substituted at provisioning | `cosmosdb.yaml`, `mock.yaml`, `agent_provisioner.py`, `config.py` |

### Bug 3 — Three Sub-Causes

1. **Prompts URL missing `?scenario=` filter** → `config.py` fetched all prompts instead of the selected scenario's. Fixed by adding `?scenario={scenario_prefix}&include_content=true`.

2. **ARM creation blocking reads** → `_get_prompts_container()` always ran ARM `begin_create_update_sql_database().result()` (10-30s blocking) even on read paths. The caller in `config.py` had a 10s timeout → timeout → no prompts → fallback defaults. Fixed by splitting into `ensure_created=True` (writes only) vs `False` (reads, default).

3. **Cosmos composite index requirement** → Query `ORDER BY c.agent, c.scenario, c.version DESC` requires a composite index not defined on the container. Cosmos returned 400, exception was silently caught by `except Exception`, returned `[]`. Agents got placeholder prompts ("You are a telemetry analysis agent."). Fixed by removing `ORDER BY` from Cosmos query and sorting in Python instead.

### Documentation Added

- 8 new lessons (§11–§18) appended to `azure_deployment_lessons.md`:
  - §11 Cosmos ID restrictions
  - §12 Per-scenario databases
  - §13 ARM blocking reads
  - §14 N+1 HTTP anti-pattern
  - §15 X-Graph header in OpenAPI
  - §16 azure_config.env vs container env vars
  - §17 Code-only redeployment
  - §18 Two-phase Cosmos create pattern

---

## 2. Files Modified (All Unstaged)

### `graph-query-api/router_prompts.py`
- Replaced `PLATFORM_DB = "platform-config"` with per-scenario `_db_name_for_scenario()`
- Added `_containers: dict[str, object] = {}` cache (was single `_container`)
- Added `_parse_scenario_from_id()` — splits on `__`
- `_get_prompts_container(scenario, *, ensure_created=False)` — reads skip ARM, writes use ARM
- Added `_list_prompt_databases()` — ARM listing of `*-prompts` databases
- `list_prompts()` — added `include_content` query param, removed `ORDER BY`, sort in Python
- `list_prompt_scenarios()` — uses `_list_prompt_databases()` instead of `SELECT DISTINCT`
- `get_prompt()` — derives scenario from ID via `_parse_scenario_from_id()`
- `create_prompt()` — ID format `scenario__name__v{n}`, `ensure_created=True`
- `update_prompt()`, `delete_prompt()` — derive scenario from ID

### `graph-query-api/router_ingest.py`
- `upload_prompts()` — passes `sc_name` and `ensure_created=True` to `_get_prompts_container()`
- Prompt ID format changed to `__` separator in two places (~L1259, ~L1292)

### `api/app/routers/config.py`
- Prompt fetch: single request with `?scenario={sc}&include_content=true` (was N+1)
- Timeout: 30s (was 10s)
- `GRAPH_QUERY_API_URI` fallback: uses `CONTAINER_APP_HOSTNAME` env var if primary not set
- Passes `graph_name=req.graph` to `provisioner.provision_all()`

### `scripts/agent_provisioner.py`
- `_load_openapi_spec()` — new `graph_name` parameter, replaces `{graph_name}` in spec text
- `provision_all()` — new `graph_name` parameter, passed to both OpenAPI tool spec loads

### `graph-query-api/openapi/cosmosdb.yaml`
- Added `X-Graph` header parameter to `/query/graph` and `/query/telemetry`
- `default: "{graph_name}"` — substituted at provisioning time

### `graph-query-api/openapi/mock.yaml`
- Same `X-Graph` header additions as `cosmosdb.yaml`

### `documentation/azure_deployment_lessons.md`
- Appended §11–§18 (315 lines)

### `documentation/ARCHITECTURE.md.bak` and `ARCHITECTURE.md.bak2`
- Backup copies created during session (not functional — just snapshots)

---

## 3. Deployment State

### What Needs Deploying

All code changes are **unstaged and undeployed**. To deploy:

```bash
cd ~/projects/autonomous-network-demo
azd deploy app          # ~60-90s, rebuilds container image
```

After deploy completes, re-provision agents through the UI:
1. Open the app URL
2. Click ⚙ Settings
3. Data Sources tab → select graph (`telco-noc-topology`), indexes, prompt set
4. Click **Provision Agents**

### No Infra Changes Needed

All fixes are code-only. No Bicep/env var changes. `azd deploy app` is sufficient — do NOT run `azd up`.

### Azure Environment

| Property | Value |
|----------|-------|
| Resource Group | `rg-cosmosv8b` |
| Location | `swedencentral` |
| Container App | `ca-app-{resourceToken}` (unified: nginx + API + graph-query-api) |
| Cosmos Gremlin | `cosmos-gremlin-frdnei7slkssy.gremlin.cosmos.azure.com` |
| Cosmos NoSQL | `cosmos-gremlin-frdnei7slkssy-nosql.documents.azure.com` |
| Gremlin DB | `networkgraph` |
| Gremlin Graph | `telco-noc-topology` |
| Telemetry DB | `telco-noc-telemetry` |
| Prompts DB | `telco-noc-prompts` (created by upload/create) |

---

## 4. Remaining / Unverified Items

### From BUGSTOFIX.md

| # | Bug | Status |
|---|-----|--------|
| 1 | Prompt upload "illegal chars" | **FIXED** — `__` delimiter |
| 2 | Wrong database name | **FIXED** — per-scenario `{scenario}-prompts` |
| 3 | Agents without prompts/tools | **FIXED** — 3 sub-causes resolved |
| 4 | Graph topology doesn't load via agents | **LIKELY FIXED** — X-Graph header added, but needs verification after deploy |

### Bug 4 Verification Steps

After deploying and re-provisioning agents:
1. Submit an alert in the UI
2. Check that GraphExplorerAgent's `step_complete` event shows actual graph data (vertices/edges) in its response — NOT `columns: [], data: []`
3. Check container logs for `X-Graph` header being received: look for the graph name in graph-query-api request logs
4. If still empty, check that the provisioned agent's OpenAPI spec has the correct graph name baked in (not `{graph_name}` literal)

### Potential Issues to Watch

1. **ARCHITECTURE.md is stale** — still references `platform-config` database and old ID format (`scenario/name/v1`) in some places. Consider updating.

2. **Dead code in router_ingest.py** — Lines ~125–605 contain OLD commented-out monolithic upload code. Should be cleaned up.

3. **Silent exception handling** — The `except Exception` pattern in `_query_scenario()` returns `[]` on ANY error. The ORDER BY fix resolved the specific Cosmos 400, but other errors would still be silently swallowed. Consider logging at `error` level instead of `warning`.

4. **BUGSTOFIX.md** — Should be updated to reflect fixed status. Current file still lists all bugs as open.

---

## 5. Architecture Quick Reference

### Request Flow (Agent → Graph Data)

```
Frontend POST /api/config/apply { graph: "telco-noc-topology", prompt_scenario: "telco-noc" }
  → config.py fetches GET http://127.0.0.1:8100/query/prompts?scenario=telco-noc&include_content=true
  → config.py calls provisioner.provision_all(graph_name="telco-noc-topology", prompts={...})
  → _load_openapi_spec() replaces {graph_name} → "telco-noc-topology" in OpenAPI YAML
  → Foundry agent created with OpenApiTool containing X-Graph default header

At investigation time:
  → Orchestrator delegates to GraphExplorerAgent
  → GraphExplorerAgent calls POST /query/graph with X-Graph: telco-noc-topology
  → get_scenario_context() reads header → ScenarioContext(graph_name="telco-noc-topology")
  → get_backend_for_context() returns cached CosmosDBGremlinBackend for that graph
  → Gremlin query executes against correct graph → returns data
```

### Per-Scenario Naming Convention

| Data Type | Name Pattern | Example |
|-----------|-------------|---------|
| Gremlin graph | `{scenario}-topology` | `telco-noc-topology` |
| Telemetry DB | `{scenario}-telemetry` | `telco-noc-telemetry` |
| Prompts DB | `{scenario}-prompts` | `telco-noc-prompts` |
| Runbooks index | `{scenario}-runbooks-index` | `telco-noc-runbooks-index` |
| Tickets index | `{scenario}-tickets-index` | `telco-noc-tickets-index` |
| Prompt doc ID | `{scenario}__{agent}__{version}` | `telco-noc__orchestrator__v1` |

### Key Config Paths (Inside Container)

| Item | Path |
|------|------|
| API code | `/app/api/app/` |
| graph-query-api code | `/app/graph-query-api/` |
| Scripts | `/app/scripts/` |
| OpenAPI specs | `/app/graph-query-api/openapi/` |
| agent_ids.json | `/app/scripts/agent_ids.json` |
| Frontend build | `/usr/share/nginx/html/` |

### Two Cosmos Accounts, Two Auth Methods

| Account | API | Auth | Env Vars |
|---------|-----|------|----------|
| `cosmos-gremlin-*` | Gremlin | Key (`COSMOS_GREMLIN_PRIMARY_KEY`) | `COSMOS_GREMLIN_ENDPOINT`, `COSMOS_GREMLIN_PRIMARY_KEY` |
| `cosmos-gremlin-*-nosql` | NoSQL | RBAC (`DefaultAzureCredential`) | `COSMOS_NOSQL_ENDPOINT` |

---

## 6. How to Continue

### If bugs are verified fixed after deploy:
1. Update BUGSTOFIX.md to mark bugs as resolved
2. Clean up ARCHITECTURE.md to reflect changes (per-scenario prompts, X-Graph header, `__` ID format)
3. Remove dead code in `router_ingest.py` (lines ~125–605)
4. Consider improving error logging in `_query_scenario()` — use `logger.error` instead of `logger.warning`

### If prompts still not passed after deploy:
1. Pull container logs: `az containerapp logs show --name <app> -g rg-cosmosv8b --type console`
2. Search for "prompts" or "Cosmos" errors
3. Check if `telco-noc-prompts` database exists in Cosmos Data Explorer
4. Test directly: `curl https://<app-url>/query/prompts?scenario=telco-noc&include_content=true`

### If graph queries still return empty:
1. Check container logs for the `X-Graph` header value in incoming requests
2. Verify the OpenAPI spec baked into the agent: look for `default: "telco-noc-topology"` (not `{graph_name}`)
3. Test directly: `curl -X POST https://<app-url>/query/graph -H "X-Graph: telco-noc-topology" -H "Content-Type: application/json" -d '{"query": "g.V().limit(5)"}'`

### Key files to read first:
- This file (WORKING_HANDOFF.md)
- `documentation/azure_deployment_lessons.md` (§11–§18)
- `documentation/ARCHITECTURE.md` (overall system, may be slightly stale)
- `documentation/BUGSTOFIX.md` (original bug descriptions)