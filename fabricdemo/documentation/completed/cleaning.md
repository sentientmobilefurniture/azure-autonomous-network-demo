# Codebase Audit — fabricdemo

**Date**: 2025-02-19
**Scope**: Full project audit of `/projects/autonomous-network-demo/fabricdemo`
**Categories**: Bugs, Dead Code, Config Issues, Error Handling, Security, Performance, Concurrency
**Status**: ✅ All 68 fixes implemented (2025-02-19)

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 4 |
| High | 9 |
| Medium | 25 |
| Low | 30 |
| **Total** | **68** |

---

## Critical

### C-1 — Dockerfile missing COPY for `stores/`, `adapters/`, `services/` directories

| Field | Value |
|-------|-------|
| **Category** | Bug / Deployment |
| **File** | `graph-query-api/Dockerfile` |
| **Line(s)** | 14–15 |
| **Description** | The application imports from `stores/`, `adapters/`, and `services/`, but the Dockerfile only copies `backends/` and `openapi/`. The container crashes with `ModuleNotFoundError` at runtime for any code path that touches interactions, cosmos, or blob uploads. |
| **Fix** | Add `COPY stores/ ./stores/`, `COPY adapters/ ./adapters/`, `COPY services/ ./services/` after the existing COPY lines. |

### C-2 — `getScenario()` permanently caches a rejected promise on fetch failure

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `frontend/src/config.ts` |
| **Line(s)** | 34–46 |
| **Description** | If the API is down at startup, `_fetchPromise` is a rejected promise and `_cached` is never set. All subsequent calls return the same rejected promise — the app can never load the scenario without a full page reload. |
| **Fix** | Add a `.catch()` that clears `_fetchPromise` so subsequent calls retry: `.catch((err) => { _fetchPromise = null; throw err; })` |

### C-3 — `test_orchestrator.py` double-appends `/api/projects/` path

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `scripts/testing_scripts/test_orchestrator.py` |
| **Line(s)** | 80–83 |
| **Description** | `PROJECT_ENDPOINT` is already a full project-scoped URL (e.g., `https://aif-xxx.services.ai.azure.com/api/projects/proj-xxx`). The code does `endpoint = f"{base_endpoint}/api/projects/{project_name}"`, doubling the path: `.../api/projects/proj-xxx/api/projects/proj-xxx`. This causes a 404 at runtime. |
| **Fix** | Use `PROJECT_ENDPOINT` directly: `endpoint = os.environ["PROJECT_ENDPOINT"].rstrip("/")` |

### C-4 — OpenAPI spec `X-Graph` required header ignored by implementation

| Field | Value |
|-------|-------|
| **Category** | API Contract Mismatch |
| **File** | `graph-query-api/openapi/mock.yaml` |
| **Line(s)** | 43–51, 83–91 |
| **Description** | The mock OpenAPI spec defines `X-Graph` as a **required** header for `/query/graph` and `/query/telemetry`, but the router endpoints don't read this header — they use `get_scenario_context()`. Agents are forced to send a header that is silently ignored; if omitted, spec validation rejects the request. |
| **Fix** | Remove the `X-Graph` parameter from the OpenAPI spec (leftover from a previous design). |

---

## High

### H-1 — OpenAPI spec `container_name` field mismatch on `/query/telemetry`

| Field | Value |
|-------|-------|
| **Category** | API Contract Mismatch |
| **File** | `graph-query-api/openapi/mock.yaml` |
| **Line(s)** | 95–115 |
| **Description** | The spec requires `container_name` in the telemetry request body, but `TelemetryQueryRequest` in `models.py` only has a `query` field. Agents send `container_name` which is silently ignored. |
| **Fix** | Remove `container_name` from the OpenAPI spec's required list and properties, or add it to `TelemetryQueryRequest`. |

### H-2 — Three Bicep params not wired in `.bicepparam`

