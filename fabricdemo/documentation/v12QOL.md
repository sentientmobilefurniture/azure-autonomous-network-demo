# v12 QOL — Static Topology for Graph Visualizer

## Problem

The graph visualizer currently queries Fabric Graph (GQL) for topology data every time the frontend loads or refreshes. This means:

1. **Cold-start latency** — Fabric Graph can take 30–60s to warm up (status `02000` / `ColdStartTimeout`), causing the visualizer to spin or fail on first load.
2. **Unnecessary API cost** — The topology is static seed data (CSVs). It never changes at runtime. Querying a live database for data we already have locally is wasteful.
3. **Coupling** — The visualizer shouldn't depend on Fabric Graph being provisioned/healthy just to show the network topology. The graph is for the *agents* to query, not the UI.

## Goal

Serve the graph visualizer's topology from a **pre-built static JSON file** that ships inside the container image — no Fabric Graph queries needed for visualization.

The `POST /query/topology` endpoint and `FabricGQLBackend.get_topology()` method stay in place for agents or future use, but the frontend no longer calls them for its initial topology render.

---

## Current Flow

```
Browser (useTopology.ts)
  │  POST /query/topology
  ▼
graph-query-api (router_topology.py)
  │  get_backend_for_context() → FabricGQLBackend
  ▼
FabricGQLBackend.get_topology()
  │  7× GQL queries via Fabric REST API (with retry/cold-start handling)
  ▼
Response: { nodes[], edges[], meta }
```

**Key files in the current flow:**

| File | Role |
|------|------|
| `frontend/src/hooks/useTopology.ts` | `POST /query/topology` fetch hook |
| `graph-query-api/router_topology.py` | FastAPI endpoint, TTL cache, backend dispatch |
| `graph-query-api/backends/fabric.py` | `FabricGQLBackend.get_topology()` — 7 GQL queries merged |
| `graph-query-api/backends/mock.py` | `MockGraphBackend` — loads `fixtures/mock_topology.json` |
| `graph-query-api/backends/fixtures/mock_topology.json` | Pre-built nodes/edges (used when `GRAPH_BACKEND=mock`) |

## Target Flow

```
Browser (useTopology.ts)
  │  GET /query/topology.json   (or POST /query/topology — backed by static file)
  ▼
graph-query-api (or nginx direct)
  │  Read /app/graph-query-api/backends/fixtures/topology.json
  ▼
Response: { nodes[], edges[], meta }
```

No Fabric Graph queries. No cold-start. Sub-millisecond response.

---

## Implementation Plan

### Task 1: Build script to generate `topology.json` from CSVs + graph_schema.yaml

**What:** Create a Python script `scripts/generate_topology_json.py` that reads the scenario's `graph_schema.yaml` and all referenced CSVs, then outputs a `topology.json` file matching the exact `TopologyResponse` schema the frontend expects.

**Details:**
- Parse `data/scenarios/telco-noc/graph_schema.yaml` for vertex and edge definitions
- Read each CSV file referenced in the schema
- Build nodes array: `{ id: "{Label}:{IdValue}", label: "{Label}", properties: {...} }`
- Build edges array by resolving edge definitions (source/target lookups, filters, properties)
- Produce edge IDs matching current format: `"{edgeLabel}:{sourceId}→{targetId}"`
- Compute `meta`: `{ node_count, edge_count, query_time_ms: 0, labels: [...], cached: false }`
- Write output to `graph-query-api/backends/fixtures/topology.json`

**Validation:** Output should be structurally identical to what `FabricGQLBackend.get_topology()` returns. Diff against `mock_topology.json` for sanity (they should be similar but `mock_topology.json` may be a subset).

**Files to create:**
- `scripts/generate_topology_json.py`

**Files to update:**
- `data/generate_all.sh` — add a step to run the topology JSON generator after CSV generation

---

### Task 2: Add a `static` backend (or extend `mock` backend to be the default)

**What:** Instead of keeping `GRAPH_BACKEND=fabric-gql` for topology visualization, introduce a `static` backend mode (or reuse `mock`) that serves the pre-built `topology.json` for the `/query/topology` endpoint.

**Option A — New `StaticTopologyBackend` (recommended):**
- Create `graph-query-api/backends/static.py`
- Loads `fixtures/topology.json` at startup (same as `mock.py` pattern)
- `get_topology()` returns the full file content, with optional `vertex_labels` filtering
- `execute_query()` raises or delegates to `FabricGQLBackend` (agents still need live GQL)
- Register as `GRAPH_BACKEND=static`

**Option B — Frontend-only change:**
- Instead of hitting `/query/topology`, the frontend loads `/topology.json` as a static asset served by nginx
- Simpler but loses the ability to filter by `vertex_labels` server-side
- Would need to copy `topology.json` into `frontend/public/` at build time

