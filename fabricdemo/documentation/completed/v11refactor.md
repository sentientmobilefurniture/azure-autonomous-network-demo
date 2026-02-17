# Refactor: Simplify, Solidify, Harden

## Objective:
Discover opportunities to streamline code in order to make it easier to fix bugs and maintain the codebase without negatively impacting functionality or ruining the application. Goal is to reduce the overall number of lines by genericizing certain functions. 

## Summary

### Tier 1 — Quick wins (zero/low risk, no architectural change)

| # | Area | File(s) | Est. Reduction | Risk |
|---|------|---------|---------------|------|
| 1 | Unify tarball extraction | `router_ingest.py` | ~15 lines | Low |
| 2 | Consolidate Gremlin retry | `router_ingest.py`, `backends/cosmosdb.py` | ~25 lines | Low |
| 3 | Upload endpoint boilerplate | `router_ingest.py` | ~60 lines | Low |
| 4 | Delete dead frontend code | `AlertChart.tsx`, `MetricCard.tsx` | ~51 lines | Zero |
| 5 | Deduplicate infra nodes | `api/app/routers/config.py` | ~20 lines | Zero |
| 6 | Extract orchestrator helpers | `api/app/orchestrator.py` | ~25 lines | Low |
| 7 | Extract BindingCard component | `SettingsModal.tsx` | ~80 lines | Low |
| 8 | Fix prompts async violation | `router_prompts.py` | 0 (correctness) | Low |
| 9 | Deprecate `provision_all()` | `agent_provisioner.py` | ~164 lines | Medium |

### Tier 2 — Cross-cutting deduplication (low/medium risk, targeted refactors)

| # | Area | File(s) | Est. Reduction | Risk |
|---|------|---------|---------------|------|
| 10 | Unify Gremlin client creation | `router_ingest.py`, `backends/cosmosdb.py` | ~30 lines | Low |
| 11 | Unify ARM mgmt-client creation | `router_ingest.py`, `cosmos_helpers.py`, `backends/cosmosdb.py` | ~20 lines | Low |
| 12 | Deduplicate Fabric `_get_token()` | `backends/fabric.py`, `router_fabric_discovery.py` | ~8 lines | Zero |
| 13 | Consolidate `TELEMETRY_REQUIRED_VARS` | `config.py`, `adapters/cosmos_config.py` | ~5 lines | Zero |
| 14 | Unify `agent_ids.json` readers | `orchestrator.py`, `agents.py`, `alert.py`, `config.py` | ~40 lines | Low |
| 15 | Generic Fabric `_find_or_create` | `fabric_provision.py` | ~160 lines | Medium |
| 16 | Deduplicate SSE log broadcast | `api/app/routers/logs.py`, `graph-query-api/main.py` | ~80 lines | Low |
| 17 | Deduplicate version-query logic | `router_prompts.py`, `router_ingest.py` | ~25 lines | Low |
| 18 | Consolidate scenario name validation | `router_scenarios.py` | ~15 lines | Zero |
| 19 | Extract shared SSE boilerplate | `fabric_provision.py` | ~60 lines | Low |
| 20 | Deduplicate provisioning helpers | `agent_provisioner.py`, `config.py`, `provision_agents.py` | ~40 lines | Low |

### Tier 3 — Frontend structural improvements (low risk, improved DX)

| # | Area | File(s) | Est. Reduction | Risk |
|---|------|---------|---------------|------|
| 21 | Extract `formatTimeAgo` util | `App.tsx`, `InteractionSidebar.tsx` | ~8 lines | Zero |
| 22 | Extract `usePausableSimulation` hook | `GraphTopologyViewer.tsx`, `ResourceVisualizer.tsx` | ~70 lines | Low |
| 23 | Extract `useTooltipTracking` hook | `GraphTopologyViewer.tsx`, `ResourceVisualizer.tsx` | ~60 lines | Low |
| 24 | Extract `useClickOutside` hook | `AlertInput.tsx`, `ScenarioChip.tsx`, `ColorWheelPopover.tsx` | ~30 lines | Zero |
| 25 | Reuse `<ThinkingDots>` in DiagnosisPanel | `DiagnosisPanel.tsx` | ~10 lines | Zero |
| 26 | Merge `COLOR_PALETTE` / `AUTO_PALETTE` | `graphConstants.ts`, `useNodeColor.ts` | ~4 lines | Zero |
| 27 | Extract `<ProgressBar>` component | `SettingsModal.tsx`, `AddScenarioModal.tsx`, `ProvisioningBanner.tsx` | ~20 lines | Zero |
| 28 | Extract `<ModalShell>` wrapper | `SettingsModal.tsx`, `AddScenarioModal.tsx` | ~40 lines | Low |
| 29 | Deduplicate provisioning SSE calls | `ProvisioningBanner.tsx`, `useScenarios.ts`, `SettingsModal.tsx` | ~50 lines | Low |
| 30 | Move topology types to `types/` | `useTopology.ts` → `types/index.ts` | 0 (reorg) | Zero |

### Tier 4 — Structural / architectural (medium risk, higher payoff)

| # | Area | File(s) | Est. Reduction | Risk |
|---|------|---------|---------------|------|
| 31 | Split `router_ingest.py` God module | `router_ingest.py` → 3-4 modules | 0 (reorg) | Medium |
| 32 | Split `SettingsModal.tsx` into tab components | `SettingsModal.tsx` → 5 tab files | 0 (reorg) | Medium |
| 33 | Extract upload orchestration hook | `AddScenarioModal.tsx` → `useScenarioUpload.ts` | 0 (reorg) | Medium |
| 34 | Lift `savedScenarios` into Context | `useScenarios.ts` → `ScenarioContext.tsx` | ~20 lines, fix 4x fetch | Medium |
| 35 | Fix async violations in `config.py` | `api/app/routers/config.py` | 0 (correctness) | Low |
| 36 | Centralize path/config constants | 5+ files → shared `paths.py` | ~25 lines | Low |

### Tier 5 — Dead code & cleanup

| # | Area | File(s) | Est. Reduction | Risk |
|---|------|---------|---------------|------|
| 37 | Delete `FabricGQLBackend.aclose()` | `backends/fabric.py` | ~5 lines | Zero |
| 38 | ~~Remove unused `GRAPH_BACKEND` import~~ | `backends/cosmosdb.py` | — | ~~Zero~~ SKIP |
| 39 | Remove unused `close_all_backends` import | `graph-query-api/main.py` | ~1 line | Zero |
| 40 | Delete unused Fabric env vars | `adapters/fabric_config.py` | ~8 lines | Zero |
| 41 | Delete empty `NODE_COLORS`/`NODE_SIZES` | `graphConstants.ts` | ~6 lines | Zero |
| 42 | Remove `runStarted` prop plumbing | `App.tsx` → `DiagnosisPanel.tsx` | ~4 lines | Zero |
| 43 | Move mock topology data to JSON fixture | `backends/mock.py` | ~140 lines (to file) | Zero |

### Tier 6 — Architectural correctness (medium risk, prevents silent bugs)

