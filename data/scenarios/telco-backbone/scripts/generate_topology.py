"""
Generate static topology CSV files for the telco-backbone scenario.

Outputs 10 CSV files:
  - DimDataCenter.csv
  - DimCoreRouter.csv
  - DimTransportLink.csv
  - DimAggSwitch.csv
  - DimBaseStation.csv
  - DimBGPSession.csv
  - DimMPLSPath.csv
  - DimService.csv
  - DimSLAPolicy.csv
  - DimFirewallCluster.csv
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


def generate_data_centers() -> None:
    headers = ["DataCenterId", "City", "Region", "Tier", "PowerRedundancy"]
    rows = [
        ["DC-SYD-01", "Sydney", "NSW", "Tier4", "2N"],
        ["DC-MEL-01", "Melbourne", "VIC", "Tier4", "2N"],
        ["DC-ADL-01", "Adelaide", "SA", "Tier3", "N+1"],
        ["DC-PER-01", "Perth", "WA", "Tier3", "N+1"],
        ["DC-CBR-01", "Canberra", "ACT", "Tier4", "2N"],
    ]
    write_csv("DimDataCenter.csv", headers, rows)


def generate_core_routers() -> None:
    headers = ["RouterId", "City", "Region", "Vendor", "Model", "DataCenterId"]
    rows = [
        ["CORE-SYD-01", "Sydney", "NSW", "Cisco", "ASR-9922", "DC-SYD-01"],
        ["CORE-MEL-01", "Melbourne", "VIC", "Cisco", "ASR-9922", "DC-MEL-01"],
        ["CORE-ADL-01", "Adelaide", "SA", "Juniper", "MX10008", "DC-ADL-01"],
        ["CORE-PER-01", "Perth", "WA", "Juniper", "MX10008", "DC-PER-01"],
        ["CORE-CBR-01", "Canberra", "ACT", "Nokia", "7750-SR14", "DC-CBR-01"],
    ]
    write_csv("DimCoreRouter.csv", headers, rows)


def generate_transport_links() -> None:
    headers = ["LinkId", "LinkType", "CapacityGbps", "SourceRouterId", "TargetRouterId"]
    rows = [
        # Inter-city backbone links
        ["LINK-SYD-MEL-FIBRE-01", "DWDM_100G", 100, "CORE-SYD-01", "CORE-MEL-01"],
        ["LINK-MEL-ADL-FIBRE-01", "DWDM_100G", 100, "CORE-MEL-01", "CORE-ADL-01"],
        ["LINK-ADL-PER-SUBMARINE-01", "SUBMARINE_40G", 40, "CORE-ADL-01", "CORE-PER-01"],  # primary — gets cut
        ["LINK-ADL-PER-MICROWAVE-01", "MICROWAVE_10G", 10, "CORE-ADL-01", "CORE-PER-01"],  # backup — low capacity
        ["LINK-SYD-CBR-FIBRE-01", "DWDM_100G", 100, "CORE-SYD-01", "CORE-CBR-01"],
        ["LINK-SYD-ADL-FIBRE-01", "DWDM_100G", 100, "CORE-SYD-01", "CORE-ADL-01"],  # inland alternate
        # Aggregation uplinks
        ["LINK-SYD-AGG-NORTH-01", "100GE", 100, "CORE-SYD-01", "CORE-SYD-01"],
        ["LINK-SYD-AGG-SOUTH-01", "100GE", 100, "CORE-SYD-01", "CORE-SYD-01"],
        ["LINK-MEL-AGG-EAST-01", "100GE", 100, "CORE-MEL-01", "CORE-MEL-01"],
        ["LINK-MEL-AGG-WEST-01", "100GE", 100, "CORE-MEL-01", "CORE-MEL-01"],
        ["LINK-ADL-AGG-NORTH-01", "100GE", 100, "CORE-ADL-01", "CORE-ADL-01"],
        ["LINK-ADL-AGG-SOUTH-01", "100GE", 100, "CORE-ADL-01", "CORE-ADL-01"],
        ["LINK-PER-AGG-CENTRAL-01", "100GE", 100, "CORE-PER-01", "CORE-PER-01"],
        ["LINK-CBR-AGG-CENTRAL-01", "100GE", 100, "CORE-CBR-01", "CORE-CBR-01"],
    ]
    write_csv("DimTransportLink.csv", headers, rows)


def generate_firewall_clusters() -> None:
    headers = ["FirewallId", "City", "Vendor", "Model", "DataCenterId"]
    rows = [
        ["FW-SYD-01", "Sydney", "Palo Alto", "PA-7080", "DC-SYD-01"],
        ["FW-MEL-01", "Melbourne", "Palo Alto", "PA-7080", "DC-MEL-01"],
        ["FW-ADL-01", "Adelaide", "Fortinet", "FG-3700F", "DC-ADL-01"],
        ["FW-PER-01", "Perth", "Fortinet", "FG-3700F", "DC-PER-01"],
        ["FW-CBR-01", "Canberra", "Palo Alto", "PA-7080", "DC-CBR-01"],
    ]
    write_csv("DimFirewallCluster.csv", headers, rows)


def generate_agg_switches() -> None:
    headers = ["SwitchId", "City", "UplinkRouterId"]
    rows = [
        ["AGG-SYD-NORTH-01", "Sydney", "CORE-SYD-01"],
        ["AGG-SYD-SOUTH-01", "Sydney", "CORE-SYD-01"],
        ["AGG-MEL-EAST-01", "Melbourne", "CORE-MEL-01"],
        ["AGG-MEL-WEST-01", "Melbourne", "CORE-MEL-01"],
        ["AGG-ADL-NORTH-01", "Adelaide", "CORE-ADL-01"],
        ["AGG-ADL-SOUTH-01", "Adelaide", "CORE-ADL-01"],  # knocked out by DC-ADL-01 power failure
        ["AGG-PER-CENTRAL-01", "Perth", "CORE-PER-01"],
        ["AGG-CBR-CENTRAL-01", "Canberra", "CORE-CBR-01"],
    ]
    write_csv("DimAggSwitch.csv", headers, rows)


def generate_base_stations() -> None:
    headers = ["StationId", "StationType", "AggSwitchId", "City"]
    rows = [
        ["GNB-SYD-2041", "5G_NR", "AGG-SYD-NORTH-01", "Sydney"],
        ["GNB-SYD-2042", "5G_NR", "AGG-SYD-NORTH-01", "Sydney"],
        ["GNB-SYD-2043", "5G_NR", "AGG-SYD-SOUTH-01", "Sydney"],
        ["GNB-MEL-3011", "5G_NR", "AGG-MEL-EAST-01", "Melbourne"],
        ["GNB-MEL-3012", "5G_NR", "AGG-MEL-WEST-01", "Melbourne"],
        ["GNB-ADL-5011", "5G_NR", "AGG-ADL-NORTH-01", "Adelaide"],
        ["GNB-ADL-5012", "5G_NR", "AGG-ADL-SOUTH-01", "Adelaide"],  # impacted by power failure
        ["GNB-PER-6011", "5G_NR", "AGG-PER-CENTRAL-01", "Perth"],
        ["GNB-PER-6012", "5G_NR", "AGG-PER-CENTRAL-01", "Perth"],
        ["GNB-CBR-7011", "5G_NR", "AGG-CBR-CENTRAL-01", "Canberra"],
    ]
    write_csv("DimBaseStation.csv", headers, rows)


def generate_bgp_sessions() -> None:
    headers = ["SessionId", "PeerARouterId", "PeerBRouterId", "ASNumberA", "ASNumberB"]
    rows = [
        ["BGP-SYD-MEL-01", "CORE-SYD-01", "CORE-MEL-01", 64512, 64513],
        ["BGP-MEL-ADL-01", "CORE-MEL-01", "CORE-ADL-01", 64513, 64514],
        ["BGP-ADL-PER-01", "CORE-ADL-01", "CORE-PER-01", 64514, 64515],
        ["BGP-SYD-CBR-01", "CORE-SYD-01", "CORE-CBR-01", 64512, 64516],
        ["BGP-SYD-ADL-01", "CORE-SYD-01", "CORE-ADL-01", 64512, 64514],
    ]
    write_csv("DimBGPSession.csv", headers, rows)


def generate_mpls_paths() -> None:
    headers = ["PathId", "PathType"]
    rows = [
        # ADL-PER corridor (primary incident corridor)
        ["MPLS-PATH-ADL-PER-PRIMARY", "PRIMARY"],       # via submarine cable
        ["MPLS-PATH-ADL-PER-SECONDARY", "SECONDARY"],   # via microwave backup (10G only!)
        # SYD-MEL corridor
        ["MPLS-PATH-SYD-MEL-PRIMARY", "PRIMARY"],
        # MEL-ADL corridor
        ["MPLS-PATH-MEL-ADL-PRIMARY", "PRIMARY"],
        # SYD-CBR corridor
        ["MPLS-PATH-SYD-CBR-PRIMARY", "PRIMARY"],
        # SYD-ADL corridor (inland alternate)
        ["MPLS-PATH-SYD-ADL-PRIMARY", "PRIMARY"],
        # Multi-hop indirect: SYD → MEL → ADL → PER (tertiary to Perth)
        ["MPLS-PATH-SYD-PER-VIA-MEL-ADL", "TERTIARY"],
        # Multi-hop indirect: SYD → ADL → PER (alternate tertiary)
        ["MPLS-PATH-SYD-PER-VIA-ADL", "TERTIARY"],
    ]
    write_csv("DimMPLSPath.csv", headers, rows)


def generate_services() -> None:
    headers = ["ServiceId", "ServiceType", "CustomerName", "CustomerCount", "ActiveUsers"]
    rows = [
        # Enterprise VPNs
        ["VPN-IRONORE-CORP", "EnterpriseVPN", "IronOre Mining Ltd", 1, 2200],
        ["VPN-WESTGAS-CORP", "EnterpriseVPN", "WestGas Energy", 1, 850],
        ["VPN-GOVDEFENCE", "GovernmentVPN", "Department of Defence", 1, 3400],
        ["VPN-FINSERV-CORP", "EnterpriseVPN", "FinServ Holdings", 1, 1500],
        ["VPN-UNILINK", "EnterpriseVPN", "UniLink Education", 1, 4200],
        # Broadband bundles
        ["BB-BUNDLE-SYD-NORTH", "Broadband", "Residential - Sydney North", 3200, 3200],
        ["BB-BUNDLE-MEL-EAST", "Broadband", "Residential - Melbourne East", 2800, 2800],
        ["BB-BUNDLE-ADL-SOUTH", "Broadband", "Residential - Adelaide South", 1800, 1800],
        ["BB-BUNDLE-PER-CENTRAL", "Broadband", "Residential - Perth Central", 2100, 2100],
        # Mobile 5G services
        ["MOB-5G-SYD-2041", "Mobile5G", "Mobile Subscribers - SYD 2041", 4200, 4200],
        ["MOB-5G-MEL-3011", "Mobile5G", "Mobile Subscribers - MEL 3011", 3800, 3800],
        ["MOB-5G-ADL-5011", "Mobile5G", "Mobile Subscribers - ADL 5011", 2600, 2600],
        ["MOB-5G-PER-6011", "Mobile5G", "Mobile Subscribers - PER 6011", 3100, 3100],
        ["MOB-5G-CBR-7011", "Mobile5G", "Mobile Subscribers - CBR 7011", 1900, 1900],
    ]
    write_csv("DimService.csv", headers, rows)


def generate_sla_policies() -> None:
    headers = ["SLAPolicyId", "ServiceId", "AvailabilityPct", "MaxLatencyMs", "PenaltyPerHourUSD", "Tier"]
    rows = [
        ["SLA-IRONORE-GOLD", "VPN-IRONORE-CORP", 99.99, 25, 75000, "GOLD"],
        ["SLA-WESTGAS-GOLD", "VPN-WESTGAS-CORP", 99.99, 30, 60000, "GOLD"],
        ["SLA-GOVDEFENCE-PLATINUM", "VPN-GOVDEFENCE", 99.999, 10, 150000, "PLATINUM"],
        ["SLA-FINSERV-SILVER", "VPN-FINSERV-CORP", 99.95, 15, 35000, "SILVER"],
        ["SLA-UNILINK-SILVER", "VPN-UNILINK", 99.95, 20, 20000, "SILVER"],
        ["SLA-BB-PER-STANDARD", "BB-BUNDLE-PER-CENTRAL", 99.5, 50, 0, "STANDARD"],
        ["SLA-BB-ADL-STANDARD", "BB-BUNDLE-ADL-SOUTH", 99.5, 50, 0, "STANDARD"],
    ]
    write_csv("DimSLAPolicy.csv", headers, rows)


def main() -> None:
    print("Generating topology data (telco-backbone entity tables)...")
    generate_data_centers()
    generate_core_routers()
    generate_transport_links()
    generate_firewall_clusters()
    generate_agg_switches()
    generate_base_stations()
    generate_bgp_sessions()
    generate_mpls_paths()
    generate_services()
    generate_sla_policies()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
