# Prompt Fragments Reference

## Overview

Every scenario requires a set of prompt fragments in `data/prompts/` that
connect the generated data to the AI agents. These prompts are uploaded to
Cosmos DB and composed at runtime by the API provisioner.

**Critical rule: use `{graph_name}` and `{scenario_prefix}` placeholders.**
The API config router substitutes them at runtime:
- `{graph_name}` → e.g. `cloud-outage-topology`
- `{scenario_prefix}` → e.g. `cloud-outage`

## Required Prompt Files

```
data/prompts/
├── foundry_orchestrator_agent.md      # Main investigation agent
├── foundry_telemetry_agent_v2.md      # Telemetry/anomaly agent
├── foundry_runbook_kb_agent.md        # Runbook search agent
├── foundry_historical_ticket_agent.md # Ticket search agent
├── alert_storm.md                     # Default demo alert input
└── graph_explorer/
    ├── core_schema.md                 # Full entity schema
    ├── core_instructions.md           # Gremlin traversal instructions
    ├── description.md                 # Agent description for Foundry
    ├── language_gremlin.md            # Gremlin query examples
    └── language_mock.md               # Mock mode NL examples
```

## Per-File Specifications

### `foundry_orchestrator_agent.md`

The main investigation agent that coordinates sub-agents. Must include:

1. **Role**: You are a network operations / cloud ops / etc. AI investigator
2. **Investigation flow**: Step-by-step process (triage → root cause → blast radius → remediation)
3. **Sub-agent descriptions**: What each sub-agent can do (graph explorer, telemetry, runbooks, tickets)
4. **Alert types**: List of domain-specific alert types and their severity mapping
5. **Telemetry baselines**: Normal vs anomalous ranges for each metric
6. **Scenario Context section** (X-GRAPH RULE): Must state the active graph name
   using placeholders:

```markdown
## Scenario Context

The current active scenario graph is `{graph_name}`.
The telemetry database is `{scenario_prefix}-telemetry`.
```

### `foundry_telemetry_agent_v2.md`

The telemetry/anomaly detection agent. Must include:

1. **Cosmos NoSQL container schemas**: For each container, list partition key, columns, types
2. **Value ranges**: Normal vs anomalous ranges for each numeric column
3. **Query patterns**: Example Cosmos SQL queries for the containers
4. **CRITICAL RULE #7** (X-GRAPH RULE): Must include explicitly:

```markdown
**CRITICAL RULE #7**: Always include the `X-Graph` header with the value
`{graph_name}` in every API request. Without this header, queries
will fail with "Resource Not Found".
```

### `graph_explorer/core_instructions.md`

Gremlin traversal instructions. Must include:

1. **Available edge labels**: List all edge relationships in this scenario
2. **Traversal patterns**: How to find root cause, blast radius, dependency chains
3. **Property filters**: Which properties can be filtered on
4. **CRITICAL RULE #6** (X-GRAPH RULE): Must include explicitly:

```markdown
**CRITICAL RULE #6**: Always include the `X-Graph` header with the value
`{graph_name}` in every API request. Without this header, queries
will fail with "Resource Not Found".
```

### `graph_explorer/core_schema.md`

Full entity schema listing ALL instances. Example format:

```markdown
## Vertex Types

### CoreRouter (3 instances)
| RouterId | City | Region | Vendor | Model |
|----------|------|--------|--------|-------|
| CORE-SYD-01 | Sydney | NSW | Cisco | ASR-9922 |
| CORE-MEL-01 | Melbourne | VIC | Cisco | ASR-9922 |
| CORE-BNE-01 | Brisbane | QLD | Juniper | MX10008 |

### TransportLink (10 instances)
...

## Edge Types
| Edge Label | Source Type | Target Type | Description |
|-----------|------------|------------|-------------|
| connects_to | TransportLink | CoreRouter | Physical connectivity |
| aggregates_to | AggSwitch | CoreRouter | Aggregation uplink |
...
```

### `graph_explorer/description.md`

Short agent description used for Foundry registration:

```markdown
Graph Explorer agent for <scenario-name>. Queries the <domain> graph topology
via Gremlin to investigate entity relationships, dependency chains, blast radius,
and root cause paths.
```

### `graph_explorer/language_gremlin.md`

Gremlin query examples specific to this scenario's edge labels:

```markdown
## Example Queries

### Find all entities connected to a router
```gremlin
g.V().has('CoreRouter', 'RouterId', 'CORE-SYD-01').both().path()
```

### Find services depending on a failed link
```gremlin
g.V().has('TransportLink', 'LinkId', 'LINK-SYD-MEL-FIBRE-01')
  .in('routes_via').in('depends_on')
  .has(label, 'Service').valueMap(true)
```
```

### `graph_explorer/language_mock.md`

Natural language examples for mock/demo mode without Gremlin:

```markdown
## Example Queries (Natural Language)

- "Show me all devices connected to CORE-SYD-01"
- "What services depend on LINK-SYD-MEL-FIBRE-01?"
- "Find the blast radius of a failure on AGG-SYD-NORTH-01"
- "List all SLA policies that would be breached if VPN-ACME-CORP goes down"
```

### `foundry_runbook_kb_agent.md`

Domain-specific runbook agent prompt:

```markdown
You are a runbook search agent for <domain> operations. You search the
AI Search index for relevant operational procedures based on the incident
type and affected entities.

Available runbooks cover: <list domain-specific procedure types>
```

### `foundry_historical_ticket_agent.md`

Domain-specific ticket agent prompt:

```markdown
You are a historical ticket search agent. You search past incident tickets
to find precedent cases that match the current investigation.

Historical incidents in this dataset cover root cause types:
<list the root_cause_type values from your tickets>
```

### `alert_storm.md`

A realistic alert CSV snippet that kicks off the demo investigation.
Should contain 5–10 rows from the AlertStream showing the initial cascade:

```markdown
AlertId,Timestamp,SourceNodeId,SourceNodeType,AlertType,Severity,Description,...
ALT-20260206-003001,2026-02-06T14:30:00.000Z,LINK-SYD-MEL-FIBRE-01,TransportLink,LINK_DOWN,CRITICAL,Physical link loss of light detected,...
ALT-20260206-003002,2026-02-06T14:30:02.100Z,CORE-SYD-01,CoreRouter,BGP_PEER_LOSS,CRITICAL,BGP peer CORE-MEL-01 unreachable,...
...
```

## X-Graph Header Rule — Full Explanation

### Why This Exists

The Azure AI Foundry `OpenApiTool` does NOT reliably enforce `default` or `enum`
constraints from OpenAPI specs. The LLM controls parameter values and often
ignores schema constraints, sending empty or wrong values for the `X-Graph` header.

### Defense-in-Depth

Three layers work together:
1. **OpenAPI `enum` constraint**: `enum: ["{graph_name}"]` in the API spec template
   (substituted by the agent provisioner's `_load_openapi_spec()`)
2. **Prompt CRITICAL RULE**: Natural language instruction in the agent's system prompt
   (substituted by the config router's `.replace("{graph_name}", ...)`)
3. **Runtime substitution**: Both the config router (prompts) and agent provisioner
   (OpenAPI specs) substitute `{graph_name}` → concrete value like `telco-noc-topology`

### Which Files Need It

| File | Section/Rule | Content |
|------|-------------|---------|
| `foundry_orchestrator_agent.md` | Scenario Context | "The current active scenario graph is `{graph_name}`." |
| `foundry_telemetry_agent_v2.md` | CRITICAL RULE #7 | "Always include the X-Graph header with the value `{graph_name}`." |
| `graph_explorer/core_instructions.md` | CRITICAL RULE #6 | "Always include the X-Graph header with the value `{graph_name}`." |

### Graph Name Convention

- Graph name: `<scenario-name>-topology` (e.g. `telco-noc-topology`)
- Telemetry DB derived at runtime: `rsplit("-", 1)[0]` + `-telemetry` → `telco-noc-telemetry`
- In prompt files, use `{graph_name}` and `{scenario_prefix}` — substituted at runtime

## Optional Custom Instructions

If present, these files are appended to the corresponding agent's composed prompt.
If absent, they are silently skipped — zero configuration cost:

| File | Purpose |
|------|---------|
| `orchestrator_custom.md` | Extra investigation hints, domain heuristics |
| `graph_explorer/custom_instructions.md` | Traversal recipes, entity tips |
| `telemetry_custom.md` | Metric interpretation guidance |
| `runbook_custom.md` | Domain-specific search hints |
| `ticket_custom.md` | Domain-specific search hints |
