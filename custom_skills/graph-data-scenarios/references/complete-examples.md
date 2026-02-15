# Complete Examples

Full annotated code from the reference scenarios. Use these as templates
when creating a new scenario.

## Topology Generator — Cloud-Outage

Complete `generate_topology.py` showing all 8 entity types:

```python
"""
Generate static topology CSV files for cloud datacenter entity tables.

Domain: Cloud infrastructure — multi-region datacenter with availability zones,
racks, hosts, VMs, load balancers, services, and SLA policies.

Incident scenario: Cooling failure in AZ-US-EAST-A causes cascading host
thermal shutdowns, VM unreachability, and service degradation.

Outputs 8 CSV files:
  - DimRegion.csv
  - DimAvailabilityZone.csv
  - DimRack.csv
  - DimHost.csv
  - DimVirtualMachine.csv
  - DimLoadBalancer.csv
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


def generate_regions() -> None:
    headers = ["RegionId", "RegionName", "Country", "Provider"]
    rows = [
        ["REGION-US-EAST", "US East", "United States", "CloudCorp"],
        ["REGION-US-WEST", "US West", "United States", "CloudCorp"],
        ["REGION-EU-WEST", "EU West", "Ireland", "CloudCorp"],
    ]
    write_csv("DimRegion.csv", headers, rows)


def generate_availability_zones() -> None:
    headers = ["AZId", "AZName", "RegionId", "CoolingSystem", "PowerFeedCount"]
    rows = [
        ["AZ-US-EAST-A", "US-East-AZ-A", "REGION-US-EAST", "CRAC-UNIT-A1", 2],
        ["AZ-US-EAST-B", "US-East-AZ-B", "REGION-US-EAST", "CRAC-UNIT-B1", 2],
        ["AZ-US-WEST-A", "US-West-AZ-A", "REGION-US-WEST", "CRAC-UNIT-A1", 2],
        ["AZ-EU-WEST-A", "EU-West-AZ-A", "REGION-EU-WEST", "CRAC-UNIT-A1", 2],
    ]
    write_csv("DimAvailabilityZone.csv", headers, rows)


def generate_racks() -> None:
    headers = ["RackId", "RackPosition", "AZId", "MaxPowerKW", "CoolingZone"]
    rows = [
        # US-East AZ-A (incident zone — 3 racks)
        ["RACK-US-EAST-A-01", "Row-1-Pos-1", "AZ-US-EAST-A", 20, "Zone-North"],
        ["RACK-US-EAST-A-02", "Row-1-Pos-2", "AZ-US-EAST-A", 20, "Zone-North"],
        ["RACK-US-EAST-A-03", "Row-2-Pos-1", "AZ-US-EAST-A", 20, "Zone-South"],
        # US-East AZ-B (failover zone — 2 racks)
        ["RACK-US-EAST-B-01", "Row-1-Pos-1", "AZ-US-EAST-B", 20, "Zone-North"],
        ["RACK-US-EAST-B-02", "Row-1-Pos-2", "AZ-US-EAST-B", 20, "Zone-South"],
        # US-West AZ-A (1 rack)
        ["RACK-US-WEST-A-01", "Row-1-Pos-1", "AZ-US-WEST-A", 20, "Zone-North"],
        # EU-West AZ-A (1 rack)
        ["RACK-EU-WEST-A-01", "Row-1-Pos-1", "AZ-EU-WEST-A", 20, "Zone-North"],
    ]
    write_csv("DimRack.csv", headers, rows)


def generate_hosts() -> None:
    headers = ["HostId", "Hostname", "RackId", "CPUCores", "MemoryGB", "Vendor"]
    rows = [
        # AZ-A hosts (impacted by cooling failure)
        ["HOST-USE-A-01-01", "nyc-host-01", "RACK-US-EAST-A-01", 64, 256, "Dell"],
        ["HOST-USE-A-01-02", "nyc-host-02", "RACK-US-EAST-A-01", 64, 256, "Dell"],
        ["HOST-USE-A-02-01", "nyc-host-03", "RACK-US-EAST-A-02", 128, 512, "HPE"],
        ["HOST-USE-A-02-02", "nyc-host-04", "RACK-US-EAST-A-02", 128, 512, "HPE"],
        ["HOST-USE-A-03-01", "nyc-host-05", "RACK-US-EAST-A-03", 64, 256, "Dell"],
        # AZ-B hosts (failover targets)
        ["HOST-USE-B-01-01", "nyc-host-06", "RACK-US-EAST-B-01", 64, 256, "Dell"],
        ["HOST-USE-B-01-02", "nyc-host-07", "RACK-US-EAST-B-01", 128, 512, "HPE"],
        ["HOST-USE-B-02-01", "nyc-host-08", "RACK-US-EAST-B-02", 64, 256, "Dell"],
        # US-West host
        ["HOST-USW-A-01-01", "lax-host-01", "RACK-US-WEST-A-01", 64, 256, "Dell"],
        # EU-West host
        ["HOST-EUW-A-01-01", "dub-host-01", "RACK-EU-WEST-A-01", 64, 256, "Dell"],
    ]
    write_csv("DimHost.csv", headers, rows)


def generate_virtual_machines() -> None:
    headers = ["VMId", "VMName", "HostId", "ServiceId", "vCPUs", "MemoryGB", "OSType"]
    rows = [
        # AZ-A VMs (impacted) — 2 VMs per host
        ["VM-USE-A-01-01-0001", "web-prod-01", "HOST-USE-A-01-01", "SVC-WEB-FRONTEND", 4, 16, "Linux"],
        ["VM-USE-A-01-01-0002", "web-prod-02", "HOST-USE-A-01-01", "SVC-WEB-FRONTEND", 4, 16, "Linux"],
        ["VM-USE-A-01-02-0001", "api-prod-01", "HOST-USE-A-01-02", "SVC-PAYMENT-API", 8, 32, "Linux"],
        ["VM-USE-A-02-01-0001", "db-prod-01", "HOST-USE-A-02-01", "SVC-ORDER-DB", 16, 128, "Linux"],
        ["VM-USE-A-02-01-0002", "db-prod-02", "HOST-USE-A-02-01", "SVC-ORDER-DB", 16, 128, "Linux"],
        ["VM-USE-A-02-02-0001", "cache-prod-01", "HOST-USE-A-02-02", "SVC-CACHE-LAYER", 8, 64, "Linux"],
        ["VM-USE-A-03-01-0001", "search-prod-01", "HOST-USE-A-03-01", "SVC-SEARCH", 8, 32, "Linux"],
        # AZ-B VMs (failover replicas)
        ["VM-USE-B-01-01-0001", "web-dr-01", "HOST-USE-B-01-01", "SVC-WEB-FRONTEND", 4, 16, "Linux"],
        ["VM-USE-B-01-02-0001", "api-dr-01", "HOST-USE-B-01-02", "SVC-PAYMENT-API", 8, 32, "Linux"],
        ["VM-USE-B-02-01-0001", "db-dr-01", "HOST-USE-B-02-01", "SVC-ORDER-DB", 16, 128, "Linux"],
        # US-West VM
        ["VM-USW-A-01-01-0001", "cdn-west-01", "HOST-USW-A-01-01", "SVC-CDN-EDGE", 4, 16, "Linux"],
        # EU-West VM
        ["VM-EUW-A-01-01-0001", "cdn-eu-01", "HOST-EUW-A-01-01", "SVC-CDN-EDGE", 4, 16, "Linux"],
    ]
    write_csv("DimVirtualMachine.csv", headers, rows)


def generate_load_balancers() -> None:
    headers = ["LBId", "LBName", "LBType", "RegionId", "Algorithm", "HealthCheckPath"]
    rows = [
        ["LB-US-EAST-WEB-01", "web-lb-east", "Application", "REGION-US-EAST", "RoundRobin", "/health"],
        ["LB-US-EAST-API-01", "api-lb-east", "Application", "REGION-US-EAST", "LeastConnections", "/api/health"],
        ["LB-GLOBAL-CDN-01", "cdn-global-lb", "Network", "REGION-US-EAST", "GeoDNS", "/"],
    ]
    write_csv("DimLoadBalancer.csv", headers, rows)


def generate_services() -> None:
    headers = ["ServiceId", "ServiceName", "ServiceType", "Tier", "Owner"]
    rows = [
        ["SVC-WEB-FRONTEND", "Web Frontend", "WebApp", "Tier-1", "Platform Team"],
        ["SVC-PAYMENT-API", "Payment API", "API", "Tier-1", "Payments Team"],
        ["SVC-ORDER-DB", "Order Database", "Database", "Tier-1", "Data Team"],
        ["SVC-CACHE-LAYER", "Cache Layer", "Cache", "Tier-2", "Platform Team"],
        ["SVC-SEARCH", "Search Service", "Search", "Tier-2", "Search Team"],
        ["SVC-CDN-EDGE", "CDN Edge", "CDN", "Tier-2", "Platform Team"],
    ]
    write_csv("DimService.csv", headers, rows)


def generate_sla_policies() -> None:
    headers = ["SLAId", "SLAName", "ServiceId", "UptimePct", "MaxLatencyMs", "RPOMinutes"]
    rows = [
        ["SLA-WEB-FRONTEND-GOLD", "Web Frontend SLA", "SVC-WEB-FRONTEND", 99.99, 200, 5],
        ["SLA-PAYMENT-API-GOLD", "Payment API SLA", "SVC-PAYMENT-API", 99.99, 100, 1],
        ["SLA-ORDER-DB-GOLD", "Order DB SLA", "SVC-ORDER-DB", 99.999, 50, 0],
        ["SLA-CACHE-LAYER-SILVER", "Cache Layer SLA", "SVC-CACHE-LAYER", 99.9, 500, 15],
        ["SLA-SEARCH-SILVER", "Search SLA", "SVC-SEARCH", 99.9, 300, 30],
    ]
    write_csv("DimSLAPolicy.csv", headers, rows)


def main() -> None:
    print("Generating cloud topology data (datacenter entity tables)...")
    generate_regions()
    generate_availability_zones()
    generate_racks()
    generate_hosts()
    generate_virtual_machines()
    generate_load_balancers()
    generate_services()
    generate_sla_policies()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
```

