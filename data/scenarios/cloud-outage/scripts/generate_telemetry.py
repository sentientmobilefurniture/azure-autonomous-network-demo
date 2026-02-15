"""
Generate telemetry CSV files for the cloud-outage scenario.

Incident: Cooling system failure in AZ-US-EAST-A causes cascading thermal
shutdowns across 5 hosts, affecting 8 VMs and 6 services.

Outputs 2 CSV files:
  - AlertStream.csv      (~5000 rows: 54h baseline + 90s incident cascade)
  - HostMetrics.csv      (~8640 rows: 72h of 5-min samples across 10 hosts)
"""

import csv
import os
import random
from datetime import datetime, timedelta, timezone

random.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "telemetry")

# ── Incident timeline ─────────────────────────────────────────────────────
INCIDENT_START = datetime(2026, 2, 6, 14, 30, 0, tzinfo=timezone.utc)

# ── Entity ID lists (cross-ref with topology) ─────────────────────────────
AZ_A_HOSTS = [
    "HOST-USE-A-01-01", "HOST-USE-A-01-02", "HOST-USE-A-02-01",
    "HOST-USE-A-02-02", "HOST-USE-A-03-01",
]
AZ_A_VMS = [
    "VM-USE-A-0101-01", "VM-USE-A-0101-02", "VM-USE-A-0102-01",
    "VM-USE-A-0201-01", "VM-USE-A-0202-01", "VM-USE-A-0202-02",
    "VM-USE-A-0301-01", "VM-USE-A-0301-02",
]
AZ_B_HOSTS = ["HOST-USE-B-01-01", "HOST-USE-B-01-02", "HOST-USE-B-02-01"]
AZ_A_RACKS = ["RACK-US-EAST-A-01", "RACK-US-EAST-A-02", "RACK-US-EAST-A-03"]
AZ_A_ID = "AZ-US-EAST-A"

IMPACTED_SERVICES = [
    "SVC-ECOMMERCE-WEB", "SVC-ECOMMERCE-API", "SVC-ECOMMERCE-DB",
    "SVC-CACHE-CLUSTER", "SVC-ML-PIPELINE", "SVC-MONITORING",
    "SVC-LOGGING", "SVC-PAYMENT",
]
FAILOVER_SERVICES = ["SVC-ECOMMERCE-WEB", "SVC-ECOMMERCE-API", "SVC-ECOMMERCE-DB"]
LB_IDS = ["LB-USE-WEB", "LB-USE-API", "LB-USE-DB", "LB-GLOBAL"]

# All nodes for baseline noise
ALL_NODES = (
    [(h, "Host") for h in AZ_A_HOSTS + AZ_B_HOSTS + ["HOST-USW-A-01-01", "HOST-EUW-A-01-01"]]
    + [(v, "VirtualMachine") for v in AZ_A_VMS + ["VM-USE-B-0101-01", "VM-USE-B-0101-02", "VM-USE-B-0102-01", "VM-USE-B-0201-01", "VM-USW-A-0101-01", "VM-EUW-A-0101-01"]]
    + [(s, "Service") for s in IMPACTED_SERVICES]
    + [(lb, "LoadBalancer") for lb in LB_IDS]
    + [(r, "Rack") for r in AZ_A_RACKS + ["RACK-US-EAST-B-01", "RACK-US-EAST-B-02"]]
)

# ── Metric defaults (the no-null baseline snapshot) ────────────────────────
def baseline_snapshot():
    return {
        "temp": round(random.uniform(22.0, 28.0), 1),
        "cpu": round(random.uniform(15.0, 45.0), 1),
        "mem": round(random.uniform(30.0, 60.0), 1),
        "disk_iops": round(random.uniform(200, 800)),
    }


def write_csv(filename, headers, rows):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"  ✓ {filename} ({len(rows)} rows)")


def ts(offset_seconds: float) -> str:
    """ISO timestamp relative to INCIDENT_START."""
    dt = INCIDENT_START + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def jitter(base: float, spread: float = 2.0) -> float:
    return base + random.uniform(-spread, spread)