| Field | Value |
|-------|-------|
| **Category** | Config Issue |
| **File** | `infra/main.bicepparam` |
| **Line(s)** | End of file (missing) |
| **Description** | `main.bicep` declares params `defaultScenario`, `runbooksIndexName`, and `ticketsIndexName`, and `deploy.sh` sets them via `azd env set`. But `main.bicepparam` has no `readEnvironmentVariable()` calls for them. Result: empty `DEFAULT_SCENARIO` and generic index names in production. |
| **Fix** | Add: `param defaultScenario = readEnvironmentVariable('DEFAULT_SCENARIO', '')`, `param runbooksIndexName = readEnvironmentVariable('RUNBOOKS_INDEX_NAME', 'runbooks-index')`, `param ticketsIndexName = readEnvironmentVariable('TICKETS_INDEX_NAME', 'tickets-index')` |

### H-3 — telecom-playground generators don't produce all required CSVs

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `data/scenarios/telecom-playground/scripts/generate_topology.py` |
| **Line(s)** | All |
| **Description** | `graph_schema.yaml` defines 3 additional vertex types (`PhysicalConduit`, `AmplifierSite`, `Advisory`) and 3 additional edge/fact tables. The generator scripts are identical to telco-noc and don't produce these 6 CSV files. Running `generate_all.sh` would overwrite `DimCoreRouter.csv` without the `FirmwareVersion` column that the schema requires. |
| **Fix** | Update telecom-playground generators to include the additional entity generators and add `FirmwareVersion` to `generate_core_routers()`. |

### H-4 — Duplicate `FABRIC_API_URL` and `FABRIC_SCOPE` definitions

| Field | Value |
|-------|-------|
| **Category** | Config Issue |
| **File** | `graph-query-api/fabric_discovery.py` L39–40, `graph-query-api/adapters/fabric_config.py` L19–20 |
| **Line(s)** | Multiple |
| **Description** | `FABRIC_API_URL` and `FABRIC_SCOPE` are read from `os.getenv()` in two separate modules. `backends/fabric.py` imports from `adapters.fabric_config`, while `fabric_discovery.py` uses its own copy. They could silently diverge. |
| **Fix** | Consolidate to a single source of truth in `adapters/fabric_config.py`; have `fabric_discovery.py` import from there. |

### H-5 — Duplicate `FABRIC_WORKSPACE_ID` definitions

| Field | Value |
|-------|-------|
| **Category** | Config Issue |
| **File** | `graph-query-api/config.py` L50, `graph-query-api/adapters/fabric_config.py` L26 |
| **Line(s)** | 50, 26 |
| **Description** | `FABRIC_WORKSPACE_ID` is read independently in both `config.py` and `adapters/fabric_config.py`. Same divergence risk. |
| **Fix** | Consolidate to one location. |

### H-6 — Three separate `DefaultAzureCredential` instances in graph-query-api

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `graph-query-api/config.py` L22, `graph-query-api/fabric_discovery.py` L73, `graph-query-api/backends/fabric_kql.py` L40 |
| **Line(s)** | Multiple |
| **Description** | Three separate `DefaultAzureCredential` instances are created instead of using the shared `config.get_credential()`. Each has its own token cache, wasting resources and potentially causing auth inconsistencies. |
| **Fix** | Have `fabric_discovery.py` and `backends/fabric_kql.py` import and use `config.get_credential()`. |

### H-7 — TOCTOU race condition in `get_fabric_config()`

| Field | Value |
|-------|-------|
| **Category** | Concurrency |
| **File** | `graph-query-api/fabric_discovery.py` |
| **Line(s)** | 236–247 |
| **Description** | Cache check is inside `_cache_lock`, but discovery runs outside the lock. Two concurrent threads could both see an expired cache and both run `_discover_fabric_config()` simultaneously. |
| **Fix** | Hold the lock during discovery or use a "discovery in progress" sentinel. |

