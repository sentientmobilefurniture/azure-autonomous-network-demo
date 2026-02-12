// ============================================================================
// Cosmos DB Private Endpoints + Private DNS Zones
//
// Creates private endpoints for both Cosmos DB accounts (Gremlin + NoSQL)
// and links them to Private DNS zones so the Container App resolves
// Cosmos hostnames to VNet-internal IPs.
//
// This makes the Container App immune to Azure Policy toggling
// publicNetworkAccess — traffic flows over the VNet backbone regardless.
// ============================================================================

@description('Azure region for the private endpoints')
param location string

@description('Resource tags')
param tags object = {}

@description('Resource ID of the VNet')
param vnetId string

@description('Resource ID of the subnet for private endpoints')
param privateEndpointsSubnetId string

@description('Resource ID of the Cosmos DB Gremlin account')
param cosmosGremlinAccountId string

@description('Name of the Cosmos DB Gremlin account')
param cosmosGremlinAccountName string

@description('Resource ID of the Cosmos DB NoSQL account')
param cosmosNoSqlAccountId string

@description('Name of the Cosmos DB NoSQL account')
param cosmosNoSqlAccountName string

// ─── Private DNS Zone: Gremlin ───────────────────────────────────────────────

resource gremlinDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.gremlin.cosmos.azure.com'
  location: 'global'
  tags: tags
}

resource gremlinDnsVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: gremlinDnsZone
  name: '${cosmosGremlinAccountName}-vnet-link'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

resource gremlinPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${cosmosGremlinAccountName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointsSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'cosmos-gremlin'
        properties: {
          privateLinkServiceId: cosmosGremlinAccountId
          groupIds: ['Gremlin']
        }
      }
    ]
  }
}

resource gremlinDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: gremlinPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'gremlin-config'
        properties: {
          privateDnsZoneId: gremlinDnsZone.id
        }
      }
    ]
  }
}

// ─── Private DNS Zone: NoSQL (SQL API) ───────────────────────────────────────

resource noSqlDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.documents.azure.com'
  location: 'global'
  tags: tags
}

resource noSqlDnsVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: noSqlDnsZone
  name: '${cosmosNoSqlAccountName}-vnet-link'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

resource noSqlPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${cosmosNoSqlAccountName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointsSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'cosmos-nosql'
        properties: {
          privateLinkServiceId: cosmosNoSqlAccountId
          groupIds: ['Sql']
        }
      }
    ]
  }
}

resource noSqlDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: noSqlPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'nosql-config'
        properties: {
          privateDnsZoneId: noSqlDnsZone.id
        }
      }
    ]
  }
}
