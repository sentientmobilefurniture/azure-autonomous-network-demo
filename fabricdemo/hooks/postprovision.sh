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
# 2. Populate azure_config.env for downstream scripts
# --------------------------------------------------------------------------
echo ""
echo "Populating azure_config.env..."

CONFIG_FILE="$PROJECT_ROOT/azure_config.env"

# Get subscription ID
SUB_ID=$(az account show --query id -o tsv)

# Save azd-provided Bicep outputs BEFORE sourcing — the source below would
# overwrite them with the (empty) values from the existing config file.
AZD_GRAPH_QUERY_API_URI="${GRAPH_QUERY_API_URI:-}"
AZD_APP_URI="${APP_URI:-}"
AZD_APP_PRINCIPAL_ID="${APP_PRINCIPAL_ID:-}"
AZD_COSMOS_NOSQL_ENDPOINT="${COSMOS_NOSQL_ENDPOINT:-}"

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
PREV_CORS="${CORS_ORIGINS:-http://localhost:5173}"
PREV_GPT_CAPACITY="${GPT_CAPACITY_1K_TPM:-10}"
PREV_GRAPH_BACKEND="${GRAPH_BACKEND:-fabric-gql}"
PREV_FABRIC_ADMIN="${AZURE_FABRIC_ADMIN:-}"
PREV_FABRIC_SKU="${FABRIC_CAPACITY_SKU:-}"

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
PROJECT_ENDPOINT=${AZURE_AI_PROJECT_ENDPOINT:-}

# --- Model deployments (USER: must match infra/modules/ai-foundry.bicep) ---
MODEL_DEPLOYMENT_NAME=$MODEL_DEPLOY
EMBEDDING_MODEL=$EMBED_MODEL
EMBEDDING_DIMENSIONS=$EMBED_DIMS

# --- Azure AI Search (AUTO: name from deployment) ---
AI_SEARCH_NAME=${AZURE_SEARCH_NAME:-}
RUNBOOKS_INDEX_NAME=${RUNBOOKS_INDEX_NAME:-runbooks-index}
TICKETS_INDEX_NAME=${TICKETS_INDEX_NAME:-tickets-index}

# --- Azure Storage (AUTO: name from deployment) ---
STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT

# --- Deployment settings (USER: edit before 'azd up') ---
GPT_CAPACITY_1K_TPM=${PREV_GPT_CAPACITY}

# --- App / CORS (USER: change for production deployment) ---
CORS_ORIGINS=${PREV_CORS}

# --- Graph Backend ---
# Controls which graph database backend is used by graph-query-api
# Options: "fabric-gql" (GQL via Microsoft Fabric), "mock" (static responses)
GRAPH_BACKEND=${PREV_GRAPH_BACKEND}

# --- Unified app (AUTO: from deployment) ---
APP_URI=${AZD_APP_URI:-${APP_URI:-}}
APP_PRINCIPAL_ID=${AZD_APP_PRINCIPAL_ID:-${APP_PRINCIPAL_ID:-}}
# GRAPH_QUERY_API_URI points to the same unified container
GRAPH_QUERY_API_URI=${AZD_GRAPH_QUERY_API_URI:-${APP_URI:-}}

# --- Cosmos DB NoSQL / Interactions (AUTO: from deployment) ---
COSMOS_NOSQL_ENDPOINT=${AZD_COSMOS_NOSQL_ENDPOINT:-${COSMOS_NOSQL_ENDPOINT:-}}

# --- Fabric Admin & Capacity (USER/AUTO: admin auto-detected, SKU user-configurable) ---
AZURE_FABRIC_ADMIN=${PREV_FABRIC_ADMIN}
FABRIC_CAPACITY_SKU=${PREV_FABRIC_SKU:-F8}

# --- Fabric Resources ---
# Graph Model ID, Eventhouse Query URI, and KQL DB name are
# discovered at runtime by graph-query-api/fabric_discovery.py.
FABRIC_CAPACITY_ID=${FABRIC_CAPACITY_ID:-}
FABRIC_WORKSPACE_ID=${FABRIC_WORKSPACE_ID:-}
FABRIC_EVENTHOUSE_ID=${FABRIC_EVENTHOUSE_ID:-}
EOF

echo "  \u2713 azure_config.env written"

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
    sed -i "s|^FABRIC_CAPACITY_ID=.*|FABRIC_CAPACITY_ID=$CAP_GUID|" "$CONFIG_FILE"
    # Add if not present
    grep -q "^FABRIC_CAPACITY_ID=" "$CONFIG_FILE" || echo "FABRIC_CAPACITY_ID=$CAP_GUID" >> "$CONFIG_FILE"
    echo "  ✓ FABRIC_CAPACITY_ID=$CAP_GUID"
  else
    echo "  ⚠ Could not resolve Fabric capacity GUID — set FABRIC_CAPACITY_ID manually in azure_config.env"
    echo "    (Fabric portal → Capacity settings → copy the Capacity ID)"
  fi
fi

echo ""
echo "✅ Post-provision complete!"
