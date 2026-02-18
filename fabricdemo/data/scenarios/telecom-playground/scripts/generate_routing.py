"""
Generate relationship / junction table CSV files for network data.

Outputs 2 CSV files:
  - FactMPLSPathHops.csv   (MPLSPath --ROUTES_VIA--> nodes)
  - FactServiceDependency.csv  (Service --DEPENDS_ON_MPLSPATH/AGGSWITCH/BASESTATION--> resources)
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
        # OzMine VPN depends on SYD-BNE MPLS path (HQ in Sydney, mines near Brisbane)
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
