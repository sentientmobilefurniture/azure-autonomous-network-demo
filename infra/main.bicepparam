// ============================================================================
// Parameters file for Autonomous Network NOC Demo
//
// Two deployment paths:
//   graphBackend = 'fabric'   → provisions Fabric capacity (requires AZURE_FABRIC_ADMIN)
//   graphBackend = 'cosmosdb' → provisions Cosmos DB Gremlin (no Fabric capacity)
//
// Set environment variables before deploying:
//   AZURE_ENV_NAME        — e.g. "noc-demo"
//   AZURE_LOCATION        — e.g. "australiaeast"
//   AZURE_PRINCIPAL_ID    — your user object ID (az ad signed-in-user show --query id -o tsv)
//   GRAPH_BACKEND         — "fabric" or "cosmosdb" (default: "cosmosdb")
//   AZURE_FABRIC_ADMIN    — (fabric path only) email for Fabric capacity admin
//   AZURE_FABRIC_SKU      — (fabric path only) Fabric SKU, default F8
// ============================================================================

using './main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'noc-demo')
param location = readEnvironmentVariable('AZURE_LOCATION', 'eastus2')
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID', '')
param graphBackend = readEnvironmentVariable('GRAPH_BACKEND', 'cosmosdb')
param fabricAdminEmail = readEnvironmentVariable('AZURE_FABRIC_ADMIN', '')
param fabricSkuName = readEnvironmentVariable('AZURE_FABRIC_SKU', 'F8')
param gptCapacity = int(readEnvironmentVariable('GPT_CAPACITY_1K_TPM', '300'))
param tags = {
  project: 'autonomous-network-noc'
  environment: readEnvironmentVariable('AZURE_ENV_NAME', 'noc-demo')
  graphBackend: readEnvironmentVariable('GRAPH_BACKEND', 'cosmosdb')
}

// Deploy:
//   GRAPH_BACKEND=cosmosdb azd up        # Cosmos DB path (no Fabric)
//   GRAPH_BACKEND=fabric AZURE_FABRIC_ADMIN=you@example.com azd up   # Fabric path
