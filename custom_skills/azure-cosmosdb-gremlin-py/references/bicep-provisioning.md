# Bicep Provisioning — Azure Cosmos DB for Apache Gremlin

Bicep modules for deploying an Azure Cosmos DB account with the Gremlin API,
a Gremlin database, and a graph (container) with partition key configuration.

---

## Module: Cosmos DB Gremlin Account

```bicep
// infra/modules/cosmos-gremlin.bicep

@description('Name of the Cosmos DB account')
param accountName string

@description('Azure region for the account')
param location string = resourceGroup().location

@description('Name of the Gremlin database')
param databaseName string = 'networkgraph'

@description('Name of the Gremlin graph')
param graphName string = 'topology'

@description('Partition key path for the graph')
param partitionKeyPath string = '/partitionKey'

@description('Maximum throughput for autoscale (RU/s)')
param maxThroughput int = 1000

@description('Tags to apply to all resources')
param tags object = {}

// ─── Cosmos DB Account with Gremlin capability ───────────────────────────────

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      { name: 'EnableGremlin' }
    ]
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    enableAutomaticFailover: false
    enableMultipleWriteLocations: false
    publicNetworkAccess: 'Enabled'
  }
}

// ─── Gremlin Database ────────────────────────────────────────────────────────

resource database 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2024-11-15' = {
  name: databaseName
  parent: cosmosAccount
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// ─── Gremlin Graph (Container) ───────────────────────────────────────────────

resource graph 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs@2024-11-15' = {
  name: graphName
  parent: database
  properties: {
    resource: {
      id: graphName
      partitionKey: {
        paths: [partitionKeyPath]
        kind: 'Hash'
        version: 2
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          { path: '/*' }
        ]
        excludedPaths: [
          { path: '/"_etag"/?' }
        ]
      }
    }
    options: {
      autoscaleSettings: {
        maxThroughput: maxThroughput
      }
    }
  }
}

// ─── Outputs ─────────────────────────────────────────────────────────────────

@description('The Gremlin endpoint hostname (without protocol)')
output gremlinEndpoint string = '${cosmosAccount.name}.gremlin.cosmos.azure.com'

@description('The Cosmos DB account name')
output cosmosAccountName string = cosmosAccount.name

@description('The Gremlin database name')
output gremlinDatabaseName string = database.name

@description('The Gremlin graph name')
output gremlinGraphName string = graph.name

@description('The Cosmos DB account resource ID')
output cosmosAccountId string = cosmosAccount.id
```

---

## Usage in main.bicep

```bicep
// infra/main.bicep

param cosmosGremlinAccountName string = 'cosmos-gremlin-${uniqueString(resourceGroup().id)}'

module cosmosGremlin 'modules/cosmos-gremlin.bicep' = {
  name: 'cosmos-gremlin'
  params: {
    accountName: cosmosGremlinAccountName
    location: location
    databaseName: 'networkgraph'
    graphName: 'topology'
    partitionKeyPath: '/partitionKey'
    maxThroughput: 1000
    tags: {
      project: 'autonomous-network-demo'
      environment: 'dev'
    }
  }
}

// Pass outputs to Container App as environment variables
module api 'modules/api.bicep' = {
  name: 'api'
  params: {
    // ... existing params
    cosmosGremlinEndpoint: cosmosGremlin.outputs.gremlinEndpoint
    cosmosGremlinDatabase: cosmosGremlin.outputs.gremlinDatabaseName
    cosmosGremlinGraph: cosmosGremlin.outputs.gremlinGraphName
  }
}
```

---

## Retrieving the Primary Key

The Cosmos DB account primary key must be retrieved post-deployment (it cannot be
output from Bicep for security reasons). Use `az CLI` or a post-provision hook:

```bash
#!/bin/bash
# hooks/postprovision.sh (append)

# Get Cosmos DB Gremlin primary key
COSMOS_ACCOUNT_NAME=$(az cosmosdb list \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "[?contains(name, 'gremlin')].name | [0]" -o tsv)

COSMOS_GREMLIN_PRIMARY_KEY=$(az cosmosdb keys list \
  --name "$COSMOS_ACCOUNT_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --type keys \
  --query "primaryMasterKey" -o tsv)

# Store in Key Vault (recommended)
az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name "cosmos-gremlin-key" \
  --value "$COSMOS_GREMLIN_PRIMARY_KEY"

# Or write to env file (dev only)
echo "COSMOS_GREMLIN_PRIMARY_KEY=$COSMOS_GREMLIN_PRIMARY_KEY" >> azure_config.env
```

---

## Azure CLI Alternative Provisioning

For quick setup without Bicep:

```bash
# 1. Create account with Gremlin capability
az cosmosdb create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACCOUNT_NAME" \
  --locations "regionName=$LOCATION" \
  --capabilities "EnableGremlin"

# 2. Create Gremlin database
az cosmosdb gremlin database create \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$ACCOUNT_NAME" \
  --name "networkgraph"

# 3. Create graph with partition key
az cosmosdb gremlin graph create \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$ACCOUNT_NAME" \
  --database-name "networkgraph" \
  --name "topology" \
  --partition-key-path "/partitionKey" \
  --max-throughput 1000

# 4. Get connection info
az cosmosdb show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACCOUNT_NAME" \
  --query "{endpoint: name, host: documentEndpoint}"

az cosmosdb keys list \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACCOUNT_NAME" \
  --type keys
```

