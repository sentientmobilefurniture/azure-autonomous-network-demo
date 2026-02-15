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
| `COSMOS_GREMLIN_GRAPH` | Bicep (default: topology) | Fallback graph if no X-Graph header |
| `COSMOS_NOSQL_ENDPOINT` | postprovision (from `{account}-nosql`) | Telemetry + prompts |
| `COSMOS_NOSQL_DATABASE` | Bicep (default: telemetry) | Fallback telemetry db |
| `AI_SEARCH_NAME` | Bicep | Search indexer, index listing |
| `STORAGE_ACCOUNT_NAME` | Bicep | Blob upload |
| `APP_URI` / `GRAPH_QUERY_API_URI` | postprovision | Agent OpenAPI tool base URL |
| `EMBEDDING_MODEL` | Bicep (default: text-embedding-3-small) | Search vectorizer |
| `EMBEDDING_DIMENSIONS` | Bicep (default: 1536) | Vector field dimensions |
| `CORS_ORIGINS` | Bicep (default: *) / user (local: http://localhost:5173) | CORS allowed origins (unified in V8 refactor — both services use `allow_credentials=True`) |
| `AGENT_IDS_PATH` | Bicep (default: /app/scripts/agent_ids.json) | Path to provisioned agent IDs |
| `CONTAINER_APP_HOSTNAME` | runtime (auto-set by Azure) | Fallback for `GRAPH_QUERY_API_URI` |
| `DEFAULT_SCENARIO` | user (default: telco-noc) | Vestigial — in template but not consumed by runtime |
| `LOADED_SCENARIOS` | user (default: telco-noc) | Vestigial — in template but not consumed by runtime |
| `RUNBOOKS_INDEX_NAME` | user (default: runbooks-index) | In template but not consumed by graph-query-api runtime |
| `TICKETS_INDEX_NAME` | user (default: tickets-index) | In template but not consumed by graph-query-api runtime |
| `RUNBOOKS_CONTAINER_NAME` | user (default: runbooks) | In template but not consumed by graph-query-api runtime |
| `TICKETS_CONTAINER_NAME` | user (default: tickets) | In template but not consumed by graph-query-api runtime |
| `AI_FOUNDRY_ENDPOINT` | postprovision | AI Foundry hub endpoint (separate from PROJECT_ENDPOINT) |
| `GRAPH_QUERY_API_PRINCIPAL_ID` | postprovision | Managed identity principal for RBAC |

## Local Development

```bash
# Terminal 1: graph-query-api
cd graph-query-api && source ../azure_config.env && GRAPH_BACKEND=mock uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload

# Terminal 2: API
cd api && source ../azure_config.env && uv run uvicorn app.main:app --reload --port 8000

# Terminal 3: Frontend (auto-proxies /api→:8000, /query→:8100)
cd frontend && npm run dev
```
