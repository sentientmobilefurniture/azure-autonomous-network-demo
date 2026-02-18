# V12 — Telco NOC Scenario Deep Dive

## 1. What Problem Is This Showing?

### The Core Pain Point: Alert Storm Root-Cause Analysis

Telecom Network Operations Centres (NOCs) face a brutal operational reality: **a single physical fault generates thousands of cascading alerts across multiple network layers within seconds**. A fibre cut on a backbone corridor doesn't just produce one alarm — it triggers a chain reaction:

1. **Physical layer** — loss of light on the transport link (1 alert)
2. **Routing layer** — BGP peer loss on both routers (2 alerts), OSPF adjacency drops (4 alerts), route withdrawals (20 alerts)
3. **Service layer** — every enterprise VPN, broadband bundle, and mobile service that transits the failed link starts degrading (hundreds of SERVICE_DEGRADATION alerts)
4. **Noise layer** — keepalive timeouts, duplicate alerts, and transient threshold breaches pile up (thousands of MINOR alerts)

**Result:** ~3,700 alerts in ~2 hours, of which exactly **1** is the root cause and the rest are symptoms.

Human NOC operators spend 30–90 minutes manually triaging these storms. During that time, SLA clocks are ticking ($50,000/hour for a GOLD enterprise customer), customers are calling, and the blast radius is growing. The scenario demonstrates how an AI-powered autonomous network operations system can:

- **Cut through the noise** — correlate alerts across layers using the topology graph
- **Identify root cause in seconds** — trace the earliest CRITICAL alert to its infrastructure entity
- **Map the blast radius** — traverse graph relationships to determine every affected service, customer, and SLA
- **Recommend remediation** — match the incident type to runbook procedures, draw on historical precedent
- **Quantify financial exposure** — calculate SLA penalty risk by linking services to their policy tiers

### Why This Matters for Telco

| Pain Point | How the Scenario Demonstrates It |
|---|---|
| **Alert fatigue** | 3,691 alerts from 1 fibre cut — operators can't manually triage this |
| **Slow MTTR** | Without graph-based correlation, root cause takes 30–90 min to find |
| **SLA penalty exposure** | GOLD tier customers face $50K/hr penalties — every minute matters |
| **Siloed data** | Topology, telemetry, runbooks, and tickets are in separate systems |
| **Institutional knowledge loss** | Past incident resolutions live in tickets that new operators can't find |

---

## 2. How Does It Work? (Architecture)

### Multi-Agent Orchestration

The scenario uses a **4-specialist-agent + 1-orchestrator** architecture, each with a dedicated data domain:

```
                    ┌─────────────────────┐
                    │    Orchestrator      │
                    │  (Diagnosis Engine)  │
                    └──────────┬──────────┘
                               │
          ┌────────────┬───────┴───────┬────────────┐
          │            │               │            │
   ┌──────▼──────┐ ┌───▼────┐ ┌────────▼───┐ ┌─────▼──────┐
   │  Graph      │ │Telemetry│ │  Runbook   │ │ Historical │
   │  Explorer   │ │ Agent   │ │  KB Agent  │ │  Ticket    │
   │  Agent      │ │         │ │            │ │  Agent     │
   └──────┬──────┘ └───┬────┘ └────────┬───┘ └─────┬──────┘
          │            │               │            │
   Fabric Graph   Fabric KQL    AI Search      AI Search
   (Topology)    (Alerts &     (Runbooks)     (Tickets)
                 Telemetry)
```

**Orchestrator** — Coordinates the investigation. Receives the user query (or alert storm trigger), delegates to specialists, synthesises findings into a diagnosis with root cause, blast radius, and remediation plan.

**GraphExplorerAgent** — Queries the Fabric Graph (GQL/Gremlin) to traverse the network topology ontology. Answers: "What services depend on this link?", "What MPLS paths transit this corridor?", "What's the SLA for this customer?"

**TelemetryAgent** — Queries Fabric KQL (Kusto) for time-series telemetry and alert streams. Returns raw data: optical power readings, link utilisation, alert types and severities. Does not interpret — the Orchestrator does.

**RunbookKBAgent** — Searches Azure AI Search over operational runbook documents. Returns standard operating procedures for fibre cuts, BGP peer loss, alert storm triage, traffic reroutes.

**HistoricalTicketAgent** — Searches Azure AI Search over past incident tickets. Returns precedents: "This exact link failed 3 times before — here's what worked."

---

## 3. The Ontology (Graph Schema)

### Vertex Types (8 entity types)

| Label | CSV Source | ID Column | Count | Purpose |
|---|---|---|---|---|
| **CoreRouter** | DimCoreRouter.csv | RouterId | 3 | Backbone routers (Sydney, Melbourne, Brisbane) — Cisco ASR-9922, Juniper MX10008 |
| **AggSwitch** | DimAggSwitch.csv | SwitchId | 6 | Aggregation switches — 2 per city, uplink to core router |
| **BaseStation** | DimBaseStation.csv | StationId | 8 | 5G NR base stations — backhaul via aggregation switches |
| **TransportLink** | DimTransportLink.csv | LinkId | 10 | Physical transport links — 4 DWDM backbone + 6 metro 100GE |
| **MPLSPath** | DimMPLSPath.csv | PathId | 5 | Logical MPLS label-switched paths — PRIMARY, SECONDARY, TERTIARY |
| **Service** | DimService.csv | ServiceId | 10 | Customer-facing services — 3 enterprise VPNs, 3 broadband bundles, 4 mobile 5G |
| **SLAPolicy** | DimSLAPolicy.csv | SLAPolicyId | 5 | SLA contracts — GOLD ($50K/hr), SILVER ($25K/hr), STANDARD ($0) |
| **BGPSession** | DimBGPSession.csv | SessionId | 3 | eBGP peering sessions between core routers (AS64512–64514) |

### Edge Types (7 relationship types)

| Label | Source → Target | CSV Source | Count | Meaning |
|---|---|---|---|---|
| **connects_to** | TransportLink → CoreRouter | DimTransportLink.csv | 20 (2 per link) | Physical connectivity — each link connects to source and target router |
| **aggregates_to** | AggSwitch → CoreRouter | DimAggSwitch.csv | 6 | Metro aggregation — switch uplinks to its parent core router |
| **backhauls_via** | BaseStation → AggSwitch | DimBaseStation.csv | 8 | RAN backhaul — base station connects via aggregation switch |
| **routes_via** | MPLSPath → TransportLink | FactMPLSPathHops.csv | 9 (filtered) | Logical-to-physical mapping — which transport links an MPLS path traverses |
| **depends_on** | Service → MPLSPath/AggSwitch/BaseStation | FactServiceDependency.csv | 15 | Service dependency — which infrastructure a service relies on |
| **governed_by** | SLAPolicy → Service | DimSLAPolicy.csv | 5 | Contractual binding — which SLA governs a service |
| **peers_over** | BGPSession → CoreRouter | DimBGPSession.csv | 6 (2 per session) | Routing peering — which routers participate in a BGP session |

### Ontology Diagram

```
BaseStation ──backhauls_via──▶ AggSwitch ──aggregates_to──▶ CoreRouter
                                                               ▲
                                                               │
                                               TransportLink ──connects_to
                                                     ▲
                                                     │
                                              MPLSPath ──routes_via
                                                     ▲
                                                     │
                                              Service ──depends_on──▶ MPLSPath
                                                │                      AggSwitch
                                                │                      BaseStation
                                                ▼
                                            SLAPolicy ──governed_by──▶ Service

                                BGPSession ──peers_over──▶ CoreRouter
```

### Why This Ontology Design?

The ontology is purpose-built for **blast radius analysis**. Given any failing entity, you can traverse the graph to answer:

- **Upstream:** "What is the root cause?" — follow `connects_to`, `routes_via` edges upstream to the physical layer
- **Downstream:** "What is affected?" — follow `depends_on`, `governed_by` edges downstream to services and SLAs
- **Lateral:** "What else shares this infrastructure?" — find all services that `depends_on` the same MPLSPath or TransportLink

---

## 4. Graph Data — Entity Details

### CoreRouter (3 nodes)

| RouterId | City | Region | Vendor | Model |
|---|---|---|---|---|
| CORE-SYD-01 | Sydney | NSW | Cisco | ASR-9922 |
| CORE-MEL-01 | Melbourne | VIC | Cisco | ASR-9922 |
| CORE-BNE-01 | Brisbane | QLD | Juniper | MX10008 |

These form a **triangle topology** — SYD↔MEL, SYD↔BNE, MEL↔BNE — providing path diversity for failover.

### TransportLink (10 links)

**Backbone (DWDM 100G) — 4 links:**

| LinkId | Type | Capacity | Source | Target |
|---|---|---|---|---|
| LINK-SYD-MEL-FIBRE-01 | DWDM_100G | 100 Gbps | CORE-SYD-01 | CORE-MEL-01 |
| LINK-SYD-MEL-FIBRE-02 | DWDM_100G | 100 Gbps | CORE-SYD-01 | CORE-MEL-01 |
| LINK-SYD-BNE-FIBRE-01 | DWDM_100G | 100 Gbps | CORE-SYD-01 | CORE-BNE-01 |
| LINK-MEL-BNE-FIBRE-01 | DWDM_100G | 100 Gbps | CORE-MEL-01 | CORE-BNE-01 |

Two parallel fibres on the SYD-MEL corridor (FIBRE-01 and FIBRE-02) — this is realistic telco design for redundancy. The scenario's fibre cut hits FIBRE-01, leaving FIBRE-02 as the secondary path.

**Metro (100GE) — 6 links:**

| LinkId | Type | Capacity | Router |
|---|---|---|---|
| LINK-SYD-AGG-NORTH-01 | 100GE | 100 Gbps | CORE-SYD-01 |
| LINK-SYD-AGG-SOUTH-01 | 100GE | 100 Gbps | CORE-SYD-01 |
| LINK-MEL-AGG-EAST-01 | 100GE | 100 Gbps | CORE-MEL-01 |
| LINK-MEL-AGG-WEST-01 | 100GE | 100 Gbps | CORE-MEL-01 |
| LINK-BNE-AGG-CENTRAL-01 | 100GE | 100 Gbps | CORE-BNE-01 |
| LINK-BNE-AGG-SOUTH-01 | 100GE | 100 Gbps | CORE-BNE-01 |

### MPLSPath (5 paths)

| PathId | Type | Hops (in order) |
|---|---|---|
| MPLS-PATH-SYD-MEL-PRIMARY | PRIMARY | SYD-01 → FIBRE-01 → MEL-01 |
| MPLS-PATH-SYD-MEL-SECONDARY | SECONDARY | SYD-01 → FIBRE-02 → MEL-01 |
| MPLS-PATH-SYD-BNE-PRIMARY | PRIMARY | SYD-01 → SYD-BNE-FIBRE-01 → BNE-01 |
| MPLS-PATH-MEL-BNE-PRIMARY | PRIMARY | MEL-01 → MEL-BNE-FIBRE-01 → BNE-01 |
| MPLS-PATH-SYD-MEL-VIA-BNE | TERTIARY | SYD-01 → SYD-BNE-FIBRE-01 → BNE-01 → MEL-BNE-FIBRE-01 → MEL-01 |

The TERTIARY path (SYD→BNE→MEL) is the last-resort route if both direct SYD-MEL fibres fail. This path exists in the data and was used in historical ticket INC-2025-11-22-0055 (storm damage, both fibres cut).

### Service (10 services)

| ServiceId | Type | Customer | Users |
|---|---|---|---|
| VPN-ACME-CORP | EnterpriseVPN | ACME Corporation | 450 |
| VPN-BIGBANK | EnterpriseVPN | BigBank Financial | 1,200 |
| VPN-OZMINE | EnterpriseVPN | OzMine Resources | 680 |
| BB-BUNDLE-SYD-NORTH | Broadband | Residential - Sydney North | 3,200 |
| BB-BUNDLE-MEL-EAST | Broadband | Residential - Melbourne East | 2,800 |
| BB-BUNDLE-BNE-CENTRAL | Broadband | Residential - Brisbane Central | 2,400 |
| MOB-5G-SYD-2041 | Mobile5G | Mobile Subscribers | 4,200 |
| MOB-5G-SYD-2042 | Mobile5G | Mobile Subscribers | 4,300 |
| MOB-5G-MEL-3011 | Mobile5G | Mobile Subscribers | 3,800 |
| MOB-5G-BNE-4011 | Mobile5G | Mobile Subscribers | 3,600 |

**Total affected users across all services: ~24,630**

### Service Dependencies (FactServiceDependency — 15 rows)

| Service | Depends On | Type | Strength |
|---|---|---|---|
| VPN-ACME-CORP | MPLS-PATH-SYD-MEL-PRIMARY | MPLSPath | PRIMARY |
| VPN-ACME-CORP | MPLS-PATH-SYD-MEL-SECONDARY | MPLSPath | SECONDARY |
| VPN-ACME-CORP | MPLS-PATH-SYD-MEL-VIA-BNE | MPLSPath | TERTIARY |
| VPN-BIGBANK | MPLS-PATH-SYD-MEL-PRIMARY | MPLSPath | PRIMARY |
| VPN-BIGBANK | MPLS-PATH-SYD-MEL-SECONDARY | MPLSPath | SECONDARY |
| VPN-BIGBANK | MPLS-PATH-SYD-MEL-VIA-BNE | MPLSPath | TERTIARY |
| VPN-OZMINE | MPLS-PATH-SYD-BNE-PRIMARY | MPLSPath | PRIMARY |
| VPN-OZMINE | MPLS-PATH-SYD-MEL-VIA-BNE | MPLSPath | SECONDARY |
| BB-BUNDLE-SYD-NORTH | AGG-SYD-NORTH-01 | AggSwitch | PRIMARY |
| BB-BUNDLE-MEL-EAST | AGG-MEL-EAST-01 | AggSwitch | PRIMARY |
| BB-BUNDLE-BNE-CENTRAL | AGG-BNE-CENTRAL-01 | AggSwitch | PRIMARY |
| MOB-5G-SYD-2041 | GNB-SYD-2041 | BaseStation | PRIMARY |
| MOB-5G-SYD-2042 | GNB-SYD-2042 | BaseStation | PRIMARY |
| MOB-5G-MEL-3011 | GNB-MEL-3011 | BaseStation | PRIMARY |
| MOB-5G-BNE-4011 | GNB-BNE-4011 | BaseStation | PRIMARY |

Key insight: VPN-ACME-CORP and VPN-BIGBANK both depend on the same primary MPLS path through LINK-SYD-MEL-FIBRE-01. When that link fails, both enterprise customers are impacted simultaneously.

### SLAPolicy (5 policies)

