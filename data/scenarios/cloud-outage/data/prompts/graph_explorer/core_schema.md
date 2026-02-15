# Cloud Infrastructure Topology Ontology — Full Schema

## Entity Types

### Region (3 instances)

Top-level cloud regions.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **RegionId** | String | **Primary key.** | `REGION-US-EAST` |
| RegionName | String | Display name. | `US East` |
| Country | String | Country. | `United States` |
| Provider | String | Cloud provider. | `CloudCorp` |

**All instances:**

| RegionId | RegionName | Country | Provider |
|---|---|---|---|
| REGION-US-EAST | US East | United States | CloudCorp |
| REGION-US-WEST | US West | United States | CloudCorp |
| REGION-EU-WEST | EU West | Ireland | CloudCorp |

---

### AvailabilityZone (4 instances)

Isolated fault domains within a region.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **AZId** | String | **Primary key.** | `AZ-US-EAST-A` |
| AZName | String | Display name. | `US-East-AZ-A` |
| RegionId | String | Parent region (FK → Region.RegionId). | `REGION-US-EAST` |
| CoolingSystem | String | CRAC unit identifier. | `CRAC-UNIT-A1` |
| PowerFeedCount | Integer | Number of independent power feeds. | `2` |

**All instances:**

| AZId | AZName | RegionId | CoolingSystem | PowerFeedCount |
|---|---|---|---|---|
| AZ-US-EAST-A | US-East-AZ-A | REGION-US-EAST | CRAC-UNIT-A1 | 2 |
| AZ-US-EAST-B | US-East-AZ-B | REGION-US-EAST | CRAC-UNIT-B1 | 2 |
| AZ-US-WEST-A | US-West-AZ-A | REGION-US-WEST | CRAC-UNIT-A1 | 2 |
| AZ-EU-WEST-A | EU-West-AZ-A | REGION-EU-WEST | CRAC-UNIT-A1 | 2 |

---

### Rack (7 instances)

Server racks within availability zones.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **RackId** | String | **Primary key.** | `RACK-US-EAST-A-01` |
| RackPosition | String | Physical position. | `Row-1-Pos-1` |
| AZId | String | Parent AZ (FK → AvailabilityZone.AZId). | `AZ-US-EAST-A` |
| MaxPowerKW | Integer | Maximum power capacity in kW. | `20` |
| CoolingZone | String | Cooling zone within AZ. | `Zone-North` |

**All instances:**

| RackId | RackPosition | AZId | MaxPowerKW | CoolingZone |
|---|---|---|---|---|
| RACK-US-EAST-A-01 | Row-1-Pos-1 | AZ-US-EAST-A | 20 | Zone-North |
| RACK-US-EAST-A-02 | Row-1-Pos-2 | AZ-US-EAST-A | 20 | Zone-North |
| RACK-US-EAST-A-03 | Row-2-Pos-1 | AZ-US-EAST-A | 20 | Zone-South |
| RACK-US-EAST-B-01 | Row-1-Pos-1 | AZ-US-EAST-B | 20 | Zone-North |
| RACK-US-EAST-B-02 | Row-1-Pos-2 | AZ-US-EAST-B | 20 | Zone-South |
| RACK-US-WEST-A-01 | Row-1-Pos-1 | AZ-US-WEST-A | 20 | Zone-North |
| RACK-EU-WEST-A-01 | Row-1-Pos-1 | AZ-EU-WEST-A | 20 | Zone-North |

---

### Host (10 instances)

Physical servers within racks.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **HostId** | String | **Primary key.** | `HOST-USE-A-01-01` |
| Hostname | String | DNS hostname. | `nyc-host-01` |
| RackId | String | Parent rack (FK → Rack.RackId). | `RACK-US-EAST-A-01` |
| CPUCores | Integer | CPU core count. | `64` |
| MemoryGB | Integer | Memory in GB. | `256` |
| Vendor | String | Hardware vendor. | `Dell` |

**All instances:**

