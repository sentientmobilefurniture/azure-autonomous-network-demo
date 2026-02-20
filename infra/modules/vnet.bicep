// ============================================================================
// Virtual Network — Container Apps subnet + Private Endpoints subnet
//
// Provides network isolation for Container Apps and private connectivity
// to Cosmos DB via Private Endpoints + Private DNS zones.
// ============================================================================

@description('Name of the virtual network')
param name string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('Address space for the VNet')
param addressPrefix string = '10.0.0.0/16'

@description('Address prefix for the Container Apps subnet (/23 minimum required)')
param containerAppsSubnetPrefix string = '10.0.0.0/23'

@description('Address prefix for the Private Endpoints subnet')
param privateEndpointsSubnetPrefix string = '10.0.2.0/24'

// ---------------------------------------------------------------------------
// Virtual Network
// ---------------------------------------------------------------------------

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [addressPrefix]
    }
    subnets: [
      {
        name: 'snet-container-apps'
        properties: {
          addressPrefix: containerAppsSubnetPrefix
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: privateEndpointsSubnetPrefix
        }
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output id string = vnet.id
output name string = vnet.name
output containerAppsSubnetId string = vnet.properties.subnets[0].id
output privateEndpointsSubnetId string = vnet.properties.subnets[1].id
