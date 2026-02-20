# Deployment Flow — End-to-End Reference

> Generated from `deploy.sh` audit. Concise step-by-step logic with data-flow annotations showing where each config value originates and how it reaches the running container.

---

## Architecture: How Config Reaches the Container

```
┌─────────────────────────────────────────────────────────────────┐
│                     Container App (runtime)                     │
│                                                                 │
│  ┌──────────────┐           ┌────────────────────┐              │
│  │ Bicep env vars│           │ /app/azure_config  │              │
│  │ (platform)    │           │ .env (baked file)  │              │
│  └──────┬───────┘           └────────┬───────────┘              │
│         │                            │                          │
│         ▼                            ▼                          │
│  ┌─────────────────────────────────────────────┐                │
│  │           os.environ at startup             │                │
│  │                                             │                │
│  │  API:           load_dotenv(override=False)  │  ← Bicep wins │
│  │  graph-query-api: load_dotenv(override=True) │  ← File wins  │
│  └─────────────────────────────────────────────┘                │
│                                                                 │
│  supervisord → nginx(:80) + api(:8000) + graph-query-api(:8100) │
└─────────────────────────────────────────────────────────────────┘
```

**Two config injection paths exist in parallel:**

| Path | Set by | Updated by |
|------|--------|------------|
| **Bicep platform env vars** | `main.bicep` Container App `env:` array | `azd provision` |
| **Baked `/app/azure_config.env`** | `COPY azure_config.env` in Dockerfile | `azd deploy app` (image rebuild) |

**Critical:** `graph-query-api` uses `load_dotenv(override=True)` — the baked file **always wins** over Bicep env vars. Since `deploy.sh` deploys the app only once at the end (Step 7) after all provisioning, the baked file always has final values. The `override=True` vs `override=False` distinction only matters if someone runs `azd provision` manually without a subsequent `azd deploy app`.

---

## Full deploy.sh Flow

### Pre-flight (before any steps)

```
Parse CLI flags:
  --skip-infra, --skip-app, --skip-local
  --provision-fabric, --provision-data, --provision-agents, --provision-all
  --env NAME, --location LOC, --scenario NAME
  --yes / -y  (skip all prompts)
  --help / -h (print usage and exit)
Set PROJECT_ROOT, CONFIG_FILE, CONFIG_TEMPLATE
```

### Scenario + Fabric Names

```
1. Resolve scenario: --scenario flag → DEFAULT_SCENARIO env var → list data/scenarios/*/
2. Parse scenario.yaml → extract RUNBOOKS_INDEX_NAME, TICKETS_INDEX_NAME
3. Collect Fabric resource names (interactive or defaults):
   FABRIC_WORKSPACE_NAME, FABRIC_LAKEHOUSE_NAME, FABRIC_EVENTHOUSE_NAME, FABRIC_ONTOLOGY_NAME
```

### Step 0 — Prerequisites

```
Check/install: python3 ≥3.11, uv, node ≥20, az, azd
Verify: az login, azd auth login
Register providers: Microsoft.App, Microsoft.ContainerService
```

### Step 1 — Environment Selection

```
List existing azd environments
  → Use existing / Delete+recreate / Create new
  → Result: USE_ENV is set, azd env selected
```

### Step 2 — Configure azure_config.env

```
1. IF azure_config.env exists:
     Extract all non-empty KEY=VALUE pairs into _PREV_VALS{}
2. cp azure_config.env.template → azure_config.env  (ALWAYS — fresh structure)
3. Restore _PREV_VALS into the fresh copy via set_config()
4. Write known values immediately:
     DEFAULT_SCENARIO, FABRIC_WORKSPACE_NAME, FABRIC_LAKEHOUSE_NAME,
     FABRIC_EVENTHOUSE_NAME, FABRIC_ONTOLOGY_NAME,
     RUNBOOKS_INDEX_NAME, TICKETS_INDEX_NAME, AZURE_LOCATION, GRAPH_BACKEND
```

**Data state after Step 2:** azure_config.env has user-provided names + preserved previous values. Azure resource IDs are empty unless carried from a prior run.

### Step 2b — Generate Static Topology JSON

```
Run scripts/generate_topology_json.py --scenario $SCENARIO_NAME
  → Outputs graph-query-api/backends/fixtures/topology.json
  → Baked into Docker image for instant frontend graph rendering
```

### Step 3 — Infrastructure (conditional)

#### Path A: `--skip-infra` NOT set (fresh deploy)

