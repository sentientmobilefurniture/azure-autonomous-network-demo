# Scenario Management

> **Full specification:** `documentation/SCENARIOHANDLING.md` (1403 lines)
> **Status:** Phases 1-3 Complete, Phase 4 Partial

## Overview

Scenarios are first-class objects in the system. A **scenario** bundles together:
- A `scenario.yaml` manifest (v2.0 format) defining all resources and agents
- A Gremlin graph (`{name}-topology` — from `data_sources.graph.config.graph`)
- Telemetry containers (`{name}-*` prefix — from `data_sources.telemetry.config.container_prefix`)
- Runbook search indexes (`{name}-runbooks-index` — from `data_sources.search_indexes.runbooks.index_name`)
- Ticket search indexes (`{name}-tickets-index` — from `data_sources.search_indexes.tickets.index_name`)
- Prompts database/container (`prompts` / `{name}` — from scenario config)
- Agent definitions (N agents with roles, tools, instructions — from `agents:` section)
- A metadata record in Cosmos NoSQL (`scenarios/scenarios`)
- A config record in Cosmos NoSQL (`scenarios/configs`) — for `config_store.py`

Previously, users had to manually upload 5 tarballs, select each data source from
individual dropdowns, and provision agents — 6+ manual steps with no "scenario"
concept. Now users can create, save, switch, and delete complete scenarios from the UI.

### Scenario Name Override & Manifest Rewriting

Users can name a scenario anything when uploading (e.g., `telco-noc2`) even if the
`scenario.yaml` manifest says `name: telco-noc`. When a `scenario_name` override is
provided and differs from the manifest's `name`, `_rewrite_manifest_prefix()` in
`router_ingest.py` rewrites all resource names in the manifest to use the new name:

| Resource | Before (manifest says `telco-noc`) | After override to `telco-noc2` |
|----------|-----------------------------------|--------------------------------|
| Graph | `telco-noc-topology` | `telco-noc2-topology` |
| Telemetry containers | `telco-noc-AlertStream` | `telco-noc2-AlertStream` |
| Search indexes | `telco-noc-runbooks-index` | `telco-noc2-runbooks-index` |
| Saved config (config_store) | `name: telco-noc` | `name: telco-noc2` |

This ensures query-time prefix derivation (`graph_name.rsplit("-", 1)[0]`) in
`get_scenario_context()` produces a prefix that matches the telemetry containers.

## User Flow

1. **Create:** Click "+New Scenario" → name + 5 file slots → Save → sequential upload → metadata saved
2. **Switch:** Click scenario in Header chip dropdown → auto-binds all data sources → auto-provisions agents (config-driven N agents from `scenario.yaml agents:` section, or legacy 5-agent fallback)
3. **Delete:** ⋮ menu on scenario card → confirmation → deletes metadata only (data preserved)
4. **Needs-provisioning:** If agents are not provisioned for the active scenario, ProvisioningBanner shows amber bar with "Provision Now" button

## Architecture

```
┌─────────────┐    ┌──────────────────────────────────┐    ┌─────────────────────┐
│ ScenarioChip│───▶│ useScenarios.selectScenario()     │───▶│POST /api/config/apply│
│  (Header)   │    │ setActiveScenario() → auto-derive │    │ (SSE provisioning)  │
└─────────────┘    └──────────────────────────────────┘    └─────────────────────┘
       │                      │                                     │
       │            ┌─────────▼───────────┐               ┌────────▼──────────┐
       │            │ ScenarioContext      │               │ ProvisioningBanner│
       │            │ activeScenario       │               │ (28px feedback)   │
       │            │ activeGraph → X-Graph│               └───────────────────┘
       │            │ provisioningStatus   │
       │            │ localStorage persist │
       │            └─────────────────────┘
       │
┌──────▼──────────┐    ┌───────────────────────────────┐
│ AddScenarioModal│───▶│ POST /query/upload/* ×5        │
│ (5 file slots)  │    │ (with ?scenario_name= override)│
│ detectSlot()    │    │ ↓                              │
│ auto-detect     │    │ POST /query/scenarios/save     │
└─────────────────┘    └───────────────────────────────┘
```

