#!/usr/bin/env bash
set -euo pipefail

# 1. Tear down all Azure resources via azd
source azure_config.env 2>/dev/null || true
azd down --force --purge

# 2. If azd down didn't purge Cognitive Services (soft-delete), do it manually
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

# 3. If the resource group is still lingering
if [ -n "$RG" ]; then
  az group delete --name "$RG" --yes --no-wait
fi

# 4. Clear the azd environment state
azd env delete --yes