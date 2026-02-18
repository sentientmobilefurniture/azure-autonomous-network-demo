# Scenario Decoupling — Implementation Plan

> **Goal:** Remove every hardcoded `telco-noc` reference from source code so that `./deploy.sh --scenario <name>` reads everything from `data/scenarios/<name>/scenario.yaml` and provisions automatically.

> **Invariant:** After this work, adding a new scenario requires **only** creating a new `data/scenarios/<name>/` folder with a valid `scenario.yaml` — zero code changes.

---

## 0. Design Principles

| Principle | Rule |
|---|---|
| **Single source of truth** | `scenario.yaml` is the only place scenario-specific values live. |
| **Runtime env var** | `DEFAULT_SCENARIO` is the one env var that names the active scenario. Every consumer reads it. |
| **Resolve-once, pass-down** | A new shared module (`scenario_loader.py`) parses `scenario.yaml` once and hands a typed dict to all consumers. |
| **No search-and-replace** | Don't just swap `telco-noc` for a variable — delete the hardcoded structures entirely and derive them from `scenario.yaml`. |
| **Index names from YAML** | `scenario.yaml` is authoritative for AI Search index names. Current code uses `runbooks-index` / `tickets-index` while `scenario.yaml` uses `telco-noc-runbooks-index` / `telco-noc-tickets-index`. After decoupling, the YAML values win everywhere. |

### 0.1 Index Name Reconciliation

**Current state (inconsistency):**
- `scenario.yaml` defines: `telco-noc-runbooks-index`, `telco-noc-tickets-index`
- Code / Bicep / env vars use: `runbooks-index`, `tickets-index`

**Decision:** `scenario.yaml` is the single source of truth. After decoupling:
- The Bicep env vars `RUNBOOKS_INDEX_NAME` / `TICKETS_INDEX_NAME` will be set from `scenario.yaml` values via `azd env set` (or `deploy.sh` pre-processing).
- All runtime code reads index names from `scenario.yaml` or from the env vars that `deploy.sh` populates from it.
- `provision_search_index.py` creates indexes using the names from `scenario.yaml`.

---

## 1. Add `--scenario` to `deploy.sh`

**File:** `deploy.sh`

### 1.1 New CLI flag

Add a `--scenario` argument alongside the existing flags (after line 65):

```bash
SCENARIO_NAME=""

# Add to the while loop:
    --scenario)          SCENARIO_NAME="$2"; shift 2 ;;
```

### 1.2 Default discovery

If `--scenario` is not provided, auto-detect. Add after argument parsing (around line 88):

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

```bash
SCENARIO_DIR="$PROJECT_ROOT/data/scenarios/$SCENARIO_NAME"
SCENARIO_YAML="$SCENARIO_DIR/scenario.yaml"

if [[ ! -f "$SCENARIO_YAML" ]]; then
  fail "Scenario manifest not found: $SCENARIO_YAML"
  exit 1
fi

export DEFAULT_SCENARIO="$SCENARIO_NAME"
info "Scenario: $SCENARIO_NAME (from $SCENARIO_YAML)"

# Extract index names from scenario.yaml for Bicep / env vars
# Uses python3 to parse YAML — python3 is guaranteed available
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
```

### 1.4 Propagate to azd env

```bash
azd env set DEFAULT_SCENARIO "$SCENARIO_NAME"
azd env set RUNBOOKS_INDEX_NAME "$RUNBOOKS_INDEX_NAME"
azd env set TICKETS_INDEX_NAME "$TICKETS_INDEX_NAME"
```

This ensures all three values flow into `postprovision.sh` hooks, Container App env vars (via Bicep parameters), and all downstream scripts.

### 1.5 Pass scenario to topology generation (line ~501)

Replace the hardcoded invocation:

```bash
# Before (line 501)
(cd "$PROJECT_ROOT" && uv run python "$TOPO_SCRIPT")

# After
(cd "$PROJECT_ROOT" && uv run python "$TOPO_SCRIPT" --scenario "$SCENARIO_NAME")
```

Same for the python3 fallback on line 504:

```bash
# Before (line 504)
(cd "$PROJECT_ROOT" && python3 "$TOPO_SCRIPT")

# After
(cd "$PROJECT_ROOT" && python3 "$TOPO_SCRIPT" --scenario "$SCENARIO_NAME")
```

`generate_topology_json.py` already accepts `--scenario` — this just wires it up.