| # | Area | File(s) | Est. Reduction | Risk |
|---|------|---------|---------------|------|
| 44 | Promote `savedScenarios` + `activeScenarioRecord` to context | `ScenarioContext.tsx`, `useScenarios.ts` | ~20 lines, fix 4x fetch | Medium |
| 45 | Clear investigation state on scenario switch | `App.tsx`, `useInvestigation.ts` | ~5 lines (correctness) | Low |
| 46 | Persist `_current_config` to disk | `api/app/routers/config.py` | 0 (correctness) | Medium |
| 47 | Scope localStorage graph customizations per scenario | `GraphTopologyViewer.tsx` | ~4 lines | Low |
| 48 | Provisioning concurrency guard | `config.py`, `ScenarioContext.tsx`, `Header.tsx` | ~15 lines | Medium |
| 49 | Derive agent count from actual data | `Header.tsx`, `ScenarioContext.tsx` | ~5 lines | Low |
| 50 | Fix blocking urllib calls in `config.py` | `api/app/routers/config.py` | ~15 lines | Low |

| | | | **Est. Total** | |
|---|------|---------|---------------|------|
| **Tiers 1-6** | | | **~1,400–1,600 lines reduced/reorganized** | |

## Implementation Plan

### 1. Unify tarball extraction in `router_ingest.py` (Low risk, ~15 lines)

**Problem:** Three different tarball extraction patterns exist:
- `_extract_tar()` shared helper — used by `upload_graph` and `upload_telemetry`
- `_upload_knowledge_files()` (runbooks + tickets) — inline `tarfile.open().extractall()` + `os.walk()`
- `upload_prompts` — separate inline `tarfile.open().extractall()` + `os.walk()`

**Fix:** Replace all inline `tarfile.open()` + `extractall()` calls with `_extract_tar()`. The helper already handles nested-directory detection (finds the directory containing `scenario.yaml`), which the inline versions skip.

**Files:** `graph-query-api/router_ingest.py` lines ~639-641 and ~886

---

### 2. Consolidate Gremlin retry logic (Low risk, ~25 lines)

**Problem:** Three separate Gremlin retry implementations:
1. `router_ingest.py` `_gremlin_submit()` — basic retry on 429/408 (~8 lines), used only by `delete_scenario()`
2. `backends/cosmosdb.py` `_submit_query()` — full retry with reconnection (~55 lines), used by query/topology
3. `backends/cosmosdb.py` `_submit_with_retry()` — duplicate of `_gremlin_submit()` (~15 lines), used only by `ingest()`

**Fix:** 
- Delete `_gremlin_submit()` from `router_ingest.py`
- Delete `_submit_with_retry()` from `cosmosdb.py`
- Extract the shared retry-loop logic from `_gremlin_submit()` / `_submit_with_retry()` into a standalone `gremlin_submit_with_retry(client, query, bindings)` helper (e.g. in a new `graph-query-api/gremlin_helpers.py`)
- **Do NOT merge into `_submit_query()`** — `_submit_query()` is an instance method on `CosmosDBGremlinBackend` that uses `self._get_client()` and `self._lock` for reconnection, and hardcodes `bindings={}`. Ingest callers need explicit `bindings` and an explicit `client` parameter.
- The standalone helper covers the 429/408 retry pattern; the instance method `_submit_query()` keeps its reconnection logic.

**Files:** `graph-query-api/router_ingest.py`, `graph-query-api/backends/cosmosdb.py`

---

### 3. Extract upload endpoint boilerplate (Low risk, ~60 lines)

**Problem:** All 5 upload endpoints repeat identical patterns:
- Filename validation (`.tar.gz` / `.tgz` check) — 5 times
- `content = await file.read()` + byte-count logging — 5 times
- `scenario_name` override + `_rewrite_manifest_prefix()` — 3 times
- `return sse_upload_response(work, error_label=…)` — 5 times

**Fix:** Create a shared decorator or helper:
```python
async def _validate_upload(file: UploadFile) -> bytes:
    """Validate tarball filename and read content. Raises HTTPException on invalid."""
    if not (file.filename or "").endswith((".tar.gz", ".tgz")):
        raise HTTPException(400, "Expected .tar.gz or .tgz file")
    content = await file.read()
    logger.info("Received %s (%d bytes)", file.filename, len(content))
    return content
```

Each endpoint reduces from ~8 lines of validation to `content = await _validate_upload(file)`.

**Files:** `graph-query-api/router_ingest.py`

---

### 4. Delete dead frontend components (Zero risk, ~51 lines)

**Problem:** `AlertChart.tsx` (21 lines) and `MetricCard.tsx` (30 lines) exist in `frontend/src/components/` but are not imported by any component in the main frontend. They're only referenced in `fabric_implementation_references/` (a separate reference copy, not the live app).

**Fix:** Delete both files.

**Files:** `frontend/src/components/AlertChart.tsx`, `frontend/src/components/MetricCard.tsx`

---

### 5. Deduplicate `_infra_nodes_only()` in config.py (Zero risk, ~20 lines)

**Problem:** `_build_resource_graph()` creates 5 infrastructure nodes inline with env-var lookups. `_infra_nodes_only()` creates the exact same 5 nodes. The inline version in `_build_resource_graph()` is redundant.

**Fix:** Replace the inline infrastructure node construction in `_build_resource_graph()` with a call to `_infra_nodes_only()`.

**Files:** `api/app/routers/config.py`

---

### 6. Extract orchestrator argument/name resolution helpers (Low risk, ~25 lines)

**Problem:** In `orchestrator.py`'s `SSEEventHandler`, argument extraction and agent name resolution are duplicated between the `on_run_step` completed path and the failed path:
- Connected agent arguments JSON parsing — identical ~12 lines in both paths
- Agent name resolution from `ca.name` or `ca.agent_id` lookup — identical ~6 lines in both paths

**Fix:** Extract two helper methods:
```python
def _resolve_agent_name(self, ca) -> str:
    """Resolve agent name from ConnectedAgentTool reference."""

def _extract_arguments(self, ca) -> str:
    """Parse and truncate arguments from ConnectedAgentTool."""
```

**Files:** `api/app/orchestrator.py`

---

### 7. Extract `BindingCard` from SettingsModal (Low risk, ~80 lines)

**Problem:** `SettingsModal.tsx` (860 lines) contains 5 nearly-identical data-source binding blocks in the "Custom mode" section of the Data Sources tab (L419–L555). Each block is ~25 lines of JSX with the same structure: colored dot indicator + label + select/text input (4 with `<select>` dropdowns + 1 auto-derived read-only field).

**Fix:** Extract a `BindingCard` component:
```tsx
interface BindingCardProps {
  label: string;
  color: string;
  value: string;
  options?: string[];
  readOnly?: boolean;
  onChange: (v: string) => void;
}
function BindingCard({ label, color, value, options, readOnly, onChange }: BindingCardProps) { ... }
```

5 blocks × 25 lines → 5 calls × 3 lines + 1 component × 25 lines = ~40 lines (saves ~85 lines).

**Files:** `frontend/src/components/SettingsModal.tsx`

---

### 8. Fix `router_prompts.py` async violation (Low risk, correctness fix)

**Problem:** `_list_prompt_scenarios()` is a sync function that calls the ARM SDK's `sql_resources.list_sql_containers()` directly. It's invoked from async handlers `list_prompts` and `list_prompt_scenarios` without `asyncio.to_thread()`, blocking the event loop for the duration of the ARM call (~200-500ms).