### H-8 — `get_cosmos_client()` raises HTTPException during module import

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **File** | `graph-query-api/cosmos_helpers.py` |
| **Line(s)** | 37–38 |
| **Description** | `get_cosmos_client()` raises `HTTPException(503)` when `COSMOS_NOSQL_ENDPOINT` is not configured. This can be called during module import via `stores/__init__.py` → `CosmosDocumentStore.__init__` → `get_or_create_container`, crashing the app at startup even for backends like `mock` that don't need Cosmos. |
| **Fix** | Defer Cosmos initialization to first actual use, or catch the error at import time and set a fallback. |

### H-9 — `SCENARIO.name` missing from `fetchInteractions` effect dependency array

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `frontend/src/App.tsx` |
| **Line(s)** | 63–65 |
| **Description** | `useEffect(() => { fetchInteractions(SCENARIO.name); }, [fetchInteractions])` — `SCENARIO.name` is not in the dependency array. On mount `SCENARIO.name` is `""` (default), and when the scenario loads the effect never re-runs, so interactions are fetched for the wrong (empty) scenario. |
| **Fix** | Add `SCENARIO.name` to the dep array: `[fetchInteractions, SCENARIO.name]` |

---

## Medium

### M-1 — Incorrect exception types caught in `_load_stub_agent_names()`

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `api/app/routers/alert.py` |
| **Line(s)** | 42 |
| **Description** | `except (FileNotFoundError, json.JSONDecodeError)` catches exceptions from the old file-based agent discovery. Current `get_agent_list()` calls Foundry over the network — it will never raise these. Real failures (`HttpResponseError`, `ClientAuthenticationError`) propagate unhandled. |
| **Fix** | Change to `except Exception:` since this is a best-effort lookup with a fallback. |

### M-2 — `_get_credential()` singleton not thread-safe (2 copies)

| Field | Value |
|-------|-------|
| **Category** | Concurrency |
| **File** | `api/app/agent_ids.py` L46–51, `api/app/orchestrator.py` L37–42 |
| **Line(s)** | Multiple |
| **Description** | Both modules have their own `_credential = None` / `_get_credential()` singleton. Neither is thread-safe. Maintaining two independent singletons is unnecessary duplication. |
| **Fix** | Extract credential management into a shared module (e.g., `app/auth.py`) with a `threading.Lock`. |

### M-3 — `run_complete` emitted after error on silent-failure path

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `api/app/orchestrator.py` |
| **Line(s)** | 417–422 |
| **Description** | When a run produces no response text (silent failure), `handler.run_failed` is `False`. `run_complete` is emitted after the `error` event, contradicting it. The frontend receives both error and completion events. |
| **Fix** | Track a `_error_emitted` flag and skip `run_complete` when an error was already sent. |

### M-4 — `_event_loop` in `LogBroadcaster` overwritten by last subscriber

| Field | Value |
|-------|-------|
| **Category** | Concurrency |
| **File** | `api/app/log_broadcaster.py` L56 |
| **Line(s)** | 56 |
| **Description** | `self._event_loop` is set to `asyncio.get_running_loop()` each time `subscribe()` is called. If multiple SSE subscribers connect, the last one's loop overwrites the previous. |
| **Fix** | Store the event loop per-queue instead of per-broadcaster. |

### M-5 — `SCENARIO_NAME` / `_manifest` computed once at import time

| Field | Value |
|-------|-------|
| **Category** | Config Issue |
| **File** | `api/app/routers/config.py` |
| **Line(s)** | 30, 108–109 |
| **Description** | Values are computed at import from `os.getenv("DEFAULT_SCENARIO", "")`. If the env var is set after import or changed at runtime, the API serves stale data. |
| **Fix** | Document that changing `DEFAULT_SCENARIO` requires restart, or make these lazy-loaded. |

### M-6 — Data-ops log endpoint receives no events (dead filter prefixes)

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `api/app/routers/logs.py` |
| **Line(s)** | 40–42 |
| **Description** | Data-ops broadcaster filters for `"app.fabric"` or `"api.config"`, but no logger uses these names. Loggers use `__name__` (e.g., `"app.routers.config"`). The `fabric_provision.py` module was deleted. The data-ops SSE endpoint will **never receive any log events**. |
| **Fix** | Update filter prefixes to match actual logger names, or remove the data-ops broadcaster if no longer needed. |

