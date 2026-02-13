#!/usr/bin/env bash
# ============================================================================
# Autonomous Network NOC Demo — Per-Environment Deployment Script
# ============================================================================
#
# Like deploy.sh, but each azd environment gets its OWN config file under
# envs/{env-name}.env.  A symlink azure_config.env → envs/{name}.env ensures
# hooks and Python scripts work unchanged.  This prevents cross-environment
# config contamination when switching between deployments.
#
# Usage:
#   chmod +x deploy_app.sh
#   ./deploy_app.sh --env cosmosprod5 --location eastus2
#   ./deploy_app.sh --env-file envs/cosmosprod5.env   # reuse existing env file
#
# Options:
#   --env NAME         azd environment name (creates envs/{NAME}.env if needed)
#   --env-file PATH    Use an existing env file (derives env name from filename)
#   --skip-infra       Skip azd up (reuse existing Azure resources)
#   --skip-index       Skip AI Search index creation
#   --skip-data        Skip Cosmos DB data loading
#   --skip-agents      Skip agent provisioning
#   --skip-local       Skip starting local API + frontend
#   --location LOC     Azure location (default: swedencentral)
#   --yes              Skip all confirmation prompts
#
# Environment file lifecycle:
#   1. First deploy:  template → envs/{name}.env (fresh, no stale values)
#   2. azd up:        postprovision.sh writes outputs → azure_config.env (symlink)
#   3. Re-deploy:     same env file is re-used, preserving populated values
#   4. Switch envs:   ./deploy_app.sh --env other-env  (symlink moves, no contamination)
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
  echo "║  Autonomous Network NOC Demo — Per-Environment Deployment    ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo -e "${NC}"
}

# ── Parse arguments ─────────────────────────────────────────────────

SKIP_INFRA=false
SKIP_INDEX=false
SKIP_DATA=false
SKIP_AGENTS=false
SKIP_LOCAL=false
AUTO_YES=false
AZD_ENV_NAME=""
ENV_FILE_ARG=""
AZURE_LOC=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-infra)   SKIP_INFRA=true; shift ;;
    --skip-index)   SKIP_INDEX=true; shift ;;
    --skip-data)    SKIP_DATA=true; shift ;;
    --skip-agents)  SKIP_AGENTS=true; shift ;;
    --skip-local)   SKIP_LOCAL=true; shift ;;
    --yes|-y)       AUTO_YES=true; shift ;;
    --env)          AZD_ENV_NAME="$2"; shift 2 ;;
    --env-file)     ENV_FILE_ARG="$2"; shift 2 ;;
    --location)     AZURE_LOC="$2"; shift 2 ;;
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

ENVS_DIR="$PROJECT_ROOT/envs"
SYMLINK_PATH="$PROJECT_ROOT/azure_config.env"
TEMPLATE_FILE="$PROJECT_ROOT/azure_config.env.template"
AGENT_IDS_FILE="$PROJECT_ROOT/scripts/agent_ids.json"

mkdir -p "$ENVS_DIR"

# ── Helper: prompt user ────────────────────────────────────────────

confirm() {
  local msg="$1"
  if $AUTO_YES; then return 0; fi
  echo -en "${YELLOW}?${NC}  ${msg} [y/N] "
  read -r answer
  [[ "$answer" =~ ^[Yy] ]]
}

choose() {
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

# ══════════════════════════════════════════════════════════════════════
# Step 0: Prerequisites
# ══════════════════════════════════════════════════════════════════════

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
    return 1
  fi
}

install_uv() {
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
}

install_node() {
  info "Installing Node.js 20 via nvm..."
  if ! command -v nvm &>/dev/null; then
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

# ── Check each prerequisite ────────────────────────────────────────

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

# Version checks
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 11) )); then
    fail "Python $PY_VER found but 3.11+ is required."
    PREREQ_OK=false
  fi
fi

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

# Azure auth
if ! az account show &>/dev/null; then
  warn "Not logged in to Azure CLI."
  info "Running: az login"
  az login
fi
ok "Azure CLI authenticated: $(az account show --query name -o tsv)"

if ! azd auth login --check-status &>/dev/null 2>&1; then
  warn "Not logged in to azd."
  info "Running: azd auth login"
  azd auth login
fi
ok "azd authenticated"

# Resource providers
for provider in Microsoft.App Microsoft.ContainerService; do
  state=$(az provider show --namespace "$provider" --query "registrationState" -o tsv 2>/dev/null || echo "NotRegistered")
  if [[ "$state" != "Registered" ]]; then
    info "Registering resource provider $provider (state: $state)..."
    az provider register --namespace "$provider" --wait
    ok "$provider registered"
  fi
