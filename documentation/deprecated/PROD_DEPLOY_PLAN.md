# V5 Production Deployment Plan

## Goal

Deploy all three services to Azure Container Apps so the entire application runs
in Azure with no local processes required. Currently only `graph-query-api` is
deployed; the `api` (FastAPI backend) and `frontend` (React SPA) run locally.

## Current vs Target Architecture

```
CURRENT (local + Azure hybrid)
──────────────────────────────
Browser → localhost:5173 (Vite dev) → localhost:8000 (uvicorn) → Foundry Agents
                                                                      │
Foundry Agents → OpenApiTool → ca-graphquery-xxx.azurecontainerapps.io → Cosmos DB
                                      (Container App, deployed)

TARGET (fully deployed)
───────────────────────
Browser → ca-frontend-xxx.azurecontainerapps.io (nginx, static + reverse proxy)
              │
              │ /api/* /health proxied to internal FQDN
              ▼
          ca-api-xxx (internal ingress, port 8000)
              │ azure-ai-agents SDK
              ▼
          Foundry Orchestrator Agent
              │ ConnectedAgentTool
              ├─ GraphExplorer  → OpenApiTool → ca-graphquery-xxx (internal, port 8100) → Cosmos DB
              ├─ Telemetry      → OpenApiTool → ca-graphquery-xxx → Cosmos DB NoSQL
              ├─ RunbookKB      → AzureAISearchTool → AI Search
              └─ HistoricalTicket → AzureAISearchTool → AI Search
```

---

## Gap Analysis

| # | Gap | Severity | Component |
|---|-----|----------|-----------|
| 1 | No Dockerfile for `api/` | Blocker | api |
| 2 | No Dockerfile for `frontend/` | Blocker | frontend |
| 3 | `azure.yaml` only has `graph-query-api` service | Blocker | config |
| 4 | `main.bicep` only deploys one Container App | Blocker | infra |
| 5 | `agent_ids.json` loaded from local filesystem | Blocker | api |
| 6 | CORS_ORIGINS hardcoded to localhost | High | api |
| 7 | No RBAC for api Container App → Foundry | High | infra |
| 8 | Frontend uses relative URLs (need reverse proxy) | Medium | frontend |
| 9 | Bicep outputs don't capture new service URIs | Medium | infra |
| 10 | `graph-query-api` ingress should become internal | Low | infra/security |
| 11 | `postprovision.sh` doesn't write new outputs | Low | hooks |

---

## Implementation Plan

### Phase 1: Dockerfiles & Build Config

#### 1.1 Create `api/Dockerfile`

```dockerfile
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Install deps first (cache layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY app/ ./app/

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Key decisions:**
- No `azure_config.env` baked in — all config via Container App env vars
- `agent_ids.json` NOT in the image — see Phase 3 for the solution
- `load_dotenv()` calls in main.py/orchestrator.py are no-ops when env vars
  are already set (Container App injects them)

#### 1.2 Create `frontend/Dockerfile`

Multi-stage build: Node for `npm run build`, then nginx to serve static + proxy.

```dockerfile
# Stage 1 — Build
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2 — Serve
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

#### 1.3 Create `frontend/nginx.conf`

Serves static assets and reverse-proxies `/api/*` and `/health` to the api
Container App's **internal FQDN** (injected at deploy time via envsubst).