## Telemetry Generator — Telco-NOC Alert Cascade

The core cascade pattern from `generate_telemetry.py`. This shows the
most important sections — the full implementation is ~300 lines.

```python
"""
Generate alert stream and link telemetry CSV files for Cosmos DB NoSQL.
Outputs: AlertStream.csv (~5,000 rows), LinkTelemetry.csv (~8,600 rows)
"""

import csv
import os
import random
from datetime import datetime, timedelta, timezone

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "telemetry")
INCIDENT_START = datetime(2026, 2, 6, 14, 30, 0, tzinfo=timezone.utc)
random.seed(42)

# ── Topology references (must match entity CSVs exactly) ──────────────────
CORE_ROUTERS = ["CORE-SYD-01", "CORE-MEL-01", "CORE-BNE-01"]
AGG_SWITCHES = ["AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01", "AGG-MEL-EAST-01", ...]
BASE_STATIONS = ["GNB-SYD-2041", "GNB-SYD-2042", ...]
TRANSPORT_LINKS = ["LINK-SYD-MEL-FIBRE-01", "LINK-SYD-MEL-FIBRE-02", ...]
SERVICES = ["VPN-ACME-CORP", "VPN-BIGBANK", ...]

# Nodes impacted by the SYD-MEL fibre-01 cut (downstream tiers)
IMPACTED_ROUTERS = ["CORE-SYD-01", "CORE-MEL-01"]
IMPACTED_AGG = ["AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01", "AGG-MEL-EAST-01", "AGG-MEL-WEST-01"]
IMPACTED_GNB = ["GNB-SYD-2041", "GNB-SYD-2042", "GNB-SYD-2043", ...]
IMPACTED_SERVICES = ["VPN-ACME-CORP", "VPN-BIGBANK", "BB-BUNDLE-SYD-NORTH", ...]

def write_csv(filename, headers, rows):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, filename), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def ts(offset_seconds):
    return (INCIDENT_START + timedelta(seconds=offset_seconds)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def jitter(base, spread=2.0):
    return base + random.uniform(-spread, spread)

def generate_alert_stream():
    headers = ["AlertId", "Timestamp", "SourceNodeId", "SourceNodeType",
               "AlertType", "Severity", "Description",
               "OpticalPowerDbm", "BitErrorRate", "CPUUtilPct", "PacketLossPct"]
    alerts = []
    counter = 0

    # Normal-range generators (ensure no nulls)
    def normal_optical(): return round(random.uniform(-3.5, -2.5), 1)
    def normal_ber(): return round(random.uniform(1e-14, 1e-11), 15)
    def normal_cpu(): return round(random.uniform(15, 45), 1)
    def normal_pkt_loss(): return round(random.uniform(0.0, 0.05), 3)
    def baseline_snapshot():
        return {"optical": normal_optical(), "ber": normal_ber(),
                "cpu": normal_cpu(), "pkt_loss": normal_pkt_loss()}

    def add(offset, node_id, node_type, alert_type, severity, desc,
            optical=None, ber=None, cpu=None, pkt_loss=None):
        nonlocal counter
        counter += 1
        snap = baseline_snapshot()
        alerts.append([
            f"ALT-20260206-{counter:06d}", ts(offset), node_id, node_type,
            alert_type, severity, desc,
            optical if optical is not None else snap["optical"],
            ber if ber is not None else snap["ber"],
            cpu if cpu is not None else snap["cpu"],
            pkt_loss if pkt_loss is not None else snap["pkt_loss"],
        ])

    # ── Baseline: 54h of normal noise (~3000 alerts) ──────────────────
    for _ in range(random.randint(2800, 3400)):
        offset = random.uniform(-54 * 3600, -60)
        node, ntype = random.choice(all_nodes)
        add(offset, node, ntype, "HIGH_CPU", "WARNING", "CPU spike — routine", 
            cpu=round(random.uniform(55, 75), 1))

    # ── T+0s: Root cause — fibre cut ─────────────────────────────────
    add(0.0, "LINK-SYD-MEL-FIBRE-01", "TransportLink", "LINK_DOWN",
        "CRITICAL", "Physical link loss of light detected",
        optical=-40.0, ber=1.0, pkt_loss=100.0)

    # ── T+2s: BGP peer loss ──────────────────────────────────────────
    add(2.1, "CORE-SYD-01", "CoreRouter", "BGP_PEER_LOSS",
        "CRITICAL", "BGP peer CORE-MEL-01 unreachable",
        cpu=round(random.uniform(78, 88), 1), pkt_loss=round(random.uniform(2, 8), 2))

    # ── T+5s: OSPF adjacency drops ──────────────────────────────────
    # ── T+10s: Route withdrawals (~20 alerts) ────────────────────────
    # ── T+15s: HIGH_CPU reconvergence (~50 alerts) ───────────────────
    # ── T+30s: Packet loss downstream (~200 alerts) ──────────────────
    # ── T+60s: Service degradation (~500 alerts) ─────────────────────
    # ── T+70-90s: Flapping/duplicates (fill to ~2000) ────────────────

    alerts.sort(key=lambda r: r[1])  # Sort by timestamp
    write_csv("AlertStream.csv", headers, alerts)
```

