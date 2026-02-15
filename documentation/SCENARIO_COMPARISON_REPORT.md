# Scenario Comparison Report

**Reference (Gold Standard):** `telco-noc`
**Compared Scenarios:** `customer-recommendation`, `cloud-outage`
**Base Path:** `data/scenarios/<scenario>/`

---

## Table of Contents

1. [Directory Structure](#1-directory-structure)
2. [Configuration Files](#2-configuration-files)
   - [scenario.yaml](#21-scenarioyaml)
   - [graph_schema.yaml](#22-graph_schemayaml)
3. [Prompt Files](#3-prompt-files)
   - [Default Alert / Alert Storm](#31-default-alert--alert-storm)
   - [Orchestrator Agent](#32-orchestrator-agent)
   - [Telemetry Agent v2](#33-telemetry-agent-v2)
   - [Historical Ticket Agent](#34-historical-ticket-agent)
   - [Runbook KB Agent](#35-runbook-kb-agent)
   - [Graph Explorer — core_instructions.md](#36-graph-explorer--core_instructionsmd)
   - [Graph Explorer — core_schema.md](#37-graph-explorer--core_schemamd)
   - [Graph Explorer — description.md](#38-graph-explorer--descriptionmd)
   - [Graph Explorer — language_gremlin.md](#39-graph-explorer--language_gremlinmd)
   - [Graph Explorer — language_mock.md](#310-graph-explorer--language_mockmd)
4. [Script Files](#4-script-files)
   - [generate_all.sh](#41-generate_allsh)
   - [generate_topology.py](#42-generate_topologypy)
   - [generate_telemetry.py](#43-generate_telemetrypy)
   - [generate_tickets.py](#44-generate_ticketspy)
   - [generate_routing.py](#45-generate_routingpy)
5. [Knowledge / Runbooks](#5-knowledge--runbooks)
6. [Knowledge / Tickets](#6-knowledge--tickets)
7. [Data / Entities (CSVs)](#7-data--entities-csvs)
8. [Data / Telemetry (CSVs)](#8-data--telemetry-csvs)
9. [Issues & Recommendations](#9-issues--recommendations)

---

## 1. Directory Structure

All three scenarios share an identical directory tree:

```
<scenario>/
├── scenario.yaml
├── graph_schema.yaml
├── data/
│   ├── entities/          # Dim*.csv + Fact*.csv
│   ├── knowledge/
│   │   ├── runbooks/      # .md
│   │   └── tickets/       # .txt
│   ├── prompts/
│   │   ├── <default_alert>.md
│   │   ├── foundry_orchestrator_agent.md
│   │   ├── foundry_historical_ticket_agent.md
│   │   ├── foundry_runbook_kb_agent.md
│   │   ├── foundry_telemetry_agent_v2.md
│   │   └── graph_explorer/
│   │       ├── core_instructions.md
│   │       ├── core_schema.md
│   │       ├── description.md
│   │       ├── language_gremlin.md
│   │       └── language_mock.md
│   └── telemetry/         # AlertStream.csv + domain-specific metrics CSV
└── scripts/
    ├── generate_all.sh
    ├── generate_topology.py
    ├── generate_telemetry.py
    ├── generate_tickets.py
    └── generate_routing.py
```

**Structural Differences:** None — the tree is identical. The only variance is file *naming* (the default alert prompt) and file *counts* (entities, runbooks, routing CSVs).

---

## 2. Configuration Files

### 2.1 scenario.yaml

| Field | telco-noc | customer-recommendation | cloud-outage |
|-------|-----------|------------------------|--------------|
| `name` | `telco-noc` | `customer-recommendation` | `cloud-outage` |
| `display_name` | Telco NOC — Fibre-Cut Alert Storm | Customer Recommendation — Model Bias Alert Storm | Cloud Outage — Cooling-Failure Alert Storm |
| `domain` | `telecommunications` | `e-commerce` | `cloud-infrastructure` |
| `description` | Fibre cut on SYD-MEL link cascade | Model bias → wrong products → return spike | Cooling failure → thermal cascade → VM/service outage |
| `default_alert` | `prompts/alert_storm.md` | `prompts/default_alert.md` | `prompts/default_alert.md` |
| Cosmos containers | `AlertStream` (partition: `/SourceNodeType`) + `LinkTelemetry` (partition: `/LinkId`) | `AlertStream` (partition: `/SourceNodeType`) + `RecommendationMetrics` (partition: `/SegmentId`) | `AlertStream` (partition: `/SourceNodeType`) + `HostMetrics` (partition: `/HostId`) |
| `numeric_fields` | UtilizationPct, BitErrorRate, OpticalPowerDbm, LatencyMs, PacketLossPct | ClickRatePct, ConversionRatePct, ReturnRatePct, AvgOrderValueUSD | TemperatureCelsius, CPUUtilPct, MemoryUtilPct, DiskIOPS |

**Differences from telco-noc:**
- **Alert file naming**: telco-noc uses the unique name `alert_storm.md`; both others use `default_alert.md`. This inconsistency means the telco-noc prompt file is named differently from the convention the other two scenarios follow.
- **Partition keys**: Each scenario has a different partition key on its domain-specific container — `/LinkId`, `/SegmentId`, `/HostId` — aligned to the natural entity grain; AlertStream is always `/SourceNodeType`.
- **Numeric fields**: Completely domain-specific, no overlap.

### 2.2 graph_schema.yaml

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Vertex types (8 each)** | CoreRouter, AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession | CustomerSegment, Customer, ProductCategory, Product, Campaign, Supplier, Warehouse, SLAPolicy | Region, AvailabilityZone, Rack, Host, VirtualMachine, LoadBalancer, Service, SLAPolicy |
| **Edge examples** | connects_to, aggregates_to, routes_via, depends_on, governs | belongs_to, purchased, promotes, targets, supplied_by, stored_in, governs | contains_az, has_rack, hosts_server, runs, serves, routes_to, governs |
| **Edge filters** | None | `purchased` edge has `negate: true` filter (unique) | None |
| **SLAPolicy scope** | ServiceId → Service | SegmentId → CustomerSegment | ServiceId → Service |

**Differences from telco-noc:**
- Entity count is always 8 vertex types, maintaining parity.
- **customer-recommendation** introduces `negate: true` on the `purchased` edge filter — no other scenario uses this. This allows the graph query layer to negate edge traversal conditions (e.g., "customers who have NOT purchased").
- **SLAPolicy** is structurally the same but scoped to different target entities.
- All edges are domain-specific; none are reused across scenarios.

---

## 3. Prompt Files

### 3.1 Default Alert / Alert Storm

| | telco-noc | customer-recommendation | cloud-outage |
|-|-----------|------------------------|--------------|
| **Filename** | `alert_storm.md` | `default_alert.md` | `default_alert.md` |
| **Alert type** | LINK_DOWN on LINK-SYD-MEL-FIBRE-01 | MODEL_BIAS_DETECTED on CAMP-NEWUSER-Q1 | COOLING_FAILURE on AZ-US-EAST-A |
| **Severity** | CRITICAL | CRITICAL | CRITICAL |
| **Source entity** | TransportLink | Campaign | AvailabilityZone |
| **Downstream effects listed** | BGP sessions, MPLS paths, services | Customer segments, return rate spike, SLA breach risk | Racks, hosts, VMs, load balancers, services |

**Structure**: All three follow an identical markdown template: heading, alert properties (Severity, Source, AlertType, SourceNodeType, AlertMessage, Timestamp), a "downstream-effects" section. Fully domain-adapted.

### 3.2 Orchestrator Agent

**File:** `foundry_orchestrator_agent.md`

All three follow the same template with these sections:
1. Role & Identity
2. Scenario Context (X-Graph header value)
3. Specialist Agent Descriptions (4 agents)
4. Telemetry Baselines table
5. Investigation Flows (Flow A: known alert, Flow B: general question)
6. Situation Report format
7. Rules & Constraints

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Role** | Senior Network Operations Engineer | Senior E-Commerce Operations Analyst | Senior Cloud Infrastructure Operations Engineer |
| **X-Graph header** | `telco-noc` | `customer-recommendation` | `cloud-outage` |
| **Baseline metrics** | UtilizationPct ~30%, BitErrorRate ~1e-9, OpticalPowerDbm ~-5, LatencyMs ~2, PacketLossPct ~0.01 | ClickRatePct ~4.5%, ConversionRatePct ~2.8%, ReturnRatePct ~2.1%, AvgOrderValueUSD ~$175 | TemperatureCelsius ~25°C, CPUUtilPct ~35%, MemoryUtilPct ~50%, DiskIOPS ~2000 |
| **Flow A** steps | Topology → Telemetry → Runbooks → Tickets → SitRep | Topology → Telemetry → Runbooks → Tickets → SitRep | Topology → Telemetry → Runbooks → Tickets → SitRep |
| **SitRep format** | Identical template across all 3 | ✓ | ✓ |

**Differences from telco-noc:** Pure domain adaptation. The template structure, section ordering, rule set, and SitRep format are identical.

### 3.3 Telemetry Agent v2

**File:** `foundry_telemetry_agent_v2.md`

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Containers** | AlertStream + LinkTelemetry | AlertStream + RecommendationMetrics | AlertStream + HostMetrics |
| **Schema fields (domain)** | LinkId, UtilizationPct, BitErrorRate, OpticalPowerDbm, LatencyMs, PacketLossPct | SegmentId, ClickRatePct, ConversionRatePct, ReturnRatePct, AvgOrderValueUSD | HostId, TemperatureCelsius, CPUUtilPct, MemoryUtilPct, DiskIOPS |
| **Example queries** | 4 SQL examples with LinkTelemetry | 4 SQL examples with RecommendationMetrics | 4 SQL examples with HostMetrics |
| **X-Graph header** | `telco-noc` | `customer-recommendation` | `cloud-outage` |

**Differences from telco-noc:** Same template structure (Role → Containers → Schema → SQL Examples → Rules). All domain-adapted.

### 3.4 Historical Ticket Agent

**File:** `foundry_historical_ticket_agent.md`

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Role** | Historical Ticket Analyst for telecom NOC | Historical Ticket Analyst for e-commerce recommendation platform | Historical Ticket Analyst for cloud infrastructure |
| **Ticket fields** | Same 7-field schema across all | ✓ | ✓ |
| **Domain examples** | Fibre cuts, BGP issues | Model bias, campaign targeting | Cooling failures, thermal shutdowns |

**Differences from telco-noc:** Minimal — role description and domain examples change; the ticket field schema and instructions are identical.

### 3.5 Runbook KB Agent

**File:** `foundry_runbook_kb_agent.md`

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Role** | Runbook and Knowledge Base Specialist for telecom | Runbook and Knowledge Base Specialist for e-commerce | Runbook and Knowledge Base Specialist for cloud infrastructure |
| **Runbooks listed** | 5: fibre_cut_runbook, bgp_peer_loss_runbook, traffic_engineering_reroute, alert_storm_triage_guide, customer_communication_template | 5: model_bias_runbook, campaign_suspension_runbook, alert_storm_triage_guide, recommendation_rollback_runbook, customer_communication_template | 5: cooling_failure_runbook, host_thermal_shutdown_runbook, vm_live_migration_guide, loadbalancer_failover_guide, alert_storm_triage_guide |

**⚠️ CRITICAL ISSUE — customer-recommendation:**
The prompt lists 5 runbook filenames that **do not match** the actual files on disk:

| Prompt says | Actual file on disk |
|-------------|-------------------|
| `model_bias_runbook.md` | `recommendation_bias_runbook.md` |
| `campaign_suspension_runbook.md` | `campaign_targeting_validation.md` |
| `recommendation_rollback_runbook.md` | `return_rate_investigation.md` |
| `customer_communication_template.md` | **DOES NOT EXIST** |
| `alert_storm_triage_guide.md` | ✓ matches |

The prompt lists 5 runbooks but only 4 files exist on disk, and 3 of the 4 existing files have different names than what the prompt describes.

**telco-noc and cloud-outage:** Prompt runbook listings match actual files on disk ✓

### 3.6 Graph Explorer — core_instructions.md

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Role** | Graph explorer for telecom network topology | Graph explorer for e-commerce recommendation topology | Graph explorer for cloud infrastructure topology |
| **X-Graph header** | `telco-noc` | `customer-recommendation` | `cloud-outage` |
| **Capabilities** | Same 4 capabilities across all | ✓ | ✓ |

**Differences from telco-noc:** Domain adaptation only. Same template structure (Role → X-Graph Header → Capabilities → Rules).

### 3.7 Graph Explorer — core_schema.md

This is the largest and most varied file across scenarios. It contains the full vertex and edge schema with **every entity instance enumerated**.

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Vertex types** | 8 | 8 | 8 |
| **Entity instances listed** | ~50+ (routers, switches, links, paths, services, SLAs, BGP sessions) | ~50+ (segments, customers, categories, products, campaigns, suppliers, warehouses, SLAs) | ~50+ (regions, AZs, racks, hosts, VMs, LBs, services, SLAs) |
| **Edge types** | ~8 (connects_to, aggregates_to, routes_via, carried_on, depends_on, has_session, governs) | ~8 (belongs_to, purchased, categorized_under, promotes, targets, supplied_by, stored_in, governs) | ~8 (contains_az, has_rack, hosts_server, runs, serves, routes_to, balanced_by, governs) |
| **Edge instances listed** | All specific connections enumerated | All specific connections enumerated | All specific connections enumerated |

**Differences from telco-noc:** Completely different entities and relationships. Same documentation format (Entity table → Instance list → Edge definitions → Edge instance list).

### 3.8 Graph Explorer — description.md

Single paragraph used as the Foundry agent description field.

| telco-noc | customer-recommendation | cloud-outage |
|-----------|------------------------|--------------|
| "Explores a telco transport network graph..." | "Explores an e-commerce recommendation graph..." | "Explores a cloud infrastructure graph..." |

**Differences from telco-noc:** One sentence changed for domain context.

### 3.9 Graph Explorer — language_gremlin.md

Provides Gremlin query examples for the graph query API.

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Example queries** | ~10 queries using CoreRouter, TransportLink, MPLSPath, etc. | ~10 queries using Customer, Product, Campaign, etc. | ~10 queries using Host, VM, LoadBalancer, etc. |
| **Edge traversals** | connects_to, routes_via, depends_on | belongs_to, purchased, promotes | contains_az, has_rack, runs |
| **Filter patterns** | has('Status','Active'), has('UtilizationPct',gt(80)) | has('ReturnRatePct',gt(10)), has('AvgOrderValueUSD',gt(500)) | has('TemperatureCelsius',gt(35)), has('CPUUtilPct',gt(80)) |

**Differences from telco-noc:** Domain-adapted query examples. Same pedagogical structure (simple → complex queries).

### 3.10 Graph Explorer — language_mock.md

Natural language query examples for the mock graph backend.

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Example queries** | "Show me all links between SYD and MEL", "What services depend on MPLS-PATH-SYD-MEL-PRIMARY?" | "Show me all products promoted by CAMP-NEWUSER-Q1", "Which customers have returned products?" | "Show me all VMs running on HOST-USE-R01-H01", "What services are served by LB-USE-WEB?" |
| **Count** | ~8 examples | ~8 examples | ~8 examples |

**Differences from telco-noc:** Domain-adapted. Same format.

---

## 4. Script Files

### 4.1 generate_all.sh

Identical structure across all three. A bash wrapper that calls the 4 Python scripts in sequence:
```bash
python generate_topology.py
python generate_telemetry.py
python generate_tickets.py
python generate_routing.py
```

**Only difference:** The `echo` statement at the start references the scenario name.

### 4.2 generate_topology.py

Generates `Dim*.csv` files for graph vertex entities.

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Entity types** | CoreRouter, AggSwitch, BaseStation, TransportLink, MPLSPath, Service, SLAPolicy, BGPSession | CustomerSegment, Customer, ProductCategory, Product, Campaign, Supplier, Warehouse, SLAPolicy | Region, AvailabilityZone, Rack, Host, VirtualMachine, LoadBalancer, Service, SLAPolicy |
| **Dim CSV files** | 8 | 8 | 8 |
| **Entity count** | ~40–50 instances | ~40–50 instances | ~40–50 instances |
| **Shared entity** | SLAPolicy (ServiceId-scoped) | SLAPolicy (SegmentId-scoped) | SLAPolicy (ServiceId-scoped) |

**Pattern:** Each script defines each entity type as a list of dicts, then writes to CSV using `csv.DictWriter`. Same code pattern throughout.

**Differences from telco-noc:**
- Completely different entity schemas and property names
- customer-recommendation: SLAPolicy uses `SegmentId` instead of `ServiceId`
- cloud-outage: SLAPolicy uses `ServiceId` (matches telco-noc pattern)

### 4.3 generate_telemetry.py

Generates `AlertStream.csv` + one domain-specific metrics CSV.

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Alert CSV** | AlertStream.csv | AlertStream.csv | AlertStream.csv |
| **Metrics CSV** | LinkTelemetry.csv | RecommendationMetrics.csv | HostMetrics.csv |
| **Baseline period** | 54 hours noise | 54 hours noise | 54 hours noise |
| **Incident cascade** | 90 seconds, ~5000 alerts | 90 seconds, ~5000 alerts | 90 seconds, ~5000 alerts |
| **Cascade pattern** | Physical → Routing → Service: LINK_DOWN → BGP_PEER_LOSS → OSPF_ADJACENCY_DOWN → ROUTE_WITHDRAWAL → HIGH_CPU → PACKET_LOSS → SERVICE_DEGRADATION | Business logic: MODEL_BIAS_DETECTED → STALE_PRICE_FEED → SEGMENT_MISMATCH → HIGH_RETURN_RATE → REVENUE_DROP → INVENTORY_ALERT → SLA_RISK | Physical → Logical: COOLING_FAILURE → TEMP_WARNING → THERMAL_CRITICAL → HOST_CPU_THROTTLE → VM_PERFORMANCE_DEGRADED → FAILOVER_TRIGGERED → SERVICE_DEGRADATION |
| **Metrics fields** | UtilizationPct, BitErrorRate, OpticalPowerDbm, LatencyMs, PacketLossPct | ClickRatePct, ConversionRatePct, ReturnRatePct, AvgOrderValueUSD | TemperatureCelsius, CPUUtilPct, MemoryUtilPct, DiskIOPS |

**Differences from telco-noc:** Same temporal pattern (54h baseline + 90s cascade) and approximate alert volume. The cascade steps and metric fields are fully domain-adapted.

### 4.4 generate_tickets.py

Generates 10 historical incident ticket `.txt` files.

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Ticket count** | 10 | 10 | 10 |
| **Date range** | INC-2025-08 → INC-2026-02 | INC-2025-05 → INC-2026-01 | INC-2025-06 → INC-2026-01 |
| **Ticket format** | Same 7-field format across all | ✓ | ✓ |
| **Domain topics** | Fibre cuts, BGP peer loss, DWDM degradation, high CPU, APC failure, SLA breach, OSPF adjacency loss | Model bias, segment mismatch, high return rate, stale price feed, campaign targeting error, warehouse overload | Cooling failure, thermal shutdown, VM degradation, LB failover, power spike, network partition, disk failure |

**Differences from telco-noc:** Same structure and count. Domain-adapted incident content.

### 4.5 generate_routing.py

Generates `Fact*.csv` junction/bridge tables for graph edges.

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Fact CSV files** | **2**: FactMPLSPathHops.csv, FactServiceDependency.csv | **3**: FactPurchaseHistory.csv, FactCampaignTargeting.csv, FactProductWarehouse.csv | **1**: FactServiceDependency.csv |
| **Total rows** | ~30 + ~10 | ~50 + ~10 + ~15 | ~10 |

**⚠️ Issues:**
1. **cloud-outage produces only 1 Fact CSV** — the docstring in `generate_routing.py` mentions `FactVMPlacement.csv` but the code never generates it. This is a discrepancy between documentation and implementation.
2. **Inconsistent fact table counts**: telco-noc=2, customer-recommendation=3, cloud-outage=1. The cloud-outage scenario may be missing junction tables needed for some graph edges (e.g., VM-to-Host placement, Service-to-LB routing).

---

## 5. Knowledge / Runbooks

### File Inventory

| | telco-noc (5 files) | customer-recommendation (4 files) | cloud-outage (5 files) |
|-|--------------------|---------------------------------|----------------------|
| 1 | `alert_storm_triage_guide.md` | `alert_storm_triage_guide.md` | `alert_storm_triage_guide.md` |
| 2 | `bgp_peer_loss_runbook.md` | `campaign_targeting_validation.md` | `cooling_failure_runbook.md` |
| 3 | `customer_communication_template.md` | `recommendation_bias_runbook.md` | `host_thermal_shutdown_runbook.md` |
| 4 | `fibre_cut_runbook.md` | `return_rate_investigation.md` | `loadbalancer_failover_guide.md` |
| 5 | `traffic_engineering_reroute.md` | — | `vm_live_migration_guide.md` |

### Shared Files

**`alert_storm_triage_guide.md`** exists in all three scenarios but is completely rewritten per domain:
- **telco-noc**: Physical → Logical cascade, 2000+ alerts, topological correlation, alert type hierarchy (LINK_DOWN → BGP_PEER_LOSS → ... → SERVICE_DEGRADATION)
- **customer-recommendation**: Model → Business logic cascade, traces through Campaign → Segment → Customer → Product, focuses on revenue impact assessment
- **cloud-outage**: Physical → Logical cascade (Cooling → Rack → Host → VM → Service → LB), focuses on failover verification and SLA impact

### Runbook Quality Comparison

| Quality Metric | telco-noc | customer-recommendation | cloud-outage |
|---------------|-----------|------------------------|--------------|
| Gremlin examples included | ✓ (in 4/5 runbooks) | ✓ (in 3/4 runbooks) | ✓ (in 4/5 runbooks) |
| Escalation matrix | ✓ (detailed in fibre_cut) | Partial | ✓ (detailed in cooling_failure) |
| Decision trees | ✓ (bgp_peer_loss) | ✗ | ✗ |
| Communication templates | ✓ (customer_communication_template - very detailed with 3 templates) | ✗ (missing!) | ✗ |
| Recovery procedures | ✓ | ✓ | ✓ |
| Cross-references | ✓ (runbooks link to each other) | ✗ | ✗ |

**⚠️ customer-recommendation has only 4 runbooks** vs 5 for telco-noc and cloud-outage.

**⚠️ Neither customer-recommendation nor cloud-outage has a customer_communication_template** — telco-noc's version is a rich, reusable template (Initial Notification, Update, Resolution with variable substitution). The other scenarios should probably have domain-adapted versions.

---

## 6. Knowledge / Tickets

| Aspect | telco-noc | customer-recommendation | cloud-outage |
|--------|-----------|------------------------|--------------|
| **Count** | 10 | 10 | 10 |
| **Format** | 7-field text (ID, Date, Severity, Title, Summary, Root Cause, Resolution) | Same | Same |
| **Date range** | Aug 2025 – Feb 2026 | May 2025 – Jan 2026 | Jun 2025 – Jan 2026 |
| **Generated by** | `generate_tickets.py` | `generate_tickets.py` | `generate_tickets.py` |

All three use the same ticket format and count. No structural differences.

---

## 7. Data / Entities (CSVs)

| telco-noc (10 files) | customer-recommendation (11 files) | cloud-outage (9 files) |
|---------------------|-----------------------------------|-----------------------|
| DimCoreRouter.csv | DimCustomerSegment.csv | DimRegion.csv |
| DimAggSwitch.csv | DimCustomer.csv | DimAvailabilityZone.csv |
| DimBaseStation.csv | DimProductCategory.csv | DimRack.csv |
| DimTransportLink.csv | DimProduct.csv | DimHost.csv |
| DimMPLSPath.csv | DimCampaign.csv | DimVirtualMachine.csv |
| DimService.csv | DimSupplier.csv | DimLoadBalancer.csv |
| DimSLAPolicy.csv | DimWarehouse.csv | DimService.csv |
| DimBGPSession.csv | DimSLAPolicy.csv | DimSLAPolicy.csv |
| FactMPLSPathHops.csv | FactPurchaseHistory.csv | FactServiceDependency.csv |
| FactServiceDependency.csv | FactCampaignTargeting.csv | |
| | FactProductWarehouse.csv | |

**Counts**: 10, 11, 9. The variance is due to different numbers of Fact tables.

---

## 8. Data / Telemetry (CSVs)

| telco-noc | customer-recommendation | cloud-outage |
|-----------|------------------------|--------------|
| AlertStream.csv | AlertStream.csv | AlertStream.csv |
| LinkTelemetry.csv | RecommendationMetrics.csv | HostMetrics.csv |

All have exactly 2 telemetry CSVs. AlertStream is shared; the second is domain-specific.

---

## 9. Issues & Recommendations

### 🔴 Critical Issues

| # | Scenario | Issue | Details |
|---|----------|-------|---------|
| 1 | customer-recommendation | **Runbook KB prompt references non-existent files** | The `foundry_runbook_kb_agent.md` prompt lists 5 runbooks but only 4 exist on disk, and 3 of the 4 have different names than what the prompt describes. This means the AI Search index will be built from the actual files, but the agent's instructions reference wrong filenames — the agent may fail to retrieve the correct runbooks. |
| 2 | cloud-outage | **generate_routing.py missing FactVMPlacement.csv** | The script's docstring mentions generating `FactVMPlacement.csv` but the code only generates `FactServiceDependency.csv`. The VM-to-Host relationship exists in the graph schema but has no corresponding Fact table for bulk ingest. |

### 🟡 Moderate Issues

| # | Scenario | Issue | Details |
|---|----------|-------|---------|
| 3 | telco-noc | **Inconsistent alert file naming** | Uses `alert_storm.md` while both other scenarios use `default_alert.md`. The `scenario.yaml` handles this correctly, but it creates an unnecessary naming inconsistency. Consider renaming to `default_alert.md` for consistency. |
| 4 | customer-recommendation | **Missing customer_communication_template** | telco-noc has a detailed, reusable customer communication template. Neither customer-recommendation nor cloud-outage has one. For SLA-bearing scenarios, this is important. |
| 5 | customer-recommendation | **Only 4 runbooks vs 5** | Has fewer runbooks than telco-noc and cloud-outage. Could benefit from a 5th (e.g., a customer communication template adapted for e-commerce). |
| 6 | customer-recommendation / cloud-outage | **No cross-references between runbooks** | telco-noc runbooks link to each other with "Related Runbooks" sections. The other scenarios' runbooks mostly lack this. |

### 🟢 Minor / Cosmetic

| # | Scenario | Issue | Details |
|---|----------|-------|---------|
| 7 | cloud-outage | **Fewer Fact tables** | Only 1 Fact CSV vs telco-noc's 2 and customer-recommendation's 3. This may be intentional if edges are defined directly in `generate_topology.py`, but should be verified. |
| 8 | All | **Date range inconsistency in tickets** | Each scenario uses a different date range for historical tickets. Not a functional issue but worth noting for demo consistency. |
| 9 | customer-recommendation / cloud-outage | **No decision trees in runbooks** | telco-noc's `bgp_peer_loss_runbook.md` has a detailed ASCII decision tree. The other scenarios' runbooks could benefit from similar structured diagnostic trees. |

### Recommendations

1. **Fix customer-recommendation runbook prompt** (Critical) — Update `foundry_runbook_kb_agent.md` to reference the actual filenames on disk, or rename the files to match the prompt.
2. **Implement FactVMPlacement.csv** in cloud-outage's `generate_routing.py` — or remove the mention from the docstring.
3. **Standardize alert file naming** — rename telco-noc's `alert_storm.md` to `default_alert.md` and update `scenario.yaml`.
4. **Add customer communication templates** to customer-recommendation and cloud-outage scenarios.
5. **Add cross-references** to runbooks in customer-recommendation and cloud-outage.
6. **Add a 5th runbook** to customer-recommendation to reach parity.

---

*Generated from full file-by-file comparison of all three scenario directories.*
