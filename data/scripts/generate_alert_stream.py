"""
Generate alert stream and link telemetry CSV files for Cosmos DB NoSQL.

Outputs 2 CSV files:
  - AlertStream.csv     (~5,000 rows) — 54h baseline + cascading alert storm over 90 seconds
  - LinkTelemetry.csv   (~8,600 rows) — 72h baseline + incident link metrics
"""

import csv
import os
import random
from datetime import datetime, timedelta, timezone

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "telemetry")

# Incident start time
INCIDENT_START = datetime(2026, 2, 6, 14, 30, 0, tzinfo=timezone.utc)

# Seed for reproducibility
random.seed(42)

# --------------------------------------------------------------------------- #
#  Topology references (must match network entity tables)
# --------------------------------------------------------------------------- #

CORE_ROUTERS = ["CORE-SYD-01", "CORE-MEL-01", "CORE-BNE-01"]
AGG_SWITCHES = [
    "AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01",
    "AGG-MEL-EAST-01", "AGG-MEL-WEST-01",
    "AGG-BNE-CENTRAL-01", "AGG-BNE-SOUTH-01",
]
BASE_STATIONS = [
    "GNB-SYD-2041", "GNB-SYD-2042", "GNB-SYD-2043",
    "GNB-MEL-3011", "GNB-MEL-3012", "GNB-MEL-3021",
    "GNB-BNE-4011", "GNB-BNE-4012",
]
TRANSPORT_LINKS = [
    "LINK-SYD-MEL-FIBRE-01", "LINK-SYD-MEL-FIBRE-02",
    "LINK-SYD-BNE-FIBRE-01", "LINK-MEL-BNE-FIBRE-01",
    "LINK-SYD-AGG-NORTH-01", "LINK-SYD-AGG-SOUTH-01",
    "LINK-MEL-AGG-EAST-01", "LINK-MEL-AGG-WEST-01",
    "LINK-BNE-AGG-CENTRAL-01", "LINK-BNE-AGG-SOUTH-01",
]
SERVICES = [
    "VPN-ACME-CORP", "VPN-BIGBANK", "VPN-OZMINE",
    "BB-BUNDLE-SYD-NORTH", "BB-BUNDLE-MEL-EAST", "BB-BUNDLE-BNE-CENTRAL",
    "MOB-5G-SYD-2041", "MOB-5G-SYD-2042", "MOB-5G-MEL-3011", "MOB-5G-BNE-4011",
]

# Nodes impacted by the SYD-MEL fibre-01 cut (downstream)
IMPACTED_SYD_ROUTERS = ["CORE-SYD-01", "CORE-MEL-01"]
IMPACTED_AGG = ["AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01", "AGG-MEL-EAST-01", "AGG-MEL-WEST-01"]
IMPACTED_GNB = ["GNB-SYD-2041", "GNB-SYD-2042", "GNB-SYD-2043", "GNB-MEL-3011", "GNB-MEL-3012", "GNB-MEL-3021"]
IMPACTED_SERVICES = ["VPN-ACME-CORP", "VPN-BIGBANK", "BB-BUNDLE-SYD-NORTH", "BB-BUNDLE-MEL-EAST", "MOB-5G-SYD-2041", "MOB-5G-SYD-2042", "MOB-5G-MEL-3011"]

# Links used by the indirect reroute path (SYD→BNE→MEL) — these see increased load
REROUTE_LINKS = ["LINK-SYD-BNE-FIBRE-01", "LINK-MEL-BNE-FIBRE-01"]


def write_csv(filename: str, headers: list[str], rows: list[list]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"  ✓ {filename} ({len(rows)} rows)")