| HostId | Hostname | RackId | CPUCores | MemoryGB | Vendor |
|---|---|---|---|---|---|
| HOST-USE-A-01-01 | nyc-host-01 | RACK-US-EAST-A-01 | 64 | 256 | Dell |
| HOST-USE-A-01-02 | nyc-host-02 | RACK-US-EAST-A-01 | 64 | 256 | Dell |
| HOST-USE-A-02-01 | nyc-host-03 | RACK-US-EAST-A-02 | 128 | 512 | HPE |
| HOST-USE-A-02-02 | nyc-host-04 | RACK-US-EAST-A-02 | 128 | 512 | HPE |
| HOST-USE-A-03-01 | nyc-host-05 | RACK-US-EAST-A-03 | 64 | 256 | Dell |
| HOST-USE-B-01-01 | nyc-host-06 | RACK-US-EAST-B-01 | 64 | 256 | Dell |
| HOST-USE-B-01-02 | nyc-host-07 | RACK-US-EAST-B-01 | 128 | 512 | HPE |
| HOST-USE-B-02-01 | nyc-host-08 | RACK-US-EAST-B-02 | 64 | 256 | Dell |
| HOST-USW-A-01-01 | lax-host-01 | RACK-US-WEST-A-01 | 64 | 256 | Dell |
| HOST-EUW-A-01-01 | dub-host-01 | RACK-EU-WEST-A-01 | 64 | 256 | Lenovo |

---

### VirtualMachine (14 instances)

VMs running on physical hosts.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **VMId** | String | **Primary key.** | `VM-USE-A-0101-01` |
| VMName | String | VM display name. | `web-frontend-1` |
| HostId | String | Parent host (FK → Host.HostId). | `HOST-USE-A-01-01` |
| ServiceId | String | Service this VM serves (FK → Service.ServiceId). | `SVC-ECOMMERCE-WEB` |
| vCPUs | Integer | Virtual CPU count. | `4` |
| MemoryGB | Integer | Memory in GB. | `16` |
| OSType | String | Operating system. | `Linux` |

**All instances:**

| VMId | VMName | HostId | ServiceId | vCPUs | MemoryGB |
|---|---|---|---|---|---|
| VM-USE-A-0101-01 | web-frontend-1 | HOST-USE-A-01-01 | SVC-ECOMMERCE-WEB | 4 | 16 |
| VM-USE-A-0101-02 | web-frontend-2 | HOST-USE-A-01-01 | SVC-ECOMMERCE-WEB | 4 | 16 |
| VM-USE-A-0102-01 | api-gateway-1 | HOST-USE-A-01-02 | SVC-ECOMMERCE-API | 8 | 32 |
| VM-USE-A-0201-01 | db-primary | HOST-USE-A-02-01 | SVC-ECOMMERCE-DB | 16 | 128 |
| VM-USE-A-0202-01 | cache-node-1 | HOST-USE-A-02-02 | SVC-CACHE-CLUSTER | 8 | 64 |
| VM-USE-A-0202-02 | ml-trainer-1 | HOST-USE-A-02-02 | SVC-ML-PIPELINE | 32 | 256 |
| VM-USE-A-0301-01 | monitoring-1 | HOST-USE-A-03-01 | SVC-MONITORING | 4 | 16 |
| VM-USE-A-0301-02 | log-collector-1 | HOST-USE-A-03-01 | SVC-LOGGING | 4 | 16 |
| VM-USE-B-0101-01 | web-frontend-3 | HOST-USE-B-01-01 | SVC-ECOMMERCE-WEB | 4 | 16 |
| VM-USE-B-0101-02 | api-gateway-2 | HOST-USE-B-01-01 | SVC-ECOMMERCE-API | 8 | 32 |
| VM-USE-B-0102-01 | db-replica | HOST-USE-B-01-02 | SVC-ECOMMERCE-DB | 16 | 128 |
| VM-USE-B-0201-01 | cache-node-2 | HOST-USE-B-02-01 | SVC-CACHE-CLUSTER | 8 | 64 |
| VM-USW-A-0101-01 | cdn-edge-1 | HOST-USW-A-01-01 | SVC-CDN | 4 | 16 |
| VM-EUW-A-0101-01 | cdn-edge-2 | HOST-EUW-A-01-01 | SVC-CDN | 4 | 16 |

---

### LoadBalancer (4 instances)

Load balancers distributing traffic.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **LBId** | String | **Primary key.** | `LB-USE-WEB` |
| LBName | String | Display name. | `WebLB-USEast` |
| LBType | String | Type. Values: `Application`, `Network`, `DNS`. | `Application` |
| RegionId | String | Region (FK → Region.RegionId). | `REGION-US-EAST` |
| Algorithm | String | Load balancing algorithm. | `RoundRobin` |
| HealthCheckPath | String | Health check endpoint. | `/healthz` |

