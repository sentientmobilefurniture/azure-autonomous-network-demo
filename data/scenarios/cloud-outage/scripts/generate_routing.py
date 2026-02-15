"""
Generate junction/routing CSV files encoding graph edges for the cloud-outage scenario.

Outputs 2 CSV files:
  - FactVMPlacement.csv       — which VMs run on which hosts (with LB membership)
  - FactServiceDependency.csv — service-to-service and service-to-infra dependencies
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


def generate_service_dependencies() -> None:
    """Service-level dependency graph: which services depend on which infrastructure or other services."""
    headers = ["ServiceId", "DependsOnId", "DependsOnType", "DependencyStrength"]
    rows = [
        # E-Commerce Web depends on API, Cache, CDN, Auth
        ["SVC-ECOMMERCE-WEB", "SVC-ECOMMERCE-API", "Service", "PRIMARY"],
        ["SVC-ECOMMERCE-WEB", "SVC-CACHE-CLUSTER", "Service", "PRIMARY"],
        ["SVC-ECOMMERCE-WEB", "SVC-CDN", "Service", "SECONDARY"],
        ["SVC-ECOMMERCE-WEB", "SVC-AUTH", "Service", "PRIMARY"],
        # API depends on DB, Cache, Auth, Payment
        ["SVC-ECOMMERCE-API", "SVC-ECOMMERCE-DB", "Service", "PRIMARY"],
        ["SVC-ECOMMERCE-API", "SVC-CACHE-CLUSTER", "Service", "PRIMARY"],
        ["SVC-ECOMMERCE-API", "SVC-AUTH", "Service", "PRIMARY"],
        ["SVC-ECOMMERCE-API", "SVC-PAYMENT", "Service", "SECONDARY"],
        # Payment depends on DB
        ["SVC-PAYMENT", "SVC-ECOMMERCE-DB", "Service", "PRIMARY"],
        # ML Pipeline depends on DB, Logging
        ["SVC-ML-PIPELINE", "SVC-ECOMMERCE-DB", "Service", "SECONDARY"],
        ["SVC-ML-PIPELINE", "SVC-LOGGING", "Service", "SECONDARY"],
        # Monitoring depends on nothing (root)
        # Logging depends on nothing (root)
        # Services depend on LoadBalancers
        ["SVC-ECOMMERCE-WEB", "LB-USE-WEB", "LoadBalancer", "PRIMARY"],
        ["SVC-ECOMMERCE-API", "LB-USE-API", "LoadBalancer", "PRIMARY"],
        ["SVC-ECOMMERCE-DB", "LB-USE-DB", "LoadBalancer", "PRIMARY"],
        ["SVC-CDN", "LB-GLOBAL", "LoadBalancer", "PRIMARY"],
    ]
    write_csv("FactServiceDependency.csv", headers, rows)


def main() -> None:
    print("Generating cloud-outage routing/junction data ...")
    generate_service_dependencies()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
