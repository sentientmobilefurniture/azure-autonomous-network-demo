"""
Generate static topology CSV files for the hello-world scenario.

Outputs 3 CSV files:
  - DimServer.csv       (2 rows)
  - DimApplication.csv  (3 rows)
  - DimDatabase.csv     (2 rows)
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


def generate_servers() -> None:
    headers = ["ServerId", "Hostname", "OS", "CPUCores", "MemoryGB"]
    rows = [
        ["SRV-ALPHA-01", "alpha-prod-01", "Ubuntu 22.04", 32, 128],
        ["SRV-BETA-01", "beta-prod-01", "Ubuntu 22.04", 16, 64],
    ]
    write_csv("DimServer.csv", headers, rows)


def generate_applications() -> None:
    headers = ["AppId", "AppName", "AppType", "ServerId", "DatabaseId"]
    rows = [
        ["APP-WEB-01", "Web Frontend", "web", "SRV-ALPHA-01", "DB-REPLICA-01"],
        ["APP-API-01", "API Backend", "api", "SRV-ALPHA-01", "DB-PRIMARY-01"],
        ["APP-WORKER-01", "Background Worker", "worker", "SRV-BETA-01", "DB-PRIMARY-01"],
    ]
    write_csv("DimApplication.csv", headers, rows)


def generate_databases() -> None:
    headers = ["DatabaseId", "DatabaseName", "Engine", "SizeGB"]
    rows = [
        ["DB-PRIMARY-01", "Primary PostgreSQL", "PostgreSQL 16", 500],
        ["DB-REPLICA-01", "Read Replica", "PostgreSQL 16", 500],
    ]
    write_csv("DimDatabase.csv", headers, rows)


def main() -> None:
    print("Generating hello-world topology data...")
    generate_servers()
    generate_databases()
    generate_applications()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
