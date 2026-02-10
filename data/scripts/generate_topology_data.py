"""
Generate static topology CSV files for Fabric Lakehouse entity tables.

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

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "lakehouse")


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
        # Inter-city backbone links
        ["LINK-SYD-MEL-FIBRE-01", "DWDM_100G", 100, "CORE-SYD-01", "CORE-MEL-01"],
        ["LINK-SYD-MEL-FIBRE-02", "DWDM_100G", 100, "CORE-SYD-01", "CORE-MEL-01"],
        ["LINK-SYD-BNE-FIBRE-01", "DWDM_100G", 100, "CORE-SYD-01", "CORE-BNE-01"],
        ["LINK-MEL-BNE-FIBRE-01", "DWDM_100G", 100, "CORE-MEL-01", "CORE-BNE-01"],
        # Aggregation uplinks — Sydney
        ["LINK-SYD-AGG-NORTH-01", "100GE", 100, "CORE-SYD-01", "CORE-SYD-01"],
        ["LINK-SYD-AGG-SOUTH-01", "100GE", 100, "CORE-SYD-01", "CORE-SYD-01"],
        # Aggregation uplinks — Melbourne
        ["LINK-MEL-AGG-EAST-01", "100GE", 100, "CORE-MEL-01", "CORE-MEL-01"],
        ["LINK-MEL-AGG-WEST-01", "100GE", 100, "CORE-MEL-01", "CORE-MEL-01"],
        # Aggregation uplinks — Brisbane
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
        # Indirect path via Brisbane — used when both SYD-MEL fibres fail
        ["MPLS-PATH-SYD-MEL-VIA-BNE", "TERTIARY"],
    ]
    write_csv("DimMPLSPath.csv", headers, rows)


def generate_services() -> None:
    headers = ["ServiceId", "ServiceType", "CustomerName", "CustomerCount", "ActiveUsers"]
    rows = [
        # Sydney / Melbourne enterprise VPNs
        ["VPN-ACME-CORP", "EnterpriseVPN", "ACME Corporation", 1, 450],
        ["VPN-BIGBANK", "EnterpriseVPN", "BigBank Financial", 1, 1200],
        # Brisbane enterprise VPN — mining company with FIFO workforce
        ["VPN-OZMINE", "EnterpriseVPN", "OzMine Resources", 1, 680],
        # Broadband bundles
        ["BB-BUNDLE-SYD-NORTH", "Broadband", "Residential - Sydney North", 3200, 3200],
        ["BB-BUNDLE-MEL-EAST", "Broadband", "Residential - Melbourne East", 2800, 2800],
        ["BB-BUNDLE-BNE-CENTRAL", "Broadband", "Residential - Brisbane Central", 2400, 2400],
        # Mobile 5G services
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
    print("Generating topology data (Lakehouse entity tables)...")
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
