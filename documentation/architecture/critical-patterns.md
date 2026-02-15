# Critical Patterns & Lessons

## 1. async/await + Azure SDK — `asyncio.to_thread()` Requirement

**All Azure SDK calls MUST be in `asyncio.to_thread()`**. The `DefaultAzureCredential`, `gremlinpython` WebSocket client, `CosmosClient`, and ARM management clients all internally use event loops that conflict with FastAPI's async loop. Every upload endpoint wraps its entire SDK chain in a sync function called via `to_thread`.

## 2. Credential Isolation in Threads

**IMPORTANT:** ARM calls that run inside `asyncio.to_thread()` should use the
cached credential from `cosmos_helpers.get_mgmt_client()` (which uses `config.get_credential()`).
The V8 refactor centralised all credential and client creation into `cosmos_helpers.py`,
eliminating per-router `DefaultAzureCredential` instantiation. The shared credential
is safe when used consistently through the centralised helpers.

## 3. Cosmos DB — Two-Phase Pattern

The built-in data contributor role (`00000000-0000-0000-0000-000000000002`) does NOT include database/container creation permissions. Upload endpoints use:
1. **ARM** (`azure-mgmt-cosmosdb`) for database/container/graph creation — requires `DocumentDB Account Contributor` role
2. **Data plane** (`CosmosClient` or Gremlin) for data operations — requires `Cosmos DB Built-in Data Contributor` role (or key auth for Gremlin)

## 4. Cosmos Gremlin — Key Auth Only

The Gremlin wire protocol (WSS) does **not support Azure AD / Managed Identity**. Must use primary key auth. This is a Cosmos DB limitation, not a code choice. NoSQL/SQL API supports both.

## 5. ConnectedAgentTool — Server-Side Execution

Sub-agents using `ConnectedAgentTool` run **server-side inside Foundry**. They cannot execute client-side callbacks. This means `FunctionTool` does NOT work — use `OpenApiTool` (HTTP endpoint) instead.

| Tool Type | Execution | Works with ConnectedAgentTool? |
|-----------|-----------|-------------------------------|
| `FunctionTool` | Client-side callback | **No** — no client process to call back to |
| `OpenApiTool` | Server-side REST call | **Yes** — Foundry calls the HTTP endpoint directly |
| `AzureAISearchTool` | Server-side | **Yes** — Foundry has native integration |
| `BingGroundingTool` | Server-side | **Yes** |
| `CodeInterpreterTool` | Server-side sandbox | **Yes** |

**Lesson:** If a sub-agent needs to access a database or custom service, you must expose it as an HTTP API and use `OpenApiTool`. There is no way to run arbitrary Python callbacks from a ConnectedAgentTool sub-agent.

## 6. OpenApiTool — HTTP Errors Are Fatal

Foundry's `OpenApiTool` treats HTTP 4xx/5xx as fatal. The LLM never sees the error message. Solution: return HTTP 200 with error in the response body + instructional description in the OpenAPI spec.

## 7. Azure Policy Overrides Bicep

Bicep only sets the *initial* state. Azure Policy evaluates continuously and can override properties (e.g., flipping `publicNetworkAccess` to `Disabled`). Always verify deployed state with `az resource show`.

## 8. Private Endpoints Pattern

When any Azure service needs VNet connectivity, the standard pattern requires **3 resources per endpoint**:
1. **Private Endpoint** — NIC attached to subnet, linked to target resource with API-specific `groupId`
2. **Private DNS Zone** — resolves service FQDN to private IP (e.g., `privatelink.documents.azure.com`)
3. **DNS Zone Group** — attaches DNS zone to endpoint for automatic A-record registration

A **VNet Link** connects the Private DNS Zone to the VNet so DNS resolution works from within.

Cosmos DB needs **separate endpoints per API**:

| Cosmos DB API | groupId | Private DNS Zone |
|---------------|---------|------------------|
| NoSQL (SQL) | `Sql` | `privatelink.documents.azure.com` |
| Gremlin | `Gremlin` | `privatelink.gremlin.cosmos.azure.com` |
| MongoDB | `MongoDB` | `privatelink.mongo.cosmos.azure.com` |
| Cassandra | `Cassandra` | `privatelink.cassandra.cosmos.azure.com` |
| Table | `Table` | `privatelink.table.cosmos.azure.com` |

