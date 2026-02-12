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

@description('Graph backend: "cosmosdb" deploys Cosmos DB Gremlin.')
@allowed(['cosmosdb'])
param graphBackend string = 'cosmosdb'

@description('Developer IP for local Cosmos DB access (leave empty in CI/CD)')
param devIpAddress string = ''

// Derived flag for conditional deployment
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
    storageContainerName: storage.outputs.containerName
    gptCapacity: gptCapacity
  }
}

// ---------------------------------------------------------------------------
// Container Apps (graph-query-api micro-service)
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

module graphQueryApi 'modules/container-app.bicep' = {
  scope: rg
  params: {
    name: 'ca-graphquery-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'graph-query-api' })
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
    ], deployCosmosGremlin ? [
      { name: 'COSMOS_GREMLIN_ENDPOINT', value: cosmosGremlin!.outputs.gremlinEndpoint }
      { name: 'COSMOS_GREMLIN_DATABASE', value: 'networkgraph' }
      { name: 'COSMOS_GREMLIN_GRAPH', value: 'topology' }
      { name: 'COSMOS_GREMLIN_PRIMARY_KEY', secretRef: 'cosmos-gremlin-key' }
      { name: 'COSMOS_NOSQL_ENDPOINT', value: cosmosGremlin!.outputs.cosmosNoSqlEndpoint }
      { name: 'COSMOS_NOSQL_DATABASE', value: cosmosGremlin!.outputs.telemetryDatabaseName }
    ] : [])
    secrets: deployCosmosGremlin ? [
      { name: 'cosmos-gremlin-key', value: cosmosGremlin!.outputs.primaryKey }
    ] : []
  }
}

// ---------------------------------------------------------------------------
// Container App — API (FastAPI backend, Foundry agent orchestrator)
// ---------------------------------------------------------------------------

module apiService 'modules/container-app.bicep' = {
  scope: rg
  params: {
    name: 'ca-api-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'api' })
    containerAppsEnvironmentId: containerAppsEnv.outputs.id
    containerRegistryName: containerAppsEnv.outputs.registryName
    targetPort: 8000
    externalIngress: false  // Only accessed by the frontend reverse proxy (internal)
    minReplicas: 1
    maxReplicas: 3
    cpu: '0.5'
    memory: '1Gi'
    env: [
      { name: 'PROJECT_ENDPOINT', value: aiFoundry.outputs.foundryEndpoint }
      { name: 'AI_FOUNDRY_PROJECT_NAME', value: aiFoundry.outputs.projectName }
      { name: 'MODEL_DEPLOYMENT_NAME', value: 'gpt-4.1' }
      { name: 'CORS_ORIGINS', value: '*' }
      { name: 'AGENT_IDS_PATH', value: '/app/scripts/agent_ids.json' }
    ]
  }
}

// ---------------------------------------------------------------------------
// Container App — Frontend (React + nginx reverse proxy)
// ---------------------------------------------------------------------------

module frontend 'modules/container-app.bicep' = {
  scope: rg
  params: {
    name: 'ca-frontend-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'frontend' })
    containerAppsEnvironmentId: containerAppsEnv.outputs.id
    containerRegistryName: containerAppsEnv.outputs.registryName
    targetPort: 80
    externalIngress: true   // Public-facing UI
    minReplicas: 1
    maxReplicas: 2
    cpu: '0.25'
    memory: '0.5Gi'
    env: [
      { name: 'API_BACKEND_URL', value: 'https://${apiService.outputs.fqdn}' }
    ]
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
    cosmosNoSqlAccountName: deployCosmosGremlin ? 'cosmos-gremlin-${resourceToken}-nosql' : ''
    containerAppPrincipalId: graphQueryApi.outputs.principalId
    apiContainerAppPrincipalId: apiService.outputs.principalId
  }
}

// ---------------------------------------------------------------------------
// Private Endpoints — Cosmos DB Gremlin + NoSQL over VNet backbone
// Protects the Container App → Cosmos DB path from Azure Policy toggling
// publicNetworkAccess. Traffic stays on the VNet regardless.
// ---------------------------------------------------------------------------

module cosmosPrivateEndpoints 'modules/cosmos-private-endpoints.bicep' = if (deployCosmosGremlin) {
  scope: rg
  params: {
    location: location
    tags: tags
    vnetId: vnet.outputs.id
    privateEndpointsSubnetId: vnet.outputs.privateEndpointsSubnetId
    cosmosGremlinAccountId: cosmosGremlin!.outputs.cosmosAccountId
    cosmosGremlinAccountName: cosmosGremlin!.outputs.cosmosAccountName
    cosmosNoSqlAccountId: cosmosGremlin!.outputs.cosmosNoSqlAccountId
    cosmosNoSqlAccountName: cosmosGremlin!.outputs.cosmosNoSqlAccountName
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
output GRAPH_QUERY_API_URI string = graphQueryApi.outputs.uri
output GRAPH_QUERY_API_PRINCIPAL_ID string = graphQueryApi.outputs.principalId
output API_URI string = apiService.outputs.uri
output API_PRINCIPAL_ID string = apiService.outputs.principalId
output FRONTEND_URI string = frontend.outputs.uri
output COSMOS_GREMLIN_ENDPOINT string = deployCosmosGremlin ? cosmosGremlin!.outputs.gremlinEndpoint : ''
output COSMOS_GREMLIN_ACCOUNT_NAME string = deployCosmosGremlin ? cosmosGremlin!.outputs.cosmosAccountName : ''
output COSMOS_NOSQL_ENDPOINT string = deployCosmosGremlin ? cosmosGremlin!.outputs.cosmosNoSqlEndpoint : ''
output COSMOS_NOSQL_DATABASE string = deployCosmosGremlin ? cosmosGremlin!.outputs.telemetryDatabaseName : ''
