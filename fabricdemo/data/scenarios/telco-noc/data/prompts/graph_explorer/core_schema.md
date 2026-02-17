# Network Topology Ontology — Full Schema

## Entity Types

### CoreRouter (3 instances)

Backbone routers at city level. Each city has one core router.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **RouterId** | String | **Primary key.** | `CORE-SYD-01` |
| City | String | City where the router is located. | `Sydney` |
| Region | String | State / region. | `NSW` |
| Vendor | String | Equipment manufacturer. | `Cisco` |
| Model | String | Hardware model. | `ASR-9922` |

**All instances:**

| RouterId | City | Region | Vendor | Model |
|---|---|---|---|---|
| CORE-SYD-01 | Sydney | NSW | Cisco | ASR-9922 |
| CORE-MEL-01 | Melbourne | VIC | Cisco | ASR-9922 |
| CORE-BNE-01 | Brisbane | QLD | Juniper | MX10008 |

---

### TransportLink (10 instances)

Physical transport links. 4 are inter-city DWDM backbone fibres, 6 are local aggregation uplinks.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **LinkId** | String | **Primary key.** | `LINK-SYD-MEL-FIBRE-01` |
| LinkType | String | Technology type. Values: `DWDM_100G`, `100GE`. | `DWDM_100G` |
| CapacityGbps | Integer | Link capacity in Gbps. | `100` |
| SourceRouterId | String | Source router (FK → CoreRouter.RouterId). | `CORE-SYD-01` |
| TargetRouterId | String | Target router (FK → CoreRouter.RouterId). | `CORE-MEL-01` |

**Inter-city backbone links (DWDM_100G):**

| LinkId | SourceRouterId | TargetRouterId | Notes |
|---|---|---|---|
| LINK-SYD-MEL-FIBRE-01 | CORE-SYD-01 | CORE-MEL-01 | Primary SYD↔MEL — the link that gets cut in the demo |
| LINK-SYD-MEL-FIBRE-02 | CORE-SYD-01 | CORE-MEL-01 | Backup SYD↔MEL — redundant pair |
| LINK-SYD-BNE-FIBRE-01 | CORE-SYD-01 | CORE-BNE-01 | SYD↔BNE |
| LINK-MEL-BNE-FIBRE-01 | CORE-MEL-01 | CORE-BNE-01 | MEL↔BNE |

**Aggregation uplinks (100GE):** LINK-SYD-AGG-NORTH-01, LINK-SYD-AGG-SOUTH-01, LINK-MEL-AGG-EAST-01, LINK-MEL-AGG-WEST-01, LINK-BNE-AGG-CENTRAL-01, LINK-BNE-AGG-SOUTH-01. Each connects a core router to itself (local uplink).

---

### AggSwitch (6 instances)

Aggregation switches between core routers and base stations. Two per city.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SwitchId** | String | **Primary key.** | `AGG-SYD-NORTH-01` |
| City | String | City. | `Sydney` |
| UplinkRouterId | String | Upstream core router (FK → CoreRouter.RouterId). | `CORE-SYD-01` |

**All instances:**

| SwitchId | City | UplinkRouterId |
|---|---|---|
| AGG-SYD-NORTH-01 | Sydney | CORE-SYD-01 |
| AGG-SYD-SOUTH-01 | Sydney | CORE-SYD-01 |
| AGG-MEL-EAST-01 | Melbourne | CORE-MEL-01 |
| AGG-MEL-WEST-01 | Melbourne | CORE-MEL-01 |
| AGG-BNE-CENTRAL-01 | Brisbane | CORE-BNE-01 |
| AGG-BNE-SOUTH-01 | Brisbane | CORE-BNE-01 |

---

### BaseStation (8 instances)

5G NR base stations (gNodeBs) at the network edge.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **StationId** | String | **Primary key.** | `GNB-SYD-2041` |
| StationType | String | Radio technology. Always `5G_NR`. | `5G_NR` |
| AggSwitchId | String | Upstream agg switch (FK → AggSwitch.SwitchId). | `AGG-SYD-NORTH-01` |
| City | String | City. | `Sydney` |

