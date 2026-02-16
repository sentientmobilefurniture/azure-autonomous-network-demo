# V9generalflow.md — Audit Report

> **Audited:** 2026-02-16
> **Source:** [V9generalflow.md](V9generalflow.md)
> **Scope:** Bugs, gotchas, and issues that could ruin implementation

---

## Severity Legend

| Level | Meaning |
|-------|---------|
| **CRITICAL** | Runtime failure in core functionality. Must fix before implementing. |
| **HIGH** | Will cause startup crashes, incorrect behavior, or dead-end implementation. |
| **MEDIUM** | Performance regressions, misleading guidance, or incomplete specifications. |
| **LOW** | Cosmetic inaccuracies, wasted effort, or unnecessary work. |

---

## CRITICAL Issues

### C-1. `DocumentStore.list()` Missing `parameters` Argument

**Location:** Item 1 — DocumentStore Protocol definition (L263–L275)

The Protocol defines:
```python
async def list(self, *, query: str | None = None, partition_key: str | None = None, max_items: int | None = None)
```

But the actual codebase uses **parameterized Cosmos queries** (`parameters=[{"name": "@foo", "value": bar}]`) at **7 call sites across 4 files**:

| File | Parameters Used |
|------|----------------|
| `router_interactions.py` L75–82 | `@scenario`, `@limit` |
| `router_prompts.py` L129 | `@agent` |
| `router_prompts.py` L202–209 | `@agent`, `@scenario`, `@name` |
| `router_ingest.py` L790–801 | `@a`, `@s`, `@n` |
| `router_ingest.py` L837–845 | `@s` |

Without `parameters`, the only way to pass filter values is string interpolation — **an SQL injection vector** against Cosmos DB.

**Proposed Fix:** Add `parameters` to the Protocol and implementation:

```python
# In DocumentStore Protocol
async def list(
    self,
    *,
    query: str | None = None,
    parameters: list[dict[str, Any]] | None = None,   # ← ADD
    partition_key: str | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]: ...

# In CosmosDocumentStore.list()
kwargs: dict = {"query": q, "enable_cross_partition_query": True}
if parameters:
    kwargs["parameters"] = parameters               # ← ADD
if partition_key:
    kwargs["partition_key"] = partition_key
    kwargs["enable_cross_partition_query"] = False   # ← see also M-1
```

---

### C-2. `ConnectedAgentTool` Missing `.definitions` Call

**Location:** Item 8 — `provision_from_config()` (L937–L952)

The plan creates `ConnectedAgentTool` objects and passes them directly to `create_agent()`:

```python
connected_tools = [
    ConnectedAgentTool(id=created_agents[name], name=name, description=f"Delegate to {name}")
    for name in agent_def.get("connected_agents", [])
]
agent = self._client.agents.create_agent(..., tools=connected_tools)
```

But the actual working code in `agent_provisioner.py` L256–261 calls `.definitions`:

```python
ct = ConnectedAgentTool(id=sa["id"], name=sa["name"], description=sa["description"])
connected_tools.extend(ct.definitions)  # ← .definitions required
```

The SDK expects tool **definitions** (dicts), not wrapper objects. Without `.definitions`, the orchestrator gets created with **zero connected agents**.

**Proposed Fix:**

```python
for name in agent_def.get("connected_agents", []):
    ct = ConnectedAgentTool(
        id=created_agents[name], name=name, description=f"Delegate to {name}"
    )
    connected_tools.extend(ct.definitions)  # ← use .definitions

agent = self._client.agents.create_agent(
    ..., tools=connected_tools  # now contains dicts, not wrapper objects
)
```

---

### C-3. `_build_tools()` Missing `.definitions` and `tool_resources`

**Location:** Item 8 — `_build_tools()` (L958–L975)

The plan appends raw tool objects:
```python
tools.append(OpenApiTool(...))
tools.append(AzureAISearchTool(...))
```

But the actual SDK usage requires:

| Tool Type | Actual Pattern | What Plan Does |
|-----------|---------------|----------------|
| `OpenApiTool` | `tools = tool.definitions` | `tools.append(OpenApiTool(...))` — wrong type |
| `AzureAISearchTool` | `tools=search_tool.definitions, tool_resources=search_tool.resources` | `tools.append(AzureAISearchTool(...))` — missing `tool_resources` |

`create_agent(tools=[OpenApiTool(...)])` will raise a type error. `AzureAISearchTool` additionally requires `tool_resources` passed as a **separate** kwarg to `create_agent()`.

**Proposed Fix:** Restructure `_build_tools()` to return both `tool_definitions` and `tool_resources`:

```python
def _build_tools(self, agent_def, config, api_uri, search_conn_id, graph_name):
    tool_definitions = []
    tool_resources = None

    for tool_def in agent_def.get("tools", []):
        if tool_def["type"] == "openapi":
            spec = _load_openapi_spec(...)
            tool = OpenApiTool(name=..., spec=spec, description=...,
                               auth=OpenApiAnonymousAuthDetails())
            tool_definitions.extend(tool.definitions)  # ← .definitions

        elif tool_def["type"] == "azure_ai_search":
            index_name = config["data_sources"]["search_indexes"][tool_def["index_key"]]
            search_tool = AzureAISearchTool(
                index_connection_id=search_conn_id, index_name=index_name
            )
            tool_definitions.extend(search_tool.definitions)  # ← .definitions
            tool_resources = search_tool.resources             # ← capture resources

    return tool_definitions, tool_resources

# Usage in provision_from_config():
tools, tool_resources = self._build_tools(agent_def, ...)
agent = self._client.agents.create_agent(
    ..., tools=tools, tool_resources=tool_resources   # ← pass both
)
```

---

## HIGH Issues

### H-1. `max_items` Maps to `max_item_count` — Wrong Semantics

**Location:** Item 1 — `CosmosDocumentStore.list()` (L306–L308)

The plan maps `max_items` → `max_item_count`:
```python
if max_items:
    kwargs["max_item_count"] = max_items
```

But `max_item_count` controls **page size** (items per round-trip), not total result count. `list(container.query_items(max_item_count=50))` still returns **ALL matching documents** — just fetched in 50-item pages.

The actual code limits results via SQL `OFFSET 0 LIMIT @limit`:
```python
query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
params.append({"name": "@limit", "value": limit})
```

**Proposed Fix:** Remove `max_items` from the Protocol. Callers embed `LIMIT` in their SQL query string (and use the `parameters` argument from C-1 to pass the value safely). This matches the existing pattern.

```python
# Remove max_items from Protocol signature:
async def list(
    self,
    *,
    query: str | None = None,
    parameters: list[dict[str, Any]] | None = None,
    partition_key: str | None = None,
    # max_items removed — use SQL LIMIT instead
) -> list[dict[str, Any]]: ...
```

---

### H-2. Plan's Migration Example Doesn't Match Actual Code

**Location:** Item 4a — "Current Code Pattern" (L553–L564)

The plan shows:
```python
# Plan's version of router_interactions.py
query += f" WHERE c.scenario = '{scenario}'"  # ← string interpolation
items = list(container.query_items(query=query, enable_cross_partition_query=True))
return items[:limit]
```

The **actual code** at `router_interactions.py` L70–93:
```python
# Actual code — parameterized, branched, different limit mechanism
params.append({"name": "@scenario", "value": scenario})
query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
if scenario:
    container.query_items(query=query, parameters=params, partition_key=scenario)
else:
    container.query_items(query=query, parameters=params, enable_cross_partition_query=True)
```

Key differences:
1. Uses parameterized queries (not f-string interpolation)
2. Uses `partition_key=scenario` for scoped queries (not always `enable_cross_partition_query=True`)
3. Uses SQL `OFFSET 0 LIMIT @limit` (not Python `[:limit]` slicing)