| SLAPolicyId | Service | Availability | Max Latency | Penalty/Hour | Tier |
|---|---|---|---|---|---|
| SLA-ACME-GOLD | VPN-ACME-CORP | 99.99% | 15 ms | $50,000 | GOLD |
| SLA-BIGBANK-SILVER | VPN-BIGBANK | 99.95% | 20 ms | $25,000 | SILVER |
| SLA-OZMINE-GOLD | VPN-OZMINE | 99.99% | 18 ms | $40,000 | GOLD |
| SLA-BB-SYD-STANDARD | BB-BUNDLE-SYD-NORTH | 99.5% | 50 ms | $0 | STANDARD |
| SLA-BB-BNE-STANDARD | BB-BUNDLE-BNE-CENTRAL | 99.5% | 50 ms | $0 | STANDARD |

**Maximum financial exposure per hour: $115,000** (ACME + BigBank + OzMine combined)

### BGPSession (3 sessions)

| SessionId | Peer A | Peer B | AS A | AS B |
|---|---|---|---|---|
| BGP-SYD-MEL-01 | CORE-SYD-01 | CORE-MEL-01 | 64512 | 64513 |
| BGP-SYD-BNE-01 | CORE-SYD-01 | CORE-BNE-01 | 64512 | 64514 |
| BGP-MEL-BNE-01 | CORE-MEL-01 | CORE-BNE-01 | 64513 | 64514 |

Private ASNs (64512–64514) represent the telco's own backbone BGP mesh.

---

## 5. Telemetry Data

### AlertStream (3,691 alerts)

**Time window:** 2026-02-04T08:30 → 2026-02-06T14:31 (~54 hours)

**Distribution by type:**

| Alert Type | Count | Meaning |
|---|---|---|
| PACKET_LOSS_THRESHOLD | 1,198 | Transient packet loss events (mostly noise) |
| SERVICE_DEGRADATION | 1,144 | Service-level impact — the downstream effect |
| DUPLICATE_ALERT | 886 | Re-fired alerts from the same source (noise) |
| HIGH_CPU | 436 | Routers under load during reroute convergence |
| ROUTE_WITHDRAWAL | 20 | BGP routes being withdrawn after link failure |
| OSPF_ADJACENCY_DOWN | 4 | OSPF neighbours lost on failed interfaces |
| BGP_PEER_LOSS | 2 | BGP sessions dropped (SYD↔MEL) |
| LINK_DOWN | 1 | **THE ROOT CAUSE** — loss of light on FIBRE-01 |

**Distribution by severity:**

| Severity | Count |
|---|---|
| MINOR | 2,528 (68.5%) |
| WARNING | 657 (17.8%) |
| MAJOR | 372 (10.1%) |
| CRITICAL | 134 (3.6%) |

### The Incident Timeline (2026-02-06)

The scenario contains a clear fibre-cut incident with precise temporal ordering:

| Time | Event | Alert Type | Entity |
|---|---|---|---|
| **14:30:00.000** | Loss of light on FIBRE-01 | LINK_DOWN (CRITICAL) | LINK-SYD-MEL-FIBRE-01 |
| **14:30:02.100** | BGP peer SYD→MEL unreachable | BGP_PEER_LOSS (CRITICAL) | CORE-SYD-01 |
| **14:30:02.300** | BGP peer MEL→SYD unreachable | BGP_PEER_LOSS (CRITICAL) | CORE-MEL-01 |
| **14:30:04–05** | OSPF adjacencies drop (4 alerts) | OSPF_ADJACENCY_DOWN (MAJOR) | CORE-SYD-01, CORE-MEL-01 |
| **14:30:07–08** | Route withdrawals begin (20 alerts) | ROUTE_WITHDRAWAL (MAJOR) | CORE-SYD-01, CORE-MEL-01 |
| **14:30:08+** | Alert storm begins — hundreds of SERVICE_DEGRADATION, HIGH_CPU, PACKET_LOSS_THRESHOLD alerts cascade | Mixed | All downstream entities |

### LinkTelemetry (8,640 readings)

5-minute interval time-series for all 10 transport links over ~3 days. Metrics per reading:

- **UtilizationPct** — link capacity usage
- **OpticalPowerDbm** — optical signal strength
- **BitErrorRate** — bit error rate
- **LatencyMs** — round-trip latency

**The fibre cut signature in LinkTelemetry for LINK-SYD-MEL-FIBRE-01:**

| Time | Util% | OpticalPower | BER | Latency |
|---|---|---|---|---|
| 14:25 | 54.3% | -3.0 dBm | 6.6e-12 | 5.4 ms |
| **14:30** | **0.0%** | **-40.0 dBm** | **1.0** | **9999 ms** |
| 14:35 | 0.0% | -40.0 dBm | 1.0 | 9999 ms |
| ... | 0.0% | -40.0 dBm | 1.0 | 9999 ms |

Classic loss-of-light signature: optical power drops from -3 dBm to -40 dBm, BER goes to 1.0 (total error), latency becomes 9999 ms (unreachable), utilisation drops to 0%.

---

## 6. Knowledge Sources

### Runbooks (5 documents — Azure AI Search index: `telco-noc-runbooks-index`)

| Document | Purpose | Key Content |
|---|---|---|
| **fibre_cut_runbook.md** | Fibre cut detection, verification, recovery | Detection criteria (optical power < -30 dBm, BER = 1.0), verification steps, immediate actions (suppress downstream alerts, assess alternate path, initiate MPLS failover), escalation ladder (L1→L2→L3) |
| **alert_storm_triage_guide.md** | Alert storm root cause identification | 3-step triage: temporal clustering (find earliest alert), topological correlation (common upstream ancestor in graph), alert type hierarchy (physical → routing → service) |
| **bgp_peer_loss_runbook.md** | BGP session diagnosis and recovery | Decision tree: is transport link down? → root cause is transport, not BGP. Is remote router reachable via alternate path? → path-specific issue |
| **traffic_engineering_reroute.md** | MPLS traffic reroute procedure | Pre-checks (alternate path exists, capacity < 80%, no conflicting maintenance), execution steps, post-reroute validation |
| **customer_communication_template.md** | SLA breach notification templates | Templates for initial notification (within 15 min), update cadence, resolution notification. Placeholder fields for incident details |

### Historical Tickets (10 incidents — Azure AI Search index: `telco-noc-tickets-index`)

| Ticket ID | Title | Severity | Root Cause | Resolution Time | SLA Breach? |
|---|---|---|---|---|---|
| INC-2025-08-14-0042 | Fibre cut SYD-MEL — contractor damage | P1 | LINK-SYD-MEL-FIBRE-01 | 6 hours | No |
| INC-2025-09-02-0018 | DWDM amplifier failure MEL-BNE | P1 | LINK-MEL-BNE-FIBRE-01 | 4 hours | No |
| INC-2025-10-19-0007 | BGP misconfiguration — route leak SYD-BNE | P2 | CORE-BNE-01 | 14 min | No |
| INC-2025-11-05-0031 | Power outage AGG-SYD-NORTH-01 — UPS failure | P1 | AGG-SYD-NORTH-01 | 8 min | No |
| INC-2025-11-22-0055 | Fibre cut SYD-MEL — storm damage (BOTH fibres) | P1 | LINK-SYD-MEL-FIBRE-01 | 18 hours | **Yes** |
| INC-2025-12-03-0012 | Base station backhaul degradation | P3 | GNB-MEL-3011 | 3 days | No |
| INC-2026-01-08-0003 | OSPF flap storm — IOS-XR bug | P2 | CORE-SYD-01 | 45 min | No |
| INC-2026-01-15-0021 | Capacity exhaustion FIBRE-02 during maintenance | P2 | LINK-SYD-MEL-FIBRE-02 | 2 hours | No |
| INC-2026-01-28-0009 | DNS resolution failure (customer-side) | P2 | VPN-ACME-CORP | 1 hour | No |
| INC-2026-02-01-0015 | Scheduled fibre maintenance SYD-BNE | P3 | LINK-SYD-BNE-FIBRE-01 | 6 hours | No |

**Historical patterns worth noting:**
- LINK-SYD-MEL-FIBRE-01 is a **repeat offender** — 3 incidents in 6 months (contractor damage, storm damage, current incident)
- The storm-damage incident (INC-2025-11-22-0055) is the only SLA breach — both SYD-MEL fibres were cut simultaneously, forcing the TERTIARY path via Brisbane (higher latency)
- A mix of root cause types: FIBRE_CUT, AMPLIFIER_FAILURE, MISCONFIGURATION, POWER_FAILURE, SOFTWARE_BUG, CAPACITY_EXHAUSTION, SERVICE_MISCONFIGURATION, PLANNED_MAINTENANCE

---

## 7. The Demonstration Flow

When the scenario runs, the default prompt ([alert_storm.md](../data/scenarios/telco-noc/data/prompts/alert_storm.md)) feeds the Orchestrator a raw dump of ~20 recent critical/major alerts. The AI then:

1. **Temporal clustering** — Identifies the LINK_DOWN at 14:30:00 as the earliest alert
2. **Graph traversal** — Asks GraphExplorerAgent: "What MPLS paths traverse LINK-SYD-MEL-FIBRE-01?" → finds PRIMARY and SECONDARY paths, traces to VPN-ACME-CORP, VPN-BIGBANK
3. **Telemetry verification** — Asks TelemetryAgent: "Get LinkTelemetry for LINK-SYD-MEL-FIBRE-01" → confirms loss of light (-40 dBm, BER=1.0)
4. **Runbook lookup** — Asks RunbookKBAgent: "Fibre cut procedure" → gets detection criteria, immediate actions, escalation
5. **Historical precedent** — Asks HistoricalTicketAgent: "Previous fibre cuts on SYD-MEL corridor" → finds INC-2025-08-14-0042 (resolved in 6h) and INC-2025-11-22-0055 (SLA breach, 18h)
6. **Synthesis** — Produces a diagnosis report with root cause, blast radius, affected services, SLA exposure ($75K/hr for ACME+BigBank), remediation steps, and historical context

---

## 8. Data Generation

All data is generated by Python scripts in [scripts/](../data/scenarios/telco-noc/scripts/):

| Script | What it generates |
|---|---|
| `generate_topology.py` | DimCoreRouter, DimAggSwitch, DimBaseStation, DimTransportLink CSVs |
| `generate_routing.py` | DimMPLSPath, DimService, DimSLAPolicy, DimBGPSession, FactMPLSPathHops, FactServiceDependency CSVs |
| `generate_telemetry.py` | AlertStream.csv, LinkTelemetry.csv — includes realistic noise + the fibre-cut incident |
| `generate_tickets.py` | Historical incident tickets in data/knowledge/tickets/ |
| `generate_all.sh` | Runs all generators in sequence |

---

## 9. Summary Statistics

| Category | Metric | Value |
|---|---|---|
| **Graph** | Vertex types | 8 |
| | Edge types | 7 |
| | Total vertices | ~50 |
| | Total edges | ~69 |
| **Telemetry** | Alert records | 3,691 |
| | Telemetry readings | 8,640 |
| | Time span | ~54 hours |
| **Knowledge** | Runbook documents | 5 |
| | Historical tickets | 10 |
| **Services** | Enterprise VPN customers | 3 |
| | Broadband bundles | 3 |
| | Mobile 5G services | 4 |
| | Total end users affected | ~24,630 |
| **Financial** | Max SLA penalty/hour | $115,000 |
| **Agents** | Specialist agents | 4 |
| | Orchestrator | 1 |

---

## 10. Proposed Enhancements

### Scenarios Requiring No Graph Changes

| # | Scenario | New Data Needed | Demo Value |
|---|---|---|---|
| 1 | **Planned Maintenance Impact Analysis** — "We need to take LINK-SYD-MEL-FIBRE-01 offline Saturday. What's the blast radius?" Same graph traversal as fibre cut, but proactive. | New prompt only | Shows AI doing proactive risk assessment, not just reactive diagnosis |
| 2 | **AggSwitch Power Failure** — AGG-SYD-NORTH-01 loses power, all downstream BaseStations lose backhaul, mobile/broadband degrade but enterprise VPNs unaffected. Different blast radius shape. | New telemetry + prompt | Demonstrates traversal through `backhauls_via` path — mobile/broadband-only impact |
| 3 | **Capacity Congestion (Slow Burn)** — Evening peak pushes FIBRE-02 to 95% utilisation during FIBRE-01 maintenance. QoS drops broadband, enterprise VPNs survive. | New telemetry showing gradual ramp | Non-failure scenario — shows breadth beyond hard faults |

### Scenarios Requiring Graph Expansion

| # | Scenario | Graph Addition | New Data Needed | Demo Value |
|---|---|---|---|---|
| 4 | **Shared Physical Risk / Conduit Correlation** — Both SYD-MEL fibres share the same conduit near Goulburn. Storm takes out both. Why did "redundancy" fail? | `PhysicalConduit` vertex (2–3 nodes), `routed_through` edges (~4) | Small graph expansion | Explains the dual-fibre-cut SLA breach (INC-2025-11-22-0055) — powerful for planners |
| 5 | **Predictive Degradation (Amplifier Aging)** — Optical power on MEL-BNE slowly drops from -3 → -20 dBm over 2 weeks. AI spots trend and predicts failure before it happens. | `AmplifierSite` vertex (3–4 nodes), `amplifies` edges (~8) | Slow-degradation telemetry series | Most impressive for audience: "AI predicted the failure 3 days early" |
| 6 | **Multi-Vendor Software Bug Correlation** — OSPF flaps on CORE-SYD-01 match a known IOS-XR bug. AI correlates firmware version to advisory. | `FirmwareVersion` property on CoreRouter, `Advisory` vertex with `affects_version` edges | Advisory documents for AI Search | Shows AI as knowledge correlator — connects telemetry patterns to vendor advisories |

### Priority Recommendation

**Phase 1 (no code changes):** Scenarios 1 + 2 — new prompts and telemetry only, dramatically widen the demo repertoire.  
**Phase 2 (small graph expansion):** Scenario 4 (PhysicalConduit) — ~5 vertices, ~10 edges, unlocks the "hidden shared risk" narrative.  
**Phase 3 (medium expansion):** Scenario 5 (predictive) — most impressive for exec audiences, requires sustained telemetry generation.

---

## 11. Demo Flows

### Demo Flow 1: Fibre Cut — Reactive Alert Storm Diagnosis

> **Core value demonstrated:** AI cuts through thousands of cascading alerts to find root cause in seconds, maps blast radius across the full service stack, and recommends remediation with financial context — a task that takes human NOC operators 30–90 minutes.

#### Prompt

> "We're seeing a massive alert storm — over 3,000 alerts in the last 90 seconds across the SYD-MEL corridor. Multiple enterprise VPNs are reporting tunnel failures, broadband customers are complaining, and CPU on both SYD and MEL core routers is spiking. What's happening, what's affected, and what do we do?"

#### Orchestrator Investigation Workflow