**All instances:**

| StationId | AggSwitchId | City |
|---|---|---|
| GNB-SYD-2041 | AGG-SYD-NORTH-01 | Sydney |
| GNB-SYD-2042 | AGG-SYD-NORTH-01 | Sydney |
| GNB-SYD-2043 | AGG-SYD-SOUTH-01 | Sydney |
| GNB-MEL-3011 | AGG-MEL-EAST-01 | Melbourne |
| GNB-MEL-3012 | AGG-MEL-EAST-01 | Melbourne |
| GNB-MEL-3021 | AGG-MEL-WEST-01 | Melbourne |
| GNB-BNE-4011 | AGG-BNE-CENTRAL-01 | Brisbane |
| GNB-BNE-4012 | AGG-BNE-SOUTH-01 | Brisbane |

---

### BGPSession (3 instances)

BGP peering sessions between core routers. One per inter-city router pair.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SessionId** | String | **Primary key.** | `BGP-SYD-MEL-01` |
| PeerARouterId | String | First peer (FK → CoreRouter.RouterId). | `CORE-SYD-01` |
| PeerBRouterId | String | Second peer (FK → CoreRouter.RouterId). | `CORE-MEL-01` |
| ASNumberA | Integer | BGP AS number for peer A. | `64512` |
| ASNumberB | Integer | BGP AS number for peer B. | `64513` |

**All instances:**

| SessionId | PeerARouterId | PeerBRouterId | ASNumberA | ASNumberB |
|---|---|---|---|---|
| BGP-SYD-MEL-01 | CORE-SYD-01 | CORE-MEL-01 | 64512 | 64513 |
| BGP-SYD-BNE-01 | CORE-SYD-01 | CORE-BNE-01 | 64512 | 64514 |
| BGP-MEL-BNE-01 | CORE-MEL-01 | CORE-BNE-01 | 64513 | 64514 |

---

### MPLSPath (5 instances)

MPLS label-switched paths carrying service traffic between cities.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **PathId** | String | **Primary key.** | `MPLS-PATH-SYD-MEL-PRIMARY` |
| PathType | String | Redundancy tier. Values: `PRIMARY`, `SECONDARY`, `TERTIARY`. | `PRIMARY` |

**All instances:**

| PathId | PathType | What it traverses |
|---|---|---|
| MPLS-PATH-SYD-MEL-PRIMARY | PRIMARY | CORE-SYD-01 → LINK-SYD-MEL-FIBRE-01 → CORE-MEL-01 |
| MPLS-PATH-SYD-MEL-SECONDARY | SECONDARY | CORE-SYD-01 → LINK-SYD-MEL-FIBRE-02 → CORE-MEL-01 |
| MPLS-PATH-SYD-BNE-PRIMARY | PRIMARY | CORE-SYD-01 → LINK-SYD-BNE-FIBRE-01 → CORE-BNE-01 |
| MPLS-PATH-MEL-BNE-PRIMARY | PRIMARY | CORE-MEL-01 → LINK-MEL-BNE-FIBRE-01 → CORE-BNE-01 |
| MPLS-PATH-SYD-MEL-VIA-BNE | TERTIARY | CORE-SYD-01 → LINK-SYD-BNE-FIBRE-01 → CORE-BNE-01 → LINK-MEL-BNE-FIBRE-01 → CORE-MEL-01 |

---

### Service (10 instances)

Customer-facing services. Three types: EnterpriseVPN, Broadband, Mobile5G.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **ServiceId** | String | **Primary key.** | `VPN-ACME-CORP` |
| ServiceType | String | Category. Values: `EnterpriseVPN`, `Broadband`, `Mobile5G`. | `EnterpriseVPN` |
| CustomerName | String | Customer or subscriber group name. | `ACME Corporation` |
| CustomerCount | Integer | Number of customers served (1 for VPN, thousands for broadband/mobile). | `1` |
| ActiveUsers | Integer | Current active user count. | `450` |

