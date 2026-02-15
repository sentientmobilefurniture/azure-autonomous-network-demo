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


# ── Regions ────────────────────────────────────────────────────────────────
def generate_regions() -> None:
    headers = ["RegionId", "RegionName", "Country", "Provider"]
    rows = [
        ["REGION-US-EAST", "US East", "United States", "CloudCorp"],
        ["REGION-US-WEST", "US West", "United States", "CloudCorp"],
        ["REGION-EU-WEST", "EU West", "Ireland", "CloudCorp"],
    ]
    write_csv("DimRegion.csv", headers, rows)


# ── Availability Zones ─────────────────────────────────────────────────────
def generate_availability_zones() -> None:
    headers = ["AZId", "AZName", "RegionId", "CoolingSystem", "PowerFeedCount"]
    rows = [
        ["AZ-US-EAST-A", "US-East-AZ-A", "REGION-US-EAST", "CRAC-UNIT-A1", 2],
        ["AZ-US-EAST-B", "US-East-AZ-B", "REGION-US-EAST", "CRAC-UNIT-B1", 2],
        ["AZ-US-WEST-A", "US-West-AZ-A", "REGION-US-WEST", "CRAC-UNIT-A1", 2],
        ["AZ-EU-WEST-A", "EU-West-AZ-A", "REGION-EU-WEST", "CRAC-UNIT-A1", 2],
    ]
    write_csv("DimAvailabilityZone.csv", headers, rows)


# ── Racks ──────────────────────────────────────────────────────────────────
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


# ── Hosts ──────────────────────────────────────────────────────────────────
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
        ["HOST-EUW-A-01-01", "dub-host-01", "RACK-EU-WEST-A-01", 64, 256, "Lenovo"],
    ]
    write_csv("DimHost.csv", headers, rows)


# ── Virtual Machines ───────────────────────────────────────────────────────
def generate_virtual_machines() -> None:
    headers = ["VMId", "VMName", "HostId", "ServiceId", "vCPUs", "MemoryGB", "OSType"]
    rows = [
        # VMs on AZ-A hosts (impacted)
        ["VM-USE-A-0101-01", "web-frontend-1", "HOST-USE-A-01-01", "SVC-ECOMMERCE-WEB", 4, 16, "Linux"],
        ["VM-USE-A-0101-02", "web-frontend-2", "HOST-USE-A-01-01", "SVC-ECOMMERCE-WEB", 4, 16, "Linux"],
        ["VM-USE-A-0102-01", "api-gateway-1", "HOST-USE-A-01-02", "SVC-ECOMMERCE-API", 8, 32, "Linux"],
        ["VM-USE-A-0201-01", "db-primary", "HOST-USE-A-02-01", "SVC-ECOMMERCE-DB", 16, 128, "Linux"],
        ["VM-USE-A-0202-01", "cache-node-1", "HOST-USE-A-02-02", "SVC-CACHE-CLUSTER", 8, 64, "Linux"],
        ["VM-USE-A-0202-02", "ml-trainer-1", "HOST-USE-A-02-02", "SVC-ML-PIPELINE", 32, 256, "Linux"],
        ["VM-USE-A-0301-01", "monitoring-1", "HOST-USE-A-03-01", "SVC-MONITORING", 4, 16, "Linux"],
        ["VM-USE-A-0301-02", "log-collector-1", "HOST-USE-A-03-01", "SVC-LOGGING", 4, 16, "Linux"],
        # VMs on AZ-B hosts (failover)
        ["VM-USE-B-0101-01", "web-frontend-3", "HOST-USE-B-01-01", "SVC-ECOMMERCE-WEB", 4, 16, "Linux"],
        ["VM-USE-B-0101-02", "api-gateway-2", "HOST-USE-B-01-01", "SVC-ECOMMERCE-API", 8, 32, "Linux"],
        ["VM-USE-B-0102-01", "db-replica", "HOST-USE-B-01-02", "SVC-ECOMMERCE-DB", 16, 128, "Linux"],
        ["VM-USE-B-0201-01", "cache-node-2", "HOST-USE-B-02-01", "SVC-CACHE-CLUSTER", 8, 64, "Linux"],
        # US-West VM
        ["VM-USW-A-0101-01", "cdn-edge-1", "HOST-USW-A-01-01", "SVC-CDN", 4, 16, "Linux"],
        # EU-West VM
        ["VM-EUW-A-0101-01", "cdn-edge-2", "HOST-EUW-A-01-01", "SVC-CDN", 4, 16, "Linux"],
    ]
    write_csv("DimVirtualMachine.csv", headers, rows)


