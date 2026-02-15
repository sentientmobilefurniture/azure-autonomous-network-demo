# Infrastructure, Dockerfile & RBAC

## Infrastructure (Bicep)

### `infra/main.bicep` — Subscription-Scoped

**Scope**: `subscription` (creates resource group named `rg-{environmentName}`)

**Key Parameters**:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `environmentName` | (required) | Prefix for all resources |
| `location` | (required) | Azure region |
| `principalId` | — | User principal for role assignments |
| `gptCapacity` | 300 | In 1K TPM units |
| `graphBackend` | `"cosmosdb"` | `@allowed(['cosmosdb'])` — only `cosmosdb` at Bicep level; `mock` is a runtime-only env var override, never a Bicep parameter |
| `devIpAddress` | — | For local Cosmos firewall rules |

**Modules deployed** (9 total):

| Module | Purpose | Conditional? |
|--------|---------|--------------|
| `vnet` | VNet with infrastructure + private endpoint subnets | No |
| `search` | AI Search service | No |
| `storage` | Storage account (blob containers) | No |
| `cosmosGremlin` | Cosmos DB Gremlin account | If `graphBackend == 'cosmosdb'` |
| `aiFoundry` | AI Foundry hub + project | No |
| `containerAppsEnv` | Container Apps Environment (VNet-integrated) | No |
| `app` | Unified container app (port 80, 1-3 replicas, 1 CPU / 2Gi) | No |
| `roles` | All RBAC role assignments | No |
| `cosmosPrivateEndpoints` | Private endpoints for both Cosmos accounts | If `graphBackend == 'cosmosdb'` |

**CRITICAL**: Cosmos DB uses **TWO separate accounts** — one for Gremlin (graph data), one for NoSQL (telemetry + prompts). The NoSQL account is named `{gremlin-account}-nosql`.

**Env vars passed to Container App** (from Bicep):
```
PROJECT_ENDPOINT, AI_FOUNDRY_PROJECT_NAME, MODEL_DEPLOYMENT_NAME=gpt-4.1,
CORS_ORIGINS=*, AGENT_IDS_PATH=/app/scripts/agent_ids.json, GRAPH_BACKEND,
COSMOS_GREMLIN_ENDPOINT, COSMOS_GREMLIN_DATABASE=networkgraph,
COSMOS_GREMLIN_GRAPH=topology, COSMOS_GREMLIN_PRIMARY_KEY (secret ref),
COSMOS_NOSQL_ENDPOINT, COSMOS_NOSQL_DATABASE,
AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP,
AI_SEARCH_NAME, STORAGE_ACCOUNT_NAME, AI_FOUNDRY_NAME,
EMBEDDING_MODEL=text-embedding-3-small, EMBEDDING_DIMENSIONS=1536
```

**Bicep outputs** (consumed by `postprovision.sh`):
`AZURE_RESOURCE_GROUP`, `APP_URI`, `APP_PRINCIPAL_ID`, `GRAPH_QUERY_API_URI` (= `APP_URI`), `COSMOS_GREMLIN_ENDPOINT`, `COSMOS_NOSQL_ENDPOINT`, etc.

### Resource Naming Convention

Uses deterministic hash token: `toLower(uniqueString(subscription().id, environmentName, location))` — consistent across deployments, globally unique.

### Bicep Patterns

**`readEnvironmentVariable()` for config**: Bicep parameter files can read environment variables, avoiding hardcoded values:
```bicepparam
param cosmosGremlinDatabase = readEnvironmentVariable('COSMOS_GREMLIN_DATABASE', 'networkgraph')
```
Combined with `preprovision.sh` syncing values from `azure_config.env` to `azd env`, this creates a single-source-of-truth config pattern.

**Conditional module deployment**: Use boolean parameters to skip expensive modules during iterative development:
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

## Dockerfile & Container Build

**Multi-stage build (2 stages):**

### Stage 1: Frontend Build
```dockerfile
FROM node:20-alpine AS frontend-build
# npm ci && npm run build → React artifacts in /build/dist
```

### Stage 2: Python + nginx
```dockerfile
FROM python:3.11-slim
# Installs: nginx, supervisor, uv (from ghcr.io/astral-sh/uv:latest)

# IMPORTANT: Both pyproject.toml AND uv.lock files are copied.
# `uv sync --frozen` requires uv.lock to exist.
# If uv.lock is missing, the build fails.

# graph-query-api at /app/graph-query-api
#   uv sync --frozen --no-dev --no-install-project
#   Copies: *.py, backends/, openapi/

# api at /app/api
#   uv sync --frozen --no-dev --no-install-project
#   Copies: app/

# Scripts at /app/scripts
#   Copies: agent_provisioner.py
#   (scenario_loader.py removed in V8 refactor; agent_ids.json created at runtime)

# Data at /app/data/scenarios (YAML only — .md prompts excluded by .dockerignore)

# Frontend static → /usr/share/nginx/html
# ENV AGENT_IDS_PATH=/app/scripts/agent_ids.json
# EXPOSE 80
# CMD: supervisord
```

**Path structure in container**:
```
/app/
├── api/                    # API service
│   ├── app/                # FastAPI app package
│   └── .venv/              # uv-managed virtualenv
├── graph-query-api/        # Query service
│   ├── backends/
│   ├── openapi/
│   └── .venv/
├── scripts/                # Shared scripts
│   ├── agent_provisioner.py
│   └── agent_ids.json      # Written at runtime by provisioning
└── data/scenarios/          # YAML manifests only
```

---

## RBAC Roles (Container App Managed Identity)

| Role | Scope | Purpose |
|------|-------|---------|
| Cognitive Services OpenAI User | Foundry | Invoke GPT models |
| Cognitive Services Contributor | Foundry | Manage agents |
| Azure AI Developer | Resource group | Agent invocation |
| Cognitive Services User | Foundry | Broad data-plane |
| Cosmos DB Built-in Data Contributor | NoSQL account | Query/upsert telemetry + prompts (data plane) |
| DocumentDB Account Contributor | Gremlin account | Create graphs via ARM (management plane) |
| DocumentDB Account Contributor | NoSQL account | Create databases/containers via ARM |
| Storage Blob Data Contributor | Storage account | Upload runbooks/tickets to blob |
| Search Service Contributor | AI Search | Create indexes/indexers |
| Search Index Data Contributor | AI Search | Read/write index data |

All defined in `infra/modules/roles.bicep`.

**Key distinction**: Cosmos DB has **separate RBAC systems** for management plane (ARM roles like `DocumentDB Account Contributor`) vs data plane (`Cosmos DB Built-in Data Contributor` — GUID `00000000-0000-0000-0000-000000000002`). The data contributor role does NOT include database/container creation — that's why upload endpoints use the two-phase ARM + data-plane pattern.
