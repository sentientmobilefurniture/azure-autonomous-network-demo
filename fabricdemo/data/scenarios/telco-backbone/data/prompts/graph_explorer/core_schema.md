# Network Topology Ontology — Full Schema

## Entity Types

### DataCenter (5 instances)

Physical datacenter facilities. Each city has one datacenter.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **DataCenterId** | String | **Primary key.** | `DC-SYD-01` |
| City | String | City where the datacenter is located. | `Sydney` |
| Region | String | State / region. | `NSW` |
| Tier | String | Datacenter tier classification. Values: `Tier3`, `Tier4`. | `Tier4` |
| PowerRedundancy | String | Power redundancy level. Values: `N+1`, `2N`. | `2N` |

**All instances:**

| DataCenterId | City | Region | Tier | PowerRedundancy |
|---|---|---|---|---|
| DC-SYD-01 | Sydney | NSW | Tier4 | 2N |
| DC-MEL-01 | Melbourne | VIC | Tier4 | 2N |
| DC-ADL-01 | Adelaide | SA | Tier3 | N+1 |
| DC-PER-01 | Perth | WA | Tier3 | N+1 |
| DC-CBR-01 | Canberra | ACT | Tier4 | 2N |

---

### CoreRouter (5 instances)

Backbone routers at city level. Each city has one core router, housed in a datacenter.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **RouterId** | String | **Primary key.** | `CORE-SYD-01` |
| City | String | City where the router is located. | `Sydney` |
| Region | String | State / region. | `NSW` |
| Vendor | String | Equipment manufacturer. | `Cisco` |
| Model | String | Hardware model. | `ASR-9922` |
| DataCenterId | String | Hosting datacenter (FK → DataCenter.DataCenterId). | `DC-SYD-01` |

**All instances:**

| RouterId | City | Region | Vendor | Model | DataCenterId |
|---|---|---|---|---|---|
| CORE-SYD-01 | Sydney | NSW | Cisco | ASR-9922 | DC-SYD-01 |
| CORE-MEL-01 | Melbourne | VIC | Cisco | ASR-9922 | DC-MEL-01 |
| CORE-ADL-01 | Adelaide | SA | Juniper | MX10008 | DC-ADL-01 |
| CORE-PER-01 | Perth | WA | Juniper | MX10008 | DC-PER-01 |
| CORE-CBR-01 | Canberra | ACT | Nokia | 7750-SR14 | DC-CBR-01 |

---

### TransportLink (14 instances)

Physical transport links. 6 are inter-city backbone links, 8 are local aggregation uplinks.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **LinkId** | String | **Primary key.** | `LINK-SYD-MEL-FIBRE-01` |
| LinkType | String | Technology type. Values: `DWDM_100G`, `SUBMARINE_40G`, `MICROWAVE_10G`, `100GE`. | `DWDM_100G` |
| CapacityGbps | Integer | Link capacity in Gbps. | `100` |
| SourceRouterId | String | Source router (FK → CoreRouter.RouterId). | `CORE-SYD-01` |
| TargetRouterId | String | Target router (FK → CoreRouter.RouterId). | `CORE-MEL-01` |

**Inter-city backbone links:**

| LinkId | LinkType | CapacityGbps | SourceRouterId | TargetRouterId | Notes |
|---|---|---|---|---|---|
| LINK-SYD-MEL-FIBRE-01 | DWDM_100G | 100 | CORE-SYD-01 | CORE-MEL-01 | SYD↔MEL terrestrial |
| LINK-MEL-ADL-FIBRE-01 | DWDM_100G | 100 | CORE-MEL-01 | CORE-ADL-01 | MEL↔ADL terrestrial |
| LINK-ADL-PER-SUBMARINE-01 | SUBMARINE_40G | 40 | CORE-ADL-01 | CORE-PER-01 | Primary ADL↔PER — submarine cable (gets cut) |
| LINK-ADL-PER-MICROWAVE-01 | MICROWAVE_10G | 10 | CORE-ADL-01 | CORE-PER-01 | Backup ADL↔PER — microwave (low capacity) |
| LINK-SYD-CBR-FIBRE-01 | DWDM_100G | 100 | CORE-SYD-01 | CORE-CBR-01 | SYD↔CBR terrestrial |
| LINK-SYD-ADL-FIBRE-01 | DWDM_100G | 100 | CORE-SYD-01 | CORE-ADL-01 | Inland alternate SYD↔ADL |

**Aggregation uplinks (100GE):** LINK-SYD-AGG-NORTH-01, LINK-SYD-AGG-SOUTH-01, LINK-MEL-AGG-EAST-01, LINK-MEL-AGG-WEST-01, LINK-ADL-AGG-NORTH-01, LINK-ADL-AGG-SOUTH-01, LINK-PER-AGG-CENTRAL-01, LINK-CBR-AGG-CENTRAL-01. Each connects a core router to itself (local uplink).

---

### FirewallCluster (5 instances)

