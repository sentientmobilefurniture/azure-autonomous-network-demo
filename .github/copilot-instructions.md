# Autonomous Network NOC Demo — Copilot Instructions

## Project Overview

Multi-agent NOC (Network Operations Center) demo using Azure AI Foundry agents
with Microsoft Fabric data sources and Azure AI Search knowledge bases.

## Architecture

5 Foundry Agents in an orchestrator pattern:

| Agent | Tool | Data Source |
|-------|------|-------------|
| GraphExplorerAgent | `FabricTool` | Lakehouse (ontology graph) |
| TelemetryAgent | `FabricTool` | Eventhouse (KQL telemetry) |
| RunbookKBAgent | `AzureAISearchTool` | runbooks-index |
| HistoricalTicketAgent | `AzureAISearchTool` | tickets-index |
| Orchestrator | `ConnectedAgentTool` | Wired to all 4 above |

## SDK Versions & Patterns

- **azure-ai-projects** `>=1.0.0,<2.0.0` (v1 API — v2 is incompatible)
- **azure-ai-agents** `==1.2.0b6` (first version with `FabricTool`)
- Use `AIProjectClient` with **project-scoped endpoint**: `https://{resource}.cognitiveservices.azure.com/api/projects/{project_name}`
- Access agents via `project_client.agents` (returns `AgentsClient`)
- Connection IDs must be **project-scoped**: `.../accounts/{acct}/projects/{proj}/connections/{name}`

## Key SDK References

Before writing agent/tool code, read the local references:

```
~/references/skills/.github/skills/azure-ai-projects-py/references/tools.md
~/references/skills/.github/skills/azure-ai-projects-py/references/agents.md
```

## Configuration

Single source of truth: `azure_config.env`
- Auto-populated fields come from `azd up` (postprovision.sh)
- Fabric Data Agent IDs set via `collect_fabric_agents.py`
- Fabric connection names set manually after portal setup

## File Conventions

- Prompts: `data/prompts/foundry_*.md` — each has `## Foundry Agent Description` section
- Scripts: top-level Python files with `load_config()` using `azure_config.env`
- Infrastructure: `infra/` directory with Bicep modules
