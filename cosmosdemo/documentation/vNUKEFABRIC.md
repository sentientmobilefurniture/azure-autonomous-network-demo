# Fabric Removal Audit — vNUKEFABRIC

**Date:** 2026-02-17  
**Purpose:** Complete removal of all Microsoft Fabric references from the autonomous-network-demo project.  
This document traces every Fabric-related element that was present and subsequently removed.

---

## Summary

| Category | Files Affected | Action |
|---|---|---|
| Python files (deleted entirely) | 6 | Deleted |
| Python files (edited to remove Fabric) | 7 | Edited |
| TypeScript/TSX files (deleted entirely) | 2 | Deleted |
| TypeScript/TSX files (edited to remove Fabric) | 8 | Edited |
| Config files (edited) | 3 | Edited |
| Scenario data directory | 1 directory | Deleted |
| fabric_implementation_references/ | Entire directory | Left intact (reference archive) |
| Documentation with "fabric" in name | 4 files | Left intact (historical docs) |

---

## 1. Files Deleted Entirely

### Backend (Python)

| File | Purpose | Line Count |
|---|---|---|
| `api/app/routers/fabric_provision.py` | Fabric resource provisioning router — workspace, lakehouse, eventhouse, ontology provisioning via SSE. Routes under `/api/fabric/*`. ~1600 lines. | ~1600 |
| `graph-query-api/backends/fabric.py` | FabricGQLBackend — GQL queries against Microsoft Fabric Graph Model REST API. Included `acquire_fabric_token()`, query execution, health checks. | ~270 |
| `graph-query-api/backends/fabric_kql.py` | FabricKQLBackend — Telemetry queries against Fabric Eventhouse via KQL. | ~100 |
| `graph-query-api/adapters/fabric_config.py` | Fabric-specific env var reads: FABRIC_API_URL, FABRIC_SCOPE, FABRIC_WORKSPACE_ID, FABRIC_GRAPH_MODEL_ID, FABRIC_WORKSPACE_NAME, FABRIC_LAKEHOUSE_NAME, FABRIC_EVENTHOUSE_NAME, FABRIC_ONTOLOGY_NAME, FABRIC_CAPACITY_ID. Status flags: FABRIC_CONFIGURED, FABRIC_WORKSPACE_CONNECTED, FABRIC_QUERY_READY. | ~70 |
| `graph-query-api/router_fabric_discovery.py` | Fabric workspace resource discovery router under `/query/fabric/*` — list ontologies, graph models, eventhouses, lakehouses, KQL databases, health check. | ~230 |
| `graph-query-api/router_fabric_connections.py` | Fabric workspace connection CRUD router under `/query/fabric/connections` — save/list/delete/select workspace connections stored in Cosmos container `fabric-connections`. | ~160 |

### Frontend (TypeScript/TSX)

| File | Purpose |
|---|---|
| `frontend/src/components/FabricConnectionPanel.tsx` | Modal for Fabric workspace connection management — add/delete/select workspace connections. Called from Header. 263 lines. |
| `frontend/src/hooks/useFabricDiscovery.ts` | React hook for Fabric workspace resource discovery — health check, ontology/graphModel/eventhouse/lakehouse/kqlDatabase listing, provision pipeline SSE. 264 lines. |

### Scenario Data

| Path | Purpose |
|---|---|
| `data/scenarios/telco-noc-fabric/` (entire directory) | Fabric-backed scenario: scenario.yaml + tarballs (graph, prompts, runbooks, telemetry, tickets). scenario.yaml configured `connector: "fabric-gql"` for graph and `connector: "fabric-kql"` for telemetry. |

---

## 2. Files Edited — Backend

### `api/app/main.py`
- **L27:** Removed `from app.routers import fabric_provision`
- **L55:** Removed `app.include_router(fabric_provision.router)`

### `api/app/routers/upload_jobs.py`
- **L35:** Removed `API_SELF = "http://127.0.0.1:8000"  # local api service for Fabric endpoint`
- **L192-216:** Removed Fabric-specific routing logic: `if step_name == "graph" and backend == "fabric-gql"` and `elif step_name == "telemetry" and telemetry_backend == "fabric-kql"` branches that routed to `/api/fabric/provision/graph` and `/api/fabric/provision/telemetry`
- **L247-282:** Removed `fabric_resources` capture + persist logic (PUT to `/query/scenarios/{name}/fabric-resources`)

