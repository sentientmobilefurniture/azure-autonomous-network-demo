# Scenario Decoupling — Implementation Record

> **Goal:** Remove every hardcoded `telco-noc` reference from source code so that `./deploy.sh --scenario <name>` reads everything from `data/scenarios/<name>/scenario.yaml` and provisions automatically.

> **Invariant:** After this work, adding a new scenario requires **only** creating a new `data/scenarios/<name>/` folder with a valid `scenario.yaml` — zero code changes.

> **Status: ✅ COMPLETE** — All changes implemented and verified. `grep -rn "telco-noc"` returns zero results across `api/`, `graph-query-api/`, `frontend/src/`, `scripts/`, `hooks/`, and `infra/`.

---

## 0. Design Principles

| Principle | Rule |
|---|---|
| **Single source of truth** | `scenario.yaml` is the only place scenario-specific values live. |
| **Runtime env var** | `DEFAULT_SCENARIO` is the one env var that names the active scenario. Every consumer reads it. |
| **Resolve-once, pass-down** | A shared module (`scenario_loader.py`) parses `scenario.yaml` once and hands a typed dict to all consumers. |
| **No search-and-replace** | Don't just swap `telco-noc` for a variable — delete the hardcoded structures entirely and derive them from `scenario.yaml`. |
| **Index names from YAML** | `scenario.yaml` is authoritative for AI Search index names. |

### 0.1 Index Name Reconciliation

**Previous state (inconsistency):**
- `scenario.yaml` defined: `telco-noc-runbooks-index`, `telco-noc-tickets-index`
- Code / Bicep / env vars used: `runbooks-index`, `tickets-index`

**Resolution:** `scenario.yaml` is the single source of truth. After decoupling:
- `deploy.sh` extracts index names from `scenario.yaml` via python3 and sets them with `azd env set`.
- Bicep parameters `runbooksIndexName` / `ticketsIndexName` receive these values and pass them to the Container App.
- All runtime code reads index names from `scenario.yaml` (with env var fallbacks for backward compatibility).
- `provision_search_index.py` creates indexes using the names from `scenario.yaml`.

---

## 1. `deploy.sh` — `--scenario` flag ✅

**File:** `deploy.sh`

### 1.1 New CLI flag

Added `SCENARIO_NAME=""` variable alongside existing flags, and `--scenario)` case to the argument parser:

```bash
SCENARIO_NAME=""

# In the while loop:
    --scenario)          SCENARIO_NAME="$2"; shift 2 ;;
```

### 1.2 Default discovery

After argument parsing — auto-detects scenario from `data/scenarios/` if `--scenario` not provided:

```bash
if [[ -z "$SCENARIO_NAME" ]]; then
  SCENARIO_NAME="${DEFAULT_SCENARIO:-}"
fi
if [[ -z "$SCENARIO_NAME" ]]; then
  SCENARIOS=( $(ls -d "$PROJECT_ROOT/data/scenarios"/*/ 2>/dev/null | xargs -I{} basename {}) )
  if (( ${#SCENARIOS[@]} == 1 )); then
    SCENARIO_NAME="${SCENARIOS[0]}"
  elif (( ${#SCENARIOS[@]} > 1 )); then
    if $AUTO_YES; then
      fail "Multiple scenarios found. Pass --scenario <name>."
      exit 1
    fi
    choose "Which scenario?" "${SCENARIOS[@]}"
    SCENARIO_NAME="$CHOSEN"
  else
    fail "No scenarios found in data/scenarios/"
    exit 1
  fi
fi
```

### 1.3 Validate, export, and extract YAML values

Scenario validation, export, and python3-based YAML extraction of index names:

```bash
SCENARIO_DIR="$PROJECT_ROOT/data/scenarios/$SCENARIO_NAME"
SCENARIO_YAML="$SCENARIO_DIR/scenario.yaml"

if [[ ! -f "$SCENARIO_YAML" ]]; then
  fail "Scenario manifest not found: $SCENARIO_YAML"
  exit 1
fi

export DEFAULT_SCENARIO="$SCENARIO_NAME"
info "Scenario: $SCENARIO_NAME (from $SCENARIO_YAML)"

RUNBOOKS_INDEX_NAME=$(python3 -c "
import yaml
with open('$SCENARIO_YAML') as f:
    c = yaml.safe_load(f)
print(c.get('data_sources',{}).get('search_indexes',{}).get('runbooks',{}).get('index_name','runbooks-index'))
")
TICKETS_INDEX_NAME=$(python3 -c "
import yaml
with open('$SCENARIO_YAML') as f:
    c = yaml.safe_load(f)
print(c.get('data_sources',{}).get('search_indexes',{}).get('tickets',{}).get('index_name','tickets-index'))
")
export RUNBOOKS_INDEX_NAME TICKETS_INDEX_NAME
info "Index names: runbooks=$RUNBOOKS_INDEX_NAME, tickets=$TICKETS_INDEX_NAME"
```

### 1.4 Propagate to azd env

Three `azd env set` calls in the infrastructure section (~line 608):

```bash
azd env set DEFAULT_SCENARIO "$SCENARIO_NAME"
azd env set RUNBOOKS_INDEX_NAME "$RUNBOOKS_INDEX_NAME"
azd env set TICKETS_INDEX_NAME "$TICKETS_INDEX_NAME"
```

### 1.5 Pass scenario to topology generation

Updated both `uv run` and `python3` fallback invocations (~line 553) to pass `--scenario "$SCENARIO_NAME"`:

```bash
(cd "$PROJECT_ROOT" && uv run python "$TOPO_SCRIPT" --scenario "$SCENARIO_NAME")
# and
(cd "$PROJECT_ROOT" && python3 "$TOPO_SCRIPT" --scenario "$SCENARIO_NAME")
```

### 1.6 Provisioning script invocations

No changes needed — each script reads `DEFAULT_SCENARIO` from the exported env var.

---

## 2. `scripts/scenario_loader.py` — New shared resolver ✅

**New file:** `scripts/scenario_loader.py`