### M-7 — `/api/services/health` reports "connected" without probing

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `api/app/main.py` |
| **Line(s)** | 88–129 |
| **Description** | The endpoint reports services as `"connected"` simply because their env vars are set. No actual connectivity check is performed. `partial` and `error_count` are always 0. |
| **Fix** | Rename statuses to `"configured"` / `"not_configured"`, or add real connectivity probes. |

### M-8 — `run_complete` references handler from last retry iteration only

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `api/app/orchestrator.py` |
| **Line(s)** | 417–422 |
| **Description** | After the retry for-loop, `handler.ui_step` and `handler.total_tokens` reflect only the last attempt, not cumulative totals. `handler._elapsed()` measures only from the last attempt's t0. |
| **Fix** | Track cumulative step count, total tokens, and overall start time outside the loop. |

### M-9 — Dead module: `prompt_helpers.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/prompt_helpers.py` |
| **Line(s)** | 1–37 |
| **Description** | `get_next_version()` is never imported or called anywhere. References non-existent `router_prompts.py` and `router_ingest.py`. |
| **Fix** | Delete the file. |

### M-10 — Dead module: `search_indexer.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/search_indexer.py` |
| **Line(s)** | 1–206 |
| **Description** | `create_search_index()` is never imported or called. Leftover from previous version with ingest endpoints. |
| **Fix** | Delete the file. |

### M-11 — Dead module: `sse_helpers.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/sse_helpers.py` |
| **Line(s)** | 1–77 |
| **Description** | `SSEProgress` and `sse_upload_response()` are never imported or called. References non-existent `router_ingest.py`. |
| **Fix** | Delete the file. |

### M-12 — Dead module: `services/blob_uploader.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/services/blob_uploader.py` |
| **Line(s)** | 1–68 |
| **Description** | `upload_files_to_blob()` is never imported or called. Leftover from removed ingest functionality. |
| **Fix** | Delete the file. |

### M-13 — Dead module: `stores/mock_store.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/stores/mock_store.py` |
| **Line(s)** | 1–53 |
| **Description** | `MockDocumentStore` is never imported, registered, or used anywhere. Not in `stores/__init__.py`. |
| **Fix** | Register it for mock/test mode, or delete the file. |

### M-14 — Dead adapters: unused exports in `adapters/fabric_config.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/adapters/fabric_config.py` |
| **Line(s)** | 43–75 |
| **Description** | `FABRIC_WORKSPACE_CONNECTED`, `FABRIC_CONFIGURED`, `FABRIC_QUERY_READY`, `is_fabric_configured()`, and `fabric_asset_names()` are defined but never used outside this file. |
| **Fix** | Remove unused exports. |

### M-15 — Unused imports: `asyncio`, `json`, `datetime`, `timezone` in `main.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/main.py` |
| **Line(s)** | 34–39 |
| **Description** | Four imports are never used. |
| **Fix** | Remove them. |

### M-16 — Unused imports in `router_graph.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/router_graph.py` |
| **Line(s)** | 10–12 |
| **Description** | `GRAPH_BACKEND`, `GraphBackend`, and `ScenarioContext` are imported but never referenced. |
| **Fix** | Remove unused imports. |

### M-17 — Unused import `time` in `router_telemetry.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/router_telemetry.py` |
| **Line(s)** | 11 |
| **Description** | `time` is imported but never used. |
| **Fix** | Remove the import. |

### M-18 — `close_cosmos_client()` never called during shutdown

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `graph-query-api/cosmos_helpers.py` |
| **Line(s)** | 43–52 |
| **Description** | `close_cosmos_client()` is defined but never called. The app's `_lifespan` only calls `close_graph_backend()`, leaving the Cosmos client connection pool open. |
| **Fix** | Call `close_cosmos_client()` in the lifespan shutdown block in `main.py`. |

### M-19 — `threading.Lock` used in async topology endpoint