## Key Files Added/Modified

**Scenario management files (from SCENARIOHANDLING.md):**

| File | Type | Purpose |
|------|------|---------|
| `graph-query-api/router_scenarios.py` | **New** (~220 lines) | Scenario CRUD endpoints + `_get_scenarios_container()` + metadata fields (use_cases, example_questions, graph_styles, domain) |
| `frontend/src/utils/sseStream.ts` | **New** (~142 lines) | Shared `consumeSSE()` + `uploadWithSSE()` utilities |
| `frontend/src/components/AddScenarioModal.tsx` | **New** (~682 lines) | Multi-slot file upload with auto-detect; captures `scenario_metadata` from graph upload onComplete |
| `frontend/src/components/ScenarioChip.tsx` | **New** (~153 lines) | Header scenario selector chip + flyout |
| `frontend/src/components/ProvisioningBanner.tsx` | **New** (~101 lines) | Non-blocking provisioning feedback banner; handles `needs-provisioning` state with amber ⚠ + "Provision Now" button |
| `frontend/src/components/TabBar.tsx` | **New** (~31 lines) | Investigate / Scenario Info / Resources tab bar |
| `frontend/src/components/ScenarioInfoPanel.tsx` | **New** (~95 lines) | Scenario detail: description, use cases, clickable example questions. Fetches `savedScenarios` on mount (V9.5 fix) |
| `frontend/src/hooks/useNodeColor.ts` | **New** (~42 lines) | Centralised node color resolution hook with 4-tier fallback + auto-palette |
| `frontend/src/context/ScenarioContext.tsx` | **Modified** (~174 lines) | Added `activeScenario`, `activePromptSet`, `provisioningStatus`, localStorage, `scenarioNodeColors`, `scenarioNodeSizes`, `setScenarioStyles` |
| `frontend/src/types/index.ts` | **Modified** (~77 lines) | Added `SavedScenario`, `SlotKey`, `SlotStatus`, `ScenarioUploadSlot` + graph_styles/use_cases/example_questions/domain fields |
| `frontend/src/hooks/useScenarios.ts` | **Modified** (~192 lines) | Added scenario CRUD + selection + `graph_styles` push to context on scenario select |
| `frontend/src/components/SettingsModal.tsx` | **Modified** (~673 lines) | 3-tab layout, scenario cards, read-only Data Sources when active |
| `frontend/src/components/Header.tsx` | **Modified** (~72 lines) | Added ScenarioChip + ProvisioningBanner + dynamic agent status |
| `frontend/src/App.tsx` | **Modified** (~209 lines) | Added TabBar + tab state + conditional rendering (investigate vs info tab) + InteractionSidebar |
| `frontend/src/components/graph/GraphCanvas.tsx` | **Modified** (~184 lines) | Uses `useNodeColor()` hook + scenario-driven sizes |
| `frontend/src/components/graph/GraphToolbar.tsx` | **Modified** (~137 lines) | Split label chips into dot (color picker) + text (filter toggle); `onSetColor` prop; renders `ColorWheelPopover` |
| `frontend/src/components/graph/GraphTooltip.tsx` | **Modified** (~80 lines) | Accepts `nodeColorOverride` prop; uses `useNodeColor()` |
| `frontend/src/components/GraphTopologyViewer.tsx` | **Modified** (~214 lines) | Passes `nodeColorOverride` + `onSetColor` to GraphToolbar and GraphTooltip |
| `frontend/src/components/graph/ColorWheelPopover.tsx` | **New** (~300 lines) | HSL color wheel + hex input + preset swatches; pure canvas, no deps |
| `frontend/src/components/AlertInput.tsx` | **Modified** (~68 lines) | Added `exampleQuestions` prop + suggestion chips (visible when textarea empty) |
| `frontend/src/components/InvestigationPanel.tsx` | **Modified** (~69 lines) | Self-sources example questions from `useScenarios()` + context; passes to AlertInput |
| `graph-query-api/main.py` | **Modified** | Mounted `router_scenarios` (6th router) + `router_interactions` (7th router) |
| `graph-query-api/router_ingest.py` | **Modified** (~871 lines) | Added `scenario_name` param to all 5 upload endpoints; extracts `scenario_metadata` from manifest |

