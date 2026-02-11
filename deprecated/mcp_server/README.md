# MCP Server — Autonomous Network NOC Tools

Custom MCP server hosted on **Azure Functions** that exposes network operations
tools to the **Foundry Agent Service** via the Model Context Protocol.

## Architecture

```
┌─────────────────────────┐       MCP Protocol        ┌──────────────────────┐
│  Foundry Agent Service  │ ──────────────────────────▶│  Azure Functions     │
│  (Supervisor Agent)     │  POST /runtime/webhooks/   │  (MCP Extension)     │
│                         │        mcp                 │                      │
│  Tool: MCPTool(         │◀──────────────────────────│  ┌─ query_eventhouse  │
│    server_url=...,      │       JSON responses       │  ├─ search_tickets   │
│    server_label=...)    │                            │  └─ create_incident  │
└─────────────────────────┘                            └──────────────────────┘
                                                              │
                                                              ▼
                                                    ┌──────────────────┐
                                                    │ Fabric Eventhouse │
                                                    │ AI Search        │
                                                    └──────────────────┘
```

## Tools

| Tool | Description |
|---|---|
| `query_eventhouse` | KQL queries against Fabric Eventhouse (AlertStream, LinkTelemetry) |
| `search_tickets` | Vector search historical incident tickets via AI Search |
| `create_incident` | Create a new incident ticket (demo: logged to stdout) |

## Prerequisites

- Python 3.11+
- [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local) >= 4.0.7030
- [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) (local storage emulator)

## Local Development

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure local settings**
   
   Copy values from `../azure_config.env` into `local.settings.json`:
   ```json
   {
     "Values": {
       "EVENTHOUSE_QUERY_URI": "<your-eventhouse-query-uri>",
       "AI_SEARCH_NAME": "<your-search-service-name>"
     }
   }
   ```

3. **Start Azurite** (required for Azure Functions)
   
   ```bash
   # VS Code: Ctrl+Shift+P → "Azurite: Start"
   # Or from terminal:
   npx azurite --location ~/.azurite
   ```

4. **Start the MCP server**  
   
   ```bash
   cd mcp_server
   func start
   ```
   
   Server runs at: `http://localhost:7071/runtime/webhooks/mcp`

5. **Test with VS Code Copilot**  
   
   The `.vscode/mcp.json` file is pre-configured. In Copilot Agent mode,
   ask the MCP server to run a tool.

## Deploy to Azure

```bash
# Create a Flex Consumption Function App (see SETUP.md)
# Then deploy:
func azure functionapp publish <your-function-app-name>
```

Required app settings on the Function App:
```bash
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings \
    "EVENTHOUSE_QUERY_URI=<your-uri>" \
    "AI_SEARCH_NAME=<your-search-name>"
```

## Connect to Foundry Agent Service

After deployment, connect the MCP server to your agent:

1. **Foundry Portal** → Build → Select agent → Tools → Add → Custom → MCP
2. **Endpoint**: `https://<funcapp>.azurewebsites.net/runtime/webhooks/mcp`
3. **Authentication**: Microsoft Entra / Key-based / Unauthenticated
4. **Connect** → Test with a prompt

Or programmatically in `create_agents.py`:
```python
from azure.ai.agents.models import McpTool

mcp_tool = McpTool(
    server_url="https://<funcapp>.azurewebsites.net/runtime/webhooks/mcp",
    server_label="noc_tools",
)

agent = project_client.agents.create_agent(
    model=MODEL,
    name="noc_supervisor",
    instructions=SUPERVISOR_INSTRUCTIONS,
    tools=mcp_tool.definitions,
)
```
