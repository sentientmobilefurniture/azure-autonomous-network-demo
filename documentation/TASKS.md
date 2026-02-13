### Automation
- [x] Multi-agent workflow provisioning
- [x] Test multi-agent flow programmatically
- [x] Stream agent events with input/output metadata
- [x] Decouple from legacy Data Agent → OpenApiTool + graph-query-api
- [x] Deploy graph-query-api to Container Apps (`azd deploy`)

### Frontend & API
- [x] FastAPI backend with SSE streaming
- [x] React/Vite dark theme UI scaffold
- [x] Wire real orchestrator into SSE endpoint
- [x] Deploy graph-query-api to Azure Container Apps
- [x] Test independent graph querying
- [x] Fix unreliable behavior - Ontology/Data file mismatch + confusing prompt spec - Fixed
- [x] Verify that v2 architecture works with current UI
- [x] Fix event streaming not working
- [x] Final test before merging v2architecture
- [x] Revamp UI for better presentation and readability
- [ ] Deploy main API to Azure Container Apps
- [ ] Deploy frontend to Azure Static Web Apps

### Future
- [x] Format query and response text with markdown
- [x] Create and test graph query tool — FunctionTool PoC → OpenApiTool production
- [x] Generalize data ingestion functions to be dataset agnostic
- [ ] Generalize prompt, ontology, etc... dataset wise. We should try to build these things from services.
- [x] Prep the codebase for dual-graph architecture. Shift graph-specific files into specific locations, genericize graph APIs to allow easy swap out, restructure agent prompts with core model and graphdb-specific model (and build from those components) and control all these via the GRAPH_BACKEND param in azure_config.env
- [x] Add graceful failure - If orchestrator run fails, retry with the entire thread including the error message. 
- [x] Fix slow cosmosdb data ingestion — Async bulk upserts (50 concurrent), CSVs uploaded to blob storage, `--from-blob` flag for native blob-sourced ingestion
- [ ] Make the agent flow even more WOWZA - Agent analyzing/auditing/classifying? Parallel execution doing some other stuff? The possibility of finetuning - THIS SHOULD ALL BE IN A KNOWLEDGE GRAPH DRREEEEEEAM deck
- [x] Verify that the cosmosDB stuff works
- [ ] Conversation persistence is necessary - Selection from a menu
- [ ] Real-time graph visualization in UI (D3-force / Neovis.js over Bolt websockets)
- [ ] What realtime azure component is most appropriate for ingesting real-time telemetry and alerts? Is it azure eventhub? can we simulate a constant alert ingestion via OTel, and then have a button to trigger a flood of horrible telemetry to simulate a scenario, and then fire an alert that then triggers the agent workflow? This should actually be V5
- [ ] Multi scenario with data generalization should be V6 - We could create customized hardcoded scenarios to start and let the user select which one via a button - All the data pregenerated, ingested into cosmos - The button chooses which data tables?
- [ ] Realtime dashboarding in the UI ought to be V7
- [ ] Click on a node, select a particular type of error or scenario, trigger it!
- [ ] Cache common graph queries (Redis / embedding cache)
- [ ] Link telemetry from all agents rather than just the orchestrator
- [ ] MCP server tools
- [ ] CosmosDB for tickets
- [ ] Corrective action API
- [ ] Expand data complexity and size to more closely model real world
- [ ] Play by play commentary on each step of the demo
- [ ] Better and more readable formatting of demo output
- [ ] Logs and Application Insights to trace server-side errors
- [ ] Display final response somewhere — wireframe needed


## Active Deployments

cosmosprod4 (Dev deployment) - https://ca-app-4mboze7wbz4b6.calmmeadow-59f74fcf.eastus2.azurecontainerapps.io/ 
cosmosgraphstable3 (Stable deployment - as of 13/02/26) - https://ca-app-o7wx7vphrn44w.proudbeach-afa9c88b.swedencentral.azurecontainerapps.io/