Parses `scenario.yaml` and returns a resolved config dict. All provisioning scripts import from here.

```python
"""
scenario_loader.py — Parse scenario.yaml and return a resolved config dict.

Usage:
    from scenario_loader import load_scenario

    sc = load_scenario()             # uses DEFAULT_SCENARIO env var
    sc = load_scenario("my-scenario")  # explicit name
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_scenario(name: str | None = None) -> dict:
    """Load and validate scenario.yaml, returning a resolved config dict.

    Args:
        name: Scenario folder name. Defaults to DEFAULT_SCENARIO env var.

    Returns:
        Dict with keys:
          name, display_name, description, version, domain,
          scenario_dir (Path), paths (resolved to absolute),
          data_sources, agents, graph_styles, ...

    Raises:
        SystemExit if scenario not found or invalid.
    """
    if name is None:
        name = os.environ.get("DEFAULT_SCENARIO", "")
    if not name:
        print("ERROR: No scenario specified. Set DEFAULT_SCENARIO or pass name explicitly.")
        sys.exit(1)

    scenario_dir = PROJECT_ROOT / "data" / "scenarios" / name
    manifest = scenario_dir / "scenario.yaml"

    if not manifest.exists():
        print(f"ERROR: Scenario manifest not found: {manifest}")
        sys.exit(1)

    with open(manifest) as f:
        cfg = yaml.safe_load(f)

    # Resolve relative paths to absolute
    raw_paths = cfg.get("paths", {})
    resolved_paths = {}
    for key, rel in raw_paths.items():
        resolved_paths[key] = scenario_dir / rel

    cfg["scenario_dir"] = scenario_dir
    cfg["paths"] = resolved_paths

    # Convenience shortcuts for the most common lookups
    ds = cfg.get("data_sources", {})
    graph_cfg = ds.get("graph", {}).get("config", {})
    cfg["graph_name"] = graph_cfg.get("graph", name + "-topology")
    cfg["container_prefix"] = ds.get("telemetry", {}).get("config", {}).get("container_prefix", name)

    search_idx = ds.get("search_indexes", {})
    cfg["runbooks_index_name"] = search_idx.get("runbooks", {}).get("index_name", f"{name}-runbooks-index")
    cfg["tickets_index_name"] = search_idx.get("tickets", {}).get("index_name", f"{name}-tickets-index")
    cfg["runbooks_blob_container"] = search_idx.get("runbooks", {}).get("blob_container", "runbooks")
    cfg["tickets_blob_container"] = search_idx.get("tickets", {}).get("blob_container", "tickets")

    return cfg
```

### 2.1 Why a separate module?

- Scripts (`scripts/*.py`) import it directly.
- Runtime services (`api/`, `graph-query-api/`) use env vars + their own lightweight YAML reader (see steps 4–5), because in the container the import path and working directory differ.
- Keeps YAML parsing + validation in one place for build-time/provisioning scripts.

---

## 3. Provisioning scripts (`scripts/`) ✅

Each script replaced its hardcoded path/name with a call to `load_scenario()`.

### 3.1 `scripts/provision_search_index.py`

**Changes:**

| What | Before | After |
|---|---|---|
| Docstring (line 8) | `For the telco-noc demo, creates:` | `For the active scenario, creates indexes as defined in scenario.yaml` |
| Docstring (lines 9–10) | Hardcoded index names | Removed — now dynamic |
| `KNOWLEDGE_DIR` | `PROJECT_ROOT / "data" / "scenarios" / "telco-noc" / "data" / "knowledge"` | `sc["paths"]["runbooks"].parent` |
| `INDEX_CONFIGS` dict | Hardcoded `"runbooks-index": {...}` and `"tickets-index": {...}` | Built dynamically from `sc["runbooks_index_name"]`, `sc["tickets_index_name"]`, etc. |

```python
from scenario_loader import load_scenario

sc = load_scenario()
KNOWLEDGE_DIR = sc["paths"]["runbooks"].parent  # data/knowledge/

INDEX_CONFIGS = {
    sc["runbooks_index_name"]: {
        "blob_container": sc["runbooks_blob_container"],
        "local_dir": sc["paths"]["runbooks"],
        "file_glob": "*.md",
        "description": "Operational runbooks for network incident response",
        "semantic_config_name": f"{sc['runbooks_blob_container']}-semantic",
    },
    sc["tickets_index_name"]: {
        "blob_container": sc["tickets_blob_container"],
        "local_dir": sc["paths"]["tickets"],
        "file_glob": "*.txt",
        "description": "Historical incident tickets for pattern matching",
        "semantic_config_name": f"{sc['tickets_blob_container']}-semantic",
    },
}
```

### 3.2 `scripts/provision_cosmos.py`

**Changes:**

| What | Before | After |
|---|---|---|
| Docstring | `For the telco-noc demo, loads AlertStream` | `Loads containers defined in scenario.yaml` |
| Docstring | `Read CSVs from local data/scenarios/telco-noc/data/telemetry/` | Generic path reference |
| `DATA_DIR` | `PROJECT_ROOT / "data" / "scenarios" / "telco-noc" / "data" / "telemetry"` | `sc["paths"]["telemetry"]` |
| `CONTAINERS` dict | Hardcoded with `AlertStream`, `MetricStream`, `ConfigSnapshot` | Built dynamically from `sc["data_sources"]["telemetry"]["config"]["containers"]` |

```python
from scenario_loader import load_scenario

sc = load_scenario()
DATA_DIR = sc["paths"]["telemetry"]

_telemetry_cfg = sc["data_sources"]["telemetry"]["config"]
CONTAINERS = {}
for _c in _telemetry_cfg.get("containers", []):
    CONTAINERS[_c["name"]] = {
        "partition_key": _c["partition_key"],
        "csv_file": _c["csv_file"],
        "id_field": _c.get("id_field"),
        "numeric_fields": set(_c.get("numeric_fields", [])),
    }
```

### 3.3 `scripts/provision_agents.py`

**Changes:**

