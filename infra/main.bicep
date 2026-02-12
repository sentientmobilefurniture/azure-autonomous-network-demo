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

@description('Admin email for Fabric capacity (only used on Fabric path)')
param fabricAdminEmail string = ''

@description('SKU for Fabric capacity (F2-F2048). PAUSE when not in use to control cost.')
@allowed(['F2', 'F4', 'F8', 'F16', 'F32', 'F64', 'F128', 'F256', 'F512', 'F1024', 'F2048'])
param fabricSkuName string = 'F8'

@description('GPT model capacity in 1K TPM units (e.g. 10 = 10K tokens/min, 100 = 100K TPM)')
param gptCapacity int = 300

@description('Graph backend: "fabric" deploys Fabric capacity, "cosmosdb" deploys Cosmos DB Gremlin. Controls which infra path is provisioned.')
@allowed(['fabric', 'cosmosdb'])
param graphBackend string = 'fabric'

// Derived flags for conditional deployment
var deployFabric = graphBackend == 'fabric' && !empty(fabricAdminEmail)
var deployCosmosGremlin = graphBackend == 'cosmosdb'


// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

var abbrs = {
  resourceGroup: 'rg-'
  aiFoundry: 'aif-'
  aiFoundryProject: 'proj-'
  search: 'srch-'
  storage: 'st'
  fabric: 'fab-'
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

module fabric 'modules/fabric.bicep' = if (deployFabric) {
  scope: rg
  params: {
    name: 'fab${resourceToken}'
    location: location
    tags: tags
    adminEmail: fabricAdminEmail
    skuName: fabricSkuName
  }
}

// ---------------------------------------------------------------------------
// Cosmos DB Gremlin (graphBackend == 'cosmosdb')
// ---------------------------------------------------------------------------

module cosmosGremlin 'modules/cosmos-gremlin.bicep' = if (deployCosmosGremlin) {
  scope: rg
  params: {
    accountName: 'cosmos-gremlin-${resourceToken}'
    location: location
    databaseName: 'networkgraph'
    graphName: 'topology'
    partitionKeyPath: '/partitionKey'
    maxThroughput: 1000
    tags: union(tags, { component: 'graph-backend' })
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
    storageContainerName: storage.outputs.containerName
    gptCapacity: gptCapacity
  }
}

// ---------------------------------------------------------------------------
// Container Apps (fabric-query-api micro-service)
// ---------------------------------------------------------------------------

module containerAppsEnv 'modules/container-apps-environment.bicep' = {
  scope: rg
  params: {
    name: 'cae-${resourceToken}'
    location: location
    tags: tags
  }
}

module fabricQueryApi 'modules/container-app.bicep' = {
  scope: rg
  params: {
    name: 'ca-fabricquery-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'fabric-query-api' })
    containerAppsEnvironmentId: containerAppsEnv.outputs.id
    containerRegistryName: containerAppsEnv.outputs.registryName
    targetPort: 8100
    externalIngress: true   // Foundry OpenApiTool calls from outside the VNet
    minReplicas: 1
    maxReplicas: 2
    cpu: '0.25'
    memory: '0.5Gi'
    env: union([
      { name: 'GRAPH_BACKEND', value: graphBackend }
      { name: 'EVENTHOUSE_QUERY_URI', value: '' }
      { name: 'FABRIC_KQL_DB_NAME', value: '' }
    ], deployFabric ? [
      { name: 'FABRIC_WORKSPACE_ID', value: '' }
      { name: 'FABRIC_GRAPH_MODEL_ID', value: '' }
    ] : [], deployCosmosGremlin ? [
      { name: 'COSMOS_GREMLIN_ENDPOINT', value: cosmosGremlin!.outputs.gremlinEndpoint }
      { name: 'COSMOS_GREMLIN_DATABASE', value: 'networkgraph' }
      { name: 'COSMOS_GREMLIN_GRAPH', value: 'topology' }
      { name: 'COSMOS_GREMLIN_PRIMARY_KEY', secretRef: 'cosmos-gremlin-key' }
    ] : [])
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
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_AI_FOUNDRY_NAME string = aiFoundry.outputs.foundryName
output AZURE_AI_FOUNDRY_ENDPOINT string = aiFoundry.outputs.foundryEndpoint
output AZURE_AI_FOUNDRY_PROJECT_NAME string = aiFoundry.outputs.projectName
output AZURE_SEARCH_NAME string = search.outputs.name
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.name
output AZURE_FABRIC_CAPACITY_NAME string = deployFabric ? fabric!.outputs.name : ''
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerAppsEnv.outputs.registryEndpoint
output FABRIC_QUERY_API_URI string = fabricQueryApi.outputs.uri
output FABRIC_QUERY_API_PRINCIPAL_ID string = fabricQueryApi.outputs.principalId
output COSMOS_GREMLIN_ENDPOINT string = deployCosmosGremlin ? cosmosGremlin!.outputs.gremlinEndpoint : ''
output COSMOS_GREMLIN_ACCOUNT_NAME string = deployCosmosGremlin ? cosmosGremlin!.outputs.cosmosAccountName : ''