---

## Container App Environment Variables

When deploying the API Container App, inject these environment variables:

```bicep
// In the Container App module
env: [
  { name: 'COSMOS_GREMLIN_ENDPOINT', value: cosmosGremlinEndpoint }
  { name: 'COSMOS_GREMLIN_DATABASE', value: 'networkgraph' }
  { name: 'COSMOS_GREMLIN_GRAPH', value: 'topology' }
  {
    name: 'COSMOS_GREMLIN_PRIMARY_KEY'
    secretRef: 'cosmos-gremlin-key'   // from Key Vault
  }
]
```

---

## ARM Template Reference

Official Bicep resource definitions from
[Microsoft.DocumentDB databaseAccounts/gremlinDatabases](https://learn.microsoft.com/en-us/azure/templates/microsoft.documentdb/databaseaccounts/gremlindatabases?pivots=deployment-language-bicep).

### Latest API Version

The latest stable API version is `2024-11-15`. Preview: `2025-11-01-preview`.
Always pin to stable for production. The module above uses `2024-11-15`.

### Full Resource Format (gremlinDatabases)

```bicep
resource symbolicname 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2024-11-15' = {
  parent: resourceSymbolicName
  name: 'string'
  tags: { /* key: 'value' */ }
  location: 'string'
  identity: {
    type: 'None' | 'SystemAssigned' | 'UserAssigned' | 'SystemAssigned,UserAssigned'
    userAssignedIdentities: {
      '/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{name}': {}
    }
  }
  properties: {
    resource: {
      id: 'string'                    // Required — database name
      createMode: 'Default'           // 'Default' or 'Restore'
      restoreParameters: {
        restoreSource: 'string'       // Restorable account ID
        restoreTimestampInUtc: 'string'  // ISO-8601
        restoreWithTtlDisabled: false
      }
    }
    options: {
      throughput: int                 // Fixed RU/s (mutually exclusive with autoscale)
      autoscaleSettings: {
        maxThroughput: int            // e.g. 1000
      }
    }
  }
}
```

### Key Property Reference

| Property | Type | Description |
|----------|------|-------------|
| `resource.id` | string (required) | Name of the Gremlin database |
| `resource.createMode` | `'Default'` \| `'Restore'` | Default = new, Restore = from backup |
| `resource.restoreParameters` | object | Only for `createMode: 'Restore'` |
| `options.throughput` | int | Fixed RU/s (mutually exclusive with autoscale) |
| `options.autoscaleSettings.maxThroughput` | int | Max RU/s for autoscale |
| `identity.type` | string | Managed identity type for the resource |

### Account-Level Properties Worth Knowing

These go on the `databaseAccounts` resource (not the database):

```bicep
properties: {
  // ... existing properties ...
  enableFreeTier: false              // Only 1 free-tier account per subscription
  enableAnalyticalStorage: false     // Analytical store (HTAP) — not used for Gremlin demo
  disableLocalAuth: false            // Set true to force Entra-only (NoSQL only, N/A for Gremlin wire)
  disableKeyBasedMetadataWriteAccess: false  // Prevent key-based control plane ops
  defaultIdentity: 'FirstPartyIdentity'     // Identity for CMK encryption
}
```

### Azure Quickstart Templates

Pre-built Bicep/ARM templates from Microsoft:

| Template | Description |
|----------|-------------|
| [Cosmos DB Gremlin — dedicated throughput](https://aka.ms/azqst) | Account + database + graph with fixed RU/s, 2 regions |
| [Cosmos DB Gremlin — autoscale](https://aka.ms/azqst) | Account + database + graph with autoscale RU/s, 2 regions |

> These are available via `az deployment group create` or the Azure Portal
> "Deploy a custom template" → "Quickstart templates" search.

---

## Cost Considerations

| Configuration | Estimated Monthly Cost | Notes |
|---------------|----------------------|-------|
| Serverless | ~$0-5/mo for demo | Pay per RU consumed, ideal for low-traffic |
| Autoscale 1000 RU/s | ~$58/mo | Scales 100-1000 RU/s automatically |
| Provisioned 400 RU/s | ~$23/mo | Fixed throughput, lowest provisioned |

**Recommendation for demo**: Use autoscale with `maxThroughput: 1000` RU/s.
This handles burst loads during demo sessions and scales down when idle.

For serverless (even cheaper, no minimum):

```bicep
// Replace the options block in the graph resource
options: {}  // Remove autoscaleSettings entirely

// Add serverless capability to the account
capabilities: [
  { name: 'EnableGremlin' }
  { name: 'EnableServerless' }
]
```

---

## Security Hardening (Production)

For production deployments, add:

```bicep
// Private endpoint (no public access)
resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: '${accountName}-pe'
  location: location
  properties: {
    subnet: { id: subnetId }
    privateLinkServiceConnections: [
      {
        name: '${accountName}-plsc'
        properties: {
          privateLinkServiceId: cosmosAccount.id
          groupIds: ['Gremlin']
        }
      }
    ]
  }
}

// Disable public access
// Set publicNetworkAccess: 'Disabled' in the account properties
```