**V10 interaction history files:**

| File | Type | Purpose |
|------|------|---------|
| `graph-query-api/router_interactions.py` | **New** (~146 lines) | Interaction history CRUD: 4 endpoints (list, save, get, delete). Cosmos database `interactions` / container `interactions` (PK `/scenario`) |
| `frontend/src/hooks/useInteractions.ts` | **New** (~63 lines) | Interaction CRUD hook: fetch/save/delete. Auto-fetches on mount and `activeScenario` change |
| `frontend/src/components/InteractionSidebar.tsx` | **New** (~154 lines) | Collapsible right sidebar showing saved investigations. Relative timestamps, scenario badges, query previews. Click to replay; hover-reveal delete |
| `frontend/src/App.tsx` | **Modified** (~209 lines) | Added `useInteractions()`, `InteractionSidebar` rendering, auto-save on investigation completion, `viewingInteraction` + `sidebarCollapsed` state |

**V10 config-driven files:**

| File | Type | Purpose |
|------|------|---------|
| `graph-query-api/config_store.py` | **New** (~62 lines) | Reads/writes scenario config to Cosmos `scenarios/configs` (PK `/scenario_name`) |
| `graph-query-api/config_validator.py` | **New** (~104 lines) | Validates `agents:` section — required fields, unique names, at most 1 orchestrator, valid tool types |
| `graph-query-api/adapters/cosmos_config.py` | **New** (~30 lines) | Isolates Cosmos-specific env vars; `CosmosGremlinConfig` + `CosmosNoSqlConfig` |
| `graph-query-api/stores/__init__.py` | **New** | `DocumentStore` Protocol + registry (`_STORE_REGISTRY`, `get_store()`) |
| `graph-query-api/stores/cosmos_nosql.py` | **New** | `CosmosDocumentStore` implementation; auto-registered as `"cosmosdb-nosql"` |
| `graph-query-api/stores/mock_store.py` | **New** | `MockDocumentStore` for testing; auto-registered as `"mock"` |
| `graph-query-api/openapi/templates/graph.yaml` | **New** | Template OpenAPI spec with `{base_url}`, `{graph_name}`, `{query_language_description}` placeholders |
| `graph-query-api/openapi/templates/telemetry.yaml` | **New** | Template OpenAPI spec with `{base_url}`, `{database}`, `{container_prefix}` placeholders |
| `frontend/src/components/EmptyState.tsx` | **New** | First-run onboarding: 4-step guide shown when no scenario is active |
| `frontend/src/components/ResourceVisualizer.tsx` | **New** | Resource/agent topology graph tab; uses `useResourceGraph()` |
| `frontend/src/hooks/useResourceGraph.ts` | **New** | Fetches `GET /api/config/resources`; returns typed `ResourceNode[]` + `ResourceEdge[]` |
| `frontend/src/components/resource/ResourceCanvas.tsx` | **New** | `react-force-graph-2d` with 4 custom shapes (circle, diamond, round-rect, hexagon) |
| `frontend/src/components/resource/ResourceToolbar.tsx` | **New** | Type-filter chips, search, pause/play, zoom-to-fit |
| `frontend/src/components/resource/ResourceTooltip.tsx` | **New** | Animated tooltip on node/edge hover |
| `frontend/src/components/resource/resourceConstants.ts` | **New** | Design tokens: colors, sizes, dash patterns, labels for 12 node types + 8 edge types |

**V8 refactor files (from V8REFACTOR.md):**