Per Critical Pattern #1 in the architecture docs: "All Azure SDK calls MUST be in `asyncio.to_thread()`."

**Fix:** Wrap the `_list_prompt_scenarios()` call in `asyncio.to_thread()`:
```python
scenarios = await asyncio.to_thread(_list_prompt_scenarios)
```

**Files:** `graph-query-api/router_prompts.py`

---

### 9. Deprecate `provision_all()` in agent_provisioner.py (Medium risk, ~164 lines)

**Problem:** `agent_provisioner.py` contains two provisioning paths:
- `provision_all()` — legacy, hardcodes exactly 5 agents with specific roles and tools (~164 lines, L199–L362)
- `provision_from_config()` — config-driven, creates N agents from `scenario.yaml`'s `agents:` section (~134 lines, L376–L509)

Both share identical `emit()` helper definitions, `AGENT_IDS_FILE` save logic, and result-building code. The config-driven path supersedes the legacy path.

**Prerequisites:** Verify that all active scenarios include an `agents:` section in their `scenario.yaml`. Currently only `telco-noc` has local data; check its manifest.

**Fix (phased):**
1. **Phase A (safe):** Extract shared helpers (`_save_agent_ids()`, `_emit()`, `_build_result()`) to eliminate duplication between the two methods (~30 lines saved)
2. **Phase B (after verification):** Delete `provision_all()` entirely and update `provision_agents.py` CLI wrapper to always call `provision_from_config()` (~164 lines saved)

**Risk mitigation:** `provision_all()` is called from `provision_agents.py` CLI and from `api/app/routers/config.py` (fallback when no config `agents:` section exists). Phase B should only proceed after confirming all deployed scenarios have config-driven agents.

**Files:** `scripts/agent_provisioner.py`, `scripts/provision_agents.py`, `api/app/routers/config.py`

---

---

## Tier 2 — Cross-cutting deduplication

### 10. Unify Gremlin client creation (Low risk, ~30 lines)

**Problem:** Three separate places construct a Gremlin `client.Client` with identical WSS URL formatting, username construction, and serializer selection:
1. `router_ingest.py` `_gremlin_client()` (~8 lines)
2. `backends/cosmosdb.py` `_get_client()` (~12 lines)
3. `backends/cosmosdb.py` `ingest()` inner `_load()` (~7 lines, creates yet another client inline)

**Fix:** Extract the Gremlin client construction logic into a standalone factory function (e.g. `create_gremlin_client(graph_name)` in `gremlin_helpers.py` or `backends/__init__.py`). Delete `_gremlin_client()` from `router_ingest.py` and the inline client creation in `_load()`.

⚠️ **Gotcha:** `_get_client()` in `cosmosdb.py` is an **instance method** that caches a client **bound to a specific graph** via the `username` field (`/dbs/{db}/colls/{graph_name}`). The `ingest()` method creates a separate client because it targets a **different graph** than the backend's default. A shared factory must accept `graph_name` as a parameter — do NOT share a single cached client across code that targets different graphs.

**Files:** `graph-query-api/router_ingest.py`, `graph-query-api/backends/cosmosdb.py`

---

### 11. Unify ARM CosmosDBManagementClient creation (Low risk, ~20 lines)

**Problem:** Four separate places instantiate `CosmosDBManagementClient`:
1. `router_ingest.py` `_ensure_nosql_containers()` — inline construction
2. `router_ingest.py` `_list_graphs()` — inline `CosmosDBManagementClient(DefaultAzureCredential(), sub_id)` (creates a new credential instead of using `get_credential()`)
3. `cosmos_helpers.py` `get_mgmt_client()` — the intended cached singleton
4. `backends/cosmosdb.py` line ~302 — yet another inline construction

**Fix:** All call sites should use `cosmos_helpers.get_mgmt_client()`. Delete inline constructions. This also fixes the `DefaultAzureCredential()` leak in `router_ingest.py` where a new credential is constructed instead of reusing the shared one.

**Files:** `graph-query-api/router_ingest.py`, `graph-query-api/backends/cosmosdb.py`, `graph-query-api/cosmos_helpers.py`

---

### 12. Deduplicate Fabric `_get_token()` (Zero risk, ~8 lines)

**Problem:** `backends/fabric.py` and `router_fabric_discovery.py` both define identical `_get_token()` functions that acquire a Fabric API token via `asyncio.to_thread(credential.get_token, FABRIC_SCOPE)`.

**Fix:** Move `_get_token()` to a shared location (e.g., `adapters/fabric_config.py` or `backends/fabric.py`) and import it in `router_fabric_discovery.py`.

**Files:** `graph-query-api/backends/fabric.py`, `graph-query-api/router_fabric_discovery.py`

---

### 13. Consolidate `TELEMETRY_REQUIRED_VARS` (Zero risk, ~5 lines)

**Problem:** `TELEMETRY_REQUIRED_VARS` is defined identically in both `config.py` and `adapters/cosmos_config.py`. Two sources of truth for the same constant.

**Fix:** Keep the definition in `config.py` (the canonical config module) and import it in `adapters/cosmos_config.py`.

**Files:** `graph-query-api/config.py`, `graph-query-api/adapters/cosmos_config.py`

---

### 14. Unify `agent_ids.json` readers (Low risk, ~50 lines)

**Problem:** Four separate files independently read and parse `agent_ids.json` with different approaches:
1. `orchestrator.py` `_cached_agent_data()` — mtime-cached reader that parses to dict
2. `orchestrator.py` `load_agents_from_file()` — direct `json.loads()`, does NOT use the cache
3. `agents.py` `_load_dynamic_stubs()` — reads the same file, builds almost identical output as `load_agents_from_file()`
4. `alert.py` `_load_stub_agent_names()` — reads the file a fourth time for just agent names
5. `config.py` — reads `agent_ids.json` at module level with `try/except`

All four also independently compute the file path using different `Path()` resolution patterns.

**Fix:** Create a single `agent_ids.py` module (or add to an existing shared module) with:
```python
AGENT_IDS_PATH = Path(__file__).resolve().parents[N] / "scripts" / "agent_ids.json"

def load_agent_ids() -> dict:
    """Read and parse agent_ids.json with file-mtime caching."""

def get_agent_names() -> dict[str, str]:
    """Return {agent_id: agent_name} mapping."""

def get_agent_list() -> list[dict]:
    """Return list of agent stubs for the /agents endpoint."""
```

All four files import from this single module.

**Files:** `api/app/orchestrator.py`, `api/app/routers/agents.py`, `api/app/routers/alert.py`, `api/app/routers/config.py`

> **Note:** `provision_agents.py` / `deploy.sh` reference `agent_ids.json` but do not parse it in Python — excluded from this item.

---

### 15. Generic Fabric `_find_or_create` helper (Medium risk, ~160 lines)

**Problem:** `fabric_provision.py` has four nearly identical `_find_or_create_*` functions (`_find_or_create_lakehouse`, `_find_or_create_eventhouse`, `_find_or_create_kql_database`, `_find_or_create_ontology`) that all follow the same pattern:
1. GET list endpoint → find item by name
2. If not found, POST create endpoint
3. Handle 201 (immediate) / 202 (LRO) responses
4. Return item ID

Each function is ~40-50 lines. The only differences are the URL path, the JSON body shape, and the display name.

