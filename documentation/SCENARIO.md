# Scenario

## Objective

Demonstrate that a fully autonomous network operations centre can be built
today as an Azure-native product using generally available services. No
third-party orchestration frameworks, no bespoke graph databases, no custom
ML pipelines. Every component — knowledge graph, telemetry store, search
indices, agent runtime, model hosting — runs on Azure Cosmos DB, Foundry, and
AI Search.

The demo answers one question: **when a fibre is cut and hundreds of alerts
fire simultaneously, can AI agents autonomously diagnose the root cause,
assess blast radius, retrieve the correct operating procedure, find
historical precedent, and produce an actionable situation report — without
a human touching a single system?**

---

## Why this matters

Telcos generate billions of alerts per day. Human operators cannot triage at
that scale. The industry roadmap (TM Forum Autonomous Networks L4/L5)
requires the network to self-diagnose and eventually self-heal, progressing
from "humans in the loop" to "humans on the loop" to "humans outside the
loop."

The blockers are not models — GPT-4 class LLMs can reason — they are:

1. **Knowledge.** Models need structured, machine-readable knowledge about
   network topology, service dependencies, SLA exposure, and operational
   procedures. This goes far beyond RAG on PDFs. It requires relationships,
   hierarchies, and semantics — a knowledge plane.
2. **Integration.** That knowledge is scattered across siloed systems:
   topology in one database, telemetry in another, runbooks in a wiki,
   tickets in a ticketing system. An agent must reach all of them.
3. **Orchestration.** A single agent cannot do it all. You need specialist
   agents with scoped access and a supervisor that coordinates them.

This demo shows that Azure already has all the pieces, and they compose
naturally.

---

## The incident

A fibre is cut on the Sydney–Melbourne backbone corridor
(`LINK-SYD-MEL-FIBRE-01`). This is a physical-layer failure on a DWDM 100G
transport link caused by third-party contractor activity. It triggers:

- Total loss of light on the primary inter-city fibre
- BGP session drop between CORE-SYD-01 and CORE-MEL-01
- MPLS primary path failure (MPLS-PATH-SYD-MEL-PRIMARY)
- Cascading SERVICE_DEGRADATION alerts across every service that depends on
  that path: enterprise VPNs (VPN-ACME-CORP, VPN-BIGBANK), broadband
  bundles, mobile 5G backhaul

The symptom an operator sees is an **alert storm**: 20 alerts hitting within
one second, across multiple service types and severities, with no obvious
common label. The alerts name services, not infrastructure — the operator
sees "VPN tunnel unreachable" and "backhaul degradation," not "fibre cut."

The challenge: correlate symptoms to a single root cause buried three
dependency layers deep.

---

## The network

A synthetic but realistic three-city Australian telecom network:

**Infrastructure layer**
- 3 core routers (Sydney, Melbourne, Brisbane) — Cisco ASR-9922 / Juniper MX10008
- 10 transport links — 4 inter-city DWDM backbone fibres + 6 local aggregation uplinks
- 6 aggregation switches — 2 per city
- 8 5G NR base stations (gNodeBs) at the edge

**Logical layer**
- 3 iBGP peering sessions between core routers
- 5 MPLS label-switched paths (primary, secondary, tertiary) carrying traffic between cities
- 10 customer-facing services — 3 EnterpriseVPN, 3 Broadband, 4 Mobile5G
- 5 SLA policies with availability, latency, and financial penalty terms

**Relationships** (the knowledge that matters)
- TransportLinks connect CoreRouters
- AggSwitches aggregate to CoreRouters
- BaseStations backhaul via AggSwitches
- MPLSPaths route via TransportLinks
- Services depend on MPLSPaths / AggSwitches / BaseStations
- SLAPolicies govern Services
- BGPSessions peer over CoreRouters

These relationships are what let an agent trace from "VPN-ACME-CORP is
degraded" backward through dependencies to "LINK-SYD-MEL-FIBRE-01 is dark."

---

## Data stores and what lives in them

| Store | Azure Service | Contents | Query method |
|-------|---------------|----------|--------------|
| **Topology graph** | Azure Cosmos DB (Gremlin) | 8 entity types, 7 relationship types, ~50 nodes | Gremlin via graph-query-api |
| **Telemetry** | Azure Cosmos DB NoSQL | `AlertStream` (alerts with severity, optical power, BER, CPU, packet loss), `LinkTelemetry` (5-min interval readings per link) | SQL via graph-query-api |
| **Runbooks** | Azure AI Search (`runbooks-index`) | 5 operational runbooks: fibre cut, BGP peer loss, alert storm triage, traffic reroute, customer communication | Hybrid search (vector + keyword) |
| **Tickets** | Azure AI Search (`tickets-index`) | 10 historical incidents (Aug 2025 – Feb 2026) with root cause, resolution, timing, lessons learned | Hybrid search (vector + keyword) |

---

## The agents

Five Foundry agents, each scoped to one responsibility:

| Agent | Role | Data source | Tool |
|-------|------|-------------|------|
| **Orchestrator** | Supervisor. Receives alert, coordinates investigation, synthesises diagnosis. Does not access data directly. | — | ConnectedAgentTool (all 4 below) |
| **GraphExplorerAgent** | Topology and dependency analysis. Forward trace (link → path → service → SLA) and reverse trace (service → path → link). | Cosmos DB Gremlin | OpenApiTool → graph-query-api |
| **TelemetryAgent** | Raw data retrieval. Returns alerts, telemetry readings, metric values without interpretation. The orchestrator interprets. | Cosmos DB NoSQL | OpenApiTool → graph-query-api |
| **RunbookKBAgent** | Procedure lookup. Returns SOPs, diagnostic steps, escalation paths, communication templates. | AI Search `runbooks-index` | AzureAISearchTool |
| **HistoricalTicketAgent** | Precedent search. Finds past incidents with matching root cause type, corridor, or failure pattern. | AI Search `tickets-index` | AzureAISearchTool |