| Field | Value |
|-------|-------|
| **Category** | Concurrency |
| **File** | `graph-query-api/router_topology.py` |
| **Line(s)** | 68–72 |
| **Description** | `_topo_cache` and `_topo_lock` use `threading.Lock`, but the topology endpoint is `async`. Using a regular lock blocks the event loop under high concurrency. |
| **Fix** | Use `asyncio.Lock` instead. |

### M-20 — `deploy.sh` duplicate `GPT_CAPACITY_1K_TPM` in config

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `deploy.sh` |
| **Line(s)** | 739, 757 |
| **Description** | The heredoc that writes `azure_config.env` includes `GPT_CAPACITY_1K_TPM` twice. The second value silently overrides the first when sourced. |
| **Fix** | Remove the duplicate under "Deployment settings". |

### M-21 — Inconsistent `EVENTHOUSE_NAME` default

| Field | Value |
|-------|-------|
| **Category** | Config Issue |
| **File** | `scripts/fabric/_config.py` |
| **Line(s)** | 43 |
| **Description** | Defaults to `"NetworkTelemetryEH_3117"` while `azure_config.env.template` sets `"NetworkTelemetryEH"`. Creates wrong eventhouse name if env var is unset. |
| **Fix** | Change default to `"NetworkTelemetryEH"`. |

### M-22 — Hardcoded `FABRIC_WORKSPACE_ID` in template

| Field | Value |
|-------|-------|
| **Category** | Config Issue |
| **File** | `azure_config.env.template` |
| **Line(s)** | 57 |
| **Description** | Template contains a hardcoded workspace ID `cfd2b9e2-83d8-462d-a2ec-61369c4c8600`. Users copying the template get a wrong workspace ID. |
| **Fix** | Change to `FABRIC_WORKSPACE_ID=` (empty). |

### M-23 — CORS `*` hardcoded in Bicep overrides user config

| Field | Value |
|-------|-------|
| **Category** | Security |
| **File** | `infra/main.bicep` |
| **Line(s)** | 199 |
| **Description** | The Bicep template hardcodes `CORS_ORIGINS: '*'` for the Container App. This overrides whatever the user sets in `azure_config.env`. |
| **Fix** | Remove hardcoded `*` and either pass as a Bicep parameter or derive from the app's own URI. |

### M-24 — `provision_cosmos.py` uses hardcoded partition key fields

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `scripts/provision_cosmos.py` |
| **Line(s)** | 118–122 |
| **Description** | `_clear_container` queries `SourceNodeType` and `LinkId` as partition keys. Hardcoded to only work with current tables. New containers with different keys will fail silently. |
| **Fix** | Pass the partition key path from container config and use it dynamically. |

### M-25 — `postprovision.sh` uses `DEFAULT_SCENARIO` before it's reliably available

| Field | Value |
|-------|-------|
| **Category** | Config Issue |
| **File** | `hooks/postprovision.sh` |
| **Line(s)** | 25 |
| **Description** | Uses `${DEFAULT_SCENARIO}` to construct blob paths before any config file is sourced. When running `azd up` directly (not through `deploy.sh`), may be empty, causing uploads to target the wrong path. |
| **Fix** | Add fallback: read from azd env first, default to `telecom-playground`. |

---

## Low

### L-1 — Unused `load_agents_from_file()` function

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `api/app/orchestrator.py` |
| **Line(s)** | 86–89 |
| **Description** | Defined but never called. Vestige of file-based agent discovery. |
| **Fix** | Remove the function. |

### L-2 — Unused imports in `orchestrator.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `api/app/orchestrator.py` |
| **Line(s)** | 22, 25, 27 |
| **Description** | `Path`, `load_dotenv`, and `PROJECT_ROOT`/`CONFIG_FILE` are imported but never used directly. |
| **Fix** | Remove `Path` and `load_dotenv`. Change the `app.paths` import to an explicit side-effect import. |

### L-3 — Unused import `Path` in `alert.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `api/app/routers/alert.py` |
| **Line(s)** | 13 |
| **Description** | `from pathlib import Path` imported but never used. |
| **Fix** | Remove the import. |

