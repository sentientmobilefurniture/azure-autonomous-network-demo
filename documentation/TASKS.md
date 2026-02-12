### Automation
- [x] Bug fix provision_ontology.py
- [x] Auto fill eventhouse tables
- [x] Multi-agent workflow provisioning
- [x] Test multi-agent flow programmatically
- [x] Stream agent events with input/output metadata
- [x] Decouple from Fabric Data Agent → OpenApiTool + fabric-query-api
- [x] Automate Fabric role assignment (`assign_fabric_role.py`)
- [x] Deploy fabric-query-api to Container Apps (`azd deploy`)

### Frontend & API
- [x] FastAPI backend with SSE streaming
- [x] React/Vite dark theme UI scaffold
- [x] Wire real orchestrator into SSE endpoint
- [x] Deploy fabric-query-api to Azure Container Apps
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
- [x] Query Fabric graph directly (GQL via REST API)
- [x] Create and test graph query tool — FunctionTool PoC → OpenApiTool production
- [x] Generalize data ingestion functions to be dataset agnostic
- [ ] Generalize prompt, ontology, etc... dataset wise. We should try to build these things from services.
- [x] Prep the codebase for dual-graph architecture. Shift fabric specific files into specific locations, genericize graph APIs to allow easy swap out, restructure agent prompts with core model and graphdb-specific model (and build from those components) and control all these via the GRAPH_BACKEND param in azure_config.env
- [x] Add graceful failure - If orchestrator run fails, retry with the entire thread including the error message. 
- [ ] Make the agent flow even more WOWZA - Agent analyzing/auditing/classifying? Parallel execution doing some other stuff? The possibility of finetuning - THIS SHOULD ALL BE IN A KNOWLEDGE GRAPH DRREEEEEEAM deck
- [ ] Verify that the cosmosDB stuff works
- [ ] **Neo4j graph backend** — Replace Fabric GraphModel with Neo4j for demo. Enables real-time graph mutations from the UI (add/remove nodes, trigger faults, visualize topology live). Cypher ≈ GQL. Fabric remains the production-scale story; Neo4j is the interactive demo story.
- [ ] Real-time graph visualization in UI (D3-force / Neovis.js over Bolt websockets)
- [ ] Click on a node, select a particular type of error or scenario, trigger it!
- [ ] Cache common GQL queries (Redis / embedding cache)
- [ ] Link telemetry from all agents rather than just the orchestrator
- [ ] MCP server tools
- [ ] CosmosDB for tickets
- [ ] Corrective action API
- [ ] Expand data complexity and size to more closely model real world
- [ ] Play by play commentary on each step of the demo
- [ ] Better and more readable formatting of demo output
- [ ] Logs and Application Insights to trace server-side errors
- [ ] Display final response somewhere — wireframe needed