```nginx
server {
    listen 80;
    server_name _;

    # Static SPA assets
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # Reverse proxy to api Container App (internal FQDN)
    location /api/ {
        proxy_pass ${API_BACKEND_URL};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support — disable buffering
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        chunked_transfer_encoding on;
    }

    location /health {
        proxy_pass ${API_BACKEND_URL};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

**Important:** The `API_BACKEND_URL` must be resolved at container start time.
Update the Dockerfile CMD to use `envsubst`:

```dockerfile
CMD ["/bin/sh", "-c", "envsubst '${API_BACKEND_URL}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
```

And rename `nginx.conf` → `nginx.conf.template` in the COPY step.

**Why reverse proxy instead of CORS?**
- No frontend code changes (all relative paths work as-is)
- No CORS complexity between frontend and api
- Single external URL for users
- SSE works seamlessly through nginx

---

### Phase 2: Infrastructure (Bicep)

#### 2.1 Add two Container App modules to `main.bicep`

```bicep
// ---------------------------------------------------------------------------
// API Container App (FastAPI backend — orchestrator bridge)
// ---------------------------------------------------------------------------

module apiService 'modules/container-app.bicep' = {
  scope: rg
  params: {
    name: 'ca-api-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'api' })
    containerAppsEnvironmentId: containerAppsEnv.outputs.id
    containerRegistryName: containerAppsEnv.outputs.registryName
    targetPort: 8000
    externalIngress: false   // Internal only — frontend proxies to it
    minReplicas: 1
    maxReplicas: 3
    cpu: '0.5'
    memory: '1Gi'
    env: [
      { name: 'PROJECT_ENDPOINT', value: aiFoundry.outputs.foundryEndpoint }
      { name: 'AI_FOUNDRY_PROJECT_NAME', value: aiFoundry.outputs.projectName }
      { name: 'MODEL_DEPLOYMENT_NAME', value: 'gpt-4.1' }
      { name: 'CORS_ORIGINS', value: '*' }  // Behind nginx proxy, not directly exposed
    ]
  }
}

// ---------------------------------------------------------------------------
// Frontend Container App (nginx — static SPA + reverse proxy to api)
// ---------------------------------------------------------------------------

module frontend 'modules/container-app.bicep' = {
  scope: rg
  params: {
    name: 'ca-frontend-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'frontend' })
    containerAppsEnvironmentId: containerAppsEnv.outputs.id
    containerRegistryName: containerAppsEnv.outputs.registryName
    targetPort: 80
    externalIngress: true   // Public — this is the user-facing entry point
    minReplicas: 1
    maxReplicas: 2
    cpu: '0.25'
    memory: '0.5Gi'
    env: [
      { name: 'API_BACKEND_URL', value: 'http://ca-api-${resourceToken}' }
      // ^ Internal FQDN within the same Container Apps Environment
    ]
  }
}
```

**Ingress topology:**

| Service | External? | Why |
|---------|-----------|-----|
| `frontend` | Yes | User-facing — browser connects here |
| `api` | No (internal) | Only frontend nginx proxies to it |
| `graph-query-api` | Yes → **No (internal)** | Only Foundry OpenApiTool calls it. **But**: Foundry agents call from outside the VNet, so this must stay **external** unless using Foundry VNet injection. Keep external for now. |

**Note on `graph-query-api` ingress:** Foundry's Agent Service makes OpenApiTool
calls from Azure-managed infrastructure, not from within your VNet. The Container
App must remain externally accessible for Foundry to reach it. To lock it down,
consider API key auth or managed identity token validation on the endpoint.

#### 2.2 Frontend `API_BACKEND_URL` resolution

Within the same Container Apps Environment, services can reach each other via their
**internal FQDN**: `<app-name>.<environment-default-domain>`. However, the exact
domain suffix is dynamic.

Better approach: use the Container App's **internal URL** output from Bicep. The
Container Apps Environment creates an internal domain automatically. For internal-
ingress apps, the FQDN format is:
`<app-name>.internal.<env-unique-id>.<region>.azurecontainerapps.io`

The cleanest solution is to use the `apiService.outputs.fqdn` as a dependency:

```bicep
module frontend 'modules/container-app.bicep' = {
  // ...
  params: {
    env: [
      { name: 'API_BACKEND_URL', value: 'https://${apiService.outputs.fqdn}' }
    ]
  }
}
```

This creates an implicit dependency — `frontend` deploys after `api`, which is
correct behaviour since the frontend needs to know the api's FQDN.

#### 2.3 Update `roles.bicep` for api Container App

The api service needs to invoke Foundry agents via `DefaultAzureCredential`. Add:

```bicep
@description('Principal ID of the API Container App managed identity (for Foundry agent access)')
param apiContainerAppPrincipalId string = ''

// API Container App MI → Cognitive Services OpenAI User (invoke agents)
resource apiOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(apiContainerAppPrincipalId)) {
  name: guid(foundry.id, apiContainerAppPrincipalId, roles.cognitiveServicesOpenAiUser)
  scope: foundry
  properties: {
    principalId: apiContainerAppPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAiUser)
    principalType: 'ServicePrincipal'
  }
}

