"""
Generate AlertStream telemetry for the hello-world scenario.

Produces ~40 rows:
  - ~30 baseline alerts over 6 hours (low severity noise)
  - ~10 incident alerts over 60 seconds (SRV-ALPHA-01 crash cascade)
"""

import csv
import os
import random
from datetime import datetime, timedelta, timezone

random.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "telemetry")

# Incident starts at this time
INCIDENT_START = datetime(2026, 2, 6, 14, 30, 0, tzinfo=timezone.utc)

# Entity IDs (must match topology exactly)
SERVERS = ["SRV-ALPHA-01", "SRV-BETA-01"]
APPS = ["APP-WEB-01", "APP-API-01", "APP-WORKER-01"]
DATABASES = ["DB-PRIMARY-01", "DB-REPLICA-01"]

ALL_NODES = (
    [(s, "Server") for s in SERVERS]
    + [(a, "Application") for a in APPS]
    + [(d, "Database") for d in DATABASES]
)

counter = 0
alerts: list[list] = []


def ts(offset_seconds: float) -> str:
    """ISO timestamp relative to INCIDENT_START."""
    return (INCIDENT_START + timedelta(seconds=offset_seconds)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def normal_cpu() -> float:
    return round(random.uniform(15, 55), 1)


def normal_memory() -> float:
    return round(random.uniform(30, 65), 1)


def normal_disk() -> float:
    return round(random.uniform(20, 55), 1)


def normal_response() -> float:
    return round(random.uniform(50, 180), 1)


def add(offset, node_id, node_type, alert_type, severity, description,
        cpu=None, mem=None, disk=None, resp=None):
    global counter
    counter += 1
    alerts.append([
        f"ALT-20260206-{counter:06d}",
        ts(offset),
        node_id,
        node_type,
        alert_type,
        severity,
        description,
        cpu if cpu is not None else normal_cpu(),
        mem if mem is not None else normal_memory(),
        disk if disk is not None else normal_disk(),
        resp if resp is not None else normal_response(),
    ])


def generate_baseline():
    """6 hours of low-severity noise before the incident."""
    baseline_start = -6 * 3600  # 6 hours before incident
    for i in range(30):
        offset = baseline_start + i * 720  # one alert every ~12 min
        node_id, node_type = random.choice(ALL_NODES)
        alert_type = random.choice(["HEALTH_CHECK", "METRIC_WARNING", "LOG_ANOMALY"])
        add(offset, node_id, node_type, alert_type, "WARNING",
            f"Routine {alert_type.lower()} on {node_id}")


def generate_incident():
    """SRV-ALPHA-01 crash cascade over ~60 seconds."""
    # T+0: Server crash
    add(0, "SRV-ALPHA-01", "Server", "SERVER_DOWN", "CRITICAL",
        "Server SRV-ALPHA-01 unresponsive — kernel panic detected",
        cpu=0.0, mem=0.0, disk=0.0, resp=9999.0)

    # T+2: Web app unreachable
    add(2, "APP-WEB-01", "Application", "APP_UNREACHABLE", "CRITICAL",
        "APP-WEB-01 health check failed — host SRV-ALPHA-01 down",
        cpu=0.0, mem=0.0, resp=9999.0)

    # T+3: API app unreachable
    add(3, "APP-API-01", "Application", "APP_UNREACHABLE", "CRITICAL",
        "APP-API-01 health check failed — host SRV-ALPHA-01 down",
        cpu=0.0, mem=0.0, resp=9999.0)

    # T+5: Database connection spike on primary (worker still running)
    add(5, "DB-PRIMARY-01", "Database", "CONNECTION_SPIKE", "WARNING",
        "Connection pool spike — APP-API-01 connections dropped",
        cpu=75.0, mem=80.0)

    # T+8: Worker detects API unavailable
    add(8, "APP-WORKER-01", "Application", "DEPENDENCY_FAILURE", "MAJOR",
        "APP-WORKER-01 cannot reach APP-API-01 — job queue stalling",
        resp=5000.0)

    # T+15: Replica connection drop
    add(15, "DB-REPLICA-01", "Database", "CONNECTION_DROP", "WARNING",
        "Read replica lost all connections from APP-WEB-01",
        cpu=10.0, mem=25.0)

    # T+30: Worker retry exhaustion
    add(30, "APP-WORKER-01", "Application", "RETRY_EXHAUSTED", "MAJOR",
        "APP-WORKER-01 retry limit reached for API calls",
        resp=9999.0)

    # T+45: Server still down confirmation
    add(45, "SRV-ALPHA-01", "Server", "SERVER_DOWN", "CRITICAL",
        "SRV-ALPHA-01 still unreachable after 45s — IPMI unresponsive",
        cpu=0.0, mem=0.0, disk=0.0, resp=9999.0)

    # T+50: Database primary CPU settling
    add(50, "DB-PRIMARY-01", "Database", "METRIC_WARNING", "WARNING",
        "DB-PRIMARY-01 CPU returning to normal after connection cleanup",
        cpu=45.0, mem=60.0)

    # T+60: Worker partial recovery
    add(60, "APP-WORKER-01", "Application", "HEALTH_CHECK", "WARNING",
        "APP-WORKER-01 processing from local queue only",
        resp=500.0)


def main():
    generate_baseline()
    generate_incident()

    # Sort by timestamp
    alerts.sort(key=lambda r: r[1])

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "AlertStream.csv")
    headers = [
        "AlertId", "Timestamp", "SourceNodeId", "SourceNodeType",
        "AlertType", "Severity", "Description",
        "CPUUtilPct", "MemoryUtilPct", "DiskUsagePct", "ResponseTimeMs",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(alerts)
    print(f"  ✓ AlertStream.csv ({len(alerts)} rows)")
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