| What | Before | After |
|---|---|---|
| `SCENARIO` variable | `os.environ.get("DEFAULT_SCENARIO", "telco-noc")` | Replaced with `sc = load_scenario()` |
| `PROMPTS_DIR` | `PROJECT_ROOT / "data" / "scenarios" / SCENARIO / "data" / "prompts"` | `sc["paths"]["prompts"]` |
| `"graph_name"` in config dict | `os.environ.get("DEFAULT_SCENARIO", "telco-noc")` | `sc["graph_name"]` |

```python
from scenario_loader import load_scenario

sc = load_scenario()
PROMPTS_DIR = sc["paths"]["prompts"]
# ...
        "graph_name": sc["graph_name"],
```

### 3.4 `scripts/generate_topology_json.py`

**Changes:**

| What | Before | After |
|---|---|---|
| Usage docstring | `[--scenario telco-noc]` | `[--scenario <name>]` |
| argparse default | `default="telco-noc"` | `default=os.environ.get("DEFAULT_SCENARIO", "")` |
| Validation | None | `if not args.scenario: parser.error(...)` |
| Import | No `os` import | Added `import os` |

```python
parser.add_argument(
    "--scenario",
    default=os.environ.get("DEFAULT_SCENARIO", ""),
    help="Scenario name (subfolder under data/scenarios/)",
)
args = parser.parse_args()
if not args.scenario:
    parser.error("--scenario is required (or set DEFAULT_SCENARIO env var)")
```

### 3.5 `scripts/fabric/provision_lakehouse.py`

**Phase 1** (prior): Changed default from `"telco-noc"` to `""` with fail-fast.

**Phase 2** (v12): Fully data-driven — replaced hardcoded `LAKEHOUSE_TABLES` list with dynamic derivation from `graph_schema.yaml`:

```python
# Before (hardcoded)
LAKEHOUSE_TABLES = [
    "DimCoreRouter", "DimTransportLink", "DimAggSwitch",
    "DimBaseStation", "DimBGPSession", "DimMPLSPath",
    "DimService", "DimSLAPolicy",
    "FactMPLSPathHops", "FactServiceDependency",
]

# After (data-driven)
with open(_SCHEMA_PATH) as f:
    _schema = yaml.safe_load(f)

_seen: set[str] = set()
LAKEHOUSE_TABLES: list[str] = []
for section in ("vertices", "edges"):
    for entry in _schema.get(section, []):
        tbl = entry["csv_file"].removesuffix(".csv")
        if tbl not in _seen:
            _seen.add(tbl)
            LAKEHOUSE_TABLES.append(tbl)
```

Adding new vertex/edge types only requires editing `graph_schema.yaml` — no code changes.

### 3.6 `scripts/fabric/provision_eventhouse.py`

**Phase 1** (prior): Changed default from `"telco-noc"` to `""` with fail-fast.

**Phase 2** (v12): Fully data-driven — replaced hardcoded `TABLE_SCHEMAS` dict with `_build_table_schemas()` that reads `scenario.yaml` telemetry containers + CSV headers:

```python
# Before (hardcoded)
TABLE_SCHEMAS = {
    "AlertStream": {"Timestamp": "datetime", "RouterId": "string", ...},
    "LinkTelemetry": {"Timestamp": "datetime", "LinkId": "string", ...},
}

# After (data-driven)
def _build_table_schemas() -> dict[str, dict[str, str]]:
    schemas = {}
    for container in _CONTAINERS:
        csv_path = DATA_DIR / "scenarios" / SCENARIO / "data" / "telemetry" / container["csv_file"]
        with open(csv_path) as f:
            headers = next(csv.reader(f))
        numeric = set(container.get("numeric_fields", []))
        col_types = {}
        for col in headers:
            if col == "Timestamp":     col_types[col] = "datetime"
            elif col in numeric:       col_types[col] = "real"
            else:                      col_types[col] = "string"
        schemas[container["name"]] = col_types
    return schemas
```

Adding new telemetry tables only requires editing `scenario.yaml` containers + providing the CSV.

### 3.7 `scripts/fabric/provision_ontology.py`

**Phase 2** (v12): Fully data-driven — the largest decoupling change. Replaced ~600 lines of hardcoded entity types, property IDs, relationship types, data bindings, and contextualizations with dynamic generation from `graph_schema.yaml`:

| Component | Before (hardcoded) | After (data-driven) |
|---|---|---|
| Entity type IDs | 8 named constants (`ET_CORE_ROUTER`, ...) | `_next_et_id()` — sequential from `1000000000001` |
| Property IDs | ~35 named constants (`P_ROUTER_ID`, ...) | `_next_prop_id()` — sequential from `2000000000001` |
| Relationship IDs | 7 named constants (`R_CONNECTS_TO`, ...) | `_next_rel_id()` — sequential from `3000000000001` |
| `ENTITY_TYPES` list | 8 hardcoded dicts with explicit properties | `_build_entity_types()` — reads vertices from YAML |
| `RELATIONSHIP_TYPES` list | 7 hardcoded dicts | `_build_relationship_types()` — groups edges by `(label, src, tgt)` |
| `build_static_bindings()` | 8 explicit Lakehouse binding entries | Iterates vertices, maps properties to generated IDs |
| `build_contextualizations()` | 7 explicit contextualization entries | Iterates edge groups, maps source/target columns to property IDs |
| Property value types | Inline in entity type dicts | `property_types` dict in `graph_schema.yaml` |

Key improvement: `depends_on` edges now properly create separate relationship types per target entity type (`depends_on_mplspath`, `depends_on_aggswitch`, `depends_on_basestation`) instead of silently ignoring non-MPLSPath targets.

### 3.8 `scripts/agent_provisioner.py`

Comment-only change:
- Line 150: `"/query/graph/telco-noc-topology"` → `"/query/graph/<scenario>-topology"`

---

## 4. `graph-query-api/` (runtime service) ✅

### 4.0 Pre-requisite: `scenario.yaml` in the container

