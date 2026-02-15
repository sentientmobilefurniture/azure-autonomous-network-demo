# Project Structure (as of 2026-02-16)

```
.
├── deploy.sh                   # Deployment: infra only (Steps 0-3, 6-7)
├── Dockerfile                  # Unified container (nginx + API + graph-query-api)
├── nginx.conf                  # Reverse proxy (100m upload, SSE support)
├── supervisord.conf            # Process manager
├── azure.yaml                  # azd service definition
├── azure_config.env            # Runtime config (gitignored, auto-populated)
├── azure_config.env.template   # Config template
│
├── api/                        # FastAPI backend (:8000)
│   ├── pyproject.toml          # Deps: fastapi, uvicorn, python-dotenv, sse-starlette,
│   │                           #       azure-identity, azure-ai-projects, azure-ai-agents, pyyaml
│   └── app/
│       ├── main.py             # Mounts 4 routers + /health + CORS (54 lines)
│       ├── orchestrator.py     # Foundry agent bridge (sync SDK → async SSE, 500 lines)
│       └── routers/
│           ├── alert.py        # POST /api/alert → SSE investigation stream (91 lines)
│           ├── agents.py       # GET /api/agents → agent list from agent_ids.json (29 lines)
│           ├── config.py       # POST /api/config/apply → SSE provisioning stream
│           │                   # GET /api/config/current → current config state (264 lines)
│           └── logs.py         # GET /api/logs → SSE log broadcast (128 lines)
│
├── graph-query-api/            # Data management + query microservice (:8100)
│   ├── pyproject.toml          # Deps: fastapi, gremlinpython, azure-cosmos,
│   │                           #       azure-mgmt-cosmosdb, azure-storage-blob,
│   │                           #       azure-search-documents, sse-starlette, pyyaml
│   ├── config.py               # ScenarioContext, X-Graph header, env vars, credential
│   ├── cosmos_helpers.py       # Centralised Cosmos client/container init + caching (~132 lines)
│   ├── main.py                 # Mounts 7 routers + /health + /query/logs (SSE) + request logging middleware
│   ├── models.py               # Pydantic request/response models
│   ├── router_graph.py         # POST /query/graph (per-scenario Gremlin)
│   ├── router_telemetry.py     # POST /query/telemetry (per-scenario NoSQL)
│   ├── router_topology.py      # POST /query/topology (graph visualization)
│   ├── router_ingest.py        # Upload endpoints + scenario/index listing (~871 lines)
│   ├── router_prompts.py       # Prompts CRUD in Cosmos (~288 lines)
│   ├── router_scenarios.py     # Scenario metadata CRUD in Cosmos (~220 lines)
│   ├── router_interactions.py  # Interaction history CRUD (~146 lines)
│   ├── sse_helpers.py          # SSE upload lifecycle helper (~86 lines)
│   ├── search_indexer.py       # AI Search indexer pipeline creation
│   ├── openapi/
│   │   ├── cosmosdb.yaml       # OpenAPI spec for live mode (has {base_url} placeholder)
│   │   └── mock.yaml           # OpenAPI spec for mock mode
│   └── backends/
│       ├── __init__.py         # GraphBackend Protocol + per-graph cache + factory
│       ├── cosmosdb.py         # CosmosDBGremlinBackend (303 lines, retry logic)
│       └── mock.py             # Static topology (offline demos)
│
├── frontend/                   # React/Vite dashboard
│   ├── package.json            # Deps: react, react-force-graph-2d,
│   │                           #       @microsoft/fetch-event-source, framer-motion,
│   │                           #       react-markdown, react-resizable-panels, tailwindcss
│   ├── vite.config.ts          # Dev proxy: /api→:8000, /query→:8100, /health→:8000
│   └── src/
│       ├── main.tsx            # Wraps App in ScenarioProvider
│       ├── App.tsx             # Tab bar + 3-zone layout + interaction sidebar (~209 lines)
│       ├── types/index.ts      # Shared TypeScript interfaces (StepEvent, SavedScenario, etc., ~77 lines)
│       ├── styles/globals.css  # CSS variables, dark theme, Tailwind imports (159 lines)
│       ├── context/
│       │   └── ScenarioContext.tsx  # Full scenario state: activeScenario, bindings,
│       │                           # provisioningStatus, localStorage persistence,
│       │                           # auto-derivation, scenarioNodeColors/Sizes (~174 lines)
│       ├── hooks/
│       │   ├── useInvestigation.ts  # SSE alert investigation (POST, sends X-Graph, ~133 lines)
│       │   ├── useTopology.ts       # Topology fetch (POST, sends X-Graph, auto-refetch, ~80 lines)
│       │   ├── useScenarios.ts      # Graph/index discovery + saved scenario CRUD +
│       │   │                        # selectScenario with auto-provisioning (~192 lines)
│       │   ├── useInteractions.ts   # Interaction history CRUD (fetch/save/delete, ~63 lines)
│       │   └── useNodeColor.ts      # Centralised node color resolution hook (~42 lines)
│       ├── utils/
│       │   └── sseStream.ts         # Shared consumeSSE() + uploadWithSSE() utilities (~142 lines)
│       └── components/
│           ├── Header.tsx           # Title bar + ScenarioChip + ProvisioningBanner + HealthDot + ⚙ (~72 lines)
│           ├── ScenarioChip.tsx     # Header scenario selector chip + flyout dropdown (~153 lines)
│           ├── ProvisioningBanner.tsx # Non-blocking 28px banner during agent provisioning (~101 lines)
│           ├── TabBar.tsx            # Investigate / Scenario Info tab bar (~31 lines)
│           ├── ScenarioInfoPanel.tsx # Scenario detail view: use cases + example questions (~95 lines)
│           ├── AddScenarioModal.tsx  # Scenario creation: name + 5 slot file upload + auto-detect (~682 lines)
│           ├── HealthDot.tsx        # Polls /health every 15s (~40 lines)
│           ├── SettingsModal.tsx     # 3 tabs: Scenarios + Data Sources + Upload (~673 lines)
│           ├── ActionButton.tsx      # Extracted reusable action button with status state machine (~52 lines)
│           ├── TabbedLogStream.tsx   # Tabbed log stream viewer (~48 lines)
│           ├── MetricsBar.tsx       # Resizable panel: topology viewer + log stream (~50 lines)
│           ├── GraphTopologyViewer.tsx  # Owns all overlay state, delegates to graph/* (~214 lines)
│           ├── InvestigationPanel.tsx   # Alert input + agent timeline + scenario example questions (~69 lines)
│           ├── InteractionSidebar.tsx   # Collapsible right sidebar: saved interaction history (~154 lines)
│           ├── DiagnosisPanel.tsx    # Final markdown report (ReactMarkdown, ~112 lines)
│           ├── AlertInput.tsx       # Textarea + submit button + example question chips (~68 lines)
│           ├── AlertChart.tsx       # Alert visualization (UNUSED — dead code, ~21 lines)
│           ├── MetricCard.tsx       # Metric display card (UNUSED — dead code, ~30 lines)
│           ├── AgentTimeline.tsx     # Step cards + thinking dots (~61 lines)
│           ├── StepCard.tsx         # Individual agent step display (~85 lines)
│           ├── ThinkingDots.tsx     # Animated thinking indicator (~31 lines)
│           ├── ErrorBanner.tsx      # Error display (~51 lines)
│           ├── LogStream.tsx        # SSE log viewer (EventSource → /api/logs, ~127 lines)
│           └── graph/
│               ├── GraphCanvas.tsx      # ForceGraph2D wrapper (forwardRef, canvas rendering, ~184 lines)
│               ├── GraphToolbar.tsx     # Label filters, search, zoom controls, color dot → popover (~137 lines)
│               ├── GraphTooltip.tsx     # Hover tooltip (framer-motion, ~80 lines)
│               ├── GraphContextMenu.tsx # Right-click: display field + color picker
│               ├── ColorWheelPopover.tsx # HSL color wheel + hex input + preset swatches (~260 lines)
│               └── graphConstants.ts    # NODE_COLORS, NODE_SIZES, COLOR_PALETTE by vertex label
│
├── data/
│   ├── generate_all.sh         # Generate + package all scenarios as 5 per-type tarballs
│   └── scenarios/
│       └── telco-noc/          # scenario.yaml, graph_schema.yaml, scripts/, data/
│                               # (only scenario with local data packs; others need generation)
│
├── scripts/
│   ├── agent_provisioner.py    # AgentProvisioner class (importable, 281 lines)
│   ├── provision_agents.py     # Thin CLI wrapper for agent provisioning (~178 lines)
│   ├── agent_ids.json          # Output of provisioning (agent IDs) — read by orchestrator
│   └── testing_scripts/        # CLI test tools
│
├── infra/                      # Bicep IaC
│   ├── main.bicep              # Subscription-scoped (creates RG, deploys 9 modules)
│   ├── main.bicepparam         # Bicep parameter file (uses readEnvironmentVariable())
│   ├── nuclear_teardown.sh     # Full teardown: azd down + Cognitive Services purge + RG delete
│   └── modules/                # vnet, search, storage, cosmosGremlin, aiFoundry,
│                               # containerAppsEnv, app, roles, cosmosPrivateEndpoints
│
├── hooks/
│   ├── preprovision.sh         # Syncs azure_config.env → azd env (5 vars)
│   └── postprovision.sh        # Populates azure_config.env + Cosmos credentials
│
└── deprecated/                 # Superseded scripts (kept for reference)
    └── scripts/                # Old CLI-based indexers + Cosmos provisioners
```
