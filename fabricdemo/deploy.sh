#!/usr/bin/env bash
# ============================================================================
# AI Incident Investigator — End-to-End Deployment Script
# ============================================================================
#
# Deploys the full pipeline:
#   1. Azure infrastructure (AI Foundry, AI Search, Storage, Cosmos DB (interactions), Container Apps)
#   2. Unified Container App deployment (nginx + API + graph-query-api)
#   3. Local services (optional — all services deployed to Azure)
#
# After infrastructure is provisioned, run provisioning scripts for Fabric,
# data loading, and agent creation using the --provision-* flags.
#
# Usage:
#   chmod +x deploy.sh && ./deploy.sh
#
# Options:
#   --skip-infra         Skip azd up (reuse existing Azure resources)
#   --skip-app           Skip app container deploy (use with --skip-infra)
#   --skip-local         Skip starting local API + frontend
#   --provision-fabric   Run Fabric provisioning (lakehouse, eventhouse, ontology)
#   --provision-data     Run data provisioning (AI Search indexes)
#   --provision-agents   Run agent provisioning
#   --provision-all      Run all provisioning steps (fabric + data + agents)
#   --env NAME           Use a specific azd environment name
#   --location LOC       Azure location (default: swedencentral)
#   --scenario NAME      Scenario name (subfolder under data/scenarios/)
#   --yes                Skip all confirmation prompts
#
# ============================================================================
set -euo pipefail

# ── Colour helpers ──────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()    { echo -e "${GREEN}✓${NC}  $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
fail()  { echo -e "${RED}✗${NC}  $*"; }
step()  { echo -e "\n${BOLD}${CYAN}━━━ $* ━━━${NC}\n"; }
banner() {
  echo -e "\n${BOLD}${CYAN}"
  echo "╔════════════════════════════════════════════════════════════════╗"
  echo "║  AI Incident Investigator — Deployment                       ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo -e "${NC}"
}

# ── Parse arguments ─────────────────────────────────────────────────

SKIP_INFRA=false
SKIP_APP=false
SKIP_LOCAL=false
PROVISION_FABRIC=false
PROVISION_DATA=false
PROVISION_AGENTS=false
AUTO_YES=false
AZD_ENV_NAME=""
AZURE_LOC=""
SCENARIO_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-infra)        SKIP_INFRA=true; shift ;;
    --skip-app)          SKIP_APP=true; shift ;;
    --skip-local)        SKIP_LOCAL=true; shift ;;
    --provision-fabric)  PROVISION_FABRIC=true; shift ;;
    --provision-data)    PROVISION_DATA=true; shift ;;
    --provision-agents)  PROVISION_AGENTS=true; shift ;;
    --provision-all)     PROVISION_FABRIC=true; PROVISION_DATA=true; PROVISION_AGENTS=true; shift ;;
    --yes|-y)            AUTO_YES=true; shift ;;
    --env)               AZD_ENV_NAME="$2"; shift 2 ;;
    --location)          AZURE_LOC="$2"; shift 2 ;;
    --scenario)          SCENARIO_NAME="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,/^set -euo/p' "$0" | head -n -1
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      echo "Run with --help for usage."
      exit 1
      ;;
  esac
done

# ── Locate project root ────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

CONFIG_FILE="$PROJECT_ROOT/azure_config.env"

# ── Helper: prompt user ────────────────────────────────────────────

confirm() {
  local msg="$1"
  if $AUTO_YES; then return 0; fi
  echo -en "${YELLOW}?${NC}  ${msg} [y/N] "
  read -r answer
  [[ "$answer" =~ ^[Yy] ]]
}

choose() {
  # Usage: choose "prompt" option1 option2 option3
  # Returns the chosen option text
  local prompt="$1"; shift
  local options=("$@")
  echo -e "\n${YELLOW}?${NC}  ${prompt}"
  for i in "${!options[@]}"; do
    echo "   $((i+1))) ${options[$i]}"
  done
  while true; do
    echo -en "   Choice [1-${#options[@]}]: "
    read -r choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
      CHOSEN="${options[$((choice-1))]}"
      return 0
    fi
    echo "   Invalid choice."
  done
}

# ── Scenario discovery ──────────────────────────────────────────────

if [[ -z "$SCENARIO_NAME" ]]; then
  SCENARIO_NAME="${DEFAULT_SCENARIO:-}"