// API Container App MI → Cognitive Services Contributor (create threads, manage runs)
resource apiCognitiveServicesContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(apiContainerAppPrincipalId)) {
  name: guid(foundry.id, apiContainerAppPrincipalId, roles.cognitiveServicesContributor)
  scope: foundry
  properties: {
    principalId: apiContainerAppPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesContributor)
    principalType: 'ServicePrincipal'
  }
}
```

Wire it in `main.bicep`:

```bicep
module roles 'modules/roles.bicep' = {
  // ... existing params ...
  params: {
    apiContainerAppPrincipalId: apiService.outputs.principalId   // NEW
    // ... rest unchanged ...
  }
}
```

#### 2.4 Add Bicep outputs for new services

```bicep
output API_URI string = apiService.outputs.uri
output API_PRINCIPAL_ID string = apiService.outputs.principalId
output FRONTEND_URI string = frontend.outputs.uri
```

#### 2.5 Update `postprovision.sh`

Add the new outputs to azure_config.env:

```bash
AZD_API_URI="${API_URI:-}"
AZD_FRONTEND_URI="${FRONTEND_URI:-}"

# ... in the config writing section:
API_URI=${AZD_API_URI}
FRONTEND_URI=${AZD_FRONTEND_URI}
```

---

### Phase 3: `agent_ids.json` — Container-Compatible Loading

The current `orchestrator.py` reads `scripts/agent_ids.json` from the local
filesystem. This file won't exist inside the api container.

**Three options (ranked):**

#### Option A: Bake into Docker image at deploy time (Simplest) ✅ RECOMMENDED

After agents are provisioned, copy `agent_ids.json` into the api image. This means
the agent provisioning step must happen **before** `azd deploy api`.

Add to `api/Dockerfile`:
```dockerfile
COPY scripts/agent_ids.json /app/agent_ids.json
```

Update `orchestrator.py` to check an env var first:
```python
AGENT_IDS_FILE = Path(os.getenv(
    "AGENT_IDS_PATH",
    str(PROJECT_ROOT / "scripts" / "agent_ids.json")
))
```

Set `AGENT_IDS_PATH=/app/agent_ids.json` in the Container App env.

**Trade-off:** Re-provisioning agents requires `azd deploy api` to rebuild the
image. Acceptable for this project since agents rarely change.

#### Option B: Upload to blob, fetch at startup (More Flexible)

`postprovision.sh` uploads `agent_ids.json` to blob storage.
`orchestrator.py` fetches it once at startup via `BlobClient`.

More moving parts but decouples agent provisioning from container deployment.

#### Option C: Query Foundry API for agent IDs at startup (Most Robust)

Use the Foundry SDK to list agents matching known names. No file dependency.
Most resilient but adds startup latency and requires agent names to be stable.

**Decision: Go with Option A** for simplicity. The deploy.sh already runs agent
provisioning after infrastructure, so the sequence is natural:
1. `azd up` → provisions infra + deploys initial placeholder containers
2. `provision_agents.py` → creates `agent_ids.json`
3. `azd deploy api` → rebuild with `agent_ids.json` baked in

---

### Phase 4: `azure.yaml` Service Registration

```yaml
services:
  api:
    project: ./api
    language: python
    host: containerapp
    docker:
      path: ./Dockerfile
      context: ..     # Parent dir so we can COPY scripts/agent_ids.json
      remoteBuild: true

  graph-query-api:
    project: ./graph-query-api
    language: python
    host: containerapp
    docker:
      path: ./Dockerfile
      context: .
      remoteBuild: true

  frontend:
    project: ./frontend
    language: js
    host: containerapp
    docker:
      path: ./Dockerfile
      context: .
      remoteBuild: true