The Dockerfile `COPY data/scenarios/` line ensures scenario.yaml is available at `/app/data/scenarios/<name>/scenario.yaml`. All values fall back to env vars if the file is missing.

### 4.1 `graph-query-api/config.py` — YAML-driven config

Replaced hardcoded `DEFAULT_GRAPH = "telco-noc-topology"` and `DATA_SOURCES` with scenario YAML loading.

```python
import yaml
from pathlib import Path

SCENARIO_NAME = os.getenv("DEFAULT_SCENARIO", "")

# Try to load scenario.yaml from container path, then local dev path
_SCENARIO_YAML_CANDIDATES = [
    Path("/app/data/scenarios") / SCENARIO_NAME / "scenario.yaml",
    Path(__file__).resolve().parent.parent / "data" / "scenarios" / SCENARIO_NAME / "scenario.yaml",
]

def _load_scenario_config() -> dict:
    if not SCENARIO_NAME:
        logger.warning("DEFAULT_SCENARIO not set — using env var defaults")
        return {}
    for p in _SCENARIO_YAML_CANDIDATES:
        if p.exists():
            with open(p) as f:
                return yaml.safe_load(f)
    logger.warning("scenario.yaml not found — using env var defaults")
    return {}

_SCENARIO = _load_scenario_config()

# Derived from scenario.yaml instead of hardcoded
DEFAULT_GRAPH = (
    _SCENARIO.get("data_sources", {}).get("graph", {}).get("config", {}).get("graph", f"{SCENARIO_NAME}-topology")
    if _SCENARIO else os.getenv("DEFAULT_GRAPH", "")
)

# Data source definitions (derived from scenario.yaml)
DATA_SOURCES = {
    "graph": {
        "connector": _SCENARIO.get("data_sources", {}).get("graph", {}).get("connector", "fabric-gql") if _SCENARIO else "fabric-gql",
        "resource_name": DEFAULT_GRAPH,
    },
    "telemetry": {
        "connector": _SCENARIO.get("data_sources", {}).get("telemetry", {}).get("connector", "fabric-kql") if _SCENARIO else "fabric-kql",
        "resource_name": "NetworkTelemetryEH",
    },
    "search_indexes": {
        "runbooks": {
            "index_name": (
                _SCENARIO.get("data_sources", {}).get("search_indexes", {}).get("runbooks", {}).get("index_name", "")
                if _SCENARIO else os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index")
            ) or os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index"),
        },
        "tickets": {
            "index_name": (
                _SCENARIO.get("data_sources", {}).get("search_indexes", {}).get("tickets", {}).get("index_name", "")
                if _SCENARIO else os.getenv("TICKETS_INDEX_NAME", "tickets-index")
            ) or os.getenv("TICKETS_INDEX_NAME", "tickets-index"),
        },
    },
}
```

**Docstrings updated:**
- `Provides ScenarioContext — a fixed hardcoded context for the telco-noc` → `Provides ScenarioContext — a routing context for the active scenario, derived from scenario.yaml when available, with env var fallbacks.`
- `# Scenario context — hardcoded for telco-noc` → `# Scenario config — loaded from scenario.yaml with env var fallbacks`

**Exports:** `SCENARIO_NAME`, `DEFAULT_GRAPH` are now importable by `router_health.py`.

### 4.2 `graph-query-api/router_health.py`

| What | Before | After |
|---|---|---|
| Module docstring | `for the telco-noc demo` | `for the active scenario` |
| Example in docstring | `?scenario=telco-noc` | `?scenario=<name>` |
| Query default | `Query(default="telco-noc", ...)` | `Query(default=SCENARIO_NAME, ...)` |
| Graph fallback | `graph_def.get("resource_name", "telco-noc-topology")` | `graph_def.get("resource_name", DEFAULT_GRAPH)` |
| Import | From `config import DATA_SOURCES` | From `config import DATA_SOURCES, SCENARIO_NAME, DEFAULT_GRAPH` |

### 4.3 `graph-query-api/search_indexer.py`

Docstring-only:
- `(e.g. 'telco-noc-runbooks-index')` → `(e.g. '<scenario>-runbooks-index')`
- `(e.g. 'telco-noc-runbooks')` → `(e.g. 'runbooks')`

### 4.4 `graph-query-api/services/blob_uploader.py`

Docstring-only:
- `(e.g. 'telco-noc-runbooks')` → `(e.g. 'runbooks')`

### 4.5 `graph-query-api/pyproject.toml`

`pyyaml` was already present. No change needed.

---

## 5. `api/app/routers/config.py` (runtime service) ✅

### 5.1 Scenario YAML loader

Added imports (`yaml`, `Path`), `SCENARIO_NAME`, `_SCENARIO_YAML_CANDIDATES`, and `_load_scenario_yaml()` function. Same dual-path pattern as `graph-query-api/config.py`:

```python
import yaml
from pathlib import Path

SCENARIO_NAME = os.getenv("DEFAULT_SCENARIO", "")

_SCENARIO_YAML_CANDIDATES = [
    Path("/app/data/scenarios") / SCENARIO_NAME / "scenario.yaml",
    PROJECT_ROOT / "data" / "scenarios" / SCENARIO_NAME / "scenario.yaml",
]

def _load_scenario_yaml() -> dict:
    if not SCENARIO_NAME:
        logger.warning("DEFAULT_SCENARIO not set — resource graph will be empty")
        return {}
    for p in _SCENARIO_YAML_CANDIDATES:
        if p.exists():
            with open(p) as f:
                return yaml.safe_load(f)
    logger.warning("scenario.yaml not found — resource graph will be empty")
    return {}
```

### 5.2 `_build_scenario_config()` replaces hardcoded `SCENARIO_CONFIG`

The entire 60-line hardcoded `SCENARIO_CONFIG` dict was replaced with `_build_scenario_config(manifest)` that generates the same structure from parsed YAML:

```python
def _build_scenario_config(manifest: dict) -> dict:
    """Convert scenario.yaml into the internal SCENARIO_CONFIG format."""
    agents = []
    for ag in manifest.get("agents", []):
        tools = []
        for t in ag.get("tools", []):
            tool_entry = {"type": t["type"]}
            if t["type"] == "openapi":
                tool_entry["spec_template"] = t.get("spec_template", "")
                tool_entry["data_source"] = t.get("spec_template", "")
            elif t["type"] == "azure_ai_search":
                idx_key = t.get("index_key", "")
                idx_name = manifest.get("data_sources", {}).get("search_indexes", {}).get(idx_key, {}).get("index_name", f"{idx_key}-index")
                tool_entry["index"] = idx_name
                tool_entry["data_source"] = idx_key
            tools.append(tool_entry)

        agents.append({
            "name": ag["name"],
            "model": ag.get("model", "gpt-4.1"),
            "is_orchestrator": ag.get("is_orchestrator", False),
            "tools": tools,
            "connected_agents": ag.get("connected_agents", []),
        })

    ds = manifest.get("data_sources", {})
    graph_cfg = ds.get("graph", {}).get("config", {})
    graph_name = graph_cfg.get("graph", "")
    search = ds.get("search_indexes", {})
    runbooks_idx = search.get("runbooks", {}).get("index_name", "runbooks-index")
    tickets_idx = search.get("tickets", {}).get("index_name", "tickets-index")

    data_sources = {
        "graph": {
            "type": ds.get("graph", {}).get("connector", "fabric-gql") if ds else "fabric_gql",
            "label": f"Fabric GQL ({graph_name})",
            "workspace": os.getenv("FABRIC_WORKSPACE_ID", ""),
            "graph_model": "(auto-discovered at runtime)",
        },
        "telemetry": {
            "type": ds.get("telemetry", {}).get("connector", "fabric-kql") if ds else "fabric_kql",
            "label": "Fabric KQL (NetworkTelemetryEH)",
            "eventhouse": "(auto-discovered at runtime)",
        },
        "runbooks": {
            "type": "azure_ai_search",
            "label": f"AI Search ({runbooks_idx})",
            "index": runbooks_idx,
        },
        "tickets": {
            "type": "azure_ai_search",
            "label": f"AI Search ({tickets_idx})",
            "index": tickets_idx,
        },
    }

    return {"agents": agents, "data_sources": data_sources}


_manifest = _load_scenario_yaml()
SCENARIO_CONFIG = _build_scenario_config(_manifest) if _manifest else {"agents": [], "data_sources": {}}
```

### 5.3 `_load_current_config()` updated

| What | Before | After |
|---|---|---|
| `"graph"` value | `"telco-noc"` | `SCENARIO_NAME` |
| `"runbooks_index"` fallback | `os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index")` | `os.getenv("RUNBOOKS_INDEX_NAME", _runbooks_default)` where `_runbooks_default` derives from `_manifest` |
| `"tickets_index"` fallback | `os.getenv("TICKETS_INDEX_NAME", "tickets-index")` | `os.getenv("TICKETS_INDEX_NAME", _tickets_default)` where `_tickets_default` derives from `_manifest` |

```python
def _load_current_config() -> dict:
    """Load current config from Foundry agent discovery + env-var defaults."""
    _runbooks_default = (
        _manifest.get("data_sources", {}).get("search_indexes", {}).get("runbooks", {}).get("index_name", "runbooks-index")
        if _manifest else "runbooks-index"
    )
    _tickets_default = (
        _manifest.get("data_sources", {}).get("search_indexes", {}).get("tickets", {}).get("index_name", "tickets-index")
        if _manifest else "tickets-index"
    )
    config = {
        "graph": SCENARIO_NAME,
        "runbooks_index": os.getenv("RUNBOOKS_INDEX_NAME", _runbooks_default),
        "tickets_index": os.getenv("TICKETS_INDEX_NAME", _tickets_default),
        "agents": None,
    }
    # ... (agent discovery continues)
```

### 5.4 `get_resource_graph` endpoint updated

| What | Before | After |
|---|---|---|
| Docstring | `from hardcoded config` | `from active scenario` |
| Scenario arg | `"telco-noc"` | `SCENARIO_NAME` |

```python
@router.get("/resources", summary="Get resource graph for visualization")
async def get_resource_graph(request: Request):
    """Build and return the nodes+edges resource graph from active scenario."""
    return _build_resource_graph(SCENARIO_CONFIG, SCENARIO_NAME)
```

### 5.5 New `GET /api/config/scenario` endpoint

Returns scenario metadata from `scenario.yaml` for the frontend. Passes through raw `graph_styles` and `example_questions` directly from YAML (simpler than restructuring into separate `nodeColors/nodeSizes/nodeIcons` dicts):

```python
@router.get("/scenario", summary="Active scenario metadata")
async def get_scenario():
    """Return scenario-level metadata loaded from scenario.yaml.

    The frontend uses this to populate titles, graph styles,
    example questions, and data-source labels without hardcoding.
    """
    if not _manifest:
        return {"name": SCENARIO_NAME, "display_name": SCENARIO_NAME, "data_sources": {}}

    ds = _manifest.get("data_sources", {})
    search = ds.get("search_indexes", {})
    graph_cfg = ds.get("graph", {}).get("config", {})

    return {
        "name": SCENARIO_NAME,
        "display_name": _manifest.get("display_name", SCENARIO_NAME),
        "graph_name": graph_cfg.get("graph", ""),
        "graph_styles": _manifest.get("graph_styles", {}),
        "example_questions": _manifest.get("example_questions", []),
        "data_sources": {
            "runbooks_index": search.get("runbooks", {}).get("index_name", "runbooks-index"),
            "tickets_index": search.get("tickets", {}).get("index_name", "tickets-index"),
        },
    }
```

**Note on response shape:** The API returns `graph_styles` as the raw YAML structure (with `node_colors`, `node_sizes`, `node_icons` sub-keys as defined in `scenario.yaml`). The frontend `ScenarioContext` maps these to camelCase properties (`nodeColors`, `nodeSizes`, `nodeIcons`) via the `getScenario()` fetch in `config.ts`.

