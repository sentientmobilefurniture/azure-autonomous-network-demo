// ============================================================================
// Microsoft Fabric Capacity
// ============================================================================

@description('Name of the Fabric capacity')
param name string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('Admin email address for Fabric capacity')
param adminEmail string

@description('SKU for Fabric capacity. PAUSE when not in use to avoid cost burn.')
@allowed(['F2', 'F4', 'F8', 'F16', 'F32', 'F64', 'F128', 'F256', 'F512', 'F1024', 'F2048'])
param skuName string = 'F8'

// ---------------------------------------------------------------------------
// Fabric Capacity
// ---------------------------------------------------------------------------

resource fabricCapacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: [
        adminEmail
      ]
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output id string = fabricCapacity.id
output name string = fabricCapacity.name