def ts(offset_seconds: float) -> str:
    """Return ISO timestamp offset from incident start."""
    return (INCIDENT_START + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def jitter(base: float, spread: float = 2.0) -> float:
    """Add random jitter to a time offset."""
    return base + random.uniform(-spread, spread)


def generate_alert_stream() -> None:
    """
    Generates ~5,000 alerts: ~3,000 baseline over 54 hours (2 days 6h) +
    ~2,000 storm alerts over a 90-second cascade following a fibre cut.

    IMPORTANT: Every row includes ALL FOUR numeric telemetry columns
    (OpticalPowerDbm, BitErrorRate, CPUUtilPct, PacketLossPct) — no nulls.
    The alert type indicates which metric triggered the threshold, but the
    row captures a full telemetry snapshot of the node at that instant. This
    mirrors real monitoring systems (SNMP polls all OIDs) and is required by
    downstream anomaly detection, which rejects rows with null values.

    Baseline period provides "normal" low-severity background noise
    (~1 alert per minute) so the Anomaly Detector can distinguish
    the storm spike from steady-state behavior.

    Alert cascade timeline:
      T+0s     LINK_DOWN on LINK-SYD-MEL-FIBRE-01                    (1)
      T+2s     BGP_PEER_LOSS                                         (2)
      T+5s     OSPF_ADJACENCY_DOWN                                   (4)
      T+10s    ROUTE_WITHDRAWAL                                      (~20)
      T+15s    HIGH_CPU on routers reconverging                       (~50)
      T+30s    PACKET_LOSS_THRESHOLD on downstream agg/base           (~200)
      T+60s    SERVICE_DEGRADATION on customer services               (~500)
      T+90s    DUPLICATE_ALERT flapping/repeated                      fills to ~2000
    """
    headers = [
        "AlertId", "Timestamp", "SourceNodeId", "SourceNodeType",
        "AlertType", "Severity", "Description",
        "OpticalPowerDbm", "BitErrorRate", "CPUUtilPct", "PacketLossPct",
    ]

    alerts: list[list] = []
    alert_counter = 0

    # ── Normal-range telemetry values (full snapshot per row) ───────
    def normal_optical() -> float:
        """Normal optical power: -3.5 to -2.5 dBm."""
        return round(random.uniform(-3.5, -2.5), 1)

    def normal_ber() -> float:
        """Normal bit error rate: ~1e-14 to 1e-11 (negligible)."""
        return round(random.uniform(1e-14, 1e-11), 15)

    def normal_cpu() -> float:
        """Normal CPU: 15-45%."""
        return round(random.uniform(15, 45), 1)

    def normal_pkt_loss() -> float:
        """Normal packet loss: 0.0-0.05%."""
        return round(random.uniform(0.0, 0.05), 3)

    def baseline_snapshot() -> dict:
        """Full telemetry snapshot with all-normal values."""
        return {
            "optical": normal_optical(),
            "ber": normal_ber(),
            "cpu": normal_cpu(),
            "pkt_loss": normal_pkt_loss(),
        }

    def add(offset: float, node_id: str, node_type: str, alert_type: str,
            severity: str, description: str,
            optical: float | None = None, ber: float | None = None,
            cpu: float | None = None, pkt_loss: float | None = None) -> None:
        """Add an alert row. Any metric not explicitly set gets a normal-range value."""
        nonlocal alert_counter
        alert_counter += 1
        snap = baseline_snapshot()
        alerts.append([
            f"ALT-20260206-{alert_counter:06d}",
            ts(offset), node_id, node_type,
            alert_type, severity, description,
            optical if optical is not None else snap["optical"],
            ber if ber is not None else snap["ber"],
            cpu if cpu is not None else snap["cpu"],
            pkt_loss if pkt_loss is not None else snap["pkt_loss"],
        ])

    # ── Baseline: Normal alert activity for 54 hours before incident ──
    # Sporadic low-severity alerts at ~1 per minute (typical NOC background noise)
    baseline_start = -54 * 3600  # 54 hours (2 days 6h) before incident
    baseline_end = -60            # stop 1 minute before the storm
    baseline_alerts_by_type = {
        "CoreRouter": [
            ("HIGH_CPU", "WARNING", "CPU utilization {cpu}% — routine process spike"),
            ("PACKET_LOSS_THRESHOLD", "MINOR", "Packet loss {pkt}% — transient microloop"),
        ],
        "AggSwitch": [
            ("HIGH_CPU", "WARNING", "CPU utilization {cpu}% — routine process spike"),
            ("PACKET_LOSS_THRESHOLD", "MINOR", "Packet loss {pkt}% — transient microloop"),
            ("DUPLICATE_ALERT", "MINOR", "Periodic keepalive timeout — auto-recovered"),
        ],
        "BaseStation": [
            ("DUPLICATE_ALERT", "MINOR", "Periodic keepalive timeout — auto-recovered"),
            ("SERVICE_DEGRADATION", "MINOR", "Brief latency increase on link — within SLA"),
            ("PACKET_LOSS_THRESHOLD", "MINOR", "Packet loss {pkt}% — transient microloop"),
        ],
        "TransportLink": [
            ("PACKET_LOSS_THRESHOLD", "MINOR", "Packet loss {pkt}% — transient microloop"),
            ("DUPLICATE_ALERT", "MINOR", "Periodic keepalive timeout — auto-recovered"),
            ("SERVICE_DEGRADATION", "MINOR", "Brief latency increase on link — within SLA"),
        ],
    }
    baseline_nodes = (
        [(r, "CoreRouter") for r in CORE_ROUTERS]
        + [(s, "AggSwitch") for s in AGG_SWITCHES]
        + [(b, "BaseStation") for b in BASE_STATIONS]
        + [(l, "TransportLink") for l in TRANSPORT_LINKS]
    )
    num_baseline_alerts = random.randint(2800, 3400)  # ~1/min over 54 hours
    for _ in range(num_baseline_alerts):
        offset = random.uniform(baseline_start, baseline_end)
        node, node_type = random.choice(baseline_nodes)
        alert_def = random.choice(baseline_alerts_by_type[node_type])
        # Slightly elevated values for the triggering metric (still "normal-ish")
        cpu_val = round(random.uniform(55, 75), 1) if "cpu" in alert_def[2] else None
        pkt_val = round(random.uniform(0.1, 0.8), 2) if "pkt" in alert_def[2] else None
        desc = alert_def[2]
        if cpu_val is not None:
            desc = desc.format(cpu=cpu_val, pkt="")
        elif pkt_val is not None:
            desc = desc.format(cpu="", pkt=pkt_val)
        add(offset, node, node_type, alert_def[0],
            alert_def[1], desc, cpu=cpu_val, pkt_loss=pkt_val)

    # ── T+0s: Root cause ────────────────────────────────────────────
    # Loss of light: optical power collapses, BER maxes out
    add(0.0, "LINK-SYD-MEL-FIBRE-01", "TransportLink", "LINK_DOWN",
        "CRITICAL", "Physical link loss of light detected",
        optical=-40.0, ber=1.0, pkt_loss=100.0, cpu=normal_cpu())

    # ── T+2s: BGP peer loss ─────────────────────────────────────────
    # Routers see CPU spike as BGP reconverges, packet loss climbs
    add(2.1, "CORE-SYD-01", "CoreRouter", "BGP_PEER_LOSS",
        "CRITICAL", "BGP peer CORE-MEL-01 (AS64513) unreachable via LINK-SYD-MEL-FIBRE-01",
        cpu=round(random.uniform(78, 88), 1), pkt_loss=round(random.uniform(2, 8), 2))
    add(2.3, "CORE-MEL-01", "CoreRouter", "BGP_PEER_LOSS",
        "CRITICAL", "BGP peer CORE-SYD-01 (AS64512) unreachable via LINK-SYD-MEL-FIBRE-01",
        cpu=round(random.uniform(78, 88), 1), pkt_loss=round(random.uniform(2, 8), 2))

    # ── T+5s: OSPF adjacency drops ─────────────────────────────────
    for i, iface in enumerate(["Gi0/0/0/1", "Gi0/0/0/2", "Gi0/0/0/3", "Gi0/0/0/4"]):
        router = IMPACTED_SYD_ROUTERS[i % 2]
        add(jitter(5.0, 1.0), router, "CoreRouter", "OSPF_ADJACENCY_DOWN",
            "MAJOR", f"OSPF adjacency lost on interface {iface}",
            cpu=round(random.uniform(80, 92), 1), pkt_loss=round(random.uniform(3, 12), 2))

    # ── T+10s: Route withdrawals ────────────────────────────────────
    prefixes = [
        "10.1.0.0/16", "10.2.0.0/16", "10.3.0.0/16", "10.4.0.0/16",
        "172.16.0.0/12", "172.17.0.0/16", "172.18.0.0/16",
        "192.168.1.0/24", "192.168.2.0/24", "192.168.3.0/24",
        "10.10.0.0/16", "10.20.0.0/16", "10.30.0.0/16",
        "10.100.0.0/16", "10.101.0.0/16", "10.102.0.0/16",
        "10.200.0.0/16", "10.201.0.0/16", "10.202.0.0/16", "10.203.0.0/16",
    ]
    for prefix in prefixes:
        router = random.choice(IMPACTED_SYD_ROUTERS)
        add(jitter(10.0, 3.0), router, "CoreRouter", "ROUTE_WITHDRAWAL",
            "MAJOR", f"Route {prefix} withdrawn — next-hop unreachable via SYD-MEL corridor",
            cpu=round(random.uniform(82, 95), 1), pkt_loss=round(random.uniform(5, 15), 2))

    # ── T+15s: HIGH_CPU on reconverging routers ─────────────────────
    for _ in range(50):
        router = random.choice(IMPACTED_SYD_ROUTERS + IMPACTED_AGG[:2])
        cpu = round(random.uniform(85, 99), 1)
        add(jitter(15.0, 5.0), router,
            "CoreRouter" if router.startswith("CORE") else "AggSwitch",
            "HIGH_CPU", "WARNING",
            f"CPU utilization {cpu}% — route reconvergence in progress",
            cpu=cpu, pkt_loss=round(random.uniform(1, 10), 2))

    # ── T+30s: Packet loss on downstream links ─────────────────────
    for _ in range(200):
        node = random.choice(IMPACTED_AGG + IMPACTED_GNB)
        node_type = "AggSwitch" if node.startswith("AGG") else "BaseStation"
        pkt = round(random.uniform(0.5, 15.0), 2)
        add(jitter(30.0, 10.0), node, node_type, "PACKET_LOSS_THRESHOLD",
            "MAJOR", f"Packet loss {pkt}% exceeded threshold on upstream path",
            pkt_loss=pkt, cpu=round(random.uniform(50, 80), 1))

    # ── T+60s: Service degradation ──────────────────────────────────
    svc_descriptions = {
        "EnterpriseVPN": "VPN tunnel unreachable — primary MPLS path down",
        "Broadband": "Customer broadband degraded — upstream path impacted",
        "Mobile5G": "Backhaul degradation — voice quality MOS below threshold",
    }
    for _ in range(500):
        svc = random.choice(IMPACTED_SERVICES)
        if svc.startswith("VPN"):
            svc_type = "EnterpriseVPN"
            severity = "CRITICAL"
        elif svc.startswith("BB"):
            svc_type = "Broadband"
            severity = "MAJOR"
        else:
            svc_type = "Mobile5G"
            severity = "WARNING"
        pkt = round(random.uniform(1.0, 25.0), 2)
        add(jitter(60.0, 15.0), svc, "Service", "SERVICE_DEGRADATION",
            severity, svc_descriptions[svc_type],
            pkt_loss=pkt, cpu=round(random.uniform(40, 75), 1))

    # ── T+70-90s: Duplicate / flapping alerts to fill to ~2000 ──────
    target_total = 2000
    remaining = target_total - len(alerts)
    all_impacted = IMPACTED_SYD_ROUTERS + IMPACTED_AGG + IMPACTED_GNB + IMPACTED_SERVICES
    dup_types = ["DUPLICATE_ALERT", "PACKET_LOSS_THRESHOLD", "HIGH_CPU", "SERVICE_DEGRADATION"]
    for _ in range(max(0, remaining)):
        node = random.choice(all_impacted)
        if node.startswith("CORE"):
            node_type = "CoreRouter"
        elif node.startswith("AGG"):
            node_type = "AggSwitch"
        elif node.startswith("GNB"):
            node_type = "BaseStation"
        else:
            node_type = "Service"
        alert_type = random.choice(dup_types)
        # Flapping: metrics oscillating between bad and recovering
        add(jitter(80.0, 10.0), node, node_type, alert_type,
            random.choice(["WARNING", "MAJOR"]),
            f"Repeated alert — {alert_type.lower().replace('_', ' ')} on {node}",
            cpu=round(random.uniform(60, 95), 1),
            pkt_loss=round(random.uniform(0.5, 20), 2))

    # Sort by timestamp
    alerts.sort(key=lambda r: r[1])
    write_csv("AlertStream.csv", headers, alerts)


def generate_link_telemetry() -> None:
    """
    Generate baseline + incident link telemetry for all transport links.
    72h of 5-min samples per link (60h before + 12h after incident), with anomaly at incident time.

    After the fibre cut:
      - FIBRE-01: dead (0% util, loss of light)
      - FIBRE-02: jumps to ~70-82% (direct failover)
      - SYD-BNE + MEL-BNE: increase by ~15-20% (indirect reroute traffic)
      - Agg uplinks: baseline or slight increase
    """
    headers = ["LinkId", "Timestamp", "UtilizationPct", "OpticalPowerDbm", "BitErrorRate", "LatencyMs"]
    rows: list[list] = []

    # Generate 72 hours of data at 5-min intervals (60h before + 12h after)
    start_time = INCIDENT_START - timedelta(hours=60)
    interval_minutes = 5
    num_samples = (72 * 60) // interval_minutes  # 864 per link

    # Baseline utilisation profiles per link type
    baseline_profiles = {
        # Backbone links
        "LINK-SYD-MEL-FIBRE-01": {"util": 55.0, "latency": (4, 8)},
        "LINK-SYD-MEL-FIBRE-02": {"util": 38.0, "latency": (4, 8)},
        "LINK-SYD-BNE-FIBRE-01": {"util": 42.0, "latency": (6, 12)},
        "LINK-MEL-BNE-FIBRE-01": {"util": 35.0, "latency": (8, 14)},
        # Agg uplinks — lower utilisation
        "LINK-SYD-AGG-NORTH-01": {"util": 45.0, "latency": (1, 3)},
        "LINK-SYD-AGG-SOUTH-01": {"util": 40.0, "latency": (1, 3)},
        "LINK-MEL-AGG-EAST-01":  {"util": 38.0, "latency": (1, 3)},
        "LINK-MEL-AGG-WEST-01":  {"util": 35.0, "latency": (1, 3)},
        "LINK-BNE-AGG-CENTRAL-01": {"util": 32.0, "latency": (1, 3)},
        "LINK-BNE-AGG-SOUTH-01":   {"util": 28.0, "latency": (1, 3)},
    }

    for link in TRANSPORT_LINKS:
        is_cut_link = link == "LINK-SYD-MEL-FIBRE-01"
        is_backup_link = link == "LINK-SYD-MEL-FIBRE-02"
        is_reroute_link = link in REROUTE_LINKS
        profile = baseline_profiles.get(link, {"util": 40.0, "latency": (4, 12)})

        for i in range(num_samples):
            sample_time = start_time + timedelta(minutes=i * interval_minutes)
            sample_ts = sample_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            # After incident for the cut link: anomalous values
            if is_cut_link and sample_time >= INCIDENT_START:
                rows.append([
                    link, sample_ts,
                    0.0,       # no traffic
                    -40.0,     # loss of light
                    1.0,       # max BER
                    9999.0,    # effectively infinite latency
                ])
            # After incident for backup link: increased utilisation
            elif is_backup_link and sample_time >= INCIDENT_START:
                rows.append([
                    link, sample_ts,
                    round(random.uniform(68, 82), 1),   # traffic shifted here
                    round(random.uniform(-3.5, -2.8), 1),
                    round(random.uniform(1e-12, 1e-10), 13),
                    round(random.uniform(9, 14), 1),
                ])
            # After incident for reroute path links: moderate increase
            elif is_reroute_link and sample_time >= INCIDENT_START:
                reroute_util = profile["util"] + random.uniform(12, 22)
                rows.append([
                    link, sample_ts,
                    round(reroute_util, 1),
                    round(random.uniform(-3.5, -2.8), 1),
                    round(random.uniform(1e-13, 1e-11), 14),
                    round(random.uniform(profile["latency"][0] + 3, profile["latency"][1] + 5), 1),
                ])
            else:
                # Normal baseline
                base_util = profile["util"]
                lat_lo, lat_hi = profile["latency"]
                rows.append([
                    link, sample_ts,
                    round(random.uniform(base_util - 5, base_util + 5), 1),
                    round(random.uniform(-3.5, -2.5), 1),
                    round(random.uniform(1e-14, 1e-11), 15),
                    round(random.uniform(lat_lo, lat_hi), 1),
                ])

    write_csv("LinkTelemetry.csv", headers, rows)


def main() -> None:
    print("Generating alert stream and link telemetry (telemetry data)...")
    generate_alert_stream()
    generate_link_telemetry()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