### `api/app/routers/logs.py`
- **L32-39:** Changed data-ops broadcaster comment from "Fabric provisioning + agent config" to just "agent config". Changed filter from `("app.fabric", "api.config")` to `("api.config",)`
- **L66:** Changed docstring from "Fabric, config" to "config"

### `graph-query-api/main.py`
- **L43-44:** Removed `from router_fabric_discovery import router as fabric_discovery_router` and `from router_fabric_connections import router as fabric_connections_router`
- **L178-179:** Removed `app.include_router(fabric_discovery_router)` and `app.include_router(fabric_connections_router)`

### `graph-query-api/backends/__init__.py`
- **L168-183:** Removed registration of `FabricGQLBackend` ("fabric-gql") and `FabricKQLBackend` ("fabric-kql")

### `graph-query-api/config.py`
- **L81:** Removed `telemetry_backend_type: "fabric-kql"` field from ScenarioContext
- **L82-84:** Removed `fabric_workspace_id`, `fabric_graph_model_id`, `fabric_eventhouse_id` fields from ScenarioContext
- **L90:** Removed `"fabric-gql": "fabric-gql"` from CONNECTOR_TO_BACKEND
- **L96:** Removed `"fabric-kql": "fabric-kql"` from TELEMETRY_CONNECTOR_MAP
- **L124-153:** Removed per-scenario `fabric_resources` extraction block
- **L170-172:** Removed fabric_workspace_id/fabric_graph_model_id/fabric_eventhouse_id from context population
- **L184:** Removed `"fabric-gql": ("FABRIC_WORKSPACE_ID", "FABRIC_GRAPH_MODEL_ID")` from BACKEND_REQUIRED_VARS

### `graph-query-api/router_scenarios.py`
- **L220:** Removed `f"{name}-fabric" if graph_connector == "fabric-gql"` suggestion in 409 conflict error
- **L263-291:** Removed entire `PUT /scenarios/{name}/fabric-resources` endpoint (`update_fabric_resources`)

### `graph-query-api/router_telemetry.py`
- **L87-88:** Removed `if ctx.telemetry_backend_type == "fabric-kql": return await _query_fabric_kql(req, ctx)` dispatch
- **L134-159:** Removed entire `_query_fabric_kql()` function

### `graph-query-api/router_graph.py`
- **L57-58:** Removed `workspace_id=ctx.fabric_workspace_id or None, graph_model_id=ctx.fabric_graph_model_id or None` kwargs from `backend.execute_query()`

### `graph-query-api/router_health.py`
- **L37:** Removed `"fabric-gql": "fabric-gql"` from backend_type mapping
- **L50-55:** Removed `if connector == "fabric-kql"` branch that created FabricKQLBackend for telemetry ping

### `graph-query-api/ingest/graph_ingest.py`
- **L~88-95:** Removed guard that rejected graph upload for Fabric scenarios (`if graph_connector == "fabric-gql": raise ValueError(...)`)

### `scripts/agent_provisioner.py`
- **L78-88:** Removed `"fabric"` entry from CONNECTOR_OPENAPI_VARS
- **L95:** Removed `"fabric"` entry from GRAPH_TOOL_DESCRIPTIONS

### `api/pyproject.toml`
- Removed `"azure-storage-file-datalake>=12.14.0",  # OneLake CSV upload (Fabric Lakehouse)"` dependency
- Removed `"azure-kusto-ingest>=4.3.0",             # Eventhouse KQL ingestion"` dependency

---

## 3. Files Edited — Frontend

### `frontend/src/components/Header.tsx`
- Removed `import { FabricConnectionPanel } from './FabricConnectionPanel'`
- Removed `const [fabricOpen, setFabricOpen] = useState(false)` state
- Removed `🔌 Fabric` button
- Removed `onFabricSetup={() => setFabricOpen(true)}` prop on ServiceHealthPopover
- Removed `<FabricConnectionPanel open={fabricOpen} onClose={() => setFabricOpen(false)} />` component mount

