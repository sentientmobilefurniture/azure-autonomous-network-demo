#!/usr/bin/env bash
# ============================================================================
# Post-provision hook — upload data to deployed Azure resources
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# azd populates outputs as env vars prefixed with AZURE_
# These come from main.bicep outputs
STORAGE_ACCOUNT="${AZURE_STORAGE_ACCOUNT_NAME:?Missing output AZURE_STORAGE_ACCOUNT_NAME}"
RG="${AZURE_RESOURCE_GROUP:?Missing output AZURE_RESOURCE_GROUP}"

echo "============================================"
echo "Post-provision: uploading data"
echo "  Storage : $STORAGE_ACCOUNT"
echo "  RG      : $RG"
echo "============================================"

# Ensure DEFAULT_SCENARIO is set (may not be in env when running azd up directly)
DEFAULT_SCENARIO="${DEFAULT_SCENARIO:-$(azd env get-values 2>/dev/null | grep '^DEFAULT_SCENARIO=' | cut -d'=' -f2 | tr -d '"' || true)}"
DEFAULT_SCENARIO="${DEFAULT_SCENARIO:-telecom-playground}"

# --------------------------------------------------------------------------
# 1. Upload runbooks + tickets to blob storage
#    (RBAC may take a few minutes to propagate after deployment)
# --------------------------------------------------------------------------
DATA_DIR="$PROJECT_ROOT/data/scenarios/${DEFAULT_SCENARIO}/data/knowledge"
MAX_ATTEMPTS=6
WAIT_SECS=30

for container in runbooks tickets; do
  src_dir="$DATA_DIR/$container"
  if [ ! -d "$src_dir" ]; then
    echo "  ⚠ $src_dir not found — skipping $container upload"
    continue
  fi

  for attempt in $(seq 1 $MAX_ATTEMPTS); do
    echo "  Attempt $attempt/$MAX_ATTEMPTS — uploading to '$container'..."
    if az storage blob upload-batch \
        --destination "$container" \
        --account-name "$STORAGE_ACCOUNT" \
        --source "$src_dir" \
        --auth-mode login \
        --overwrite \
        --only-show-errors 2>/dev/null; then
      echo "  ✓ $container uploaded"
      break
    fi

    if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
      echo "  ⏳ RBAC not yet propagated — waiting ${WAIT_SECS}s..."
      sleep "$WAIT_SECS"
    else
      echo "  ✗ Failed to upload '$container' after $MAX_ATTEMPTS attempts."
      echo "    RBAC may still be propagating. Run: azd hooks run postprovision"
    fi
  done
done

# --------------------------------------------------------------------------
# 2. Populate azure_config.env with deployment outputs
# --------------------------------------------------------------------------
echo ""
echo "Populating azure_config.env with deployment outputs..."

CONFIG_FILE="$PROJECT_ROOT/azure_config.env"

# set_config: update a key in azure_config.env (created from template by deploy.sh)
set_config() {
  local key="$1" val="$2"
  # Use SOH (\x01) as sed delimiter to avoid conflicts with URLs/paths
  local d=$'\x01'
  if grep -q "^${key}=" "$CONFIG_FILE" 2>/dev/null; then
    sed -i "s${d}^${key}=.*${d}${key}=${val}${d}" "$CONFIG_FILE"
  else
    echo "${key}=${val}" >> "$CONFIG_FILE"
  fi
}

# The config file should already exist (deploy.sh copies from template).
# If somehow it doesn't, create from template.
if [[ ! -f "$CONFIG_FILE" ]]; then
  TEMPLATE="$PROJECT_ROOT/azure_config.env.template"
  if [[ -f "$TEMPLATE" ]]; then
    cp "$TEMPLATE" "$CONFIG_FILE"
    echo "  ⚠ azure_config.env was missing — recreated from template"
  else
    echo "  ✗ Neither azure_config.env nor template found — cannot proceed"
    exit 1
  fi
fi

# Get subscription ID
SUB_ID=$(az account show --query id -o tsv)