Full DNS zone mapping for all Azure services: [Private endpoint DNS zone values](https://learn.microsoft.com/azure/private-link/private-endpoint-dns)

**Keep Public Access Enabled During Provisioning:** If provisioning scripts run from your dev machine (outside VNet), keep `publicNetworkAccess: 'Enabled'` in Bicep. The private endpoint provides a parallel path — it doesn't require disabling public access. If policy later disables the public path, VNet-connected services still work; only external scripts break.

## 9. Container Apps VNet + External Ingress

Must use `internal: false` in VNet config for the Container App because AI Foundry's `OpenApiTool` calls the app from **outside** the VNet. This preserves the public FQDN while routing outbound traffic through VNet + private endpoints.

**Subnet sizing:**

| Environment Type | Minimum Subnet | API Version |
|-----------------|----------------|-------------|
| Consumption-only (legacy) | `/23` (512 addresses) | `2023-05-01` |
| Workload profiles | `/27` (32 addresses) | `2023-05-01` and later |

Consumption-only requires delegation to `Microsoft.App/environments`. Workload profiles are more subnet-efficient.

**Container Apps Environment VNet config is immutable after creation.** Cannot add VNet to existing CAE. Recovery: `azd down && azd up` (full teardown + reprovision), or manually delete just the CAE resource then `azd provision && azd deploy`.

## 10. Two Cosmos Accounts

The system uses **two separate Cosmos DB accounts**:
- `{name}` — Gremlin API (graph data, key auth)
- `{name}-nosql` — NoSQL/SQL API (telemetry + prompts, RBAC auth)

Each needs its own private endpoint (with different `groupId` values).

## 11. Cosmos DB Document ID Restrictions

Cosmos DB NoSQL rejects document IDs containing `/`, `\`, `?`, or `#`. Use `__` (double underscore) as the segment separator:

```python
# BAD — Cosmos rejects this
doc_id = f"{scenario}/{prompt_name}/v{version}"

# GOOD
doc_id = f"{scenario}__{prompt_name}__v{version}"
# e.g. "telco-noc__orchestrator__v1"
```

Also broken: FastAPI path parameters — an ID containing `/` is interpreted as multiple URL segments and never matches the route. The `__` separator avoids both issues.

**Files affected:** `router_prompts.py` (create_prompt), `router_ingest.py` (upload_prompts). Code that parses IDs back uses `_parse_scenario_from_id()` splitting on `__`.

## 12. Per-Scenario Cosmos Databases — Naming Convention

Scenario data uses a mix of shared databases with per-scenario containers/graphs,
and dedicated databases. The V10 config-driven architecture reads these from
`scenario.yaml` `data_sources:` section rather than deriving them by convention:

| Data Type | Database Name | Container/Graph | Partition Key | Source |
|-----------|--------------|-----------------|---------------|--------|
| Graph | `networkgraph` (shared) | `{scenario}-topology` | N/A (graph) | `data_sources.graph.config` |
| Telemetry | `telemetry` (shared) | `{scenario}-AlertStream`, `{scenario}-LinkTelemetry` | per container | `data_sources.telemetry.config` |
| Prompts | `prompts` (shared) | `{scenario}` | `/agent` | Derived from scenario name |
| Scenario Registry | `scenarios` (shared) | `scenarios` | `/id` | Hardcoded |
| Scenario Config | `scenarios` (shared) | `configs` | `/scenario_name` | `config_store.py` |
| Interaction History | `interactions` (shared) | `interactions` | `/scenario` | Hardcoded |

> **V10 change**: Telemetry moved from per-scenario databases (`{scenario}-telemetry`)
> to a shared `telemetry` database with per-scenario container prefixes. Prompts
> similarly moved to a shared `prompts` database. This reduces ARM creation overhead
> and simplifies cleanup.

To discover which scenarios have data, query `scenarios/scenarios` with cross-partition query
or use `GET /api/config/resources` for a resource graph visualization.

## 13. ARM Creation Calls Block the Event Loop — Split Read vs Write

Cosmos ARM management plane calls (`begin_create_update_sql_database().result()`) block for 10-30 seconds. If these run on every container access (including reads), FastAPI's event loop is blocked and downstream requests timeout.

**How this manifests:** Agent provisioning calls `GET /query/prompts` to fetch prompts. If `_get_prompts_container()` triggers ARM creation on every access, the response takes 30+ seconds. The caller (`config.py`) has a timeout via `urllib.request.urlopen(..., timeout=30)`. The request times out, no prompts are returned, and agents get placeholder defaults like `"You are a graph explorer agent."`

**Fix:** Split the container accessor:
```python
def _get_prompts_container(scenario: str, *, ensure_created: bool = False):
    # ensure_created=False (default): Data-plane client only. Fast. For reads.
    # ensure_created=True: ARM create db/container first. Slow. For writes/uploads.
```

- **Read paths** (list, get, scenarios) → `ensure_created=False`
- **Write paths** (upload, create) → `ensure_created=True`

## 14. Avoid N+1 HTTP Requests Between Co-Located Services

When API (:8000) fetches data from graph-query-api (:8100) inside the same container, each HTTP request has overhead. An N+1 pattern (1 list + N detail requests) multiplies timeout risk.

**Fix:** Use `include_content` query parameter on list endpoints:
```python
url = f"http://127.0.0.1:8100/query/prompts?scenario={sc}&include_content=true"
```

This returns everything in a single request. Also set `timeout=30` (not 10) for internal service calls that hit Cosmos.

## 15. OpenAPI Tools MUST Include X-Graph Header for Per-Scenario Routing

When agents call `/query/graph` or `/query/telemetry` via `OpenApiTool`, Foundry's server-side HTTP client sends the request. If the OpenAPI spec doesn't define an `X-Graph` header parameter, the agent can't send it. The graph-query-api falls back to the default graph from env vars, not the scenario-specific graph. Queries return empty results.

**V10 approach — OpenAPI templates:** Instead of static spec files, V10 uses template
files at `openapi/templates/{graph,telemetry}.yaml` with placeholders:
```yaml
parameters:
  - name: X-Graph
    in: header
    required: true
    schema:
      type: string
      enum: ["{graph_name}"]  # Replaced at provisioning time — single-value enum CONSTRAINS the LLM
```

The provisioner reads the template, replaces `{graph_name}`, `{base_url}`,
`{query_language_description}`, etc. with actual values from `scenario.yaml`,
and passes the filled spec to `OpenApiTool`.

Legacy static specs (`openapi/cosmosdb.yaml`, `openapi/mock.yaml`) still exist for
backward compatibility with non-config-driven provisioning.

**CRITICAL — Use `enum`, NOT `default`:** LLM agents ignore `default` values (they're advisory hints). The LLM will see a parameter named `X-Graph`, infer it needs a graph name, and choose a plausible but wrong value like `"topology"`. A single-value `enum` constrains the LLM to exactly one valid value — it has no choice but to send the correct graph name. This applies to ANY OpenAPI parameter consumed by an LLM agent that MUST have a specific value (routing headers, API keys, fixed config values).

## 16. Container App Env Vars vs azure_config.env — Two Parallel Config Paths

The container **never reads** `azure_config.env`. There are two parallel paths:

```
azure_config.env (local)           Container App env vars
├── Written by: postprovision.sh   ├── Set by: infra/main.bicep env:[]
├── Used by:                       ├── Used by:
│   - Local dev servers            │   - API (os.environ)
│   - preprovision.sh hook         │   - graph-query-api
│   - Local scripts                │   - agent_provisioner.py
└── NOT in Docker image            └── Injected by Azure at start
```

To add a new config variable:
1. Add to `infra/main.bicep` in the container app `env:` array
2. Add to `hooks/postprovision.sh` to populate `azure_config.env`
3. Read in Python via `os.getenv("VAR_NAME")`

Do NOT `COPY azure_config.env` in the Dockerfile. Do NOT `source azure_config.env` in supervisord.

**Exception — `GRAPH_QUERY_API_URI`:** Not set in `main.bicep` (circular reference — URL unknown until after deployment). Falls back to `CONTAINER_APP_HOSTNAME` (auto-set by Azure on every Container App):
```python
graph_query_uri = os.getenv("GRAPH_QUERY_API_URI", "")
if not graph_query_uri:
    hostname = os.getenv("CONTAINER_APP_HOSTNAME", "")
    if hostname:
        graph_query_uri = f"https://{hostname}"
```

## 17. Code-Only Redeployment Decision Tree

| Change Type | Command | Time |
|-------------|---------|------|
| Python code, OpenAPI specs, static files | `azd deploy app` | ~60-90s |
| Bicep infrastructure (new resources, env vars, RBAC) | `azd up` | ~5-10min |
| New env var in container | `azd up` (env vars are in Bicep) | ~5-10min |
| Frontend-only changes | `azd deploy app` | ~60-90s |
| Dockerfile changes | `azd deploy app` | ~60-90s |

**After code-only deploy:** If you changed agent provisioning logic or OpenAPI specs, you must also re-provision agents through the UI (⚙ → Provision Agents) because old agents in Foundry still have old tool specs baked in.

## 18. Cosmos NoSQL RBAC — Both Roles Required

**Both** roles must be assigned to the Container App's managed identity:
- `DocumentDB Account Contributor` on both Cosmos accounts (management plane — ARM create db/container)
- `Cosmos DB Built-in Data Contributor` SQL role on the NoSQL account (data plane — upsert/query)

Cosmos DB NoSQL has its **own RBAC system** separate from ARM:

| Role | GUID | Scope |
|------|------|-------|
| Cosmos DB Built-in Data Reader | `00000000-0000-0000-0000-000000000001` | Data plane read |
| Cosmos DB Built-in Data Contributor | `00000000-0000-0000-0000-000000000002` | Data plane read/write |

These are assigned via `Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments` (NOT `Microsoft.Authorization/roleAssignments`). The ARM role `DocumentDB Account Contributor` controls management plane only.

**Critical:** Create a **fresh** `DefaultAzureCredential()` inside the `asyncio.to_thread()` sync function for ARM calls. Do NOT reuse a credential instance created in the async event loop context — it may have an incompatible transport.

## 19. OpenAPI Tool Headers — Use `enum`, Not `default`

When Foundry's `OpenApiTool` sends HTTP requests on behalf of an agent, the LLM decides parameter values. A `default` value is only a hint — the LLM can and does ignore it, choosing plausible but wrong values (e.g., `X-Graph: topology` instead of `X-Graph: telco-noc-topology`).

**Fix:** Use a single-value `enum` to constrain the LLM:
```yaml
# BAD — LLM ignores default
schema:
  type: string
  default: "telco-noc-topology"

# GOOD — LLM has no choice
schema:
  type: string
  enum: ["telco-noc-topology"]
```

In template form: `enum: ["{graph_name}"]`. The provisioner substitutes the actual value.

**Rule:** When an OpenAPI parameter consumed by an LLM agent MUST have a specific value, use `enum` with a single entry — never `default`. `default` is advisory; `enum` is a constraint. Applies to routing headers, API keys, fixed config values — any parameter where the LLM should not be making a choice.

## 20. Debugging Azure Connectivity Issues

**Diagnostic checklist** when a service returns 403 or connection refused:

1. **Check actual deployed network settings** (not what Bicep says):
   ```bash
   az cosmosdb show -n <name> -g <rg> --query "publicNetworkAccess"
   az cosmosdb show -n <name> -g <rg> --query "ipRules"
   ```

2. **Check for Azure Policy overrides:**
   ```bash
   az monitor activity-log list --resource-group <rg> \
     --query "[?authorization.action=='Microsoft.DocumentDB/databaseAccounts/write'].{caller:caller, time:eventTimestamp, status:status.value}" \
     --output table
   ```

3. **Check RBAC assignments** (for AAD-authed services):
   ```bash
   az role assignment list --scope <resource-id> --output table
   ```

4. **Check private endpoint connection status:**
   ```bash
   az network private-endpoint-connection list --id <resource-id> --output table
   # Status should be "Approved"
   ```

5. **Check DNS resolution from within the VNet:**
   ```bash
   # From a Container App console or VM in the VNet:
   nslookup <account>.documents.azure.com
   # Should resolve to 10.x.x.x (private IP), not a public IP
   ```

**`az cosmosdb update` PreconditionFailed:** Usually means another operation is in progress (wait and retry), a policy is actively enforcing state, or the account has a resource lock. Check activity log to identify the conflicting operation.

## 21. General Deployment Principles

1. **Verify deployed state, not intended state.** Bicep is declarative but not authoritative — policies, manual edits, and drift happen.
2. **Defense in depth for networking.** Private endpoints are the most robust path. Public access + IP rules is fragile (IPs change, policies override).
3. **Design APIs for LLM consumers.** If an agent calls your API, errors must be in the response body (not HTTP status codes), and error messages must contain enough context for the LLM to self-correct.
4. **Understand where your code runs.** Server-side agent tools can't call back to your process. Container Apps in a VNet route outbound through the VNet. Bicep runs at deployment time, but policies run continuously.
5. **Use a single config file.** A dotenv file synced bidirectionally via azd hooks prevents config drift across Bicep, scripts, and runtime.
6. **Immutable infrastructure choices.** Some settings (VNet on CAE, Cosmos DB partition keys) can't be changed after creation. Know which ones before deploying.
7. **Test with `azd deploy` before `azd up`.** Code-only redeployment is 10× faster than full infra provisioning. Structure your workflow to iterate on code separately from infra.

## 22. Two Separate Log Broadcasting Systems

API (:8000) and graph-query-api (:8100) each have their own SSE log endpoint
with **independent** ring buffers, subscriber queues, and filters:
- API: `GET /api/logs` — captures `app.*`, `azure.*`, `uvicorn.*` loggers
- graph-query-api: `GET /query/logs` — captures only `graph-query-api.*` loggers

The V8 refactor removed the shadowed `/api/logs` endpoint from graph-query-api
(it was unreachable in production due to nginx routing `/api/*` → :8000).
The graph-query-api log stream is now at `/query/logs` which is routed correctly
through nginx.

## 23. No Authentication on Any Endpoint

Neither the API nor graph-query-api implements authentication or authorization.
All endpoints are publicly accessible when exposed via Container App with external
ingress. Security relies on the Container App's network configuration.
