# Deployment

## `deploy.sh` — 5 Steps (no data loading, no agent provisioning)

| Step | What |
|------|------|
| 0 | Prerequisites check (Python, uv, Node, az, azd); auto-installs uv and node 20 |
| 1 | Azure environment selection (creates or selects `azd` environment, sets subscription) |
| 2 | Configure azure_config.env (writes template with placeholders) |
| 3 | `azd up` (runs preprovision → Bicep infra → container deploy → postprovision) |
| 6 | Health check (`curl -sf {APP_URI}/health` with retries) |
| 7 | Local dev servers (optional) |

Steps 4, 5, old-7 (search indexes, Cosmos data, agent provisioning) were removed.
All data + agent operations happen through the UI.

**Flags**: `--skip-infra`, `--skip-local`, `--env NAME`, `--location LOC`, `--yes`

**Dead flags** (parse but do nothing, steps removed): `--skip-index`, `--skip-data`, `--skip-agents`.

**Default location**: `swedencentral`.

**Health check**: 5 retries, 15s between attempts.

**BUG — Step 7 (local services)**: The automated start only launches API (:8000) and
frontend (:5173) but does NOT start graph-query-api (:8100). All `/query/*` requests
fail in automated local mode. The `--skip-local` manual instructions correctly
mention all 3 services.

## azd Lifecycle Hooks

**`hooks/preprovision.sh`**:
- Syncs selected vars from `azure_config.env` → `azd env` so Bicep's `readEnvironmentVariable()` can access them

**`hooks/postprovision.sh`**:
- Does NOT upload any blob data (removed in V8)
- Writes `azure_config.env` with Bicep outputs (subscription, RG, endpoints)
- **Fetches Cosmos Gremlin primary key** via `az cosmosdb keys list`
- **Derives Gremlin endpoint** from account name: `{account}.gremlin.cosmos.azure.com`
- **Queries separate NoSQL account** (`{account}-nosql`) for NoSQL endpoint
- Contains a dead `upload_with_retry` function (6 attempts, 30s wait) — defined but never called
- `DEFAULT_SCENARIO` and `LOADED_SCENARIOS` vars ARE defined in `azure_config.env.template` (with defaults `telco-noc`) and synced in preprovision.sh, but are not consumed by any runtime code — they are vestigial from the pre-V8 CLI-based data loading workflow

**Config bidirectional flow**:
```
azure_config.env → preprovision → azd env → Bicep params
                                                    ↓
azure_config.env ← postprovision ← Bicep outputs
```

## Post-Deployment Workflow

**Option A — Scenario-based (recommended):**
1. `./data/generate_all.sh [scenario]` → creates 5 per-type tarballs
2. Open app → click "+New Scenario" in Header chip or ⚙ Settings → Scenarios tab
3. Name the scenario → drag-drop all 5 tarballs (auto-detected by filename) → Save
4. Scenario auto-provisions agents and loads topology — ready to investigate

**Option B — Manual/Custom (ad-hoc uploads):**
1. `./data/generate_all.sh [scenario]` → creates 5 per-type tarballs
2. Open app → ⚙ Settings → Upload tab → upload each tarball (graph first recommended)
3. Data Sources tab → select graph, indexes, prompt set
4. Click "Load Topology" → verifies graph data loads in viewer
5. Click "Provision Agents" → creates 5 agents with selected prompts and data bindings

## Code-Only Redeployment

For code changes without infra changes: `azd deploy app` (rebuilds container, ~60-90s).
Uses `remoteBuild: true` in `azure.yaml` — Docker images built in ACR, not locally.
This avoids cross-platform issues (e.g., building on ARM Mac for Linux amd64):

```yaml
# azure.yaml
services:
  app:
    host: containerapp
    docker:
      path: ./Dockerfile
      remoteBuild: true
```

| Change Type | Command | Time |
|-------------|---------|------|
| Python code, OpenAPI specs, static files | `azd deploy app` | ~60-90s |
| Bicep infrastructure (new resources, env vars, RBAC) | `azd up` | ~5-10min |
| New env var in container | `azd up` (env vars are in Bicep) | ~5-10min |
| Frontend-only / Dockerfile changes | `azd deploy app` | ~60-90s |

**After code-only deploy:** If you changed agent provisioning logic or OpenAPI specs,
re-provision agents through the UI (⚙ → Provision Agents) — old agents in Foundry
still have old tool specs baked in.

## Full Teardown (`infra/nuclear_teardown.sh`)

Use when you need to completely destroy the environment and start fresh:

```bash
./infra/nuclear_teardown.sh
```

Steps:
1. Sources `azure_config.env` (error-suppressed if missing)
2. `azd down --force --purge` — destroys all azd-managed resources
3. If `AI_FOUNDRY_NAME` + `AZURE_RESOURCE_GROUP` + `AZURE_LOCATION` are set: purges soft-deleted Cognitive Services account via `az cognitiveservices account purge`
4. If `AZURE_RESOURCE_GROUP` is set: `az group delete --yes --no-wait` to clean up any lingering resources
5. `azd env delete --yes` — removes local azd environment state

**When to use vs. `azd down`:** Use `nuclear_teardown.sh` when `azd down` fails to
fully clean up (orphaned Cognitive Services soft-deletes, resource locks), or when
you need a guaranteed clean slate. Use `azd down` for normal teardown.