Network security clusters providing deep packet inspection and policy enforcement.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **FirewallId** | String | **Primary key.** | `FW-SYD-01` |
| City | String | City. | `Sydney` |
| Vendor | String | Equipment manufacturer. | `Palo Alto` |
| Model | String | Hardware model. | `PA-7080` |
| DataCenterId | String | Hosting datacenter (FK → DataCenter.DataCenterId). | `DC-SYD-01` |

**All instances:**

| FirewallId | City | Vendor | Model | DataCenterId |
|---|---|---|---|---|
| FW-SYD-01 | Sydney | Palo Alto | PA-7080 | DC-SYD-01 |
| FW-MEL-01 | Melbourne | Palo Alto | PA-7080 | DC-MEL-01 |
| FW-ADL-01 | Adelaide | Fortinet | FG-3700F | DC-ADL-01 |
| FW-PER-01 | Perth | Fortinet | FG-3700F | DC-PER-01 |
| FW-CBR-01 | Canberra | Palo Alto | PA-7080 | DC-CBR-01 |

---

### AggSwitch (8 instances)

Aggregation switches between core routers and base stations.

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
| AGG-ADL-NORTH-01 | Adelaide | CORE-ADL-01 |
| AGG-ADL-SOUTH-01 | Adelaide | CORE-ADL-01 |
| AGG-PER-CENTRAL-01 | Perth | CORE-PER-01 |
| AGG-CBR-CENTRAL-01 | Canberra | CORE-CBR-01 |

---

### BaseStation (10 instances)

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
| GNB-MEL-3012 | AGG-MEL-WEST-01 | Melbourne |
| GNB-ADL-5011 | AGG-ADL-NORTH-01 | Adelaide |
| GNB-ADL-5012 | AGG-ADL-SOUTH-01 | Adelaide |
| GNB-PER-6011 | AGG-PER-CENTRAL-01 | Perth |
| GNB-PER-6012 | AGG-PER-CENTRAL-01 | Perth |
| GNB-CBR-7011 | AGG-CBR-CENTRAL-01 | Canberra |

---

### BGPSession (5 instances)

BGP peering sessions between core routers.

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
| BGP-MEL-ADL-01 | CORE-MEL-01 | CORE-ADL-01 | 64513 | 64514 |
| BGP-ADL-PER-01 | CORE-ADL-01 | CORE-PER-01 | 64514 | 64515 |
| BGP-SYD-CBR-01 | CORE-SYD-01 | CORE-CBR-01 | 64512 | 64516 |
| BGP-SYD-ADL-01 | CORE-SYD-01 | CORE-ADL-01 | 64512 | 64514 |

---

### MPLSPath (8 instances)

MPLS label-switched paths carrying service traffic between cities.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **PathId** | String | **Primary key.** | `MPLS-PATH-ADL-PER-PRIMARY` |
| PathType | String | Redundancy tier. Values: `PRIMARY`, `SECONDARY`, `TERTIARY`. | `PRIMARY` |

**All instances:**

| PathId | PathType | What it traverses |
|---|---|---|
| MPLS-PATH-ADL-PER-PRIMARY | PRIMARY | CORE-ADL-01 → LINK-ADL-PER-SUBMARINE-01 → CORE-PER-01 |
| MPLS-PATH-ADL-PER-SECONDARY | SECONDARY | CORE-ADL-01 → LINK-ADL-PER-MICROWAVE-01 → CORE-PER-01 |
| MPLS-PATH-SYD-MEL-PRIMARY | PRIMARY | CORE-SYD-01 → LINK-SYD-MEL-FIBRE-01 → CORE-MEL-01 |
| MPLS-PATH-MEL-ADL-PRIMARY | PRIMARY | CORE-MEL-01 → LINK-MEL-ADL-FIBRE-01 → CORE-ADL-01 |
| MPLS-PATH-SYD-CBR-PRIMARY | PRIMARY | CORE-SYD-01 → LINK-SYD-CBR-FIBRE-01 → CORE-CBR-01 |
| MPLS-PATH-SYD-ADL-PRIMARY | PRIMARY | CORE-SYD-01 → LINK-SYD-ADL-FIBRE-01 → CORE-ADL-01 |
| MPLS-PATH-SYD-PER-VIA-MEL-ADL | TERTIARY | CORE-SYD-01 → LINK-SYD-MEL-FIBRE-01 → CORE-MEL-01 → LINK-MEL-ADL-FIBRE-01 → CORE-ADL-01 → LINK-ADL-PER-SUBMARINE-01 → CORE-PER-01 |
| MPLS-PATH-SYD-PER-VIA-ADL | TERTIARY | CORE-SYD-01 → LINK-SYD-ADL-FIBRE-01 → CORE-ADL-01 → LINK-ADL-PER-SUBMARINE-01 → CORE-PER-01 |

---

### Service (14 instances)

Customer-facing services. Four types: EnterpriseVPN, GovernmentVPN, Broadband, Mobile5G.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **ServiceId** | String | **Primary key.** | `VPN-IRONORE-CORP` |
| ServiceType | String | Category. Values: `EnterpriseVPN`, `GovernmentVPN`, `Broadband`, `Mobile5G`. | `EnterpriseVPN` |
| CustomerName | String | Customer or subscriber group name. | `IronOre Mining Ltd` |
| CustomerCount | Integer | Number of customers served. | `1` |
| ActiveUsers | Integer | Current active user count. | `2200` |

