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
| Latitude | Double | GPS latitude (WGS84). | `-33.8688` |
| Longitude | Double | GPS longitude (WGS84). | `151.2093` |

**All instances:**

| RouterId | City | Region | Vendor | Model | FirmwareVersion | Latitude | Longitude |
|---|---|---|---|---|---|---|---|
| CORE-SYD-01 | Sydney | NSW | Cisco | ASR-9922 | IOS-XR-7.9.2 | -33.8688 | 151.2093 |
| CORE-MEL-01 | Melbourne | VIC | Cisco | ASR-9922 | IOS-XR-7.9.2 | -37.8136 | 144.9631 |
| CORE-BNE-01 | Brisbane | QLD | Juniper | MX10008 | JUNOS-23.4R1 | -27.4698 | 153.0251 |

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
| Latitude | Double | GPS latitude (WGS84). | `-33.7960` |
| Longitude | Double | GPS longitude (WGS84). | `151.1840` |

**All instances:**

| SwitchId | City | UplinkRouterId | Latitude | Longitude |
|---|---|---|---|---|
| AGG-SYD-NORTH-01 | Sydney | CORE-SYD-01 | -33.7960 | 151.1840 |
| AGG-SYD-SOUTH-01 | Sydney | CORE-SYD-01 | -33.9410 | 151.1730 |
| AGG-MEL-EAST-01 | Melbourne | CORE-MEL-01 | -37.8200 | 145.0650 |
| AGG-MEL-WEST-01 | Melbourne | CORE-MEL-01 | -37.8100 | 144.8850 |
| AGG-BNE-CENTRAL-01 | Brisbane | CORE-BNE-01 | -27.4700 | 153.0230 |
| AGG-BNE-SOUTH-01 | Brisbane | CORE-BNE-01 | -27.5540 | 153.0480 |

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
| Latitude | Double | GPS latitude (WGS84). | `-34.7546` |
| Longitude | Double | GPS longitude (WGS84). | `149.7186` |

**All instances:**

| SiteId | Location | InstalledYear | LastCalibration | Latitude | Longitude |
|---|---|---|---|---|---|
| AMP-SYD-MEL-GOULBURN | Goulburn NSW — 195km from Sydney | 2018 | 2025-09-15 | -34.7546 | 149.7186 |
| AMP-SYD-MEL-ALBURY | Albury NSW — 460km from Sydney | 2018 | 2025-06-20 | -36.0737 | 146.9135 |
| AMP-SYD-BNE-COFFS | Coffs Harbour NSW — 540km from Sydney | 2019 | 2025-11-01 | -30.2963 | 153.1157 |
| AMP-MEL-BNE-GRAFTON | Grafton NSW — 340km from Melbourne | 2020 | 2025-03-10 | -29.6900 | 152.9330 |

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

### Sensor (18 instances)

Physical sensors attached to infrastructure nodes. Each sensor has a specific type,
monitors a specific entity, and has GPS coordinates for field dispatch.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SensorId** | String | **Primary key.** | `SENS-SYD-MEL-F1-OPT-002` |
| SensorType | String | Measurement type: `OpticalPower`, `BitErrorRate`, `Temperature`, `CPULoad`, `Vibration`. | `OpticalPower` |
| MonitoredEntityId | String | FK to the infrastructure entity this sensor observes. | `LINK-SYD-MEL-FIBRE-01` |
| MonitoredEntityType | String | Type of the monitored entity: `TransportLink`, `CoreRouter`, `AmplifierSite`. | `TransportLink` |
| MountLocation | String | Human-readable where-to-find description. | `Splice point — Goulburn interchange` |
| Latitude | Double | GPS latitude (WGS84). | `-34.7546` |
| Longitude | Double | GPS longitude (WGS84). | `149.7186` |
| InstalledDate | String | Installation date. | `2018-06-15` |
| Status | String | `ACTIVE` or `INACTIVE`. | `ACTIVE` |

**All instances:**

