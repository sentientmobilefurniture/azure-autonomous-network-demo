# Complete Examples

Full annotated code from the **telco-noc** canonical reference scenario. Use
these as templates when creating a new scenario. Each script is production-tested
and lives in `data/scenarios/telco-noc/scripts/`.

## Topology Generator — `generate_topology.py`

Complete script showing all 8 entity types with inline hardcoded data:

```python
"""
Generate static topology CSV files for network entity tables.

Outputs 8 CSV files:
  - DimCoreRouter.csv
  - DimTransportLink.csv
  - DimAggSwitch.csv
  - DimBaseStation.csv
  - DimBGPSession.csv
  - DimMPLSPath.csv
  - DimService.csv
  - DimSLAPolicy.csv
"""

import csv
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "entities")


def write_csv(filename: str, headers: list[str], rows: list[list]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"  ✓ {filename} ({len(rows)} rows)")


def generate_core_routers() -> None:
    headers = ["RouterId", "City", "Region", "Vendor", "Model"]
    rows = [
        ["CORE-SYD-01", "Sydney", "NSW", "Cisco", "ASR-9922"],
        ["CORE-MEL-01", "Melbourne", "VIC", "Cisco", "ASR-9922"],
        ["CORE-BNE-01", "Brisbane", "QLD", "Juniper", "MX10008"],
    ]
    write_csv("DimCoreRouter.csv", headers, rows)


def generate_transport_links() -> None:
    headers = ["LinkId", "LinkType", "CapacityGbps", "SourceRouterId", "TargetRouterId"]
    rows = [
        ["LINK-SYD-MEL-FIBRE-01", "DWDM_100G", 100, "CORE-SYD-01", "CORE-MEL-01"],
        ["LINK-SYD-MEL-FIBRE-02", "DWDM_100G", 100, "CORE-SYD-01", "CORE-MEL-01"],
        ["LINK-SYD-BNE-FIBRE-01", "DWDM_100G", 100, "CORE-SYD-01", "CORE-BNE-01"],
        ["LINK-MEL-BNE-FIBRE-01", "DWDM_100G", 100, "CORE-MEL-01", "CORE-BNE-01"],
        ["LINK-SYD-AGG-NORTH-01", "100GE", 100, "CORE-SYD-01", "CORE-SYD-01"],
        ["LINK-SYD-AGG-SOUTH-01", "100GE", 100, "CORE-SYD-01", "CORE-SYD-01"],
        ["LINK-MEL-AGG-EAST-01", "100GE", 100, "CORE-MEL-01", "CORE-MEL-01"],
        ["LINK-MEL-AGG-WEST-01", "100GE", 100, "CORE-MEL-01", "CORE-MEL-01"],
        ["LINK-BNE-AGG-CENTRAL-01", "100GE", 100, "CORE-BNE-01", "CORE-BNE-01"],
        ["LINK-BNE-AGG-SOUTH-01", "100GE", 100, "CORE-BNE-01", "CORE-BNE-01"],
    ]
    write_csv("DimTransportLink.csv", headers, rows)


def generate_agg_switches() -> None:
    headers = ["SwitchId", "City", "UplinkRouterId"]
    rows = [
        ["AGG-SYD-NORTH-01", "Sydney", "CORE-SYD-01"],
        ["AGG-SYD-SOUTH-01", "Sydney", "CORE-SYD-01"],
        ["AGG-MEL-EAST-01", "Melbourne", "CORE-MEL-01"],
        ["AGG-MEL-WEST-01", "Melbourne", "CORE-MEL-01"],
        ["AGG-BNE-CENTRAL-01", "Brisbane", "CORE-BNE-01"],
        ["AGG-BNE-SOUTH-01", "Brisbane", "CORE-BNE-01"],
    ]
    write_csv("DimAggSwitch.csv", headers, rows)


def generate_base_stations() -> None:
    headers = ["StationId", "StationType", "AggSwitchId", "City"]
    rows = [
        ["GNB-SYD-2041", "5G_NR", "AGG-SYD-NORTH-01", "Sydney"],
        ["GNB-SYD-2042", "5G_NR", "AGG-SYD-NORTH-01", "Sydney"],
        ["GNB-SYD-2043", "5G_NR", "AGG-SYD-SOUTH-01", "Sydney"],
        ["GNB-MEL-3011", "5G_NR", "AGG-MEL-EAST-01", "Melbourne"],
        ["GNB-MEL-3012", "5G_NR", "AGG-MEL-EAST-01", "Melbourne"],
        ["GNB-MEL-3021", "5G_NR", "AGG-MEL-WEST-01", "Melbourne"],
        ["GNB-BNE-4011", "5G_NR", "AGG-BNE-CENTRAL-01", "Brisbane"],
        ["GNB-BNE-4012", "5G_NR", "AGG-BNE-SOUTH-01", "Brisbane"],
    ]
    write_csv("DimBaseStation.csv", headers, rows)


def generate_bgp_sessions() -> None:
    headers = ["SessionId", "PeerARouterId", "PeerBRouterId", "ASNumberA", "ASNumberB"]
    rows = [
        ["BGP-SYD-MEL-01", "CORE-SYD-01", "CORE-MEL-01", 64512, 64513],
        ["BGP-SYD-BNE-01", "CORE-SYD-01", "CORE-BNE-01", 64512, 64514],
        ["BGP-MEL-BNE-01", "CORE-MEL-01", "CORE-BNE-01", 64513, 64514],
    ]
    write_csv("DimBGPSession.csv", headers, rows)


def generate_mpls_paths() -> None:
    headers = ["PathId", "PathType"]
    rows = [
        ["MPLS-PATH-SYD-MEL-PRIMARY", "PRIMARY"],
        ["MPLS-PATH-SYD-MEL-SECONDARY", "SECONDARY"],
        ["MPLS-PATH-SYD-BNE-PRIMARY", "PRIMARY"],
        ["MPLS-PATH-MEL-BNE-PRIMARY", "PRIMARY"],
        ["MPLS-PATH-SYD-MEL-VIA-BNE", "TERTIARY"],
    ]
    write_csv("DimMPLSPath.csv", headers, rows)


def generate_services() -> None:
    headers = ["ServiceId", "ServiceType", "CustomerName", "CustomerCount", "ActiveUsers"]
    rows = [
        ["VPN-ACME-CORP", "EnterpriseVPN", "ACME Corporation", 1, 450],
        ["VPN-BIGBANK", "EnterpriseVPN", "BigBank Financial", 1, 1200],
        ["VPN-OZMINE", "EnterpriseVPN", "OzMine Resources", 1, 680],
        ["BB-BUNDLE-SYD-NORTH", "Broadband", "Residential - Sydney North", 3200, 3200],
        ["BB-BUNDLE-MEL-EAST", "Broadband", "Residential - Melbourne East", 2800, 2800],
        ["BB-BUNDLE-BNE-CENTRAL", "Broadband", "Residential - Brisbane Central", 2400, 2400],
        ["MOB-5G-SYD-2041", "Mobile5G", "Mobile Subscribers - SYD 2041", 4200, 4200],
        ["MOB-5G-SYD-2042", "Mobile5G", "Mobile Subscribers - SYD 2042", 4300, 4300],
        ["MOB-5G-MEL-3011", "Mobile5G", "Mobile Subscribers - MEL 3011", 3800, 3800],
        ["MOB-5G-BNE-4011", "Mobile5G", "Mobile Subscribers - BNE 4011", 3600, 3600],
    ]
    write_csv("DimService.csv", headers, rows)


def generate_sla_policies() -> None:
    headers = ["SLAPolicyId", "ServiceId", "AvailabilityPct", "MaxLatencyMs", "PenaltyPerHourUSD", "Tier"]
    rows = [
        ["SLA-ACME-GOLD", "VPN-ACME-CORP", 99.99, 15, 50000, "GOLD"],
        ["SLA-BIGBANK-SILVER", "VPN-BIGBANK", 99.95, 20, 25000, "SILVER"],
        ["SLA-OZMINE-GOLD", "VPN-OZMINE", 99.99, 18, 40000, "GOLD"],
        ["SLA-BB-SYD-STANDARD", "BB-BUNDLE-SYD-NORTH", 99.5, 50, 0, "STANDARD"],
        ["SLA-BB-BNE-STANDARD", "BB-BUNDLE-BNE-CENTRAL", 99.5, 50, 0, "STANDARD"],
    ]
    write_csv("DimSLAPolicy.csv", headers, rows)


def main() -> None:
    print("Generating topology data (network entity tables)...")
    generate_core_routers()
    generate_transport_links()
    generate_agg_switches()
    generate_base_stations()
    generate_bgp_sessions()
    generate_mpls_paths()
    generate_services()
    generate_sla_policies()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
```