fi
if [[ -z "$SCENARIO_NAME" ]]; then
  SCENARIOS=( $(ls -d "$PROJECT_ROOT/data/scenarios"/*/ 2>/dev/null | xargs -I{} basename {}) )
  if (( ${#SCENARIOS[@]} == 1 )); then
    SCENARIO_NAME="${SCENARIOS[0]}"
  elif (( ${#SCENARIOS[@]} > 1 )); then
    if $AUTO_YES; then
      fail "Multiple scenarios found. Pass --scenario <name>."
      exit 1
    fi
    choose "Which scenario?" "${SCENARIOS[@]}"
    SCENARIO_NAME="$CHOSEN"
  else
    fail "No scenarios found in data/scenarios/"
    exit 1
  fi
fi

SCENARIO_DIR="$PROJECT_ROOT/data/scenarios/$SCENARIO_NAME"
SCENARIO_YAML="$SCENARIO_DIR/scenario.yaml"

if [[ ! -f "$SCENARIO_YAML" ]]; then
  fail "Scenario manifest not found: $SCENARIO_YAML"
  exit 1
fi

export DEFAULT_SCENARIO="$SCENARIO_NAME"
info "Scenario: $SCENARIO_NAME (from $SCENARIO_YAML)"

# Extract index names from scenario.yaml for Bicep / env vars
RUNBOOKS_INDEX_NAME=$(python3 -c "
import yaml
with open('$SCENARIO_YAML') as f:
    c = yaml.safe_load(f)
print(c.get('data_sources',{}).get('search_indexes',{}).get('runbooks',{}).get('index_name','runbooks-index'))
")
TICKETS_INDEX_NAME=$(python3 -c "
import yaml
with open('$SCENARIO_YAML') as f:
    c = yaml.safe_load(f)
print(c.get('data_sources',{}).get('search_indexes',{}).get('tickets',{}).get('index_name','tickets-index'))
")
export RUNBOOKS_INDEX_NAME TICKETS_INDEX_NAME
info "Index names: runbooks=$RUNBOOKS_INDEX_NAME, tickets=$TICKETS_INDEX_NAME"

# ── Helper: auto-discover resources from existing Azure RG ─────────

discover_resources_from_rg() {
  # Populates AUTO-filled variables by querying existing Azure resources.
  # Called when azure_config.env is missing/empty and --skip-infra is used.
  local rg="$1"

  if ! az group show --name "$rg" &>/dev/null; then
    warn "Resource group '$rg' not found — cannot auto-discover resources."
    return 1
  fi

  info "Auto-discovering resources from resource group: $rg"

  # Subscription
  AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv 2>/dev/null || true)

  # AI Foundry (CognitiveServices account of kind AIServices)
  AI_FOUNDRY_NAME=$(az cognitiveservices account list -g "$rg" \
    --query "[?kind=='AIServices'].name | [0]" -o tsv 2>/dev/null || true)
  if [[ -n "$AI_FOUNDRY_NAME" ]]; then
    AI_FOUNDRY_ENDPOINT="https://${AI_FOUNDRY_NAME}.cognitiveservices.azure.com/"
    ok "AI Foundry:   $AI_FOUNDRY_NAME"
  fi

  # AI Foundry project (child account of the foundry)
  AI_FOUNDRY_PROJECT_NAME=$(az cognitiveservices account list -g "$rg" \
    --query "[?kind=='AIServices' && contains(name,'proj')].name | [0]" -o tsv 2>/dev/null || true)
  # Fallback: derive from foundry name  (aif-xxx → proj-xxx)
  if [[ -z "$AI_FOUNDRY_PROJECT_NAME" && -n "$AI_FOUNDRY_NAME" ]]; then
    local suffix="${AI_FOUNDRY_NAME#aif-}"
    AI_FOUNDRY_PROJECT_NAME="proj-${suffix}"
  fi

  # Build the correct project endpoint (services.ai.azure.com, not cognitiveservices)
  if [[ -n "$AI_FOUNDRY_NAME" && -n "$AI_FOUNDRY_PROJECT_NAME" ]]; then
    PROJECT_ENDPOINT="https://${AI_FOUNDRY_NAME}.services.ai.azure.com/api/projects/${AI_FOUNDRY_PROJECT_NAME}"
    ok "Project EP:   $PROJECT_ENDPOINT"
  fi

  # AI Search
  AI_SEARCH_NAME=$(az search service list -g "$rg" \
    --query "[0].name" -o tsv 2>/dev/null || true)
  [[ -n "$AI_SEARCH_NAME" ]] && ok "AI Search:    $AI_SEARCH_NAME"

  # Storage Account
  STORAGE_ACCOUNT_NAME=$(az storage account list -g "$rg" \
    --query "[0].name" -o tsv 2>/dev/null || true)
  [[ -n "$STORAGE_ACCOUNT_NAME" ]] && ok "Storage:      $STORAGE_ACCOUNT_NAME"

  # Cosmos DB NoSQL
  local cosmos_name
  cosmos_name=$(az cosmosdb list -g "$rg" \
    --query "[0].name" -o tsv 2>/dev/null || true)
  if [[ -n "$cosmos_name" ]]; then
    COSMOS_NOSQL_ENDPOINT=$(az cosmosdb show -n "$cosmos_name" -g "$rg" \
      --query "documentEndpoint" -o tsv 2>/dev/null || true)
    [[ -n "$COSMOS_NOSQL_ENDPOINT" ]] && ok "Cosmos DB:    $cosmos_name"
  fi

  # Container App (unified app)
  local ca_name
  ca_name=$(az containerapp list -g "$rg" \
    --query "[0].name" -o tsv 2>/dev/null || true)
  if [[ -n "$ca_name" ]]; then
    APP_URI=$(az containerapp show -n "$ca_name" -g "$rg" \
      --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || true)
    if [[ -n "$APP_URI" && ! "$APP_URI" =~ ^https:// ]]; then
      APP_URI="https://$APP_URI"
    fi
    GRAPH_QUERY_API_URI="$APP_URI"
    APP_PRINCIPAL_ID=$(az containerapp show -n "$ca_name" -g "$rg" \
      --query "identity.principalId" -o tsv 2>/dev/null || true)
    [[ -n "$APP_URI" ]] && ok "App URI:      $APP_URI"
  fi

  # Fabric admin from azd env (preserved across runs)
  if [[ -z "${AZURE_FABRIC_ADMIN:-}" ]]; then
    AZURE_FABRIC_ADMIN=$(azd env get-values 2>/dev/null | grep "^AZURE_FABRIC_ADMIN=" | cut -d'"' -f2 || true)
  fi

  ok "Auto-discovery complete"
}

# ── Step 0: Prerequisites ──────────────────────────────────────────

banner

step "Step 0: Checking & installing prerequisites"

# ── Auto-install helpers ────────────────────────────────────────────

install_python3() {
  info "Installing Python 3..."
  if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
  elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3 >/dev/null
  elif command -v brew &>/dev/null; then
    brew install python@3.12
  else
    fail "Cannot auto-install Python 3 — unknown package manager."
    fail "Install manually: https://www.python.org/downloads/"
    return 1
  fi
}

install_uv() {
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Add to PATH for this session
  export PATH="$HOME/.local/bin:$PATH"
}

install_node() {
  info "Installing Node.js 20 via nvm..."
  if ! command -v nvm &>/dev/null; then
    # nvm is a shell function; try sourcing it
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [[ -s "$NVM_DIR/nvm.sh" ]]; then
      source "$NVM_DIR/nvm.sh"
    else
      info "Installing nvm first..."
      curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
      export NVM_DIR="$HOME/.nvm"
      source "$NVM_DIR/nvm.sh"
    fi
  fi
  nvm install 20
  nvm use 20
}

install_az() {
  info "Installing Azure CLI..."
  curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
}

install_azd() {
  info "Installing Azure Developer CLI..."
  curl -fsSL https://aka.ms/install-azd.sh | bash
  export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
}

# ── Check each prerequisite, offer install if missing ───────────────

PREREQ_OK=true

ensure_cmd() {
  local cmd="$1" friendly="$2" installer="$3"
  if command -v "$cmd" &>/dev/null; then
    ok "$friendly: $(command -v "$cmd")"
    return 0
  fi

  warn "$friendly not found."
  if $AUTO_YES || confirm "Install $friendly now?"; then
    if $installer; then
      # Re-check
      if command -v "$cmd" &>/dev/null; then
        ok "$friendly installed: $(command -v "$cmd")"
        return 0
      fi
      # Some tools (node via nvm) may need hash reset
      hash -r 2>/dev/null
      if command -v "$cmd" &>/dev/null; then
        ok "$friendly installed: $(command -v "$cmd")"
        return 0
      fi
    fi
    fail "$friendly installation failed."
    PREREQ_OK=false
  else
    fail "$friendly is required. Skipping."
    PREREQ_OK=false
  fi
}

ensure_cmd python3 "Python 3.11+" install_python3
ensure_cmd uv      "uv"           install_uv
ensure_cmd node    "Node.js 20+"  install_node
ensure_cmd az      "Azure CLI"    install_az
ensure_cmd azd     "Azure Developer CLI" install_azd

# Verify Python version is 3.11+
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 11) )); then
    fail "Python $PY_VER found but 3.11+ is required."
    PREREQ_OK=false
  fi
fi

# Verify Node.js version is 20+
if command -v node &>/dev/null; then
  NODE_MAJOR=$(node --version | sed 's/v//' | cut -d. -f1)
  if (( NODE_MAJOR < 20 )); then
    warn "Node.js v$(node --version | sed 's/v//') found but 20+ is recommended."
  fi
fi

if ! $PREREQ_OK; then
  fail "Missing prerequisites. Install them and re-run."
  exit 1
fi

# Verify az login
if ! az account show &>/dev/null; then
  warn "Not logged in to Azure CLI."
  info "Running: az login"
  az login
fi
ok "Azure CLI authenticated: $(az account show --query name -o tsv)"

# Verify azd login
if ! azd auth login --check-status &>/dev/null 2>&1; then
  warn "Not logged in to azd."
  info "Running: azd auth login"
  azd auth login
fi
ok "azd authenticated"

# Ensure required resource providers are registered (idempotent, skips if already registered)
for provider in Microsoft.App Microsoft.ContainerService; do
  state=$(az provider show --namespace "$provider" --query "registrationState" -o tsv 2>/dev/null || echo "NotRegistered")
  if [[ "$state" != "Registered" ]]; then
    info "Registering resource provider $provider (state: $state)..."
    az provider register --namespace "$provider" --wait
    ok "$provider registered"
  fi
done

# ── Step 1: Environment selection ───────────────────────────────────

step "Step 1: Azure environment selection"

# Check existing environments
EXISTING_ENVS=$(azd env list --output json 2>/dev/null || echo "[]")
ENV_COUNT=$(echo "$EXISTING_ENVS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [[ -n "$AZD_ENV_NAME" ]]; then
  # Explicit --env flag
  info "Using environment from --env flag: $AZD_ENV_NAME"
  USE_ENV="$AZD_ENV_NAME"

elif (( ENV_COUNT > 0 )); then
  echo ""
  info "Found existing azd environment(s):"
  azd env list 2>/dev/null
  echo ""

  DEFAULT_ENV=$(echo "$EXISTING_ENVS" | python3 -c "
import sys, json
envs = json.load(sys.stdin)
default = [e for e in envs if e.get('IsDefault')]
print(default[0]['Name'] if default else envs[0]['Name'])
" 2>/dev/null || echo "")

  if $AUTO_YES; then
    USE_ENV="$DEFAULT_ENV"
    info "Auto-selecting default environment: $USE_ENV"
  else
    choose "What would you like to do?" \
      "Use existing environment: $DEFAULT_ENV" \
      "Delete existing and create new environment" \
      "Create a new separate environment"

    case "$CHOSEN" in
      "Use existing"*)
        USE_ENV="$DEFAULT_ENV"
        ;;
      "Delete existing"*)
        warn "This will destroy all Azure resources in '$DEFAULT_ENV'."
        if confirm "Are you sure?"; then
          info "Tearing down '$DEFAULT_ENV'..."
          azd env select "$DEFAULT_ENV" 2>/dev/null || true
          azd down --force --purge 2>&1 | tail -5 || true
          azd env delete "$DEFAULT_ENV" --yes 2>/dev/null || true
          ok "Old environment deleted."
        else
          info "Aborted."
          exit 0
        fi
        echo -en "${YELLOW}?${NC}  New environment name: "
        read -r USE_ENV
        ;;
      "Create a new"*)
        echo -en "${YELLOW}?${NC}  New environment name: "
        read -r USE_ENV
        ;;
    esac
  fi
else
  if $AUTO_YES; then
    USE_ENV="noc-fabric"
    info "No existing environments. Creating: $USE_ENV"
  else
    echo -en "${YELLOW}?${NC}  No existing environments. Enter a name for the new environment: "
    read -r USE_ENV
  fi
fi

# Validate env name
if [[ -z "$USE_ENV" ]]; then
  fail "Environment name cannot be empty."
  exit 1
fi

# Select or create the environment
if azd env list 2>/dev/null | grep -q "$USE_ENV"; then
  azd env select "$USE_ENV"
  ok "Selected existing environment: $USE_ENV"
else
  azd env new "$USE_ENV"
  ok "Created new environment: $USE_ENV"
fi

# ── Step 2: Configure azure_config.env ──────────────────────────────

step "Step 2: Configuring for Fabric GQL backend"

# Nuke stale config — every deploy starts clean.
# User-configurable values (model names, SKU, admin email) are extracted
# before deletion and re-injected.  AUTO values (resource IDs,
# endpoints, workspace IDs) are always re-discovered from Azure.
if [[ -f "$CONFIG_FILE" ]]; then
  info "Extracting user-set values from existing azure_config.env..."
  while IFS='=' read -r key val; do
    case "$key" in
      MODEL_DEPLOYMENT_NAME|EMBEDDING_MODEL|EMBEDDING_DIMENSIONS|GPT_CAPACITY_1K_TPM|\
      CORS_ORIGINS|FABRIC_CAPACITY_SKU|AZURE_FABRIC_ADMIN)
        val="${val%\"}"; val="${val#\"}"
        val="${val%\'}"; val="${val#\'}"
        export "$key=$val"
        ;;
    esac
  done < <(grep -E '^[A-Z_]+=' "$CONFIG_FILE" 2>/dev/null || true)
  info "Deleting stale azure_config.env (will be regenerated from Azure state)"
  rm -f "$CONFIG_FILE"
fi

# Determine location
if [[ -z "$AZURE_LOC" ]]; then
  # Try to read from existing config or azd env
  AZURE_LOC=$(azd env get-values 2>/dev/null | grep "^AZURE_LOCATION=" | cut -d'"' -f2 || echo "")
  if [[ -z "$AZURE_LOC" ]]; then
    AZURE_LOC="swedencentral"
  fi
  if ! $AUTO_YES; then
    echo -en "${YELLOW}?${NC}  Azure location [${AZURE_LOC}]: "
    read -r loc_input
    if [[ -n "$loc_input" ]]; then AZURE_LOC="$loc_input"; fi
  fi
fi
info "Location: $AZURE_LOC"

# Force Fabric GQL backend
GRAPH_BACKEND=fabric-gql
ok "Location: $AZURE_LOC"
ok "Config will be regenerated from Azure state (no stale values)"

# ── Step 2b: Generate static topology JSON ──────────────────────────
# Builds topology.json from CSVs + graph_schema.yaml so the frontend
# graph visualizer loads instantly without querying Fabric Graph.
# The file lands in graph-query-api/backends/fixtures/ which the
# Dockerfile already COPYs into the container image.

step "Step 2b: Generating static topology JSON"

TOPO_SCRIPT="$PROJECT_ROOT/scripts/generate_topology_json.py"
TOPO_OUTPUT="$PROJECT_ROOT/graph-query-api/backends/fixtures/topology.json"

if [[ -f "$TOPO_SCRIPT" ]]; then
  if command -v uv &>/dev/null; then
    info "Generating topology.json from scenario CSVs..."
    (cd "$PROJECT_ROOT" && uv run python "$TOPO_SCRIPT" --scenario "$SCENARIO_NAME") && ok "topology.json generated → $TOPO_OUTPUT" || warn "Topology generation failed — frontend will fall back to live queries"
  elif command -v python3 &>/dev/null; then
    info "Generating topology.json from scenario CSVs (python3)..."
    (cd "$PROJECT_ROOT" && python3 "$TOPO_SCRIPT" --scenario "$SCENARIO_NAME") && ok "topology.json generated → $TOPO_OUTPUT" || warn "Topology generation failed — frontend will fall back to live queries"
  else
    warn "Neither uv nor python3 found — skipping topology generation"
  fi
else
  warn "Topology generator script not found at $TOPO_SCRIPT — skipping"
fi

# ── Step 3: Deploy infrastructure ───────────────────────────────────

if $SKIP_INFRA; then
  step "Step 3: Infrastructure provisioning (SKIPPED)"
  info "Using existing Azure resources."

  if $SKIP_APP; then
    info "App container deploy also skipped (--skip-app)."
  else
    # Still deploy the app container (rebuild + push image)
    info "Deploying app container..."

    # Ensure uv.lock files exist for Docker builds (--frozen requires them)
    for svc_dir in api graph-query-api; do
      if [[ -f "$PROJECT_ROOT/$svc_dir/pyproject.toml" && ! -f "$PROJECT_ROOT/$svc_dir/uv.lock" ]]; then
        info "Generating missing uv.lock for $svc_dir..."
        (cd "$PROJECT_ROOT/$svc_dir" && uv lock)
        ok "$svc_dir/uv.lock created"
      fi
    done

    if ! azd deploy app --no-prompt; then
      fail "azd deploy app failed."
      exit 1
    fi
    ok "App container deployed!"
  fi
else
  step "Step 3: Deploying Azure infrastructure (azd up)"

  info "This will provision:"
  echo "   • Resource Group"
  echo "   • AI Foundry (account + project + GPT-4.1 deployment)"
  echo "   • Azure AI Search"
  echo "   • Storage Account"
  echo "   • Cosmos DB NoSQL (interactions store)"
  echo "   • Container Apps Environment (ACR + Log Analytics)"
  echo "   • Unified Container App (nginx + API + graph-query-api)"
  echo ""

  if ! $AUTO_YES; then
    if ! confirm "Proceed with infrastructure deployment?"; then
      info "Skipping infrastructure. Re-run with --skip-infra to use existing."
      exit 0
    fi
  fi

  # Set essential azd env vars
  azd env set AZURE_LOCATION "$AZURE_LOC"
  azd env set GRAPH_BACKEND "fabric-gql"
  azd env set GPT_CAPACITY_1K_TPM "${GPT_CAPACITY_1K_TPM:-300}"
  azd env set DEFAULT_SCENARIO "$SCENARIO_NAME"
  azd env set RUNBOOKS_INDEX_NAME "$RUNBOOKS_INDEX_NAME"
  azd env set TICKETS_INDEX_NAME "$TICKETS_INDEX_NAME"

  # Auto-detect dev IP for Cosmos DB firewall whitelist
  if [[ -z "${DEV_IP_ADDRESS:-}" ]]; then
    info "Detecting dev machine IP for Cosmos DB firewall..."
    DEV_IP_ADDRESS=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || true)
    if [[ -n "$DEV_IP_ADDRESS" ]]; then
      export DEV_IP_ADDRESS
      ok "Dev IP: $DEV_IP_ADDRESS (will be added to Cosmos DB firewall)"
    else
      warn "Could not detect dev IP — Cosmos DB will only be accessible from VNet"
    fi
  else
    export DEV_IP_ADDRESS
    ok "Using DEV_IP_ADDRESS=$DEV_IP_ADDRESS for Cosmos DB firewall"
  fi

  # Ensure uv.lock files exist for Docker builds (--frozen requires them)
  for svc_dir in api graph-query-api; do
    if [[ -f "$PROJECT_ROOT/$svc_dir/pyproject.toml" && ! -f "$PROJECT_ROOT/$svc_dir/uv.lock" ]]; then
      info "Generating missing uv.lock for $svc_dir..."
      (cd "$PROJECT_ROOT/$svc_dir" && uv lock)
      ok "$svc_dir/uv.lock created"
    fi
  done

  info "Running azd up (this may take 10-15 minutes)..."
  echo ""

  # azd up runs: preprovision → Bicep → deploy unified app → postprovision
  if ! azd up; then
    fail "azd up failed. Check the output above for errors."
    fail "Common issues:"
    echo "   • Quota exceeded — try a different location"
    echo "   • Soft-deleted resources — run: azd down --purge, then retry"
    echo "   • Name conflict — use a different --env name"
    exit 1
  fi

  ok "Infrastructure deployed!"

  # Reload config (postprovision.sh should have populated it)
  if [[ -f "$CONFIG_FILE" ]]; then
    set -a; source "$CONFIG_FILE"; set +a
  fi
fi

# ── Step 3b: Auto-discover / verify resource config ─────────────────
# Always runs — handles: skip-infra, no-Bicep-changes (postprovision skipped),
# deleted azure_config.env, or partial postprovision population.

step "Step 3b: Verifying & discovering Azure resource configuration"

# Determine resource group from config, azd env, or convention
RG="${AZURE_RESOURCE_GROUP:-}"
if [[ -z "$RG" ]]; then
  AZD_ENV=$(azd env get-values 2>/dev/null | grep "^AZURE_ENV_NAME=" | cut -d'"' -f2 || true)
  if [[ -n "$AZD_ENV" ]]; then
    RG="rg-${AZD_ENV}"
  fi
fi

if [[ -z "$RG" ]]; then
  fail "Cannot determine resource group. Set AZURE_RESOURCE_GROUP or ensure azd env is configured."
  exit 1
fi

AZURE_RESOURCE_GROUP="$RG"

# Check if critical values are missing
if [[ -z "${AI_FOUNDRY_NAME:-}" || -z "${AI_SEARCH_NAME:-}" || -z "${APP_URI:-}" || -z "${STORAGE_ACCOUNT_NAME:-}" ]]; then
  info "One or more resource values missing — running auto-discovery from $RG..."
  discover_resources_from_rg "$RG"
else
  ok "All critical config values already present"
fi

# Write the fully resolved azure_config.env
info "Writing azure_config.env..."
cat > "$CONFIG_FILE" <<CONFIGEOF
# ============================================================================
# Autonomous Network NOC Demo — Configuration (Fabric GQL Flow)
# ============================================================================
# Generated by deploy.sh at $(date -u +%Y-%m-%dT%H:%M:%SZ)
# GRAPH_BACKEND=fabric-gql — graph queries use GQL via Microsoft Fabric
# ============================================================================

# --- Scenario ---
DEFAULT_SCENARIO=${DEFAULT_SCENARIO:-telecom-playground}

# --- Core Azure settings (AUTO: from deployment/discovery) ---
AZURE_SUBSCRIPTION_ID=${AZURE_SUBSCRIPTION_ID:-}
AZURE_RESOURCE_GROUP=${AZURE_RESOURCE_GROUP:-}
AZURE_LOCATION=${AZURE_LOC}

# --- AI Foundry (AUTO: from deployment/discovery) ---
AI_FOUNDRY_NAME=${AI_FOUNDRY_NAME:-}
AI_FOUNDRY_ENDPOINT=${AI_FOUNDRY_ENDPOINT:-}
AI_FOUNDRY_PROJECT_NAME=${AI_FOUNDRY_PROJECT_NAME:-}
PROJECT_ENDPOINT=${PROJECT_ENDPOINT:-}

# --- Model deployments (USER) ---
MODEL_DEPLOYMENT_NAME=${MODEL_DEPLOYMENT_NAME:-gpt-4.1}
EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-small}
EMBEDDING_DIMENSIONS=${EMBEDDING_DIMENSIONS:-1536}
GPT_CAPACITY_1K_TPM=${GPT_CAPACITY_1K_TPM:-300}

# --- Azure AI Search (AUTO: from deployment/discovery) ---
AI_SEARCH_NAME=${AI_SEARCH_NAME:-}
RUNBOOKS_INDEX_NAME=${RUNBOOKS_INDEX_NAME:-runbooks-index}
TICKETS_INDEX_NAME=${TICKETS_INDEX_NAME:-tickets-index}

# --- Azure Storage (AUTO: from deployment/discovery) ---
STORAGE_ACCOUNT_NAME=${STORAGE_ACCOUNT_NAME:-}

# --- App / CORS (USER) ---
CORS_ORIGINS=${CORS_ORIGINS:-http://localhost:5173}

# --- Graph Backend ---
GRAPH_BACKEND=${GRAPH_BACKEND:-fabric-gql}

# --- Topology Source (static = pre-built JSON, live = query graph) ---
TOPOLOGY_SOURCE=static

# --- Unified app (AUTO: from deployment/discovery) ---
APP_URI=${APP_URI:-}
APP_PRINCIPAL_ID=${APP_PRINCIPAL_ID:-}
GRAPH_QUERY_API_URI=${GRAPH_QUERY_API_URI:-}

# --- Cosmos DB NoSQL / Interactions (AUTO: from deployment/discovery) ---
COSMOS_NOSQL_ENDPOINT=${COSMOS_NOSQL_ENDPOINT:-}

# --- Fabric Admin & Capacity (USER/AUTO) ---
AZURE_FABRIC_ADMIN=${AZURE_FABRIC_ADMIN:-}
FABRIC_CAPACITY_SKU=${FABRIC_CAPACITY_SKU:-F8}

# --- Fabric Resources ---
# Graph Model ID, Eventhouse Query URI, and KQL DB name are
# discovered at runtime by graph-query-api/fabric_discovery.py.
FABRIC_CAPACITY_ID=${FABRIC_CAPACITY_ID:-}
FABRIC_WORKSPACE_ID=${FABRIC_WORKSPACE_ID:-}
FABRIC_LAKEHOUSE_ID=${FABRIC_LAKEHOUSE_ID:-}
FABRIC_EVENTHOUSE_ID=${FABRIC_EVENTHOUSE_ID:-}
FABRIC_KQL_DB_ID=${FABRIC_KQL_DB_ID:-}
FABRIC_KQL_DB_NAME=${FABRIC_KQL_DB_NAME:-}
EVENTHOUSE_QUERY_URI=${EVENTHOUSE_QUERY_URI:-}
CONFIGEOF

ok "azure_config.env written"
set -a; source "$CONFIG_FILE"; set +a

# Final verification — warn but don't exit (user may be doing partial re-deploy)
MISSING_VARS=()
[[ -z "${AI_FOUNDRY_NAME:-}" ]]       && MISSING_VARS+=("AI_FOUNDRY_NAME")
[[ -z "${AI_SEARCH_NAME:-}" ]]        && MISSING_VARS+=("AI_SEARCH_NAME")
[[ -z "${STORAGE_ACCOUNT_NAME:-}" ]]  && MISSING_VARS+=("STORAGE_ACCOUNT_NAME")
[[ -z "${APP_URI:-}" ]]               && MISSING_VARS+=("APP_URI")
[[ -z "${PROJECT_ENDPOINT:-}" ]]      && MISSING_VARS+=("PROJECT_ENDPOINT")

if (( ${#MISSING_VARS[@]} > 0 )); then
  warn "These values are still missing after discovery:"
  for v in "${MISSING_VARS[@]}"; do echo "   • $v"; done
  warn "Resources may not exist yet. Run without --skip-infra to provision them."
else
  ok "All critical config values populated"
  info "App URI: $APP_URI"
fi

# ── Step 4: Fabric Provisioning (optional) ──────────────────────────

if $PROVISION_FABRIC; then
  step "Step 4: Provisioning Fabric resources"

  # 4a: Find-or-create workspace, wait for it, write FABRIC_WORKSPACE_ID.
  #     This MUST run first — every downstream step needs the workspace.
  info "4a: Ensuring Fabric workspace exists..."
  if ! (source "$CONFIG_FILE" && uv run python scripts/fabric/provision_workspace.py); then
    fail "Workspace provisioning failed — cannot continue with Fabric."
    exit 1
  fi

  # Re-source to pick up FABRIC_WORKSPACE_ID written by provision_workspace.py
  set -a; source "$CONFIG_FILE"; set +a
  FABRIC_WS_ID="${FABRIC_WORKSPACE_ID:-}"

  if [[ -z "$FABRIC_WS_ID" ]]; then
    fail "FABRIC_WORKSPACE_ID still empty after workspace provisioning — aborting."
    exit 1
  fi
  ok "Workspace ready: $FABRIC_WS_ID"

  # 4b: Grant Container App Contributor access to Fabric workspace
  info "4b: Fabric workspace RBAC..."
  CA_PRINCIPAL="${APP_PRINCIPAL_ID:-}"

  if [[ -z "$CA_PRINCIPAL" ]]; then
    warn "APP_PRINCIPAL_ID not set — skipping Fabric RBAC."
    info "Run 'azd up' first to provision the Container App."
  else
    info "Granting Container App ($CA_PRINCIPAL) Contributor access to Fabric workspace..."
    FABRIC_TOKEN=$(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv 2>/dev/null || true)
    if [[ -z "$FABRIC_TOKEN" ]]; then
      warn "Could not get Fabric API token — skipping. Grant access manually in the Fabric portal."
    else
      HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "https://api.fabric.microsoft.com/v1/workspaces/${FABRIC_WS_ID}/roleAssignments" \
        -H "Authorization: Bearer $FABRIC_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"principal\":{\"id\":\"${CA_PRINCIPAL}\",\"type\":\"ServicePrincipal\"},\"role\":\"Contributor\"}" 2>/dev/null || echo "000")
      if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "201" ]]; then
        ok "Container App granted Contributor on Fabric workspace"
      elif [[ "$HTTP_CODE" == "409" ]]; then
        ok "Container App already has access to Fabric workspace"
      else
        warn "Fabric RBAC assignment returned HTTP $HTTP_CODE"
        info "You may need to grant access manually:"
        echo "   Fabric portal → workspace → Manage access → Add '$CA_PRINCIPAL' as Contributor"
      fi
    fi
  fi

  # 4c–4e: Provision Fabric items (workspace guaranteed to exist with ID set)
  info "4c: Provisioning Lakehouse..."
  (source "$CONFIG_FILE" && uv run python scripts/fabric/provision_lakehouse.py) || warn "Lakehouse provisioning failed"

  info "4d: Provisioning Eventhouse..."
  (source "$CONFIG_FILE" && uv run python scripts/fabric/provision_eventhouse.py) || warn "Eventhouse provisioning failed"

  info "4e: Provisioning Ontology + Graph Model..."
  (source "$CONFIG_FILE" && uv run python scripts/fabric/provision_ontology.py) || warn "Ontology provisioning failed"

  # 4f: Re-populate config to capture any NEW resource IDs created above
  info "4f: Re-populating Fabric config (capture new resource IDs)..."
  (source "$CONFIG_FILE" && uv run python scripts/fabric/populate_fabric_config.py) || warn "Config re-population failed"
  set -a; source "$CONFIG_FILE"; set +a

  # NOTE: Graph Model ID, Eventhouse Query URI, and KQL DB name are
  # discovered at runtime by graph-query-api/fabric_discovery.py.
  # However, FABRIC_WORKSPACE_ID MUST be synced to the Container App
  # (see Step 6b) — discovery needs it as the bootstrap value.

  ok "Fabric provisioning complete"
else
  step "Step 4: Fabric Provisioning (SKIPPED — use --provision-fabric)"
fi

# ── Step 5: Data Provisioning (optional) ────────────────────────────

if $PROVISION_DATA; then
  step "Step 5: Provisioning data"

  info "5a: Creating AI Search indexes..."
  (source "$CONFIG_FILE" && uv run python scripts/provision_search_index.py --upload-files) || warn "Search index provisioning failed"

  ok "Data provisioning complete"
else
  step "Step 5: Data Provisioning (SKIPPED — use --provision-data)"
fi

# ── Step 6: Agent Provisioning (optional) ───────────────────────────

if $PROVISION_AGENTS; then
  step "Step 6: Provisioning AI Foundry agents"

  (source "$CONFIG_FILE" && uv run python scripts/provision_agents.py) || warn "Agent provisioning failed"

  ok "Agent provisioning complete — container app will discover agents at runtime"
else
  step "Step 6: Agent Provisioning (SKIPPED — use --provision-agents)"
fi

# ── Step 6b: Sync azure_config.env → azd env → Container App ────────
# After Fabric provisioning (Step 4) populates azure_config.env with
# discovered IDs (workspace, eventhouse, graph model, etc.), those values
# must be pushed into azd env so that `azd provision` can inject them
# into the Container App's environment variables via Bicep.
#
# Without this step, the Container App keeps stale values from the
# initial `azd up` run when Fabric resources didn't exist yet.

step "Step 6b: Syncing azure_config.env → Container App env vars"

# Reload the latest azure_config.env (may have been updated by Step 4)
if [[ -f "$CONFIG_FILE" ]]; then
  set -a; source "$CONFIG_FILE"; set +a
fi

# List of vars that azure_config.env may update after initial azd up.
# These MUST be pushed into azd env so Bicep can inject them into the
# Container App.  Add new vars here as needed.
SYNC_VARS=(
  FABRIC_WORKSPACE_ID
)

SYNC_NEEDED=false
for var in "${SYNC_VARS[@]}"; do
  LOCAL_VAL="${!var:-}"
  AZD_VAL=$(azd env get-values 2>/dev/null | grep "^${var}=" | cut -d'"' -f2 || true)
  if [[ -n "$LOCAL_VAL" && "$LOCAL_VAL" != "$AZD_VAL" ]]; then
    info "  Syncing $var → azd env  ($AZD_VAL → $LOCAL_VAL)"
    azd env set "$var" "$LOCAL_VAL"
    SYNC_NEEDED=true
  fi
done

if $SYNC_NEEDED; then
  info "Env vars changed — running azd provision to update Container App..."
  if azd provision --no-prompt; then
    ok "Container App env vars updated"
  else
    warn "azd provision failed — Container App may have stale env vars"
    warn "You can manually fix with: azd env set FABRIC_WORKSPACE_ID <correct-id> && azd provision --no-prompt"
  fi
else
  ok "azd env already in sync with azure_config.env"
fi

# ── Step 7: Verify unified app health ───────────────────────────────

step "Step 7: Verifying unified app deployment"

GQ_URI="${APP_URI:-}"
if [[ -z "$GQ_URI" ]]; then
  fail "APP_URI not set — cannot verify deployment."
  exit 1
fi

info "Checking health at $GQ_URI/health ..."

HEALTH_OK=false
for attempt in 1 2 3 4 5; do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$GQ_URI/health" 2>/dev/null || echo "000")
  if [[ "$HTTP_CODE" == "200" ]]; then
    HEALTH_OK=true
    break
  fi
  if (( attempt < 5 )); then
    warn "Attempt $attempt: HTTP $HTTP_CODE — waiting 15s for container to start..."
    sleep 15
  fi
done

if $HEALTH_OK; then
  ok "App is healthy"
else
  fail "App not responding after 5 attempts."
  fail "The Container App may still be starting or the image build may have failed."
  echo ""
  info "Debug commands:"
  echo "   az containerapp logs show --name <ca-name> --resource-group ${AZURE_RESOURCE_GROUP:-} --type console --tail 50"
  echo "   azd deploy app"
  warn "Continuing anyway — agent provisioning may fail if the API is down."
fi

# ── Step 8: Start local services (optional — all services deployed to Azure) ──

if $SKIP_LOCAL; then
  step "Step 8: Local services (SKIPPED)"
  echo ""
  ok "Deployment complete! All services are running in Azure."
  echo ""
  echo "   App URL:   ${APP_URI:-<check azure_config.env>}"
  echo ""
  echo "   To run locally instead:"
  echo "   # Terminal 1 — API"
  echo "   cd api && source ../azure_config.env && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
  echo ""
  echo "   # Terminal 2 — Graph Query API"
  echo "   cd graph-query-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload"
  echo ""
  echo "   # Terminal 3 — Frontend"
  echo "   cd frontend && npm install && npm run dev"
  echo ""
  echo "   Open http://localhost:5173"
else
  step "Step 8: Starting local API + Frontend"

  # Kill any existing processes on our ports
  lsof -ti:8000,8100,5173 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  sleep 1

  # Install frontend deps
  info "Installing frontend dependencies..."
  (cd frontend && npm install --silent 2>&1 | tail -3) || true

  # Ensure API venv is synced (recreate if shebang points to stale path)
  info "Syncing API dependencies..."
  if [[ -f "$PROJECT_ROOT/api/.venv/bin/uvicorn" ]]; then
    SHEBANG_PYTHON=$(head -1 "$PROJECT_ROOT/api/.venv/bin/uvicorn" | sed 's/^#!//')
    if [[ ! -x "$SHEBANG_PYTHON" ]]; then
      warn "Stale API venv detected (python not found at $SHEBANG_PYTHON) — recreating..."
      rm -rf "$PROJECT_ROOT/api/.venv"
    fi
  fi
  (cd "$PROJECT_ROOT/api" && uv sync --quiet 2>&1) || true

  # Start API in background
  info "Starting API on port 8000..."
  (cd "$PROJECT_ROOT/api" && source "$CONFIG_FILE" && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
  API_PID=$!

  # Wait for API to be ready
  info "Waiting for API to start..."
  for i in $(seq 1 15); do
    if curl -s http://localhost:8000/health &>/dev/null; then
      ok "API is running (PID $API_PID)"
      break
    fi
    if (( i == 15 )); then
      fail "API did not start within 15 seconds."
      kill $API_PID 2>/dev/null || true
      exit 1
    fi
    sleep 1
  done

  # Start frontend in background
  info "Starting frontend on port 5173..."
  (cd "$PROJECT_ROOT/frontend" && npm run dev) &
  FE_PID=$!

  # Wait for frontend
  sleep 3
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>/dev/null | grep -q "200"; then
    ok "Frontend is running (PID $FE_PID)"
  else
    warn "Frontend may still be starting..."
  fi

  # Register cleanup
  trap "info 'Shutting down...'; kill $API_PID $FE_PID 2>/dev/null; exit 0" INT TERM

  echo ""
fi

# ── Summary ─────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Deployment Complete!                                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "  ${BOLD}Environment:${NC}      $USE_ENV"
echo -e "  ${BOLD}Graph Backend:${NC}    fabric-gql (GQL via Fabric)"
echo -e "  ${BOLD}Data Loading:${NC}     Via provisioning scripts (--provision-data)"
echo -e "  ${BOLD}Location:${NC}         ${AZURE_LOC}"
echo -e "  ${BOLD}Resource Group:${NC}   ${AZURE_RESOURCE_GROUP:-<pending>}"
echo ""
echo -e "  ${BOLD}Azure Services:${NC}"
echo "    AI Foundry:       ${AI_FOUNDRY_NAME:-<pending>}"
echo "    AI Search:        ${AI_SEARCH_NAME:-<pending>}"
echo "    Storage:          ${STORAGE_ACCOUNT_NAME:-<pending>}"
echo "    Cosmos DB (NoSQL): ${COSMOS_NOSQL_ENDPOINT:-<pending>}"
echo "    App URL:          ${APP_URI:-<pending>}"
echo ""

echo -e "  ${BOLD}Agents:${NC}"
echo "    Agents are discovered from AI Foundry at runtime (no agent_ids.json needed)."
echo "    Provisioned agents: GraphExplorerAgent, TelemetryAgent, RunbookKBAgent,"
echo "                        HistoricalTicketAgent, Orchestrator"
echo ""

if ! $SKIP_LOCAL; then
  echo -e "  ${BOLD}Local Services:${NC}"
  echo "    API:       http://localhost:8000"
  echo "    Frontend:  http://localhost:5173"
  echo ""
  echo -e "  ${BOLD}Test:${NC}"
  echo "    Open http://localhost:5173 and paste an alert:"
  echo "    14:31:14.259 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable"
  echo ""
  echo -e "  ${BOLD}CLI test:${NC}"
  echo "    source azure_config.env && uv run python scripts/testing_scripts/test_orchestrator.py"
  echo ""
  echo "  Press Ctrl+C to stop local services."
  wait
fi

echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo "    azd deploy app                     # Redeploy unified app after code changes"
echo "    source azure_config.env && uv run python scripts/provision_agents.py --force  # Re-provision agents"
echo "    azd down --force --purge           # Tear down all Azure resources"
echo ""
echo -e "  ${BOLD}Provisioning:${NC}"
echo "    ./deploy.sh --provision-fabric     # Provision Fabric resources"
echo "    ./deploy.sh --provision-data       # Provision AI Search indexes"
echo "    ./deploy.sh --provision-agents     # Provision AI agents"
echo "    ./deploy.sh --provision-all        # Do all of the above"
echo ""
