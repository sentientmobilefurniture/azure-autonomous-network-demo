# Dead Code Cleanup — Implementation Plan

> **Scope:** `fabricdemo/` — source code, configs, scripts, infra, frontend  
> **Last verified:** 2026-02-20 — every item below confirmed via exhaustive grep + import-chain analysis  
> **Status:** Ready to implement  

---

## Table of Contents

1. [Phase 1 — Delete Entire Dead Files](#phase-1--delete-entire-dead-files) (~4,500 lines, zero risk)
2. [Phase 2 — Remove "Data Ops" Terminal Tab](#phase-2--remove-data-ops-terminal-tab) (3 files, ~50 lines)
3. [Phase 3 — Inline Dead Code Removal](#phase-3--inline-dead-code-removal) (API, graph-query-api, frontend)
4. [Phase 4 — Dependency Cleanup](#phase-4--dependency-cleanup) (3 pyproject.toml + 1 package.json)
5. [Phase 5 — Dockerfile Cleanup](#phase-5--dockerfile-cleanup) (2 COPY lines)
6. [Phase 6 — Refactoring Opportunities](#phase-6--refactoring-opportunities) (not dead code, but high-impact maintainability)
7. [Do NOT Delete — Verified Alive](#do-not-delete--verified-alive)
8. [Audit Corrections](#audit-corrections) (original claims that were wrong)
9. [Impact Summary](#impact-summary)

---

## Phase 1 — Delete Entire Dead Files

Every file below has **zero live importers or references**. Deletion has no impact on the running application.

### 1A. Frontend Components (7 files, 717 lines)

| # | File | Lines | Why Dead |
|---|------|------:|----------|
| 1 | `frontend/src/components/InteractionSidebar.tsx` | 183 | Not imported or rendered anywhere. Replaced by `SessionSidebar`. |
| 2 | `frontend/src/components/InvestigationPanel.tsx` | 66 | Not imported or rendered anywhere. Replaced by `ChatPanel` + `ChatInput`. |
| 3 | `frontend/src/components/DiagnosisPanel.tsx` | 100 | Not imported or rendered anywhere. Diagnosis shown inline via `DiagnosisBlock`. |
| 4 | `frontend/src/components/EmptyState.tsx` | 36 | Not imported or rendered anywhere. `ChatPanel` has its own inline empty state. |
| 5 | `frontend/src/components/AgentTimeline.tsx` | 129 | Only imported by the dead `InvestigationPanel.tsx` — transitively dead. |
| 6 | `frontend/src/components/AlertInput.tsx` | 123 | Only imported by the dead `InvestigationPanel.tsx` — transitively dead. (Reference in `useClickOutside.ts` is a comment, not an import.) |
| 7 | `frontend/src/components/ErrorBanner.tsx` | 80 | Only imported by the dead `InvestigationPanel.tsx` — transitively dead. |

### 1B. Frontend Hooks (3 files, 263 lines)

| # | File | Lines | Why Dead |
|---|------|------:|----------|
| 8 | `frontend/src/hooks/useInteractions.ts` | 63 | Not called anywhere. Replaced by `useSession()` + `useSessions()`. |
| 9 | `frontend/src/hooks/useInvestigation.ts` | 150 | Not called anywhere. Replaced by `useSession()` SSE stream model. |
| 10 | `frontend/src/hooks/useResourceGraph.ts` | 50 | Not called anywhere. `ResourceVisualizer` uses `useArchitectureGraph()`. |

### 1C. Scripts (3 files, 622 lines)

| # | File | Lines | Why Dead |
|---|------|------:|----------|
| 11 | `scripts/provision_cosmos.py` | 334 | Never called from `deploy.sh`, hooks, or `azure.yaml`. Root `pyproject.toml` doesn't include `azure-cosmos` — script can't run via `uv run`. |
| 12 | `scripts/fabric/collect_fabric_agents.py` | 192 | Never called. No `GRAPH_DATA_AGENT_ID` / `TELEMETRY_DATA_AGENT_ID` env vars exist. Demo uses Foundry agents, not Fabric Data Agents. |
| 13 | `scripts/fabric/assign_fabric_role.py` | 96 | Functionality duplicated inline in `deploy.sh` Step 4b. Never called from any pipeline. |

### 1D. Graph Query API (1 directory + 1 spec file)

| # | File | Lines | Why Dead |
|---|------|------:|----------|
| 14 | `graph-query-api/services/` (entire dir) | 1 | Contains only an `__init__.py` with one comment line. No module imports from `services`. Empty placeholder never implemented. |
| 15 | `graph-query-api/openapi/mock.yaml` | 116 | Only reachable via `OPENAPI_SPEC_MAP` fallback in `agent_provisioner.py`, which is itself dead code (deploy.sh always uses template path with `fabric-gql`). Transitively dead. **Delete alongside the `OPENAPI_SPEC_MAP` cleanup in Phase 3.** |

### 1E. Root-Level Files

| # | File | Lines | Why Dead |
|---|------|------:|----------|
| 16 | `architecture_graph.json` (root) | 1000 | Never loaded by any code. API serves `data/architecture_graph.json` at `/api/config/architecture`. Dockerfile doesn't COPY the root file. Orphaned design document. |
| 17 | `custom_skills/azure-container-neo4j-py/` (entire dir) | ~4 files | Copilot skill for Neo4j. Project uses Fabric Graph (GQL). No code references Neo4j. Not shipped in any artifact. |

### 1F. Stale Documentation

| # | File | Why Dead |
|---|------|----------|
| 18 | `documentation/completed/decoupling.md.bak` | `.bak` backup of existing `decoupling.md`. Orphaned artifact (637 lines). |

**Implementation — run from `fabricdemo/`:**

```bash
# 1A — Dead frontend components
rm frontend/src/components/InteractionSidebar.tsx
rm frontend/src/components/InvestigationPanel.tsx
rm frontend/src/components/DiagnosisPanel.tsx
rm frontend/src/components/EmptyState.tsx
rm frontend/src/components/AgentTimeline.tsx
rm frontend/src/components/AlertInput.tsx
rm frontend/src/components/ErrorBanner.tsx

# 1B — Dead frontend hooks
rm frontend/src/hooks/useInteractions.ts
rm frontend/src/hooks/useInvestigation.ts
rm frontend/src/hooks/useResourceGraph.ts

# 1C — Dead scripts
rm scripts/provision_cosmos.py
rm scripts/fabric/collect_fabric_agents.py
rm scripts/fabric/assign_fabric_role.py

# 1D — Dead graph-query-api package
rm -rf graph-query-api/services/

# 1E — Root-level dead files
rm architecture_graph.json
rm -rf custom_skills/azure-container-neo4j-py/

# 1F — Stale docs
rm documentation/completed/decoupling.md.bak
```

**Post-deletion verification:**

```bash
# Confirm no broken imports (should return 0 results for deleted names)
grep -rn "InteractionSidebar\|InvestigationPanel\|DiagnosisPanel\|EmptyState\b\|AgentTimeline\|AlertInput\|ErrorBanner" frontend/src/ --include='*.tsx' --include='*.ts' | grep -v "\.bak\|node_modules"
grep -rn "useInteractions\|useInvestigation\|useResourceGraph" frontend/src/ --include='*.tsx' --include='*.ts'
grep -rn "provision_cosmos\|collect_fabric_agents\|assign_fabric_role" scripts/ deploy.sh azure.yaml hooks/
```

---

## Phase 2 — Remove "Data Ops" Terminal Tab

The "Data Ops" tab streams from two SSE endpoints whose backend log filters mostly match **phantom logger names** (modules that don't exist). The valid logs (`app.routers.config`, `graph-query-api.cosmos`) already appear in the main "API" and "Graph API" tabs respectively. The tab provides no unique information.

**Affected files (3):**

| File | What to Remove |
|------|----------------|
| `frontend/src/components/TerminalPanel.tsx` | Remove the `Data Ops` entry from `LOG_STREAMS` (lines 16–19) |
| `api/app/routers/logs.py` | Remove `_data_ops_broadcaster`, its handler, filter, and the `/api/logs/data-ops` endpoint (lines 31–41 + 62–65) |
| `graph-query-api/main.py` | Remove `_data_ops_broadcaster`, its handler, filter, and the `/query/logs/data-ops` endpoint (lines 153–186) |

**Detail on phantom logger names:**

| Endpoint | Filter Matches Logger | Logger Exists? |
|----------|----------------------|----------------|
| `/api/logs/data-ops` | `app.routers.config` | YES — but already in main `/api/logs` stream |
| `/api/logs/data-ops` | `app.routers.fabric` | **NO** — no `routers/fabric.py` exists |
| `/query/logs/data-ops` | `graph-query-api.cosmos` | YES — but already in main `/query/logs` stream |
| `/query/logs/data-ops` | `graph-query-api.ingest` | **NO** — no ingest module exists |
| `/query/logs/data-ops` | `graph-query-api.indexer` | **NO** — no indexer module exists |
| `/query/logs/data-ops` | `graph-query-api.blob` | **NO** — no blob module exists |

---

## Phase 3 — Inline Dead Code Removal

### 3A. API Backend (`api/`)

| # | File | What to Change | Lines Affected | Risk |
|---|------|----------------|:--------------:|:----:|
| 1 | `api/app/orchestrator.py` L27 | Remove `get_agent_list` from the import statement (keep `load_agent_ids`, `get_agent_names`) | 1 | NONE |
| 2 | `api/app/sessions.py` L58 | Remove `_thread: Optional[threading.Thread] = field(default=None, repr=False)`. Also remove `import threading` if no longer needed. | 2 | NONE |
| 3 | `api/app/main.py` L29 | Remove redundant `load_dotenv(os.path.join(..., "azure_config.env"))` call — already loaded by `paths.py` at import time. | 1 | NONE |
| 4 | `api/app/main.py` L89 | Remove dead `services = []` assignment (overwritten at L148 with no read in between). | 1 | NONE |
| 5 | `api/app/main.py` L107 | Prefix `resp` with `_` or remove assignment: the HTTP response is never inspected (function relies on exception-on-failure). | 1 | NONE |
| 6 | `api/app/main.py` L128 | Same as above for `_check_cosmos()` — `resp` assigned but never read. | 1 | NONE |
| 7 | `api/app/main.py` L164–183 | Collapse the `services_models()` try block — the try path and except path both read the same env vars and produce identical results. Remove the `AIProjectClient` instantiation + `get_chat_completions_client()` call that discards its result. | ~20 | LOW |
| 8 | `api/app/routers/logs.py` L39 | Remove `"app.routers.fabric"` from the filter tuple — no such module exists. (Only if keeping Data Ops tab; otherwise removed entirely in Phase 2.) | 1 | NONE |
| 9 | `api/app/dispatch.py` L111–118 | Remove the `PRESENTER_EMAIL` no-op stub block (reads env var, logs it, does nothing). Keep the env var in `azure_config.env.template` for future use. | ~8 | NONE |
| 10 | `api/app/paths.py` L19 | Remove export of `CONFIG_FILE` from `__all__` or docstring (it's only used internally). Or leave as-is — purely cosmetic. | 0–1 | NONE |

### 3B. Graph Query API (`graph-query-api/`)

| # | File | What to Change | Lines Affected | Risk |
|---|------|----------------|:--------------:|:----:|
| 11 | `graph-query-api/router_telemetry.py` L56 | Remove the redundant local `from backends.fabric_kql import FabricKQLBackend` re-import inside `_query_fabric_kql()`. | 1 | NONE |
| 12 | `graph-query-api/router_telemetry.py` L14–15, L53 | Remove `ScenarioContext` import and the unused `ctx: ScenarioContext` parameter from `_query_fabric_kql()`. Update any callers of `_query_fabric_kql()` to stop passing `ctx`. | ~3 | LOW |
| 13 | `graph-query-api/backends/__init__.py` L91–97 | Remove `get_backend()` function — never called, docstring says "use `get_backend_for_context()` instead". | ~7 | NONE |
| 14 | `graph-query-api/backends/fabric.py` L213–240 | Remove `_build_topology_query()` method — never called. `get_topology()` builds queries inline. | ~28 | NONE |
| 15 | `graph-query-api/router_topology.py` L75–89 | Remove `invalidate_topology_cache()` function — zero callers. Carried over from cosmosdemo. | ~15 | NONE |
| 16 | `graph-query-api/adapters/fabric_config.py` L26, L41–45 | Remove 6 dead constants: `FABRIC_WORKSPACE_ID`, `FABRIC_WORKSPACE_NAME`, `FABRIC_LAKEHOUSE_NAME`, `FABRIC_EVENTHOUSE_NAME`, `FABRIC_ONTOLOGY_NAME`, `FABRIC_CAPACITY_ID`. Also remove `_require_env()` helper if no remaining callers. **This also fixes a latent bug:** `_require_env()` for these vars runs at import time, crashing the app if they're unset — even though no code uses them. | ~25 | NONE (fixes bug) |
| 17 | `graph-query-api/fabric_discovery.py` L176 | Remove unused `eventhouses` dict comprehension — built but never referenced. | 1 | NONE |
| 18 | `graph-query-api/cosmos_helpers.py` L5–10 | Update stale docstring — references to `router_prompts`, `router_scenarios`, `router_ingest` which don't exist. | ~5 | NONE |

### 3C. Frontend (`frontend/`)

| # | File | What to Change | Lines Affected | Risk |
|---|------|----------------|:--------------:|:----:|
| 19 | `frontend/src/utils/agentType.ts` L6–18 | Remove `getVisualizationType()` function — never called. Keep `getVizButtonMeta()` (used by `StepCard`, `StepVisualizationModal`). | ~13 | NONE |
| 20 | `frontend/src/config.ts` L70–72 | Remove `getScenarioSync()` function — never called. Scenario accessed via `useScenario()` context hook. | ~3 | NONE |
| 21 | `frontend/src/types/index.ts` L5 | Remove `VisualizationType` type alias — only imported by the dead `getVisualizationType()`. | 1 | NONE |
| 22 | `frontend/src/types/index.ts` L107–119 | Remove `Interaction` interface — only imported by the dead `useInteractions.ts` and `InteractionSidebar.tsx` (both deleted in Phase 1). References in `GraphCanvas.tsx:211` and `ResourceCanvas.tsx:335` are section-heading comments, not imports. | ~13 | NONE |
| 23 | `frontend/src/styles/globals.css` | Remove dead CSS: `.glass-panel` (L130–132), `.resize-handle` + variants (L144–198, 8 rules), `.animate-in` (L203–205), `@keyframes fadeIn` (L208–211), `@keyframes slideUp` (L213–217), `--transition-fast` + `--transition-normal` (L40–41). | ~70 | NONE |

### 3D. Scripts (`scripts/`)

| # | File | What to Change | Lines Affected | Risk |
|---|------|----------------|:--------------:|:----:|
| 24 | `scripts/agent_provisioner.py` L39–41 | Remove `OPENAPI_SPEC_MAP` dict (only maps `"mock"` → `mock.yaml`; never reached since `spec_template` is always provided). | ~3 | NONE |
| 25 | `scripts/agent_provisioner.py` L47–57 | Remove `CONNECTOR_OPENAPI_VARS["mock"]` block — `deploy.sh` forces `GRAPH_BACKEND=fabric-gql`. | ~11 | NONE |
| 26 | `scripts/agent_provisioner.py` L65–87 | Remove `GRAPH_TOOL_DESCRIPTIONS["mock"]` — never reached with `fabric-gql` backend. | ~23 | NONE |
| 27 | `scripts/provision_agents.py` L38–41 | Remove `LANGUAGE_FILE_MAP["mock"]` entry — never exercised with `fabric` backend. | ~3 | NONE |

---

## Phase 4 — Dependency Cleanup

Remove unused dependencies to reduce container image size and installation time.

### 4A. `api/pyproject.toml` — remove 3 deps

| Dependency | Why Unused |
|------------|------------|
| `python-multipart>=0.0.9` | No endpoint uses `File`, `UploadFile`, or `Form`. |
| `azure-storage-file-datalake>=12.14.0` | No file in `api/app/` imports `azure.storage.filedatalake`. |
| `azure-kusto-ingest>=4.3.0` | No file in `api/app/` imports `azure.kusto`. |

### 4B. `graph-query-api/pyproject.toml` — remove 4 deps

| Dependency | Why Unused |
|------------|------------|
| `sse-starlette>=1.6.0` | SSE uses `starlette.responses.StreamingResponse` + hand-written `LogBroadcaster`. |
| `azure-storage-blob>=12.19.0` | No blob storage ops in graph-query-api. Residual from cosmosdemo. |
| `azure-search-documents>=11.6.0` | `router_search.py` calls Azure AI Search REST API via `httpx`, not the SDK. |
| `python-multipart>=0.0.9` | API uses exclusively JSON bodies, no form uploads. |

### 4C. Root `pyproject.toml` — remove 1 dep

| Dependency | Why Unused |
|------------|------------|
| `pandas>=2.2.0` | No script imports pandas. |

### 4D. `frontend/package.json` — remove 1 dep

| Dependency | Why Unused |
|------------|------------|
| `react-resizable-panels` `^4.6.2` | Never imported in `src/`. Custom `useResizable` hook used instead. `.resize-handle` CSS is also dead (removed in Phase 3). |

**After removing dependencies, regenerate lockfiles:**

```bash
# Python
cd api && uv lock && cd ..
cd graph-query-api && uv lock && cd ..
uv lock  # root

# Frontend
cd frontend && npm install && cd ..
```

---

## Phase 5 — Dockerfile Cleanup

| Line | Current | Action | Why |
|------|---------|--------|-----|
| ~40 | `COPY graph-query-api/services/ ./services/` | **Delete this line** | Copies an empty package (1-line `__init__.py`) that nothing imports. Removed in Phase 1. |
| ~52 | `COPY scripts/agent_provisioner.py /app/scripts/` | **Delete this line** | API code never imports from `/app/scripts/` at runtime. Provisioning runs outside the container via `deploy.sh`. If manual in-container re-provisioning is needed, the script can be copied ad hoc via `az webapp ssh`. |

---

## Phase 6 — Refactoring Opportunities

These are **not dead code** — they're maintainability issues to address after the dead code is cleaned up. Lower priority but high impact.

### 6A. SSEEventHandler Duplication (~550 lines duplicated)

| File | Description |
|------|-------------|
| `api/app/orchestrator.py` | `SSEEventHandler(AgentEventHandler)` is defined as a nested class **twice**: once inside `run_orchestrator()` (~L114–509, 400 lines) and again inside `run_orchestrator_session()` (~L746–1099, 353 lines). All methods are verbatim-identical. The second copy acknowledges this: *"We re-create a local class to keep the `_put` closure correct."* |

**Fix:** Extract `SSEEventHandler` as a module-level class parameterized with a `_put` callable (injected via `__init__`). Both `run_orchestrator()` and `run_orchestrator_session()` instantiate it with their respective `_put` functions.

### 6B. `_thread_target()` Near-Duplication (~160 lines)

| File | Description |
|------|-------------|
| `api/app/orchestrator.py` | `_thread_target()` exists twice (~L514–676 vs ~L1095–1264). Session variant adds `cancel_event` checks, `existing_thread_id` reuse, and `thread_created` event. Could be unified into one parameterized function. |

### 6C. Credential/Client Duplication

| Files | Description |
|-------|-------------|
| `api/app/orchestrator.py` + `api/app/agent_ids.py` | `_get_credential()` and `_get_project_client()` are duplicated across both files with independent `DefaultAzureCredential` singletons. Comment says "shared with agent_ids module" but they are **not shared**. Should be extracted to a shared module. |

### 6D. Trivial Wrapper

| File | Description |
|------|-------------|
| `api/app/orchestrator.py` L65–68 | `_load_agent_names()` is a pure pass-through to `get_agent_names()`. No caching, no transformation. Could be inlined. Low priority. |

### 6E. Dead Props (keep but note)

| File | Prop | Description |
|------|------|-------------|
| `frontend/src/components/resource/ResourceCanvas.tsx` L37 | `highlightIds?: Set<string>` | Defined but never passed by `ResourceVisualizer.tsx`. Always `undefined` at runtime. Keep if planning future use; remove if not. |
| `frontend/src/hooks/useSessions.ts` L8 | `_scenario?: string` | Accepted but never read. Underscore prefix signals intentional ignoring. Keep if planning future filtering. |

### 6F. Testing / Utility Scripts (keep, do not delete)

| File | Lines | Description |
|------|------:|-------------|
| `scripts/testing_scripts/test_graph_query_api.py` | 137 | Manual test script for graph-query-api. Dev utility, not runtime. |
| `scripts/testing_scripts/test_orchestrator.py` | 301 | Manual test script for orchestrator. Dev utility, not runtime. |
| `scripts/generate_sensor_data.py` | 329 | Standalone data generator for `SensorReadings.csv`. Keep if data may need regeneration. |

---

## Do NOT Delete — Verified Alive

These items were investigated and **confirmed active**. Deleting them WILL break the application.

| Item | Why It's Alive |
|------|----------------|
| `graph-query-api/cosmos_config.py` | Cosmos DB NoSQL config for session/interaction persistence |
| `graph-query-api/cosmos_helpers.py` | Imported by `stores/cosmos_nosql.py`, `main.py` shutdown hook |
| `graph-query-api/stores/cosmos_nosql.py` | Session/interaction data store. Import chain: `cosmos_config → cosmos_helpers → cosmos_nosql → router_interactions` |
| `scripts/scenario_loader.py` | Imported by `provision_search_index.py` (L70) and `provision_agents.py` (L31) — both called from `deploy.sh` |
| `scripts/generate_topology_json.py` | Called by `deploy.sh` at L646 |
| `graph-query-api/router_replay.py` | Imported at `main.py` L47, included in router setup at L135 |
| `api/app/dispatch.py` | Imported by `orchestrator.py` for `dispatch_field_engineer` |
| `data/architecture_graph.json` | Served by `api/app/routers/config.py` at `/api/config/architecture` |
| `PRESENTER_EMAIL` env var | Read by `dispatch.py` (placeholder but wired — keep in `azure_config.env.template`) |

---

## Audit Corrections

Items from earlier audits that were found to be **incorrect** during verification:

| Original Claim | Verdict | Detail |
|----------------|---------|--------|
| `PRESENTER_EMAIL` is unused | **PARTIALLY WRONG** | The env var IS read by `dispatch.py`. What's dead is the *email sending logic* (unimplemented placeholder). The variable itself is live config for a future feature. |
| `openapi/mock.yaml` is independently dead | **NUANCED** | Referenced by `OPENAPI_SPEC_MAP` which is itself dead (deploy.sh always uses template path). Transitively dead — safe to delete only alongside the `OPENAPI_SPEC_MAP` cleanup. |
| Cosmos modules are dead | **WRONG** | All three (`cosmos_config.py`, `cosmos_helpers.py`, `cosmos_nosql.py`) are active. Fabricdemo uses Cosmos DB NoSQL for session persistence. Do NOT delete. |
| `_data_ops_broadcaster` in `api/app/routers/logs.py` is fully useless | **NUANCED** | The `app.routers.fabric` half of the filter is dead (module doesn't exist), but `app.routers.config` IS valid and its logs do flow through. However, these logs already appear in the main `/api/logs` stream, making the separate endpoint redundant. |
| Dockerfile COPY of `agent_provisioner.py` is dead | **NUANCED** | Not needed at runtime, but could serve manual in-container re-provisioning. Risk is low either way — removal recommended with the note that `az webapp ssh` + manual copy is an alternative if ever needed. |

---

## Impact Summary

| Phase | Files Removed | Lines Removed | Risk Level |
|-------|:------------:|:-------------:|:----------:|
| **Phase 1** — Dead file deletion | **18+ files** | **~4,500** | ZERO |
| **Phase 2** — Data Ops tab removal | 3 files (edits) | ~50 | LOW |
| **Phase 3** — Inline dead code | ~15 files (edits) | ~250 | LOW |
| **Phase 4** — Unused dependencies | 4 files (edits) | 9 lines | LOW |
| **Phase 5** — Dockerfile cleanup | 1 file (edit) | 2 lines | LOW |
| **Phase 6** — Refactoring (optional) | 2–3 files | ~550 (dedup) | MEDIUM |
| **Total** | **~21+ files deleted** | **~4,800+ lines** | |

### Execution Order

Phases 1–5 are independent and can be done in any order. Phase 6 (refactoring) should be done last, after the codebase is clean.

**Recommended sequence:** Phase 1 → Phase 4 → Phase 5 → Phase 2 → Phase 3 → Phase 6

This order maximizes early wins (file deletions, dep cleanup) before making surgical inline edits.
