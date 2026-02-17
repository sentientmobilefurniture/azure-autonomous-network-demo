"""
Generate relationship / junction table CSV files for the telco-backbone scenario.

Outputs 3 CSV files:
  - FactMPLSPathHops.csv        (MPLSPath --ROUTES_VIA--> nodes)
  - FactServiceDependency.csv   (Service --DEPENDS_ON--> resources)
  - FactFirewallProtects.csv    (FirewallCluster --PROTECTS--> Service)
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
        # ADL-PER Primary: ADL router → submarine cable → PER router
        ["MPLS-PATH-ADL-PER-PRIMARY", 1, "CORE-ADL-01", "CoreRouter"],
        ["MPLS-PATH-ADL-PER-PRIMARY", 2, "LINK-ADL-PER-SUBMARINE-01", "TransportLink"],
        ["MPLS-PATH-ADL-PER-PRIMARY", 3, "CORE-PER-01", "CoreRouter"],
        # ADL-PER Secondary: ADL router → microwave backup → PER router
        ["MPLS-PATH-ADL-PER-SECONDARY", 1, "CORE-ADL-01", "CoreRouter"],
        ["MPLS-PATH-ADL-PER-SECONDARY", 2, "LINK-ADL-PER-MICROWAVE-01", "TransportLink"],
        ["MPLS-PATH-ADL-PER-SECONDARY", 3, "CORE-PER-01", "CoreRouter"],
        # SYD-MEL Primary: SYD router → fibre → MEL router
        ["MPLS-PATH-SYD-MEL-PRIMARY", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-MEL-PRIMARY", 2, "LINK-SYD-MEL-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-MEL-PRIMARY", 3, "CORE-MEL-01", "CoreRouter"],
        # MEL-ADL Primary: MEL router → fibre → ADL router
        ["MPLS-PATH-MEL-ADL-PRIMARY", 1, "CORE-MEL-01", "CoreRouter"],
        ["MPLS-PATH-MEL-ADL-PRIMARY", 2, "LINK-MEL-ADL-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-MEL-ADL-PRIMARY", 3, "CORE-ADL-01", "CoreRouter"],
        # SYD-CBR Primary: SYD router → fibre → CBR router
        ["MPLS-PATH-SYD-CBR-PRIMARY", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-CBR-PRIMARY", 2, "LINK-SYD-CBR-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-CBR-PRIMARY", 3, "CORE-CBR-01", "CoreRouter"],
        # SYD-ADL Primary: SYD router → inland fibre → ADL router
        ["MPLS-PATH-SYD-ADL-PRIMARY", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-ADL-PRIMARY", 2, "LINK-SYD-ADL-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-ADL-PRIMARY", 3, "CORE-ADL-01", "CoreRouter"],
        # SYD-PER via MEL-ADL (indirect 5-hop): SYD → SYD-MEL → MEL → MEL-ADL → ADL → ADL-PER-SUB → PER
        ["MPLS-PATH-SYD-PER-VIA-MEL-ADL", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-PER-VIA-MEL-ADL", 2, "LINK-SYD-MEL-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-PER-VIA-MEL-ADL", 3, "CORE-MEL-01", "CoreRouter"],
        ["MPLS-PATH-SYD-PER-VIA-MEL-ADL", 4, "LINK-MEL-ADL-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-PER-VIA-MEL-ADL", 5, "CORE-ADL-01", "CoreRouter"],
        ["MPLS-PATH-SYD-PER-VIA-MEL-ADL", 6, "LINK-ADL-PER-SUBMARINE-01", "TransportLink"],
        ["MPLS-PATH-SYD-PER-VIA-MEL-ADL", 7, "CORE-PER-01", "CoreRouter"],
        # SYD-PER via ADL (alternate indirect 3-hop): SYD → SYD-ADL → ADL → ADL-PER-SUB → PER
        ["MPLS-PATH-SYD-PER-VIA-ADL", 1, "CORE-SYD-01", "CoreRouter"],
        ["MPLS-PATH-SYD-PER-VIA-ADL", 2, "LINK-SYD-ADL-FIBRE-01", "TransportLink"],
        ["MPLS-PATH-SYD-PER-VIA-ADL", 3, "CORE-ADL-01", "CoreRouter"],
        ["MPLS-PATH-SYD-PER-VIA-ADL", 4, "LINK-ADL-PER-SUBMARINE-01", "TransportLink"],
        ["MPLS-PATH-SYD-PER-VIA-ADL", 5, "CORE-PER-01", "CoreRouter"],
    ]
    write_csv("FactMPLSPathHops.csv", headers, rows)


def generate_service_dependencies() -> None:
    """Service-to-resource dependency mappings."""
    headers = ["ServiceId", "DependsOnId", "DependsOnType", "DependencyStrength"]
    rows = [
        # IronOre Mining VPN: Perth HQ ↔ Adelaide operations — depends on ADL-PER paths
        ["VPN-IRONORE-CORP", "MPLS-PATH-ADL-PER-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-IRONORE-CORP", "MPLS-PATH-ADL-PER-SECONDARY", "MPLSPath", "SECONDARY"],
        ["VPN-IRONORE-CORP", "MPLS-PATH-SYD-PER-VIA-ADL", "MPLSPath", "TERTIARY"],
        # WestGas Energy VPN: Perth HQ ↔ Melbourne office
        ["VPN-WESTGAS-CORP", "MPLS-PATH-ADL-PER-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-WESTGAS-CORP", "MPLS-PATH-ADL-PER-SECONDARY", "MPLSPath", "SECONDARY"],
        ["VPN-WESTGAS-CORP", "MPLS-PATH-SYD-PER-VIA-MEL-ADL", "MPLSPath", "TERTIARY"],
        # Defence VPN: Canberra ↔ Adelaide (secure comms)
        ["VPN-GOVDEFENCE", "MPLS-PATH-SYD-CBR-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-GOVDEFENCE", "MPLS-PATH-SYD-ADL-PRIMARY", "MPLSPath", "PRIMARY"],
        # FinServ VPN: Sydney ↔ Melbourne
        ["VPN-FINSERV-CORP", "MPLS-PATH-SYD-MEL-PRIMARY", "MPLSPath", "PRIMARY"],
        # UniLink Education: Sydney ↔ multiple campuses
        ["VPN-UNILINK", "MPLS-PATH-SYD-MEL-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-UNILINK", "MPLS-PATH-SYD-CBR-PRIMARY", "MPLSPath", "PRIMARY"],
        ["VPN-UNILINK", "MPLS-PATH-SYD-ADL-PRIMARY", "MPLSPath", "SECONDARY"],
        # Broadband bundles depend on aggregation switches
        ["BB-BUNDLE-SYD-NORTH", "AGG-SYD-NORTH-01", "AggSwitch", "PRIMARY"],
        ["BB-BUNDLE-MEL-EAST", "AGG-MEL-EAST-01", "AggSwitch", "PRIMARY"],
        ["BB-BUNDLE-ADL-SOUTH", "AGG-ADL-SOUTH-01", "AggSwitch", "PRIMARY"],  # impacted by power failure
        ["BB-BUNDLE-PER-CENTRAL", "AGG-PER-CENTRAL-01", "AggSwitch", "PRIMARY"],
        # Mobile services depend on base stations
        ["MOB-5G-SYD-2041", "GNB-SYD-2041", "BaseStation", "PRIMARY"],
        ["MOB-5G-MEL-3011", "GNB-MEL-3011", "BaseStation", "PRIMARY"],
        ["MOB-5G-ADL-5011", "GNB-ADL-5011", "BaseStation", "PRIMARY"],
        ["MOB-5G-PER-6011", "GNB-PER-6011", "BaseStation", "PRIMARY"],
        ["MOB-5G-CBR-7011", "GNB-CBR-7011", "BaseStation", "PRIMARY"],
    ]
    write_csv("FactServiceDependency.csv", headers, rows)


def generate_firewall_protects() -> None:
    """Firewall-to-service protection mappings."""
    headers = ["FirewallId", "ServiceId", "PolicyType"]
    rows = [
        # Sydney firewall protects east-coast services
        ["FW-SYD-01", "VPN-FINSERV-CORP", "ENTERPRISE"],
        ["FW-SYD-01", "VPN-UNILINK", "ENTERPRISE"],
        ["FW-SYD-01", "BB-BUNDLE-SYD-NORTH", "RESIDENTIAL"],
        # Melbourne firewall
        ["FW-MEL-01", "VPN-FINSERV-CORP", "ENTERPRISE"],
        ["FW-MEL-01", "BB-BUNDLE-MEL-EAST", "RESIDENTIAL"],
        # Adelaide firewall
        ["FW-ADL-01", "VPN-IRONORE-CORP", "ENTERPRISE"],
        ["FW-ADL-01", "BB-BUNDLE-ADL-SOUTH", "RESIDENTIAL"],
        # Perth firewall
        ["FW-PER-01", "VPN-IRONORE-CORP", "ENTERPRISE"],
        ["FW-PER-01", "VPN-WESTGAS-CORP", "ENTERPRISE"],
        ["FW-PER-01", "BB-BUNDLE-PER-CENTRAL", "RESIDENTIAL"],
        # Canberra firewall — government
        ["FW-CBR-01", "VPN-GOVDEFENCE", "GOVERNMENT"],
    ]
    write_csv("FactFirewallProtects.csv", headers, rows)


def main() -> None:
    print("Generating routing data (telco-backbone junction tables)...")
    generate_mpls_path_hops()
    generate_service_dependencies()
    generate_firewall_protects()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