| SensorId | SensorType | MonitoredEntityId | MonitoredEntityType | MountLocation | Lat/Long |
|---|---|---|---|---|---|
| SENS-SYD-MEL-F1-OPT-001 | OpticalPower | LINK-SYD-MEL-FIBRE-01 | TransportLink | Campbelltown splice | -34.065, 150.814 |
| SENS-SYD-MEL-F1-OPT-002 | OpticalPower | LINK-SYD-MEL-FIBRE-01 | TransportLink | Goulburn interchange | -34.755, 149.719 |
| SENS-SYD-MEL-F1-OPT-003 | OpticalPower | LINK-SYD-MEL-FIBRE-01 | TransportLink | North of Albury | -36.024, 146.912 |
| SENS-SYD-MEL-F1-BER-001 | BitErrorRate | LINK-SYD-MEL-FIBRE-01 | TransportLink | SYD head-end CORE-SYD-01 rack B3 | -33.869, 151.209 |
| SENS-SYD-MEL-F1-BER-002 | BitErrorRate | LINK-SYD-MEL-FIBRE-01 | TransportLink | MEL tail-end CORE-MEL-01 rack A7 | -37.814, 144.963 |
| SENS-SYD-MEL-F2-OPT-001 | OpticalPower | LINK-SYD-MEL-FIBRE-02 | TransportLink | Campbelltown splice (FIBRE-02) | -34.065, 150.814 |
| SENS-SYD-MEL-F2-OPT-002 | OpticalPower | LINK-SYD-MEL-FIBRE-02 | TransportLink | Goulburn interchange (shared conduit) | -34.755, 149.719 |
| SENS-SYD-BNE-F1-OPT-001 | OpticalPower | LINK-SYD-BNE-FIBRE-01 | TransportLink | Gosford (80km N of Sydney) | -33.425, 151.342 |
| SENS-SYD-BNE-F1-OPT-002 | OpticalPower | LINK-SYD-BNE-FIBRE-01 | TransportLink | Coffs Harbour (AMP-SYD-BNE-COFFS) | -30.296, 153.116 |
| SENS-MEL-BNE-F1-OPT-001 | OpticalPower | LINK-MEL-BNE-FIBRE-01 | TransportLink | Sale (120km E of Melbourne) | -38.100, 147.068 |
| SENS-MEL-BNE-F1-OPT-002 | OpticalPower | LINK-MEL-BNE-FIBRE-01 | TransportLink | Grafton (AMP-MEL-BNE-GRAFTON) | -29.690, 152.933 |
| SENS-CORE-SYD-01-TEMP-001 | Temperature | CORE-SYD-01 | CoreRouter | Main chassis exhaust vent | -33.869, 151.209 |
| SENS-CORE-SYD-01-CPU-001 | CPULoad | CORE-SYD-01 | CoreRouter | Control plane module | -33.869, 151.209 |
| SENS-CORE-MEL-01-TEMP-001 | Temperature | CORE-MEL-01 | CoreRouter | Main chassis exhaust vent | -37.814, 144.963 |
| SENS-CORE-MEL-01-CPU-001 | CPULoad | CORE-MEL-01 | CoreRouter | Control plane module | -37.814, 144.963 |
| SENS-CORE-BNE-01-TEMP-001 | Temperature | CORE-BNE-01 | CoreRouter | Main chassis exhaust vent | -27.470, 153.025 |
| SENS-AMP-GOULBURN-VIB-001 | Vibration | AMP-SYD-MEL-GOULBURN | AmplifierSite | Amplifier housing vibration monitor | -34.755, 149.719 |
| SENS-AMP-ALBURY-VIB-001 | Vibration | AMP-SYD-MEL-ALBURY | AmplifierSite | Amplifier housing vibration monitor | -36.074, 146.914 |

### Relationships
- `(Sensor)-[monitors]->(TransportLink|CoreRouter|AmplifierSite)` — which infrastructure this sensor observes

### Key query patterns
- "What sensors are on LINK-SYD-MEL-FIBRE-01?" → find all Sensor nodes with `monitors` edge to that link
- "Where is sensor SENS-SYD-MEL-F1-OPT-002 located?" → return Latitude, Longitude, MountLocation
- "What sensors are near Goulburn?" → filter by Latitude/Longitude proximity or MountLocation text

