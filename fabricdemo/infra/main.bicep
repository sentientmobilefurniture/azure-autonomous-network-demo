// ============================================================================
// Autonomous Network NOC Demo — Main Orchestrator
// Subscription-scoped deployment that creates the resource group and all services
// ============================================================================

targetScope = 'subscription'

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

@minLength(1)
@maxLength(64)
@description('Name of the environment (used as prefix for all resources)')
param environmentName string

@description('Primary location for all resources')
param location string

@description('Object ID of the user principal to assign roles to')
param principalId string

@description('Tags to apply to all resources')
param tags object = {}

@description('GPT model capacity in 1K TPM units (e.g. 10 = 10K tokens/min, 100 = 100K TPM)')
param gptCapacity int = 300

@description('Graph backend: "fabric-gql" uses Microsoft Fabric for graph queries.')
param graphBackend string = 'fabric-gql'

@description('Fabric workspace ID (set after Fabric provisioning)')
param fabricWorkspaceId string = ''

@description('Fabric capacity SKU (F8 default). Pause when not in use to control cost.')
@allowed(['F2', 'F4', 'F8', 'F16', 'F32', 'F64', 'F128', 'F256', 'F512', 'F1024', 'F2048'])
param fabricCapacitySku string = 'F8'

@description('Admin email for Fabric capacity')
param fabricAdminEmail string = ''

@description('Developer IP for local Cosmos DB access (leave empty in CI/CD)')
param devIpAddress string = ''


// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

var abbrs = {
  resourceGroup: 'rg-'
  aiFoundry: 'aif-'
  aiFoundryProject: 'proj-'
  search: 'srch-'
  storage: 'st'
  fabric: 'fc'
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

// ---------------------------------------------------------------------------
// Resource Group
// ---------------------------------------------------------------------------

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: '${abbrs.resourceGroup}${environmentName}'
  location: location
  tags: tags
}

// ---------------------------------------------------------------------------
// Module Deployments
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Virtual Network (Container Apps + Private Endpoints subnets)
// ---------------------------------------------------------------------------

module vnet 'modules/vnet.bicep' = {
  scope: rg
  params: {
    name: 'vnet-${resourceToken}'
    location: location
    tags: tags
  }
}

module search 'modules/search.bicep' = {
  scope: rg
  params: {
    name: '${abbrs.search}${resourceToken}'
    location: location
    tags: tags
  }
}