| File | Type | Purpose |
|------|------|---------|
| `graph-query-api/sse_helpers.py` | **New** (~86 lines) | SSE upload lifecycle helper (`SSEProgress`, `sse_upload_response()`) |
| `graph-query-api/cosmos_helpers.py` | **New** (~132 lines) | Centralised Cosmos client/container init + ARM caching |
| `frontend/src/components/ActionButton.tsx` | **New** (~52 lines) | Extracted reusable action button with status state machine |
| `frontend/src/components/TabbedLogStream.tsx` | **New** (~48 lines) | Tabbed log stream viewer |
| `scripts/scenario_loader.py` | **Deleted** | Dead code — no imports anywhere; removed |
| `graph-query-api/router_ingest.py` | **Modified** (~852 lines, was ~1384) | Dead code removed, SSE scaffolds → `sse_upload_response()`, shared `_upload_knowledge_files()` |
| `scripts/provision_agents.py` | **Modified** (~178 lines, was ~518) | Refactored to thin CLI wrapper around `AgentProvisioner` |
| `api/app/orchestrator.py` | **Modified** | mtime-based `agent_ids.json` caching |
| `graph-query-api/main.py` | **Modified** (~237 lines) | Removed shadowed `/api/logs`, CORS unified |
| `graph-query-api/router_prompts.py` | **Modified** (~288 lines) | Uses `cosmos_helpers`, removed `_DC` imports |
| `graph-query-api/router_interactions.py` | **Modified** (~146 lines) | Uses `cosmos_helpers`, removed `_DC` imports |
| `api/app/main.py` | **Modified** | CORS unified with graph-query-api |

## Cosmos DB "scenarios" Registry

| Property | Value |
|----------|-------|
| Account | Same NoSQL account (`{name}-nosql`) |
| Database | `scenarios` |
| Container | `scenarios` (metadata) |
| Partition Key | `/id` (scenario name) |
| Throughput | Default (minimal — low volume) |

**V10 addition — Config Store:**

| Property | Value |
|----------|-------|
| Account | Same NoSQL account |
| Database | `scenarios` |
| Container | `configs` |
| Partition Key | `/scenario_name` |
| Purpose | Stores parsed `scenario.yaml` as JSON for `config_store.py` reads |

The database + container are created on first use (same ARM two-phase pattern).
No new env vars required — uses existing `COSMOS_NOSQL_ENDPOINT`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`.

## Scenario Name Validation

Names must match: `^[a-z0-9](?!.*--)[a-z0-9-]{0,48}[a-z0-9]$`
- Lowercase alphanumeric + hyphens only
- No consecutive hyphens (Azure Blob container name restriction)
- 2-50 chars
- Must not end with reserved suffixes: `-topology`, `-telemetry`, `-prompts`, `-runbooks`, `-tickets`
- Enforced in both frontend (input validation) and backend (Pydantic `field_validator` + endpoint validation)

## Implementation Deviations (from SCENARIOHANDLING.md plan)

| # | Plan Said | Implementation | Rationale |
|---|-----------|---------------|----------|
| D-1 | `@microsoft/fetch-event-source` for SSE | Native `fetch()` + `consumeSSE()` | Plan's UX-11 specifies extracting existing native pattern; works correctly with POST + SSE |
| D-2 | `selectScenario` calls all 5 individual setters | Calls only `setActiveScenario(name)` | Auto-derives all 4 bindings; individual calls redundant |
| D-3 | Rename `scenario` param to `scenario_name` | Kept both; `scenario_name` takes priority | Backwards compatibility with existing scripts |
| D-4 | `ProvisioningStatus` in `types/index.ts` | Defined in `ScenarioContext.tsx` | Co-locating avoids circular dependency |
| D-5 | SSE `event:` type markers | Heuristic field-checking | Backend SSE uses `data:` lines only, not `event:` markers |

## Phase 4 Remaining Work

| Item | Status |
|------|--------|
| Override confirmation with detailed metadata (vertex count, prompt count) | 🔶 Basic only |
| Delete with framer-motion exit animation | 🔶 Inline confirmation; no animation |
| Backend `first_time: true` signal for upload performance warning | 🔶 Static warning only |
| Partial upload recovery (retry individual failed uploads) | ⬜ Not done |
| Focus trapping for accessibility | ⬜ Not done |
| Error toasts with auto-dismiss | ⬜ Errors display inline |
| Empty state illustrations | ⬜ Text only |