# ── AlertStream generation ─────────────────────────────────────────────────
def generate_alert_stream() -> None:
    alerts = []
    counter = 0

    def add(offset, node_id, node_type, alert_type, severity, description,
            temp=None, cpu=None, mem=None, disk_iops=None):
        nonlocal counter
        counter += 1
        snap = baseline_snapshot()
        alerts.append([
            f"ALT-20260206-{counter:06d}",
            ts(offset), node_id, node_type,
            alert_type, severity, description,
            temp if temp is not None else snap["temp"],
            cpu if cpu is not None else snap["cpu"],
            mem if mem is not None else snap["mem"],
            disk_iops if disk_iops is not None else snap["disk_iops"],
        ])

    # ── Baseline: 54 hours of low-severity noise ───────────────────────────
    baseline_start = -54 * 3600
    baseline_end = -60
    num_baseline = random.randint(2800, 3400)

    baseline_alerts_by_type = {
        "Host": [
            ("HIGH_CPU", "WARNING", "CPU utilization {cpu}% — routine batch job"),
            ("HIGH_MEMORY", "MINOR", "Memory utilization {mem}% — cache warm-up"),
            ("DISK_IO_SPIKE", "MINOR", "Disk IOPS {iops} — scheduled backup"),
        ],
        "VirtualMachine": [
            ("HIGH_CPU", "WARNING", "VM CPU utilization {cpu}% — application spike"),
            ("HIGH_MEMORY", "WARNING", "VM memory utilization {mem}% — heap expansion"),
            ("OOM_WARNING", "MINOR", "OOM score approaching threshold"),
        ],
        "Service": [
            ("LATENCY_WARNING", "WARNING", "P99 latency elevated — {cpu}ms"),
            ("ERROR_RATE_SPIKE", "MINOR", "5xx error rate 0.3% — transient"),
        ],
        "LoadBalancer": [
            ("HEALTH_CHECK_FAIL", "MINOR", "Health check timeout — auto-recovered"),
            ("CONNECTION_SPIKE", "WARNING", "Active connections elevated"),
        ],
        "Rack": [
            ("POWER_FLUCTUATION", "MINOR", "Minor power fluctuation — within tolerance"),
            ("TEMP_WARNING", "MINOR", "Ambient temperature {temp}°C — slightly elevated"),
        ],
    }

    for _ in range(num_baseline):
        offset = random.uniform(baseline_start, baseline_end)
        node_id, node_type = random.choice(ALL_NODES)
        alert_defs = baseline_alerts_by_type.get(node_type, baseline_alerts_by_type["Host"])
        atype, sev, desc_tmpl = random.choice(alert_defs)
        snap = baseline_snapshot()
        desc = desc_tmpl.format(cpu=snap["cpu"], mem=snap["mem"], temp=snap["temp"], iops=snap["disk_iops"])
        add(offset, node_id, node_type, atype, sev, desc)

    # ── Incident Cascade ───────────────────────────────────────────────────
    # T+0s: COOLING_FAILURE on AZ-A
    add(0, AZ_A_ID, "AvailabilityZone", "COOLING_FAILURE", "CRITICAL",
        "CRAC Unit A1 failure — cooling loop pressure drop detected. Ambient temp rising.",
        temp=38.0, cpu=25.0)

    # T+5s: THERMAL_WARNING on all AZ-A racks
    for rack_id in AZ_A_RACKS:
        add(jitter(5), rack_id, "Rack", "THERMAL_WARNING", "MAJOR",
            f"Rack {rack_id} inlet temperature exceeding 35°C threshold",
            temp=round(random.uniform(36.0, 42.0), 1))

    # T+15s: THERMAL_WARNING on AZ-A hosts (temp climbing)
    for host_id in AZ_A_HOSTS:
        add(jitter(15), host_id, "Host", "THERMAL_WARNING", "MAJOR",
            f"Host {host_id} CPU temperature 78°C — thermal throttling imminent",
            temp=round(random.uniform(42.0, 50.0), 1), cpu=round(random.uniform(65.0, 80.0), 1))

    # T+30s: THERMAL_SHUTDOWN on first 3 hosts
    for host_id in AZ_A_HOSTS[:3]:
        add(jitter(30), host_id, "Host", "THERMAL_SHUTDOWN", "CRITICAL",
            f"Host {host_id} thermal protection activated — emergency shutdown initiated",
            temp=round(random.uniform(85.0, 95.0), 1), cpu=0.0, mem=0.0, disk_iops=0)

    # T+35s: VM_UNREACHABLE for VMs on shutdown hosts
    shutdown_host_vms = [v for v in AZ_A_VMS if any(h in v for h in ["0101", "0102", "0201"])]
    for vm_id in shutdown_host_vms:
        add(jitter(35), vm_id, "VirtualMachine", "VM_UNREACHABLE", "CRITICAL",
            f"VM {vm_id} unreachable — host thermal shutdown",
            cpu=0.0, mem=0.0, disk_iops=0)

    # T+40s: Remaining AZ-A hosts thermal throttle
    for host_id in AZ_A_HOSTS[3:]:
        add(jitter(40), host_id, "Host", "CPU_THROTTLE", "MAJOR",
            f"Host {host_id} CPU frequency reduced to 60% — thermal throttling active",
            temp=round(random.uniform(70.0, 82.0), 1), cpu=round(random.uniform(85.0, 95.0), 1))

    # T+42s: Remaining VMs HIGH_CPU and HIGH_MEMORY
    remaining_vms = [v for v in AZ_A_VMS if v not in [vm for vm in shutdown_host_vms]]
    for vm_id in remaining_vms:
        add(jitter(42), vm_id, "VirtualMachine", "HIGH_CPU", "MAJOR",
            f"VM {vm_id} CPU saturated due to host thermal throttle",
            cpu=round(random.uniform(90.0, 99.0), 1), mem=round(random.uniform(80.0, 95.0), 1))

    # T+45s: SERVICE_DEGRADATION — blast radius hits services
    for svc_id in IMPACTED_SERVICES:
        add(jitter(45), svc_id, "Service", "SERVICE_DEGRADATION", "CRITICAL",
            f"Service {svc_id} degraded — backend instances unhealthy",
            cpu=round(random.uniform(85.0, 99.0), 1))

    # T+50s: Load balancer health checks fail
    for lb_id in LB_IDS[:3]:
        add(jitter(50), lb_id, "LoadBalancer", "HEALTH_CHECK_FAIL", "CRITICAL",
            f"Load balancer {lb_id} — multiple backend targets unhealthy",
            cpu=round(random.uniform(40.0, 60.0), 1))

    # T+55s: FAILOVER_TRIGGERED on LBs for services with AZ-B replicas
    for lb_id in LB_IDS[:3]:
        add(jitter(55), lb_id, "LoadBalancer", "FAILOVER_TRIGGERED", "MAJOR",
            f"Load balancer {lb_id} — traffic rerouted to AZ-B backend pool",
            cpu=round(random.uniform(50.0, 70.0), 1))

    # T+58s: AZ-B hosts absorbing redirected traffic
    for host_id in AZ_B_HOSTS:
        add(jitter(58), host_id, "Host", "HIGH_CPU", "WARNING",
            f"Host {host_id} absorbing failover traffic — CPU elevated",
            cpu=round(random.uniform(70.0, 85.0), 1), mem=round(random.uniform(65.0, 80.0), 1))

    # T+60-90s: Flapping and duplicate alerts (alert storm tail)
    for i in range(1500):
        offset = jitter(60 + random.uniform(0, 30), spread=3.0)
        node_id, node_type = random.choice(
            [(h, "Host") for h in AZ_A_HOSTS]
            + [(v, "VirtualMachine") for v in AZ_A_VMS]
            + [(s, "Service") for s in IMPACTED_SERVICES]
        )
        alert_types = ["DUPLICATE_ALERT", "SERVICE_DEGRADATION", "VM_UNREACHABLE",
                       "HEALTH_CHECK_FAIL", "HIGH_CPU", "HIGH_MEMORY"]
        atype = random.choice(alert_types)
        sev = random.choice(["WARNING", "MINOR", "MAJOR"])
        add(offset, node_id, node_type, atype, sev,
            f"[Storm] {atype} on {node_id} — correlates with AZ-A cooling failure",
            cpu=round(random.uniform(0, 99), 1),
            mem=round(random.uniform(0, 99), 1))

    # Sort by timestamp
    alerts.sort(key=lambda r: r[1])

    headers = [
        "AlertId", "Timestamp", "SourceNodeId", "SourceNodeType",
        "AlertType", "Severity", "Description",
        "TemperatureCelsius", "CPUUtilPct", "MemoryUtilPct", "DiskIOPS",
    ]
    write_csv("AlertStream.csv", headers, alerts)


