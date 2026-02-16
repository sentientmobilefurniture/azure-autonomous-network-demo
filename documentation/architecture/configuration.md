# Configuration Reference

All config lives in `azure_config.env`. Key variables:

| Variable | Set by | Used by |
|----------|--------|---------|
| `AZURE_SUBSCRIPTION_ID` | postprovision | ARM calls, agent provisioner |
| `AZURE_RESOURCE_GROUP` | postprovision | ARM calls |
| `PROJECT_ENDPOINT` | postprovision / Bicep | Agent provisioner, orchestrator |
| `AI_FOUNDRY_PROJECT_NAME` | postprovision / Bicep | Agent provisioner, orchestrator |
| `AI_FOUNDRY_NAME` | postprovision / Bicep | Search connection ID |
| `MODEL_DEPLOYMENT_NAME` | user (default: gpt-4.1) | Agent model |
| `GRAPH_BACKEND` | user (default: cosmosdb) | Backend selector (cosmosdb / mock) |
| `COSMOS_GREMLIN_ENDPOINT` | postprovision | Gremlin WSS connection |
| `COSMOS_GREMLIN_PRIMARY_KEY` | postprovision (`az cosmosdb keys list`) | Gremlin key auth |
| `COSMOS_GREMLIN_DATABASE` | Bicep (default: networkgraph) | Gremlin db (shared across scenarios) |
| `COSMOS_NOSQL_ENDPOINT` | postprovision (from `{account}-nosql`) | Telemetry + prompts |
| `COSMOS_NOSQL_DATABASE` | Bicep (default: telemetry) | Shared telemetry db |
| `AI_SEARCH_NAME` | Bicep | Search indexer, index listing |
| `STORAGE_ACCOUNT_NAME` | Bicep | Blob upload |
| `APP_URI` / `GRAPH_QUERY_API_URI` | postprovision | Agent OpenAPI tool base URL |
| `EMBEDDING_MODEL` | Bicep (default: text-embedding-3-small) | Search vectorizer |
| `EMBEDDING_DIMENSIONS` | Bicep (default: 1536) | Vector field dimensions |
| `CORS_ORIGINS` | Bicep (default: *) / user (local: http://localhost:5173) | CORS allowed origins (unified in V8 refactor — both services use `allow_credentials=True`) |
| `AGENT_IDS_PATH` | Bicep (default: /app/scripts/agent_ids.json) | Path to provisioned agent IDs |
| `CONTAINER_APP_HOSTNAME` | runtime (auto-set by Azure) | Fallback for `GRAPH_QUERY_API_URI` |
| `AI_FOUNDRY_ENDPOINT` | postprovision | AI Foundry hub endpoint (separate from PROJECT_ENDPOINT) |
| `GRAPH_QUERY_API_PRINCIPAL_ID` | postprovision | Managed identity principal for RBAC |

### Removed Variables (V10)

The following variables were present in earlier versions but have been removed
from `azure_config.env.template`. They are no longer needed because graph name,
index names, and scenario loading are now config-driven from `scenario.yaml`:

| Variable | Previously | Reason Removed |
|----------|-----------|----------------|
| `COSMOS_GREMLIN_GRAPH` | Bicep (default: topology) | Graph name comes from `data_sources.graph.config.graph` in scenario.yaml |
| `DEFAULT_SCENARIO` | user (default: telco-noc) | Scenarios loaded via UI, not CLI |
| `LOADED_SCENARIOS` | user (default: telco-noc) | Scenarios loaded via UI, not CLI |
| `RUNBOOKS_INDEX_NAME` | user (default: runbooks-index) | Index name comes from `data_sources.search_indexes.runbooks.index_name` in scenario.yaml |
| `TICKETS_INDEX_NAME` | user (default: tickets-index) | Index name comes from `data_sources.search_indexes.tickets.index_name` in scenario.yaml |
| `RUNBOOKS_CONTAINER_NAME` | user (default: runbooks) | Blob container comes from `data_sources.search_indexes.runbooks.blob_container` in scenario.yaml |
| `TICKETS_CONTAINER_NAME` | user (default: tickets) | Blob container comes from `data_sources.search_indexes.tickets.blob_container` in scenario.yaml |

## Local Development

```bash
# Terminal 1: graph-query-api
cd graph-query-api && source ../azure_config.env && GRAPH_BACKEND=mock uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload

# Terminal 2: API
cd api && source ../azure_config.env && uv run uvicorn app.main:app --reload --port 8000

# Terminal 3: Frontend (auto-proxies /api→:8000, /query→:8100)
cd frontend && npm run dev
```
