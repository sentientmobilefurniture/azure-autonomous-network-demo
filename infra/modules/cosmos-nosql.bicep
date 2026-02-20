// infra/modules/cosmos-nosql.bicep
// Azure Cosmos DB NoSQL account — interactions database only.

@description('Name of the Cosmos DB NoSQL account')
param accountName string

@description('Azure region for the account')
param location string = resourceGroup().location

@description('Tags to apply to all resources')
param tags object = {}

@description('Developer IP address for firewall exceptions (optional)')
param devIpAddress string = ''

// ─── Cosmos DB NoSQL Account ─────────────────────────────────────────────────

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: accountName
  location: location
  tags: union(tags, { component: 'interactions-store' })
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

// ─── Interactions Database + Container ───────────────────────────────────────

resource interactionsDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  name: 'interactions'
  parent: cosmosAccount
  properties: {
    resource: {
      id: 'interactions'
    }
  }
}

resource interactionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  name: 'interactions'
  parent: interactionsDatabase
  properties: {
    resource: {
      id: 'interactions'
      partitionKey: {
        paths: ['/scenario']
        kind: 'Hash'
        version: 2
      }
      indexingPolicy: {
        compositeIndexes: [
          [
            { path: '/scenario', order: 'ascending' }
            { path: '/created_at', order: 'descending' }
          ]
        ]
      }
      defaultTtl: 7776000 // 90 days in seconds
    }
    options: {
      autoscaleSettings: {
        maxThroughput: 1000
      }
    }
  }
}

// ─── Outputs ─────────────────────────────────────────────────────────────────

@description('The Cosmos DB NoSQL endpoint')
output cosmosNoSqlEndpoint string = cosmosAccount.properties.documentEndpoint

@description('The Cosmos DB account resource ID')
output cosmosAccountId string = cosmosAccount.id

@description('The Cosmos DB account name')
output cosmosAccountName string = cosmosAccount.name

@description('The interactions database name')
output interactionsDatabaseName string = interactionsDatabase.name