**Key patterns to note:**
- `write_csv()` helper is reused across all generators
- `OUTPUT_DIR` resolves relative to the script location
- Entity IDs encode hierarchy: `CORE-SYD-01`, `AGG-SYD-NORTH-01`, `GNB-SYD-2041`
- FK columns reference parent IDs: `UplinkRouterId → RouterId`, `AggSwitchId → SwitchId`
- Functions called in dependency order (parents before children)

## Routing Generator — `generate_routing.py`

Complete script showing both junction table patterns:

```python
"""
Generate relationship / junction table CSV files for network data.

Outputs 2 CSV files:
  - FactMPLSPathHops.csv   (MPLSPath --ROUTES_VIA--> nodes)
  - FactServiceDependency.csv  (Service --DEPENDS_ON--> resources)
"""

import csv
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "entities")


def write_csv(filename: str, headers: list[str], rows: list[list]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"  ✓ {filename} ({len(rows)} rows)")


def generate_mpls_path_hops() -> None:
    """Each MPLS path traverses a sequence of routers and transport links."""
    headers = ["PathId", "HopOrder", "NodeId", "NodeType"]
    rows = [
        # SYD-MEL Primary: SYD router → fibre 01 → MEL router
        ["MPLS-PATH-SYD-MEL-PRIMARY", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-MEL-PRIMARY", 2, "LINK-SYD-MEL-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-MEL-PRIMARY", 3, "CORE-MEL-01", "CoreRouter"],
        # SYD-MEL Secondary: SYD router → fibre 02 → MEL router
        ["MPLS-PATH-SYD-MEL-SECONDARY", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-MEL-SECONDARY", 2, "LINK-SYD-MEL-FIBRE-02", "TransportLink"],
        ["MPLS-PATH-SYD-MEL-SECONDARY", 3, "CORE-MEL-01", "CoreRouter"],
        # SYD-BNE Primary: SYD router → fibre → BNE router
        ["MPLS-PATH-SYD-BNE-PRIMARY", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-BNE-PRIMARY", 2, "LINK-SYD-BNE-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-BNE-PRIMARY", 3, "CORE-BNE-01", "CoreRouter"],
        # MEL-BNE Primary: MEL router → fibre → BNE router
        ["MPLS-PATH-MEL-BNE-PRIMARY", 1, "CORE-MEL-01", "CoreRouter"],
        ["MPLS-PATH-MEL-BNE-PRIMARY", 2, "LINK-MEL-BNE-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-MEL-BNE-PRIMARY", 3, "CORE-BNE-01", "CoreRouter"],
        # SYD-MEL via BNE (indirect): SYD → SYD-BNE fibre → BNE → MEL-BNE fibre → MEL
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 2, "LINK-SYD-BNE-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 3, "CORE-BNE-01", "CoreRouter"],
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 4, "LINK-MEL-BNE-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 5, "CORE-MEL-01", "CoreRouter"],
    ]
    write_csv("FactMPLSPathHops.csv", headers, rows)


def generate_service_dependencies() -> None:
    """Service-to-resource dependency mappings."""
    headers = ["ServiceId", "DependsOnId", "DependsOnType", "DependencyStrength"]
    rows = [
        # Enterprise VPNs depend on MPLS paths
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-SECONDARY", "MPLSPath", "SECONDARY"],
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-VIA-BNE", "MPLSPath", "TERTIARY"],
        ["VPN-BIGBANK", "MPLS-PATH-SYD-MEL-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-BIGBANK", "MPLS-PATH-SYD-MEL-SECONDARY", "MPLSPath", "SECONDARY"],
        ["VPN-BIGBANK", "MPLS-PATH-SYD-MEL-VIA-BNE", "MPLSPath", "TERTIARY"],
        # OzMine VPN depends on SYD-BNE MPLS path
        ["VPN-OZMINE", "MPLS-PATH-SYD-BNE-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-OZMINE", "MPLS-PATH-SYD-MEL-VIA-BNE", "MPLSPath", "SECONDARY"],
        # Broadband bundles depend on aggregation switches
        ["BB-BUNDLE-SYD-NORTH", "AGG-SYD-NORTH-01", "AggSwitch", "PRIMARY"],
        ["BB-BUNDLE-MEL-EAST", "AGG-MEL-EAST-01", "AggSwitch", "PRIMARY"],
        ["BB-BUNDLE-BNE-CENTRAL", "AGG-BNE-CENTRAL-01", "AggSwitch", "PRIMARY"],
        # Mobile services depend on base stations
        ["MOB-5G-SYD-2041", "GNB-SYD-2041", "BaseStation", "PRIMARY"],
        ["MOB-5G-SYD-2042", "GNB-SYD-2042", "BaseStation", "PRIMARY"],
        ["MOB-5G-MEL-3011", "GNB-MEL-3011", "BaseStation", "PRIMARY"],
        ["MOB-5G-BNE-4011", "GNB-BNE-4011", "BaseStation", "PRIMARY"],
    ]
    write_csv("FactServiceDependency.csv", headers, rows)


def main() -> None:
    print("Generating routing data (network junction tables)...")
    generate_mpls_path_hops()
    generate_service_dependencies()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
```