```

**Note on api context:** set to `..` (project root) so the Dockerfile can
`COPY scripts/agent_ids.json`. The Dockerfile paths adjust accordingly.

---

### Phase 5: Security Hardening

#### 5.1 Lock down `graph-query-api`

Currently external with no auth. Options:

1. **API key header** — Add a shared secret env var checked in middleware.
   Configure the same secret in the agent's OpenApiTool auth config.
2. **Managed identity token validation** — Validate the Bearer token is from
   the Foundry service principal. More complex but zero-secret.
3. **Accept the risk** — For a demo, the Container App URL is obscure and
   auto-generated. Low risk but not production-grade.

**Recommendation for this project:** Option 1 (API key) — low effort, effective.

#### 5.2 Cosmos DB: disable public access in production

Once everything runs through Container Apps + private endpoints, toggle:

```bicep
publicNetworkAccess: 'Disabled'
```

This closes the public endpoint entirely. All traffic goes through private
endpoints on the VNet. The `devIpAddress` parameter we added becomes irrelevant
in production (leave `DEV_IP_ADDRESS` empty).

#### 5.3 Container App scaling

| Service | Min | Max | CPU | Memory | Rationale |
|---------|-----|-----|-----|--------|-----------|
| `api` | 1 | 3 | 0.5 | 1Gi | SSE streaming + agent SDK are memory-intensive |
| `graph-query-api` | 1 | 2 | 0.25 | 0.5Gi | Lightweight proxy, Gremlin client is connection-pooled |
| `frontend` | 1 | 2 | 0.25 | 0.5Gi | Static file serving, minimal compute |

---

### Phase 6: Deploy Script Updates

Update `deploy.sh` to orchestrate the full pipeline:

```
Step 3: azd up
   → Provisions infra (3 Container Apps + all Azure services)
   → Deploys placeholder containers for api + frontend
   → postprovision uploads data

Step 4: Create search indexes (unchanged)

Step 5: Load Cosmos DB data (unchanged)

Step 6: Verify graph-query-api health (unchanged)

Step 7: Provision agents → agent_ids.json

Step 8 (NEW): Rebuild & deploy api with agent_ids.json
   → azd deploy api

Step 9 (UPDATED): Verify all services
   → Curl frontend FQDN
   → Curl api /health via frontend proxy

Step 10: Remove --skip-local (no longer needed)
   → Print the frontend URL instead
```

---

## Implementation Order

| Step | Action | Files Changed | Estimated Time |
|------|--------|---------------|----------------|
| 1 | Create `api/Dockerfile` | New file | 5 min |
| 2 | Create `frontend/Dockerfile` + `frontend/nginx.conf.template` | 2 new files | 15 min |
| 3 | Update `orchestrator.py` — env var for agent_ids path | 1 file | 5 min |
| 4 | Update `azure.yaml` — add api + frontend services | 1 file | 5 min |
| 5 | Update `main.bicep` — add api + frontend Container Apps | 1 file | 15 min |
| 6 | Update `roles.bicep` — add api MI → Foundry RBAC | 1 file | 10 min |
| 7 | Update `main.bicep` — add outputs | 1 file | 5 min |
| 8 | Update `postprovision.sh` — capture new outputs | 1 file | 10 min |
| 9 | Update `deploy.sh` — add step 8 (redeploy api) | 1 file | 15 min |
| 10 | Bicep build & validate | — | 5 min |
| 11 | Test: `azd up` from clean environment | — | 15-20 min |
| 12 | Test: full pipeline via `deploy.sh --yes` | — | 20-30 min |

**Total estimated effort: ~2-3 hours**

---

## Deployment Command (Target State)

```bash
# Full deployment from scratch
./deploy.sh --yes --location swedencentral

# Or step by step:
azd up                                          # Infra + placeholder containers
source azure_config.env
uv run python scripts/create_runbook_indexer.py  # Search indexes
uv run python scripts/create_tickets_indexer.py
uv run python scripts/cosmos/provision_cosmos_gremlin.py   # Graph data
uv run python scripts/cosmos/provision_cosmos_telemetry.py  # Telemetry data
uv run python scripts/provision_agents.py --force           # Agents → agent_ids.json
azd deploy api                                   # Rebuild with agent_ids.json

# Open the app
echo "Open: $(azd env get-values | grep FRONTEND_URI)"
```

---

## Rollback Plan

If anything fails during the full deployment:

- `azd down --force --purge` — tears down everything
- The current local-dev workflow continues to work unchanged (Vite proxy + uvicorn)
- All Bicep changes are additive — existing `graph-query-api` deployment is untouched

---

## Out of Scope (Future)

- Custom domain + TLS certificate (Azure Front Door or Container Apps custom domain)
- CI/CD pipeline (GitHub Actions with `azd pipeline config`)
- Blue/green deployments with Container App revisions
- Application Insights SDK integration (distributed tracing)
- Rate limiting / WAF on the frontend
- Key Vault for Cosmos DB Gremlin key (currently passed as Container App secret)
