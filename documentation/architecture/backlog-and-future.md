# Backlog & Future

## Planned Work & QOL Backlog

> **Source:** `documentation/QOLimprovements.md` + `documentation/minorQOL.md`

| # | Improvement | Status | Architecture Impact |
|---|-------------|--------|---------------------|
| 1 | **Pre-provision core Cosmos databases in Bicep** — create `networkgraph` (Gremlin), `scenarios`, `telemetry` databases at infra deploy time to avoid first-use ARM creation delays | ⬜ Not done | Would require adding `Microsoft.DocumentDB/databaseAccounts/gremlinDatabases` and `sqlDatabases` resources to `infra/modules/cosmos-gremlin.bicep`. Eliminates the ~20-30s first-access block documented in Known Issues |
| 2 | **Upload progress timer** — show elapsed time during scenario uploads | ⬜ Not done | Frontend-only change in `AddScenarioModal.tsx` |
| 3 | **Graph-query-api log stream in UI** — tabbed log pane in MetricsBar showing both API and Graph API logs | ✅ Done (V8) | Implemented via `TabbedLogStream` component. graph-query-api endpoint moved to `/query/logs`, frontend renders both streams in tabs with SSE continuity (both `LogStream` instances stay mounted) |
| 4 | **Graph pause/unpause on mouse hover** — stop force simulation when mouse is over the graph | ⬜ Not done | `GraphCanvas.tsx` change; reference implementation may exist in `custom_skills/react-force-graph-2d/` |
| 5 | **Right sidebar interaction history** — save/retrieve past investigations in Cosmos NoSQL (`interactions` database), show in sidebar with timestamps and scenario names, clickable to replay | ✅ Done (V10) | `router_interactions.py` (4 CRUD endpoints), `useInteractions` hook, `InteractionSidebar` component. Cosmos database `interactions` / container `interactions` (PK `/scenario`). Auto-saves on investigation completion; collapsible right sidebar in investigate tab |
| 6 | **Per-scenario topology databases** — move graph data from shared `networkgraph` database to scenario-specific databases (like telemetry/prompts pattern) for faster loading | ⬜ Not done | Would change the graph naming from `networkgraph/{scenario}-topology` to `{scenario}-graph/{scenario}-topology`. Affects `config.py`, `router_ingest.py`, `cosmosdb.py`, `agent_provisioner.py`. Breaking change for existing data |
| 7 | **Scenario-driven graph node colors** — `graph_styles.node_types` in `scenario.yaml` defines per-label colors and sizes; flow: scenario.yaml → graph upload → Cosmos → frontend context → graph rendering | ✅ Done (minorQOL) | New `useNodeColor` hook centralises 4-tier color fallback; `ScenarioContext` extended with `scenarioNodeColors`, `scenarioNodeSizes`, `setScenarioStyles`; `GraphCanvas`, `GraphToolbar`, `GraphTooltip` updated |
| 8 | **Scenario Info tab** — tab bar in App.tsx switches between "Investigate" and "Scenario Info" views; info panel shows description, use cases, clickable example questions | ✅ Done (minorQOL) | New `TabBar` + `ScenarioInfoPanel` components; `App.tsx` gains `activeTab` state + conditional rendering; clicking example question injects into alert input + switches to investigate tab |
| 9 | **Scenario metadata in data packs** — `use_cases`, `example_questions`, `graph_styles`, `domain` fields in `scenario.yaml`; extracted during graph upload and persisted with scenario save | ✅ Done (minorQOL) | `ScenarioSaveRequest` model extended; `router_ingest.py` extracts `scenario_metadata` from manifest; `AddScenarioModal` captures metadata from upload onComplete + forwards to save; `SavedScenario` type extended |
| 10 | **Config-driven N-agent provisioning** — `agents:` section in `scenario.yaml v2.0` defines agent topology; `provision_from_config()` replaces hardcoded 5-agent provisioning | ✅ Done (V10) | `config_store.py`, `config_validator.py`, `agent_provisioner.py` `provision_from_config()`. Legacy `provision_all()` retained as fallback |
| 11 | **DocumentStore Protocol** — registry-based store abstraction for Cosmos NoSQL operations | ✅ Done (V10) | `stores/__init__.py` Protocol + registry, `stores/cosmos_nosql.py`, `stores/mock_store.py` |
| 12 | **GraphBackend `ingest()` method** — graph backends support data ingestion via Protocol | ✅ Done (V10) | `backends/__init__.py` updated with `ingest()` in Protocol |
| 13 | **OpenAPI template specs** — `openapi/templates/{graph,telemetry}.yaml` with placeholder injection at provisioning | ✅ Done (V10) | Replaces static spec files for config-driven provisioning; legacy specs retained for backward compat |
| 14 | **Manifest normalization** — `_normalize_manifest()` auto-converts v1.0 to v2.0 `scenario.yaml` format | ✅ Done (V10) | `router_ingest.py`; handles `cosmos:` → `data_sources:`, `search_indexes:` list → dict |
| 15 | **Resource graph API** — `GET /api/config/resources` builds visual resource graph from scenario config | ✅ Done (V10) | `_build_resource_graph()` in `config.py`; returns typed `ResourceNode[]` + `ResourceEdge[]` |
| 16 | **Resource Visualizer tab** — `react-force-graph-2d` visualization of agent/tool/data-source topology | ✅ Done (V10) | `ResourceVisualizer.tsx`, `useResourceGraph.ts`, `resource/` subdir (4 files) |
| 17 | **EmptyState first-run guard** — Shows onboarding guide when no scenario active | ✅ Done (V10) | `EmptyState.tsx` in Investigate tab when `!activeScenario` |
| 18 | **Cosmos adapter isolation** — `adapters/cosmos_config.py` isolates Cosmos-specific env vars | ✅ Done (V10) | `CosmosGremlinConfig` + `CosmosNoSqlConfig` dataclasses |
| 19 | **Shared telemetry/prompts databases** — moved from per-scenario DBs to shared DBs with container prefixes | ✅ Done (V10) | `telemetry` (shared DB, `{scenario}-ContainerName` pattern), `prompts` (shared DB, `{scenario}` container) |
| 20 | **Deploy cleanup** — removed 7 vestigial env vars, `COSMOS_GREMLIN_GRAPH` from Bicep | ✅ Done (V10) | `azure_config.env.template`, `infra/main.bicep` cleaned up |

