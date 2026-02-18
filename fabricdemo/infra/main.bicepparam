// ============================================================================
// Parameters file for Autonomous Network NOC Demo
//
// Deploys Fabric GQL for graph backend, Cosmos NoSQL for metadata stores.
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
param graphBackend = readEnvironmentVariable('GRAPH_BACKEND', 'fabric-gql')
param topologySource = readEnvironmentVariable('TOPOLOGY_SOURCE', 'static')
param gptCapacity = int(readEnvironmentVariable('GPT_CAPACITY_1K_TPM', '300'))
param devIpAddress = readEnvironmentVariable('DEV_IP_ADDRESS', '')
param fabricWorkspaceId = readEnvironmentVariable('FABRIC_WORKSPACE_ID', '')
param fabricAdminEmail = readEnvironmentVariable('AZURE_FABRIC_ADMIN', '')
param fabricCapacitySku = readEnvironmentVariable('FABRIC_CAPACITY_SKU', 'F8')
param tags = {
  project: 'autonomous-network-noc'
  environment: readEnvironmentVariable('AZURE_ENV_NAME', 'noc-demo')
  graphBackend: 'fabric-gql'
}

// Deploy:
//   azd up    # Uses fabric-gql backend