**Fix:** Create a generic helper:
```python
async def _find_or_create(
    client: httpx.AsyncClient, headers: dict,
    workspace_id: str, resource_type: str,
    display_name: str, create_body: dict,
    emit: Callable[[str], None],
) -> str:
    """Generic find-or-create for Fabric workspace items."""
```

Four functions (~200 lines total) collapse to four calls (~40 lines total).

⚠️ **Gotcha:** `_find_or_create_ontology` has a unique **try/except fallback discovery pattern** (tries `/ontologies` endpoint first, falls back to `/items` with type filter). `_find_or_create_eventhouse` also uses `/items` with a type filter, unlike `_find_or_create_lakehouse` which uses a dedicated list endpoint. The generic function signature needs a `list_endpoint` parameter + optional `fallback_endpoint` / `type_filter` parameters to handle these variations:
```python
async def _find_or_create(
    client: httpx.AsyncClient, headers: dict,
    workspace_id: str, resource_type: str,
    display_name: str, create_body: dict,
    emit: Callable[[str], None],
    list_endpoint: str | None = None,   # Use dedicated endpoint if provided
    type_filter: str | None = None,     # Filter /items by type if no dedicated endpoint
    fallback_endpoint: str | None = None,  # For ontology's fallback pattern
) -> str:
```

**Files:** `api/app/routers/fabric_provision.py`

---

### 16. Deduplicate SSE log broadcast infrastructure (Low risk, ~80 lines)

**Problem:** `api/app/routers/logs.py` (~80 lines) and `graph-query-api/main.py` (L140-220, ~80 lines) contain near-identical SSE log broadcasting code:
- Subscriber set with asyncio.Queue
- Broadcast function iterating subscribers
- Custom logging.Handler subclass that calls broadcast
- SSE generator yielding from subscriber queue
- Log endpoint returning StreamingResponse/EventSourceResponse

The only differences are variable naming and SSE serialization format.

**Fix:** Extract a reusable `LogBroadcaster` class:
```python
class LogBroadcaster:
    def __init__(self, max_buffer: int = 200):
        self._subscribers: set[asyncio.Queue] = set()
        self._buffer: deque = deque(maxlen=max_buffer)
    
    def broadcast(self, record: dict): ...
    def subscribe(self) -> AsyncGenerator: ...
    def get_handler(self) -> logging.Handler: ...
```

Both services import and instantiate `LogBroadcaster` instead of reimplementing the same infrastructure.

**Files:** `api/app/routers/logs.py`, `graph-query-api/main.py`

---

### 17. Deduplicate version-query logic (Low risk, ~25 lines)

**Problem:** The "query max version and increment" pattern for prompt versioning appears three times:
1. `router_prompts.py` L195-210 — `SELECT c.version FROM c WHERE ... ORDER BY c.version DESC`
2. `router_ingest.py` L958-970 — same query, same next-version calculation
3. `router_ingest.py` L1010-1023 — same pattern again for a different prompt type

**Fix:** Extract a shared helper:
```python
def get_next_version(container, scenario: str, prompt_type: str) -> int:
    """Query highest existing version for a prompt and return next version number."""
```

**Files:** `graph-query-api/router_prompts.py`, `graph-query-api/router_ingest.py`

---

### 18. Consolidate scenario name validation (Zero risk, ~15 lines)

**Problem:** `router_scenarios.py` implements scenario name validation twice:
1. `_validate_scenario_name()` — standalone function using `_NAME_RE` and `_RESERVED_SUFFIXES` (~18 lines)
2. `ScenarioSaveRequest.validate_name()` — Pydantic validator re-implementing the exact same logic (~13 lines)

**Fix:** Extract a pure validation function that raises `ValueError`, used by both:
```python
def _check_scenario_name(name: str) -> None:
    """Raise ValueError if name is invalid. Pure validation, no HTTP concerns."""
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid scenario name: {name!r}")
    if any(name.endswith(s) for s in _RESERVED_SUFFIXES):
        raise ValueError(f"Reserved suffix in name: {name!r}")

def _validate_scenario_name(name: str) -> None:
    """HTTP-aware wrapper. Raises HTTPException(400)."""
    try:
        _check_scenario_name(name)
    except ValueError as e:
        raise HTTPException(400, str(e))

@field_validator("name")
@classmethod
def validate_name(cls, v: str) -> str:
    _check_scenario_name(v)  # raises ValueError → Pydantic converts to 422
    return v
```

⚠️ **Gotcha:** Do NOT call `_validate_scenario_name()` directly from the Pydantic validator — it raises `HTTPException`, which Pydantic does not catch. Pydantic only catches `ValueError`/`TypeError`/`AssertionError`. An uncaught `HTTPException` would propagate as a 500 Internal Server Error instead of a 422 validation error.

**Files:** `graph-query-api/router_scenarios.py`

---

### 19. Extract shared SSE boilerplate in `fabric_provision.py` (Low risk, ~60 lines)

**Problem:** All four provisioning endpoints in `fabric_provision.py` (`provision_fabric_resources`, `provision_lakehouse`, `provision_eventhouse`, `provision_ontology`) have identical SSE wrapper boilerplate:
```python
async def stream():
    try:
        # ... unique logic ...
        yield _sse_event("done", {...})
    except HTTPException as he:
        yield _sse_event("error", {"detail": he.detail})
    except Exception as exc:
        yield _sse_event("error", {"detail": str(exc)})
    finally:
        await client.aclose()
return EventSourceResponse(stream())
```

Each is ~25 lines of identical structure wrapping ~5 lines of unique logic.

**Fix:** Create a wrapper:
```python
async def sse_provision_stream(client: httpx.AsyncClient, work: Callable):
    """Wrap an async provisioning function with standard SSE error handling."""
    try:
        async for event in work():
            yield event
        yield _sse_event("done", {"status": "complete"})
    except HTTPException as he:
        yield _sse_event("error", {"detail": he.detail})
    except Exception as exc:
        yield _sse_event("error", {"detail": str(exc)})
    finally:
        await client.aclose()
```

**Files:** `api/app/routers/fabric_provision.py`

---

### 20. Deduplicate provisioning helpers (Low risk, ~40 lines)

**Problem:** Three files independently implement the same provisioning utilities:
- **Connection ID construction:** `agent_provisioner.py` has `_build_connection_id()` helper; `config.py` builds the identical ARM resource ID string inline (~5 lines each)
- **Prompt placeholder substitution:** `provision_agents.py` has `_substitute_placeholders()` doing `.replace("{graph_name}", ...).replace("{scenario_prefix}", ...)`; `config.py` does the same inline
- **Project endpoint construction:** `f"{base_endpoint}/api/projects/{project_name}"` appears in 3 files

**Fix:** Move these to `agent_provisioner.py` (already the home for provisioning logic) and export them:
```python
def build_connection_id(sub_id, rg, foundry, project, connection_name) -> str: ...
def substitute_placeholders(text, graph_name, scenario_prefix) -> str: ...
def build_project_endpoint(base_endpoint, project_name) -> str: ...
```

**Files:** `scripts/agent_provisioner.py`, `scripts/provision_agents.py`, `api/app/routers/config.py`

---

## Tier 3 — Frontend structural improvements

### 21. Extract `formatTimeAgo` to shared utils (Zero risk, ~8 lines)

