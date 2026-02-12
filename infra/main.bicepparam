// ============================================================================
// Parameters file for Autonomous Network NOC Demo
//
// Deploys Cosmos DB Gremlin for graph backend.
//
// Set environment variables before deploying:
//   AZURE_ENV_NAME        — e.g. "noc-demo"
//   AZURE_LOCATION        — e.g. "australiaeast"
//   AZURE_PRINCIPAL_ID    — your user object ID (az ad signed-in-user show --query id -o tsv)
// ============================================================================

using './main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'noc-demo')
param location = readEnvironmentVariable('AZURE_LOCATION', 'eastus2')
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID', '')
param graphBackend = 'cosmosdb'
param gptCapacity = int(readEnvironmentVariable('GPT_CAPACITY_1K_TPM', '300'))
param tags = {
  project: 'autonomous-network-noc'
  environment: readEnvironmentVariable('AZURE_ENV_NAME', 'noc-demo')
  graphBackend: 'cosmosdb'
}

// Deploy:
//   azd up    # Uses cosmosdb backend
