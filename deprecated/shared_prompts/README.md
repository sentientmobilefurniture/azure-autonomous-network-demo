# Shared Prompt Templates

This directory contains **domain-agnostic** prompt templates shared across all
scenarios. Each agent's final prompt is composed by combining a shared template
from here with scenario-specific fragments from `data/scenarios/<name>/data/prompts/`.

## Prompt composition (Phase 3)

```
Orchestrator    = shared/orchestrator_core.md    + scenario/prompts/orchestrator.md
GraphExplorer   = shared/graph_explorer_core.md  + scenario/prompts/graph_explorer/schema.md + language_{backend}.md
Telemetry       = shared/telemetry_core.md       + scenario/prompts/telemetry_agent.md
Runbook         = shared/runbook_core.md         + scenario/prompts/runbook_custom.md (optional)
Ticket          = shared/ticket_core.md          + scenario/prompts/ticket_custom.md (optional)
```

## Current state

These files are **stubs** created during Phase 1. The actual domain-agnostic
content will be extracted from the current prompts and placed here in Phase 3
when the prompt composition system is built.