module storage 'modules/storage.bicep' = {
  scope: rg
  params: {
    name: '${abbrs.storage}${resourceToken}'
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Microsoft Fabric Capacity
// ---------------------------------------------------------------------------

module fabric 'modules/fabric.bicep' = if (!empty(fabricAdminEmail)) {
  scope: rg
  params: {
    name: '${abbrs.fabric}${resourceToken}'
    location: location
    tags: union(tags, { component: 'fabric-capacity' })
    adminEmail: fabricAdminEmail
    skuName: fabricCapacitySku
  }
}

// ---------------------------------------------------------------------------
// Cosmos DB NoSQL (interactions store only)
// ---------------------------------------------------------------------------

module cosmosNoSql 'modules/cosmos-nosql.bicep' = {
  scope: rg
  params: {
    accountName: 'cosmos-nosql-${resourceToken}'
    location: location
    tags: union(tags, { component: 'interactions-store' })
    devIpAddress: devIpAddress
  }
}

module aiFoundry 'modules/ai-foundry.bicep' = {
  scope: rg
  params: {
    foundryName: '${abbrs.aiFoundry}${resourceToken}'
    projectName: '${abbrs.aiFoundryProject}${resourceToken}'
    location: location
    tags: tags
    aiSearchId: search.outputs.id
    aiSearchName: search.outputs.name
    storageAccountId: storage.outputs.id
    storageAccountName: storage.outputs.name
    storageContainerName: 'network-data'
    gptCapacity: gptCapacity
  }
}

// ---------------------------------------------------------------------------
// Container Apps Environment + Unified App
// ---------------------------------------------------------------------------

module containerAppsEnv 'modules/container-apps-environment.bicep' = {
  scope: rg
  params: {
    name: 'cae-${resourceToken}'
    location: location
    tags: tags
    infrastructureSubnetId: vnet.outputs.containerAppsSubnetId
  }
}

// Single unified container: nginx (:80) + API (:8000) + graph-query-api (:8100)
module app 'modules/container-app.bicep' = {
  scope: rg
  params: {
    name: 'ca-app-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'app' })
    containerAppsEnvironmentId: containerAppsEnv.outputs.id
    containerRegistryName: containerAppsEnv.outputs.registryName
    targetPort: 80
    externalIngress: true
    minReplicas: 1
    maxReplicas: 3
    cpu: '1.0'
    memory: '2Gi'
    env: union([
      { name: 'PROJECT_ENDPOINT', value: aiFoundry.outputs.foundryEndpoint }
      { name: 'AI_FOUNDRY_PROJECT_NAME', value: aiFoundry.outputs.projectName }
      { name: 'MODEL_DEPLOYMENT_NAME', value: 'gpt-4.1' }
      { name: 'CORS_ORIGINS', value: '*' }
      { name: 'GRAPH_BACKEND', value: graphBackend }
      { name: 'COSMOS_NOSQL_ENDPOINT', value: cosmosNoSql.outputs.cosmosNoSqlEndpoint }
      { name: 'AZURE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
      { name: 'AZURE_RESOURCE_GROUP', value: rg.name }
      { name: 'AI_SEARCH_NAME', value: search.outputs.name }
      { name: 'AZURE_SEARCH_ENDPOINT', value: search.outputs.endpoint }
      { name: 'RUNBOOKS_INDEX_NAME', value: 'runbooks-index' }
      { name: 'TICKETS_INDEX_NAME', value: 'tickets-index' }
      { name: 'STORAGE_ACCOUNT_NAME', value: storage.outputs.name }
      { name: 'AI_FOUNDRY_NAME', value: aiFoundry.outputs.foundryName }
      { name: 'EMBEDDING_MODEL', value: 'text-embedding-3-small' }
      { name: 'EMBEDDING_DIMENSIONS', value: '1536' }
      { name: 'FABRIC_WORKSPACE_ID', value: fabricWorkspaceId }
    ], [])
    secrets: []
  }
}

module roles 'modules/roles.bicep' = {
  scope: rg
  params: {
    principalId: principalId
    foundryName: aiFoundry.outputs.foundryName
    searchName: search.outputs.name
    storageAccountName: storage.outputs.name
    searchPrincipalId: search.outputs.principalId
    foundryPrincipalId: aiFoundry.outputs.foundryPrincipalId
    cosmosNoSqlAccountName: cosmosNoSql.outputs.cosmosAccountName
    containerAppPrincipalId: app.outputs.principalId
    apiContainerAppPrincipalId: app.outputs.principalId
  }
}

// ---------------------------------------------------------------------------
// Private Endpoints — Cosmos DB NoSQL over VNet backbone
// Protects the Container App → Cosmos DB path from Azure Policy toggling
// publicNetworkAccess. Traffic stays on the VNet regardless.
// ---------------------------------------------------------------------------

module cosmosPrivateEndpoints 'modules/cosmos-private-endpoints.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    vnetId: vnet.outputs.id
    privateEndpointsSubnetId: vnet.outputs.privateEndpointsSubnetId
    cosmosNoSqlAccountId: cosmosNoSql.outputs.cosmosAccountId
    cosmosNoSqlAccountName: cosmosNoSql.outputs.cosmosAccountName
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_VNET_NAME string = vnet.outputs.name
output AZURE_AI_FOUNDRY_NAME string = aiFoundry.outputs.foundryName
output AZURE_AI_FOUNDRY_ENDPOINT string = aiFoundry.outputs.foundryEndpoint
output AZURE_AI_FOUNDRY_PROJECT_NAME string = aiFoundry.outputs.projectName
output AZURE_SEARCH_NAME string = search.outputs.name
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerAppsEnv.outputs.registryEndpoint
output APP_URI string = app.outputs.uri
output APP_PRINCIPAL_ID string = app.outputs.principalId
// Foundry agents use GRAPH_QUERY_API_URI — same container, same URL
output GRAPH_QUERY_API_URI string = app.outputs.uri
output COSMOS_NOSQL_ENDPOINT string = cosmosNoSql.outputs.cosmosNoSqlEndpoint
output FABRIC_CAPACITY_NAME string = !empty(fabricAdminEmail) ? fabric.outputs.name : ''