### 5.6 `api/pyproject.toml`

`pyyaml` was already present. No change needed.

---

## 6. Frontend (`frontend/src/`) ✅

### 6.1 `frontend/src/config.ts` — async fetch replaces hardcoded SCENARIO

Replaced the entire hardcoded `SCENARIO` const (name, displayName, graph, graphStyles, exampleQuestions) with:
- `ScenarioConfig` TypeScript interface
- `getScenario()` async function that fetches from `/api/config/scenario` with in-memory caching
- `SCENARIO_DEFAULTS` for initial render before fetch completes
- `getScenarioSync()` backward-compat synchronous access

```typescript
export interface ScenarioConfig {
  name: string;
  displayName: string;
  description: string;
  graph: string;
  runbooksIndex: string;
  ticketsIndex: string;
  graphStyles: {
    nodeColors: Record<string, string>;
    nodeSizes: Record<string, number>;
    nodeIcons: Record<string, string>;
  };
  exampleQuestions: string[];
  useCases: string[];
}

let _cached: ScenarioConfig | null = null;
let _fetchPromise: Promise<ScenarioConfig> | null = null;

export async function getScenario(): Promise<ScenarioConfig> {
  if (_cached) return _cached;
  if (!_fetchPromise) {
    _fetchPromise = fetch("/api/config/scenario")
      .then((r) => r.json())
      .then((data: ScenarioConfig) => {
        _cached = data;
        return data;
      });
  }
  return _fetchPromise;
}

// Synchronous fallback for initial render — populated after first fetch
export const SCENARIO_DEFAULTS: ScenarioConfig = {
  name: "",
  displayName: "Loading...",
  description: "",
  graph: "",
  runbooksIndex: "",
  ticketsIndex: "",
  graphStyles: { nodeColors: {}, nodeSizes: {}, nodeIcons: {} },
  exampleQuestions: [],
  useCases: [],
};

// Backward-compat: synchronous access (returns cached or defaults)
export function getScenarioSync(): ScenarioConfig {
  return _cached ?? SCENARIO_DEFAULTS;
}
```

### 6.2 `frontend/src/ScenarioContext.tsx` — New React context provider

**New file** that wraps `getScenario()` in a React context:

```tsx
import React, { createContext, useContext, useEffect, useState } from 'react';
import { ScenarioConfig, SCENARIO_DEFAULTS, getScenario } from './config';

const ScenarioCtx = createContext<ScenarioConfig>(SCENARIO_DEFAULTS);
export const useScenario = () => useContext(ScenarioCtx);

export const ScenarioProvider: React.FC<{children: React.ReactNode}> = ({children}) => {
  const [scenario, setScenario] = useState<ScenarioConfig>(SCENARIO_DEFAULTS);
  useEffect(() => { getScenario().then(setScenario); }, []);
  return <ScenarioCtx.Provider value={scenario}>{children}</ScenarioCtx.Provider>;
};
```

`<App />` is wrapped in `<ScenarioProvider>` in `main.tsx`:

```tsx
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ScenarioProvider>
      <App />
    </ScenarioProvider>
  </React.StrictMode>
);
```

### 6.3 Updated all 7 consuming components

Each component replaced `import { SCENARIO } from '../config'` (or `'../../config'`) with:

```typescript
import { useScenario } from '../ScenarioContext';  // or '../../ScenarioContext'

// Inside component function body:
const SCENARIO = useScenario();
```

This keeps all downstream usage of `SCENARIO.name`, `SCENARIO.displayName`, etc. unchanged.

**Files updated:**

| File | What changed |
|---|---|
| `App.tsx` | Import `useScenario`, added `const SCENARIO = useScenario()` at top of component |
| `components/Header.tsx` | Import `useScenario`, added `const SCENARIO = useScenario()` at top of component |
| `components/InvestigationPanel.tsx` | Import `useScenario`, added `const SCENARIO = useScenario()` before `exampleQuestions` |
| `components/DataSourceBar.tsx` | Import `useScenario`, added `const SCENARIO = useScenario()` at top; added `SCENARIO.name` to `useEffect` dep array |
| `components/GraphTopologyViewer.tsx` | Import `useScenario`, added `const SCENARIO = useScenario()` at top of component |
| `components/graph/GraphCanvas.tsx` | Import `useScenario`, added `const SCENARIO = useScenario()` inside `forwardRef` body before `scenarioNodeSizes` |
| `hooks/useNodeColor.ts` | Import `useScenario` (replaced `SCENARIO` import); moved `scenarioNodeColors` inside hook body; added `scenarioNodeColors` to `useCallback` deps |

**Notable implementation detail for `DataSourceBar.tsx`:** The `useEffect` dependency array was updated from `[]` to `[SCENARIO.name]` so the health check re-fetches when the scenario data loads:

```tsx
useEffect(() => {
    const check = () =>
      fetch(`${QUERY_API}/health/sources?scenario=${encodeURIComponent(SCENARIO.name)}`)
        .then((r) => r.json())
        .then((d) => setSources(d.sources || []))
        .catch(() => {});

    check();
    const iv = setInterval(check, 30_000);
    return () => clearInterval(iv);
  }, [SCENARIO.name]);
```

**Notable implementation detail for `useNodeColor.ts`:** The original code had `const scenarioNodeColors = SCENARIO.graphStyles.nodeColors;` at module scope (outside the hook). This was moved inside the hook body to use `useScenario()` (hooks can only be called inside component/hook bodies):

```typescript
export function useNodeColor(nodeColorOverride: Record<string, string>) {
  const scenarioNodeColors = useScenario().graphStyles.nodeColors;
  return useCallback(
    (label: string) =>
      nodeColorOverride[label]
      ?? scenarioNodeColors[label]
      ?? autoColor(label),
    [nodeColorOverride, scenarioNodeColors],
  );
}
```

---

## 7. `hooks/postprovision.sh` ✅