```
Step 1: TEMPORAL CLUSTERING (TelemetryAgent)
│  "Get the 20 most recent CRITICAL and MAJOR alerts, ordered by timestamp"
│  → Receives alert list. Identifies LINK_DOWN on LINK-SYD-MEL-FIBRE-01 at
│    14:30:00.000 as the EARLIEST alert. Everything else follows 2–8 seconds later.
│  → Hypothesis: LINK-SYD-MEL-FIBRE-01 is the root cause.
│
Step 2: TELEMETRY VERIFICATION (TelemetryAgent)
│  "Get LinkTelemetry readings for LINK-SYD-MEL-FIBRE-01 from the last 30 minutes"
│  → Confirms loss-of-light signature: OpticalPower = -40 dBm, BER = 1.0,
│    Latency = 9999 ms, Utilization = 0%. Classic fibre cut.
│
Step 3: BLAST RADIUS — INFRASTRUCTURE (GraphExplorerAgent)
│  "What MPLS paths route via LINK-SYD-MEL-FIBRE-01?"
│  → MPLS-PATH-SYD-MEL-PRIMARY (the failed path)
│  "What services depend on MPLS-PATH-SYD-MEL-PRIMARY?"
│  → VPN-ACME-CORP (PRIMARY dependency), VPN-BIGBANK (PRIMARY dependency)
│  "What are the SLA policies for these services?"
│  → SLA-ACME-GOLD: 99.99%, $50K/hr penalty
│  → SLA-BIGBANK-SILVER: 99.95%, $25K/hr penalty
│
Step 4: ALTERNATE PATH ASSESSMENT (GraphExplorerAgent + TelemetryAgent)
│  "What other MPLS paths connect SYD to MEL?"
│  → MPLS-PATH-SYD-MEL-SECONDARY (via FIBRE-02), MPLS-PATH-SYD-MEL-VIA-BNE (tertiary)
│  "Get LinkTelemetry for LINK-SYD-MEL-FIBRE-02"
│  → FIBRE-02 is healthy: OpticalPower = -3 dBm, Utilization = 55%. Safe to reroute.
│
Step 5: RUNBOOK LOOKUP (RunbookKBAgent)
│  "What is the procedure for a fibre cut with an available secondary path?"
│  → fibre_cut_runbook.md: Suppress downstream alerts, verify alternate path
│    utilization < 80%, initiate MPLS failover to secondary, raise P1 incident.
│  → traffic_engineering_reroute.md: Pre-checks passed (55% + rerouted traffic < 80%).
│
Step 6: HISTORICAL PRECEDENT (HistoricalTicketAgent)
│  "Have we had fibre cuts on the SYD-MEL corridor before?"
│  → INC-2025-08-14-0042: Contractor damage, same link. Resolved in 6 hours.
│    Traffic rerouted to FIBRE-02 within 45 seconds. No SLA breach.
│  → INC-2025-11-22-0055: Storm damage, BOTH fibres cut. Took 18 hours.
│    SLA BREACHED. Had to use tertiary path via Brisbane.
│  → Warning: This is the 3rd incident on this link in 6 months.
```

#### Outcome

The Orchestrator produces a **structured diagnosis report**:

- **Root Cause:** Fibre cut on LINK-SYD-MEL-FIBRE-01 — loss of light confirmed at 14:30:00 UTC
- **Blast Radius:** 2 enterprise VPNs (ACME, BigBank), 2,330 enterprise users affected
- **SLA Exposure:** $75,000/hour (ACME $50K + BigBank $25K) — clock started at 14:30
- **Recommended Action:** Initiate MPLS failover to SECONDARY path (FIBRE-02 at 55% util — safe). Suppress 3,600+ downstream alerts. Dispatch field team for physical repair.
- **Historical Context:** 3rd fibre cut on this corridor in 6 months. Previous repair took 6 hours. Recommend conduit route diversity review.
- **Risk Flag:** If FIBRE-02 also fails (as in INC-2025-11-22-0055), only tertiary path via Brisbane available — higher latency, may breach SLA.

---

### Demo Flow 2: Planned Maintenance — Proactive Risk Assessment

> **Core value demonstrated:** AI proactively assesses risk *before* work begins — maps every service, customer, and SLA that would be exposed during a maintenance window, identifies hidden risks from historical data, and recommends safeguards. This turns the NOC from reactive firefighting to proactive risk management.

#### Prompt

> "We have a planned maintenance window this Saturday 02:00–08:00 UTC on LINK-SYD-MEL-FIBRE-01 for fibre splice work. What's the risk exposure, and what safeguards should we put in place?"

#### Orchestrator Investigation Workflow

```
Step 1: MAP THE MAINTENANCE TARGET (GraphExplorerAgent)
│  "What MPLS paths route via LINK-SYD-MEL-FIBRE-01?"
│  → MPLS-PATH-SYD-MEL-PRIMARY
│  "What services depend on MPLS-PATH-SYD-MEL-PRIMARY?"
│  → VPN-ACME-CORP (PRIMARY), VPN-BIGBANK (PRIMARY)
│  "What SLA policies govern these services?"
│  → ACME: GOLD, 99.99%, $50K/hr. BigBank: SILVER, 99.95%, $25K/hr.
│
Step 2: ASSESS FAILOVER PATH READINESS (GraphExplorerAgent + TelemetryAgent)
│  "What alternate MPLS paths exist for SYD-MEL?"
│  → MPLS-PATH-SYD-MEL-SECONDARY (via FIBRE-02), MPLS-PATH-SYD-MEL-VIA-BNE (tertiary)
│  "Get recent LinkTelemetry for LINK-SYD-MEL-FIBRE-02 — what is typical
│   Saturday overnight utilisation?"
│  → Typical overnight: 25–35% utilisation. Safe headroom for rerouted traffic.
│  "What about LINK-SYD-BNE-FIBRE-01 and LINK-MEL-BNE-FIBRE-01 (tertiary path)?"
│  → Both healthy, 20–30% utilisation overnight.
│
Step 3: CHECK FOR CONFLICTING MAINTENANCE (HistoricalTicketAgent)
│  "Are there any other planned maintenance events this weekend?"
│  → INC-2026-02-01-0015: Recent SYD-BNE maintenance took 2 hours longer than
│    planned. If SYD-BNE maintenance coincides, tertiary path also unavailable.
│  → No conflicting events found for this weekend.
│
Step 4: HISTORICAL RISK ASSESSMENT (HistoricalTicketAgent)
│  "What has gone wrong during previous SYD-MEL maintenance windows?"
│  → INC-2026-01-15-0021: During FIBRE-01 maintenance, FIBRE-02 hit 95% utilisation
│    at evening peak. QoS started dropping broadband traffic.
│  → INC-2025-11-22-0055: Both fibres share the same conduit near Goulburn.
│    A storm took out both simultaneously — 18-hour outage, SLA BREACHED.
│  → KEY RISK: If FIBRE-02 fails while FIBRE-01 is under maintenance, there is
│    no direct SYD-MEL path. Only the tertiary BNE route remains.
│
Step 5: RUNBOOK PROCEDURES (RunbookKBAgent)
│  "What is the pre-maintenance checklist for taking down a transport link?"
│  → traffic_engineering_reroute.md: Pre-reroute to SECONDARY before maintenance
│    begins. Verify util < 80%. Enable QoS marking on FIBRE-02 to protect
│    enterprise traffic if congestion occurs.
│  → customer_communication_template.md: Notify ACME and BigBank operations teams
│    48 hours in advance per SLA contract terms.
```

#### Outcome

The Orchestrator produces a **pre-maintenance risk briefing**:

- **Services at Risk During Window:** VPN-ACME-CORP (GOLD), VPN-BIGBANK (SILVER)
- **Financial Exposure if Failover Also Fails:** $75,000/hour
- **Failover Path Status:** FIBRE-02 healthy, 30% overnight util — safe headroom
- **Safeguards Recommended:**
  1. Pre-reroute all SYD-MEL traffic to FIBRE-02 by 01:30 UTC (30 min before window)
  2. Enable QoS priority marking for enterprise VPN traffic on FIBRE-02
  3. Notify ACME and BigBank operations teams 48 hours in advance
  4. Stage tertiary path (via BNE) as warm standby — pre-validate LINK-SYD-BNE and LINK-MEL-BNE
  5. Set alert threshold on FIBRE-02 to CRITICAL if utilisation > 75% during window
- **Historical Warning:** This link has failed 3 times in 6 months. Both SYD-MEL fibres share the same conduit near Goulburn. Recommend future conduit route diversity project.
- **No-Go Criteria:** If FIBRE-02 utilisation exceeds 80% at window start, postpone maintenance.

---

### Demo Flow 3: Cascading Service Degradation — Customer-Initiated Escalation

> **Core value demonstrated:** When a customer calls reporting "our VPN is down", the AI doesn't just confirm the symptom — it traces the full dependency chain from service layer down to physical infrastructure, correlates with real-time telemetry, determines whether this is an isolated issue or part of a broader event, and provides a complete situational picture with ETA and customer-specific context.

#### Prompt

> "ACME Corporation just called — their VPN has been intermittent for the last 10 minutes and they're threatening SLA penalties. Is this a network issue or a customer-side problem? What services share the same infrastructure, and are other customers affected too?"

#### Orchestrator Investigation Workflow

```
Step 1: VERIFY CUSTOMER SERVICE STATUS (TelemetryAgent)
│  "Get recent alerts for SourceNodeId VPN-ACME-CORP"
│  → Multiple SERVICE_DEGRADATION alerts, severity CRITICAL:
│    "VPN tunnel unreachable — primary MPLS path down"
│  → This is a NETWORK-SIDE issue, not customer-side.
│    (Compare: INC-2026-01-28-0009 was customer-side DNS — no network alerts.)
│
Step 2: TRACE SERVICE DEPENDENCY CHAIN (GraphExplorerAgent)
│  "What infrastructure does VPN-ACME-CORP depend on?"
│  → Depends on: MPLS-PATH-SYD-MEL-PRIMARY (PRIMARY),
│    MPLS-PATH-SYD-MEL-SECONDARY (SECONDARY),
│    MPLS-PATH-SYD-MEL-VIA-BNE (TERTIARY)
│  "What transport links does MPLS-PATH-SYD-MEL-PRIMARY route via?"
│  → LINK-SYD-MEL-FIBRE-01
│  "What is the current state of LINK-SYD-MEL-FIBRE-01?"
│
Step 3: CONFIRM INFRASTRUCTURE FAILURE (TelemetryAgent)
│  "Get LinkTelemetry for LINK-SYD-MEL-FIBRE-01 from the last 30 minutes"
│  → Confirmed DOWN: OpticalPower = -40 dBm, BER = 1.0.
│  → Root cause identified: Fibre cut on primary path.
│
Step 4: IDENTIFY CO-AFFECTED CUSTOMERS (GraphExplorerAgent)
│  "What OTHER services also depend on MPLS-PATH-SYD-MEL-PRIMARY?"
│  → VPN-BIGBANK (PRIMARY dependency) — also affected!
│  "What is VPN-BIGBANK's SLA?"
│  → SILVER tier, $25K/hr penalty.
│  "Are there any broadband or mobile services affected?"
│  → BB-BUNDLE-SYD-NORTH depends on AGG-SYD-NORTH-01 (different path — NOT affected)
│  → Mobile services depend on BaseStations (different path — NOT affected)
│  → Impact is limited to SYD-MEL enterprise VPN corridor.
│
Step 5: SLA CLOCK AND FINANCIAL EXPOSURE (GraphExplorerAgent)
│  "What is VPN-ACME-CORP's SLA policy?"
│  → SLA-ACME-GOLD: 99.99% availability, 15 ms max latency, $50,000/hr penalty
│  → Customer reports 10 minutes of intermittent service.
│  → 99.99% allows 52.6 minutes of downtime per year. If this is a new incident,
│    SLA clock started ~10 minutes ago.
│
Step 6: RESOLUTION PATH AND ETA (RunbookKBAgent + HistoricalTicketAgent)
│  "What is the standard resolution for a fibre cut with available secondary?"
│  → MPLS failover to FIBRE-02 should restore service within 45–90 seconds.
│  "Has ACME been affected by fibre cuts before?"
│  → INC-2025-08-14-0042: Same link, same customer. Failover worked in 45 seconds.
│    Physical repair took 6 hours but service was restored via secondary path.
│  → If failover hasn't triggered automatically, manual initiation needed.
```

#### Outcome

The Orchestrator produces a **customer-facing situation report**:

- **Confirmation:** This IS a network-side issue — not customer configuration. Root cause is a fibre cut on LINK-SYD-MEL-FIBRE-01.
- **ACME-Specific Impact:** VPN-ACME-CORP primary MPLS path is down. 450 enterprise users affected.
- **Co-Affected Customers:** VPN-BIGBANK is also affected (1,200 users). BigBank has NOT called yet — **proactively notify them NOW**.
- **Services NOT Affected:** Broadband and mobile services use different infrastructure paths — no broader impact.
- **SLA Status:** ACME GOLD tier — $50K/hr penalty. Clock started ~10 min ago. Combined exposure with BigBank: $75K/hr.
- **Resolution:** MPLS failover to secondary path (FIBRE-02) should restore service. If automatic failover hasn't triggered, initiate manual reroute per traffic_engineering_reroute.md. Expected service restoration: < 2 minutes from manual trigger.
- **Customer Communication:** Use SLA breach notification template. Key message: "Root cause identified, failover initiated, service restoring via alternate path. Physical repair ETA: 6 hours based on precedent INC-2025-08-14-0042."
- **Proactive Action:** Contact BigBank operations team BEFORE they call us.
---

## 12. Effects of Proposed Changes — Old vs New Ontology

This section compares the **current** telco-noc ontology against the **proposed enhanced** ontology after all three phases of enhancements (Section 10) are implemented.

### 12.1 Ontology Comparison

#### Current Ontology

| Vertex Type | Count | Properties |
|---|---|---|
| CoreRouter | 4 | RouterId, City, Region, Vendor, Model |
| AggSwitch | 6 | SwitchId, City, UplinkRouterId |
| BaseStation | 12 | StationId, StationType, AggSwitchId, City |
| TransportLink | 8 | LinkId, LinkType, CapacityGbps, SourceRouterId, TargetRouterId |
| MPLSPath | 5 | PathId, PathType |
| Service | 10 | ServiceId, ServiceType, CustomerName, CustomerCount, ActiveUsers |
| SLAPolicy | 5 | SLAPolicyId, ServiceId, AvailabilityPct, MaxLatencyMs, PenaltyPerHourUSD, Tier |
| BGPSession | 3 | SessionId, PeerARouterId, PeerBRouterId, ASNumberA, ASNumberB |
| **Total** | **~50** | |