Implementers following the plan's example verbatim would lose parameterized queries, partition key scoping, and SQL LIMIT support.

**Proposed Fix:** Replace the plan's "Current Code Pattern" and "New Code Pattern" blocks with accurate representations of the actual code. The migrated version should be:

```python
# router_interactions.py — migrated (accurate)
async def list_interactions(scenario=None, limit=50):
    store = _get_store()
    query = "SELECT * FROM c"
    params = []
    if scenario:
        query += " WHERE c.scenario = @scenario"
        params.append({"name": "@scenario", "value": scenario})
    query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
    params.append({"name": "@limit", "value": limit})
    items = await store.list(
        query=query,
        parameters=params,
        partition_key=scenario,  # scoped when filtering
    )
    return items
```

---

### H-3. Six `.value` Calls Will Crash After Enum Removal

**Location:** Item 7 — Backend Registry (L830–L850)

Phase 7 removes `GraphBackendType` enum → plain `str`. But **6 call sites** use `.value`:

| File | Line | Code |
|------|------|------|
| `router_graph.py` | L51 | `ctx.backend_type.value` |
| `main.py` | L67 | `GRAPH_BACKEND.value` |
| `main.py` | L76 | `GRAPH_BACKEND.value` |
| `main.py` | L85 | `GRAPH_BACKEND.value` |
| `main.py` | L233 | `GRAPH_BACKEND.value` |
| `backends/__init__.py` | L97 | `bt.value` |

The plan generically says "Grep for `.value` on backend_type" but **doesn't list `main.py`** which has 4 of 6 occurrences. `main.py` is the FastAPI app entrypoint — `.value` on `str` = `AttributeError` = **app won't start**.

**Proposed Fix:** Add to Phase 7 an explicit checklist:

```bash
# After removing GraphBackendType enum, run:
grep -rn "\.value" graph-query-api/ | grep -i "backend"
# Expected matches (all must be changed):
#   main.py:67     GRAPH_BACKEND.value  →  GRAPH_BACKEND
#   main.py:76     GRAPH_BACKEND.value  →  GRAPH_BACKEND
#   main.py:85     GRAPH_BACKEND.value  →  GRAPH_BACKEND
#   main.py:233    GRAPH_BACKEND.value  →  GRAPH_BACKEND
#   router_graph.py:51  ctx.backend_type.value  →  ctx.backend_type
#   backends/__init__.py:97  bt.value  →  bt
```

---

### H-4. `fetch_scenario_config()` Referenced But Never Defined

**Location:** Item 8 — `api/app/routers/config.py` changes (L986–L990)

The plan shows:
```python
scenario_config = fetch_scenario_config(req.prompt_scenario)
provisioner.provision_from_config(config=scenario_config, ...)
```

But `fetch_scenario_config()` **doesn't exist anywhere** — not in the plan, not in the codebase. The `scenarios/scenarios` Cosmos container stores resource bindings but **NOT** agent definitions or tool configs. The scenario YAML with the `agents:` section (added in Phase 13) is uploaded as part of the data tarball and partially persisted — but there's no retrieval function.

**Proposed Fix:** Define the config retrieval pipeline explicitly:

```
Option A (Recommended): Store full scenario config during upload
  1. At upload time (router_ingest.py), parse scenario.yaml and store the
     full config dict in the `scenarios/scenarios` Cosmos container alongside
     existing fields (resources, upload_status, etc.)
  2. Add a `config` field to the scenario document
  3. fetch_scenario_config() = read scenario from Cosmos, return .config

Option B: Store scenario.yaml in Blob Storage
  1. During upload, also save scenario.yaml to blob storage
  2. fetch_scenario_config() = download YAML from blob, parse, return

Option A is simpler and keeps everything in one database read.
```

Add this function definition to the plan:

```python
async def fetch_scenario_config(scenario_name: str) -> dict:
    """Retrieve the full scenario config from the scenarios database."""
    store = get_document_store("scenarios", "scenarios", "/id", ensure_created=True)
    doc = await store.get(item_id=scenario_name, partition_key=scenario_name)
    config = doc.get("config")
    if not config:
        raise HTTPException(404, f"No config found for scenario '{scenario_name}'")
    return config
```

---

### H-5. Phases 8 and 9 Cannot Run in Parallel

**Location:** Implementation Phases — parallelism claim (L204)

The plan states "Phase 8 and 9 can run in parallel." But Phase 8's `_build_tools()` calls `_load_openapi_spec()` with a `spec_template` parameter:

```python
spec = _load_openapi_spec(api_uri, tool_def["spec_template"], ...)  # "spec_template" is new
```

The current `_load_openapi_spec()` in `agent_provisioner.py` L83–96 takes a `graph_backend` parameter (e.g., `"cosmosdb"`) that maps to static files. The `spec_template` → template file mapping is defined in Phase 9.

**Proposed Fix:** Update the dependency graph:
- Phase 9 (OpenAPI Templates) must come before Phase 8 (Config-Driven Provisioner)
- Or: Phase 8 must be written to use the **current** function signature (`graph_backend` param) and then be updated after Phase 9

The corrected parallelism: **Phases 8 and 9 are sequential (9 → 8), not parallel.**

---

### H-6. No Pydantic Validation for Scenario YAML Schema

**Location:** Item 13 — `scenario.yaml` with `agents:` section (L1370–L1430)

The plan adds a complex `agents:` section to scenario YAML with:
- `connected_agents` references (must match other agent names)
- `instructions_file` paths (must exist)
- `compose_with_connector` flag (triggers special behavior)
- `tools[].index_key` (must match `data_sources.search_indexes` keys)

But there is **no validation layer** anywhere in the plan. The current code parses YAML with raw `yaml.safe_load()` and dict access. A typo in `connected_agents` causes `KeyError` at provisioning time (acknowledged in Edge Cases section but with no prescribed solution).

**Proposed Fix:** Add a Pydantic model for scenario config validation to the plan, to be implemented in Phase 8:

```python
from pydantic import BaseModel, validator

class ToolDef(BaseModel):
    type: Literal["openapi", "azure_ai_search"]
    spec_template: str | None = None
    keep_path: str | None = None
    index_key: str | None = None

class AgentDef(BaseModel):
    name: str
    role: str
    model: str = "gpt-4.1"
    instructions_file: str
    compose_with_connector: bool = False
    is_orchestrator: bool = False
    connected_agents: list[str] = []
    tools: list[ToolDef] = []

class ScenarioConfig(BaseModel):
    scenario: dict
    data_sources: dict
    agents: list[AgentDef]

    @validator("agents")
    def validate_connected_agents(cls, agents):
        names = {a.name for a in agents}
        for a in agents:
            for ref in a.connected_agents:
                if ref not in names:
                    raise ValueError(f"Agent '{a.name}' references unknown connected_agent '{ref}'")
        return agents
```

Validate at upload time and provisioning time.

---

## MEDIUM Issues

### M-1. `enable_cross_partition_query` Always `True`

**Location:** Item 1 — `CosmosDocumentStore.list()` (L303–L305)

The plan always sets `enable_cross_partition_query=True`:
```python
kwargs: dict = {"query": q, "enable_cross_partition_query": True}
```

But actual code at `router_prompts.py` L209 and `router_ingest.py` L801 intentionally uses `enable_cross_partition_query=False` for queries scoped to a single partition key. Always enabling cross-partition queries causes unnecessary RU costs on large containers.

**Proposed Fix:** Default to `True` but set to `False` when `partition_key` is provided:

```python
kwargs: dict = {"query": q}
if partition_key:
    kwargs["partition_key"] = partition_key
    kwargs["enable_cross_partition_query"] = False
else:
    kwargs["enable_cross_partition_query"] = True
```

---

### M-2. `str.format_map()` Fragile for OpenAPI Templates

