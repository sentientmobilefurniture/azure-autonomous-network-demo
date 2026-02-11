// ============================================================================
// Parameters file for Autonomous Network NOC Demo
// Set environment variables before deploying:
//   AZURE_ENV_NAME        — e.g. "noc-demo"
//   AZURE_LOCATION        — e.g. "australiaeast"
//   AZURE_PRINCIPAL_ID    — your user object ID (az ad signed-in-user show --query id -o tsv)
//   AZURE_FABRIC_ADMIN    — (required) email for Fabric capacity admin
//   AZURE_FABRIC_SKU      — (optional) Fabric SKU, default F32
// ============================================================================

using './main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'noc-demo')
param location = readEnvironmentVariable('AZURE_LOCATION', 'eastus2')
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID', '')
param fabricAdminEmail = readEnvironmentVariable('AZURE_FABRIC_ADMIN', '')
param fabricSkuName = readEnvironmentVariable('AZURE_FABRIC_SKU', 'F32')
param gptCapacity = int(readEnvironmentVariable('GPT_CAPACITY_1K_TPM', '10'))
param tags = {
  project: 'autonomous-network-noc'
  environment: readEnvironmentVariable('AZURE_ENV_NAME', 'noc-demo')
}

// azd init
// azd env set AZURE_LOCATION eastus2
// azd env set AZURE_FABRIC_ADMIN <your-admin-email>
// ./deploy.sh