# Save azd-provided Bicep outputs BEFORE sourcing — the source below would
# overwrite them with the (empty) values from the existing config file.
AZD_GRAPH_QUERY_API_URI="${GRAPH_QUERY_API_URI:-}"
AZD_APP_URI="${APP_URI:-}"
AZD_APP_PRINCIPAL_ID="${APP_PRINCIPAL_ID:-}"
AZD_COSMOS_NOSQL_ENDPOINT="${COSMOS_NOSQL_ENDPOINT:-}"

# Source existing config to pick up user-set values
set -a; source "$CONFIG_FILE"; set +a

# Write deployment outputs into the config file
set_config AZURE_SUBSCRIPTION_ID "$SUB_ID"
set_config AZURE_RESOURCE_GROUP "$RG"
[[ -n "${AZURE_LOCATION:-}" ]] && set_config AZURE_LOCATION "$AZURE_LOCATION"

# AI Foundry
[[ -n "${AZURE_AI_FOUNDRY_NAME:-}" ]]        && set_config AI_FOUNDRY_NAME "$AZURE_AI_FOUNDRY_NAME"
[[ -n "${AZURE_AI_FOUNDRY_ENDPOINT:-}" ]]    && set_config AI_FOUNDRY_ENDPOINT "$AZURE_AI_FOUNDRY_ENDPOINT"
[[ -n "${AZURE_AI_FOUNDRY_PROJECT_NAME:-}" ]] && set_config AI_FOUNDRY_PROJECT_NAME "$AZURE_AI_FOUNDRY_PROJECT_NAME"
[[ -n "${AZURE_AI_PROJECT_ENDPOINT:-}" ]]    && set_config PROJECT_ENDPOINT "$AZURE_AI_PROJECT_ENDPOINT"

# AI Search
[[ -n "${AZURE_SEARCH_NAME:-}" ]] && set_config AI_SEARCH_NAME "$AZURE_SEARCH_NAME"

# Storage
set_config STORAGE_ACCOUNT_NAME "$STORAGE_ACCOUNT"

# App / Container App
APP_URI_VAL="${AZD_APP_URI:-${APP_URI:-}}"
[[ -n "$APP_URI_VAL" ]] && set_config APP_URI "$APP_URI_VAL"
PRINCIPAL_VAL="${AZD_APP_PRINCIPAL_ID:-${APP_PRINCIPAL_ID:-}}"
[[ -n "$PRINCIPAL_VAL" ]] && set_config APP_PRINCIPAL_ID "$PRINCIPAL_VAL"
GQ_VAL="${AZD_GRAPH_QUERY_API_URI:-${APP_URI_VAL:-}}"
[[ -n "$GQ_VAL" ]] && set_config GRAPH_QUERY_API_URI "$GQ_VAL"

# Cosmos DB
COSMOS_VAL="${AZD_COSMOS_NOSQL_ENDPOINT:-${COSMOS_NOSQL_ENDPOINT:-}}"
[[ -n "$COSMOS_VAL" ]] && set_config COSMOS_NOSQL_ENDPOINT "$COSMOS_VAL"

echo "  ✓ azure_config.env updated with deployment outputs"

# --------------------------------------------------------------------------
# 3. Resolve Fabric capacity GUID (if Bicep provisioned a capacity)
# --------------------------------------------------------------------------
FAB_CAP_NAME="${FABRIC_CAPACITY_NAME:-${AZURE_FABRIC_CAPACITY_NAME:-}}"
if [[ -n "$FAB_CAP_NAME" ]]; then
  echo ""
  echo "Resolving Fabric capacity GUID for '$FAB_CAP_NAME'..."
  CAP_GUID=$(az rest \
    --url "https://api.fabric.microsoft.com/v1/capacities" \
    --resource "https://api.fabric.microsoft.com" \
    --query "value[?displayName=='$FAB_CAP_NAME'].id | [0]" \
    -o tsv 2>/dev/null || true)

  if [[ -n "$CAP_GUID" && "$CAP_GUID" != "None" ]]; then
    set_config FABRIC_CAPACITY_ID "$CAP_GUID"
    echo "  ✓ FABRIC_CAPACITY_ID=$CAP_GUID"
  else
    echo "  ⚠ Could not resolve Fabric capacity GUID — set FABRIC_CAPACITY_ID manually in azure_config.env"
    echo "    (Fabric portal → Capacity settings → copy the Capacity ID)"
  fi
fi

echo ""
echo "✅ Post-provision complete!"
