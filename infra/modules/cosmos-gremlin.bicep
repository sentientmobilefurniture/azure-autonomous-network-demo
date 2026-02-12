// infra/modules/cosmos-gremlin.bicep
// Azure Cosmos DB account with Gremlin API, database, and graph.

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

@description('Developer IP address for firewall exceptions (optional)')
param devIpAddress string = ''

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
    ipRules: empty(devIpAddress) ? [] : [
      { ipAddressOrRange: devIpAddress }
    ]
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

// ─── Cosmos DB NoSQL Account (for telemetry data) ────────────────────────────

var noSqlAccountName = '${accountName}-nosql'
var telemetryDbName = 'telemetry'

resource cosmosNoSqlAccount 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: noSqlAccountName
  location: location
  tags: union(tags, { component: 'telemetry-store' })
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
    ipRules: empty(devIpAddress) ? [] : [
      { ipAddressOrRange: devIpAddress }
    ]
  }
}

resource telemetryDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  name: telemetryDbName
  parent: cosmosNoSqlAccount
  properties: {
    resource: {
      id: telemetryDbName
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

@description('The primary key for key-based Gremlin auth')
output primaryKey string = cosmosAccount.listKeys().primaryMasterKey

@description('The NoSQL account endpoint')
output cosmosNoSqlEndpoint string = cosmosNoSqlAccount.properties.documentEndpoint

@description('The telemetry database name')
output telemetryDatabaseName string = telemetryDatabase.name

@description('The NoSQL account resource ID')
output cosmosNoSqlAccountId string = cosmosNoSqlAccount.id

@description('The NoSQL account name')
output cosmosNoSqlAccountName string = cosmosNoSqlAccount.name
