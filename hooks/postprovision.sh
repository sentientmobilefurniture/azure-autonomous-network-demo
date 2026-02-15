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
# 1. Data uploads — SKIPPED (V8: data loaded via UI scenario upload)
#    The primary path for all data (graph, telemetry, runbooks, tickets)
#    is now via the UI Settings page: POST /query/scenario/upload
#    which handles blob upload + AI Search indexing automatically.
# --------------------------------------------------------------------------
echo ""
echo "Skipping blob uploads — data is loaded via UI Settings page (⚙ → Upload Scenario)"
echo "  To upload a scenario: tar czf scenario.tar.gz -C data/scenarios <name>"
echo "  Then upload via the app's Settings modal."

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
AZD_COSMOS_GREMLIN_ENDPOINT="${COSMOS_GREMLIN_ENDPOINT:-}"
AZD_COSMOS_GREMLIN_ACCOUNT_NAME="${COSMOS_GREMLIN_ACCOUNT_NAME:-}"
AZD_COSMOS_NOSQL_ENDPOINT="${COSMOS_NOSQL_ENDPOINT:-}"
AZD_COSMOS_NOSQL_DATABASE="${COSMOS_NOSQL_DATABASE:-}"

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
PREV_GRAPH_BACKEND="${GRAPH_BACKEND:-cosmosdb}"
PREV_COSMOS_GREMLIN_DB="${COSMOS_GREMLIN_DATABASE:-networkgraph}"
PREV_COSMOS_NOSQL_DB="${COSMOS_NOSQL_DATABASE:-telemetry}"

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

# --- Azure AI Search (AUTO: name from deployment) ---
AI_SEARCH_NAME=${AZURE_SEARCH_NAME:-}

# --- Azure Storage (AUTO: name from deployment) ---
STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT

# --- Deployment settings (USER: edit before 'azd up') ---
GPT_CAPACITY_1K_TPM=${PREV_GPT_CAPACITY}

# --- App / CORS (USER: change for production deployment) ---
CORS_ORIGINS=${PREV_CORS}

# --- Graph Backend ---
# Controls which graph database backend is used by graph-query-api
# Options: "cosmosdb" (Gremlin → Azure Cosmos DB), "mock" (static responses)
GRAPH_BACKEND=${PREV_GRAPH_BACKEND}

# --- Unified app (AUTO: from deployment) ---
APP_URI=${AZD_APP_URI:-${APP_URI:-}}
APP_PRINCIPAL_ID=${AZD_APP_PRINCIPAL_ID:-${APP_PRINCIPAL_ID:-}}
# GRAPH_QUERY_API_URI points to the same unified container
GRAPH_QUERY_API_URI=${AZD_GRAPH_QUERY_API_URI:-${APP_URI:-}}

# --- Cosmos DB Gremlin (required when GRAPH_BACKEND=cosmosdb) ---
COSMOS_GREMLIN_ENDPOINT=${AZD_COSMOS_GREMLIN_ENDPOINT:-${COSMOS_GREMLIN_ENDPOINT:-}}
COSMOS_GREMLIN_PRIMARY_KEY=${COSMOS_GREMLIN_PRIMARY_KEY:-}
COSMOS_GREMLIN_DATABASE=${PREV_COSMOS_GREMLIN_DB}

# --- Cosmos DB NoSQL / Telemetry (AUTO: from deployment) ---
COSMOS_NOSQL_ENDPOINT=${AZD_COSMOS_NOSQL_ENDPOINT:-${COSMOS_NOSQL_ENDPOINT:-}}
COSMOS_NOSQL_DATABASE=${AZD_COSMOS_NOSQL_DATABASE:-${PREV_COSMOS_NOSQL_DB}}
EOF
# --------------------------------------------------------------------------
# 5. Auto-populate Cosmos DB Gremlin credentials (if deployed)
# --------------------------------------------------------------------------
# Bicep outputs: COSMOS_GREMLIN_ACCOUNT_NAME, COSMOS_GREMLIN_ENDPOINT
# (no AZURE_ prefix — unlike other outputs)
COSMOS_ACCOUNT="${AZD_COSMOS_GREMLIN_ACCOUNT_NAME:-${COSMOS_GREMLIN_ACCOUNT_NAME:-}}"
if [ -n "$COSMOS_ACCOUNT" ]; then
  echo ""
  echo "Auto-populating Cosmos DB Gremlin credentials..."
  COSMOS_EP="${AZD_COSMOS_GREMLIN_ENDPOINT:-${COSMOS_GREMLIN_ENDPOINT:-}}"
  if [ -z "$COSMOS_EP" ]; then
    # Gremlin endpoint is account-name.gremlin.cosmos.azure.com
    # (NOT documentEndpoint which is for the SQL/NoSQL API)
    COSMOS_EP="${COSMOS_ACCOUNT}.gremlin.cosmos.azure.com"
  fi
  COSMOS_KEY=$(az cosmosdb keys list --name "$COSMOS_ACCOUNT" --resource-group "$RG" --query primaryMasterKey -o tsv 2>/dev/null || true)
  if [ -n "$COSMOS_KEY" ]; then
    # Patch the values in-place in azure_config.env
    sed -i "s|^COSMOS_GREMLIN_ENDPOINT=.*|COSMOS_GREMLIN_ENDPOINT=$COSMOS_EP|" "$CONFIG_FILE"
    sed -i "s|^COSMOS_GREMLIN_PRIMARY_KEY=.*|COSMOS_GREMLIN_PRIMARY_KEY=$COSMOS_KEY|" "$CONFIG_FILE"
    echo "  ✓ Cosmos DB Gremlin credentials populated"
    # Also populate the NoSQL endpoint (same account)
    COSMOS_NOSQL_EP="${AZD_COSMOS_NOSQL_ENDPOINT:-${COSMOS_NOSQL_ENDPOINT:-}}"
    if [ -z "$COSMOS_NOSQL_EP" ]; then
      # Query the separate NoSQL account (account-nosql), not the Gremlin account
      COSMOS_NOSQL_EP=$(az cosmosdb show --name "${COSMOS_ACCOUNT}-nosql" --resource-group "$RG" --query documentEndpoint -o tsv 2>/dev/null || true)
    fi
    if [ -n "$COSMOS_NOSQL_EP" ]; then
      sed -i "s|^COSMOS_NOSQL_ENDPOINT=.*|COSMOS_NOSQL_ENDPOINT=$COSMOS_NOSQL_EP|" "$CONFIG_FILE"
      echo "  ✓ Cosmos DB NoSQL endpoint populated"
    fi
  else
    echo "  ⚠ Could not fetch Cosmos DB key — set COSMOS_GREMLIN_PRIMARY_KEY manually in azure_config.env"
  fi
fi

echo "  ✓ azure_config.env written"

echo ""
echo "✅ Post-provision complete!"