**Option C — Hybrid (recommended approach):**
- Keep `POST /query/topology` endpoint but change `router_topology.py` to load from the static file *first*, falling back to the graph backend only if `TOPOLOGY_SOURCE=live` is explicitly set
- Add env var `TOPOLOGY_SOURCE` with values: `static` (default) | `live`
- When `static`: read `fixtures/topology.json`, apply `vertex_labels` filtering in-memory, return
- When `live`: existing behavior (call `FabricGQLBackend.get_topology()`)
- This approach changes the least frontend code — `useTopology.ts` keeps calling `POST /query/topology`

**Files to create/update:**
- `graph-query-api/router_topology.py` — add static file loading path (Option C)
- *or* `graph-query-api/backends/static.py` — new backend (Option A)

---

### Task 3: Bundle `topology.json` into the container image

**What:** Ensure the generated `topology.json` is available inside the container at `/app/graph-query-api/backends/fixtures/topology.json`.

**Details:**
- `deploy.sh` runs `scripts/generate_topology_json.py` **before** `azd up` (which triggers the Docker build)
- The Dockerfile already copies `graph-query-api/backends/` into the image:
  ```dockerfile
  COPY graph-query-api/backends/ ./backends/
  ```
  So placing `topology.json` in `graph-query-api/backends/fixtures/` is sufficient — it will be included automatically.
- The generated file is `.gitignore`d — it's always freshly generated from CSVs during deploy.

**Files to update:**
- `deploy.sh` — add topology JSON generation step (between Step 2 config and Step 3 infra deploy)
- `.gitignore` — add `graph-query-api/backends/fixtures/topology.json`

---

### Task 4: Update `router_topology.py` to serve static topology

**What:** Modify the `/query/topology` endpoint to read from the static JSON file instead of querying Fabric Graph.

**Implementation (Option C — hybrid):**

```python
# At module level
_STATIC_TOPO_PATH = Path(__file__).parent / "backends" / "fixtures" / "topology.json"
TOPOLOGY_SOURCE = os.getenv("TOPOLOGY_SOURCE", "static")  # "static" or "live"

def _load_static_topology() -> dict | None:
    """Load pre-built topology JSON. Returns None if file missing."""
    if _STATIC_TOPO_PATH.exists():
        return json.loads(_STATIC_TOPO_PATH.read_text())
    return None

_static_topo: dict | None = _load_static_topology()
```

In the `topology()` endpoint:
- If `TOPOLOGY_SOURCE == "static"` and `_static_topo` is not None:
  - Filter nodes by `vertex_labels` if provided
  - Remove edges whose source/target nodes were filtered out
  - Return `TopologyResponse` with `query_time_ms: 0`
- Else: fall through to existing backend.get_topology() logic

**Files to update:**
- `graph-query-api/router_topology.py`
- `graph-query-api/config.py` — add `TOPOLOGY_SOURCE` env var

---

### Task 5: Set `TOPOLOGY_SOURCE=static` as default in config

**What:** Update `azure_config.env` and `azure_config.env.template` to default to static topology.

**Files to update:**
- `azure_config.env`
- `azure_config.env.template`

---

### Task 6: Verify and clean up

**What:**
- Run the topology JSON generator and verify the output matches the Fabric GQL response shape
- Test the frontend locally with `TOPOLOGY_SOURCE=static` — confirm instant load, no cold-start wait
- Test with `TOPOLOGY_SOURCE=live` — confirm Fabric GQL fallback still works
- Test `vertex_labels` filtering works correctly with static data
- Deploy to Container App and verify end-to-end

**Bonus cleanup:**
- Remove the 30s TTL cache logic from `router_topology.py` when serving static data (unnecessary)
- Update `mock_topology.json` to match the generated `topology.json` (or remove it in favor of the single source of truth)

---

## Summary of Changes

| # | Task | Files | Effort |
|---|------|-------|--------|
| 1 | Generate `topology.json` from CSVs | `scripts/generate_topology_json.py`, `data/generate_all.sh` | Medium |
| 2 | Add static/hybrid backend option | `graph-query-api/backends/static.py` or `router_topology.py` | Small |
| 3 | Bundle into container image | `deploy.sh` or just commit the file | Trivial |
| 4 | Update topology endpoint | `router_topology.py`, `config.py` | Small |
| 5 | Default config | `azure_config.env`, `azure_config.env.template` | Trivial |
| 6 | Verify + cleanup | Testing | Small |

## Decision Points

1. **Option A vs C?** — Option C (hybrid with `TOPOLOGY_SOURCE` env var) is recommended. Minimal frontend change, easy fallback to live queries, same API contract.
2. **Generate during deploy** — `deploy.sh` runs the generator before `azd up` so the JSON is always fresh from CSVs. Not committed to git.
3. **Should agents still use live graph queries?** — Yes. `POST /query/graph` (used by agents via OpenApiTool) is unaffected. Only the *visualization* topology endpoint changes.
