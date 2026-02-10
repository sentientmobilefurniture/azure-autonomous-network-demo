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

# --------------------------------------------------------------------------
# 0. Wait for RBAC propagation (Storage Blob Data Contributor)
#    Role assignments created in the same deployment can take minutes to
#    propagate. Retry the first upload until it succeeds or we give up.
# --------------------------------------------------------------------------
upload_with_retry() {
  local container="$1"
  local source_dir="$2"
  local max_attempts=6
  local wait_secs=30

  for attempt in $(seq 1 $max_attempts); do
    echo "  Attempt $attempt/$max_attempts — uploading to '$container'..."
    if az storage blob upload-batch \
        --destination "$container" \
        --account-name "$STORAGE_ACCOUNT" \
        --source "$source_dir" \
        --auth-mode login \
        --overwrite \
        --only-show-errors 2>/dev/null; then
      echo "  ✓ $container uploaded"
      return 0
    fi

    if [ "$attempt" -lt "$max_attempts" ]; then
      echo "  ⏳ RBAC not yet propagated — waiting ${wait_secs}s..."
      sleep "$wait_secs"
    fi
  done

  echo "  ✗ Failed to upload to '$container' after $max_attempts attempts."
  echo "    RBAC may still be propagating. Run postprovision manually:"
  echo "    azd hooks run postprovision"
  return 1
}

# --------------------------------------------------------------------------
# 1. Upload runbook markdown files to blob storage
# --------------------------------------------------------------------------
echo ""
echo "Uploading runbooks to blob container 'runbooks'..."
upload_with_retry "runbooks" "$PROJECT_ROOT/data/runbooks"

# --------------------------------------------------------------------------
# 2. Upload historical ticket .txt files to blob storage
# --------------------------------------------------------------------------
echo ""
echo "Uploading tickets to blob container 'tickets'..."
upload_with_retry "tickets" "$PROJECT_ROOT/data/tickets"

# --------------------------------------------------------------------------
# 3. Populate azure_config.env for downstream scripts
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# 3. Look up Fabric capacity GUID (if deployed)
# --------------------------------------------------------------------------
FABRIC_CAP_NAME="${AZURE_FABRIC_CAPACITY_NAME:-}"
FABRIC_CAP_ID=""

if [ -n "$FABRIC_CAP_NAME" ]; then
  echo ""
  echo "Looking up Fabric capacity GUID for '$FABRIC_CAP_NAME'..."
  # Get an access token for the Fabric API
  FABRIC_TOKEN=$(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv 2>/dev/null || true)
  if [ -n "$FABRIC_TOKEN" ]; then
    FABRIC_CAP_ID=$(curl -s -H "Authorization: Bearer $FABRIC_TOKEN" \
      "https://api.fabric.microsoft.com/v1/capacities" | \
      python3 -c "import sys,json; caps=json.load(sys.stdin).get('value',[]); matches=[c['id'] for c in caps if c.get('displayName','')=='$FABRIC_CAP_NAME']; print(matches[0] if matches else '')" 2>/dev/null || true)
  fi
  if [ -n "$FABRIC_CAP_ID" ]; then
    echo "  ✓ Fabric capacity GUID: $FABRIC_CAP_ID"
  else
    echo "  ⚠ Could not resolve Fabric capacity GUID — set FABRIC_CAPACITY_ID manually in azure_config.env"
  fi
fi

# --------------------------------------------------------------------------
# 4. Populate azure_config.env for downstream scripts
# --------------------------------------------------------------------------
echo ""
echo "Populating azure_config.env..."

CONFIG_FILE="$PROJECT_ROOT/azure_config.env"

# Get subscription ID
SUB_ID=$(az account show --query id -o tsv)

# Preserve user-set values from existing azure_config.env (if present)
if [ -f "$CONFIG_FILE" ]; then
  set -a
  source "$CONFIG_FILE"
  set +a
fi

