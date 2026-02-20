#!/usr/bin/env bash
# ============================================================================
# Pre-provision hook — sync azure_config.env → azd env so Bicep sees them
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$PROJECT_ROOT/azure_config.env"

# --------------------------------------------------------------------------
# 1. Load user settings from azure_config.env into azd env
#    This is the SINGLE source of truth for all configuration.
# --------------------------------------------------------------------------
if [ -f "$CONFIG_FILE" ]; then
  echo "Syncing azure_config.env → azd env..."

  # Source the config file to read values
  set -a
  source "$CONFIG_FILE"
  set +a

  # Sync selected variables to azd env for Bicep
  # (POSIX-compatible — no associative arrays)
  for var_name in AZURE_LOCATION GPT_CAPACITY_1K_TPM GRAPH_BACKEND FABRIC_WORKSPACE_ID AZURE_FABRIC_ADMIN FABRIC_CAPACITY_SKU DEFAULT_SCENARIO RUNBOOKS_INDEX_NAME TICKETS_INDEX_NAME CORS_ORIGINS; do
    value=""
    case "$var_name" in
      AZURE_LOCATION)        value="${AZURE_LOCATION:-}" ;;
      GPT_CAPACITY_1K_TPM)   value="${GPT_CAPACITY_1K_TPM:-}" ;;
      GRAPH_BACKEND)         value="${GRAPH_BACKEND:-}" ;;
      FABRIC_WORKSPACE_ID)   value="${FABRIC_WORKSPACE_ID:-}" ;;
      AZURE_FABRIC_ADMIN)    value="${AZURE_FABRIC_ADMIN:-}" ;;
      FABRIC_CAPACITY_SKU)   value="${FABRIC_CAPACITY_SKU:-}" ;;
      DEFAULT_SCENARIO)      value="${DEFAULT_SCENARIO:-}" ;;
      RUNBOOKS_INDEX_NAME)   value="${RUNBOOKS_INDEX_NAME:-}" ;;
      TICKETS_INDEX_NAME)    value="${TICKETS_INDEX_NAME:-}" ;;
      CORS_ORIGINS)          value="${CORS_ORIGINS:-}" ;;
    esac
    if [ -n "$value" ]; then
      azd env set "$var_name" "$value"
      echo "  → $var_name=$value"
    fi
  done
else
  echo "⚠ azure_config.env not found — using azd env defaults."
  echo "  Copy azure_config.env.template → azure_config.env and set your values."
fi

# --------------------------------------------------------------------------
# 2. Resolve AZURE_PRINCIPAL_ID if not already set
# --------------------------------------------------------------------------
if [ -z "${AZURE_PRINCIPAL_ID:-}" ]; then
  echo "AZURE_PRINCIPAL_ID not set — resolving from signed-in user..."
  PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)
  azd env set AZURE_PRINCIPAL_ID "$PRINCIPAL_ID"
  echo "  → Set AZURE_PRINCIPAL_ID=$PRINCIPAL_ID"
else
  echo "  → AZURE_PRINCIPAL_ID already set: $AZURE_PRINCIPAL_ID"
fi

# --------------------------------------------------------------------------
# 3. Auto-detect AZURE_FABRIC_ADMIN if not set (enables Fabric capacity)
# --------------------------------------------------------------------------
if [ -z "${AZURE_FABRIC_ADMIN:-}" ]; then
  echo "AZURE_FABRIC_ADMIN not set — resolving from signed-in user..."
  FABRIC_ADMIN=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null || true)
  if [ -n "$FABRIC_ADMIN" ]; then
    azd env set AZURE_FABRIC_ADMIN "$FABRIC_ADMIN"
    echo "  → Set AZURE_FABRIC_ADMIN=$FABRIC_ADMIN"
  else
    echo "  ⚠ Could not resolve user email — Fabric capacity will NOT be provisioned."
    echo "    Set AZURE_FABRIC_ADMIN manually in azure_config.env to enable it."
  fi
else
  echo "  → AZURE_FABRIC_ADMIN already set: $AZURE_FABRIC_ADMIN"
fi