**Problem:** `formatTimeAgo()` is copy-pasted byte-for-byte in `App.tsx` and `InteractionSidebar.tsx`.

**Fix:** Move to `frontend/src/utils/formatTime.ts` and import in both files.

**Files:** `frontend/src/App.tsx`, `frontend/src/components/InteractionSidebar.tsx`

---

### 22. Extract `usePausableSimulation` hook (Low risk, ~70 lines)

**Problem:** `GraphTopologyViewer.tsx` and `ResourceVisualizer.tsx` both implement identical pause/freeze state machines (~35 lines each): `isPaused`, `manualPause`, `resumeTimeoutRef`, `handleMouseEnter`/`handleMouseLeave`, `handleTogglePause`, cleanup effect. Same variable names, same 300ms timeout constant.

**Fix:** Extract to `frontend/src/hooks/usePausableSimulation.ts`:
```typescript
function usePausableSimulation(canvasRef: RefObject<ForceGraphInstance>) {
  // Returns { isPaused, manualPause, handleMouseEnter, handleMouseLeave, handleTogglePause }
}
```

Both viewers replace ~35 lines with a single hook call.

**Files:** `frontend/src/components/GraphTopologyViewer.tsx`, `frontend/src/components/ResourceVisualizer.tsx`

---

### 23. Extract `useTooltipTracking` hook (Low risk, ~60 lines)

**Problem:** Both graph viewers implement identical tooltip + mouse-position tracking (~30 lines each): `tooltip` state, `mousePos` ref with global `mousemove` listener, `handleNodeHover`/`handleLinkHover` callbacks.

**Fix:** Extract to `frontend/src/hooks/useTooltipTracking.ts`:
```typescript
function useTooltipTracking() {
  // Returns { tooltip, mousePos, handleNodeHover, handleLinkHover, clearTooltip }
}
```

**Files:** `frontend/src/components/GraphTopologyViewer.tsx`, `frontend/src/components/ResourceVisualizer.tsx`

---

### 24. Extract `useClickOutside` hook (Zero risk, ~30 lines)

**Problem:** Three components manually attach `mousedown` document listeners with ref checks for click-outside behavior:
1. `AlertInput.tsx` (~8 lines)
2. `ScenarioChip.tsx` (~8 lines)
3. `ColorWheelPopover.tsx` (~6 lines)

**Fix:** Create `frontend/src/hooks/useClickOutside.ts`:
```typescript
function useClickOutside(ref: RefObject<HTMLElement>, onClose: () => void): void
```

Each component replaces 6-8 lines with a one-liner.

**Files:** `frontend/src/components/AlertInput.tsx`, `frontend/src/components/ScenarioChip.tsx`, `frontend/src/components/graph/ColorWheelPopover.tsx`

---

### 25. Reuse `<ThinkingDots>` in DiagnosisPanel (Zero risk, ~10 lines)

**Problem:** `DiagnosisPanel.tsx` contains an inline copy of the bouncing dots animation that is byte-for-byte identical to `<ThinkingDots>` (three `<div>` elements with `animate-bounce` and staggered delays).

**Fix:** Replace the inlined JSX with `<ThinkingDots />` and add the import.

**Files:** `frontend/src/components/DiagnosisPanel.tsx`

---

### 26. Merge `COLOR_PALETTE` / `AUTO_PALETTE` (Zero risk, ~4 lines)

**Problem:** `graphConstants.ts` exports `COLOR_PALETTE` (12 hex colors) and `useNodeColor.ts` defines `AUTO_PALETTE` — the same 12 colors in the same order.

**Fix:** Delete `AUTO_PALETTE` from `useNodeColor.ts` and import `COLOR_PALETTE` from `graphConstants.ts`.

**Files:** `frontend/src/components/graph/graphConstants.ts`, `frontend/src/hooks/useNodeColor.ts`

---

### 27. Extract `<ProgressBar>` component (Zero risk, ~20 lines)

**Problem:** Four places render the same progress bar JSX pattern:
- `UploadBox` in `SettingsModal.tsx`
- Overall progress in `AddScenarioModal.tsx`
- `FileSlot` in `AddScenarioModal.tsx`
- `ProvisioningBanner.tsx`

All use: outer `bg-neutral-bg2 rounded-full h-1.5` → inner `bg-brand h-1.5 rounded-full` with dynamic width.

**Fix:** Create `frontend/src/components/ProgressBar.tsx`:
```tsx
function ProgressBar({ pct, className }: { pct: number; className?: string }) {
  return (
    <div className={`bg-neutral-bg2 rounded-full h-1.5 ${className ?? ''}`}>
      <div className="bg-brand h-1.5 rounded-full transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}
```

**Files:** `SettingsModal.tsx`, `AddScenarioModal.tsx`, `ProvisioningBanner.tsx`

---

### 28. Extract `<ModalShell>` wrapper (Low risk, ~40 lines)

**Problem:** `SettingsModal.tsx` and `AddScenarioModal.tsx` both implement identical modal chrome:
- Fixed backdrop: `bg-black/60 backdrop-blur-sm`
- Dialog container: `bg-neutral-bg2 border border-white/10 rounded-xl`
- Header with title + close button (`✕`)
- Footer with action buttons

**Fix:** Create `frontend/src/components/ModalShell.tsx`:
```tsx
function ModalShell({ title, onClose, footer, children }: ModalShellProps) { ... }
```

Both modals become `<ModalShell title="Settings" onClose={...}>` wrappers around their tab content.

**Files:** `frontend/src/components/SettingsModal.tsx`, `frontend/src/components/AddScenarioModal.tsx`

---

### 29. Deduplicate provisioning SSE calls (Low risk, ~50 lines)

**Problem:** Three frontend locations independently implement the same "POST to `/api/config/apply` → `consumeSSE` → update provisioning status" pattern:
1. `ProvisioningBanner.tsx` (~25 lines)
2. `useScenarios.ts` `selectScenario` (~30 lines)
3. `SettingsModal.tsx` — two separate "Provision Agents" button handlers (~15 lines each)

**Fix:** Extract to a `useProvisioning()` hook or a shared `triggerProvisioning()` function:
```typescript
async function triggerProvisioning(
  body: object,
  onStatus: (status: string) => void,
  onProgress: (msg: string) => void,
): Promise<void>
```

All three call sites reduce to a single function call with callbacks.

**Files:** `frontend/src/components/ProvisioningBanner.tsx`, `frontend/src/hooks/useScenarios.ts`, `frontend/src/components/SettingsModal.tsx`

---

### 30. Move topology types to `types/index.ts` (Zero risk, 0 lines — reorganization)

**Problem:** Graph data types are split inconsistently:
- `TopologyNode`, `TopologyEdge`, `TopologyMeta` are exported from `useTopology.ts` (a hook file)
- `ResourceNode`, `ResourceEdge`, `ResourceNodeType` are exported from `types/index.ts` (the shared types file)

Both follow the same structural pattern but live in different places.

**Fix:** Move `TopologyNode`, `TopologyEdge`, `TopologyMeta` to `types/index.ts` alongside the Resource types. Update imports in consuming files.

**Files:** `frontend/src/hooks/useTopology.ts`, `frontend/src/types/index.ts`

---

## Tier 4 — Structural / architectural improvements