---

## The investigation flow

The orchestrator receives the alert storm and follows Flow B (alert storm /
service-level symptoms → work backward to root cause):

**Step 1 — Analyse the alert storm** (TelemetryAgent)
Fetch recent alerts across all entities. The orchestrator interprets: 20
alerts in under one second, multiple SERVICE_DEGRADATION across VPN, broadband,
and mobile services. Earliest alerts cluster around VPN-ACME-CORP and
VPN-BIGBANK. Optical power readings are anomalous (< -30 dBm).

**Step 2 — Find the common cause** (GraphExplorerAgent)
Take the list of affected service IDs and trace their dependency chains.
All affected services share a common infrastructure ancestor:
LINK-SYD-MEL-FIBRE-01. The graph reveals the three-hop path:
Service → MPLSPath → TransportLink → the cut fibre.

**Step 3 — Confirm root cause status** (TelemetryAgent)
Fetch telemetry for LINK-SYD-MEL-FIBRE-01. Optical power: -31.2 dBm (loss
of light). BER: 1.0 (total). Utilisation: 0%. Status: confirmed down.

**Step 4 — Rank root causes** (Orchestrator reasoning)
1. **Fibre cut on LINK-SYD-MEL-FIBRE-01** — loss of light, total BER, all
   dependent services impacted simultaneously. Evidence is conclusive.
2. **Transceiver failure** — possible but ruled out because both ends report
   loss of light (not single-end).
3. **BGP flap (independent)** — ruled out because BGP loss correlates
   temporally with the link failure, not vice versa.

**Step 5 — Assess blast radius** (GraphExplorerAgent)
Full downstream impact: MPLS-PATH-SYD-MEL-PRIMARY carries VPN-ACME-CORP
and VPN-BIGBANK. Broadband and mobile services affected via aggregation
paths. SLA policies retrieved — availability breach window, latency
thresholds, financial penalties.

**Step 6 — Retrieve procedures** (RunbookKBAgent)
Alert storm triage guide for correlation methodology. Fibre cut runbook for
verification steps and immediate actions (suppress downstream alerts,
assess alternate path, initiate MPLS failover to LINK-SYD-MEL-FIBRE-02).
Traffic engineering reroute procedure for failover execution. Customer
communication template for enterprise notification.

**Step 7 — Check precedents** (HistoricalTicketAgent)
INC-2025-08-14-0042: identical scenario — fibre cut on the same link by
contractor, 1,847 downstream alerts, traffic rerouted to FIBRE-02 in 45
seconds, physical repair in 6 hours. Lesson learned: alternate path had
sufficient capacity (38% utilisation); consider pre-provisioned automatic
failover for enterprise VPN customers.

**Step 8 — Situation report** (Orchestrator synthesis)
Structured output: incident summary, blast radius with entity IDs, ranked
root causes with evidence, recommended actions citing specific runbooks,
historical precedents with resolution times, risk assessment with SLA
breach windows.

---

## What this proves

| Claim | Evidence |
|-------|----------|
| **Azure can host a knowledge plane** | Cosmos DB Gremlin encodes network topology as a queryable graph with typed entities and relationships. Not a flat database — real semantic structure with multi-hop traversal. |
| **Agents can reason over structured knowledge** | GraphExplorerAgent traces 3-hop dependency chains (link → path → service → SLA) to determine blast radius from a single root cause. |
| **Agents combine structured + unstructured knowledge** | Topology from the graph, telemetry from Cosmos DB NoSQL, runbooks and tickets from vector search — four data modalities fused into one diagnosis. |
| **Multi-agent orchestration works at production quality** | Orchestrator delegates to four specialists, synthesises their outputs into a structured situation report, cites sources, and does not fabricate. |
| **The entire stack is Azure-native** | Cosmos DB (Gremlin graph, NoSQL telemetry), AI Foundry (agents, GPT-4.1), AI Search, Azure Storage. No external dependencies. |
| **This is the path to autonomous operations** | Today: agents diagnose and recommend. Next: agents execute (MPLS failover, ticket creation, customer notification) with human approval gates. Eventually: humans outside the loop for low-risk actions. |

---

## Autonomy progression

The demo sits at Level 3 on the TM Forum autonomous networks scale
(conditional automation — AI recommends, human approves). The architecture
is designed to progress:

```
L3 (this demo)     → Agents diagnose, recommend actions, human executes
L4 (next phase)    → Agents execute low-risk actions (create ticket, send
                     notification), human approves high-risk (reroute traffic)
L5 (end state)     → Agents self-heal, human monitors exceptions only
```

The gap between L3 and L4 is not architectural — it is trust. The same
agents, the same tools, the same knowledge graph. What changes is the
approval gate: from mandatory human approval on every action to selective
gating based on risk classification.

---

## End goal

A fully Azure-native autonomous network operations platform that a telco
can deploy on their own Azure tenant. Cosmos DB for the knowledge plane
(topology graph, telemetry store). Foundry for the reasoning plane (agents,
models, orchestration). AI Search for operational knowledge (runbooks,
tickets). No vendor lock-in to third-party AIOps platforms. The telco owns
the data, the models, the agents, and the knowledge graph — all running on
infrastructure they already pay for.
