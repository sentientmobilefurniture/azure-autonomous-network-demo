# Known Issues & Gotchas

## Edge Topology f-String Bug (cosmosdb.py)
The filtered edge query in `get_topology()` has an f-string continuation bug:
the `.where(otherV().hasLabel({label_csv}))` line is NOT an f-string, so `{label_csv}`
is passed as a literal. Vertex-label-filtered topology requests will fail with a
Gremlin syntax error on the cosmosdb backend. Fix: add `f` prefix to the second
string segment.

## Prompts CRUD Blocks Event Loop
`get_prompt`, `create_prompt`, `update_prompt`, `delete_prompt` in `router_prompts.py`
make synchronous Cosmos SDK calls directly in `async def` handlers without
`asyncio.to_thread()`. Only `list_prompts` and `list_prompt_scenarios` are correct.

## deploy.sh Step 7 Missing graph-query-api
Automated local mode starts API (:8000) and frontend (:5173) but NOT graph-query-api
(:8100). All `/query/*` requests fail. Manual instructions are correct.

## Dead Code in Frontend
- `AlertChart` and `MetricCard` exist but are not imported by any component

## `useInvestigation` Stale Closure
`getQueryHeaders` is not in `submitAlert`'s `useCallback` dep array. If user switches
`activeGraph` without editing alert text, the old `X-Graph` header is sent.

## Agent Provisioning Dependencies
- `GRAPH_QUERY_API_URI` must point to the Container App's public URL (set in `azure_config.env` by postprovision.sh as `APP_URI`)
- Without it, GraphExplorer and Telemetry agents are created WITHOUT tools
- `agent_provisioner.py` is at `/app/scripts/` in the container; `config.py` adds both `PROJECT_ROOT/scripts` and `PROJECT_ROOT/../scripts` to sys.path
- **V10**: Config-driven provisioning uses `openapi/templates/{graph,telemetry}.yaml` with placeholder injection; legacy provisioning falls back to `openapi/{cosmosdb|mock}.yaml`

## Graph Listing Can Be Slow
`GET /query/scenarios` tries ARM listing first (~5-10s for `CosmosDBManagementClient` discovery), falls back to Gremlin key-auth count query on default graph.

## TopologyRequest.query Is Unsupported
`TopologyRequest.query` parameter is reserved but **raises ValueError** if used. Only `vertex_labels` filtering is supported.

## Prompt Listing Without Scenario Is Slow
`GET /query/prompts` without `?scenario=X` iterates ALL `{scenario}-prompts` databases via ARM discovery — can be slow with many scenarios.

## Prompt Content Is Immutable Per Version
`PUT /query/prompts/{id}` updates metadata only (description, tags, is_active). To change content, create a new version via `POST /query/prompts` (auto-increments version, deactivates previous).

## Frontend Unused Components
`AlertChart` and `MetricCard` exist in `src/components/` but are not imported by any parent component.

## Container Apps Environment VNet Immutability
Cannot add VNet integration to an existing CAE. Must delete + recreate: `azd down && azd up`.

## Cosmos DB Public Access Policy Override
Azure Policy may silently flip `publicNetworkAccess` to `Disabled` post-deployment. Private endpoints provide a parallel path that works regardless.

## Scenario Selection Auto-Provisioning Timing
When user selects a scenario from the ScenarioChip dropdown, topology loads instantly
(via `X-Graph` header change → `useTopology` auto-refetch) but agent provisioning
takes ~30s. During this window, submitting an alert uses old agent bindings (agents
still pointing to the previous scenario's OpenAPI specs and search indexes).
The "Submit Alert" button should be disabled during provisioning.

## Scenario Registry ARM Creation on First Access
`_get_scenarios_container(ensure_created=True)` triggers ARM database + container
creation on the first `GET /query/scenarios/saved` call. This blocks for ~20-30s.
Subsequent calls use the cached container client. Consider separating the creation
to the `POST /query/scenarios/save` path and adding `ensure_created=False` for reads
(same pattern as prompts — see Critical Pattern #13).

## Telemetry Database Derivation Coupling
~~The telemetry database name is derived in two different places with two different
algorithms that must produce the same result~~ — **Resolved in V10.** Telemetry now
uses a shared `telemetry` database with per-scenario container prefixes (from
`data_sources.telemetry.config.container_prefix` in `scenario.yaml`). The old
convention-based derivation (`{scenario}-telemetry`) is superseded by config-driven
values when a v2.0 manifest is available; `_normalize_manifest()` handles backward
compatibility for v1.0 manifests.

~~**Scenario name override prefix mismatch:** When using `scenario_name` query param
to override the manifest name (e.g., uploading `telco-noc` scenario as `telco-noc2`),
the graph name came from the config (`telco-noc-topology`) but the telemetry prefix
used the override (`telco-noc2`), causing query-time lookup failures~~ — **Resolved.**
`_rewrite_manifest_prefix()` now rewrites all resource names (graph, telemetry prefix,
search indexes) in the parsed manifest when the override differs from the manifest name.

## CORS Configuration
~~CORS `allow_credentials` mismatch~~ — **Resolved in V8 refactor.** Both services
now consistently set `allow_credentials=True` and use environment-driven `CORS_ORIGINS`.

## Two Gremlin Retry Implementations
`backends/cosmosdb.py` `_submit_query()` (used by query/topology endpoints) and
`router_ingest.py` `_gremlin_submit()` (used by upload endpoints) are separate
retry implementations with different capabilities. `cosmosdb.py` handles `WSServerHandshakeError`
and reconnects on generic errors; `router_ingest.py` is simpler (no reconnect logic).
These should ideally be consolidated.

## Inconsistent Tarball Extraction
Only `/upload/graph` and `/upload/telemetry` use the shared `_extract_tar()` helper.
`/upload/runbooks`, `/upload/tickets` (via shared `_upload_knowledge_files()`), and
`/upload/prompts` each do their own inline `tarfile.open()` + `extractall()` + `os.walk()`.
Should be consolidated.

## graph-query-api Lifespan Unused Import
`main.py` imports `close_all_backends` from `backends` but does NOT call it in the
lifespan shutdown — it calls `close_graph_backend()` + `close_telemetry_backend()`
separately instead. The unused import should be removed or the shutdown should use
`close_all_backends()`.

## Template Has Vars Not Consumed at Runtime
~~`azure_config.env.template` defines `RUNBOOKS_INDEX_NAME`, `TICKETS_INDEX_NAME`,
`RUNBOOKS_CONTAINER_NAME`, `TICKETS_CONTAINER_NAME`, `DEFAULT_SCENARIO`, and
`LOADED_SCENARIOS`~~ — **Resolved in V10.** All 7 vestigial variables (`COSMOS_GREMLIN_GRAPH`,
`RUNBOOKS_INDEX_NAME`, `TICKETS_INDEX_NAME`, `RUNBOOKS_CONTAINER_NAME`,
`TICKETS_CONTAINER_NAME`, `DEFAULT_SCENARIO`, `LOADED_SCENARIOS`) have been removed
from `azure_config.env.template`. These values are now config-driven from `scenario.yaml`.
