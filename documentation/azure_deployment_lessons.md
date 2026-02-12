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