# User-configurable values — preserved from existing file, or defaults
MODEL_DEPLOY="${MODEL_DEPLOYMENT_NAME:-gpt-4.1}"
EMBED_MODEL="${EMBEDDING_MODEL:-text-embedding-3-small}"
EMBED_DIMS="${EMBEDDING_DIMENSIONS:-1536}"
FABRIC_WS="${FABRIC_WORKSPACE_NAME:-AutonomousNetworkDemo}"
LAKEHOUSE="${FABRIC_LAKEHOUSE_NAME:-NetworkTopologyLH}"
EVENTHOUSE="${FABRIC_EVENTHOUSE_NAME:-NetworkTelemetryEH_3117}"
KQL_DB_DEFAULT="${FABRIC_KQL_DB_DEFAULT:-NetworkDB}"
RUNBOOKS_IDX="${RUNBOOKS_INDEX_NAME:-runbooks-index}"
TICKETS_IDX="${TICKETS_INDEX_NAME:-tickets-index}"
RUNBOOKS_CONT="${RUNBOOKS_CONTAINER_NAME:-runbooks}"
TICKETS_CONT="${TICKETS_CONTAINER_NAME:-tickets}"
FABRIC_SKU_VAL="${FABRIC_SKU:-F32}"
FABRIC_ADMIN_VAL="${AZURE_FABRIC_ADMIN:-}"
# Preserve IDs that were set by populate_fabric_config.py
PREV_FABRIC_CAP_ID="${FABRIC_CAPACITY_ID:-}"
PREV_FABRIC_WS_ID="${FABRIC_WORKSPACE_ID:-}"
PREV_FABRIC_LH_ID="${FABRIC_LAKEHOUSE_ID:-}"
PREV_FABRIC_EH_ID="${FABRIC_EVENTHOUSE_ID:-}"
PREV_FABRIC_KQL_ID="${FABRIC_KQL_DB_ID:-}"
PREV_FABRIC_KQL_NAME="${FABRIC_KQL_DB_NAME:-}"
PREV_FABRIC_CONN="${FABRIC_CONNECTION_NAME:-}"
PREV_EH_URI="${EVENTHOUSE_QUERY_URI:-}"
PREV_AGENT_ID="${FABRIC_DATA_AGENT_ID:-}"
PREV_AGENT_API="${FABRIC_DATA_AGENT_API_VERSION:-2024-05-01-preview}"

cat > "$CONFIG_FILE" <<EOF
# ============================================================================
# Autonomous Network NOC Demo — Configuration
# ============================================================================
# This is the SINGLE source of truth for all project configuration.
# Edit values here, then run 'azd up' — preprovision.sh syncs them to Bicep.
# Auto-populated fields are updated by postprovision.sh after each deployment.
# Last updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# ============================================================================

# --- Core Azure settings (AUTO: from deployment) ---
AZURE_SUBSCRIPTION_ID=$SUB_ID
AZURE_RESOURCE_GROUP=$RG
AZURE_LOCATION=${AZURE_LOCATION:-eastus2}

# --- AI Foundry (AUTO: from deployment) ---
AI_FOUNDRY_NAME=${AZURE_AI_FOUNDRY_NAME:-}
AI_FOUNDRY_ENDPOINT=${AZURE_AI_FOUNDRY_ENDPOINT:-}
AI_FOUNDRY_PROJECT_NAME=${AZURE_AI_FOUNDRY_PROJECT_NAME:-}
PROJECT_ENDPOINT=${AZURE_AI_FOUNDRY_ENDPOINT:-}

# --- Model deployments (USER: must match infra/modules/ai-foundry.bicep) ---
MODEL_DEPLOYMENT_NAME=$MODEL_DEPLOY
EMBEDDING_MODEL=$EMBED_MODEL
EMBEDDING_DIMENSIONS=$EMBED_DIMS

# --- Azure AI Search (AUTO: name from deployment, USER: index names) ---
AI_SEARCH_NAME=${AZURE_SEARCH_NAME:-}
RUNBOOKS_INDEX_NAME=$RUNBOOKS_IDX
TICKETS_INDEX_NAME=$TICKETS_IDX

# --- Azure Storage (AUTO: name from deployment, USER: container names) ---
STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT
RUNBOOKS_CONTAINER_NAME=$RUNBOOKS_CONT
TICKETS_CONTAINER_NAME=$TICKETS_CONT

# --- Fabric deployment settings (USER: edit before 'azd up') ---
FABRIC_SKU=$FABRIC_SKU_VAL
AZURE_FABRIC_ADMIN=$FABRIC_ADMIN_VAL

# --- Fabric resource names (USER: edit before running provision_fabric.py) ---
FABRIC_WORKSPACE_NAME=$FABRIC_WS
FABRIC_LAKEHOUSE_NAME=$LAKEHOUSE
FABRIC_EVENTHOUSE_NAME=$EVENTHOUSE
FABRIC_KQL_DB_DEFAULT=$KQL_DB_DEFAULT

# --- Fabric IDs (AUTO: populated by populate_fabric_config.py) ---
FABRIC_CONNECTION_NAME=${PREV_FABRIC_CONN}
EVENTHOUSE_QUERY_URI=${PREV_EH_URI}
FABRIC_CAPACITY_ID=${FABRIC_CAP_ID:-$PREV_FABRIC_CAP_ID}
FABRIC_WORKSPACE_ID=${PREV_FABRIC_WS_ID}
FABRIC_LAKEHOUSE_ID=${PREV_FABRIC_LH_ID}
FABRIC_EVENTHOUSE_ID=${PREV_FABRIC_EH_ID}
FABRIC_KQL_DB_ID=${PREV_FABRIC_KQL_ID}
FABRIC_KQL_DB_NAME=${PREV_FABRIC_KQL_NAME}

# --- Fabric Data Agent (USER: set after creating Data Agent in Fabric portal) ---
FABRIC_DATA_AGENT_ID=${PREV_AGENT_ID}
FABRIC_DATA_AGENT_API_VERSION=${PREV_AGENT_API}
EOF

echo "  ✓ azure_config.env written"

echo ""
echo "✅ Post-provision complete!"