# ── Load Balancers ─────────────────────────────────────────────────────────
def generate_load_balancers() -> None:
    headers = ["LBId", "LBName", "LBType", "RegionId", "Algorithm", "HealthCheckPath"]
    rows = [
        ["LB-USE-WEB", "WebLB-USEast", "Application", "REGION-US-EAST", "RoundRobin", "/healthz"],
        ["LB-USE-API", "ApiLB-USEast", "Application", "REGION-US-EAST", "LeastConn", "/api/health"],
        ["LB-USE-DB", "DbLB-USEast", "Network", "REGION-US-EAST", "IPHash", "/"],
        ["LB-GLOBAL", "GlobalLB", "DNS", "REGION-US-EAST", "GeoRouting", "/"],
    ]
    write_csv("DimLoadBalancer.csv", headers, rows)


# ── Services ───────────────────────────────────────────────────────────────
def generate_services() -> None:
    headers = ["ServiceId", "ServiceName", "ServiceType", "Tier", "Owner"]
    rows = [
        ["SVC-ECOMMERCE-WEB", "E-Commerce Web Frontend", "WebApp", "Tier-1", "WebTeam"],
        ["SVC-ECOMMERCE-API", "E-Commerce API Gateway", "API", "Tier-1", "PlatformTeam"],
        ["SVC-ECOMMERCE-DB", "E-Commerce Database", "Database", "Tier-0", "DataTeam"],
        ["SVC-CACHE-CLUSTER", "Redis Cache Cluster", "Cache", "Tier-1", "PlatformTeam"],
        ["SVC-ML-PIPELINE", "ML Training Pipeline", "Compute", "Tier-2", "MLTeam"],
        ["SVC-CDN", "Content Delivery Network", "CDN", "Tier-1", "InfraTeam"],
        ["SVC-MONITORING", "Monitoring Stack", "Observability", "Tier-0", "SRETeam"],
        ["SVC-LOGGING", "Centralized Logging", "Observability", "Tier-0", "SRETeam"],
        ["SVC-AUTH", "Authentication Service", "Security", "Tier-0", "SecurityTeam"],
        ["SVC-PAYMENT", "Payment Processing", "Financial", "Tier-0", "PaymentTeam"],
    ]
    write_csv("DimService.csv", headers, rows)


# ── SLA Policies ───────────────────────────────────────────────────────────
def generate_sla_policies() -> None:
    headers = ["SLAId", "SLAName", "ServiceId", "UptimePct", "MaxLatencyMs", "RPOMinutes"]
    rows = [
        ["SLA-ECOM-PLAT", "E-Commerce Platform SLA", "SVC-ECOMMERCE-WEB", 99.99, 200, 5],
        ["SLA-ECOM-DB", "E-Commerce Database SLA", "SVC-ECOMMERCE-DB", 99.999, 50, 1],
        ["SLA-PAYMENT", "Payment Processing SLA", "SVC-PAYMENT", 99.999, 100, 0],
        ["SLA-CDN", "CDN Availability SLA", "SVC-CDN", 99.95, 500, 60],
        ["SLA-ML", "ML Pipeline SLA", "SVC-ML-PIPELINE", 99.9, 5000, 1440],
    ]
    write_csv("DimSLAPolicy.csv", headers, rows)


def main() -> None:
    print("Generating cloud-outage topology data ...")
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