# ── HostMetrics generation ─────────────────────────────────────────────────
def generate_host_metrics() -> None:
    """72 hours of 5-min samples across all 10 hosts."""
    ALL_HOSTS = AZ_A_HOSTS + AZ_B_HOSTS + ["HOST-USW-A-01-01", "HOST-EUW-A-01-01"]
    start_time = INCIDENT_START - timedelta(hours=60)
    interval_minutes = 5
    num_samples = (72 * 60) // interval_minutes  # 864 per host

    baseline_profiles = {
        "HOST-USE-A-01-01": {"cpu": 40.0, "mem": 55.0, "temp": 25.0, "iops": 500},
        "HOST-USE-A-01-02": {"cpu": 35.0, "mem": 50.0, "temp": 24.0, "iops": 450},
        "HOST-USE-A-02-01": {"cpu": 60.0, "mem": 70.0, "temp": 27.0, "iops": 1200},
        "HOST-USE-A-02-02": {"cpu": 55.0, "mem": 65.0, "temp": 26.0, "iops": 900},
        "HOST-USE-A-03-01": {"cpu": 25.0, "mem": 40.0, "temp": 23.0, "iops": 300},
        "HOST-USE-B-01-01": {"cpu": 30.0, "mem": 45.0, "temp": 24.0, "iops": 400},
        "HOST-USE-B-01-02": {"cpu": 45.0, "mem": 55.0, "temp": 25.0, "iops": 600},
        "HOST-USE-B-02-01": {"cpu": 25.0, "mem": 40.0, "temp": 23.0, "iops": 350},
        "HOST-USW-A-01-01": {"cpu": 30.0, "mem": 45.0, "temp": 24.0, "iops": 400},
        "HOST-EUW-A-01-01": {"cpu": 28.0, "mem": 42.0, "temp": 23.0, "iops": 380},
    }

    rows = []
    metric_counter = 0
    for host_id in ALL_HOSTS:
        profile = baseline_profiles.get(host_id, {"cpu": 30.0, "mem": 45.0, "temp": 24.0, "iops": 400})
        for i in range(num_samples):
            metric_counter += 1
            sample_time = start_time + timedelta(minutes=i * interval_minutes)
            sample_ts = sample_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            is_az_a = host_id in AZ_A_HOSTS
            is_az_b = host_id in AZ_B_HOSTS
            is_post_incident = sample_time >= INCIDENT_START
            is_shutdown = is_az_a and host_id in AZ_A_HOSTS[:3] and is_post_incident

            if is_shutdown:
                # Hosts that thermal-shutdown: metrics go to zero/extreme
                rows.append([
                    f"HM-{metric_counter:08d}", host_id, sample_ts,
                    0.0, 0.0, 95.0, 0,
                ])
            elif is_az_a and is_post_incident:
                # Throttled AZ-A hosts (remaining ones)
                rows.append([
                    f"HM-{metric_counter:08d}", host_id, sample_ts,
                    round(random.uniform(85, 99), 1),
                    round(random.uniform(80, 95), 1),
                    round(random.uniform(70, 85), 1),
                    round(random.uniform(100, 300)),
                ])
            elif is_az_b and is_post_incident:
                # AZ-B absorbing failover traffic
                rows.append([
                    f"HM-{metric_counter:08d}", host_id, sample_ts,
                    round(profile["cpu"] + random.uniform(20, 40), 1),
                    round(profile["mem"] + random.uniform(15, 30), 1),
                    round(profile["temp"] + random.uniform(2, 5), 1),
                    round(profile["iops"] + random.uniform(200, 500)),
                ])
            else:
                # Normal baseline with slight variance
                rows.append([
                    f"HM-{metric_counter:08d}", host_id, sample_ts,
                    round(profile["cpu"] + random.uniform(-5, 5), 1),
                    round(profile["mem"] + random.uniform(-3, 3), 1),
                    round(profile["temp"] + random.uniform(-1, 1), 1),
                    round(profile["iops"] + random.uniform(-50, 50)),
                ])

    headers = [
        "MetricId", "HostId", "Timestamp",
        "CPUUtilPct", "MemoryUtilPct", "TemperatureCelsius", "DiskIOPS",
    ]
    write_csv("HostMetrics.csv", headers, rows)


def main() -> None:
    print("Generating cloud-outage telemetry data ...")
    generate_alert_stream()
    generate_host_metrics()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