### L-4 — Unused `request` parameter in `get_resource_graph()`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `api/app/routers/config.py` |
| **Line(s)** | 297 |
| **Description** | `request: Request` is declared but never read inside the function body. |
| **Fix** | Remove the parameter. |

### L-5 — Duplicate `_get_project_client()` with inconsistent error handling

| Field | Value |
|-------|-------|
| **Category** | Dead Code / Maintenance |
| **File** | `api/app/agent_ids.py` L54–66, `api/app/orchestrator.py` L73–83 |
| **Line(s)** | Multiple |
| **Description** | Nearly identical logic. `agent_ids.py` returns `None` on missing env vars while `orchestrator.py` raises `KeyError`. |
| **Fix** | Move to a shared module. |

### L-6 — `_load_scenario_yaml()` doesn't catch invalid YAML

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **File** | `api/app/routers/config.py` |
| **Line(s)** | 38–46 |
| **Description** | If YAML file contains invalid YAML, `yaml.safe_load()` raises an exception at module import, crashing the API. |
| **Fix** | Wrap in try/except for `yaml.YAMLError`. |

### L-7 — `os.environ[]` KeyError messages are not user-friendly

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **File** | `api/app/orchestrator.py` |
| **Line(s)** | 77–78 |
| **Description** | `os.environ["PROJECT_ENDPOINT"]` raises `KeyError` with just the bare key name, which is not descriptive. |
| **Fix** | Use `os.environ.get()` with an explicit error message. |

### L-8 — Stale `__pycache__` files for deleted modules

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `api/app/routers/__pycache__/upload_jobs.cpython-312.pyc`, `api/app/routers/__pycache__/fabric_provision.cpython-312.pyc` |
| **Line(s)** | N/A |
| **Description** | Compiled bytecode for deleted modules `upload_jobs.py` and `fabric_provision.py`. |
| **Fix** | Delete the stale `.pyc` files. |

### L-9 — `data_source` field reuses `spec_template` for OpenAPI tools

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `api/app/routers/config.py` |
| **Line(s)** | 66–67 |
| **Description** | Both `spec_template` and `data_source` are set to `t.get("spec_template", "")`. If the value doesn't match any `data_sources` dict key, edge linking silently fails. |
| **Fix** | Add a dedicated `data_source` field to the YAML tool schema. |

### L-10 — CORS `allow_methods=["*"]` and `allow_headers=["*"]`

| Field | Value |
|-------|-------|
| **Category** | Security |
| **File** | `api/app/main.py` |
| **Line(s)** | 39–45 |
| **Description** | CORS middleware allows all methods and headers. Fine for demo, should be restricted for production. |
| **Fix** | Restrict to actual methods used (`GET`, `POST`, `OPTIONS`). |

### L-11 — `_discover_agents()` cache refresh not atomic

| Field | Value |
|-------|-------|
| **Category** | Concurrency |
| **File** | `api/app/agent_ids.py` |
| **Line(s)** | 143–152 |
| **Description** | TTL check and network refresh are not atomic. Multiple threads can trigger simultaneous discovery calls (thundering herd). |
| **Fix** | Use a lock or "in-flight" flag to ensure only one thread refreshes. |

### L-12 — Unused import `os` in `backends/fabric_kql.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/backends/fabric_kql.py` |
| **Line(s)** | 14 |
| **Description** | `os` is imported but never used. |
| **Fix** | Remove the import. |

### L-13 — Unused `FABRIC_WORKSPACE_ID` in `config.py`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `graph-query-api/config.py` |
| **Line(s)** | 50 |
| **Description** | Module-level variable never imported by any module. Duplicate of the one in `adapters/fabric_config.py`. |
| **Fix** | Remove from `config.py`. |

### L-14 — `AI_SEARCH_KEY` inconsistent with RBAC-only approach