```
1. Set azd env vars: AZURE_LOCATION, GRAPH_BACKEND, GPT_CAPACITY_1K_TPM,
   DEFAULT_SCENARIO, RUNBOOKS_INDEX_NAME, TICKETS_INDEX_NAME
2. Auto-detect DEV_IP_ADDRESS (for Cosmos DB firewall)
3. Run azd provision (infra only — NO Docker build):
   a. preprovision.sh:
      - Source azure_config.env → sync selected vars to azd env:
        AZURE_LOCATION, GPT_CAPACITY_1K_TPM, GRAPH_BACKEND,
        FABRIC_WORKSPACE_ID, AZURE_FABRIC_ADMIN, FABRIC_CAPACITY_SKU,
        DEFAULT_SCENARIO, RUNBOOKS_INDEX_NAME, TICKETS_INDEX_NAME, CORS_ORIGINS
      - Resolve AZURE_PRINCIPAL_ID (signed-in user)
      - Resolve AZURE_FABRIC_ADMIN (signed-in user email)
   b. Bicep provision:
      - Creates: RG, VNet, AI Foundry (account+project+GPT-4.1),
        AI Search, Storage, Cosmos DB NoSQL, Container Apps Env,
        Container App (placeholder image), RBAC roles, Private Endpoints,
        Fabric Capacity (if AZURE_FABRIC_ADMIN set)
      - Container App has system-assigned managed identity → APP_PRINCIPAL_ID
        is available immediately (no app code deploy needed)
   c. postprovision.sh:
      - Upload runbooks/ + tickets/ blobs to Storage (with RBAC retry)
      - Populate azure_config.env with Bicep outputs:
        AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AI_FOUNDRY_NAME,
        AI_FOUNDRY_ENDPOINT, AI_FOUNDRY_PROJECT_NAME, PROJECT_ENDPOINT,
        AI_SEARCH_NAME, STORAGE_ACCOUNT_NAME, APP_URI, APP_PRINCIPAL_ID,
        GRAPH_QUERY_API_URI, COSMOS_NOSQL_ENDPOINT
      - Resolve FABRIC_CAPACITY_ID (if Bicep provisioned capacity)
4. Source azure_config.env into shell
```

**Data state after Step 3A:** azure_config.env has all Azure resource IDs including APP_PRINCIPAL_ID. FABRIC_WORKSPACE_ID is still empty. No Docker image has been built yet — Container App runs a placeholder.

#### Path B: `--skip-infra` set (reuse existing)

```
Skip azd provision entirely.
```

### Step 3b — Verify & Discover (ALWAYS runs)

```
1. Determine RG: AZURE_RESOURCE_GROUP → azd env AZURE_ENV_NAME → "rg-{env}"
2. IF any critical value missing (AI_FOUNDRY_NAME, AI_SEARCH_NAME, APP_URI, STORAGE_ACCOUNT_NAME):
     Run discover_resources_from_rg() — queries Azure for each resource type
3. Source azure_config.env
```

### Step 4 — Fabric Provisioning (optional: `--provision-fabric`)

```
4a. provision_workspace.py  → writes FABRIC_WORKSPACE_ID to azure_config.env
4b. Fabric RBAC: grant APP_PRINCIPAL_ID Contributor on workspace (REST API)
4c. provision_lakehouse.py  → creates Lakehouse, writes IDs
4d. provision_eventhouse.py → creates Eventhouse + KQL DB, writes IDs
4e. provision_ontology.py   → creates Ontology + Graph Model, writes IDs
4f. populate_fabric_config.py → re-scan workspace, capture any missed IDs
    Source azure_config.env
```

**Data state after Step 4:** azure_config.env now has FABRIC_WORKSPACE_ID, FABRIC_LAKEHOUSE_ID, FABRIC_EVENTHOUSE_ID, FABRIC_ONTOLOGY_ID, etc. No Docker image exists yet — app has not been deployed.

### Step 5 — Data Provisioning (optional: `--provision-data`)

```
provision_search_index.py --upload-files
  → Creates AI Search indexes (runbooks, tickets)
  → Uploads documents + generates embeddings
```

### Step 6 — Agent Provisioning (optional: `--provision-agents`)

```
provision_agents.py
  → Creates AI Foundry agents (GraphExplorer, Telemetry, RunbookKB, HistoricalTicket, Orchestrator)
  → Agents discovered at runtime (no agent_ids.json needed)
```

### Step 7 — Deploy App (unless `--skip-app`)

```
1. Source azure_config.env (final values from all provisioning steps)
2. Sync FABRIC_WORKSPACE_ID → azd env (so Bicep env vars match too)
3. Ensure uv.lock files exist for api/ and graph-query-api/
4. azd deploy app --no-prompt:
   - Docker build: COPYs azure_config.env (fully populated) into image
   - Builds frontend (npm ci + npm run build)
   - Installs Python deps for api/ and graph-query-api/
   - Pushes to ACR, updates Container App from placeholder to real image
```

**This is the ONLY deploy.** Because it happens after all provisioning steps, the baked `azure_config.env` has all final values. No re-deploy needed.

### Step 8 — Health Check

```
Retry up to 5× (15s intervals): curl $APP_URI/health
Warn but continue if unhealthy (container may still be starting)
```

### Step 9 — Local Services (optional, default ON)