**Location:** Item 9 — OpenAPI Spec Templating (L1067–L1070)

The plan recommends `str.format_map()` over the current `.replace()`. But `format_map()` treats **any** `{...}` in the template as a placeholder. Future templates with JSON Schema examples (e.g., `{"type": "string"}`) in description fields would cause `KeyError`.

The current `.replace("{base_url}", ...)` approach is strictly safer — it only touches known placeholders.

**Proposed Fix:** Keep using `.replace()` for each known placeholder. Add a comment documenting why `format_map()` was rejected:

```python
# Using .replace() per-placeholder instead of str.format_map() because
# OpenAPI YAML files may contain literal {braces} in JSON Schema examples.
raw = raw.replace("{base_url}", api_uri.rstrip("/"))
raw = raw.replace("{graph_name}", graph_name)
raw = raw.replace("{query_language_description}", connector_vars.get("query_language_description", ""))
```

---

### M-3. `compose_with_connector: true` Under-Specified

**Location:** Item 10 — Config-Driven Prompt System (L1092–L1100)

The plan says:
> When `compose_with_connector` is true, the system reads all .md files
> in the directory, auto-selects `language_{connector}.md`, and joins them.

But the actual composition logic in `router_ingest.py` L820–870:
1. Reads files in a **hardcoded order**: `core_instructions.md`, `core_schema.md`, `language_gremlin.md`
2. Joins with `"\n\n---\n\n"` (specific separator)
3. Missing files are silently skipped
4. Only `language_gremlin.md` — no `language_kusto.md` or connector resolution

The plan's "reads all .md files" is wrong — the actual code reads a **specific ordered subset**. File order matters (instructions → schema → language-specific).

**Proposed Fix:** Replace `compose_with_connector: true` with explicit composition config:

```yaml
agents:
  - name: "GraphExplorerAgent"
    instructions:
      compose:
        files:
          - "core_instructions.md"
          - "core_schema.md"
        connector_file_pattern: "language_{connector}.md"
        separator: "\n\n---\n\n"
        directory: "prompts/graph_explorer/"
```

This makes file order, separator, and connector resolution explicit and declarative.

---

### M-4. Ingest Protocol Needs Schema-to-Dict Transformation Layer

**Location:** Item 6 — `GraphBackend.ingest()` (L714–L740)

The plan defines:
```python
async def ingest(self, vertices: list[dict], edges: list[dict], ...)
```

But the actual loading code at `router_ingest.py` L376–440 doesn't work with flat `{label, properties}` dicts. It iterates **schema definitions** from `graph_schema.yaml` and reads **CSV files** per vertex type:

```
Schema (graph_schema.yaml) → CSV file reads → Gremlin query construction → Submission
```

Moving the Gremlin submission into `GraphBackend.ingest()` is correct, but the caller (router) needs ~40 lines of transformation code to convert `(schema + CSV data) → list[dict]`. This code isn't defined in the plan.

**Proposed Fix:** Add a `_prepare_vertices_from_schema()` helper to the Phase 6 plan:

```python
# In router_ingest.py — transformation layer
def _prepare_vertices_from_schema(schema: dict, data_dir: Path) -> list[dict]:
    """Convert graph_schema.yaml vertex definitions + CSV data → flat dicts."""
    vertices = []
    for vdef in schema.get("vertices", []):
        csv_path = data_dir / vdef["csv_file"]
        rows = _read_csv(csv_path)
        for row in rows:
            vertices.append({
                "label": vdef["label"],
                "id": row[vdef["id_column"]],
                "partition_key": row.get(vdef.get("partition_key_column", vdef["id_column"])),
                "properties": {p["name"]: row.get(p["column"], "") for p in vdef["properties"]},
            })
    return vertices

# Similar for edges: _prepare_edges_from_schema()
```

---

### M-5. `search_connection_id` Hardcodes Connection Name

**Location:** Item 8 — `provision_from_config()` parameter (L907)