done

# ══════════════════════════════════════════════════════════════════════
# Step 1: Environment + env file resolution
# ══════════════════════════════════════════════════════════════════════

step "Step 1: Environment + config file resolution"

# --- Case A: --env-file provided — derive env name from filename ---
if [[ -n "$ENV_FILE_ARG" ]]; then
  if [[ ! -f "$ENV_FILE_ARG" ]]; then
    fail "Env file not found: $ENV_FILE_ARG"
    exit 1
  fi
  # Resolve to absolute path
  ENV_FILE="$(cd "$(dirname "$ENV_FILE_ARG")" && pwd)/$(basename "$ENV_FILE_ARG")"
  # Derive env name from filename (strip path and .env suffix)
  USE_ENV="$(basename "$ENV_FILE" .env)"
  info "Using provided env file: $ENV_FILE"
  info "Derived environment name: $USE_ENV"

# --- Case B: --env provided — look for or create envs/{name}.env ---
elif [[ -n "$AZD_ENV_NAME" ]]; then
  USE_ENV="$AZD_ENV_NAME"
  ENV_FILE="$ENVS_DIR/${USE_ENV}.env"

# --- Case C: Interactive — list existing envs or prompt ---
else
  # List existing env files in envs/
  EXISTING_ENV_FILES=()
  if [[ -d "$ENVS_DIR" ]]; then
    while IFS= read -r -d '' f; do
      EXISTING_ENV_FILES+=("$(basename "$f" .env)")
    done < <(find "$ENVS_DIR" -maxdepth 1 -name '*.env' -print0 2>/dev/null | sort -z)
  fi

  if (( ${#EXISTING_ENV_FILES[@]} > 0 )); then
    echo ""
    info "Found existing environment config files:"
    for ef in "${EXISTING_ENV_FILES[@]}"; do
      # Show whether the azd env exists too
      AZD_EXISTS=""
      if azd env list 2>/dev/null | grep -q "$ef"; then
        AZD_EXISTS=" (azd env exists)"
      fi
      echo "     • $ef$AZD_EXISTS"
    done
    echo ""

    OPTIONS=()
    for ef in "${EXISTING_ENV_FILES[@]}"; do
      OPTIONS+=("Use existing: $ef")
    done
    OPTIONS+=("Create a new environment")

    if $AUTO_YES; then
      USE_ENV="${EXISTING_ENV_FILES[0]}"
      info "Auto-selecting first environment: $USE_ENV"
    else
      choose "Select an environment:" "${OPTIONS[@]}"
      if [[ "$CHOSEN" == "Create a new"* ]]; then
        echo -en "${YELLOW}?${NC}  New environment name: "
        read -r USE_ENV
      else
        # Extract env name from "Use existing: {name}"
        USE_ENV="${CHOSEN#Use existing: }"
      fi
    fi
  else
    if $AUTO_YES; then
      USE_ENV="noc-cosmosdb"
      info "No existing environments. Creating: $USE_ENV"
    else
      echo -en "${YELLOW}?${NC}  No existing environments. Enter a name: "
      read -r USE_ENV
    fi
  fi

  ENV_FILE="$ENVS_DIR/${USE_ENV}.env"
fi

# Validate env name
if [[ -z "$USE_ENV" ]]; then
  fail "Environment name cannot be empty."
  exit 1
fi

# --- Create env file from template if it doesn't exist ---
if [[ ! -f "$ENV_FILE" ]]; then
  info "Creating fresh config: $ENV_FILE (from template)"
  if [[ ! -f "$TEMPLATE_FILE" ]]; then
    fail "Template not found: $TEMPLATE_FILE"
    exit 1
  fi
  cp "$TEMPLATE_FILE" "$ENV_FILE"
  ok "Config created from template (no stale values)"
else
  ok "Using existing config: $ENV_FILE"
fi

# --- Create/update symlink: azure_config.env → envs/{name}.env ---
# Remove existing file or symlink
if [[ -e "$SYMLINK_PATH" ]] || [[ -L "$SYMLINK_PATH" ]]; then
  OLD_TARGET=""
  if [[ -L "$SYMLINK_PATH" ]]; then
    OLD_TARGET="$(readlink "$SYMLINK_PATH")"
  fi
  rm -f "$SYMLINK_PATH"
  if [[ -n "$OLD_TARGET" && "$OLD_TARGET" != "$ENV_FILE" ]]; then
    info "Switched from: $OLD_TARGET"
  fi
fi

ln -s "$ENV_FILE" "$SYMLINK_PATH"
ok "azure_config.env → $(basename "$ENV_FILE")"

# --- Select or create the azd environment ---
if azd env list 2>/dev/null | grep -q "$USE_ENV"; then
  azd env select "$USE_ENV"
  ok "azd environment selected: $USE_ENV"
else
  azd env new "$USE_ENV"
  ok "azd environment created: $USE_ENV"
fi

# ══════════════════════════════════════════════════════════════════════
# Step 2: Configure env file
# ══════════════════════════════════════════════════════════════════════

step "Step 2: Configuring for Cosmos DB backend"

# Load current values
set -a; source "$ENV_FILE"; set +a

# Determine location
if [[ -z "$AZURE_LOC" ]]; then
  AZURE_LOC="${AZURE_LOCATION:-}"
  if [[ -z "$AZURE_LOC" ]]; then
    AZURE_LOC=$(azd env get-values 2>/dev/null | grep "^AZURE_LOCATION=" | cut -d'"' -f2 || echo "")
  fi
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

# Patch location into the env file (update in-place)
if grep -q "^AZURE_LOCATION=" "$ENV_FILE"; then
  sed -i "s|^AZURE_LOCATION=.*|AZURE_LOCATION=${AZURE_LOC}|" "$ENV_FILE"
else
  echo "AZURE_LOCATION=${AZURE_LOC}" >> "$ENV_FILE"
fi

# Ensure GRAPH_BACKEND=cosmosdb
if grep -q "^GRAPH_BACKEND=" "$ENV_FILE"; then
  sed -i "s|^GRAPH_BACKEND=.*|GRAPH_BACKEND=cosmosdb|" "$ENV_FILE"
else
  echo "GRAPH_BACKEND=cosmosdb" >> "$ENV_FILE"
fi

# Reload after patching
set -a; source "$ENV_FILE"; set +a

ok "Config: $ENV_FILE (GRAPH_BACKEND=cosmosdb, AZURE_LOCATION=$AZURE_LOC)"

# ══════════════════════════════════════════════════════════════════════
# Step 3: Deploy infrastructure
# ══════════════════════════════════════════════════════════════════════

if $SKIP_INFRA; then
  step "Step 3: Infrastructure deployment (SKIPPED)"
  info "Using existing Azure resources. Loading config..."
  set -a; source "$ENV_FILE"; set +a
else
  step "Step 3: Deploying Azure infrastructure (azd up)"

  info "Environment:  $USE_ENV"
  info "Config file:  envs/$(basename "$ENV_FILE")"
  info "Location:     $AZURE_LOC"
  echo ""
  info "This will provision:"
  echo "   • Resource Group"
  echo "   • AI Foundry (account + project + GPT-4.1 deployment)"
  echo "   • Azure AI Search"
  echo "   • Storage Account (runbooks + tickets blob containers)"
  echo "   • Cosmos DB Gremlin (database: networkgraph, graph: topology)"
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
  azd env set GRAPH_BACKEND "cosmosdb"
  azd env set GPT_CAPACITY_1K_TPM "${GPT_CAPACITY_1K_TPM:-300}"

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

  info "Running azd up (this may take 10-15 minutes)..."
  echo ""

  if ! azd up; then
    fail "azd up failed. Check the output above for errors."
    fail "Common issues:"
    echo "   • Quota exceeded — try a different location"
    echo "   • Soft-deleted resources — run: azd down --purge, then retry"
    echo "   • Name conflict — use a different --env name"
    exit 1
  fi

  ok "Infrastructure deployed!"

  # Reload config (postprovision.sh wrote outputs → azure_config.env → envs/{name}.env)
  set -a; source "$ENV_FILE"; set +a

  # Verify critical values were populated
  MISSING_AFTER_AZD=()
  [[ -z "${AI_SEARCH_NAME:-}" ]]          && MISSING_AFTER_AZD+=("AI_SEARCH_NAME")
  [[ -z "${STORAGE_ACCOUNT_NAME:-}" ]]    && MISSING_AFTER_AZD+=("STORAGE_ACCOUNT_NAME")
  [[ -z "${AI_FOUNDRY_NAME:-}" ]]         && MISSING_AFTER_AZD+=("AI_FOUNDRY_NAME")
  [[ -z "${PROJECT_ENDPOINT:-}" ]]        && MISSING_AFTER_AZD+=("PROJECT_ENDPOINT")
  [[ -z "${APP_URI:-}" ]]                  && MISSING_AFTER_AZD+=("APP_URI")
  [[ -z "${COSMOS_GREMLIN_ENDPOINT:-}" ]] && MISSING_AFTER_AZD+=("COSMOS_GREMLIN_ENDPOINT")

  if (( ${#MISSING_AFTER_AZD[@]} > 0 )); then
    fail "azd up completed but these values are missing from envs/$(basename "$ENV_FILE"):"
    for v in "${MISSING_AFTER_AZD[@]}"; do echo "   • $v"; done
    fail "Check postprovision.sh output. You may need to set them manually."
    exit 1
  fi

  ok "All critical config values populated"
  info "Cosmos DB endpoint: $COSMOS_GREMLIN_ENDPOINT"
  info "App URI:            $APP_URI"
fi

# ══════════════════════════════════════════════════════════════════════
# Step 3b: Cosmos DB firewall for local dev
# ══════════════════════════════════════════════════════════════════════

step "Step 3b: Configuring Cosmos DB firewall for local access"

DEV_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || curl -s --max-time 5 api.ipify.org 2>/dev/null || echo "")

if [[ -z "$DEV_IP" ]]; then
  warn "Could not detect public IP. Skipping Cosmos DB firewall update."
else
  info "Detected dev IP: $DEV_IP"

  COSMOS_GREMLIN_ACCOUNT="${COSMOS_GREMLIN_ENDPOINT%%.*}"
  COSMOS_GREMLIN_ACCOUNT="${COSMOS_GREMLIN_ACCOUNT#*//}"
  RG_NAME="${AZURE_RESOURCE_GROUP:-rg-${USE_ENV}}"
  COSMOS_NOSQL_ACCOUNT="${COSMOS_GREMLIN_ACCOUNT}-nosql"

  CURRENT_GREMLIN_IPS=$(az cosmosdb show --name "$COSMOS_GREMLIN_ACCOUNT" --resource-group "$RG_NAME" --query "ipRules[].ipAddressOrRange" -o tsv 2>/dev/null | tr '\n' ',' | sed 's/,$//')
  CURRENT_NOSQL_IPS=$(az cosmosdb show --name "$COSMOS_NOSQL_ACCOUNT" --resource-group "$RG_NAME" --query "ipRules[].ipAddressOrRange" -o tsv 2>/dev/null | tr '\n' ',' | sed 's/,$//')
  GREMLIN_HAS_IP=false; NOSQL_HAS_IP=false
  echo "$CURRENT_GREMLIN_IPS" | grep -q "$DEV_IP" && GREMLIN_HAS_IP=true
  echo "$CURRENT_NOSQL_IPS" | grep -q "$DEV_IP" && NOSQL_HAS_IP=true

  if $GREMLIN_HAS_IP && $NOSQL_HAS_IP; then
    ok "Dev IP $DEV_IP already in both Cosmos DB firewalls — skipping"
  else
    if $GREMLIN_HAS_IP; then
      ok "Dev IP already in Gremlin account firewall"
    else
      info "Adding dev IP to Cosmos DB Gremlin account firewall..."
      NEW_IPS="${CURRENT_GREMLIN_IPS:+$CURRENT_GREMLIN_IPS,}$DEV_IP"
      if az cosmosdb update --name "$COSMOS_GREMLIN_ACCOUNT" --resource-group "$RG_NAME" --ip-range-filter "$NEW_IPS" -o none 2>&1; then
        ok "Added $DEV_IP to Gremlin account firewall"
      else
        warn "Failed to update Gremlin firewall. You may need to add $DEV_IP manually."
      fi
    fi

    if az cosmosdb show --name "$COSMOS_NOSQL_ACCOUNT" --resource-group "$RG_NAME" -o none 2>/dev/null; then
      if $NOSQL_HAS_IP; then
        ok "Dev IP already in NoSQL account firewall"
      else
        info "Adding dev IP to Cosmos DB NoSQL account firewall..."
        NEW_IPS="${CURRENT_NOSQL_IPS:+$CURRENT_NOSQL_IPS,}$DEV_IP"
        if az cosmosdb update --name "$COSMOS_NOSQL_ACCOUNT" --resource-group "$RG_NAME" --ip-range-filter "$NEW_IPS" -o none 2>&1; then
          ok "Added $DEV_IP to NoSQL account firewall"
        else
          warn "Failed to update NoSQL firewall. You may need to add $DEV_IP manually."
        fi
      fi
    fi
  fi
fi

# ══════════════════════════════════════════════════════════════════════
# Step 4: Search indexes
# ══════════════════════════════════════════════════════════════════════

if $SKIP_INDEX; then
  step "Step 4: Search indexes (SKIPPED)"
else
  step "Step 4: Creating search indexes"

  info "Creating runbooks-index..."
  if uv run python scripts/create_runbook_indexer.py 2>&1; then
    ok "Runbooks index created"
  else
    fail "Runbook indexer failed."
    exit 1
  fi

  echo ""
  info "Creating tickets-index..."
  if uv run python scripts/create_tickets_indexer.py 2>&1; then
    ok "Tickets index created"
  else
    fail "Tickets indexer failed."
    exit 1
  fi
fi

# ══════════════════════════════════════════════════════════════════════
# Step 5: Cosmos DB graph data
# ══════════════════════════════════════════════════════════════════════

if $SKIP_DATA; then
  step "Step 5: Cosmos DB data (SKIPPED)"
else
  step "Step 5: Loading graph data into Cosmos DB"

  if [[ -z "${COSMOS_GREMLIN_ENDPOINT:-}" ]] || [[ -z "${COSMOS_GREMLIN_PRIMARY_KEY:-}" ]]; then
    fail "Cosmos DB credentials not set in envs/$(basename "$ENV_FILE")."
    exit 1
  fi

  info "Loading graph schema from data/graph_schema.yaml"
  info "Cosmos DB: $COSMOS_GREMLIN_ENDPOINT / $COSMOS_GREMLIN_DATABASE / $COSMOS_GREMLIN_GRAPH"
  echo ""

  if uv run python scripts/cosmos/provision_cosmos_gremlin.py 2>&1; then
    ok "Graph data loaded into Cosmos DB"
  else
    fail "Cosmos DB graph loading failed."
    echo "   To retry: source envs/$(basename "$ENV_FILE") && uv run python scripts/cosmos/provision_cosmos_gremlin.py"
    exit 1
  fi
fi

# ══════════════════════════════════════════════════════════════════════
# Step 5b: Cosmos DB telemetry data
# ══════════════════════════════════════════════════════════════════════

if $SKIP_DATA; then
  step "Step 5b: Cosmos DB telemetry data (SKIPPED)"
else
  step "Step 5b: Loading telemetry data into Cosmos DB"

  if [[ -z "${COSMOS_NOSQL_ENDPOINT:-}" ]]; then
    fail "COSMOS_NOSQL_ENDPOINT not set in envs/$(basename "$ENV_FILE")."
    exit 1
  fi

  info "Loading telemetry data from data/telemetry/"
  info "Cosmos DB: $COSMOS_NOSQL_ENDPOINT / $COSMOS_NOSQL_DATABASE"
  echo ""

  if uv run python scripts/cosmos/provision_cosmos_telemetry.py 2>&1; then
    ok "Telemetry data loaded into Cosmos DB"
  else
    fail "Cosmos DB telemetry loading failed."
    echo "   To retry: source envs/$(basename "$ENV_FILE") && uv run python scripts/cosmos/provision_cosmos_telemetry.py"
    exit 1
  fi
fi

# ══════════════════════════════════════════════════════════════════════
# Step 6: Verify app health
# ══════════════════════════════════════════════════════════════════════

step "Step 6: Verifying unified app deployment"

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
  HEALTH_BODY=$(curl -s "$GQ_URI/health" 2>/dev/null)
  ok "App is healthy: $HEALTH_BODY"
else
  fail "App not responding after 5 attempts."
  warn "Continuing — agent provisioning may fail if the API is down."
fi

# ══════════════════════════════════════════════════════════════════════
# Step 7: Provision AI agents
# ══════════════════════════════════════════════════════════════════════

if $SKIP_AGENTS; then
  step "Step 7: Agent provisioning (SKIPPED)"
else
  step "Step 7: Provisioning AI Foundry agents"

  info "Creating 5 agents (orchestrator + 4 specialists) with --force"
  export GRAPH_BACKEND=cosmosdb

  if uv run python scripts/provision_agents.py --force 2>&1; then
    ok "All agents provisioned"
  else
    fail "Agent provisioning failed."
    echo "   To retry: source envs/$(basename "$ENV_FILE") && GRAPH_BACKEND=cosmosdb uv run python scripts/provision_agents.py --force"
    exit 1
  fi

  if [[ -f "$AGENT_IDS_FILE" ]]; then
    ORCH_ID=$(python3 -c "import json; print(json.load(open('$AGENT_IDS_FILE'))['orchestrator']['id'])" 2>/dev/null || echo "")
    if [[ -n "$ORCH_ID" ]]; then
      ok "Orchestrator agent: $ORCH_ID"
    fi
  else
    fail "agent_ids.json not created."
  fi
fi

# ══════════════════════════════════════════════════════════════════════
# Step 7b: Redeploy with agent_ids.json
# ══════════════════════════════════════════════════════════════════════

step "Step 7b: Redeploying app with agent_ids.json"

if [[ -f "$AGENT_IDS_FILE" ]]; then
  info "Rebuilding app container to include agent_ids.json..."
  if azd deploy app 2>&1; then
    ok "App redeployed with agent_ids.json"
  else
    fail "App redeploy failed. To retry: azd deploy app"
    warn "Continuing."
  fi
else
  warn "Skipping — agent_ids.json not found."
fi

# ══════════════════════════════════════════════════════════════════════
# Step 8: Local services (optional)
# ══════════════════════════════════════════════════════════════════════

if $SKIP_LOCAL; then
  step "Step 8: Local services (SKIPPED)"
  echo ""
  ok "Deployment complete! All services are running in Azure."
  echo ""
  echo "   App URL:   ${APP_URI:-<check envs/$(basename "$ENV_FILE")>}"
  echo ""
  echo "   To run locally:"
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

  lsof -ti:8000,5173 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  sleep 1

  info "Installing frontend dependencies..."
  (cd frontend && npm install --silent 2>&1 | tail -3) || true

  info "Starting API on port 8000..."
  (cd "$PROJECT_ROOT/api" && source "$ENV_FILE" && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
  API_PID=$!

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

  info "Starting frontend on port 5173..."
  (cd "$PROJECT_ROOT/frontend" && npm run dev) &
  FE_PID=$!

  sleep 3
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>/dev/null | grep -q "200"; then
    ok "Frontend is running (PID $FE_PID)"
  else
    warn "Frontend may still be starting..."
  fi

  trap "info 'Shutting down...'; kill $API_PID $FE_PID 2>/dev/null; exit 0" INT TERM
  echo ""
fi

# ══════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════

echo ""
echo -e "${BOLD}${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Deployment Complete!                                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "  ${BOLD}Environment:${NC}      $USE_ENV"
echo -e "  ${BOLD}Config file:${NC}      envs/$(basename "$ENV_FILE")"
echo -e "  ${BOLD}Graph Backend:${NC}    cosmosdb (Gremlin)"
echo -e "  ${BOLD}Location:${NC}         ${AZURE_LOC}"
echo -e "  ${BOLD}Resource Group:${NC}   ${AZURE_RESOURCE_GROUP:-<pending>}"
echo ""
echo -e "  ${BOLD}Azure Services:${NC}"
echo "    AI Foundry:       ${AI_FOUNDRY_NAME:-<pending>}"
echo "    AI Search:        ${AI_SEARCH_NAME:-<pending>}"
echo "    Storage:          ${STORAGE_ACCOUNT_NAME:-<pending>}"
echo "    Cosmos DB:        ${COSMOS_GREMLIN_ENDPOINT:-<pending>}"
echo "    App URL:          ${APP_URI:-<pending>}"
echo ""

if [[ -f "$AGENT_IDS_FILE" ]]; then
  echo -e "  ${BOLD}Agents:${NC}"
  python3 -c "
import json
with open('$AGENT_IDS_FILE') as f:
    data = json.load(f)
print(f\"    Orchestrator:           {data['orchestrator']['id']}\")
for name, info in data.get('sub_agents', {}).items():
    print(f\"    {name:26s} {info['id']}\")
" 2>/dev/null || echo "    (could not read agent_ids.json)"
  echo ""
fi

if ! $SKIP_LOCAL; then
  echo -e "  ${BOLD}Local Services:${NC}"
  echo "    API:       http://localhost:8000"
  echo "    Frontend:  http://localhost:5173"
  echo ""
  echo "  Press Ctrl+C to stop local services."
  wait
fi

echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo "    azd deploy app                                                      # Redeploy after code changes"
echo "    source envs/$(basename "$ENV_FILE") && uv run python scripts/provision_agents.py --force  # Re-provision agents"
echo "    azd down --force --purge                                            # Tear down all Azure resources"
echo "    ./deploy_app.sh --env other-name                                     # Deploy to a different environment"
echo ""