```
IF --skip-local: print Azure URL + local dev instructions, exit
ELSE:
  Kill existing processes on :8000, :8100, :5173
  npm install frontend
  Sync API venv (detect+recreate stale .venv if needed)
  Start API:      source azure_config.env && uv run uvicorn ... :8000
  Start Frontend: npm run dev → :5173
  Register trap for Ctrl+C cleanup
```

**Note:** graph-query-api is NOT started locally. The local API uses `GRAPH_QUERY_API_URI` (which points to the deployed Azure Container App) for all graph queries. This is a **hybrid local+remote** setup. To run graph-query-api locally instead, start it manually on :8100 and update `GRAPH_QUERY_API_URI=http://localhost:8100` in `azure_config.env`.

---

## Common Invocation Patterns

| Goal | Command |
|------|---------|
| Fresh full deploy | `./deploy.sh --skip-local --yes` |
| Fresh + all provisioning | `./deploy.sh --skip-local --provision-all --yes` |
| Redeploy app only | `./deploy.sh --skip-infra --skip-local --yes` |
| Provision Fabric on existing infra | `./deploy.sh --skip-infra --skip-local --provision-fabric --yes` |
| Full provisioning on existing infra | `./deploy.sh --skip-infra --skip-local --provision-all --yes` |
| Tear down everything | `azd down --force --purge` |
| Quick code redeploy | `azd deploy app` |

---

## Known Design Considerations

### 1. `override=True` in graph-query-api (mitigated)

The `graph-query-api` service loads config with `load_dotenv(override=True)`, meaning the baked file **always wins** over Container App platform env vars.

**Mitigated by deploy-last pattern:** Since `deploy.sh` now deploys the app only once (Step 7), after all provisioning is complete, the baked file always has the correct final values. The `override=True` behavior is no longer problematic during normal deployment.

**Remaining risk:** If someone runs `azd provision` manually (to update a Bicep env var) without a subsequent `azd deploy app`, `graph-query-api` will ignore the new Bicep value and use the stale baked file.

**Recommendation:** Still worth changing to `load_dotenv(override=False)` for defense in depth. The baked file would then only fill in vars that have no Bicep equivalent.

### 2. Vars in Bicep but not in baked file (harmless)

`AZURE_SEARCH_ENDPOINT` is injected by Bicep but does not exist in `azure_config.env.template`. Since neither `load_dotenv` mode touches keys absent from the file, the Bicep value is always used. No issue, but worth knowing for debugging.

### 2b. Vars synced in `preprovision.sh` but not documented elsewhere

`CORS_ORIGINS` and `FABRIC_CAPACITY_SKU` are synced from `azure_config.env` to azd env in `preprovision.sh`, but are not prominently surfaced in Step 2's "Write known values" list. These pass through to Bicep silently. If a user sets them in the config file, they take effect; if not, they're ignored. Worth knowing for debugging CORS issues or Fabric capacity sizing.

### 3. `set_config` sed escaping

Values containing `&` or `\` are now properly escaped in `set_config()` in both `deploy.sh` and `hooks/postprovision.sh`. Both use the SOH (`\x01`) delimiter and escape `&`/`\` in replacement values. Previously, `&` in a value (e.g., SAS tokens, webhook URLs) would be silently corrupted because sed interprets `&` as "the entire matched text" in replacement strings.

### 4. `postprovision.sh` duplicates `set_config`

`hooks/postprovision.sh` has its own copy of `set_config()` with the same escaping logic. While currently correct, having two separate copies is a maintenance risk — any future fix to one must be manually replicated to the other.

---

## Resolved Design Tensions (v2 refactor)

The following issues from the original `azd up`-based flow have been resolved by the `azd provision` + single `azd deploy app` refactor:

### ~~1. Step 6b was partially redundant when Step 6c ran~~ → RESOLVED

No longer applicable. There is no separate "sync + re-provision" step. The single deploy in Step 7 syncs azd env vars and builds the image with final config in one pass.

### ~~2. Step 6b triggered full postprovision re-run~~ → RESOLVED

No extra `azd provision` is called after the initial one. Blob uploads and config population happen exactly once.

### ~~3. `--skip-app` + `--provision-fabric` left graph-query-api broken~~ → MITIGATED

With `--skip-app`, the script now prints a clear warning that the Container App is running with a placeholder image. The user knows they must run `azd deploy app` manually.

### ~~4. `override=True` conflicted with Bicep injection~~ → MITIGATED

Since the app is deployed last with fully populated `azure_config.env`, the baked file and Bicep env vars agree on all values. The conflict only resurfaces if someone manually runs `azd provision` without `azd deploy app`.

### Remaining consideration: `--skip-app` silently skips the only deploy

If a user runs `./deploy.sh --skip-infra --provision-all --skip-app --yes`, all provisioning completes but the app is never deployed — the Container App still has the placeholder image (or previous image). The script warns about this but doesn't block. This is intentional (user explicitly asked to skip), but could surprise first-time users.