**All instances:**

| LBId | LBName | LBType | RegionId | Algorithm |
|---|---|---|---|---|
| LB-USE-WEB | WebLB-USEast | Application | REGION-US-EAST | RoundRobin |
| LB-USE-API | ApiLB-USEast | Application | REGION-US-EAST | LeastConn |
| LB-USE-DB | DbLB-USEast | Network | REGION-US-EAST | IPHash |
| LB-GLOBAL | GlobalLB | DNS | REGION-US-EAST | GeoRouting |

---

### Service (10 instances)

Applications and platform services.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **ServiceId** | String | **Primary key.** | `SVC-ECOMMERCE-WEB` |
| ServiceName | String | Display name. | `E-Commerce Web Frontend` |
| ServiceType | String | Category. Values: `WebApp`, `API`, `Database`, `Cache`, `Compute`, `CDN`, `Observability`, `Security`, `Financial`. | `WebApp` |
| Tier | String | Criticality tier. Values: `Tier-0`, `Tier-1`, `Tier-2`. | `Tier-1` |
| Owner | String | Team responsible. | `WebTeam` |

**All instances:**

| ServiceId | ServiceName | ServiceType | Tier | Owner |
|---|---|---|---|---|
| SVC-ECOMMERCE-WEB | E-Commerce Web Frontend | WebApp | Tier-1 | WebTeam |
| SVC-ECOMMERCE-API | E-Commerce API Gateway | API | Tier-1 | PlatformTeam |
| SVC-ECOMMERCE-DB | E-Commerce Database | Database | Tier-0 | DataTeam |
| SVC-CACHE-CLUSTER | Redis Cache Cluster | Cache | Tier-1 | PlatformTeam |
| SVC-ML-PIPELINE | ML Training Pipeline | Compute | Tier-2 | MLTeam |
| SVC-CDN | Content Delivery Network | CDN | Tier-1 | InfraTeam |
| SVC-MONITORING | Monitoring Stack | Observability | Tier-0 | SRETeam |
| SVC-LOGGING | Centralized Logging | Observability | Tier-0 | SRETeam |
| SVC-AUTH | Authentication Service | Security | Tier-0 | SecurityTeam |
| SVC-PAYMENT | Payment Processing | Financial | Tier-0 | PaymentTeam |

---

### SLAPolicy (5 instances)

SLA commitments governing services.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SLAId** | String | **Primary key.** | `SLA-ECOM-PLAT` |
| SLAName | String | Display name. | `E-Commerce Platform SLA` |
| ServiceId | String | Governed service (FK → Service.ServiceId). | `SVC-ECOMMERCE-WEB` |
| UptimePct | Double | Uptime commitment. | `99.99` |
| MaxLatencyMs | Integer | Max latency in ms. | `200` |
| RPOMinutes | Integer | Recovery point objective in minutes. | `5` |

**All instances:**

| SLAId | ServiceId | UptimePct | MaxLatencyMs | RPOMinutes |
|---|---|---|---|---|
| SLA-ECOM-PLAT | SVC-ECOMMERCE-WEB | 99.99 | 200 | 5 |
| SLA-ECOM-DB | SVC-ECOMMERCE-DB | 99.999 | 50 | 1 |
| SLA-PAYMENT | SVC-PAYMENT | 99.999 | 100 | 0 |
| SLA-CDN | SVC-CDN | 99.95 | 500 | 60 |
| SLA-ML | SVC-ML-PIPELINE | 99.9 | 5000 | 1440 |

---

## Relationships

### has_zone: Region → AvailabilityZone

A region contains availability zones.

### has_rack: AvailabilityZone → Rack

An availability zone contains racks.

### hosts_server: Rack → Host

A rack contains physical hosts.

### runs: Host → VirtualMachine

A host runs virtual machines.

### serves: VirtualMachine → Service

A VM serves a service.

### lb_in_region: LoadBalancer → Region

A load balancer is deployed in a region.

### governs: SLAPolicy → Service

An SLA policy governs a service.

### depends_on: Service → Service

A service depends on another service.

### depends_on: Service → LoadBalancer

A service depends on a load balancer.