### `frontend/src/components/EmptyState.tsx`
- Removed `interface FabricHealth` type
- Removed `fabricHealth` and `onFabricSetup` props
- Removed State 1 (Fabric partially configured) block
- Removed "Connect Fabric" card from State 2 default view
- Removed "Fabric" / "Cosmos" label from scenario list items
- Removed "connect Microsoft Fabric" text from prompt

### `frontend/src/components/AddScenarioModal.tsx`
- Removed `selectedBackend` state and `'fabric-gql'` option
- Removed backend chooser grid (Cosmos vs Fabric buttons)
- Removed Fabric name conflict warning
- Removed `fabricGraph` slot relabeling logic
- Removed Fabric backend info card ("⬡ Fabric Graph Backend Selected")

### `frontend/src/components/ScenarioManagerModal.tsx`
- Removed `onFabricSetup` prop
- Removed `handleFabricReprovision` handler
- Removed "Re-provision Fabric resources" menu item for Fabric scenarios

### `frontend/src/hooks/useScenarioUpload.ts`
- Changed `selectedBackend` type to always `'cosmosdb-gremlin'`
- Removed `'fabric-kql'` telemetry backend derivation
- Removed Fabric workspace connection resolution block
- Removed `'fabric-gql'` graph_connector metadata
- Removed `"-fabric" suffix` conflict handling in 409 error

### `frontend/src/components/ServiceHealthPopover.tsx`
- Removed `onFabricSetup` prop
- Removed "→ Set up Fabric" button for Microsoft Fabric partial status

### `frontend/src/types/index.ts`
- Removed `FabricItem` interface
- Removed `// Fabric discovery types (V11)` section
- Left `graph_connector` field on SavedScenario but removed `"fabric-gql"` from its doc comment

### `frontend/src/components/DataSourceCard.tsx`
- Removed `'fabric-gql': 'Fabric Ontology'` from connector labels
- Removed `'fabric-kql': 'Fabric Eventhouse'` from connector labels

### `frontend/src/components/TerminalPanel.tsx`
- Changed comment from "Cosmos, blob, search, ingest, Fabric" to "Cosmos, blob, search, ingest"

### `frontend/src/components/ScenarioChip.tsx`
- Removed `if (connector === 'fabric-gql')` badge rendering (Fabric badge)

---

## 4. Config Files Edited

### `azure_config.env.template`
- Removed entire `# --- Microsoft Fabric (optional — for Fabric graph/telemetry backends) ---` section (lines 54-66, 13 env vars)

### `azure_config.env`
- No Fabric variables were present in the live config (all were commented in template)

---

## 5. Environment Variables Removed

| Variable | Default | Purpose |
|---|---|---|
| `FABRIC_API_URL` | `https://api.fabric.microsoft.com/v1` | Fabric REST API endpoint |
| `FABRIC_SCOPE` | `https://api.fabric.microsoft.com/.default` | OAuth scope for Fabric API tokens |
| `FABRIC_WORKSPACE_ID` | (empty) | Fabric workspace GUID |
| `FABRIC_WORKSPACE_NAME` | `AutonomousNetworkDemo` | Fabric workspace display name |
| `FABRIC_CAPACITY_ID` | (empty) | Fabric capacity GUID |
| `FABRIC_LAKEHOUSE_NAME` | `NetworkTopologyLH` | Default lakehouse name |
| `FABRIC_EVENTHOUSE_NAME` | `NetworkTelemetryEH` | Default eventhouse name |
| `FABRIC_ONTOLOGY_NAME` | `NetworkTopologyOntology` | Default ontology name |
| `FABRIC_GRAPH_MODEL_ID` | (empty) | Graph model GUID |
| `FABRIC_ONTOLOGY_ID` | (empty) | Ontology GUID |
| `FABRIC_KQL_DB_ID` | (empty) | KQL database GUID |
| `FABRIC_KQL_DB_NAME` | (empty) | KQL database name |
| `EVENTHOUSE_QUERY_URI` | (empty) | Eventhouse query endpoint |