| Edge Type | Description | Count |
|---|---|---|
| connects_to | TransportLink → CoreRouter (both endpoints) | ~16 |
| aggregates_to | AggSwitch → CoreRouter | ~6 |
| backhauls_via | BaseStation → AggSwitch | ~12 |
| routes_via | MPLSPath → TransportLink (hop-by-hop) | ~15 |
| depends_on | Service → MPLSPath / AggSwitch / BaseStation | ~14 |
| governed_by | SLAPolicy → Service | ~5 |
| peers_over | BGPSession → CoreRouter (both peers) | ~6 |
| **Total** | | **~69** |

#### Proposed Ontology (After All Phases)

##### New Vertex Types

| Vertex Type | Phase | Count | Properties | Rationale |
|---|---|---|---|---|
| PhysicalConduit | 2 | 2–3 | ConduitId, RouteDescription, MaterialType, InstalledYear | Models shared physical infrastructure that multiple fibres traverse — explains correlated dual-fibre failures |
| AmplifierSite | 3 | 3–4 | SiteId, Location, InstalledYear, LastCalibration | Models optical amplifiers along long-haul fibre routes — enables predictive degradation detection |
| Advisory | 3 | 2–3 | AdvisoryId, VendorName, BugId, AffectedVersions, Severity | Vendor bug advisories and known defect bulletins — enables correlation of telemetry patterns to firmware issues |

##### Modified Vertex Types

| Vertex Type | Change | Phase | Rationale |
|---|---|---|---|
| CoreRouter | Add property: `FirmwareVersion` (string) | 3 | Required for Advisory correlation — match running firmware to known bugs |

##### New Edge Types

| Edge Type | Source → Target | Phase | Count | Description |
|---|---|---|---|---|
| routed_through | TransportLink → PhysicalConduit | 2 | ~4 | Maps which fibre links share the same physical duct/trench |
| amplifies | AmplifierSite → TransportLink | 3 | ~8 | Maps which amplifiers service which fibre links |
| affects_version | Advisory → CoreRouter | 3 | ~4 | Links vendor advisories to routers running affected firmware |

##### New CSV Files Required

| File | Vertex/Edge | Phase | Estimated Rows |
|---|---|---|---|
| DimPhysicalConduit.csv | PhysicalConduit vertex | 2 | 2–3 |
| DimAmplifierSite.csv | AmplifierSite vertex | 3 | 3–4 |
| DimAdvisory.csv | Advisory vertex | 3 | 2–3 |
| FactConduitMapping.csv | routed_through edges | 2 | ~4 |
| FactAmplifierMapping.csv | amplifies edges | 3 | ~8 |
| FactAdvisoryMapping.csv | affects_version edges | 3 | ~4 |

#### Summary: Old vs New Totals

| Metric | Current | Phase 2 | Phase 3 (Final) | Net Change |
|---|---|---|---|---|
| Vertex types | 8 | 9 (+PhysicalConduit) | 11 (+AmplifierSite, +Advisory) | **+3 types** |
| Edge types | 7 | 8 (+routed_through) | 10 (+amplifies, +affects_version) | **+3 types** |
| Total vertices | ~50 | ~53 | ~60 | **+~10 vertices** |
| Total edges | ~69 | ~73 | ~85 | **+~16 edges** |
| CSV files (entities) | 10 | 12 | 16 | **+6 files** |
| Vertex properties | 30 | 34 | 43 | **+13 properties** |
| Modified vertex types | 0 | 0 | 1 (CoreRouter +FirmwareVersion) | **+1 property on existing type** |

### 12.2 New Data Points By Phase

#### Phase 1 — No Graph Changes

| Data Type | New Items | Description |
|---|---|---|
| Prompts | 2 new prompt files | `planned_maintenance.md`, `aggswitch_power_failure.md` |
| Telemetry (AlertStream) | ~200–500 new alert records | AggSwitch power-failure alerts, capacity congestion alerts |
| Telemetry (LinkTelemetry) | ~500–1,000 new readings | Gradual utilisation ramp for congestion scenario |
| **Graph changes** | **None** | Existing ontology fully supports these scenarios |

#### Phase 2 — PhysicalConduit Expansion

| Data Type | New Items | Description |
|---|---|---|
| Vertices | 2–3 PhysicalConduit | Conduit routes (e.g., CONDUIT-SYD-MEL-GOULBURN, CONDUIT-SYD-MEL-COASTAL) |
| Edges | ~4 routed_through | Maps existing TransportLinks to their physical conduits |
| CSV files | 2 new files | DimPhysicalConduit.csv, FactConduitMapping.csv |
| graph_schema.yaml | 2 new entries | 1 vertex definition + 1 edge definition |
| Prompts | 1 new prompt file | `conduit_correlation.md` |
| Runbooks | 1 new runbook | `conduit_shared_risk_assessment.md` |
| **Total new data points** | **~10** | |

#### Phase 3 — AmplifierSite + Advisory Expansion

| Data Type | New Items | Description |
|---|---|---|
| Vertices | 5–7 (AmplifierSite + Advisory) | Amplifier sites on long-haul routes + vendor advisories |
| Edges | ~12 (amplifies + affects_version) | Amplifier-to-link mappings + advisory-to-router correlations |
| CSV files | 4 new files | DimAmplifierSite.csv, DimAdvisory.csv, FactAmplifierMapping.csv, FactAdvisoryMapping.csv |
| graph_schema.yaml | 4 new entries | 2 vertex definitions + 2 edge definitions |
| Vertex property change | 1 property on CoreRouter | Add FirmwareVersion to DimCoreRouter.csv + graph_schema.yaml |
| Prompts | 2 new prompt files | `predictive_degradation.md`, `firmware_advisory_correlation.md` |
| Runbooks | 2 new runbooks | `amplifier_maintenance.md`, `firmware_upgrade_procedure.md` |
| Telemetry (LinkTelemetry) | ~2,000 new readings | Slow optical degradation time series over 2 weeks |
| AI Search documents | 2–3 advisory docs | Vendor advisory bulletins for AI Search index |
| **Total new data points** | **~30** | |

### 12.3 Impact on Existing Components

| Component | Impact | Backwards-Compatible? |
|---|---|---|
| **graph_schema.yaml** | Add 3 vertex definitions + 3 edge definitions. Add `FirmwareVersion` to CoreRouter properties list | ✅ Yes — additive only |
| **DimCoreRouter.csv** | Add `FirmwareVersion` column | ✅ Yes — CSV loader ignores extra columns if not in schema |
| **Graph ingest pipeline** | No code changes — data-driven from graph_schema.yaml | ✅ Yes |
| **Agent prompts (core_schema.md)** | Must be updated to include new vertex/edge types so agents know they exist | ⚠️ Required update |
| **Frontend graph styles (config.ts + scenario.yaml)** | Recommended: add default nodeColors/nodeSizes/nodeIcons for PhysicalConduit, AmplifierSite, Advisory. However, the frontend uses a 3-tier color resolution (`userOverride → scenarioNodeColors → autoColor(hash)`) and a **color wheel popover** lets users manually pick colors at runtime. New node types will automatically get a hash-based color even without config entries — so this is a polish step, not a blocker. | ✅ Optional — auto-fallback exists |
| **scenario.yaml** | No structural changes — new prompts referenced in agents section | ✅ Yes |
| **Telemetry tables** | No schema changes — same AlertStream/LinkTelemetry tables, new rows only | ✅ Yes |
| **AI Search indexes** | May need new index for advisories OR add to existing runbooks index | ⚠️ Decision needed |
| **Data generation** | No scripts needed — CSV files will be authored directly by hand (small dataset) | ✅ Manual CSV authoring |

---

## 13. Potential Change Locations — `telco-noc` Hardcoded References

This section enumerates every location in the active project where `telco-noc` is hardcoded. Compiled as groundwork for future scenario renaming, multi-scenario support, or scenario parameterisation.

> **Scope:** Only the active project tree (`projects/autonomous-network-demo/fabricdemo/`). Excludes `backup/`, `node_modules/`, `.git/`, and compiled `dist/` outputs. Documentation files are listed separately.

### 13.1 Backend — API Server (`api/`)