## Fabric Integration (Future)

> **Source:** `documentation/v9fabricintegration.md` (plan only — no implementation in main codebase)
> **Reference code:** `fabric_implementation_references/` (full stack reference)

Planned alternative to CosmosDB/Gremlin backend using Microsoft Fabric Ontology for graph data
and Fabric Eventhouses for telemetry. Key architectural impacts if implemented:

| Requirement | Description | Files Affected |
|-------------|-------------|----------------|
| Fabric workspace ID configuration | User provides workspace ID via Settings UI | `azure_config.env`, `ScenarioContext`, `SettingsModal` |
| Ontology listing | Read available ontologies from Fabric workspace | New backend module in `graph-query-api/backends/` |
| Backend toggle | Checkbox in Settings to switch between CosmosDB and Fabric | `SettingsModal.tsx` (new tab), `config.py` (backend factory) |
| Graph topology from Fabric | Query Fabric ontology for topology visualization | New `GraphBackend` implementation |
| Telemetry from Eventhouses | Query Fabric eventhouse for telemetry data | New telemetry backend |
| Agent data connections | Create Fabric workspace connections for OpenApiTool | `agent_provisioner.py` modifications |

**Current state:** Reference implementations exist in `fabric_implementation_references/` directory
(full API, frontend, graph-query-api, data, infra). Root `pyproject.toml` includes
`azure-storage-file-datalake>=12.18.0` (OneLake/ADLS Gen2 dependency — for Fabric integration).
Env vars `FABRIC_ONTOLOGY_ID` and `FABRIC_GRAPH_MODEL_ID` may exist in some `azure_config.env` files
but are NOT in the template and NOT consumed by any runtime code.

