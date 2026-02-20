@description('Name of the Web App')
param webAppName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('App Service Plan SKU')
param skuName string = 'P0v3'

@description('AI Foundry project endpoint')
param projectEndpoint string

@description('Model deployment name')
param modelDeploymentName string = 'gpt-4.1'

@description('Cosmos DB NoSQL endpoint')
param cosmosEndpoint string = ''

@description('AI Search endpoint')
param searchEndpoint string = ''

@description('Default scenario name')
param defaultScenario string = ''

@description('Fabric workspace ID')
param fabricWorkspaceId string = ''

@description('Fabric ontology name')
param fabricOntologyName string = ''

@description('Fabric eventhouse name')
param fabricEventhouseName string = ''

@description('Azure subscription ID')
param subscriptionId string = ''

@description('Resource group name')
param resourceGroupName string = ''

@description('AI Search name')
param searchName string = ''

@description('Storage account name')
param storageAccountName string = ''

@description('AI Foundry name')
param foundryName string = ''

@description('Runbooks search index name')
param runbooksIndexName string = 'runbooks-index'

@description('Tickets search index name')
param ticketsIndexName string = 'tickets-index'

// App Service Plan
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: '${webAppName}-plan'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: skuName
  }
  properties: {
    reserved: true // Linux
  }
}

// Web App
resource webApp 'Microsoft.Web/sites@2024-04-01' = {
  name: webAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000'
      alwaysOn: true
      ftpsState: 'Disabled'
      appSettings: [
        { name: 'PROJECT_ENDPOINT', value: projectEndpoint }
        { name: 'MODEL_DEPLOYMENT_NAME', value: modelDeploymentName }
        { name: 'COSMOS_NOSQL_ENDPOINT', value: cosmosEndpoint }
        { name: 'AZURE_SEARCH_ENDPOINT', value: searchEndpoint }
        { name: 'DEFAULT_SCENARIO', value: defaultScenario }
        { name: 'FABRIC_WORKSPACE_ID', value: fabricWorkspaceId }
        { name: 'FABRIC_ONTOLOGY_NAME', value: fabricOntologyName }
        { name: 'FABRIC_EVENTHOUSE_NAME', value: fabricEventhouseName }
        { name: 'GRAPH_BACKEND', value: 'fabric-gql' }
        { name: 'TOPOLOGY_SOURCE', value: 'static' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'AZURE_SUBSCRIPTION_ID', value: subscriptionId }
        { name: 'AZURE_RESOURCE_GROUP', value: resourceGroupName }
        { name: 'AI_SEARCH_NAME', value: searchName }
        { name: 'STORAGE_ACCOUNT_NAME', value: storageAccountName }
        { name: 'AI_FOUNDRY_NAME', value: foundryName }
        { name: 'RUNBOOKS_INDEX_NAME', value: runbooksIndexName }
        { name: 'TICKETS_INDEX_NAME', value: ticketsIndexName }
      ]
    }
    httpsOnly: true
  }
}

output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output webAppPrincipalId string = webApp.identity.principalId
