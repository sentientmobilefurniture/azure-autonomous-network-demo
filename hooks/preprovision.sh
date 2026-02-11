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

  # Variables that Bicep needs (mapped to azd env var names)
  declare -A ENV_MAP=(
    ["AZURE_LOCATION"]="AZURE_LOCATION"
    ["AZURE_FABRIC_ADMIN"]="AZURE_FABRIC_ADMIN"
    ["FABRIC_SKU"]="AZURE_FABRIC_SKU"
    ["GPT_CAPACITY_1K_TPM"]="GPT_CAPACITY_1K_TPM"
  )

  # Source the config file to read values
  set -a
  source "$CONFIG_FILE"
  set +a

  for config_key in "${!ENV_MAP[@]}"; do
    azd_key="${ENV_MAP[$config_key]}"
    value="${!config_key:-}"
    if [ -n "$value" ]; then
      azd env set "$azd_key" "$value"
      echo "  → $azd_key=$value"
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