**Key patterns to note:**
- **Path hops**: `NodeType` column enables `filter` clauses in `graph_schema.yaml`
  (only `TransportLink` hops create `routes_via` edges)
- **Dependencies**: `DependsOnType` column creates different edge targets via filter
  (`MPLSPath`, `AggSwitch`, `BaseStation`)
- Every ID references an existing entity from topology CSVs

## Telemetry Generator — `generate_telemetry.py` (Key Sections)

The telemetry generator is the most complex script (~410 lines). Here are the
critical structural sections annotated:

### Header & Constants

```python
"""
Generate alert stream and link telemetry CSV files for Cosmos DB NoSQL.
Outputs 2 CSV files:
  - AlertStream.csv     (~5,000 rows) — 54h baseline + cascading alert storm
  - LinkTelemetry.csv   (~8,600 rows) — 72h baseline + incident link metrics
"""
import csv, os, random
from datetime import datetime, timedelta, timezone

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "telemetry")
INCIDENT_START = datetime(2026, 2, 6, 14, 30, 0, tzinfo=timezone.utc)
random.seed(42)

# ── Topology references (MUST match entity CSVs exactly) ──────────────────
CORE_ROUTERS = ["CORE-SYD-01", "CORE-MEL-01", "CORE-BNE-01"]
AGG_SWITCHES = ["AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01", ...]
BASE_STATIONS = ["GNB-SYD-2041", "GNB-SYD-2042", ...]
TRANSPORT_LINKS = ["LINK-SYD-MEL-FIBRE-01", "LINK-SYD-MEL-FIBRE-02", ...]
SERVICES = ["VPN-ACME-CORP", "VPN-BIGBANK", ...]

# Impacted nodes (downstream of the fibre cut)
IMPACTED_SYD_ROUTERS = ["CORE-SYD-01", "CORE-MEL-01"]
IMPACTED_AGG = ["AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01", "AGG-MEL-EAST-01", "AGG-MEL-WEST-01"]
IMPACTED_GNB = ["GNB-SYD-2041", "GNB-SYD-2042", ...]
IMPACTED_SERVICES = ["VPN-ACME-CORP", "VPN-BIGBANK", ...]
REROUTE_LINKS = ["LINK-SYD-BNE-FIBRE-01", "LINK-MEL-BNE-FIBRE-01"]
```

