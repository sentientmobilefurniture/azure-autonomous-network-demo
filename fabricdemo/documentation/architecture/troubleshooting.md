# Quick Reference: Where to Fix Things

| Problem | File(s) to check |
|---------|-----------------|
| Upload fails with event loop error | Wrap ALL SDK calls in `asyncio.to_thread()` — see `router_ingest.py` |
| Upload fails with auth/forbidden | Check RBAC in `infra/modules/roles.bicep`, `azd up` to re-apply |
| NoSQL create_database forbidden | Need ARM two-phase: create via `azure-mgmt-cosmosdb`, then data plane |
| Gremlin 401 WSServerHandshakeError | Check `COSMOS_GREMLIN_PRIMARY_KEY` in `azure_config.env` |
| Gremlin 429 throttling | Retry logic in `cosmosdb.py._submit_query()` handles this; increase RU/s |
| Graph not in dropdown | `GET /query/scenarios` in `router_ingest.py` |
| Topology viewer empty | `X-Graph` header in `useTopology.ts`, `ScenarioContext` state |
| Agent provisioning fails | `api/app/routers/config.py`, `scripts/agent_provisioner.py` |
| Agents created without prompts | Upload prompts tarball, check `GET /query/prompts/scenarios` |
| Agents created without tools | Check `GRAPH_QUERY_API_URI` env var = Container App public URL |
| Container build fails | `.dockerignore`, `Dockerfile` COPY paths |
| Search index not created | `AI_SEARCH_NAME` env var, RBAC roles, `search_indexer.py` |
| Health check HTML splash | Container still deploying; wait for revision |
| `No module named agent_provisioner` | `sys.path` in `config.py` — check both `scripts/` paths |
| Investigation stuck >2min | `EVENT_TIMEOUT` in `orchestrator.py`; check sub-agent tool errors |
| SSE stream not reaching frontend | nginx `proxy_buffering off` in `nginx.conf`; check timeouts |
| Prompt upload "illegal chars" | Doc ID has `/`—use `__` separator. See `router_prompts.py`, `router_ingest.py` |
| Cosmos policy override | Check `az cosmosdb show --query publicNetworkAccess`; use private endpoints |
| VNet connectivity issues | Check private endpoint status + DNS resolution from within VNet |
| Prompts listing slow | Use `?scenario=X` filter to avoid iterating all databases |
| Agent queries return empty results | OpenAPI spec `X-Graph` header using `default` instead of `enum`. Check `openapi/templates/graph.yaml` (V10) or legacy `openapi/cosmosdb.yaml`, use single-value `enum` |
| Topology viewer crashes on label filter | f-string bug in `cosmosdb.py` `get_topology()` edge query. Add `f` prefix. |
| Agents get placeholder prompts | `_get_prompts_container` ensure_created=True on reads blocks event loop; check timeout |
| Config var not reaching container | Add to `infra/main.bicep` `env:[]`, NOT to `azure_config.env` in Dockerfile |
| `GRAPH_QUERY_API_URI` empty in container | Falls back to `CONTAINER_APP_HOSTNAME`. Check `agent_provisioner.py` |
| Prompt CRUD slow / blocks other requests | Sync Cosmos calls in async handlers. Wrap in `asyncio.to_thread()` |
| Local dev `/query/*` fails after `deploy.sh` step 7 | Step 7 doesn't start graph-query-api. Start manually on :8100 |
| Prompt dropdown not refreshed after upload | UploadBox for prompts has no `onComplete` callback. Close/reopen modal |
| Scenario context lost on page refresh | Fixed: `activeScenario` persisted to `localStorage`, bindings auto-derived on mount |
| New scenario data pack | Follow `scenarios/telco-noc/` structure; create `scenario.yaml` + `graph_schema.yaml` |
| Saved scenario not appearing | Check `GET /query/scenarios/saved`; may be first-call ARM delay for `scenarios` db |
| Scenario selection not provisioning | Check `selectScenario()` in `useScenarios.ts`; verify `/api/config/apply` is reachable |
| ScenarioChip shows wrong scenario | Check `activeScenario` in `localStorage`; clear with `localStorage.removeItem('activeScenario')` |
| AddScenarioModal files not auto-detected | Filename must match `{name}-{slot}.tar.gz` pattern; `detectSlot()` in `AddScenarioModal.tsx` |
| Scenario name rejected by backend | Name validation: `^[a-z0-9](?!.*--)[a-z0-9-]{0,48}[a-z0-9]$`; no reserved suffixes |
| Telemetry queries return empty after rename | Upload override forces `-telemetry` suffix; check `config.py` derivation matches |
| Provisioning banner stuck | Check `provisioningStatus` state in `ScenarioContext`; 3s auto-dismiss timer may not fire if error |
| Cosmos 403 after successful deploy | Azure Policy override. Run `az cosmosdb show --query publicNetworkAccess`. See Lesson #20 diagnostic checklist |
| Need to debug VNet DNS issues | Run `nslookup <account>.documents.azure.com` from within VNet. Should resolve to `10.x.x.x`. See Lesson #20 |
| LLM agent sends wrong header value | OpenAPI spec uses `default` — change to single-value `enum`. See Lessons #15 and #19 |
| CAE needs VNet but already deployed | VNet is immutable on CAE. Must `azd down && azd up`. See Lesson #9 |
| Sub-agent tool not executing | `FunctionTool` doesn't work with `ConnectedAgentTool`. Must use `OpenApiTool`. See Lesson #5 |
| Full environment teardown needed | Use `infra/nuclear_teardown.sh` (azd down + Cognitive Services purge + RG delete + env delete) |
| First Cosmos DB access slow (~20-30s) | ARM database/container creation on first use. See QOL backlog item #1 for pre-provisioning in Bicep |
| Need to change dark theme colors | `frontend/src/styles/globals.css` — CSS custom properties for the entire color scheme |
| Upload retry logic differs from query retry | `router_ingest.py` `_gremlin_submit` vs `cosmosdb.py` `_submit_query` — different retry capabilities |
| Graph node colors wrong after scenario switch | Check `useNodeColor.ts` fallback chain; verify `setScenarioStyles()` called in `selectScenario()`; check `scenarioNodeColors` in `ScenarioContext` |
| Scenario info tab empty | Check `activeScenario` set in context; verify saved scenario has `use_cases` / `example_questions` populated |
| Example question not injecting into chat | Check `onSelectQuestion` callback in `ScenarioInfoPanel` → `App.tsx`; verify `setAlert` + tab switch logic |
| Scenario metadata not saved | Check `scenarioMetadataRef` in `AddScenarioModal.tsx`; verify graph upload `onComplete` captures `data.scenario_metadata` |
| Config-driven provisioning fails | Check `config_store.py` can read from `scenarios/configs`; verify `scenario.yaml` has `agents:` section; check `config_validator.py` validation errors |
| Resource visualizer empty | Check `GET /api/config/resources` returns data; verify `activeScenario` is set and scenario config exists in `scenarios/configs` |
| `needs-provisioning` banner not showing | `ProvisioningBanner` checks `GET /api/agents`; if endpoint fails or returns non-empty array, banner won't show |
| Legacy provisioning used instead of config-driven | Ensure `scenario.yaml` has `agents:` section; `_build_prompt_agent_map_from_config()` falls back to `PROMPT_AGENT_MAP` if no agents in config |
| v1.0 scenario.yaml not working | `_normalize_manifest()` should auto-convert; check `router_ingest.py` line ~52 for normalization logic |
| Telemetry containers not found after V10 upgrade | V10 uses shared `telemetry` DB with `{scenario}-ContainerName` pattern; old data in per-scenario DBs needs migration |
