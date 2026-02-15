# Azure Deployment Lessons Learned

General lessons from deploying multi-service applications on Azure.
Project-specific architecture details live in [ARCHITECTURE.md](ARCHITECTURE.md);
SDK-specific patterns live in the [skills references](https://github.com/microsoft/skills).

---

## 1. Azure Policy Will Override Your Bicep

**Problem:** Cosmos DB accounts deployed with `publicNetworkAccess: 'Enabled'` were
silently flipped to `Disabled` by an Azure Policy or Defender for Cloud policy —
hours or days after provisioning. This caused 403 Forbidden errors with no
deployment-time warning.

**Symptoms:**
- `403 Forbidden` from Cosmos DB SDKs (Gremlin and NoSQL)
- `az cosmosdb show` reveals `publicNetworkAccess: Disabled` despite Bicep setting it to `Enabled`
- `az cosmosdb update --public-network-access ENABLED` fails with `PreconditionFailed`

**Lesson:** Bicep only sets the *initial* state of a resource. Azure Policy evaluates
continuously and can override properties post-deployment. Never assume that what you
deployed is what's running — always verify with `az resource show` or Resource Graph.

**Fix:** Private Endpoints. Traffic flows over the Azure backbone regardless of the
`publicNetworkAccess` setting. Even if policy disables public access, VNet-connected
services continue to work.

---

## 2. Private Endpoints — The Pattern

When any Azure service (Cosmos DB, Storage, AI Search, etc.) needs to be reachable
from a VNet-integrated service (Container Apps, VMs, Functions with VNet integration),
the standard pattern is:

```
VNet
├── Subnet A: Service (e.g., Container Apps Environment)
├── Subnet B: Private Endpoints
│
Private Endpoint (groupId specific to API)
├── NIC in Subnet B
└── DNS Zone Group → Private DNS Zone → VNet Link
```

**Three resources per endpoint:**
1. **Private Endpoint** — NIC attached to a subnet, linked to the target resource with a `groupId`
2. **Private DNS Zone** — e.g., `privatelink.documents.azure.com` — resolves the service FQDN to the private IP
3. **DNS Zone Group** — attaches the DNS zone to the private endpoint for automatic A-record registration

**The VNet Link** connects the Private DNS Zone to the VNet so DNS resolution works
from within the VNet.

### GroupId Gotcha

The `groupId` is API-specific, not resource-specific. A single Cosmos DB account
with both Gremlin and SQL APIs needs **separate** private endpoints:

| Cosmos DB API | groupId | Private DNS Zone |
|---------------|---------|------------------|
| NoSQL (SQL) | `Sql` | `privatelink.documents.azure.com` |
| Gremlin | `Gremlin` | `privatelink.gremlin.cosmos.azure.com` |
| MongoDB | `MongoDB` | `privatelink.mongo.cosmos.azure.com` |
| Cassandra | `Cassandra` | `privatelink.cassandra.cosmos.azure.com` |
| Table | `Table` | `privatelink.table.cosmos.azure.com` |

The full DNS zone mapping for all Azure services is at:
[Private endpoint DNS zone values](https://learn.microsoft.com/azure/private-link/private-endpoint-dns)

### Keep Public Access Enabled During Provisioning

If you need to run provisioning scripts from your dev machine (outside the VNet),
keep `publicNetworkAccess: 'Enabled'` in Bicep. The private endpoint provides a
parallel path — it doesn't require disabling public access. If policy later disables
the public path, VNet-connected services still work; only external scripts break.

---

## 3. Container Apps VNet Integration

### Subnet Sizing

| Environment Type | Minimum Subnet | API Version |
|-----------------|----------------|-------------|
| Consumption-only (legacy) | `/23` (512 addresses) | `2023-05-01` |
| Workload profiles | `/27` (32 addresses) | `2023-05-01` and later |

The Consumption-only environment consumes the entire subnet and requires delegation
to `Microsoft.App/environments`. The workload profiles environment is more
subnet-efficient.

### Cannot Add VNet In-Place

A Container Apps Environment's VNet configuration is **immutable after creation**.
You cannot add VNet integration to an existing environment. The only path is:

1. Delete the existing Container Apps Environment
2. Re-provision with `vnetConfiguration` set

This means `azd up` (which runs in `--no-prompt` mode by default) won't cleanly
upgrade. You need either:
- `azd down && azd up` (full teardown + reprovision)
- Manual delete of just the CAE resource, then `azd provision && azd deploy`

### External vs Internal Ingress

When VNet-integrating a Container App that needs to be called from **outside** the
VNet (e.g., by an AI platform like Azure AI Foundry's `OpenApiTool`), set
`internal: false` in the `vnetConfiguration`. This preserves the public FQDN while
routing outbound traffic (to Cosmos DB, etc.) through the VNet and private endpoints.

```bicep
vnetConfiguration: {
  infrastructureSubnetId: subnetId
  internal: false  // Foundry needs to reach this from outside
}
```

---

## 4. Cosmos DB Gremlin — Auth Constraint

The Gremlin wire protocol (WebSocket over port 443) does **not support Azure AD /
Managed Identity authentication**. You must use primary key auth:

```python
# Key-based auth — the only option for Gremlin
client = Client(
    url=f"wss://{host}:443/",
    traversal_source="g",
    username=f"/dbs/{db}/colls/{graph}",
    password=primary_key,  # Must be the Cosmos DB primary key
    message_serializer=GraphSONSerializersV2d0()
)
```

This is a Cosmos DB Gremlin limitation, not a code choice. The NoSQL/SQL API
supports both key-based and AAD auth via `DefaultAzureCredential()`.

**Implication for Private Endpoints:** Switching to private endpoints only changes
the network path (public → VNet backbone). Auth remains key-based for Gremlin
regardless.

---

## 5. Azure AI Foundry Agent Tool Constraints

### ConnectedAgentTool Sub-Agents Are Server-Side

When using `ConnectedAgentTool` to create an orchestrator → sub-agent hierarchy,
the sub-agents run **server-side inside Foundry**. They cannot execute client-side
callbacks. This means:

| Tool Type | Execution | Works with ConnectedAgentTool? |
|-----------|-----------|-------------------------------|
| `FunctionTool` | Client-side callback | **No** — no client process to call back to |
| `OpenApiTool` | Server-side REST call | **Yes** — Foundry calls the HTTP endpoint directly |
| `AzureAISearchTool` | Server-side | **Yes** — Foundry has native integration |
| `BingGroundingTool` | Server-side | **Yes** |
| `CodeInterpreterTool` | Server-side sandbox | **Yes** |

**Lesson:** If a sub-agent needs to access a database or custom service, you must
expose it as an HTTP API and use `OpenApiTool`. There is no way to run arbitrary
Python callbacks from a ConnectedAgentTool sub-agent.

### OpenApiTool Error Handling — Errors as 200

Foundry's `OpenApiTool` treats HTTP 4xx/5xx as **fatal tool errors**. The sub-agent
run fails, the ConnectedAgentTool returns failure to the orchestrator, and the
orchestrator run may also fail. The LLM never sees the error message.

**Fix:** Catch all exceptions in your API and return HTTP 200 with the error in the
response body:

```python
@router.post("/query/graph")
async def query_graph(request: GraphQueryRequest):
    try:
        result = await backend.execute_query(request.query)
        return GraphQueryResponse(columns=result["columns"], data=result["data"])
    except Exception as e:
        # Return 200 so Foundry doesn't treat it as a tool failure
        return GraphQueryResponse(columns=[], data=[], error=str(e))
```

Include the `error` field in your OpenAPI spec with a description instructing the
LLM to read the error and retry:

```yaml
error:
  type: string
  nullable: true
  description: >
    If present, the query failed. Read the error message,
    fix your query syntax, and retry.
```

This enables LLM self-repair — the agent reads the error, corrects its query, and
retries without human intervention.

---

## 6. Bicep Patterns That Work

### Subscription-Scoped Deployment with azd

`azd` supports subscription-scoped deployment (`targetScope = 'subscription'`).
This lets you create resource groups in Bicep rather than requiring them to exist
beforehand:

```bicep
targetScope = 'subscription'

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
}

module cosmos 'modules/cosmos.bicep' = {
  name: 'cosmos'
  scope: rg
  params: { ... }
}
```

### Deterministic Resource Naming

Use a hash-based token for globally unique but reproducible names:

```bicep
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
// → consistent across deployments, globally unique
```

### readEnvironmentVariable() for Config

Bicep parameter files can read from environment variables, avoiding hardcoded
values:

```bicepparam
param cosmosGremlinDatabase = readEnvironmentVariable('COSMOS_GREMLIN_DATABASE', 'networkgraph')
```

Combined with `preprovision.sh` syncing values from a dotenv file to `azd env`,
this creates a single-source-of-truth config pattern.

### Conditional Module Deployment

Use boolean parameters to skip expensive modules during iterative development:

```bicep
param deployCosmosGremlin bool

module cosmos 'modules/cosmos.bicep' = if (deployCosmosGremlin) {
  name: 'cosmos'
  scope: rg
  params: { ... }
}

// Downstream modules that depend on cosmos output:
module privateEndpoints 'modules/private-endpoints.bicep' = if (deployCosmosGremlin) {
  name: 'privateEndpoints'
  scope: rg
  params: {
    cosmosAccountId: deployCosmosGremlin ? cosmos.outputs.accountId : ''
  }
}
```

---

## 7. azd Lifecycle Hooks — Practical Patterns

### preprovision.sh — Sync Config to Bicep

```bash
# Read azure_config.env and push selected vars into azd env
# so Bicep's readEnvironmentVariable() can access them
while IFS='=' read -r key value; do
    azd env set "$key" "$value"
done < <(grep -v '^#' azure_config.env | grep '=')
```

### postprovision.sh — Capture Outputs

```bash
# Write azd deployment outputs back to azure_config.env
# so scripts and local dev can use them
COSMOS_ENDPOINT=$(azd env get-value AZURE_COSMOS_ENDPOINT)
echo "COSMOS_ENDPOINT=$COSMOS_ENDPOINT" >> azure_config.env
```

This creates a bidirectional flow:
```
azure_config.env → preprovision → Bicep → postprovision → azure_config.env
```

### remoteBuild for Container Apps

When deploying Container Apps via `azd`, use `remoteBuild: true` in `azure.yaml`
so Docker images are built in ACR rather than locally. This avoids cross-platform
issues (e.g., building on ARM Mac for Linux amd64):

```yaml
services:
  graph-query-api:
    host: containerapp
    docker:
      path: ./graph-query-api/Dockerfile
      remoteBuild: true
```

### Code-Only Redeployment

For code changes that don't affect infrastructure, skip `azd up` and use:

```bash
azd deploy graph-query-api
```

This rebuilds the container image and creates a new Container App revision (~60s)
without re-running Bicep.

---

## 8. Debugging Azure Connectivity Issues

### Diagnostic Checklist

When a service returns 403 or connection refused:

1. **Check the resource's network settings** — not what Bicep says, what's actually deployed:
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

### `az cosmosdb update` PreconditionFailed

If `az cosmosdb update` fails with `PreconditionFailed`, it usually means:
- Another operation is in progress (wait and retry)
- A policy is actively enforcing the state you're trying to change
- The account has a resource lock

Check activity log to identify the conflicting operation.

---

## 9. Container App Identity and RBAC

### Managed Identity for Data Plane

Container Apps support system-assigned managed identity. Use it for data-plane
access to services that support AAD auth:

```bicep
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  identity: {
    type: 'SystemAssigned'
  }
}

// Then assign roles to the identity:
resource cosmosRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, containerApp.identity.principalId, cosmosDataContributor)
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/${cosmosDataContributor}'
    principalId: containerApp.identity.principalId
    scope: cosmosAccount.id
  }
}
```

### Cosmos DB SQL Role vs ARM Role

Cosmos DB NoSQL has its own RBAC system separate from ARM. The built-in roles are:

| Role | GUID | Scope |
|------|------|-------|
| Cosmos DB Built-in Data Reader | `00000000-0000-0000-0000-000000000001` | Data plane read |
| Cosmos DB Built-in Data Contributor | `00000000-0000-0000-0000-000000000002` | Data plane read/write |

These are different from ARM roles like `DocumentDB Account Contributor`. The ARM
role controls management plane; the SQL role controls data plane operations.

---

## 10. General Principles

1. **Verify deployed state, not intended state.** Bicep is declarative but not
   authoritative — policies, manual edits, and drift happen.

2. **Defense in depth for networking.** Private endpoints are the most robust path.
   Public access + IP rules is fragile (IPs change, policies override).

3. **Design APIs for LLM consumers.** If an agent calls your API, errors must be
   in the response body (not HTTP status codes), and error messages must contain
   enough context for the LLM to self-correct.

4. **Understand where your code runs.** Server-side agent tools can't call back to
   your process. Container Apps in a VNet route outbound through the VNet. Your
   Bicep runs at deployment time, but policies run continuously.

5. **Use a single config file.** A dotenv file synced bidirectionally via azd hooks
   prevents config drift across Bicep, scripts, and runtime.

6. **Immutable infrastructure choices.** Some settings (VNet on CAE, Cosmos DB
   partition keys) can't be changed after creation. Know which ones before deploying.

7. **Test with `azd deploy` before `azd up`.** Code-only redeployment is 10× faster
   than full infrastructure provisioning. Structure your workflow to iterate on code
   separately from infra.

---

## 11. Cosmos DB NoSQL — Document ID Restrictions

**Problem:** Cosmos DB NoSQL rejects document IDs containing `/`, `\`, `?`, or `#`.
If your code generates IDs with these characters, `upsert_item()` or `create_item()`
will fail with `"Id contains illegal chars"`.

**How this manifests:** In the browser UI, an upload endpoint that creates Cosmos
documents using a human-readable ID format like `telco-noc/orchestrator/v1` will
fail silently or with a cryptic error. The error text from Cosmos is:
```
Id contains illegal chars. Retry
```

**Fix:** Use `__` (double underscore) as the segment separator instead of `/`:
```python
# BAD — Cosmos rejects this
doc_id = f"{scenario}/{prompt_name}/v{version}"
# e.g. "telco-noc/orchestrator/v1"

# GOOD — Cosmos accepts this
doc_id = f"{scenario}__{prompt_name}__v{version}"
# e.g. "telco-noc__orchestrator__v1"
```

**Also broken:** FastAPI path parameters. A route like `GET /prompts/{prompt_id}`
with an ID containing `/` will be interpreted as multiple URL segments and never
match the route. The `__` separator avoids this too.

**Rule:** Never use `/`, `\`, `?`, or `#` in Cosmos DB document IDs. Use `__` or
`-` as delimiters. If you need to parse the ID back into components, split on `__`.

**Files affected in this project:**
- `graph-query-api/router_prompts.py` — `create_prompt()` generates the ID
- `graph-query-api/router_ingest.py` — `upload_prompts()` generates the ID
- Any code that reads prompt IDs back must use `_parse_scenario_from_id()` which
  splits on `__`

---

## 12. Per-Scenario Cosmos Databases vs Shared Database

**Problem:** Storing all scenario prompts in a single shared database (e.g.,
`platform-config`) makes it impossible to list which scenarios have prompts without
scanning all documents. It also violates the project's established per-scenario
naming convention used by telemetry (`{scenario}-telemetry`) and graphs
(`{scenario}-topology`).

**Fix:** Use per-scenario databases: `{scenario}-prompts` (e.g., `telco-noc-prompts`,
`cloud-outage-prompts`). This matches the existing patterns:

| Data Type | Database Name | Container | Partition Key |
|-----------|--------------|-----------|---------------|
| Graph | `networkgraph` (shared) | `{scenario}-topology` | N/A (graph) |
| Telemetry | `{scenario}-telemetry` | `AlertStream`, `LinkTelemetry` | `/EntityId` |
| Prompts | `{scenario}-prompts` | `prompts` | `/agent` |

**Listing scenarios:** To discover which scenarios have prompts, list all databases
via ARM (`CosmosDBManagementClient.sql_resources.list_sql_databases`) and filter for
names ending in `-prompts`. Strip the suffix to get the scenario name.

**Code pattern:**
```python
_containers: dict[str, object] = {}  # cached per-scenario containers

def _get_prompts_container(scenario: str, *, ensure_created: bool = False):
    if scenario in _containers:
        return _containers[scenario]
    db_name = f"{scenario}-prompts"
    if ensure_created:
        # ARM calls to create db + container (slow, ~10-30s)
        ...
    # Data-plane client (fast)
    client = CosmosClient(url=endpoint, credential=cred)
    container = client.get_database_client(db_name).get_container_client("prompts")
    _containers[scenario] = container
    return container
```

---

## 13. ARM Creation Calls Block the Event Loop — Split Read vs Write

**Problem:** The Cosmos DB ARM management plane calls
(`begin_create_update_sql_database().result()`) block for 10-30 seconds. If these
calls run on every container access (including reads), they block FastAPI's event
loop and cause downstream HTTP requests to timeout.

**How this manifests:** Agent provisioning calls `GET /query/prompts` to fetch
prompts from Cosmos. If the prompts router's `_get_prompts_container()` triggers
ARM creation on every access, the response takes 30+ seconds. The caller
(`config.py`) has a 10-second timeout via `urllib.request.urlopen(..., timeout=10)`.
The request times out, no prompts are returned, and agents are provisioned with
placeholder defaults like `"You are a graph explorer agent."`.

**Fix:** Split the container accessor into read-only (default) and write modes:
```python
def _get_prompts_container(scenario: str, *, ensure_created: bool = False):
    """
    ensure_created=False (default): Data-plane client only. Fast. For reads.
    ensure_created=True: ARM create db/container first. Slow. For writes/uploads.
    """
```

- **Read paths** (list prompts, get prompt, prompt scenarios) → `ensure_created=False`
- **Write paths** (upload prompts, create prompt) → `ensure_created=True`

This ensures read endpoints respond in <1 second while write endpoints still
guarantee the database exists before upserting.

---

## 14. Avoid N+1 HTTP Requests Between Co-Located Services

**Problem:** When service A (API on :8000) fetches data from service B
(graph-query-api on :8100) inside the same container, each HTTP request has
overhead. An N+1 pattern — 1 list request + N detail requests to fetch content —
multiplies timeout risk and is unnecessary when both services share the container.

**How this manifests:** Agent provisioning lists prompts, then fetches each prompt
individually to get content. With 5 agents, that's 6 HTTP requests through
localhost. If any one times out, that agent gets no prompt.

**Fix:** Add an `include_content` query parameter to the list endpoint:
```python
@router.get("/prompts")
async def list_prompts(
    scenario: str | None = None,
    include_content: bool = Query(default=False),
):
    fields = "c.id, c.agent, c.scenario, c.name, c.version, ..."
    if include_content:
        fields += ", c.content"
    # Single Cosmos query returns everything needed
```

Then the caller makes one request:
```python
url = f"http://127.0.0.1:8100/query/prompts?scenario={sc}&include_content=true"
```

**Also increase the timeout:** Even with a single request, Cosmos cold-start can
take a few seconds. Use `timeout=30` instead of `timeout=10` for internal service
calls that hit Cosmos.

---

## 15. OpenAPI Tools MUST Include X-Graph Header for Per-Scenario Routing

**Problem:** When agents call `/query/graph` or `/query/telemetry` via OpenApiTool,
the request goes through Foundry's server-side HTTP client. If the OpenAPI spec
doesn't define an `X-Graph` header parameter, the agent has no way to send it.
The graph-query-api falls back to the default graph from `COSMOS_GREMLIN_GRAPH`
env var (typically just `topology`), not the scenario-specific graph (e.g.,
`telco-noc-topology`). Queries return empty results even though data exists.

**How this manifests:** The agent runs `g.V()` and gets `columns: [], data: []`.
But the same query in Cosmos Data Explorer (which targets the correct graph)
returns hundreds of vertices. The confusion is that the query itself is correct —
only the routing is wrong.

**Fix:** Add the `X-Graph` header to the OpenAPI spec with a `default` value that
gets substituted at provisioning time:

```yaml
# In openapi/cosmosdb.yaml
/query/graph:
  post:
    parameters:
      - name: X-Graph
        in: header
        required: true
        schema:
          type: string
          default: "{graph_name}"  # Replaced at provisioning time
        description: |
          The graph name to query. Always use "{graph_name}".
```

The provisioner replaces `{graph_name}` with the actual graph name (e.g.,
`telco-noc-topology`) when loading the spec:

```python
def _load_openapi_spec(uri, backend, keep_path, graph_name="topology"):
    raw = spec_file.read_text()
    raw = raw.replace("{base_url}", uri)
    raw = raw.replace("{graph_name}", graph_name)
    return yaml.safe_load(raw)
```

**Critical flow — provisioner must receive the graph name:**
1. Frontend sends `POST /api/config/apply` with `{ graph: "telco-noc-topology" }`
2. `config.py` passes `graph_name=req.graph` to `provisioner.provision_all()`
3. `provision_all()` passes it to `_load_openapi_spec()` for each tool
4. The spec is baked into the Foundry agent with the correct default header value
5. When the agent calls `/query/graph`, Foundry sends `X-Graph: telco-noc-topology`
6. `get_scenario_context()` reads the header and routes to the correct graph

**Implication:** Agents are provisioned for a **specific** scenario's graph. If the
user switches scenarios in the UI, they must re-provision agents (click "Provision
Agents" again) to rebind the OpenAPI tool to the new graph name. This is by design —
the agents need correct schema/prompt context per scenario anyway.

---

## 16. Container App Environment Variables vs azure_config.env

**Problem:** Confusion about whether `azure_config.env` needs to be uploaded to the
container or included in the Docker image.

**Clarification:** The container **never reads** `azure_config.env`. There are two
parallel config paths that both originate from Bicep outputs:

```
┌─────────────────────────────┐     ┌──────────────────────────────┐
│  azure_config.env (local)   │     │  Container App env vars      │
│                             │     │                              │
│  Written by:                │     │  Set by:                     │
│    postprovision.sh         │     │    infra/main.bicep env:[]   │
│                             │     │                              │
│  Used by:                   │     │  Used by:                    │
│    - Local scripts          │     │    - API (os.environ)        │
│    - preprovision.sh hook   │     │    - graph-query-api         │
│    - Local dev servers      │     │    - agent_provisioner.py    │
│                             │     │                              │
│  NOT in Docker image        │     │  Injected by Azure at       │
│  NOT read at runtime        │     │  container start time        │
└─────────────────────────────┘     └──────────────────────────────┘
```

**Rule:** To add a new config variable:
1. Add it to `infra/main.bicep` in the `env:` array of the container app module
2. Add it to `hooks/postprovision.sh` to populate `azure_config.env` for local use
3. Read it in Python via `os.getenv("VAR_NAME")`

Do NOT: `COPY azure_config.env` in the Dockerfile. Do NOT: `source azure_config.env`
in supervisord. The container's env vars are the source of truth at runtime.

**Exception — GRAPH_QUERY_API_URI:** This env var isn't set in `main.bicep` because
it's a circular reference (the container's URL isn't known until after deployment).
The fix is to fall back to `CONTAINER_APP_HOSTNAME`, which Azure automatically sets
on every Container App:

```python
graph_query_uri = os.getenv("GRAPH_QUERY_API_URI", "")
if not graph_query_uri:
    hostname = os.getenv("CONTAINER_APP_HOSTNAME", "")
    if hostname:
        graph_query_uri = f"https://{hostname}"
```

---

## 17. Code-Only Redeployment — When azd deploy Is Enough

Not every change requires `azd up` (full infra + deploy). Use this decision tree:

| Change Type | Command | Time |
|-------------|---------|------|
| Python code, OpenAPI specs, static files | `azd deploy app` | ~60-90s |
| Bicep infrastructure (new resources, env vars, RBAC) | `azd up` | ~5-10min |
| New env var in container | `azd up` (env vars are in Bicep) | ~5-10min |
| Frontend-only changes | `azd deploy app` | ~60-90s |
| Dockerfile changes | `azd deploy app` | ~60-90s |

**After code-only deploy:** If you changed agent provisioning logic or OpenAPI specs,
you must also re-provision agents through the UI (⚙ → Provision Agents) because the
old agents in Foundry still have the old tool specs baked in. The deploy only updates
the container image — it doesn't automatically re-provision agents.

---

## 18. Cosmos NoSQL RBAC — Two-Phase Create Pattern

**Problem:** The `Cosmos DB Built-in Data Contributor` role
(`00000000-0000-0000-0000-000000000002`) allows read/write on the data plane but
does NOT allow creating databases or containers. Attempting to create a database
with `CosmosClient(...).create_database_if_not_exists()` using only this role will
fail with 403.

**Fix:** Use two-phase creation:

1. **Phase 1 — ARM management plane** (uses `DocumentDB Account Contributor` role):
   ```python
   from azure.mgmt.cosmosdb import CosmosDBManagementClient
   from azure.identity import DefaultAzureCredential
   mgmt = CosmosDBManagementClient(DefaultAzureCredential(), subscription_id)
   mgmt.sql_resources.begin_create_update_sql_database(
       rg, account_name, db_name,
       {"resource": {"id": db_name}},
   ).result()
   ```

2. **Phase 2 — Data plane** (uses `Cosmos DB Built-in Data Contributor` role):
   ```python
   from azure.cosmos import CosmosClient
   client = CosmosClient(url=endpoint, credential=DefaultAzureCredential())
   container = client.get_database_client(db_name).get_container_client("prompts")
   container.upsert_item(doc)
   ```

**Critical:** Create a **fresh** `DefaultAzureCredential()` inside the thread
function for ARM calls. Do NOT reuse a credential instance that was created in the
async event loop context — it may have been initialized with an incompatible
transport.

**Both roles must be assigned** to the Container App's managed identity in
`infra/modules/roles.bicep`:
- `DocumentDB Account Contributor` on both Cosmos accounts (management plane)
- `Cosmos DB Built-in Data Contributor` SQL role on the NoSQL account (data plane)
