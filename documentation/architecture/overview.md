# System Overview

Multi-agent incident investigation platform. AI agents — defined by
`scenario.yaml` configuration — collaborate via Azure AI Foundry to
diagnose operational incidents across any domain (telecommunications,
cloud infrastructure, e-commerce, etc.).

Agent topology is **config-driven**: each scenario's `agents:` section
declares N agents with their roles, models, tools (OpenAPI or AI Search),
and connected-agent relationships. The provisioner reads this config to
create exactly the agents the scenario needs — no hardcoded agent count.

The platform is **scenario-agnostic**: users upload scenario data packs via
the browser UI. The Container App ingests graph data, telemetry, knowledge
bases, and prompts into Azure services. No CLI-based data loading required.

**Scenario management** is a first-class feature: users create named scenarios
that bundle all data types, switch between them with one click (auto-provisioning
agents), and persist selections across sessions via `localStorage`. See
[Scenario Management](scenario-management.md) and `documentation/SCENARIOHANDLING.md`.

## Available Scenarios

| Scenario | Domain | Entity Types | Incident |
|----------|--------|-------------|----------|
| `telco-noc` | Telecom | CoreRouter, AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession | Fibre cut → cascading alert storm |

> **Note:** Only `telco-noc` has local data packs (scenario directory + tarballs).
> Additional scenarios (e.g., cloud-outage, customer-recommendation) are **conceptual**
> and would need to be generated with `./data/generate_all.sh` using a matching
> `scenarios/{name}/` directory before they can be uploaded.