**All instances:**

| ServiceId | ServiceType | CustomerName | ActiveUsers |
|---|---|---|---|
| VPN-IRONORE-CORP | EnterpriseVPN | IronOre Mining Ltd | 2200 |
| VPN-WESTGAS-CORP | EnterpriseVPN | WestGas Energy | 850 |
| VPN-GOVDEFENCE | GovernmentVPN | Department of Defence | 3400 |
| VPN-FINSERV-CORP | EnterpriseVPN | FinServ Holdings | 1500 |
| VPN-UNILINK | EnterpriseVPN | UniLink Education | 4200 |
| BB-BUNDLE-SYD-NORTH | Broadband | Residential - Sydney North | 3200 |
| BB-BUNDLE-MEL-EAST | Broadband | Residential - Melbourne East | 2800 |
| BB-BUNDLE-ADL-SOUTH | Broadband | Residential - Adelaide South | 1800 |
| BB-BUNDLE-PER-CENTRAL | Broadband | Residential - Perth Central | 2100 |
| MOB-5G-SYD-2041 | Mobile5G | Mobile Subscribers - SYD 2041 | 4200 |
| MOB-5G-MEL-3011 | Mobile5G | Mobile Subscribers - MEL 3011 | 3800 |
| MOB-5G-ADL-5011 | Mobile5G | Mobile Subscribers - ADL 5011 | 2600 |
| MOB-5G-PER-6011 | Mobile5G | Mobile Subscribers - PER 6011 | 3100 |
| MOB-5G-CBR-7011 | Mobile5G | Mobile Subscribers - CBR 7011 | 1900 |

---

### SLAPolicy (7 instances)

SLA commitments governing services. Not all services have an SLA policy.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SLAPolicyId** | String | **Primary key.** | `SLA-IRONORE-GOLD` |
| ServiceId | String | The governed service (FK → Service.ServiceId). | `VPN-IRONORE-CORP` |
| AvailabilityPct | Double | Uptime commitment percentage. | `99.99` |
| MaxLatencyMs | Integer | Maximum allowed latency in milliseconds. | `25` |
| PenaltyPerHourUSD | Integer | Financial penalty per hour of breach in USD. | `75000` |
| Tier | String | SLA tier. Values: `PLATINUM`, `GOLD`, `SILVER`, `STANDARD`. | `GOLD` |

**All instances:**

| SLAPolicyId | ServiceId | AvailabilityPct | MaxLatencyMs | PenaltyPerHourUSD | Tier |
|---|---|---|---|---|---|
| SLA-IRONORE-GOLD | VPN-IRONORE-CORP | 99.99 | 25 | 75000 | GOLD |
| SLA-WESTGAS-GOLD | VPN-WESTGAS-CORP | 99.99 | 30 | 60000 | GOLD |
| SLA-GOVDEFENCE-PLATINUM | VPN-GOVDEFENCE | 99.999 | 10 | 150000 | PLATINUM |
| SLA-FINSERV-SILVER | VPN-FINSERV-CORP | 99.95 | 15 | 35000 | SILVER |
| SLA-UNILINK-SILVER | VPN-UNILINK | 99.95 | 20 | 20000 | SILVER |
| SLA-BB-PER-STANDARD | BB-BUNDLE-PER-CENTRAL | 99.5 | 50 | 0 | STANDARD |
| SLA-BB-ADL-STANDARD | BB-BUNDLE-ADL-SOUTH | 99.5 | 50 | 0 | STANDARD |

---

## Relationships

### housed_in: CoreRouter → DataCenter

A core router is physically housed in a datacenter.

### located_at: FirewallCluster → DataCenter

A firewall cluster is located at a datacenter.

### connects_to: TransportLink → CoreRouter

A transport link terminates at a core router. The TransportLink entity has `SourceRouterId` and `TargetRouterId` columns.

### aggregates_to: AggSwitch → CoreRouter

An aggregation switch uplinks to a core router.

### backhauls_via: BaseStation → AggSwitch

A base station backhauls through an aggregation switch.

### routes_via: MPLSPath → TransportLink

An MPLS path traverses a transport link. Backed by the FactMPLSPathHops junction table.

### traverses: MPLSPath → CoreRouter

An MPLS path passes through a core router. Backed by the FactMPLSPathHops junction table.

### depends_on: Service → MPLSPath / AggSwitch / BaseStation

A service depends on a network resource. VPN → MPLSPath, Broadband → AggSwitch, Mobile5G → BaseStation.

### protects: FirewallCluster → Service

A firewall cluster protects a service. Backed by the FactFirewallProtects junction table with PolicyType.

### governed_by: SLAPolicy → Service

An SLA policy governs a service.

### peers_over: BGPSession → CoreRouter

A BGP session peers between two core routers.