### 1.6 Provisioning script invocations (lines 768–806)

Each provisioning script reads `DEFAULT_SCENARIO` from env. Since we exported it in 1.3, no changes to the invocation lines — but every script must honour it (steps 3.x below).

---

## 2. Create `scenario_loader.py` — the shared resolver

**New file:** `scripts/scenario_loader.py`

This is the single module that parses `scenario.yaml` and returns a structured dict. Every script imports from here instead of hardcoding paths or names.

```python
"""
scenario_loader.py — Parse scenario.yaml and return a resolved config dict.

Usage:
    from scenario_loader import load_scenario

    sc = load_scenario()             # uses DEFAULT_SCENARIO env var
    sc = load_scenario("telco-noc")  # explicit name
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

## 3. Update provisioning scripts (`scripts/`)

Each script replaces its hardcoded path / name with a call to `load_scenario()`.

### 3.1 `scripts/provision_search_index.py`

**Current hardcoded references (actual line numbers):**

| Line | Current Code | Change To |
|---|---|---|
| 8 | `For the telco-noc demo, creates:` | `For the active scenario, creates:` |
| 9 | `- runbooks-index:   blob container 'runbooks'` | Remove — will be dynamic |
| 10 | `- tickets-index:    blob container 'tickets'` | Remove — will be dynamic |
| 70 | `KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "scenarios" / "telco-noc" / "data" / "knowledge"` | `sc = load_scenario()` then `KNOWLEDGE_DIR = sc["paths"]["runbooks"].parent` |
| 83 | `"runbooks-index": {` (INDEX_CONFIGS dict key) | Build dynamically from `sc["runbooks_index_name"]` |
| 90 | `"tickets-index": {` (INDEX_CONFIGS dict key) | Build dynamically from `sc["tickets_index_name"]` |

**Implementation:** Replace the top-level `KNOWLEDGE_DIR` and `INDEX_CONFIGS` with:

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

**Current hardcoded references (actual line numbers):**

| Line | Current Code | Change To |
|---|---|---|
| 6 | `For the telco-noc demo, loads AlertStream` | Generic docstring |
| 10 | `Read CSVs from local data/scenarios/telco-noc/data/telemetry/` | Generic path |
| 47 | `DATA_DIR = PROJECT_ROOT / "data" / "scenarios" / "telco-noc" / "data" / "telemetry"` | `sc = load_scenario()` then `DATA_DIR = sc["paths"]["telemetry"]` |
| 57–72 | `CONTAINERS` dict hardcoded | Build from `sc["data_sources"]["telemetry"]["config"]["containers"]` |

**Implementation:** Replace lines 47–72:

```python
from scenario_loader import load_scenario

sc = load_scenario()
DATA_DIR = sc["paths"]["telemetry"]

# Build container definitions from scenario.yaml
_telemetry_cfg = sc["data_sources"]["telemetry"]["config"]
CONTAINERS = {}
for c in _telemetry_cfg.get("containers", []):
    CONTAINERS[c["name"]] = {
        "partition_key": c["partition_key"],
        "csv_file": c["csv_file"],
        "id_field": c.get("id_field"),
        "numeric_fields": set(c.get("numeric_fields", [])),
    }
```

### 3.3 `scripts/provision_agents.py`

**Current hardcoded references (actual line numbers):**

| Line | Current Code | Change To |
|---|---|---|
| 31 | `SCENARIO = os.environ.get("DEFAULT_SCENARIO", "telco-noc")` | `sc = load_scenario()` |
| 32 | `PROMPTS_DIR = PROJECT_ROOT / "data" / "scenarios" / SCENARIO / "data" / "prompts"` | `PROMPTS_DIR = sc["paths"]["prompts"]` |
| 90 | `"graph_name": os.environ.get("DEFAULT_SCENARIO", "telco-noc")` | `"graph_name": sc["graph_name"]` |

**Implementation:** Replace lines 31–32:

```python
from scenario_loader import load_scenario

sc = load_scenario()
PROMPTS_DIR = sc["paths"]["prompts"]
```

And line 90:

```python
        "graph_name": sc["graph_name"],
```

### 3.4 `scripts/generate_topology_json.py`

**Current hardcoded references (actual line numbers):**

| Line | Current Code | Change To |
|---|---|---|
| 10 | `python scripts/generate_topology_json.py [--scenario telco-noc]` | `[--scenario <name>]` |
| 166 | `default="telco-noc"` (argparse) | `default=os.environ.get("DEFAULT_SCENARIO", "")` |

This script already accepts `--scenario` and resolves `data/scenarios/<name>` — just change the default to read from env var and update the usage string. Add a validation check if neither is provided.

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

**Current hardcoded reference (actual line number):**

| Line | Current Code | Change To |
|---|---|---|
| 42 | `SCENARIO = os.environ.get("DEFAULT_SCENARIO", "telco-noc")` | Remove `"telco-noc"` fallback; fail-fast if unset |

**Implementation:**

```python
SCENARIO = os.environ.get("DEFAULT_SCENARIO", "")
if not SCENARIO:
    print("ERROR: DEFAULT_SCENARIO not set"); sys.exit(1)
```

Alternatively, import `load_scenario()` — but this script's import path would need `sys.path` adjustment since it's in `scripts/fabric/`. The simpler approach (remove fallback) is sufficient since `deploy.sh` always exports the env var.

### 3.6 `scripts/fabric/provision_eventhouse.py`

**Current hardcoded reference (actual line number):**

| Line | Current Code | Change To |
|---|---|---|
| 38 | `SCENARIO = os.environ.get("DEFAULT_SCENARIO", "telco-noc")` | Remove `"telco-noc"` fallback; fail-fast if unset |

Same pattern as 3.5.

### 3.7 `scripts/agent_provisioner.py`

**Current hardcoded reference (actual line number):**

| Line | Current Code | Change To |
|---|---|---|
| 150 | `# Prefix match: "/query/graph" matches "/query/graph/telco-noc-topology"` | `# Prefix match: "/query/graph" matches "/query/graph/<scenario>-topology"` |

This is a comment only — cosmetic change, no logic impact.

> **Note:** The original audit listed a `graph_name` docstring example at line 214. That reference existed in a previous version of `agent_provisioner.py` and has been refactored out. The current `provision_all()` no longer takes `graph_name` as a parameter.

---

## 4. Update `graph-query-api/` (runtime service)

The graph-query-api runs inside the container at `/app/graph-query-api/`. It needs scenario-specific values (graph name, index names, etc.) at runtime.

### 4.0 Pre-requisite: `scenario.yaml` must be in the container

**This is a critical dependency.** The unified Dockerfile does NOT currently copy `data/` into the container image (verified: no `COPY data/` line exists). Step 9 adds this. Steps 4 and 5 depend on it.

**Fallback strategy:** If `scenario.yaml` is missing (e.g., during development), all values fall back to env vars. This ensures backward compatibility during the transition.

### 4.1 `graph-query-api/config.py` — replace hardcoded config with YAML loader

**Current hardcoded references (actual line numbers):**

| Line | Current Code | Change To |
|---|---|---|
| 7 | `Provides ScenarioContext — a fixed hardcoded context for the telco-noc` | Generic docstring |
| 8 | `demo. No dynamic routing, no X-Graph header parsing, no config store.` | Generic docstring |
| 56 | `DEFAULT_GRAPH = "telco-noc-topology"` | Derive from YAML / env var |
| 72 | `# Scenario context — hardcoded for telco-noc` | Generic comment |
| 77 | `"""Fixed routing context for the telco-noc demo.` | Generic docstring |
| 106 | `"runbooks": {"index_name": "runbooks-index"},` | Derive from YAML |
| 107 | `"tickets": {"index_name": "tickets-index"},` | Derive from YAML |

**Implementation:** Add YAML loading between the existing AI_SEARCH_NAME and DEFAULT_GRAPH sections:

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

### 4.2 `graph-query-api/router_health.py`

**Current hardcoded references (actual line numbers):**

| Line | Current Code | Change To |
|---|---|---|
| 2 | `Health-check router — probes each data source for the telco-noc demo.` | `...for the active scenario.` |
| 4 | `GET /query/health/sources?scenario=telco-noc` | `GET /query/health/sources?scenario=<name>` |
| 96 | `Query(default="telco-noc", description="Scenario name")` | `Query(default=SCENARIO_NAME, ...)` — import from config |
| 104 | `graph_def.get("resource_name", "telco-noc-topology")` | `graph_def.get("resource_name", DEFAULT_GRAPH)` — import from config |

**Implementation:** Update import at top:

```python
from config import DATA_SOURCES, SCENARIO_NAME, DEFAULT_GRAPH
```

### 4.3 `graph-query-api/search_indexer.py`

**Current hardcoded references (actual line numbers):**

| Lines | Current Code | Change To |
|---|---|---|
| 82 | `index_name: Search index name (e.g. 'telco-noc-runbooks-index')` | `(e.g. '<scenario>-runbooks-index')` |
| 83 | `container_name: Blob container name (e.g. 'telco-noc-runbooks')` | `(e.g. 'runbooks')` |

Docstrings only — cosmetic.

### 4.4 `graph-query-api/services/blob_uploader.py`

**Current hardcoded reference (actual line number):**

| Line | Current Code | Change To |
|---|---|---|
| 31 | `container_name: Target blob container name (e.g. 'telco-noc-runbooks')` | `(e.g. 'runbooks')` |

Docstring only — cosmetic.

### 4.5 `graph-query-api/` dependency: add `pyyaml`

The `graph-query-api/pyproject.toml` needs `pyyaml` added as a dependency (if not already present), since `config.py` will now import `yaml`.

```bash
cd graph-query-api && uv add pyyaml
```

---

## 5. Update `api/app/routers/config.py` (runtime service)

**Current state:** Entire `SCENARIO_CONFIG` dict hardcoded (lines 27–86), `_load_current_config()` returns `"graph": "telco-noc"` (line 99), and `get_resource_graph()` passes `"telco-noc"` (line 264).

**Current hardcoded references (actual line numbers):**

| Line | Current Code | Type |
|---|---|---|
| 24 | `# Hardcoded scenario config for telco-noc` | Comment |
| 47 | `"index": "runbooks-index"` | Agent tool config |
| 54 | `"index": "tickets-index"` | Agent tool config |
| 68 | `"label": "Fabric GQL (telco-noc-topology)"` | Data source label |
| 79 | `"label": "AI Search (runbooks-index)"` | Data source label |
| 80 | `"index": "runbooks-index"` | Data source config |
| 84 | `"label": "AI Search (tickets-index)"` | Data source label |
| 85 | `"index": "tickets-index"` | Data source config |
| 99 | `"graph": "telco-noc"` | Config value |
| 100 | `"runbooks_index": os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index")` | Config value |
| 101 | `"tickets_index": os.getenv("TICKETS_INDEX_NAME", "tickets-index")` | Config value |
| 264 | `_build_resource_graph(SCENARIO_CONFIG, "telco-noc")` | Function call |

### 5.1 Add scenario YAML loader

Same pattern as graph-query-api. The api runs at `/app/api/` in the container, so `scenario.yaml` is at `/app/data/scenarios/<name>/scenario.yaml`.

```python
import yaml
from pathlib import Path

SCENARIO_NAME = os.getenv("DEFAULT_SCENARIO", "")

# Container path: /app/data/scenarios/<name>/scenario.yaml
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

_manifest = _load_scenario_yaml()
```

### 5.2 Build `SCENARIO_CONFIG` from YAML

Replace the entire hardcoded `SCENARIO_CONFIG` dict (lines 27–86) with a function that generates it from the parsed YAML:

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
                tool_entry["data_source"] = t.get("spec_template", "")  # graph/telemetry
            elif t["type"] == "azure_ai_search":
                # Resolve index key to actual index name from scenario.yaml
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
            "type": ds.get("graph", {}).get("connector", "fabric-gql"),
            "label": f"Fabric GQL ({graph_name})",
            "workspace": os.getenv("FABRIC_WORKSPACE_ID", ""),
            "graph_model": "(auto-discovered at runtime)",
        },
        "telemetry": {
            "type": ds.get("telemetry", {}).get("connector", "fabric-kql"),
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

### 5.3 Update `_load_current_config()`

Replace line 99:

```python
# Before
"graph": "telco-noc",

# After
"graph": SCENARIO_NAME,
```

Lines 100–101: the env var fallback approach already works because `deploy.sh` sets the env vars from `scenario.yaml`. The `os.getenv("RUNBOOKS_INDEX_NAME", ...)` pattern is fine — update the hardcoded fallback default:

```python
# Before
"runbooks_index": os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index"),
"tickets_index": os.getenv("TICKETS_INDEX_NAME", "tickets-index"),

# After — fallback derives from manifest if available
"runbooks_index": os.getenv("RUNBOOKS_INDEX_NAME", _manifest.get("data_sources", {}).get("search_indexes", {}).get("runbooks", {}).get("index_name", "runbooks-index") if _manifest else "runbooks-index"),
"tickets_index": os.getenv("TICKETS_INDEX_NAME", _manifest.get("data_sources", {}).get("search_indexes", {}).get("tickets", {}).get("index_name", "tickets-index") if _manifest else "tickets-index"),
```

### 5.4 Update `get_resource_graph` endpoint

Replace line 264:

```python
# Before
return _build_resource_graph(SCENARIO_CONFIG, "telco-noc")

# After
return _build_resource_graph(SCENARIO_CONFIG, SCENARIO_NAME)
```

### 5.5 Add `/scenario` metadata endpoint

Add a new endpoint for the frontend to fetch scenario info at runtime:

```python
@router.get("/scenario", summary="Get active scenario metadata")
async def get_scenario_metadata():
    """Return scenario name, display name, graph styles, example questions."""
    graph_styles = {"nodeColors": {}, "nodeSizes": {}, "nodeIcons": {}}
    for node_type, style in _manifest.get("graph_styles", {}).get("node_types", {}).items():
        graph_styles["nodeColors"][node_type] = style.get("color", "#888")
        graph_styles["nodeSizes"][node_type] = style.get("size", 16)
        graph_styles["nodeIcons"][node_type] = style.get("icon", "default")

    search = _manifest.get("data_sources", {}).get("search_indexes", {})

    return {
        "name": SCENARIO_NAME,
        "displayName": _manifest.get("display_name", SCENARIO_NAME),
        "description": _manifest.get("description", ""),
        "graph": _manifest.get("data_sources", {}).get("graph", {}).get("config", {}).get("graph", ""),
        "runbooksIndex": search.get("runbooks", {}).get("index_name", ""),
        "ticketsIndex": search.get("tickets", {}).get("index_name", ""),
        "graphStyles": graph_styles,
        "exampleQuestions": _manifest.get("example_questions", []),
        "useCases": _manifest.get("use_cases", []),
    }
```

### 5.6 `api/` dependency: add `pyyaml`

The `api/pyproject.toml` needs `pyyaml` added as a dependency (if not already present).

---

## 6. Update frontend (`frontend/src/config.ts`)

**Current state:** All values hardcoded in a single `SCENARIO` const export. 8 components import and use it.

**Current hardcoded references:**

| Line | Current Code |
|---|---|
| 5 | `name: "telco-noc"` |
| 7 | `graph: "telco-noc-topology"` |
| 8 | `runbooksIndex: "runbooks-index"` |
| 9 | `ticketsIndex: "tickets-index"` |
| 10–57 | Entire `SCENARIO` object (display name, description, graphStyles, exampleQuestions) |

**Consuming components (8 files):**

| File | Usage |
|---|---|
| `App.tsx` (lines 60, 74) | `SCENARIO.name` — interaction fetching, chat scenario param |
| `components/Header.tsx` (line 23) | `SCENARIO.displayName` |
| `components/InvestigationPanel.tsx` (line 31) | `SCENARIO.exampleQuestions` |
| `components/DataSourceBar.tsx` (line 13) | `SCENARIO.name` — health check query param |
| `components/GraphTopologyViewer.tsx` (line 18) | `SCENARIO.name` — storage prefix |
| `components/graph/GraphCanvas.tsx` (line 61) | `SCENARIO.graphStyles.nodeSizes` |
| `hooks/useNodeColor.ts` (line 5) | `SCENARIO.graphStyles.nodeColors` |

### 6.1 New frontend config approach

Replace the hardcoded `SCENARIO` with a fetch from `/api/config/scenario` (the endpoint added in step 5.5).

**`frontend/src/config.ts`** — new implementation:

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

### 6.2 Create React context provider

**New file: `frontend/src/ScenarioContext.tsx`**

```typescript
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

Wrap `<App />` in `<ScenarioProvider>` in `main.tsx` / `index.tsx`.

### 6.3 Update all 8 consuming components

Each component replaces `import { SCENARIO } from '../config'` with:

```typescript
import { useScenario } from '../ScenarioContext';

// Inside component function body:
const SCENARIO = useScenario();
```

**Files to update (mechanical change per file):**

1. `frontend/src/App.tsx` — `SCENARIO.name`
2. `frontend/src/components/Header.tsx` — `SCENARIO.displayName`
3. `frontend/src/components/InvestigationPanel.tsx` — `SCENARIO.exampleQuestions`
4. `frontend/src/components/DataSourceBar.tsx` — `SCENARIO.name`
5. `frontend/src/components/GraphTopologyViewer.tsx` — `SCENARIO.name`
6. `frontend/src/components/graph/GraphCanvas.tsx` — `SCENARIO.graphStyles.nodeSizes`
7. `frontend/src/hooks/useNodeColor.ts` — `SCENARIO.graphStyles.nodeColors` (this is a hook, not a component — it already runs inside a component, so `useScenario()` works here)

---

## 7. Update `hooks/postprovision.sh`

**Current hardcoded reference (actual line number):**

| Line | Current Code | Change To |
|---|---|---|
| 25 | `DATA_DIR="$PROJECT_ROOT/data/scenarios/telco-noc/data/knowledge"` | `DATA_DIR="$PROJECT_ROOT/data/scenarios/${DEFAULT_SCENARIO}/data/knowledge"` |

`DEFAULT_SCENARIO` is available because we set it in azd env (step 1.4) and azd exports all env values to hooks automatically.

---

## 8. Ensure `DEFAULT_SCENARIO` + index names flow into the Container App

The Container App needs `DEFAULT_SCENARIO` as an env var so runtime services know which scenario YAML to load.

### 8.1 Bicep: add `defaultScenario` parameter and parameterise index names

**File: `infra/main.bicep`**

Add parameters near the top:

```bicep
param defaultScenario string = ''
param runbooksIndexName string = 'runbooks-index'
param ticketsIndexName string = 'tickets-index'
```

Update the Container App `env` array (currently at line ~183):

```bicep
env: union([
  // ... existing entries ...
  { name: 'DEFAULT_SCENARIO', value: defaultScenario }
  { name: 'RUNBOOKS_INDEX_NAME', value: runbooksIndexName }   // was hardcoded 'runbooks-index'
  { name: 'TICKETS_INDEX_NAME', value: ticketsIndexName }     // was hardcoded 'tickets-index'
  // ... rest ...
], [])
```

**Lines to change (actual):**
- Line 195: `{ name: 'RUNBOOKS_INDEX_NAME', value: 'runbooks-index' }` → `{ name: 'RUNBOOKS_INDEX_NAME', value: runbooksIndexName }`
- Line 196: `{ name: 'TICKETS_INDEX_NAME', value: 'tickets-index' }` → `{ name: 'TICKETS_INDEX_NAME', value: ticketsIndexName }`
- Add new entry: `{ name: 'DEFAULT_SCENARIO', value: defaultScenario }`

### 8.2 Wire via `azd env set`

`deploy.sh` step 1.4 already runs:

```bash
azd env set DEFAULT_SCENARIO "$SCENARIO_NAME"
azd env set RUNBOOKS_INDEX_NAME "$RUNBOOKS_INDEX_NAME"
azd env set TICKETS_INDEX_NAME "$TICKETS_INDEX_NAME"
```

azd auto-maps env values to Bicep parameters using the naming convention. Verify by running `azd provision` — it should pick up the values from the env and pass them to the Bicep `param` declarations.

---

## 9. Ensure `scenario.yaml` + scenario data get into the Docker image

**CRITICAL: The unified Dockerfile does NOT currently copy `data/` into the container.**

The Dockerfile (lines 36–52) copies `graph-query-api/`, `api/`, and `scripts/agent_provisioner.py` but NOT `data/`. The runtime services will fail to find `scenario.yaml`.

### 9.1 Add COPY line to Dockerfile

After the existing `COPY scripts/agent_provisioner.py /app/scripts/` line (line 52), add:

```dockerfile
# ── Scenario data (YAML manifests for runtime config) ─────────────
COPY data/scenarios/ /app/data/scenarios/
```

**Image size note:** The `data/scenarios/` directory contains CSV files used only during provisioning (not at runtime). To keep the image lean, add a `.dockerignore` entry:

```
# Exclude bulk CSV data — only YAML manifests needed at runtime
data/scenarios/*/data/entities/*.csv
data/scenarios/*/data/telemetry/*.csv
data/scenarios/*/data/knowledge/runbooks/*.md
data/scenarios/*/data/knowledge/tickets/*.txt
```

Or alternatively, use a more targeted COPY with a multi-line RUN to cherry-pick only YAML files. The simpler approach (copy everything, ignore CSVs) is recommended.

### 9.2 Verify `.dockerignore`

Check if a `.dockerignore` exists. If it does, ensure it does NOT exclude `data/scenarios/`. If it excludes `data/`, add exceptions:

```
!data/scenarios/
```

---

## 10. Scenario data directory: `generate_all.sh`

**File:** `data/scenarios/telco-noc/scripts/generate_all.sh`

| Lines | Current | Change |
|---|---|---|
| 2 | `# Generate all data for the telco-noc scenario` | `# Generate all data for this scenario` |
| 5 | `echo "=== Generating telco-noc scenario data ==="` | `echo "=== Generating scenario data ==="` |

Comments/echo only — cosmetic. This script generates data *for its own scenario directory* and is run manually.

---

## 11. `data/scenarios/telco-noc/graph_schema.yaml`

**Current reference (actual line number):**

| Line | Current Code | Change |
|---|---|---|
| 13 | `# The backwards-compat symlink data/network → scenarios/telco-noc/data/entities` | Update comment to be generic or remove if symlink is deprecated |

Comment only — cosmetic.

---

## 12. `README.md`

**Current references (actual line numbers):**

| Line | Current Code |
|---|---|
| 15 | `\| **telco-noc** \| Telecommunications \| Fibre cut ... \|` |
| 154 | `- \`data/scenarios/telco-noc.tar.gz\`` |
| 235 | `│       ├── telco-noc/          # Telco — fibre cut` |

These are documentation. Update to show `telco-noc` as one example scenario among potentially many, and document the `--scenario` flag in the usage section.

---

## 13. `.azure/` environment files

**Current references:**
- `.azure/cosmosv8/.env` line 5: `DEFAULT_SCENARIO="telco-noc"`
- `.azure/cosmosv8/.env` line 8: `LOADED_SCENARIOS="telco-noc"`

These are azd env values, not source code. They're created by `azd env new` and `azd env set`. After decoupling, `deploy.sh` sets `DEFAULT_SCENARIO` automatically (step 1.4). No manual code change needed — just awareness.

---

## 14. Execution Order

Implement in dependency order to keep the project deployable at every step:

| Phase | Steps | Description | Risk |
|---|---|---|---|
| **A** | 2 | Create `scenario_loader.py` | None — new file, nothing imports it yet |
| **B** | 3.1–3.7 | Update scripts to use `scenario_loader` | Low — scripts only run manually |
| **C** | 7 | Update `postprovision.sh` | Low — one-line change |
| **D** | 9 | Add `COPY data/scenarios/` to Dockerfile | Low — needed before E/F deploy |
| **E** | 4.1–4.5 | Update `graph-query-api/config.py` + dependents + pyproject.toml | Medium — runtime service |
| **F** | 5.1–5.6 | Update `api/app/routers/config.py` + pyproject.toml | Medium — runtime service |
| **G** | 1.1–1.6 | Update `deploy.sh` | Low — orchestration only |
| **H** | 8 | Bicep: pass `DEFAULT_SCENARIO` + index names to Container App | Low — infra parameter |
| **I** | 6.1–6.3 | Frontend: fetch scenario from API via context provider | Medium — requires API endpoint from F |
| **J** | 10–12 | Cosmetic: comments, docstrings, README | Trivial |

### Suggested implementation order: A → B → C → D → G → H → E → F → I → J

This keeps scripts and deployment working at every step. The Dockerfile fix (D) must land before runtime services (E, F) are deployed. The frontend (I) is last because it requires the API endpoint from step F.

---

## 15. Testing Checklist

After implementation, verify with the existing `telco-noc` scenario:

- [ ] `./deploy.sh --scenario telco-noc --provision-all --yes --skip-local` — full deployment works
- [ ] `./deploy.sh --provision-all --yes --skip-local` — auto-detects `telco-noc` (only scenario present)
- [ ] `DEFAULT_SCENARIO` is set in azd env after deploy
- [ ] `RUNBOOKS_INDEX_NAME` in azd env matches `scenario.yaml` value (`telco-noc-runbooks-index`)
- [ ] `TICKETS_INDEX_NAME` in azd env matches `scenario.yaml` value (`telco-noc-tickets-index`)
- [ ] Agents are provisioned with correct prompt paths from `scenario.yaml`
- [ ] AI Search indexes are created with names from `scenario.yaml` (e.g., `telco-noc-runbooks-index`)
- [ ] Fabric resources (lakehouse, eventhouse, ontology) provision correctly
- [ ] Frontend loads scenario name, graph styles, and example questions from `/api/config/scenario`
- [ ] `/api/config/current` returns correct graph name (not hardcoded `telco-noc`)
- [ ] `/api/config/resources` returns correct resource graph with scenario-derived labels
- [ ] `/query/health/sources` probes correct data sources with correct index names
- [ ] Container App has `DEFAULT_SCENARIO` env var set
- [ ] `docker build` succeeds and container has `data/scenarios/` directory available
- [ ] Container runs successfully — `scenario.yaml` is found at `/app/data/scenarios/telco-noc/scenario.yaml`

### Zero-reference verification

```bash
grep -rn "telco-noc" \
  --include="*.py" --include="*.ts" --include="*.tsx" \
  --include="*.sh" --include="*.bicep" \
  api/ graph-query-api/ frontend/src/ scripts/ hooks/ infra/
```

Should return **zero** results. Only `data/scenarios/telco-noc/` and `documentation/` should contain `telco-noc`.

---

## 16. Files Changed — Summary

| File | Change Type | Complexity |
|---|---|---|
| `scripts/scenario_loader.py` | **New** | Low |
| `frontend/src/ScenarioContext.tsx` | **New** | Low |
| `deploy.sh` | Edit — add `--scenario` flag, YAML value extraction, topology `--scenario` pass-through | Low |
| `hooks/postprovision.sh` | Edit — parameterise path (1 line) | Trivial |
| `scripts/provision_search_index.py` | Edit — use `load_scenario()` for paths, index names, dict keys | Medium |
| `scripts/provision_cosmos.py` | Edit — use `load_scenario()` for data dir + container defs from YAML | Medium |
| `scripts/provision_agents.py` | Edit — use `load_scenario()` for prompts dir + graph name | Low |
| `scripts/generate_topology_json.py` | Edit — default from env var + usage string | Trivial |
| `scripts/fabric/provision_lakehouse.py` | Edit — remove fallback default, fail-fast | Trivial |
| `scripts/fabric/provision_eventhouse.py` | Edit — remove fallback default, fail-fast | Trivial |
| `scripts/agent_provisioner.py` | Edit — update comment (line 150) | Trivial |
| `graph-query-api/config.py` | Edit — load from YAML instead of hardcoded, export `SCENARIO_NAME` | Medium |
| `graph-query-api/pyproject.toml` | Edit — add `pyyaml` dependency | Trivial |
| `graph-query-api/router_health.py` | Edit — import + use `SCENARIO_NAME`, `DEFAULT_GRAPH` from config | Low |
| `graph-query-api/search_indexer.py` | Edit — docstring only | Trivial |
| `graph-query-api/services/blob_uploader.py` | Edit — docstring only | Trivial |
| `api/app/routers/config.py` | Edit — replace hardcoded SCENARIO_CONFIG + add `/scenario` endpoint | Medium |
| `api/pyproject.toml` | Edit — add `pyyaml` dependency (if not present) | Trivial |
| `frontend/src/config.ts` | Edit — replace hardcoded SCENARIO with async fetch + interface | Medium |
| `frontend/src/App.tsx` | Edit — wrap with ScenarioProvider, use `useScenario()` | Low |
| `frontend/src/components/Header.tsx` | Edit — use `useScenario()` hook | Trivial |
| `frontend/src/components/InvestigationPanel.tsx` | Edit — use `useScenario()` hook | Trivial |
| `frontend/src/components/DataSourceBar.tsx` | Edit — use `useScenario()` hook | Trivial |
| `frontend/src/components/GraphTopologyViewer.tsx` | Edit — use `useScenario()` hook | Trivial |
| `frontend/src/components/graph/GraphCanvas.tsx` | Edit — use `useScenario()` hook | Trivial |
| `frontend/src/hooks/useNodeColor.ts` | Edit — use `useScenario()` hook | Trivial |
| `Dockerfile` | Edit — add `COPY data/scenarios/` line | Trivial |
| `infra/main.bicep` | Edit — add `defaultScenario` param, parameterise index names | Low |
| `data/scenarios/telco-noc/scripts/generate_all.sh` | Edit — comments only | Trivial |
| `data/scenarios/telco-noc/graph_schema.yaml` | Edit — comment only | Trivial |
| `README.md` | Edit — document `--scenario` flag, update examples | Low |

**Total: 2 new files, 29 edits (14 trivial, 7 low, 5 medium, 0 high)**