| File | Line(s) | Reference | Context |
|---|---|---|---|
| [api/app/routers/config.py](../api/app/routers/config.py#L24) | 24 | `telco-noc` | Comment: "Hardcoded scenario config for telco-noc" |
| [api/app/routers/config.py](../api/app/routers/config.py#L68) | 68 | `telco-noc-topology` | Label string: `"Fabric GQL (telco-noc-topology)"` |
| [api/app/routers/config.py](../api/app/routers/config.py#L99) | 99 | `telco-noc` | Dict value: `"graph": "telco-noc"` |
| [api/app/routers/config.py](../api/app/routers/config.py#L264) | 264 | `telco-noc` | Function call: `_build_resource_graph(SCENARIO_CONFIG, "telco-noc")` |

### 13.2 Backend — Graph Query API (`graph-query-api/`)

| File | Line(s) | Reference | Context |
|---|---|---|---|
| [graph-query-api/config.py](../graph-query-api/config.py#L7) | 7 | `telco-noc` | Docstring: "fixed hardcoded context for the telco-noc" |
| [graph-query-api/config.py](../graph-query-api/config.py#L56) | 56 | `telco-noc-topology` | Constant: `DEFAULT_GRAPH = "telco-noc-topology"` |
| [graph-query-api/config.py](../graph-query-api/config.py#L72) | 72 | `telco-noc` | Comment: "hardcoded for telco-noc" |
| [graph-query-api/config.py](../graph-query-api/config.py#L77) | 77 | `telco-noc` | Docstring: "Fixed routing context for the telco-noc demo" |
| [graph-query-api/router_health.py](../graph-query-api/router_health.py#L2) | 2, 4 | `telco-noc` | Module docstring references |
| [graph-query-api/router_health.py](../graph-query-api/router_health.py#L96) | 96 | `telco-noc` | Query parameter default: `Query(default="telco-noc")` |
| [graph-query-api/router_health.py](../graph-query-api/router_health.py#L104) | 104 | `telco-noc-topology` | Fallback: `graph_def.get("resource_name", "telco-noc-topology")` |
| [graph-query-api/search_indexer.py](../graph-query-api/search_indexer.py#L82) | 82–83 | `telco-noc-runbooks-index`, `telco-noc-runbooks` | Docstring examples |
| [graph-query-api/services/blob_uploader.py](../graph-query-api/services/blob_uploader.py#L31) | 31 | `telco-noc-runbooks` | Docstring example |

### 13.3 Frontend (`frontend/`)

| File | Line(s) | Reference | Context |
|---|---|---|---|
| [frontend/src/config.ts](../frontend/src/config.ts#L5) | 5 | `telco-noc` | Scenario name: `name: "telco-noc"` |
| [frontend/src/config.ts](../frontend/src/config.ts#L7) | 7 | `telco-noc-topology` | Graph name: `graph: "telco-noc-topology"` |

> **Note:** The compiled bundle `frontend/dist/assets/index-*.js` also contains these values but is a build artifact — changing `config.ts` and rebuilding will update it automatically.

### 13.4 Scripts (`scripts/`)

| File | Line(s) | Reference | Context |
|---|---|---|---|
| [scripts/provision_cosmos.py](../scripts/provision_cosmos.py#L6) | 6, 10 | `telco-noc` | Docstring/comments |
| [scripts/provision_cosmos.py](../scripts/provision_cosmos.py#L47) | 47 | `telco-noc` | Path: `DATA_DIR = ... / "scenarios" / "telco-noc" / "data" / "telemetry"` |
| [scripts/provision_search_index.py](../scripts/provision_search_index.py#L8) | 8 | `telco-noc` | Docstring: "For the telco-noc demo" |
| [scripts/provision_search_index.py](../scripts/provision_search_index.py#L70) | 70 | `telco-noc` | Path: `KNOWLEDGE_DIR = ... / "scenarios" / "telco-noc" / "data" / "knowledge"` |
| [scripts/generate_topology_json.py](../scripts/generate_topology_json.py#L10) | 10 | `telco-noc` | Usage string: `--scenario telco-noc` |
| [scripts/generate_topology_json.py](../scripts/generate_topology_json.py#L166) | 166 | `telco-noc` | Argparse default: `default="telco-noc"` |
| [scripts/provision_agents.py](../scripts/provision_agents.py#L31) | 31 | `telco-noc` | Env default: `os.environ.get("DEFAULT_SCENARIO", "telco-noc")` |
| [scripts/provision_agents.py](../scripts/provision_agents.py#L90) | 90 | `telco-noc` | Graph name default: `os.environ.get("DEFAULT_SCENARIO", "telco-noc")` |
| [scripts/fabric/provision_lakehouse.py](../scripts/fabric/provision_lakehouse.py#L42) | 42 | `telco-noc` | Env default: `os.environ.get("DEFAULT_SCENARIO", "telco-noc")` |
| [scripts/fabric/provision_eventhouse.py](../scripts/fabric/provision_eventhouse.py#L38) | 38 | `telco-noc` | Env default: `os.environ.get("DEFAULT_SCENARIO", "telco-noc")` |
| [scripts/agent_provisioner.py](../scripts/agent_provisioner.py#L146) | 146 | `telco-noc-topology` | Comment: prefix match example |
| [scripts/agent_provisioner.py](../scripts/agent_provisioner.py#L214) | 214 | `telco-noc-topology` | Docstring: graph_name example |

### 13.5 Hooks (`hooks/`)

| File | Line(s) | Reference | Context |
|---|---|---|---|
| [hooks/postprovision.sh](../hooks/postprovision.sh#L25) | 25 | `telco-noc` | Path: `DATA_DIR="$PROJECT_ROOT/data/scenarios/telco-noc/data/knowledge"` |

### 13.6 Scenario Data (`data/scenarios/telco-noc/`)

| File | Line(s) | Reference | Context |
|---|---|---|---|
| [data/scenarios/telco-noc/scenario.yaml](../data/scenarios/telco-noc/scenario.yaml#L5) | 5 | `telco-noc` | Scenario name: `name: telco-noc` |
| [data/scenarios/telco-noc/scenario.yaml](../data/scenarios/telco-noc/scenario.yaml#L55) | 55 | `telco-noc-topology` | Graph resource: `graph: "telco-noc-topology"` |
| [data/scenarios/telco-noc/scenario.yaml](../data/scenarios/telco-noc/scenario.yaml#L63) | 63 | `telco-noc` | Container prefix: `container_prefix: "telco-noc"` |
| [data/scenarios/telco-noc/scenario.yaml](../data/scenarios/telco-noc/scenario.yaml#L78) | 78 | `telco-noc-runbooks-index` | Search index: `index_name: "telco-noc-runbooks-index"` |
| [data/scenarios/telco-noc/scenario.yaml](../data/scenarios/telco-noc/scenario.yaml#L82) | 82 | `telco-noc-tickets-index` | Search index: `index_name: "telco-noc-tickets-index"` |
| [data/scenarios/telco-noc/graph_schema.yaml](../data/scenarios/telco-noc/graph_schema.yaml#L13) | 13 | `telco-noc` | Comment: backwards-compat symlink path |
| [data/scenarios/telco-noc/scripts/generate_all.sh](../data/scenarios/telco-noc/scripts/generate_all.sh#L2) | 2, 5 | `telco-noc` | Comments: "Generate all data for the telco-noc scenario" |

> **Note:** The directory itself is named `data/scenarios/telco-noc/` — renaming the scenario would require moving this entire directory.

### 13.7 Azure Deployment (`.azure/`)

| Path | Reference | Context |
|---|---|---|
| `.azure/graph-fabric-telco-c/` | `telco` | Active azd environment directory name |
| `.azure/graph-fabric-telco-a/` | `telco` | Previous/alternate azd environment directory name |

> These are azd environment names, not hardcoded in source. They are created by `azd env new` and can be changed independently without code edits.

### 13.8 Files With NO `telco-noc` References

The following key project files are **scenario-agnostic** and require no changes for a scenario rename:

- `azure.yaml` — no scenario name references
- `azure_config.env` / `azure_config.env.template` — no scenario name references
- `deploy.sh` — no scenario name references
- `Dockerfile` / `api/Dockerfile` — no scenario name references
- `pyproject.toml` — no scenario name references
- `nginx.conf` / `supervisord.conf` — no scenario name references
- `infra/` (all Bicep files) — no scenario name references
- `custom_skills/` — no scenario name references

### 13.9 Documentation Files (Reference Only)

These documentation files reference `telco-noc` extensively but are not functional code. They would need updating for consistency but would not break the application:

| File | Approximate Matches |
|---|---|
| [documentation/old_ways.md](../documentation/old_ways.md) | ~40+ references |
| [documentation/old_ways_setup.md](../documentation/old_ways_setup.md) | 3 references |
| [documentation/v12QOL.md](../documentation/v12QOL.md) | 1 reference |
| [documentation/V12newscenario.md](../documentation/V12newscenario.md) | Self-references (this document) |
| [documentation/architecture/overview.md](../documentation/architecture/overview.md) | 6 references |
| [documentation/architecture/data-flow.md](../documentation/architecture/data-flow.md) | 25+ references |
| [documentation/architecture/backlog-and-future.md](../documentation/architecture/backlog-and-future.md) | 3 references |
| [documentation/completed/v11e3.md](../documentation/completed/v11e3.md) | 80+ references |
| [documentation/completed/v11fabricv3_old2.md](../documentation/completed/v11fabricv3_old2.md) | 30+ references |
| [documentation/completed/v11fabricv3.md](../documentation/completed/v11fabricv3.md) | 5+ references |
| [documentation/completed/v11refactor.md](../documentation/completed/v11refactor.md) | 1 reference |
| [documentation/completed/v11d.md](../documentation/completed/v11d.md) | 1 reference |
| [documentation/completed/v11c.md](../documentation/completed/v11c.md) | 1 reference |
| [documentation/completed/v11e.md](../documentation/completed/v11e.md) | 3 references |
| [documentation/completed/v11f.md](../documentation/completed/v11f.md) | 5 references |
| [documentation/completed/NUKECOSMOS.md](../documentation/completed/NUKECOSMOS.md) | 1 reference |

### 13.10 Summary — Change Effort for Scenario Rename

| Layer | Files to Change | Effort |
|---|---|---|
| **Backend (api/)** | 1 file, 4 occurrences | Low — single config module |
| **Backend (graph-query-api/)** | 3 files, 11 occurrences | Low — config + health + docs |
| **Frontend** | 1 file, 2 occurrences (+ rebuild) | Low — single config file |
| **Scripts** | 6 files, 12 occurrences | Medium — spread across provisioners |
| **Hooks** | 1 file, 1 occurrence | Trivial |
| **Scenario data** | 3 files, 8 occurrences + directory rename | Medium — YAML config + dir rename |
| **Documentation** | 16+ files, 200+ occurrences | High effort but non-functional |
| **Total (code + config)** | **15 files, ~38 occurrences** | **< 1 hour for a find-and-replace** |

---

## 14. Implementation Plan

This section is a **step-by-step, idiot-proof implementation guide** for an agent or developer to follow. Each step specifies the exact file, the exact content to write or change, and a verification check.

> **Prerequisites:** The current deployed `telco-noc` scenario is working. All changes below are **additive** — nothing is deleted or renamed.

### Phase 1: Data & Schema Expansion

All data files live under `data/scenarios/telco-noc/data/entities/`. Phase 1 creates new CSV files, updates the graph schema, updates the agent prompt, and adds new example questions. Provisioning script changes are in Phase 2.

---

#### Step 1.1 — Add `FirmwareVersion` column to `DimCoreRouter.csv`

**File:** `data/scenarios/telco-noc/data/entities/DimCoreRouter.csv`

**Action:** Add a `FirmwareVersion` column to the header and every row.

**Current content:**
```csv
RouterId,City,Region,Vendor,Model
CORE-SYD-01,Sydney,NSW,Cisco,ASR-9922
CORE-MEL-01,Melbourne,VIC,Cisco,ASR-9922
CORE-BNE-01,Brisbane,QLD,Juniper,MX10008
```

**New content:**
```csv
RouterId,City,Region,Vendor,Model,FirmwareVersion
CORE-SYD-01,Sydney,NSW,Cisco,ASR-9922,IOS-XR-7.9.2
CORE-MEL-01,Melbourne,VIC,Cisco,ASR-9922,IOS-XR-7.9.2
CORE-BNE-01,Brisbane,QLD,Juniper,MX10008,JUNOS-23.4R1
```

**Verify:** `head -1 data/scenarios/telco-noc/data/entities/DimCoreRouter.csv` shows `RouterId,City,Region,Vendor,Model,FirmwareVersion`.

---

#### Step 1.2 — Create `DimPhysicalConduit.csv`

**File:** `data/scenarios/telco-noc/data/entities/DimPhysicalConduit.csv` (NEW)

**Action:** Create this file with the following exact content:

```csv
ConduitId,RouteDescription,MaterialType,InstalledYear
CONDUIT-SYD-MEL-INLAND,Sydney to Melbourne via Hume Highway / Goulburn — inland route through Southern Highlands,Underground Duct,2018
CONDUIT-SYD-MEL-COASTAL,Sydney to Melbourne via Princes Highway — coastal route through Wollongong and Bairnsdale,Underground Duct,2020
CONDUIT-SYD-BNE-PACIFIC,Sydney to Brisbane via Pacific Highway — coastal route through Newcastle and Coffs Harbour,Underground Duct,2019
```

**Rationale:**
- `CONDUIT-SYD-MEL-INLAND` — Both FIBRE-01 and FIBRE-02 share this conduit (the critical shared-risk scenario). This explains why INC-2025-11-22-0055 (storm damage) took out both fibres simultaneously.
- `CONDUIT-SYD-MEL-COASTAL` — An alternate coastal route (currently unused, could be future diversity).
- `CONDUIT-SYD-BNE-PACIFIC` — The SYD-BNE fibre route.

**Verify:** `wc -l` returns 4 (header + 3 data rows). `head -1` shows `ConduitId,RouteDescription,MaterialType,InstalledYear`.

---

#### Step 1.3 — Create `FactConduitMapping.csv`

**File:** `data/scenarios/telco-noc/data/entities/FactConduitMapping.csv` (NEW)

**Action:** Create this file with the following exact content:

```csv
LinkId,ConduitId,SegmentDescription
LINK-SYD-MEL-FIBRE-01,CONDUIT-SYD-MEL-INLAND,Primary SYD-MEL fibre routed through inland conduit via Goulburn
LINK-SYD-MEL-FIBRE-02,CONDUIT-SYD-MEL-INLAND,Backup SYD-MEL fibre routed through SAME inland conduit — shared risk
LINK-SYD-BNE-FIBRE-01,CONDUIT-SYD-BNE-PACIFIC,SYD-BNE fibre routed through Pacific Highway coastal conduit
LINK-MEL-BNE-FIBRE-01,CONDUIT-SYD-MEL-COASTAL,MEL-BNE fibre routed through coastal conduit (partial overlap)
```

**Critical detail:** FIBRE-01 and FIBRE-02 both map to `CONDUIT-SYD-MEL-INLAND`. This is the key insight — so-called "redundant" fibres share a physical conduit and are NOT truly diverse.

**Verify:** `wc -l` returns 5 (header + 4 data rows). Both FIBRE-01 and FIBRE-02 reference the same ConduitId.

---

#### Step 1.4 — Create `DimAmplifierSite.csv`

**File:** `data/scenarios/telco-noc/data/entities/DimAmplifierSite.csv` (NEW)

**Action:** Create this file with the following exact content:

```csv
SiteId,Location,InstalledYear,LastCalibration
AMP-SYD-MEL-GOULBURN,Goulburn NSW — 195km from Sydney,2018,2025-09-15
AMP-SYD-MEL-ALBURY,Albury NSW — 460km from Sydney,2018,2025-06-20
AMP-SYD-BNE-COFFS,Coffs Harbour NSW — 540km from Sydney,2019,2025-11-01
AMP-MEL-BNE-GRAFTON,Grafton NSW — 340km from Melbourne via coastal route,2020,2025-03-10
```

**Rationale:** Optical amplifiers are placed every ~80-200km on long-haul fibre. Each amplifier site is a potential degradation point. `LastCalibration` enables "aging amplifier" predictive scenarios.

**Verify:** `wc -l` returns 5 (header + 4 data rows).

---

#### Step 1.5 — Create `FactAmplifierMapping.csv`

**File:** `data/scenarios/telco-noc/data/entities/FactAmplifierMapping.csv` (NEW)

**Action:** Create this file with the following exact content:

```csv
SiteId,LinkId,HopOrder
AMP-SYD-MEL-GOULBURN,LINK-SYD-MEL-FIBRE-01,1
AMP-SYD-MEL-ALBURY,LINK-SYD-MEL-FIBRE-01,2
AMP-SYD-MEL-GOULBURN,LINK-SYD-MEL-FIBRE-02,1
AMP-SYD-MEL-ALBURY,LINK-SYD-MEL-FIBRE-02,2
AMP-SYD-BNE-COFFS,LINK-SYD-BNE-FIBRE-01,1
AMP-MEL-BNE-GRAFTON,LINK-MEL-BNE-FIBRE-01,1
```

**Rationale:** Both SYD-MEL fibres share the same amplifier sites (since they share the same conduit). The Goulburn amplifier site is co-located with the conduit risk zone.

**Verify:** `wc -l` returns 7 (header + 6 data rows).

---

#### Step 1.6 — Create `DimAdvisory.csv`

**File:** `data/scenarios/telco-noc/data/entities/DimAdvisory.csv` (NEW)

**Action:** Create this file with the following exact content:

```csv
AdvisoryId,VendorName,BugId,AffectedVersions,Severity,Title,Description
ADV-CISCO-2025-001,Cisco,CSCwi82345,IOS-XR-7.9.1|IOS-XR-7.9.2,HIGH,OSPF adjacency flap under high BGP churn,OSPF adjacency may drop when BGP table exceeds 500K prefixes during reconvergence. Affects ASR-9000 series running IOS-XR 7.9.x. Fixed in IOS-XR-7.10.1.
ADV-CISCO-2025-002,Cisco,CSCwi93456,IOS-XR-7.8.1|IOS-XR-7.9.1|IOS-XR-7.9.2,MEDIUM,BFD session timeout false positive on 100GE interfaces,BFD may report false link-down on 100GE interfaces under high utilisation (>90%). Affects ASR-9000 series. Workaround: increase BFD interval to 300ms.
ADV-JUNIPER-2025-001,Juniper,PR1789012,JUNOS-23.4R1|JUNOS-23.4R2,HIGH,MPLS LDP session reset during ECMP rebalancing,LDP sessions may reset when ECMP path count changes from 2 to 1 during link failure. Affects MX10000 series. Fixed in JUNOS-24.1R1.
```

**Rationale:** These advisories are chosen to correlate with the existing scenario:
- ADV-CISCO-2025-001 affects `IOS-XR-7.9.2` which runs on CORE-SYD-01 and CORE-MEL-01 — explains OSPF flaps seen during the fibre cut reconvergence.
- ADV-CISCO-2025-002 also affects `IOS-XR-7.9.2` (added to AffectedVersions) on CORE-SYD-01 and CORE-MEL-01 — explains potential BFD false positives during high link utilisation.
- ADV-JUNIPER-2025-001 affects `JUNOS-23.4R1` which runs on CORE-BNE-01 — explains potential issues on the tertiary SYD-MEL-VIA-BNE path.

**Verify:** `wc -l` returns 4 (header + 3 data rows). Column count matches: 7 columns per row.

---

#### Step 1.7 — Create `FactAdvisoryMapping.csv`

**File:** `data/scenarios/telco-noc/data/entities/FactAdvisoryMapping.csv` (NEW)

**Action:** Create this file with the following exact content:

```csv
AdvisoryId,RouterId,MatchReason
ADV-CISCO-2025-001,CORE-SYD-01,Router runs IOS-XR-7.9.2 which matches affected version IOS-XR-7.9.2
ADV-CISCO-2025-001,CORE-MEL-01,Router runs IOS-XR-7.9.2 which matches affected version IOS-XR-7.9.2
ADV-CISCO-2025-002,CORE-SYD-01,Router runs IOS-XR-7.9.2 which matches affected version IOS-XR-7.9.2
ADV-CISCO-2025-002,CORE-MEL-01,Router runs IOS-XR-7.9.2 which matches affected version IOS-XR-7.9.2
ADV-JUNIPER-2025-001,CORE-BNE-01,Router runs JUNOS-23.4R1 which matches affected version JUNOS-23.4R1
```

**Rationale:** Pre-computed advisory-to-router mappings. The agent can traverse `Advisory -[affects_version]-> CoreRouter` to find which routers are running vulnerable firmware.

**Verify:** `wc -l` returns 6 (header + 5 data rows).

---

#### Step 1.8 — Update `graph_schema.yaml`

**File:** `data/scenarios/telco-noc/graph_schema.yaml`

**Action:** Make three changes to this file:

**Change A — Add `FirmwareVersion` to the CoreRouter vertex properties list:**

Find this line in the `vertices` section:
```yaml
    properties: [RouterId, City, Region, Vendor, Model]
```

Replace with:
```yaml
    properties: [RouterId, City, Region, Vendor, Model, FirmwareVersion]
```

**Change B — Add three new vertex definitions at the END of the `vertices:` section** (after the BGPSession entry):

```yaml

  - label: PhysicalConduit
    csv_file: DimPhysicalConduit.csv
    id_column: ConduitId
    partition_key: conduit
    properties: [ConduitId, RouteDescription, MaterialType, InstalledYear]

  - label: AmplifierSite
    csv_file: DimAmplifierSite.csv
    id_column: SiteId
    partition_key: amplifier
    properties: [SiteId, Location, InstalledYear, LastCalibration]

  - label: Advisory
    csv_file: DimAdvisory.csv
    id_column: AdvisoryId
    partition_key: advisory
    properties: [AdvisoryId, VendorName, BugId, AffectedVersions, Severity, Title, Description]
```

**Change C — Add three new edge definitions at the END of the `edges:` section** (after the last BGPSession peers_over entry):

```yaml

  # TransportLink routed_through PhysicalConduit
  - label: routed_through
    csv_file: FactConduitMapping.csv
    source:
      label: TransportLink
      property: LinkId
      column: LinkId
    target:
      label: PhysicalConduit
      property: ConduitId
      column: ConduitId
    properties:
      - name: SegmentDescription
        column: SegmentDescription

  # AmplifierSite amplifies TransportLink
  - label: amplifies
    csv_file: FactAmplifierMapping.csv
    source:
      label: AmplifierSite
      property: SiteId
      column: SiteId
    target:
      label: TransportLink
      property: LinkId
      column: LinkId
    properties:
      - name: HopOrder
        column: HopOrder

  # Advisory affects_version CoreRouter
  - label: affects_version
    csv_file: FactAdvisoryMapping.csv
    source:
      label: Advisory
      property: AdvisoryId
      column: AdvisoryId
    target:
      label: CoreRouter
      property: RouterId
      column: RouterId
    properties:
      - name: MatchReason
        column: MatchReason
```

**Verify:** After editing, `grep -c 'label:' graph_schema.yaml` in the vertices section should show 11 vertex types and the edges section should show 10+ edge entries (some edges like `connects_to` and `depends_on` have multiple entries).

---

#### Step 1.9 — Update `core_schema.md` (Agent Prompt)

**File:** `data/scenarios/telco-noc/data/prompts/graph_explorer/core_schema.md`

**Action:** Append the following three new entity type sections **before the `## Relationships` section** (i.e., after the SLAPolicy section, before line ~200). Also append the three new relationship types to the Relationships section.

**Add these entity sections before `## Relationships`:**

````markdown
---

### PhysicalConduit (3 instances)

Physical duct/trench infrastructure that transport links are routed through. CRITICAL: Multiple fibre links can share the same conduit, creating hidden shared-risk scenarios where "redundant" fibres are NOT truly diverse.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **ConduitId** | String | **Primary key.** | `CONDUIT-SYD-MEL-INLAND` |
| RouteDescription | String | Human-readable route path description. | `Sydney to Melbourne via Hume Highway / Goulburn` |
| MaterialType | String | Physical infrastructure type. | `Underground Duct` |
| InstalledYear | Integer | Year the conduit was installed. | `2018` |

**All instances:**

| ConduitId | RouteDescription | InstalledYear |
|---|---|---|
| CONDUIT-SYD-MEL-INLAND | Sydney to Melbourne via Hume Highway / Goulburn — inland route | 2018 |
| CONDUIT-SYD-MEL-COASTAL | Sydney to Melbourne via Princes Highway — coastal route | 2020 |
| CONDUIT-SYD-BNE-PACIFIC | Sydney to Brisbane via Pacific Highway — coastal route | 2019 |

**KEY INSIGHT:** LINK-SYD-MEL-FIBRE-01 and LINK-SYD-MEL-FIBRE-02 BOTH route through CONDUIT-SYD-MEL-INLAND. They are NOT physically diverse. A single conduit event (storm, excavation) can take out both "redundant" fibres simultaneously.

---

### AmplifierSite (4 instances)

Optical amplifier sites along long-haul fibre routes. Amplifiers boost optical signal every 80-200km. Aging or miscalibrated amplifiers cause gradual optical power degradation — a predictive maintenance opportunity.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SiteId** | String | **Primary key.** | `AMP-SYD-MEL-GOULBURN` |
| Location | String | Physical location description. | `Goulburn NSW — 195km from Sydney` |
| InstalledYear | Integer | Year the amplifier was installed. | `2018` |
| LastCalibration | Date | Date of last calibration. | `2025-09-15` |

**All instances:**

| SiteId | Location | InstalledYear | LastCalibration |
|---|---|---|---|
| AMP-SYD-MEL-GOULBURN | Goulburn NSW — 195km from Sydney | 2018 | 2025-09-15 |
| AMP-SYD-MEL-ALBURY | Albury NSW — 460km from Sydney | 2018 | 2025-06-20 |
| AMP-SYD-BNE-COFFS | Coffs Harbour NSW — 540km from Sydney | 2019 | 2025-11-01 |
| AMP-MEL-BNE-GRAFTON | Grafton NSW — 340km from Melbourne | 2020 | 2025-03-10 |

---

### Advisory (3 instances)

Vendor security/bug advisories that affect specific firmware versions running on network equipment. Used to correlate observed telemetry anomalies with known software defects.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **AdvisoryId** | String | **Primary key.** | `ADV-CISCO-2025-001` |
| VendorName | String | Equipment vendor. | `Cisco` |
| BugId | String | Vendor's bug tracking ID. | `CSCwi82345` |
| AffectedVersions | String | Pipe-separated list of affected firmware versions. | `IOS-XR-7.9.1\|IOS-XR-7.9.2` |
| Severity | String | Advisory severity. Values: `HIGH`, `MEDIUM`, `LOW`. | `HIGH` |
| Title | String | Short title of the advisory. | `OSPF adjacency flap under high BGP churn` |
| Description | String | Detailed description including fix version. | (see data) |

**All instances:**

| AdvisoryId | VendorName | Severity | Title | Affected Routers |
|---|---|---|---|---|
| ADV-CISCO-2025-001 | Cisco | HIGH | OSPF adjacency flap under high BGP churn | CORE-SYD-01, CORE-MEL-01 (both run IOS-XR-7.9.2) |
| ADV-CISCO-2025-002 | Cisco | MEDIUM | BFD session timeout false positive on 100GE | CORE-SYD-01, CORE-MEL-01 |
| ADV-JUNIPER-2025-001 | Juniper | HIGH | MPLS LDP session reset during ECMP rebalancing | CORE-BNE-01 (runs JUNOS-23.4R1) |

<!-- Note: "Affected Routers" in the table above is derived from FactAdvisoryMapping joins, not a column in DimAdvisory.csv -->
````

**Add these relationship descriptions to the `## Relationships` section at the bottom:**

````markdown

### routed_through: TransportLink → PhysicalConduit

A transport link is physically routed through a conduit/duct. MULTIPLE transport links can share the SAME conduit — this is how you detect shared-risk groups. Query pattern: "Which other links share the same conduit as LINK-X?" → Find LINK-X's conduit, then find all other links routed_through that conduit.

### amplifies: AmplifierSite → TransportLink

An optical amplifier site boosts the signal on a transport link. Long-haul links have multiple amplifier sites. If an amplifier degrades, optical power drops on that link segment. Query pattern: "Which amplifiers service LINK-SYD-MEL-FIBRE-01?" and "When was each last calibrated?"

### affects_version: Advisory → CoreRouter

A vendor advisory affects a router running a vulnerable firmware version. Pre-mapped from Advisory.AffectedVersions matching CoreRouter.FirmwareVersion. Query pattern: "Are any of our routers running firmware affected by known advisories?" and "Could the OSPF flaps on CORE-SYD-01 be caused by a known bug?"
````

**Verify:** The `## Relationships` section now has 10 relationship descriptions (7 original + 3 new). Search for `### routed_through`, `### amplifies`, `### affects_version` to confirm.

---

#### Step 1.10 — Update `scenario.yaml` graph_styles

**File:** `data/scenarios/telco-noc/scenario.yaml`

**Action:** Add three new entries to the `graph_styles.node_types` section, after the existing BGPSession entry:

```yaml
    PhysicalConduit: { color: "#F59E0B", size: 20, icon: "conduit" }
    AmplifierSite:   { color: "#10B981", size: 16, icon: "amplifier" }
    Advisory:        { color: "#EF4444", size: 18, icon: "advisory" }
```

> **Note:** These are default colors. Users can override them at runtime via the color wheel popover in the frontend. The color resolution chain is: `userOverride → scenarioNodeColors → autoColor(hash)`. Even if this step is skipped, new node types will get an auto-generated color.

**Verify:** `grep -c 'color:' data/scenarios/telco-noc/scenario.yaml` returns 11 (8 original + 3 new).

---

#### Step 1.11 — Update `frontend/src/config.ts` graph styles

**File:** `frontend/src/config.ts`

**Action:** Add three entries to each of the `nodeColors`, `nodeSizes`, and `nodeIcons` objects inside `graphStyles`.

**In `nodeColors` (after `BGPSession: "#F472B6"`):**
```typescript
      PhysicalConduit: "#F59E0B",
      AmplifierSite: "#10B981",
      Advisory: "#EF4444",
```

**In `nodeSizes` (after `BGPSession: 14`):**
```typescript
      PhysicalConduit: 20,
      AmplifierSite: 16,
      Advisory: 18,
```

**In `nodeIcons` (after `BGPSession: "session"`):**
```typescript
      PhysicalConduit: "conduit",
      AmplifierSite: "amplifier",
      Advisory: "advisory",
```

> **Note:** This step is **optional polish**. The `useNodeColor` hook in `frontend/src/hooks/useNodeColor.ts` already falls back to `autoColor(hash)` for unknown labels. The color wheel popover lets users pick colors at runtime. These defaults just ensure the INITIAL render looks intentional rather than hash-random.

**Verify:** After editing, rebuild the frontend (`cd frontend && npm run build`) and confirm the three new entries appear.

---

#### Step 1.12 — Update `exampleQuestions`

**Files:**
- `data/scenarios/telco-noc/scenario.yaml` (authoritative — loaded at runtime)
- `frontend/src/config.ts` (fallback defaults for dev/mock mode)

**Action:** Add 3 new example questions so users can discover the new entity types from the chat sidebar.

**In `scenario.yaml`, append to the `example_questions:` list:**

```yaml
  - "Do our 'redundant' SYD-MEL fibres share a physical conduit?"
  - "Which amplifiers service the SYD-MEL fibre and when were they last calibrated?"
  - "Are any routers running firmware affected by known vendor advisories?"
```

**In `frontend/src/config.ts`, append to the `exampleQuestions` array:**

```typescript
    "Do our 'redundant' SYD-MEL fibres share a physical conduit?",
    "Which amplifiers service the SYD-MEL fibre and when were they last calibrated?",
    "Are any routers running firmware affected by known vendor advisories?",
```

**Verify:** `grep -c '^\s*-' data/scenarios/telco-noc/scenario.yaml` in the `example_questions:` block shows **9** entries (6 original + 3 new). `exampleQuestions` in `config.ts` has **9** entries.

---

#### Step 1.13 — Verification Checklist (Phase 1)

Run these checks before proceeding to Phase 2:

| # | Check | Command / Action | Expected |
|---|---|---|---|
| 1 | CSV file count | `ls data/scenarios/telco-noc/data/entities/*.csv \| wc -l` | **16** (was 10) |
| 2 | DimCoreRouter has FirmwareVersion | `head -1 data/scenarios/telco-noc/data/entities/DimCoreRouter.csv` | Header includes `FirmwareVersion` |
| 3 | FIBRE-01 and FIBRE-02 share conduit | `grep CONDUIT-SYD-MEL-INLAND data/scenarios/telco-noc/data/entities/FactConduitMapping.csv \| wc -l` | **2** (both fibres) |
| 4 | Advisory affects correct routers | `grep CORE-SYD-01 data/scenarios/telco-noc/data/entities/FactAdvisoryMapping.csv \| wc -l` | **2** (two advisories affect SYD-01) |
| 5 | graph_schema.yaml vertex count | `awk '/^vertices:/,/^edges:/{if (/^  - label:/) c++} END{print c}' data/scenarios/telco-noc/graph_schema.yaml` | **11** |
| 6 | core_schema.md has new types | `grep -c '### PhysicalConduit\|### AmplifierSite\|### Advisory' data/scenarios/telco-noc/data/prompts/graph_explorer/core_schema.md` | **3** |
| 7 | core_schema.md has new rels | `grep -c 'routed_through\|amplifies\|affects_version' data/scenarios/telco-noc/data/prompts/graph_explorer/core_schema.md` | **3+** |
| 8 | scenario.yaml has 11 node styles | `grep -c 'color:' data/scenarios/telco-noc/scenario.yaml` | **11** |
| 9 | config.ts nodeColors count | `grep -A15 'nodeColors' frontend/src/config.ts \| grep -c ':'` | **11** |
| 10 | exampleQuestions count | `grep -c '^\s*-' data/scenarios/telco-noc/scenario.yaml` under `example_questions:` | **9** |

---

### Phase 2: Code Changes, Provisioning Scripts & Deploy

Phase 2 covers the changes needed to make the new data actually work in the deployed system:

1. **Provisioning script updates** — `provision_lakehouse.py` and `provision_ontology.py` are hardcoded and must be updated for new entity/relationship types
2. **Knowledge documents** for AI Search (new runbooks auto-discovered by the indexer)
3. **Demo scenario prompts** for new investigative flows
4. **Frontend rebuild** (if Step 1.11 was done)
5. **Deployment** with correct pipeline sequence

> **Important:** The topology generator (`generate_topology_json.py`) is fully generic and reads `graph_schema.yaml` declaratively — it needs no code changes. `deploy.sh` Step 2b auto-runs it. However, the **Fabric provisioning scripts** (`provision_lakehouse.py` and `provision_ontology.py`) are entirely hardcoded and must be manually updated to register new entity types, properties, relationships, data bindings, and contextualizations.

---

#### Step 2.1 — Update `provision_lakehouse.py` LAKEHOUSE_TABLES

**File:** `scripts/fabric/provision_lakehouse.py`

**Action:** Add 6 new entries to the `LAKEHOUSE_TABLES` list (line 46). This list controls which CSV files are uploaded to OneLake and created as managed delta Lakehouse tables.

**Current content:**

```python
LAKEHOUSE_TABLES = [
    "DimCoreRouter", "DimTransportLink", "DimAggSwitch", "DimBaseStation",
    "DimBGPSession", "DimMPLSPath", "DimService", "DimSLAPolicy",
    "FactMPLSPathHops", "FactServiceDependency",
]
```

**New content:**

```python
LAKEHOUSE_TABLES = [
    "DimCoreRouter", "DimTransportLink", "DimAggSwitch", "DimBaseStation",
    "DimBGPSession", "DimMPLSPath", "DimService", "DimSLAPolicy",
    "FactMPLSPathHops", "FactServiceDependency",
    # V12 — New entity types + junction tables
    "DimPhysicalConduit", "DimAmplifierSite", "DimAdvisory",
    "FactConduitMapping", "FactAmplifierMapping", "FactAdvisoryMapping",
]
```

**Why this matters:** Without this change, the 6 new CSV files will sit in the `entities/` directory but never be uploaded to OneLake or created as Lakehouse tables. The graph will have no data for the new types.

**Verify:** `grep -c '"Dim\|"Fact' scripts/fabric/provision_lakehouse.py` returns **16** (was 10).

---

#### Step 2.2 — Update `provision_ontology.py`

**File:** `scripts/fabric/provision_ontology.py`

This is the most labor-intensive code change (~150-200 lines of additions). The file defines the entire Fabric IQ Ontology in hardcoded Python constants. You must add new IDs, entity type definitions, relationship type definitions, data bindings, and contextualizations following the existing patterns exactly.

**Change A — Add entity type ID constants** (after `ET_SLA_POLICY = 1000000000008`, ~line 117):

```python
# V12 — New entity types
ET_PHYSICAL_CONDUIT = 1000000000009
ET_AMPLIFIER_SITE = 1000000000010
ET_ADVISORY = 1000000000011
```

**Change B — Add FirmwareVersion property ID for CoreRouter** (after `P_ROUTER_MODEL = 2000000000006`, ~line 125):

```python
P_ROUTER_FIRMWARE = 2000000000007
```

**Change C — Add property ID constants for new entity types** (after `P_SLA_TIER = 2000000000086`, ~line 175):

```python
# Property IDs — PhysicalConduit (V12)
P_CONDUIT_ID = 2000000000091
P_CONDUIT_ROUTE_DESC = 2000000000092
P_CONDUIT_MATERIAL = 2000000000093
P_CONDUIT_INSTALLED_YEAR = 2000000000094

# Property IDs — AmplifierSite (V12)
P_AMP_SITE_ID = 2000000000101
P_AMP_LOCATION = 2000000000102
P_AMP_INSTALLED_YEAR = 2000000000103
P_AMP_LAST_CALIBRATION = 2000000000104

# Property IDs — Advisory (V12)
P_ADVISORY_ID = 2000000000111
P_ADVISORY_VENDOR = 2000000000112
P_ADVISORY_BUG_ID = 2000000000113
P_ADVISORY_AFFECTED_VERSIONS = 2000000000114
P_ADVISORY_SEVERITY = 2000000000115
P_ADVISORY_TITLE = 2000000000116
P_ADVISORY_DESCRIPTION = 2000000000117
```

> **ID allocation convention:** Entity type IDs use the `1000000000xxx` range. Property IDs use `2000000000xxx` with gaps between entity types (CoreRouter 001-006, TransportLink 011-022, AggSwitch 031-034, BaseStation 041-045, BGPSession 051-055, MPLSPath 061-063, Service 071-076, SLAPolicy 081-086, now PhysicalConduit 091-094, AmplifierSite 101-104, Advisory 111-117). Relationship type IDs use `3000000000xxx`.

**Change D — Add relationship type ID constants** (after `R_PEERS_OVER = 3000000000007`, ~line 183):

```python
# V12 — New relationships
R_ROUTED_THROUGH = 3000000000008
R_AMPLIFIES = 3000000000009
R_AFFECTS_VERSION = 3000000000010
```

**Change E — Add `FirmwareVersion` property to CoreRouter entity type definition** (in the CoreRouter entry of `ENTITY_TYPES`, after `prop(P_ROUTER_MODEL, "Model"),`):

```python
            prop(P_ROUTER_FIRMWARE, "FirmwareVersion"),
```

**Change F — Add 3 new entity type definitions** (append to `ENTITY_TYPES` list, before the closing `]`):

```python
    # V12 — New entity types
    {
        "id": str(ET_PHYSICAL_CONDUIT),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "PhysicalConduit",
        "entityIdParts": [str(P_CONDUIT_ID)],
        "displayNamePropertyId": str(P_CONDUIT_ID),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_CONDUIT_ID, "ConduitId"),
            prop(P_CONDUIT_ROUTE_DESC, "RouteDescription"),
            prop(P_CONDUIT_MATERIAL, "MaterialType"),
            prop(P_CONDUIT_INSTALLED_YEAR, "InstalledYear", "BigInt"),
        ],
        "timeseriesProperties": [],
    },
    {
        "id": str(ET_AMPLIFIER_SITE),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "AmplifierSite",
        "entityIdParts": [str(P_AMP_SITE_ID)],
        "displayNamePropertyId": str(P_AMP_SITE_ID),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_AMP_SITE_ID, "SiteId"),
            prop(P_AMP_LOCATION, "Location"),
            prop(P_AMP_INSTALLED_YEAR, "InstalledYear", "BigInt"),
            prop(P_AMP_LAST_CALIBRATION, "LastCalibration"),
        ],
        "timeseriesProperties": [],
    },
    {
        "id": str(ET_ADVISORY),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "Advisory",
        "entityIdParts": [str(P_ADVISORY_ID)],
        "displayNamePropertyId": str(P_ADVISORY_ID),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_ADVISORY_ID, "AdvisoryId"),
            prop(P_ADVISORY_VENDOR, "VendorName"),
            prop(P_ADVISORY_BUG_ID, "BugId"),
            prop(P_ADVISORY_AFFECTED_VERSIONS, "AffectedVersions"),
            prop(P_ADVISORY_SEVERITY, "Severity"),
            prop(P_ADVISORY_TITLE, "Title"),
            prop(P_ADVISORY_DESCRIPTION, "Description"),
        ],
        "timeseriesProperties": [],
    },
```

**Change G — Add 3 new relationship type definitions** (append to `RELATIONSHIP_TYPES` list, before the closing `]`):

```python
    # V12 — New relationships
    {
        "id": str(R_ROUTED_THROUGH),
        "namespace": "usertypes",
        "name": "routed_through",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_TRANSPORT_LINK)},
        "target": {"entityTypeId": str(ET_PHYSICAL_CONDUIT)},
    },
    {
        "id": str(R_AMPLIFIES),
        "namespace": "usertypes",
        "name": "amplifies",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_AMPLIFIER_SITE)},
        "target": {"entityTypeId": str(ET_TRANSPORT_LINK)},
    },
    {
        "id": str(R_AFFECTS_VERSION),
        "namespace": "usertypes",
        "name": "affects_version",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_ADVISORY)},
        "target": {"entityTypeId": str(ET_CORE_ROUTER)},
    },
```

**Change H — Add `FirmwareVersion` to CoreRouter static binding** (in `build_static_bindings()`, add to the CoreRouter binding list, after `("Model", P_ROUTER_MODEL),`):

```python
                ("FirmwareVersion", P_ROUTER_FIRMWARE),
```

**Change I — Add 3 new entity type bindings** (append to the `build_static_bindings()` return dict, before the closing `}`):

```python
        # V12 — New entity types
        ET_PHYSICAL_CONDUIT: [
            lakehouse_binding("PhysicalConduit-static", "DimPhysicalConduit", [
                ("ConduitId", P_CONDUIT_ID),
                ("RouteDescription", P_CONDUIT_ROUTE_DESC),
                ("MaterialType", P_CONDUIT_MATERIAL),
                ("InstalledYear", P_CONDUIT_INSTALLED_YEAR),
            ]),
        ],
        ET_AMPLIFIER_SITE: [
            lakehouse_binding("AmplifierSite-static", "DimAmplifierSite", [
                ("SiteId", P_AMP_SITE_ID),
                ("Location", P_AMP_LOCATION),
                ("InstalledYear", P_AMP_INSTALLED_YEAR),
                ("LastCalibration", P_AMP_LAST_CALIBRATION),
            ]),
        ],
        ET_ADVISORY: [
            lakehouse_binding("Advisory-static", "DimAdvisory", [
                ("AdvisoryId", P_ADVISORY_ID),
                ("VendorName", P_ADVISORY_VENDOR),
                ("BugId", P_ADVISORY_BUG_ID),
                ("AffectedVersions", P_ADVISORY_AFFECTED_VERSIONS),
                ("Severity", P_ADVISORY_SEVERITY),
                ("Title", P_ADVISORY_TITLE),
                ("Description", P_ADVISORY_DESCRIPTION),
            ]),
        ],
```

**Change J — Add 3 new contextualizations** (append to the `build_contextualizations()` return dict, before the closing `}`):

```python
        # V12 — New relationships
        # routed_through: TransportLink → PhysicalConduit (via FactConduitMapping)
        R_ROUTED_THROUGH: [
            ctx("routed_through", "FactConduitMapping",
                [("LinkId", P_LINK_ID)],
                [("ConduitId", P_CONDUIT_ID)]),
        ],
        # amplifies: AmplifierSite → TransportLink (via FactAmplifierMapping)
        R_AMPLIFIES: [
            ctx("amplifies", "FactAmplifierMapping",
                [("SiteId", P_AMP_SITE_ID)],
                [("LinkId", P_LINK_ID)]),
        ],
        # affects_version: Advisory → CoreRouter (via FactAdvisoryMapping)
        R_AFFECTS_VERSION: [
            ctx("affects_version", "FactAdvisoryMapping",
                [("AdvisoryId", P_ADVISORY_ID)],
                [("RouterId", P_ROUTER_ID)]),
        ],
```

**Summary of changes to `provision_ontology.py`:**

| What | Lines Added | Where |
|---|---|---|
| 3 entity type IDs | 4 | After `ET_SLA_POLICY` |
| 1 property ID (FirmwareVersion) | 1 | After `P_ROUTER_MODEL` |
| 15 property IDs (3 new entity types) | 19 | After `P_SLA_TIER` |
| 3 relationship type IDs | 4 | After `R_PEERS_OVER` |
| 1 property to CoreRouter | 1 | In CoreRouter `properties` |
| 3 entity type definitions | 55 | End of `ENTITY_TYPES` |
| 3 relationship type definitions | 22 | End of `RELATIONSHIP_TYPES` |
| 1 binding to CoreRouter | 1 | In CoreRouter binding |
| 3 entity type bindings | 25 | End of `build_static_bindings()` |
| 3 contextualizations | 17 | End of `build_contextualizations()` |
| **Total** | **~150** | |

**Verify:** After editing, run `python -c "import scripts.fabric.provision_ontology"` to confirm no syntax errors. Count entity types: `grep -c 'ET_.*=' scripts/fabric/provision_ontology.py` → **11**. Count relationship types: `grep -c 'R_.*=' scripts/fabric/provision_ontology.py` → **10**.

---

#### Step 2.3 — Create advisory knowledge documents for AI Search

**Directory:** `data/scenarios/telco-noc/data/knowledge/runbooks/`

**Action:** Create these new runbook/advisory documents:

**File:** `data/scenarios/telco-noc/data/knowledge/runbooks/conduit_shared_risk_assessment.md` (NEW)

```markdown
# Conduit Shared Risk Group Assessment

## Purpose
Assess whether multiple transport links share a common physical conduit, creating a shared-risk group (SRG) where a single physical event can take out multiple "redundant" links simultaneously.

## When to Use
- After a dual-link failure on the same corridor
- During planned maintenance risk assessment on any transport link
- When reviewing route diversity for SLA-governed services

## Procedure
1. **Identify the failed/target link** (e.g., LINK-SYD-MEL-FIBRE-01)
2. **Query the conduit mapping:** Find which PhysicalConduit the link routes through
3. **Find co-routed links:** Query all other TransportLinks that route through the SAME conduit
4. **Assess impact:** If the "backup" link shares the same conduit, redundancy is illusory
5. **Check historical incidents:** Look for past dual-fibre failures on this conduit (e.g., INC-2025-11-22-0055)

## Escalation
- If both primary and backup links share a conduit: escalate to network planning for route diversity review
- Recommend installing alternate fibres through a physically separate conduit

## Known Shared-Risk Groups
- **CONDUIT-SYD-MEL-INLAND:** LINK-SYD-MEL-FIBRE-01 + LINK-SYD-MEL-FIBRE-02 — both routed through Goulburn. NOT physically diverse.
```

**File:** `data/scenarios/telco-noc/data/knowledge/runbooks/amplifier_maintenance.md` (NEW)

```markdown
# Optical Amplifier Maintenance and Degradation Response

## Purpose
Guide assessment and response when optical amplifier degradation is detected or suspected on long-haul fibre links.

## Symptoms
- Gradual optical power drop on a transport link (e.g., from -3 dBm to -15 dBm over days/weeks)
- Increasing bit error rate (BER) without sudden loss-of-light
- Latency increase on long-haul links

## Procedure
1. **Identify the affected link** and query its amplifier sites (AmplifierSite → amplifies → TransportLink)
2. **Check last calibration dates** for each amplifier on the link
3. **Correlate with telemetry:** Is the optical power degradation gradual (amplifier aging) or sudden (fibre event)?
4. **If gradual:** Schedule field maintenance for recalibration. Priority based on link criticality.
5. **If sudden:** This is NOT an amplifier issue — investigate fibre cut or splice degradation.

## Calibration Schedule
- Amplifiers should be recalibrated every 6 months
- If LastCalibration > 6 months ago AND optical power is dropping: HIGH priority recalibration
- If LastCalibration > 12 months ago: CRITICAL — schedule immediately regardless of current readings

## Escalation
- If multiple amplifiers on the same route show degradation: possible environmental issue (temperature, water ingress in conduit)
- If degradation rate suggests failure within 7 days: pre-emptive traffic reroute + emergency field dispatch
```

**File:** `data/scenarios/telco-noc/data/knowledge/runbooks/firmware_upgrade_procedure.md` (NEW)

```markdown
# Firmware Upgrade Procedure — Vendor Advisory Response

## Purpose
Guide the firmware upgrade process when a vendor advisory identifies a bug affecting routers in the network.

## When to Use
- When a vendor advisory (Advisory entity) matches a router's current FirmwareVersion
- When observed telemetry anomalies correlate with a known bug pattern
- During scheduled maintenance windows for preventive upgrades

## Procedure
1. **Identify affected routers:** Query Advisory -[affects_version]-> CoreRouter to find all routers running vulnerable firmware
2. **Assess operational impact:** What services depend on paths through these routers? What SLAs are at risk during upgrade?
3. **Schedule upgrade window:**
   - GOLD SLA services: upgrade during pre-approved maintenance window with traffic pre-routed to backup paths
   - SILVER/STANDARD: upgrade during low-traffic period (02:00-06:00 local)
4. **Pre-upgrade checks:**
   - Verify backup path availability and utilisation headroom
   - Confirm rollback firmware image is staged
   - Notify affected customers per SLA notification requirements
5. **Execute upgrade:** Follow vendor-specific upgrade guide (Cisco IOS-XR or Juniper JUNOS)
6. **Post-upgrade verification:**
   - Confirm BGP sessions re-establish
   - Confirm OSPF adjacencies are stable
   - Monitor for 30 minutes for any anomalies

## Known Advisories
- **ADV-CISCO-2025-001 (HIGH):** OSPF flap under BGP churn — upgrade to IOS-XR-7.10.1. Affects CORE-SYD-01, CORE-MEL-01.
- **ADV-CISCO-2025-002 (MEDIUM):** BFD false positive — workaround available (increase BFD interval). Upgrade to IOS-XR-7.10.1.
- **ADV-JUNIPER-2025-001 (HIGH):** LDP reset during ECMP rebalance — upgrade to JUNOS-24.1R1. Affects CORE-BNE-01.
```

**Verify:** `ls data/scenarios/telco-noc/data/knowledge/runbooks/*.md | wc -l` returns **8** (was 5, +3 new).

---

#### Step 2.4 — Create demo scenario prompt files

**Directory:** `data/scenarios/telco-noc/data/prompts/demo_scenarios/` (subdirectory to distinguish from agent system prompts)

**Action:** Create prompt files for the new demo scenarios. These are **NOT** loaded by `provision_agents.py` — they are **demo starters** meant to be copy-pasted into the chat sidebar to launch a specific investigative flow. The agent system prompts (e.g., `foundry_orchestrator_agent.md`) remain in the parent `prompts/` directory.

> **Note:** `provision_agents.py` loads only the 5 named agent prompt files. These demo scenario files are reference material for the operator — paste them into the chat to kick off a guided investigation.

**File:** `data/scenarios/telco-noc/data/prompts/demo_scenarios/planned_maintenance.md` (NEW)

```markdown
# Planned Maintenance Risk Assessment

You are the NOC AI Orchestrator. A maintenance window has been scheduled:

**Target:** LINK-SYD-MEL-FIBRE-01 (fibre splice work)
**Window:** Saturday 02:00–08:00 UTC
**Requestor:** Network Engineering team

Your task:
1. Map ALL services, customers, and SLA policies that depend on this link (or on MPLS paths that traverse it)
2. Verify that backup paths have sufficient capacity to absorb rerouted traffic during the maintenance window
3. Check for any conflicting maintenance events or known risks on backup paths
4. Review historical incidents on this corridor — has anything gone wrong during previous maintenance?
5. Identify any shared physical infrastructure risks (conduit co-routing) that could compound the exposure
6. Produce a risk assessment with: affected services, SLA exposure, backup path readiness, and recommended safeguards
```

**File:** `data/scenarios/telco-noc/data/prompts/demo_scenarios/conduit_correlation.md` (NEW)

```markdown
# Dual-Fibre Failure — Conduit Shared Risk Investigation

You are the NOC AI Orchestrator. An unusual situation has occurred:

**Incident:** BOTH LINK-SYD-MEL-FIBRE-01 and LINK-SYD-MEL-FIBRE-02 have gone down simultaneously.
**This should not happen** — these are supposed to be redundant/diverse paths.

Your task:
1. Confirm both links are truly down (check telemetry: optical power, BER, utilisation)
2. **Investigate WHY both failed:** Do these links share a physical conduit? Query the PhysicalConduit mapping.
3. If they share a conduit: explain the shared-risk group to the operator. This was NOT true redundancy.
4. Assess the blast radius: what services are affected now that BOTH primary AND secondary paths are down?
5. Find the tertiary path (SYD-MEL-VIA-BNE) — is it available? What is its current utilisation and latency?
6. Look for historical precedent — has this dual-failure happened before? Reference INC-2025-11-22-0055.
7. Recommend: immediate reroute to tertiary + long-term recommendation for conduit route diversity.
```

**File:** `data/scenarios/telco-noc/data/prompts/demo_scenarios/predictive_degradation.md` (NEW)

```markdown
# Predictive Degradation — Optical Amplifier Aging

You are the NOC AI Orchestrator. A gradual anomaly has been detected:

**Observation:** Optical power on LINK-MEL-BNE-FIBRE-01 has been slowly dropping over the past 2 weeks:
- 14 days ago: -3 dBm (normal)
- 7 days ago: -8 dBm (still within spec)
- 3 days ago: -15 dBm (degraded)
- Today: -20 dBm (approaching critical threshold at -30 dBm)

This is NOT a sudden fibre cut — it's a gradual degradation pattern consistent with amplifier aging.

Your task:
1. Confirm the degradation trend in LinkTelemetry data for this link
2. Identify which AmplifierSites service this link — query the amplifies relationship
3. Check LastCalibration dates for these amplifiers — are any overdue?
4. Calculate the degradation rate and predict when the link will hit the critical threshold (-30 dBm)
5. Assess the impact if this link fails: what services depend on it? What paths route through it?
6. Look up the amplifier maintenance runbook for the recommended procedure
7. Recommend: proactive maintenance before failure occurs, with priority based on predicted time-to-failure
```

**File:** `data/scenarios/telco-noc/data/prompts/demo_scenarios/firmware_advisory_correlation.md` (NEW)

```markdown
# Firmware Advisory Correlation — OSPF Flap Investigation

You are the NOC AI Orchestrator. A NOC operator has noticed a pattern:

**Observation:** CORE-SYD-01 and CORE-MEL-01 have been experiencing intermittent OSPF adjacency flaps during peak BGP reconvergence events. The flaps are not associated with any physical link failures — all transport links show healthy optical power and BER.

The operator suspects a software bug. Your task:
1. Check what firmware versions CORE-SYD-01 and CORE-MEL-01 are running (FirmwareVersion property)
2. Query the Advisory entities — are there any known vendor advisories affecting this firmware version?
3. If an advisory matches: explain the bug, its severity, and the recommended fix version
4. Assess the operational risk: which services and SLA policies are exposed through these routers?
5. Check if CORE-BNE-01 (the third backbone router) is also affected by any advisories
6. Look up the firmware upgrade procedure runbook
7. Recommend: upgrade schedule, considering SLA windows and traffic rerouting requirements
```

**Verify:** `ls data/scenarios/telco-noc/data/prompts/demo_scenarios/*.md | wc -l` returns **4**.

---

#### Step 2.5 — Rebuild the frontend

**Action:** Only required if you performed Step 1.11 or Step 1.12 (updating `config.ts`).

```bash
cd frontend && npm run build
```

**Verify:** `ls frontend/dist/assets/index-*.js` produces a new file. The old filename will have changed (Vite uses content hashing).

---

#### Step 2.6 — Deploy

**Action:** Redeploy the application so the new data, provisioning changes, prompts, and runbooks are picked up.

**Option A — Full deploy (recommended):**

```bash
./deploy.sh
```

This runs the complete pipeline: topology.json generation (Step 2b) → infrastructure (Step 3) → Fabric provisioning including lakehouse tables + ontology (Step 5) → data provisioning including search index (Step 6) → agent provisioning (Step 7) → health check (Step 8).

**Option B — Targeted update (if infrastructure is already provisioned):**

```bash
# 1. Regenerate topology.json from updated graph_schema.yaml
uv run python scripts/generate_topology_json.py --scenario telco-noc

# 2. Upload new runbook blobs to Azure Blob Storage
bash hooks/postprovision.sh

# 3. Re-create/run AI Search indexer to process new runbooks
uv run python scripts/provision_search_index.py

# 4. Upload CSVs + rebuild Lakehouse tables (picks up new LAKEHOUSE_TABLES entries)
uv run python scripts/fabric/provision_lakehouse.py

# 5. Re-create ontology with new entity/relationship types
uv run python scripts/fabric/provision_ontology.py

# 6. Rebuild frontend (only if Step 1.11 was done)
cd frontend && npm run build && cd ..

# 7. Deploy app code
azd deploy app --no-prompt
```

> **WARNING:** Do NOT run only `azd deploy app` and `bash hooks/postprovision.sh` — this skips the Fabric provisioning scripts and the AI Search indexer. The new entity types would not appear in the graph, and new runbooks would sit in blob storage without being indexed.

**Verify:** After deployment:
1. The graph topology in the UI should now show PhysicalConduit, AmplifierSite, and Advisory nodes
2. New node types appear in the GraphToolbar legend (with colors — either from config or auto-generated)
3. Users can click the color dot next to any new node type to open the color wheel and pick a custom color
4. The Orchestrator can answer queries about conduits, amplifiers, and advisories

---

#### Step 2.7 — Verification Checklist (Phase 2)

| # | Check | How | Expected |
|---|---|---|---|
| 1 | Runbook count | `ls data/scenarios/telco-noc/data/knowledge/runbooks/*.md \| wc -l` | **8** |
| 2 | Demo prompt count | `ls data/scenarios/telco-noc/data/prompts/demo_scenarios/*.md \| wc -l` | **4** |
| 3 | Graph has PhysicalConduit nodes | Query in UI: "Show me all physical conduits" | Returns 3 conduits |
| 4 | Shared conduit insight works | Query: "Do FIBRE-01 and FIBRE-02 share a physical conduit?" | AI identifies CONDUIT-SYD-MEL-INLAND |
| 5 | Advisory correlation works | Query: "What firmware advisories affect our Cisco routers?" | AI finds ADV-CISCO-2025-001 affecting SYD-01 and MEL-01 |
| 6 | Amplifier query works | Query: "Which amplifiers service the SYD-MEL fibre?" | AI returns Goulburn and Albury sites |
| 7 | Conduit prompt works | Copy-paste `conduit_correlation.md` into chat | Orchestrator investigates dual-fibre failure |
| 8 | Color wheel works for new types | Click color dot next to PhysicalConduit in legend | Color wheel popover opens |
| 9 | Lakehouse tables provisioned | Check Fabric Lakehouse has 16 tables | **16** (was 10) |
| 10 | Ontology has new entity types | Check Fabric IQ Ontology for 11 entity types | **11** (was 8) |

---

### Summary — Total Files Changed or Created

| Action | File | Phase | Step |
|---|---|---|---|
| **MODIFIED** | `data/scenarios/telco-noc/data/entities/DimCoreRouter.csv` | 1 | 1.1 |
| **CREATED** | `data/scenarios/telco-noc/data/entities/DimPhysicalConduit.csv` | 1 | 1.2 |
| **CREATED** | `data/scenarios/telco-noc/data/entities/FactConduitMapping.csv` | 1 | 1.3 |
| **CREATED** | `data/scenarios/telco-noc/data/entities/DimAmplifierSite.csv` | 1 | 1.4 |
| **CREATED** | `data/scenarios/telco-noc/data/entities/FactAmplifierMapping.csv` | 1 | 1.5 |
| **CREATED** | `data/scenarios/telco-noc/data/entities/DimAdvisory.csv` | 1 | 1.6 |
| **CREATED** | `data/scenarios/telco-noc/data/entities/FactAdvisoryMapping.csv` | 1 | 1.7 |
| **MODIFIED** | `data/scenarios/telco-noc/graph_schema.yaml` | 1 | 1.8 |
| **MODIFIED** | `data/scenarios/telco-noc/data/prompts/graph_explorer/core_schema.md` | 1 | 1.9 |
| **MODIFIED** | `data/scenarios/telco-noc/scenario.yaml` | 1 | 1.10, 1.12 |
| **MODIFIED** | `frontend/src/config.ts` (optional) | 1 | 1.11, 1.12 |
| **MODIFIED** | `scripts/fabric/provision_lakehouse.py` | 2 | 2.1 |
| **MODIFIED** | `scripts/fabric/provision_ontology.py` | 2 | 2.2 |
| **CREATED** | `data/scenarios/telco-noc/data/knowledge/runbooks/conduit_shared_risk_assessment.md` | 2 | 2.3 |
| **CREATED** | `data/scenarios/telco-noc/data/knowledge/runbooks/amplifier_maintenance.md` | 2 | 2.3 |
| **CREATED** | `data/scenarios/telco-noc/data/knowledge/runbooks/firmware_upgrade_procedure.md` | 2 | 2.3 |
| **CREATED** | `data/scenarios/telco-noc/data/prompts/demo_scenarios/planned_maintenance.md` | 2 | 2.4 |
| **CREATED** | `data/scenarios/telco-noc/data/prompts/demo_scenarios/conduit_correlation.md` | 2 | 2.4 |
| **CREATED** | `data/scenarios/telco-noc/data/prompts/demo_scenarios/predictive_degradation.md` | 2 | 2.4 |
| **CREATED** | `data/scenarios/telco-noc/data/prompts/demo_scenarios/firmware_advisory_correlation.md` | 2 | 2.4 |
| **Total** | **6 modified + 14 created = 20 files** | |

---

## 15. Plan Vetting — Resolution Summary

> **Original vetting (v1)** identified 11 issues across CRITICAL/HIGH/MEDIUM/LOW severity. All issues have been incorporated into the revised Section 14 (v2). This section provides a cross-reference.

| # | Severity | Issue | Resolution | Step |
|---|---|---|---|---|
| 1 | **CRITICAL** | `provision_lakehouse.py` missing 6 new table entries | Added Step 2.1 with exact code | 2.1 |
| 2 | **CRITICAL** | `provision_ontology.py` missing ~150 lines (IDs, entity types, bindings, contextualizations) | Added Step 2.2 with all 10 sub-changes (A through J) | 2.2 |
| 3 | **HIGH** | ADV-CISCO-2025-002 `AffectedVersions` missing `IOS-XR-7.9.2` | Fixed in Step 1.6 CSV content | 1.6 |
| 4 | **HIGH** | Deploy step missing `provision_search_index.py` re-run | Step 2.6 Deploy now shows full pipeline (Option A: `./deploy.sh`, Option B: manual sequence including indexer) | 2.6 |
| 5 | **HIGH** | `generate_topology_json.py` not re-run after schema changes | Noted that `deploy.sh` Step 2b auto-runs it; also included in Option B manual sequence | 2.6 |
| 6 | **HIGH** | New prompt files have no consumer / integration point | Step 2.4 clarifies they are "demo starters" for copy-paste, placed in `demo_scenarios/` subdirectory | 2.4 |
| 7 | **HIGH** | `exampleQuestions` not updated for new capabilities | Added Step 1.12 with 3 new questions for both `scenario.yaml` and `config.ts` | 1.12 |
| 8 | **MEDIUM** | Vertex-count `grep` wrong (counts all `label:` in file) | Step 1.13 Check #5 now uses `awk` to count only vertex labels | 1.13 |
| 9 | **MEDIUM** | nodeColors `grep` too broad (matches every `:` in file) | Step 1.13 Check #9 now uses `grep -A15 'nodeColors' \| grep -c ':'` | 1.13 |
| 10 | **LOW** | Advisory "Affected Routers" column is derived, could confuse implementer | Added HTML comment note in Step 1.9 | 1.9 |
| 11 | **LOW** | Demo prompt files mixed with agent system prompts | Step 2.4 now uses `prompts/demo_scenarios/` subdirectory | 2.4 |

> **All 11 issues resolved.** The plan is now implementation-ready. Phase 1 (Steps 1.1–1.13) covers data, schema, prompt, and config changes. Phase 2 (Steps 2.1–2.7) covers provisioning script updates, knowledge documents, demo prompts, frontend rebuild, deployment, and verification.