### The No-Null Pattern

```python
def normal_optical() -> float: return round(random.uniform(-3.5, -2.5), 1)
def normal_ber() -> float: return round(random.uniform(1e-14, 1e-11), 15)
def normal_cpu() -> float: return round(random.uniform(15, 45), 1)
def normal_pkt_loss() -> float: return round(random.uniform(0.0, 0.05), 3)

def baseline_snapshot() -> dict:
    return {"optical": normal_optical(), "ber": normal_ber(),
            "cpu": normal_cpu(), "pkt_loss": normal_pkt_loss()}

def add(offset, node_id, node_type, alert_type, severity, desc,
        optical=None, ber=None, cpu=None, pkt_loss=None):
    snap = baseline_snapshot()
    alerts.append([
        f"ALT-20260206-{counter:06d}", ts(offset), node_id, node_type,
        alert_type, severity, desc,
        optical if optical is not None else snap["optical"],  # ← NEVER null
        ber if ber is not None else snap["ber"],
        cpu if cpu is not None else snap["cpu"],
        pkt_loss if pkt_loss is not None else snap["pkt_loss"],
    ])
```

### Baseline Generation

```python
# 54h of low-severity background noise (~3000 alerts, ~1/min)
baseline_alerts_by_type = {
    "CoreRouter": [
        ("HIGH_CPU", "WARNING", "CPU utilization {cpu}% — routine process spike"),
        ("PACKET_LOSS_THRESHOLD", "MINOR", "Packet loss {pkt}% — transient microloop"),
    ],
    "AggSwitch": [...],
    "BaseStation": [...],
    "TransportLink": [...],
}
for _ in range(random.randint(2800, 3400)):
    offset = random.uniform(-54 * 3600, -60)
    node, node_type = random.choice(baseline_nodes)
    add(offset, node, node_type, ...)
```

