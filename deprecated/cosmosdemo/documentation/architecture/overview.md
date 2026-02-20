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

| Scenario | Domain | Graph Backend | Entity Types | Incident |
|----------|--------|--------------|-------------|----------|
| `telco-noc` | Telecom | CosmosDB Gremlin | CoreRouter, AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession | Fibre cut → cascading alert storm |
| `telco-noc-fabric` | Telecom | Fabric GQL | Same entity types as `telco-noc` | Same incident — backed by Microsoft Fabric Graph Models |

> **Note:** `telco-noc` and `telco-noc-fabric` have local data packs (scenario
> directories + tarballs). `telco-noc-fabric` uses the same topology and telemetry
> data but queries graph data via Fabric's ISO GQL API instead of Cosmos Gremlin.
> Additional scenarios (e.g., cloud-outage, customer-recommendation) are **conceptual**
> and would need to be generated with `./data/generate_all.sh` using a matching
> `scenarios/{name}/` directory before they can be uploaded.

## Graph Backend Abstraction (V11)

The platform supports **multiple graph backends** via the `GraphBackend` Protocol.
The active backend is determined per-scenario by the `data_sources.graph.connector`
field in `scenario.yaml`:

| Connector Value | Backend Registry Key | Backend Class | Query Language |
|----------------|---------------------|---------------|----------------|
| `cosmosdb-gremlin` | `cosmosdb` | `CosmosDBGremlinBackend` | Apache TinkerPop Gremlin |
| `fabric-gql` | `fabric-gql` | `FabricGQLBackend` | ISO Graph Query Language (GQL) |
| `mock` | `mock` | `MockGraphBackend` | N/A (static data) |

The `CONNECTOR_TO_BACKEND` dict in `config.py` maps connector strings to backend
registry keys. `get_scenario_context()` (now `async`) resolves the backend type by
looking up the scenario's stored config in `config_store`, falling back to the
`GRAPH_BACKEND` env var for backward compatibility.