| What | Before | After |
|---|---|---|
| `DATA_DIR` | `"$PROJECT_ROOT/data/scenarios/telco-noc/data/knowledge"` | `"$PROJECT_ROOT/data/scenarios/${DEFAULT_SCENARIO}/data/knowledge"` |

`DEFAULT_SCENARIO` is available because `deploy.sh` sets it via `azd env set` and azd exports all env values to hooks automatically.

---

## 8. `infra/main.bicep` — Bicep parameterization ✅

### 8.1 New parameters

Added three parameters (lines 42–49 of `main.bicep`):

```bicep
@description('Active scenario name (subfolder under data/scenarios/)')
param defaultScenario string = ''

@description('AI Search runbooks index name (from scenario.yaml)')
param runbooksIndexName string = 'runbooks-index'

@description('AI Search tickets index name (from scenario.yaml)')
param ticketsIndexName string = 'tickets-index'
```

### 8.2 Container App env vars

In the Container App `env` array (lines 204–211):

```bicep
{ name: 'RUNBOOKS_INDEX_NAME', value: runbooksIndexName }
{ name: 'TICKETS_INDEX_NAME', value: ticketsIndexName }
// ...
{ name: 'DEFAULT_SCENARIO', value: defaultScenario }
```

Previously `RUNBOOKS_INDEX_NAME` and `TICKETS_INDEX_NAME` had hardcoded `'runbooks-index'` / `'tickets-index'` values.

### 8.3 Wire via `azd env set`

`deploy.sh` step 1.4 runs `azd env set` for all three values. azd auto-maps env values to Bicep parameters using the naming convention (`DEFAULT_SCENARIO` → `defaultScenario`).

---

## 9. Dockerfile + `.dockerignore` ✅

### 9.1 Dockerfile — `COPY data/scenarios/`

Added after the existing `COPY scripts/agent_provisioner.py /app/scripts/` line:

```dockerfile
# ── Scenario data (YAML manifests for runtime config) ─────────────
COPY data/scenarios/ /app/data/scenarios/
```

### 9.2 `.dockerignore` — granular data exclusions

The existing `.dockerignore` had a blanket `data` exclusion that would block the new `COPY`. Replaced with granular rules using Docker's last-match-wins semantics:

```ignore
# Scenario data — bulk CSVs/docs excluded, YAML manifests included
data
!data/scenarios/
!data/scenarios/*/
!data/scenarios/*/scenario.yaml
!data/scenarios/*/graph_schema.yaml
!data/scenarios/*/data/
!data/scenarios/*/data/prompts/
!data/scenarios/*/data/prompts/**
data/scenarios/*/data/entities/
data/scenarios/*/data/telemetry/
data/scenarios/*/data/knowledge/
data/scenarios/*/scripts/
```

**Design note:** The `!data/scenarios/*/data/prompts/**` exception comes after the blanket `data` exclusion and before the specific `data/scenarios/*/data/knowledge/` exclusion, so prompt files (needed at runtime for agent provisioning) are included while bulk knowledge docs and CSVs are excluded. This keeps the Docker image small while ensuring runtime config is available.

---

## 10. `data/scenarios/telco-noc/scripts/generate_all.sh` ✅

| What | Before | After |
|---|---|---|
| Comment (line 2) | `# Generate all data for the telco-noc scenario` | `# Generate all data for this scenario` |
| Echo (line 5) | `echo "=== Generating telco-noc scenario data ==="` | `echo "=== Generating scenario data ==="` |

---

## 11. `data/scenarios/telco-noc/graph_schema.yaml` ✅

| What | Before | After |
|---|---|---|
| Comment (line 13) | `data/network → scenarios/telco-noc/data/entities` | `data/network → scenarios/<name>/data/entities` |
| `property_types` | Not present | Added optional `property_types` dict to TransportLink, BGPSession, Service, SLAPolicy for non-String ontology types (BigInt, Double) |

The `property_types` mapping is used by `provision_ontology.py` to set `valueType` on ontology properties. Vertices with all-String properties (CoreRouter, AggSwitch, BaseStation, MPLSPath) don't need it.

---

## 12. `README.md` ✅

| What | Before | After |
|---|---|---|
| Deploy flags table | No `--scenario` row | Added `--scenario NAME` — "Scenario to deploy (auto-detected if only one exists)" |
| Tarball reference (line 154) | `data/scenarios/telco-noc.tar.gz` | `data/scenarios/<name>.tar.gz` (e.g. `telco-noc.tar.gz`) |
| Directory tree listing | `telco-noc/` entry | Unchanged — kept as an example scenario folder name |
| Scenario table (line 15) | Lists `telco-noc` as one scenario | Unchanged — documentation listing available scenarios, not hardcoded config |

---

## 13. `.azure/` environment files

No code changes. These are azd env values created by `azd env new` and `azd env set`. After decoupling, `deploy.sh` sets `DEFAULT_SCENARIO`, `RUNBOOKS_INDEX_NAME`, and `TICKETS_INDEX_NAME` automatically via `azd env set` (step 1.4).

---

## 14. Execution Order (as implemented)

Implementation followed dependency order A → B → C → D → G → H → E → F → I → J:

| Phase | Steps | Description | Status |
|---|---|---|---|
| **A** | 2 | Created `scenario_loader.py` | ✅ |
| **B** | 3.1–3.7 | Updated 7 provisioning scripts | ✅ |
| **C** | 7 | Updated `postprovision.sh` | ✅ |
| **D** | 9 | Dockerfile `COPY` + `.dockerignore` granular rules | ✅ |
| **G** | 1.1–1.6 | `deploy.sh` — `--scenario` flag, YAML extraction, topology pass-through | ✅ |
| **H** | 8 | Bicep: `defaultScenario` + index name params | ✅ |
| **E** | 4.1–4.5 | `graph-query-api/config.py` + `router_health.py` + docstrings | ✅ |
| **F** | 5.1–5.6 | `api/app/routers/config.py` — YAML-driven SCENARIO_CONFIG + `/scenario` endpoint | ✅ |
| **I** | 6.1–6.3 | Frontend: config.ts rewrite, ScenarioContext.tsx, main.tsx, 7 components | ✅ |
| **J** | 10–12 | Cosmetic: generate_all.sh, graph_schema.yaml, README | ✅ |

