// infra/modules/cosmos-gremlin.bicep
// Azure Cosmos DB account with Gremlin API (graph) and NoSQL API (telemetry).

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

@description('Name of the NoSQL database for telemetry')
param telemetryDatabaseName string = 'telemetrydb'

@description('Maximum throughput for autoscale on telemetry containers (RU/s)')
param telemetryMaxThroughput int = 1000

@description('Tags to apply to all resources')
param tags object = {}

// ─── Cosmos DB Account with Gremlin capability ───────────────────────────────
// NOTE: An account with EnableGremlin can also host NoSQL (SQL API) databases.

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

// ─── Separate Cosmos DB Account for NoSQL / SQL API (telemetry) ──────────────
// A Gremlin-enabled account does NOT support SQL API requests, so we need
// a dedicated NoSQL account for telemetry data.

resource cosmosNoSqlAccount 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: '${accountName}-nosql'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
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

// ─── NoSQL Database (telemetry) ──────────────────────────────────────────────

resource telemetryDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  name: telemetryDatabaseName
  parent: cosmosNoSqlAccount
  properties: {
    resource: {
      id: telemetryDatabaseName
    }
  }
}

// ─── NoSQL Container: AlertStream ────────────────────────────────────────────

resource alertStreamContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  name: 'AlertStream'
  parent: telemetryDatabase
  properties: {
    resource: {
      id: 'AlertStream'
      partitionKey: {
        paths: ['/SourceNodeType']
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
        maxThroughput: telemetryMaxThroughput
      }
    }
  }
}

// ─── NoSQL Container: LinkTelemetry ──────────────────────────────────────────

resource linkTelemetryContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  name: 'LinkTelemetry'
  parent: telemetryDatabase
  properties: {
    resource: {
      id: 'LinkTelemetry'
      partitionKey: {
        paths: ['/LinkId']
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
        maxThroughput: telemetryMaxThroughput
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

// NOTE: Gremlin wire protocol requires key-based auth (no AAD/MI support).
// Key must pass to container-app.bicep as a secret. For production, use Key Vault.
#disable-next-line outputs-should-not-contain-secrets
@description('The primary key for key-based Gremlin auth')
output primaryKey string = cosmosAccount.listKeys().primaryMasterKey

@description('The Cosmos DB NoSQL endpoint (https://<account>.documents.azure.com:443/)')
output cosmosNoSqlEndpoint string = cosmosNoSqlAccount.properties.documentEndpoint

@description('The NoSQL telemetry database name')
output telemetryDatabaseName string = telemetryDatabase.name