### Cascade Timeline

```python
# T+0s:  Root cause — fibre cut (1 alert)
add(0.0, "LINK-SYD-MEL-FIBRE-01", "TransportLink", "LINK_DOWN",
    "CRITICAL", "Physical link loss of light detected",
    optical=-40.0, ber=1.0, pkt_loss=100.0)

# T+2s:  BGP peer loss (2 alerts)
# T+5s:  OSPF adjacency drops (4 alerts)
# T+10s: Route withdrawals (~20 alerts)
# T+15s: HIGH_CPU reconvergence (~50 alerts)
# T+30s: Packet loss downstream (~200 alerts)
# T+60s: Service degradation (~500 alerts)
# T+70-90s: Duplicate/flapping (fills to ~2000)

alerts.sort(key=lambda r: r[1])  # Sort by timestamp
```

### Per-Component Telemetry (LinkTelemetry.csv)

```python
def generate_link_telemetry():
    # 72h of 5-min samples (60h before + 12h after incident)
    baseline_profiles = {
        "LINK-SYD-MEL-FIBRE-01": {"util": 55.0, "latency": (4, 8)},   # Primary
        "LINK-SYD-MEL-FIBRE-02": {"util": 38.0, "latency": (4, 8)},   # Backup
        ...
    }
    for link in ALL_LINKS:
        for sample in range(864):  # 72h / 5min
            if is_cut_link and after_incident:
                # Dead: 0% util, -40dBm, BER=1, 9999ms latency
            elif is_backup_link and after_incident:
                # Elevated: 68-82% util (absorbing redirected traffic)
            elif is_reroute_link and after_incident:
                # Moderate increase: +12-22% util
            else:
                # Normal baseline ±5% variation
```

## Graph Schema — `graph_schema.yaml`