## SDK Versions

| Package | Version | Notes |
|---------|---------|-------|
| `azure-ai-agents` | `1.2.0b6` | OpenApiTool, ConnectedAgentTool, AzureAISearchTool |
| `azure-ai-projects` | `>=1.0.0,<2.0.0` | AIProjectClient |
| `azure-cosmos` | `>=4.9.0` | NoSQL queries + upserts |
| `azure-mgmt-cosmosdb` | `>=9.0.0` | ARM database/graph creation |
| `azure-storage-blob` | `>=12.19.0` | Blob uploads |
| `azure-search-documents` | `>=11.6.0` | Search indexer pipelines |
| `gremlinpython` | `>=3.7.0` | Cosmos Gremlin data-plane (key auth only) |
| `fastapi` | `>=0.115` | ASGI framework |
| `sse-starlette` | `>=1.6` | SSE streaming |
| `react` | 18.x | UI framework |
| `react-force-graph-2d` | ^1.29.1 | Graph visualization (canvas-based) |
| `@microsoft/fetch-event-source` | ^2.0.1 | POST-based SSE client |
| `framer-motion` | ^11.12.0 | Animation (tooltips) |
| `react-markdown` | ^10.1.0 | Diagnosis panel rendering |
| `react-resizable-panels` | ^4.6.2 | Layout panels |
| `tailwindcss` | ^3.4.15 | Styling |
| `clsx` | ^2.1.1 | Conditional CSS class composition |
| `@tailwindcss/typography` | ^0.5.19 | Prose markdown styling |
| `vite` | ^5.4.11 | Build tool |
| `typescript` | ^5.6.3 | Type checking |
| `python-multipart` | (in graph-query-api) | Required for file uploads |
| `pyyaml` | >=6.0 | scenario.yaml parsing |

## Related Documentation

| Document | Purpose |
|----------|---------|
| `documentation/SCENARIOHANDLING.md` | Scenario management feature spec — UX design, backend schema, implementation phases, deviations |
| `documentation/V8REFACTOR.md` | V8 codebase simplification & refactor — dead code removal, SSE/Cosmos helper extraction, credential centralisation, frontend componentisation, CORS unification (~1,826 lines removed) |
| `documentation/minorQOL.md` | Minor QOL improvements — scenario-driven graph colors, scenario info tab, metadata persistence, data generators. 4 phases, all complete |
| `documentation/V10generalflow.md` | V10 config-driven architecture spec — 14 phases (0-13): config-driven N-agent provisioning, DocumentStore Protocol, GraphBackend registry, OpenAPI templates, config store/validator, resource graph API, frontend genericization, telco-noc migration, deploy cleanup. All phases complete |
| `documentation/azure_deployment_lessons.md` | Detailed Azure deployment lessons (Private Endpoints, Policy, VNet, Bicep patterns) |
| `documentation/CUSTOM_SKILLS.md` | Custom skills documentation (neo4j, cosmosdb gremlin, etc.) |
| `documentation/v11customizableagentworkflows.md` | V11 customizable agent workflows (placeholder — currently empty) |
| `documentation/v8codesimplificationandrefactor.md` | V8 code simplification and refactor notes |
| `documentation/v9fabricintegration.md` | V9 Fabric ontology integration plan (alternative graph backend) |
| `documentation/QOLimprovements.md` | QOL improvement backlog (DB pre-provisioning, upload timer, graph pause, interaction history) |
| `fabric_implementation_references/` | Reference implementation for Fabric integration (full stack: API, frontend, graph-query-api, data, infra) |
| `documentation/deprecated/` | 16 historical docs (TASKS, BUGSTOFIX, SCENARIO, older versions) — kept for reference |
