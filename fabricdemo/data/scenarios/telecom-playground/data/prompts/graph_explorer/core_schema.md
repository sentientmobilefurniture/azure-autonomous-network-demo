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
| FirmwareVersion | String | Currently running firmware version. Used for Advisory correlation. | `IOS-XR-7.9.2` |

**All instances:**

| RouterId | City | Region | Vendor | Model | FirmwareVersion |
|---|---|---|---|---|---|
| CORE-SYD-01 | Sydney | NSW | Cisco | ASR-9922 | IOS-XR-7.9.2 |
| CORE-MEL-01 | Melbourne | VIC | Cisco | ASR-9922 | IOS-XR-7.9.2 |
| CORE-BNE-01 | Brisbane | QLD | Juniper | MX10008 | JUNOS-23.4R1 |

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

### routed_through: TransportLink → PhysicalConduit

A transport link is physically routed through a conduit/duct. MULTIPLE transport links can share the SAME conduit — this is how you detect shared-risk groups. Query pattern: "Which other links share the same conduit as LINK-X?" → Find LINK-X's conduit, then find all other links routed_through that conduit.

### amplifies: AmplifierSite → TransportLink

An optical amplifier site boosts the signal on a transport link. Long-haul links have multiple amplifier sites. If an amplifier degrades, optical power drops on that link segment. Query pattern: "Which amplifiers service LINK-SYD-MEL-FIBRE-01?" and "When was each last calibrated?"

### affects_version: Advisory → CoreRouter

A vendor advisory affects a router running a vulnerable firmware version. Pre-mapped from Advisory.AffectedVersions matching CoreRouter.FirmwareVersion. Query pattern: "Are any of our routers running firmware affected by known advisories?" and "Could the OSPF flaps on CORE-SYD-01 be caused by a known bug?"