| Field | Value |
|-------|-------|
| **Category** | Config Issue |
| **File** | `graph-query-api/router_health.py` |
| **Line(s)** | 28 |
| **Description** | Supports API key auth for search while the rest of the codebase uses `DefaultAzureCredential` (RBAC). Inconsistent and less secure. |
| **Fix** | Remove API key support and use only `DefaultAzureCredential`. |

### L-15 — `FabricKQLBackend` registered as graph backend

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `graph-query-api/backends/__init__.py` |
| **Line(s)** | 167–172 |
| **Description** | `FabricKQLBackend` is registered as `"fabric-kql"` in the graph backend registry but is a telemetry backend. It doesn't implement the `GraphBackend` protocol. |
| **Fix** | Don't register `FabricKQLBackend` in the graph backend registry. |

### L-16 — Request bodies logged up to 1000 bytes

| Field | Value |
|-------|-------|
| **Category** | Security |
| **File** | `graph-query-api/main.py` |
| **Line(s)** | 90–92 |
| **Description** | Could log sensitive query content or PII. The API runs inside a VNet but this is still a concern. |
| **Fix** | Reduce logged body size or make it configurable. |

### L-17 — Per-request `FabricKQLBackend()` instantiation

| Field | Value |
|-------|-------|
| **Category** | Performance |
| **File** | `graph-query-api/router_telemetry.py` |
| **Line(s)** | 53 |
| **Description** | `FabricKQLBackend()` is created on every request. The client cache inside it is per-instance, so it's discarded after each request — ineffective caching. |
| **Fix** | Use a module-level singleton. |

### L-18 — `backends/mock.py` crashes on missing fixture at import

| Field | Value |
|-------|-------|
| **Category** | Robustness |
| **File** | `graph-query-api/backends/mock.py` |
| **Line(s)** | 20 |
| **Description** | `_FIXTURE_PATH.read_text()` at import time crashes with `FileNotFoundError` if `mock_topology.json` is missing — even when `mock` backend isn't selected. Module is always imported by `backends/__init__.py`. |
| **Fix** | Wrap in try/except and return empty data, or defer loading. |

### L-19 — `fabric.py` `close()` may fail during loop shutdown

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `graph-query-api/backends/fabric.py` |
| **Line(s)** | 409–418 |
| **Description** | `close()` tries to schedule `aclose()` as a fire-and-forget task. If called during shutdown when the loop is closing, `create_task` may fail silently, leaving httpx client unclosed. |
| **Fix** | Use `await self._client.aclose()` in an async close method. |

### L-20 — `log_broadcaster.py` duplicate issue in graph-query-api

| Field | Value |
|-------|-------|
| **Category** | Concurrency |
| **File** | `graph-query-api/log_broadcaster.py` |
| **Line(s)** | 47 |
| **Description** | Same `_event_loop` overwrite-by-last-subscriber issue as API's `log_broadcaster.py` (M-4). |
| **Fix** | Store event loop per-queue. |

### L-21 — `broad_exception_catcher` for interactions routes

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **File** | `graph-query-api/router_interactions.py` |
| **Line(s)** | 101–103 |
| **Description** | `get_interaction` and `delete_interaction` catch broad `Exception` and return 404. This masks real errors (e.g., Cosmos connection failures) as "not found". |
| **Fix** | Catch `CosmosResourceNotFoundError` specifically for 404; let others propagate as 500. |

### L-22 — `formatTimeAgo` doesn't guard against invalid dates

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `frontend/src/utils/formatTime.ts` |
| **Line(s)** | 2–7 |
| **Description** | `new Date("garbage").getTime()` returns NaN, producing `"NaNd ago"`. |
| **Fix** | Add `if (isNaN(seconds)) return 'unknown';` |

### L-23 — Dead component: `ServiceHealthSummary.tsx`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `frontend/src/components/ServiceHealthSummary.tsx` |
| **Line(s)** | All |
| **Description** | Never imported or rendered. Superseded by `HealthButtonBar` + `ServiceHealthPopover`. |
| **Fix** | Delete the file. |