The `search_connection_id` is constructed in `api/app/routers/config.py` L203–208 with a **hardcoded** connection name `"aisearch-connection"`:

```python
search_conn_id = (
    f"/subscriptions/{sub_id}/resourceGroups/{rg}"
    f"/providers/Microsoft.CognitiveServices"
    f"/accounts/{foundry}/projects/{project_name}"
    f"/connections/aisearch-connection"   # ← hardcoded
)
```

This limits scenarios to a single AI Search connection per Foundry project.

**Proposed Fix:** Make the connection name configurable via env var or scenario config:

```python
search_conn_name = os.getenv("AI_SEARCH_CONNECTION_NAME", "aisearch-connection")
# Or from scenario config: config.get("search_connection_name", "aisearch-connection")
```

---

### M-6. Dependency Graph: Phase 10 Over-Constrained

**Location:** Dependency Graph (L200–L210)

The plan states "Phase 10 requires Phases 5+6". But Phase 10 (Config-Driven Prompts) replaces `PROMPT_AGENT_MAP` with config-driven mappings. Checking the code:

- Phase 5 (Blob/Search extraction) — prompts don't use blob or search services
- Phase 6 (Ingest Protocol) — prompts don't use graph ingestion
- Phase 7 (Backend Registry) — prompts don't depend on graph backend selection

Phase 10 is actually **nearly independent**. Its only real dependency is that `router_ingest.py` exists (always true).

**Proposed Fix:** Remove Phase 5, 6, 7 from Phase 10's prerequisites. Phase 10 can run in parallel with Phases 5–7.

Updated dependency graph:
```
Phase 10 (Config Prompts) — independent (can start after Phase 4d)
```

---

### M-7. Dependency Graph: Phase 2 → Phase 4 Not a Hard Prerequisite

**Location:** Dependency Graph diagram (L194–L198)

The diagram shows Phase 2 feeding into Phase 4, but the text says "Phase 4 requires Phases 1+3" (omitting 2). The text is more accurate — Phase 4 migrates routers to `DocumentStore`, which wraps `cosmos_helpers`. The routers stop importing Cosmos constants directly; they call `get_document_store()` instead. Phase 2 (moving constants to `adapters.cosmos_config`) is a cleanup that can happen before or after Phase 4.

**Proposed Fix:** Update the diagram to show Phase 2 as parallel/optional rather than a hard prerequisite for Phase 4. Or update text to match diagram (add Phase 2 as a prerequisite for clarity even if not strictly required).

---

## LOW Issues

### L-1. Wrong Line Numbers in Plan

| Reference | Plan Claims | Actual |
|-----------|-------------|--------|
| `config.py` `rsplit` | L80 | L109 |
| `config.py` `gremlin_database=` | L85 | L113 |

Cosmetic only. No functional impact but may confuse implementers searching for specific lines.

---

### L-2. All Line Counts Off by +1

| File | Plan | Actual |
|------|------|--------|
| `router_interactions.py` | 146 | 147 |
| `router_scenarios.py` | 220 | 221 |
| `router_telemetry.py` | 144 | 145 |
| `router_prompts.py` | 288 | 289 |
| `agent_provisioner.py` | 281 | 282 |
| `backends/cosmosdb.py` | 303 | 304 |
| `main.py` | 237 | 238 |

Systematic +1 error — likely trailing newline counting issue. No functional impact.

---

### L-3. Item 3 Reference Table Lists Non-Existent `ctx.gremlin_database` in `backends/cosmosdb.py`

**Location:** Item 3 — "All References to Update" table

The table claims `backends/cosmosdb.py` and `router_ingest.py` reference `ctx.gremlin_database`. In reality, `backends/cosmosdb.py` uses `COSMOS_GREMLIN_DATABASE` (constant), not `ctx.gremlin_database` (context field). Only `config.py` itself references the field (definition + assignment). This means fewer files need updating than the plan suggests.