## Routing Generator — Telco-NOC

Complete `generate_routing.py` showing both junction table patterns:

```python
"""
Generate junction table CSV files for network relationships.
Outputs: FactMPLSPathHops.csv, FactServiceDependency.csv
"""

import csv
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "entities")

def write_csv(filename, headers, rows):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, filename), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def generate_mpls_path_hops():
    """Ordered traversal: each MPLS path traverses routers and links."""
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
        # SYD-MEL via BNE (indirect failover path)
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 2, "LINK-SYD-BNE-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 3, "CORE-BNE-01", "CoreRouter"],
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 4, "LINK-MEL-BNE-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-MEL-VIA-BNE", 5, "CORE-MEL-01", "CoreRouter"],
    ]
    write_csv("FactMPLSPathHops.csv", headers, rows)

def generate_service_dependencies():
    """Typed dependencies: services depend on different resource types."""
    headers = ["ServiceId", "DependsOnId", "DependsOnType", "DependencyStrength"]
    rows = [
        # Enterprise VPNs depend on MPLS paths (primary + backup)
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-SECONDARY", "MPLSPath", "SECONDARY"],
        ["VPN-ACME-CORP", "MPLS-PATH-SYD-MEL-VIA-BNE", "MPLSPath", "TERTIARY"],
        ["VPN-BIGBANK", "MPLS-PATH-SYD-MEL-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-BIGBANK", "MPLS-PATH-SYD-MEL-SECONDARY", "MPLSPath", "SECONDARY"],
        # Broadband depends on aggregation switches
        ["BB-BUNDLE-SYD-NORTH", "AGG-SYD-NORTH-01", "AggSwitch", "PRIMARY"],
        ["BB-BUNDLE-MEL-EAST", "AGG-MEL-EAST-01", "AggSwitch", "PRIMARY"],
        # Mobile depends on base stations
        ["MOB-5G-SYD-2041", "GNB-SYD-2041", "BaseStation", "PRIMARY"],
        ["MOB-5G-MEL-3011", "GNB-MEL-3011", "BaseStation", "PRIMARY"],
    ]
    write_csv("FactServiceDependency.csv", headers, rows)

def main():
    print("Generating routing data...")
    generate_mpls_path_hops()
    generate_service_dependencies()

if __name__ == "__main__":
    main()
```

## Ticket Generator — Pattern

The ticket generator pattern is identical across all scenarios — only the
ticket content changes. See `ticket-format.md` for the complete formatter code.

Key structural elements:
1. A `generate_tickets()` function returning a list of dicts
2. A `_format_ticket()` function converting dict → structured text
3. A `main()` function writing one `.txt` file per ticket

## generate_all.sh — Runner Script

```bash
#!/usr/bin/env bash
# Generate all data for the <scenario> scenario
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Generating <scenario-name> scenario data ==="
python3 "$SCRIPT_DIR/generate_topology.py"
python3 "$SCRIPT_DIR/generate_routing.py"
python3 "$SCRIPT_DIR/generate_telemetry.py"
python3 "$SCRIPT_DIR/generate_tickets.py"
echo "=== Done ==="
```