### L-24 — Dead component: `DataSourceBar.tsx`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `frontend/src/components/DataSourceBar.tsx` |
| **Line(s)** | All |
| **Description** | Never imported by any active component. Superseded by `HealthButtonBar`. |
| **Fix** | Delete the file. |

### L-25 — Dead component: `DataSourceCard.tsx`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `frontend/src/components/DataSourceCard.tsx` |
| **Line(s)** | All |
| **Description** | Only imported by dead `DataSourceBar.tsx`. Never rendered. |
| **Fix** | Delete the file. |

### L-26 — Dead component: `ActionButton.tsx`, `ProgressBar.tsx`, `ModalShell.tsx`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `frontend/src/components/ActionButton.tsx`, `ProgressBar.tsx`, `ModalShell.tsx` |
| **Line(s)** | All |
| **Description** | Never imported or rendered anywhere. |
| **Fix** | Delete the files. |

### L-27 — Dead utility: `sseStream.ts`

| Field | Value |
|-------|-------|
| **Category** | Dead Code |
| **File** | `frontend/src/utils/sseStream.ts` |
| **Line(s)** | All (143 lines) |
| **Description** | `consumeSSE` and `uploadWithSSE` are exported but never imported anywhere. |
| **Fix** | Delete the file. |

### L-28 — `getComputedStyle` called per-node per-frame in canvas renderers

| Field | Value |
|-------|-------|
| **Category** | Performance |
| **File** | `frontend/src/components/graph/GraphCanvas.tsx` L78–99, L145–153; `frontend/src/components/resource/ResourceCanvas.tsx` L47–112, L171–185 |
| **Line(s)** | Multiple |
| **Description** | `getComputedStyle(document.documentElement)` is called inside `nodeCanvasObject` (once per node per frame) and `linkColor` callbacks. For a 200-node graph at 60fps, this is ~12,000+ calls per second. |
| **Fix** | Cache CSS custom property values in a `useMemo`/`useEffect` that reads them once (and on theme change). |

### L-29 — `nuclear_teardown.sh` missing execute permission

| Field | Value |
|-------|-------|
| **Category** | Bug |
| **File** | `infra/nuclear_teardown.sh` |
| **Line(s)** | N/A |
| **Description** | File has `644` permissions. Running `./nuclear_teardown.sh` fails with "permission denied". All other scripts have `755`. |
| **Fix** | `chmod +x infra/nuclear_teardown.sh` |

### L-30 — `deploy.sh` step numbering gap (Step 8 missing)

| Field | Value |
|-------|-------|
| **Category** | Dead Code / Cosmetic |
| **File** | `deploy.sh` |
| **Line(s)** | 978 |
| **Description** | Step numbering jumps from Step 7 to Step 9. Step 8 was removed but numbering wasn't updated. |
| **Fix** | Renumber Step 9 to Step 8. |

---

## Fix Priority

### Immediate (service-impacting)

1. **C-1** — graph-query-api Dockerfile missing directories (container crashes)
2. **C-4 / H-1** — OpenAPI spec mismatches break agent tool calls
3. **H-2** — Missing `.bicepparam` bindings → empty `DEFAULT_SCENARIO` in production
4. **C-2** — Frontend scenario caching permanently broken on first failure
5. **H-9** — Interactions fetched for empty scenario name

### Soon (correctness)

6. **C-3** — Test orchestrator double path (tests broken)
7. **M-6** — Data-ops log endpoint completely non-functional
8. **M-3 / M-8** — `run_complete` emitted incorrectly on failure/retry
9. **M-1** — Wrong exception types in stub agent name loader
10. **H-8** — Cosmos init crashes app for non-cosmos backends

### Cleanup (maintenance)

11. **M-9 through M-17** — Remove 5 dead modules and unused imports in graph-query-api
12. **L-23 through L-27** — Delete 7 dead frontend components/utilities
13. **L-1 through L-5** — Remove dead code in API backend
14. **H-4 / H-5 / H-6 / M-2** — Consolidate duplicated config/credential code