---

## 6. API Endpoints Removed

| Method | Path | Router File |
|---|---|---|
| POST | `/api/fabric/provision` | `api/app/routers/fabric_provision.py` |
| POST | `/api/fabric/provision/lakehouse` | `api/app/routers/fabric_provision.py` |
| POST | `/api/fabric/provision/graph` | `api/app/routers/fabric_provision.py` |
| POST | `/api/fabric/provision/telemetry` | `api/app/routers/fabric_provision.py` |
| GET | `/api/fabric/status` | `api/app/routers/fabric_provision.py` |
| GET | `/query/fabric/health` | `graph-query-api/router_fabric_discovery.py` |
| GET | `/query/fabric/ontologies` | `graph-query-api/router_fabric_discovery.py` |
| GET | `/query/fabric/ontologies/{id}/models` | `graph-query-api/router_fabric_discovery.py` |
| GET | `/query/fabric/graph-models` | `graph-query-api/router_fabric_discovery.py` |
| GET | `/query/fabric/eventhouses` | `graph-query-api/router_fabric_discovery.py` |
| GET | `/query/fabric/kql-databases` | `graph-query-api/router_fabric_discovery.py` |
| GET | `/query/fabric/lakehouses` | `graph-query-api/router_fabric_discovery.py` |
| GET | `/query/fabric/connections` | `graph-query-api/router_fabric_connections.py` |
| POST | `/query/fabric/connections` | `graph-query-api/router_fabric_connections.py` |
| DELETE | `/query/fabric/connections/{id}` | `graph-query-api/router_fabric_connections.py` |
| POST | `/query/fabric/connections/{id}/select` | `graph-query-api/router_fabric_connections.py` |
| PUT | `/query/scenarios/{name}/fabric-resources` | `graph-query-api/router_scenarios.py` |

---

## 7. Backend Types / Connectors Removed

| Connector | Purpose | Backend Class |
|---|---|---|
| `fabric-gql` | Graph queries via GQL against Fabric Ontology | `FabricGQLBackend` |
| `fabric-kql` | Telemetry queries via KQL against Fabric Eventhouse | `FabricKQLBackend` |

---

## 8. Directories Left Intact (Reference Only)

| Directory | Reason |
|---|---|
| `fabric_implementation_references/` | Historical reference archive — not imported by any runtime code |
| `documentation/v11fabricv3.md` | Historical design doc |
| `documentation/v11fabricv3_old.md` | Historical design doc |
| `documentation/v11fabricv3_old2.md` | Historical design doc |
| `documentation/completed/v11fabricprepa.md` | Historical design doc |
| `documentation/completed/v11fabricprepb.md` | Historical design doc |

---

## 9. UI Elements Removed

| Component/Element | Location | Description |
|---|---|---|
| `FabricConnectionPanel` | `Header.tsx` | Full modal for managing Fabric workspace connections |
| `🔌 Fabric` button | `Header.tsx` | Header button to open Fabric connection panel |
| Fabric backend selector | `AddScenarioModal.tsx` | Radio-style button to choose Fabric vs CosmosDB backend |
| "⬡ Connect Fabric" card | `EmptyState.tsx` | Empty state onboarding card for Fabric connection |
| Fabric health state | `EmptyState.tsx` | Partially-connected state showing Fabric setup progress |
| "Fabric" badge | `ScenarioChip.tsx`, `ScenarioManagerModal.tsx` | Cyan badge on Fabric-backed scenarios |
| "Re-provision Fabric resources" | `ScenarioManagerModal.tsx` | Context menu item for Fabric scenario re-provisioning |
| "→ Set up Fabric" | `ServiceHealthPopover.tsx` | Action link in health popover for partial Fabric status |
| Fabric connector labels | `DataSourceCard.tsx` | "Fabric Ontology" and "Fabric Eventhouse" labels |
| `useFabricDiscovery` hook | `hooks/useFabricDiscovery.ts` | Entire hook for Fabric workspace resource discovery |
| `FabricItem` type | `types/index.ts` | TypeScript interface for Fabric discovery items |
