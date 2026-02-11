# 1. Delete the Fabric workspace (not in the Azure RG — created via REST API)
#    Uses the workspace ID from azure_config.env
source azure_config.env 2>/dev/null || true
FABRIC_WS_ID="${FABRIC_WORKSPACE_ID:-$(grep FABRIC_WORKSPACE_ID azure_config.env 2>/dev/null | cut -d= -f2)}"
az rest --method DELETE --url "https://api.fabric.microsoft.com/v1/workspaces/$FABRIC_WS_ID"

# 2. Tear down all Azure resources via azd
azd down --force --purge

# 3. If azd down didn't purge Cognitive Services (soft-delete), do it manually
#    Uses values from azure_config.env
AI_NAME="${AI_FOUNDRY_NAME:-}"
RG="${AZURE_RESOURCE_GROUP:-}"
LOC="${AZURE_LOCATION:-}"
if [ -n "$AI_NAME" ] && [ -n "$RG" ] && [ -n "$LOC" ]; then
  az cognitiveservices account purge \
    --name "$AI_NAME" \
    --resource-group "$RG" \
    --location "$LOC"
fi

# 4. If the resource group is still lingering
if [ -n "$RG" ]; then
  az group delete --name "$RG" --yes --no-wait
fi

# 5. Clear the azd environment state
azd env delete --yes