**Proposed Fix:** Update the reference table to show only the files that actually use `gremlin_database`:
- `config.py` L87 (field definition)
- `config.py` L113 (assignment)

---

### L-4. Plan's Item 2 Misses `COSMOS_GREMLIN_GRAPH` Import in `router_ingest.py`

**Location:** Item 2 — Files Modified table

The plan lists imports to move from `config` to `adapters.cosmos_config` for `router_ingest.py`: `COSMOS_GREMLIN_*` and `COSMOS_NOSQL_ENDPOINT`. But the actual file also imports `COSMOS_GREMLIN_GRAPH` from `config`, which isn't listed. Missing this causes `ImportError`.

**Proposed Fix:** Add `COSMOS_GREMLIN_GRAPH` to the `router_ingest.py` import list:
```python
from adapters.cosmos_config import (
    COSMOS_GREMLIN_ENDPOINT,
    COSMOS_GREMLIN_PRIMARY_KEY,
    COSMOS_GREMLIN_DATABASE,
    COSMOS_GREMLIN_GRAPH,      # ← missed by plan
    COSMOS_NOSQL_ENDPOINT,
)
```

---

### L-5. Double `list()` Wrapping in `CosmosDocumentStore.list()`

**Location:** Item 1 — `CosmosDocumentStore.list()` (L301–L310)

```python
return list(await asyncio.to_thread(lambda: list(self._container.query_items(**kwargs))))
```

The inner `list()` materializes the Cosmos paging iterator (correct). The outer `list()` copies an already-materialized list (unnecessary, wastes memory).

**Proposed Fix:**
```python
return await asyncio.to_thread(lambda: list(self._container.query_items(**kwargs)))
```

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| **CRITICAL** | 3 | C-1, C-2, C-3 |
| **HIGH** | 6 | H-1, H-2, H-3, H-4, H-5, H-6 |
| **MEDIUM** | 7 | M-1, M-2, M-3, M-4, M-5, M-6, M-7 |
| **LOW** | 5 | L-1, L-2, L-3, L-4, L-5 |

### Must Fix Before Implementation Begins

1. **C-1:** Add `parameters` to `DocumentStore.list()` Protocol
2. **C-2:** Use `.definitions` on `ConnectedAgentTool`
3. **C-3:** Use `.definitions` and `tool_resources` on all tool types
4. **H-1:** Remove `max_items` — use SQL `LIMIT` instead
5. **H-2:** Rewrite migration examples to match actual parameterized query patterns
6. **H-3:** List all 6 `.value` call sites (esp. 4 in `main.py`)
7. **H-4:** Define `fetch_scenario_config()` and its storage mechanism
8. **H-5:** Fix Phase 8/9 dependency — they're sequential, not parallel
9. **H-6:** Add Pydantic validation model for scenario YAML schema

### Corrected Dependency Graph

```
Phase 1 (DocumentStore) ──┐
Phase 3 (Generic Fields)──┼──▶ Phase 4 (Migrate NoSQL Routers) ──┐
Phase 2 (Cosmos Config)   │  (parallel, not prereq for 4)         │
                          │                                        │
Phase 5 (Blob/Search) ───────────────────────────────────────────┤
Phase 6 (Ingest Protocol)────────────────────────────────────────┤
Phase 7 (Backend Registry)───────────────────────────────────────┤
Phase 10 (Config Prompts)─── (independent, can start after 4d)──┤
                                                                  │
Phase 9 (OpenAPI Templates) ──▶ Phase 8 (Config Provisioner) ────┤
                                                                  │
Phase 11 (Frontend Generic) ─────────────────────────────────────┤
Phase 12 (Viz Backend) ──────────────────────────────────────────┤
                                                                  │
                                                Phase 13 (Migrate telco-noc)
```

Key changes from original:
- Phase 2 not a hard prereq for Phase 4 (was implied by diagram)
- Phase 9 → Phase 8 (was claimed parallel)
- Phase 10 independent (was claimed to need 5+6+7)