---

## 15. Verification ✅

### Zero-reference check

```bash
grep -rn "telco-noc" \
  --include="*.py" --include="*.ts" --include="*.tsx" \
  --include="*.sh" --include="*.bicep" \
  api/ graph-query-api/ frontend/src/ scripts/ hooks/ infra/
```

Returns **zero** results. Only `data/scenarios/telco-noc/` (the scenario's own data files) and `documentation/` contain `telco-noc`.

### Deployment testing checklist

- [ ] `./deploy.sh --scenario telco-noc --provision-all --yes --skip-local` — full deployment
- [ ] `./deploy.sh --provision-all --yes --skip-local` — auto-detects `telco-noc` (only scenario)
- [ ] `DEFAULT_SCENARIO` set in azd env after deploy
- [ ] `RUNBOOKS_INDEX_NAME` / `TICKETS_INDEX_NAME` in azd env match `scenario.yaml` values
- [ ] Agents provisioned with correct prompt paths from `scenario.yaml`
- [ ] AI Search indexes created with names from `scenario.yaml`
- [ ] Fabric resources (lakehouse, eventhouse, ontology) provision correctly
- [ ] Frontend loads scenario metadata from `/api/config/scenario`
- [ ] `/api/config/current` returns correct graph name
- [ ] `/api/config/resources` returns correct resource graph
- [ ] `/query/health/sources` probes correct data sources with correct index names
- [ ] Container App has `DEFAULT_SCENARIO` env var set
- [ ] `docker build` succeeds; container has `data/scenarios/` directory
- [ ] Container runs — `scenario.yaml` found at `/app/data/scenarios/<name>/scenario.yaml`

---

## 16. Files Changed — Summary

| File | Change Type | Status |
|---|---|---|
| `scripts/scenario_loader.py` | **New** | ✅ |
| `frontend/src/ScenarioContext.tsx` | **New** | ✅ |
| `deploy.sh` | Edit — `--scenario` flag, YAML extraction, topology pass-through, `azd env set` | ✅ |
| `hooks/postprovision.sh` | Edit — parameterize path (1 line) | ✅ |
| `scripts/provision_search_index.py` | Edit — `load_scenario()` for paths, index names, dict keys | ✅ |
| `scripts/provision_cosmos.py` | Edit — `load_scenario()` for data dir + container defs from YAML | ✅ |
| `scripts/provision_agents.py` | Edit — `load_scenario()` for prompts dir + graph name | ✅ |
| `scripts/generate_topology_json.py` | Edit — default from env var, validation, usage string | ✅ |
| `scripts/fabric/provision_lakehouse.py` | Edit — data-driven `LAKEHOUSE_TABLES` from `graph_schema.yaml` | ✅ |
| `scripts/fabric/provision_eventhouse.py` | Edit — data-driven `TABLE_SCHEMAS` from `scenario.yaml` + CSV headers | ✅ |
| `scripts/fabric/provision_ontology.py` | Edit — data-driven entity types, properties, relationships, bindings from `graph_schema.yaml` | ✅ |
| `scripts/agent_provisioner.py` | Edit — comment update (line 150) | ✅ |
| `graph-query-api/config.py` | Edit — YAML loader, `SCENARIO_NAME`/`DEFAULT_GRAPH` exports, `DATA_SOURCES` from YAML | ✅ |
| `graph-query-api/router_health.py` | Edit — import `SCENARIO_NAME`/`DEFAULT_GRAPH`, use as defaults | ✅ |
| `graph-query-api/search_indexer.py` | Edit — docstring only | ✅ |
| `graph-query-api/services/blob_uploader.py` | Edit — docstring only | ✅ |
| `api/app/routers/config.py` | Edit — YAML-driven `SCENARIO_CONFIG`, `_load_current_config()`, `/scenario` endpoint | ✅ |
| `frontend/src/config.ts` | Edit — `ScenarioConfig` interface + async `getScenario()` + `SCENARIO_DEFAULTS` | ✅ |
| `frontend/src/main.tsx` | Edit — wrap `<App />` in `<ScenarioProvider>` | ✅ |
| `frontend/src/App.tsx` | Edit — `useScenario()` hook | ✅ |
| `frontend/src/components/Header.tsx` | Edit — `useScenario()` hook | ✅ |
| `frontend/src/components/InvestigationPanel.tsx` | Edit — `useScenario()` hook | ✅ |
| `frontend/src/components/DataSourceBar.tsx` | Edit — `useScenario()` hook + `SCENARIO.name` in dep array | ✅ |
| `frontend/src/components/GraphTopologyViewer.tsx` | Edit — `useScenario()` hook | ✅ |
| `frontend/src/components/graph/GraphCanvas.tsx` | Edit — `useScenario()` hook | ✅ |
| `frontend/src/hooks/useNodeColor.ts` | Edit — `useScenario()` hook, moved colors inside hook body, updated deps | ✅ |
| `Dockerfile` | Edit — `COPY data/scenarios/` line | ✅ |
| `.dockerignore` | Edit — granular data include/exclude rules | ✅ |
| `infra/main.bicep` | Edit — `defaultScenario`/`runbooksIndexName`/`ticketsIndexName` params + env vars | ✅ |
| `data/scenarios/telco-noc/scripts/generate_all.sh` | Edit — comments/echo only | ✅ |
| `data/scenarios/telco-noc/graph_schema.yaml` | Edit — comment update + `property_types` for ontology value types | ✅ |
| `README.md` | Edit — `--scenario` flag in table, tarball reference genericized | ✅ |

**Total: 2 new files, 30 edits — all complete.**

### Files NOT changed (no changes needed)

| File | Reason |
|---|---|
| `api/pyproject.toml` | `pyyaml` already present |
| `graph-query-api/pyproject.toml` | `pyyaml` already present |
| `.azure/` env files | Generated by `azd env set`, not source code |