See the full file at `data/scenarios/telco-noc/graph_schema.yaml`. Key structure:

```yaml
data_dir: data/entities

vertices:
  - label: CoreRouter
    csv_file: DimCoreRouter.csv
    id_column: RouterId
    partition_key: router
    properties: [RouterId, City, Region, Vendor, Model]
  # ... 7 more vertex definitions

edges:
  # Bidirectional: TransportLink connects_to CoreRouter (2 entries)
  - label: connects_to
    csv_file: DimTransportLink.csv
    source: { label: TransportLink, property: LinkId, column: LinkId }
    target: { label: CoreRouter, property: RouterId, column: SourceRouterId }
    properties: [{ name: direction, value: source }]
  - label: connects_to
    csv_file: DimTransportLink.csv
    source: { label: TransportLink, property: LinkId, column: LinkId }
    target: { label: CoreRouter, property: RouterId, column: TargetRouterId }
    properties: [{ name: direction, value: target }]

  # FK-based: AggSwitch aggregates_to CoreRouter
  - label: aggregates_to
    csv_file: DimAggSwitch.csv
    source: { label: AggSwitch, property: SwitchId, column: SwitchId }
    target: { label: CoreRouter, property: RouterId, column: UplinkRouterId }

  # Filtered: MPLSPath routes_via TransportLink (junction table)
  - label: routes_via
    csv_file: FactMPLSPathHops.csv
    filter: { column: NodeType, value: TransportLink }
    source: { label: MPLSPath, property: PathId, column: PathId }
    target: { label: TransportLink, property: LinkId, column: NodeId }
    properties: [{ name: HopOrder, column: HopOrder }]

  # Filtered: Service depends_on MPLSPath|AggSwitch|BaseStation (3 entries)
  - label: depends_on
    csv_file: FactServiceDependency.csv
    filter: { column: DependsOnType, value: MPLSPath }
    source: { label: Service, property: ServiceId, column: ServiceId }
    target: { label: MPLSPath, property: PathId, column: DependsOnId }
    properties: [{ name: DependencyStrength, column: DependencyStrength }]
  # ... 2 more depends_on entries for AggSwitch and BaseStation

  # Bidirectional: BGPSession peers_over CoreRouter (2 entries)
  # FK-based: SLAPolicy governed_by Service
```

Total: 8 vertex definitions, 11 edge definitions.

## `generate_all.sh`

```bash
#!/usr/bin/env bash
# Generate all data for the telco-noc scenario
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Generating telco-noc scenario data ==="
python3 "$SCRIPT_DIR/generate_topology.py"
python3 "$SCRIPT_DIR/generate_routing.py"
python3 "$SCRIPT_DIR/generate_telemetry.py"
python3 "$SCRIPT_DIR/generate_tickets.py"
echo "=== Done ==="
```

## Adapting for a New Domain

When creating a new scenario, follow this mapping from telco-noc to your domain:

| Telco-NOC | Cloud-Outage (example) | Your Domain |
|-----------|----------------------|-------------|
| CoreRouter | Region | Top-level infrastructure |
| TransportLink | AvailabilityZone | Connection/zone entities |
| AggSwitch | Rack | Mid-tier aggregation |
| BaseStation | Host | Compute/endpoint entities |
| BGPSession | (edge only) | Protocol/session entities |
| MPLSPath | (edge only) | Path/route entities |
| Service | Service | Business services |
| SLAPolicy | SLAPolicy | Policy/governance |
| `LINK_DOWN` | `COOLING_FAILURE` | Root cause alert type |
| `BGP_PEER_LOSS` | `THERMAL_SHUTDOWN` | Second-order failure |
| `SERVICE_DEGRADATION` | `VM_UNREACHABLE` | Customer impact |
| OpticalPowerDbm | TemperatureCelsius | Domain-specific metric |
| BitErrorRate | MemoryUtilPct | Domain-specific metric |
| FactMPLSPathHops | FactLBBackend | Path/routing junction |
| FactServiceDependency | FactServiceDependency | Dependency junction |