---

### DutyRoster (8 instances)

On-call field engineer assignments. Searchable by city/region and shift time (ShiftStart/ShiftEnd).
DutyRoster is a disconnected entity — no edges to other entities. It is a lookup table for field dispatch.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **RosterId** | String | **Primary key.** | `DUTY-SYD-2026-02-06-DAY` |
| PersonName | String | Full name of the engineer. | `Marcus Chen` |
| Email | String | Email address. | `marcus.chen@austtelco.com.au` |
| Phone | String | Phone number. | `+61-412-555-101` |
| City | String | Assignment city. | `Sydney` |
| Region | String | State/region. | `NSW` |
| ShiftStart | String | ISO8601 shift start time. | `2026-02-06T06:00:00Z` |
| ShiftEnd | String | ISO8601 shift end time. | `2026-02-06T18:00:00Z` |
| Role | String | `FieldEngineer` (city) or `RegionalFieldEngineer` (inter-city corridors). | `FieldEngineer` |
| HomeBase | String | Depot location with lat/long. | `Campbelltown Depot -34.0650 150.8140` |
| VehicleId | String | Assigned vehicle ID. | `VEH-SYD-03` |

**All instances:**

| RosterId | PersonName | City | Region | Role | ShiftStart | ShiftEnd |
|---|---|---|---|---|---|---|
| DUTY-SYD-2026-02-06-DAY | Marcus Chen | Sydney | NSW | FieldEngineer | 06:00 | 18:00 |
| DUTY-SYD-2026-02-06-NIGHT | Sarah O'Brien | Sydney | NSW | FieldEngineer | 18:00 | 06:00+1 |
| DUTY-MEL-2026-02-06-DAY | James Nguyen | Melbourne | VIC | FieldEngineer | 06:00 | 18:00 |
| DUTY-MEL-2026-02-06-NIGHT | Priya Sharma | Melbourne | VIC | FieldEngineer | 18:00 | 06:00+1 |
| DUTY-BNE-2026-02-06-DAY | Tom Williams | Brisbane | QLD | FieldEngineer | 06:00 | 18:00 |
| DUTY-REGIONAL-SYD-MEL-2026-02-06 | Dave Mitchell | Goulburn | NSW | RegionalFieldEngineer | 06:00 | 18:00 |
| DUTY-REGIONAL-SYD-MEL-2026-02-06-SOUTH | Karen Lee | Albury | NSW | RegionalFieldEngineer | 06:00 | 18:00 |
| DUTY-REGIONAL-SYD-BNE-2026-02-06 | Paul Jacobs | Coffs Harbour | NSW | RegionalFieldEngineer | 06:00 | 18:00 |

### Properties
- `Email`, `Phone` — contact details for dispatch
- `HomeBase` — depot location with lat/long for proximity matching
- `VehicleId` — assigned vehicle ID

### Key query patterns
- "Who is on duty in Goulburn region?" → filter by City or Region
- "What field engineers cover the SYD-MEL corridor?" → filter by Role == RegionalFieldEngineer and Region == NSW
- "Who is on duty at 14:31 on 2026-02-06?" → filter ShiftStart <= timestamp <= ShiftEnd

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

### depends_on_mplspath: Service → MPLSPath

An EnterpriseVPN service depends on an MPLS path.

### depends_on_aggswitch: Service → AggSwitch

A Broadband service depends on an aggregation switch.

### depends_on_basestation: Service → BaseStation

A Mobile5G service depends on a base station.

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

### monitors: Sensor → TransportLink | CoreRouter | AmplifierSite

A sensor physically monitors an infrastructure entity. The edge's target type depends on `MonitoredEntityType` in DimSensor.csv. Query pattern: "What sensors monitor LINK-SYD-MEL-FIBRE-01?" → find all Sensor nodes with `monitors` edge to that link. "Where is the closest sensor to the Goulburn amplifier?" → find Sensor nodes monitoring AMP-SYD-MEL-GOULBURN.