**All instances:**

| ServiceId | ServiceType | CustomerName | CustomerCount | ActiveUsers |
|---|---|---|---|---|
| VPN-ACME-CORP | EnterpriseVPN | ACME Corporation | 1 | 450 |
| VPN-BIGBANK | EnterpriseVPN | BigBank Financial | 1 | 1200 |
| VPN-OZMINE | EnterpriseVPN | OzMine Resources | 1 | 680 |
| BB-BUNDLE-SYD-NORTH | Broadband | Residential - Sydney North | 3200 | 3200 |
| BB-BUNDLE-MEL-EAST | Broadband | Residential - Melbourne East | 2800 | 2800 |
| BB-BUNDLE-BNE-CENTRAL | Broadband | Residential - Brisbane Central | 2400 | 2400 |
| MOB-5G-SYD-2041 | Mobile5G | Mobile Subscribers - SYD 2041 | 4200 | 4200 |
| MOB-5G-SYD-2042 | Mobile5G | Mobile Subscribers - SYD 2042 | 4300 | 4300 |
| MOB-5G-MEL-3011 | Mobile5G | Mobile Subscribers - MEL 3011 | 3800 | 3800 |
| MOB-5G-BNE-4011 | Mobile5G | Mobile Subscribers - BNE 4011 | 3600 | 3600 |

---

### SLAPolicy (5 instances)

SLA commitments governing services. Not all services have an SLA policy.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SLAPolicyId** | String | **Primary key.** | `SLA-ACME-GOLD` |
| ServiceId | String | The governed service (FK → Service.ServiceId). | `VPN-ACME-CORP` |
| AvailabilityPct | Double | Uptime commitment percentage. | `99.99` |
| MaxLatencyMs | Integer | Maximum allowed latency in milliseconds. | `15` |
| PenaltyPerHourUSD | Integer | Financial penalty per hour of breach in USD. | `50000` |
| Tier | String | SLA tier. Values: `GOLD`, `SILVER`, `STANDARD`. | `GOLD` |

**All instances:**

| SLAPolicyId | ServiceId | AvailabilityPct | MaxLatencyMs | PenaltyPerHourUSD | Tier |
|---|---|---|---|---|---|
| SLA-ACME-GOLD | VPN-ACME-CORP | 99.99 | 15 | 50000 | GOLD |
| SLA-BIGBANK-SILVER | VPN-BIGBANK | 99.95 | 20 | 25000 | SILVER |
| SLA-OZMINE-GOLD | VPN-OZMINE | 99.99 | 18 | 40000 | GOLD |
| SLA-BB-SYD-STANDARD | BB-BUNDLE-SYD-NORTH | 99.5 | 50 | 0 | STANDARD |
| SLA-BB-BNE-STANDARD | BB-BUNDLE-BNE-CENTRAL | 99.5 | 50 | 0 | STANDARD |

---

## Relationships

### connects_to: TransportLink → CoreRouter

A transport link terminates at a core router. The TransportLink entity has `SourceRouterId` and `TargetRouterId` columns.

### aggregates_to: AggSwitch → CoreRouter

An aggregation switch uplinks to a core router.

### backhauls_via: BaseStation → AggSwitch

A base station backhauls through an aggregation switch.

### routes_via: MPLSPath → TransportLink

An MPLS path traverses a transport link. Backed by the FactMPLSPathHops junction table.

### depends_on: Service → MPLSPath / AggSwitch / BaseStation

A service depends on a network resource. EnterpriseVPN → MPLSPath, Broadband → AggSwitch, Mobile5G → BaseStation.

### governed_by: SLAPolicy → Service

An SLA policy governs a service.

### peers_over: BGPSession → CoreRouter

A BGP session peers between two core routers.