### 31. Split `router_ingest.py` God module (Medium risk, 0 lines — reorganization)

**Problem:** At 1,059 lines, `router_ingest.py` is a God module containing:
- Manifest normalization and validation helpers
- Gremlin client creation + retry (duplicated, addressed by #2/#10)
- ARM provisioning (NoSQL containers, Gremlin graphs)
- CSV schema parsing
- Graph ingestion endpoint
- Telemetry ingestion endpoint
- Knowledge file upload (runbooks + tickets)
- Prompt upload endpoint
- Scenario listing

These are distinct concerns that make the file hard to navigate and lead to the cross-cutting duplication identified in items 1-3 and 10-11.

**Fix:** Split into focused modules:
```
graph-query-api/
  router_ingest.py          → slim router, imports from:
  ingest/
    __init__.py              → re-exports the router
    manifest.py              → _extract_tar, _rewrite_manifest_prefix, _normalize_manifest
    graph_ingest.py          → upload_graph, _ingest_graph_csv, CSV schema helpers
    telemetry_ingest.py      → upload_telemetry
    knowledge_ingest.py      → upload_knowledge, _upload_knowledge_files
    prompt_ingest.py         → upload_prompts
    arm_helpers.py           → _ensure_gremlin_graph, _ensure_nosql_containers
```

**Prerequisite:** Complete items 1-3 and 10-11 first to shrink the file and remove duplication before splitting.

**Files:** `graph-query-api/router_ingest.py`

---

### 32. Split `SettingsModal.tsx` into tab components (Medium risk, 0 lines — reorganization)

**Problem:** At 860 lines, `SettingsModal.tsx` contains four full tab views inlined in a single component:
- Scenarios tab (L187-290): saved scenario list + CRUD
- Data Sources tab (L293-605): read-only bindings or manual dropdowns + action buttons
- Upload tab (L608-680): grid of `UploadBox` components
- Fabric Setup tab (L683-840): discovery, ontology selector, provisioning

It also contains the `UploadBox` sub-component (97 lines) defined in the same file.

**Fix:** Extract each tab into its own component:
```
frontend/src/components/settings/
  SettingsModal.tsx          → ~80 lines (tab switching + ModalShell chrome)
  ScenarioSettingsTab.tsx    → ~110 lines
  DataSourceSettingsTab.tsx  → ~315 lines
  UploadSettingsTab.tsx      → ~80 lines
  FabricSetupTab.tsx         → ~160 lines
  UploadBox.tsx              → ~97 lines
```

The modal component drops from 860 lines to ~80 lines of tab-switching logic.

**Prerequisite:** Complete item 7 (BindingCard extraction) first.

**Files:** `frontend/src/components/SettingsModal.tsx`

---

### 33. Extract upload orchestration from `AddScenarioModal` (Medium risk, 0 lines — reorganization)

**Problem:** `AddScenarioModal.tsx` (704 lines) mixes complex upload-state-machine logic (12 `useState` calls, sequential upload loops, timer management) with UI rendering.

**Fix:** Extract upload orchestration into `frontend/src/hooks/useScenarioUpload.ts`:
```typescript
function useScenarioUpload() {
  // Encapsulates: modalState, overallPct, currentUploadStep, file slots,
  // sequential upload logic, progress tracking, error handling
  // Returns: { state, files, setFile, startUpload, reset, ... }
}
```

Also extract the `FileSlot` sub-component (~90 lines) to its own file. The modal drops to ~300 lines.

Related: The 12 `useState` calls should be consolidated with `useReducer` for the upload state machine.

**Files:** `frontend/src/components/AddScenarioModal.tsx`

---

### ~~34.~~ ~~Lift `savedScenarios` into ScenarioContext~~ — SUPERSEDED BY #44

> This item is fully superseded by item #44, which includes the complete design with `activeScenarioRecord`, `refreshScenarios()`, and per-component consumption. Do not implement separately — skip to #44 in Phase 5.

**Files:** `frontend/src/hooks/useScenarios.ts`, `frontend/src/context/ScenarioContext.tsx`

---

### 35. Fix async violations in `config.py` (Low risk, correctness fix) — merged with #50

**Problem:** `api/app/routers/config.py` has multiple blocking calls in async context:
1. `urllib.request.urlopen()` used in async functions (L150, L476) — blocks event loop up to 30s
2. `provisioner.provision_all()` and `provisioner.provision_from_config()` called from `asyncio.create_task()` coroutine — blocks event loop ~30s during agent provisioning

Per Critical Pattern #1: "All Azure SDK calls MUST be in `asyncio.to_thread()`."

**Fix:**
- Replace `urllib.request.urlopen()` with `httpx.AsyncClient`:
```python
import httpx

GRAPH_API_BASE = os.getenv("GRAPH_QUERY_API_URI", "http://127.0.0.1:8100")

async def _fetch_from_graph_api(path: str, params: dict = {}) -> dict:
    async with httpx.AsyncClient(base_url=GRAPH_API_BASE, timeout=30) as client:
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()
```
- Wrap provisioner calls: `await asyncio.to_thread(provisioner.provision_from_config, ...)`
- Uses the existing `GRAPH_QUERY_API_URI` env var instead of hardcoded `127.0.0.1:8100`

> **Note:** Item 50 is merged into this item. Both address the same blocking calls in `config.py`.

**Files:** `api/app/routers/config.py`

---

### 36. Centralize path and config constants (Low risk, ~25 lines)

**Problem:** `PROJECT_ROOT`, `AGENT_IDS_FILE`, `CONFIG_FILE`, and `load_dotenv(CONFIG_FILE)` are independently computed in 5+ files:
- `api/app/orchestrator.py`
- `api/app/routers/config.py`
- `api/app/routers/agents.py`
- `api/app/routers/alert.py`
- `scripts/provision_agents.py`

Each uses slightly different `Path().resolve().parents[N]` patterns. The project endpoint `f"{base_endpoint}/api/projects/{project_name}"` also appears 3 times.

**Fix:** Create `api/app/paths.py`:
```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "azure_config.env"
AGENT_IDS_FILE = PROJECT_ROOT / "scripts" / "agent_ids.json"
```

All files import from this single module.

**Files:** 5+ files across `api/` and `scripts/`

---

## Tier 5 — Dead code & cleanup

### 37. Delete `FabricGQLBackend.aclose()` (Zero risk, ~5 lines)

**Problem:** `backends/fabric.py` has both `close()` (sync) and `aclose()` (async). `close_all_backends()` in `backends/__init__.py` only calls `.close()` and checks `inspect.isawaitable(result)`. The `aclose()` method is never called by the framework — dead code.

**Fix:** Delete `aclose()`.

**Files:** `graph-query-api/backends/fabric.py`

---

### ~~38. Remove unused `GRAPH_BACKEND` import~~ — SKIP

**Problem (original claim):** `backends/cosmosdb.py` imports `GRAPH_BACKEND` from `config` but never references it.

**Verdict:** **WRONG** — `GRAPH_BACKEND` is referenced in a diagnostic error message at L133 (`"when GRAPH_BACKEND=cosmosdb"`). The import is live. Leave as-is.

---

### 39. Remove unused `close_all_backends` import (Zero risk, ~1 line)

**Problem:** `graph-query-api/main.py` imports `close_all_backends` from `backends` but only uses it indirectly via `close_graph_backend()` (which itself calls `close_all_backends()`). The direct import is unused.

**Fix:** Remove the import.

**Files:** `graph-query-api/main.py`

---

### 40. Delete unused Fabric env vars (Zero risk, ~8 lines)

**Problem:** `adapters/fabric_config.py` defines 5+ environment variable constants (`FABRIC_WORKSPACE_NAME`, `FABRIC_ONTOLOGY_ID`, `FABRIC_ONTOLOGY_NAME`, `FABRIC_EVENTHOUSE_ID`, `FABRIC_EVENTHOUSE_NAME`, `FABRIC_KQL_DB_ID`, `FABRIC_KQL_DB_NAME`, `EVENTHOUSE_QUERY_URI`) that are never referenced outside this file. Comments say "for future telemetry — Gap 1".

**Fix:** Delete unused variables. Re-add when they're actually needed (YAGNI).

**Files:** `graph-query-api/adapters/fabric_config.py`

---

### 41. Delete empty `NODE_COLORS`/`NODE_SIZES` constants (Zero risk, ~6 lines)

**Problem:** `graphConstants.ts` exports `NODE_COLORS = {}` and `NODE_SIZES = {}` as empty objects. Comments indicate all values come from scenario styles. `useNodeColor` falls through to `autoColor()` regardless, making these constants meaningless.

**Fix:** Delete the exports and remove any imports of them. If a default-fallback pattern is needed later, it can be re-added.

**Files:** `frontend/src/components/graph/graphConstants.ts`

---

### 42. Remove unused `runStarted` prop plumbing (Zero risk, ~4 lines)

**Problem:** `App.tsx` passes `runStarted` to `DiagnosisPanel`, which renames it to `_runStarted` (explicitly unused). The prop flows through the component tree for no purpose.

**Fix:** Remove `runStarted` from `DiagnosisPanel`'s props interface and stop passing it from `App.tsx`.

**Files:** `frontend/src/App.tsx`, `frontend/src/components/DiagnosisPanel.tsx`

---

### 43. Move mock topology data to JSON fixture (Zero risk, ~152 lines moved to file)

**Problem:** `backends/mock.py` contains ~152 lines of hardcoded Python literal topology data (nodes, edges, properties including `_TOPOLOGY_NODES`, `_TOPOLOGY_EDGES`, `_CORE_ROUTERS`). This makes the mock backend hard to read and the test data hard to maintain.

**Fix:** Move the topology data to `graph-query-api/backends/fixtures/mock_topology.json` and load it with `json.load()` in the mock backend. The Python file shrinks by ~152 lines while the data becomes version-controllable JSON.

**Files:** `graph-query-api/backends/mock.py`

---

## Bonus: Known bug fixes to include during refactor

These aren't line-reduction items but should be fixed while touching these files:

| Bug | File | Fix |
|-----|------|-----|
| Edge topology f-string bug | `backends/cosmosdb.py` | Add `f` prefix to `.where()` line in `get_topology()` |
| `useInvestigation` stale closure | `frontend/src/hooks/useInvestigation.ts` | Add `getQueryHeaders` to `submitAlert`'s `useCallback` dep array |
| `submitAlert` recreated on every keystroke | `frontend/src/hooks/useInvestigation.ts` | `alert` in dep array causes callback recreation on each character. Use a ref for alert value inside `submitAlert` |
| `useFabricDiscovery` stale closure | `frontend/src/hooks/useFabricDiscovery.ts` | `provisionState` check after `await consumeSSE()` uses closure value, not current state. Use a ref to track latest state |
| `logs.py` ~~unused `dead` variable~~ | ~~`api/app/routers/logs.py`~~ | ~~SKIP~~ — verified only one `dead` declaration exists; no shadowing bug |
| `graphConstants` missing try-catch | `frontend/src/components/GraphTopologyViewer.tsx` | `localStorage.getItem` + `JSON.parse` in `useState` initializer has no try-catch. Corrupt localStorage data crashes the component |
| Exception-too-broad in `router_interactions.py` | `graph-query-api/router_interactions.py` | Bare `except Exception` on L96-109 catches network errors and remaps to 404. Should catch `KeyError`/`NotFoundError` specifically |
| `config.py` redundant exception tuple | `graph-query-api/config.py` | `except (ValueError, Exception): pass` — `Exception` already subsumes `ValueError` |
| Bare `except` in `router_scenarios.py` | `graph-query-api/router_scenarios.py` | `try: existing = await store.get(...) except Exception: pass` silently swallows connection errors |
| `InvestigationPanel` redundant fetch | `frontend/src/components/InvestigationPanel.tsx` | Calls `useScenarios()` just to get `example_questions`, triggering a full scenarios fetch. Receive via context instead (addressed by item #44) |

---

## Suggested execution order

**Phase 1 — Zero-risk cleanup (day 1)**
Items 4, 5, 13, 21, 25, 26, 30, 37, ~~38 (SKIP)~~, 39, 40, 41, 42 + all zero-risk bonus bugs

**Phase 2 — Low-risk backend dedup (days 2-3)**
Items 1, 2, 3, 6, 8, 10, 11, 12, 14, 17, 18, 20, 36 + blocking-bug fixes (bonus items)

**Phase 3 — Low-risk frontend dedup (days 3-4)**
Items 7, 22, 23, 24, 27, 28, 29 + frontend bug fixes

**Phase 4 — Medium-risk structural changes (days 5-7)**
Items 9, 15, 16, 19, 31, 32, 33, 35+50 (merged — fix all blocking calls in `config.py`), 43

**Phase 5 — Architectural correctness (days 7-9)**
Items 44 (supersedes #34), 45, 46 (depends on #48), 47, 48, 49

---

## Tier 6 — Architectural correctness

### 44. Promote `activeScenarioRecord` + `savedScenarios` into context (Medium risk, eliminates 4x fetch)

**Problem:** `ScenarioContext` stores only `activeScenario: string | null` — just the name. Four hooks/components independently fetch the full scenarios list just to look up fields on the active record:

```
ScenarioChip         → useScenarios() → GET /query/scenarios/saved  ← copy A
SettingsModal        → useScenarios() → GET /query/scenarios/saved  ← copy B
InvestigationPanel   → useScenarios() → GET /query/scenarios/saved  ← copy C (only reads example_questions)
ScenarioInfoPanel    → useScenarios() → GET /query/scenarios/saved  ← copy D (only reads description)
```

Result: 3-4 identical HTTP requests on mount, with isolated copies that don't sync.

**Fix:** Add to `ScenarioContext`:

```typescript
interface ScenarioState {
  // ... existing fields ...
  savedScenarios: SavedScenario[];
  activeScenarioRecord: SavedScenario | null;
  scenariosLoading: boolean;
  refreshScenarios: () => Promise<void>;
}
```

- `InvestigationPanel` reads `activeScenarioRecord.example_questions` from context
- `ScenarioInfoPanel` reads `activeScenarioRecord.description` from context
- `ScenarioChip` reads `savedScenarios` from context
- The mount-time validation effect in `ScenarioContext` already fetches this data — just store the result instead of throwing it away
- `useScenarios()` becomes a smaller utility exposing only mutation logic (`saveScenario`, `deleteScenario`) + discovery calls

**Relationship to item #34:** Item 34 describes the same goal at a higher level. This item supersedes it with the full design including `activeScenarioRecord` and `refreshScenarios()`. Treat #34 as merged into #44.

**Files:** `frontend/src/context/ScenarioContext.tsx`, `frontend/src/hooks/useScenarios.ts`, `frontend/src/components/InvestigationPanel.tsx`, `frontend/src/components/ScenarioInfoPanel.tsx`, `frontend/src/components/ScenarioChip.tsx`

---

### 45. Clear investigation state on scenario switch (Low risk, correctness fix)

**Problem:** When the user switches scenarios, investigation state (`steps`, `finalMessage`, `thinking`, `errorMessage`, `alert` text) is never cleared. Steps from a VPN investigation in scenario A remain visible after switching to scenario B until the user manually starts a new investigation.

**Fix:** Add an effect in `App.tsx` (where `useInvestigation` is called):

```typescript
useEffect(() => {
  setSteps([]);
  setThinking(null);
  setFinalMessage('');
  setErrorMessage('');
  setRunMeta(null);
  const example = activeScenarioRecord?.example_questions?.[0];
  setAlert(example ?? '');
}, [activeScenario]);
```

The hardcoded `DEFAULT_ALERT` constant can be removed — the alert input initializes empty and populates from the scenario's `example_questions` if available.

**Files:** `frontend/src/App.tsx`, `frontend/src/hooks/useInvestigation.ts`

---

### 46. Persist `_current_config` to disk (Medium risk, prevents split-brain on restart)

**Problem:** `api/app/routers/config.py` stores active data-source bindings in an in-memory dict `_current_config`. On container restart, it reverts to env-var defaults, creating split-brain:

```
AFTER RESTART:
  Backend _current_config: { graph: "topology" }               ← reverted to env default!
  Frontend localStorage:   { activeScenario: "cloud-outage" }  ← thinks cloud-outage is active
  agent_ids.json:          { provisioned for cloud-outage }    ← agents bound to old data
```

Agents are provisioned for scenario X's data, but the backend silently queries default data sources.

**Fix:** Write `_current_config` to `active_config.json` alongside `agent_ids.json` using **atomic writes**:

```python
import tempfile

ACTIVE_CONFIG_PATH = PROJECT_ROOT / "scripts" / "active_config.json"

def _save_config(config: dict):
    with _config_lock:
        global _current_config
        _current_config = config
        # Atomic write: write to temp file, then rename (prevents corruption on crash)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=ACTIVE_CONFIG_PATH.parent, suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(config, f, indent=2)
            os.rename(tmp_path, ACTIVE_CONFIG_PATH)
        except Exception:
            os.unlink(tmp_path)
            raise

def _load_current_config() -> dict:
    global _current_config
    if _current_config is not None:
        return _current_config
    if ACTIVE_CONFIG_PATH.exists():
        try:
            _current_config = json.loads(ACTIVE_CONFIG_PATH.read_text())
            return _current_config
        except Exception:
            pass
    _current_config = { ... }  # env-var defaults
    return _current_config
```

On successful provisioning, call `_save_config()` instead of directly assigning. On startup, load from disk. Clean separation: `agent_ids.json` = agent topology, `active_config.json` = data-source bindings.

⚠️ **Prerequisite:** Implement item #48 (provisioning concurrency guard) **before** this item — without a concurrency guard, two concurrent `apply_config` calls could race on the file write. The atomic write pattern (`tempfile` + `os.rename`) protects against crash-during-write but not against two writers clobbering each other's config.

**Files:** `api/app/routers/config.py`

---

### 47. Scope localStorage graph customizations per scenario (Low risk, ~4 lines)

**Problem:** `localStorage` keys `graph-colors` and `graph-display-fields` are global. If the user sets "CoreRouter" nodes to red in scenario A, switching to scenario B inherits that override. The `useNodeColor` resolution chain (`userOverride → scenarioNodeColors → autoColor`) means user overrides always win, silently suppressing scenario B's intended styling.

**Fix:** Key localStorage entries by scenario name:

```typescript
localStorage.getItem(`graph-colors:${activeScenario ?? '__custom__'}`)
```

Also wrap reads in try-catch — currently `JSON.parse(localStorage.getItem(...))` has no error handling and corrupt data crashes the component.

**Files:** `frontend/src/components/GraphTopologyViewer.tsx`

---

### 48. Provisioning concurrency guard (Medium risk, ~15 lines)

**Problem:** Four UI entry points can trigger `POST /api/config/apply` concurrently:
1. ScenarioChip → `selectScenario()`
2. ProvisioningBanner → "Provision Now"
3. SettingsModal → "Provision Agents" (custom mode)
4. SettingsModal → "Re-provision Agents" (scenario mode)

Entry points 1-2 update `provisioningStatus` in context; 3-4 use local ActionButton state. Nothing prevents concurrent requests.

**Fix — two layers:**

1. **Frontend:** When `provisioningStatus.state === 'provisioning'`, disable all provisioning triggers (scenario selection, provision buttons)

2. **Backend:** Add an `asyncio.Lock` (not a simple bool) to `apply_config()`:
   ```python
   _provisioning_lock = asyncio.Lock()

   @router.post("/apply")
   async def apply_config(req: ConfigApplyRequest):
       if _provisioning_lock.locked():
           raise HTTPException(409, "Provisioning already in progress")
       async with _provisioning_lock:
           # ... provisioning logic ...
   ```

⚠️ **Gotcha — `finally` placement:** The current code spawns provisioning via `asyncio.create_task(run_provisioning())` and immediately starts yielding SSE events. If using a simple bool, the `finally` block **must be inside `run_provisioning()`**, not inside `apply_config()` — otherwise the flag clears when the SSE stream finishes, while the background task may still be running. Using `asyncio.Lock` as shown above avoids this entirely because the lock is held for the duration of the `async with` block.

Also: ensure all provisioning entry points (including SettingsModal's ActionButton handlers) route through `setProvisioningStatus()` in context.

**Files:** `api/app/routers/config.py`, `frontend/src/components/ScenarioChip.tsx`, `frontend/src/components/ProvisioningBanner.tsx`, `frontend/src/components/SettingsModal.tsx`

---

### 49. Derive agent count from actual data (Low risk, ~5 lines)

**Problem:** `Header.tsx` L12-20 hardcodes \"5 Agents\" regardless of actual agent count. Config-driven provisioning creates a variable number of agents.

**Fix:** The `/api/agents` endpoint already returns the actual agent list. Route the count through context via the provisioning done event:

```typescript
const agentCount = provisioningStatus.state === 'done'
  ? provisioningStatus.agentCount
  : agents.length;
// Display: `${agentCount} Agent${agentCount !== 1 ? 's' : ''} ✓`
```

Requires adding `agentCount` to the `ProvisioningStatus` "done" state, set from the SSE `complete` event data.

**Files:** `frontend/src/components/Header.tsx`, `frontend/src/context/ScenarioContext.tsx`

---

### ~~50.~~ ~~Fix blocking urllib calls in `config.py`~~ — MERGED INTO #35

> This item is fully merged into item #35 above, which now contains the complete fix including the `httpx.AsyncClient` replacement and `asyncio.to_thread()` wrapping for provisioner calls. Do not implement separately.

**Files:** `api/app/routers/config.py`