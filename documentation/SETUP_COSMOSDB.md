# Cosmos DB Backend Setup

Setup guide for `GRAPH_BACKEND=cosmosdb` — the default and recommended path.

Cosmos DB Gremlin provides a fully managed graph database with automatic indexing,
global distribution, and guaranteed low latency. Infrastructure is provisioned
entirely by `azd up` with no manual steps for the graph database itself.

---

## Prerequisites

- Completed [main Prerequisites](../README.md#prerequisites) (tools, auth)
- `GRAPH_BACKEND=cosmosdb` in `azure_config.env` (this is the default)

---

## Deployment

### 1. Deploy infrastructure

```bash
azd up -e <env-name>
```

This provisions:
- Cosmos DB Gremlin account (`cosmos-gremlin-<token>`)
- Database: `networkgraph`
- Graph container: `topology` (partition key: `/partitionKey`)
- Autoscale throughput: up to 1000 RU/s
- The Cosmos DB primary key is automatically stored as a Container App secret

`postprovision.sh` automatically:
- Writes `COSMOS_GREMLIN_ENDPOINT` to `azure_config.env`
- Fetches the primary key via `az cosmosdb keys list` and writes `COSMOS_GREMLIN_PRIMARY_KEY`

### 2. Load graph data

The graph loader reads `data/graph_schema.yaml` — a declarative manifest that
defines vertex types, edge relationships, and the CSV files that supply the data.

```bash
uv run python scripts/cosmos/provision_cosmos_gremlin.py
```

This loads:
- **8 vertex types:** CoreRouter, AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession
- **7 edge labels** across **11 edge definitions:** connects_to, aggregates_to, backhauls_via, routes_via, depends_on, governed_by, peers_over (some labels have multiple entries for bidirectional or polymorphic relationships)

The loader is idempotent — re-running it drops and recreates all data.

### 3. Set up telemetry (Cosmos DB NoSQL)

The telemetry backend (SQL queries via `/query/telemetry`) uses a Cosmos DB
NoSQL account. Infrastructure is provisioned by `azd up` alongside the Gremlin
graph account.

Load telemetry data:

```bash
uv run python scripts/cosmos/provision_cosmos_telemetry.py
```

`postprovision.sh` automatically writes `COSMOS_NOSQL_ENDPOINT` and
`COSMOS_NOSQL_DATABASE` to `azure_config.env`.

> **Note:** If you don't need telemetry queries, you can skip this step. The
> graph-query-api will start with warnings about missing telemetry env vars but
> the `/query/graph` endpoint will work.

### 4. Update Container App env vars

After loading data and populating config, redeploy to push the env vars:

```bash
azd deploy graph-query-api
```

Or update individual env vars:

```bash
source azure_config.env
az containerapp update --name <ca-name> --resource-group $AZURE_RESOURCE_GROUP \
  --set-env-vars "COSMOS_NOSQL_ENDPOINT=$COSMOS_NOSQL_ENDPOINT" "COSMOS_NOSQL_DATABASE=$COSMOS_NOSQL_DATABASE"
```

### 5. Verify

```bash
uv run python scripts/testing_scripts/test_graph_query_api.py
```

This smoke-tests both `/query/graph` and `/query/telemetry` against the deployed
Container App.

---

## Graph Schema

The graph topology is defined declaratively in `data/graph_schema.yaml`:

```yaml
data_dir: data/network

vertices:
  - label: CoreRouter
    csv_file: DimCoreRouter.csv
    id_column: RouterId
    partition_key: router
    properties: [RouterId, City, Region, Vendor, Model]
  # ... 7 more vertex types

edges:
  - label: CONNECTS_TO
    csv_file: DimTransportLink.csv
    from_label: CoreRouter
    from_column: SourceRouterId
    to_label: CoreRouter
    to_column: TargetRouterId
  # ... 10 more edge types
```

To add new vertex/edge types, edit the YAML manifest and re-run the loader — no
code changes needed.

---

## How It Works

The Cosmos DB backend (`graph-query-api/backends/cosmosdb.py`) uses:

- **gremlinpython >=3.7.0** with `GraphSONSerializersV2d0` (Cosmos DB requirement)
- **Key-based auth** over WSS (WebSocket Secure)
- **Thread-safe singleton** client with `threading.Lock()`
- **Retry with exponential backoff** on `GremlinServerError` and `WSServerHandshakeError`

Incoming Gremlin queries from the GraphExplorer agent are executed directly
against the Cosmos DB Gremlin endpoint. Results are normalized to a
`{columns, data}` format matching the Fabric backend's response shape.

---

## Cost

- **Cosmos DB Gremlin:** Autoscale to 1000 RU/s max (~$0.012/hr at minimum)
- **Container App:** 0.25 vCPU, 0.5 GiB (~$0.012/hr)
- **No Fabric capacity needed** for graph or telemetry (both use Cosmos DB)

---

## Troubleshooting

### "COSMOS_GREMLIN_PRIMARY_KEY not set"

If `postprovision.sh` couldn't auto-fetch the key (e.g. permissions issue):

```bash
# Manually fetch and set
COSMOS_ACCOUNT=$(azd env get-value COSMOS_GREMLIN_ACCOUNT_NAME)
RG=$(azd env get-value AZURE_RESOURCE_GROUP)
az cosmosdb keys list --name $COSMOS_ACCOUNT --resource-group $RG --query primaryMasterKey -o tsv
# Paste the key into azure_config.env as COSMOS_GREMLIN_PRIMARY_KEY=<key>
```

### "WSServerHandshakeError" or connection timeouts

- Verify the Cosmos DB account exists: `az cosmosdb show --name <account> --resource-group <rg>`
- Check the endpoint format: should be `wss://<account>.gremlin.cosmos.azure.com:443/`
- Ensure the primary key is correct (regenerate if needed via Azure portal)

### Empty graph results

- Re-run `uv run python scripts/cosmos/provision_cosmos_gremlin.py`
- Check that CSV files exist in `data/network/`
- Verify in Azure portal → Cosmos DB → Data Explorer that vertices exist
