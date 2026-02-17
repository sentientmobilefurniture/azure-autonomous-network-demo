"""
Generate alert stream and link telemetry CSV files for the telco-backbone scenario.

Compound incident: Cyclone damages ADL-PER submarine cable while a simultaneous
storm-related power surge at DC-ADL-01 knocks out AGG-ADL-SOUTH-01. Two root
causes, one alert storm.

Outputs 2 CSV files:
  - AlertStream.csv     (~6,000 rows) — 54h baseline + compound cascading alert storm
  - LinkTelemetry.csv   (~12,000 rows) — 72h baseline + incident link metrics (14 links)
"""

import csv
import os
import random
from datetime import datetime, timedelta, timezone

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "telemetry")

# Incident start time (submarine cable damage)
INCIDENT_START = datetime(2026, 3, 12, 9, 15, 0, tzinfo=timezone.utc)

# Seed for reproducibility
random.seed(73)

# --------------------------------------------------------------------------- #
#  Topology references (must match network entity tables)
# --------------------------------------------------------------------------- #

CORE_ROUTERS = ["CORE-SYD-01", "CORE-MEL-01", "CORE-ADL-01", "CORE-PER-01", "CORE-CBR-01"]
AGG_SWITCHES = [
    "AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01",
    "AGG-MEL-EAST-01", "AGG-MEL-WEST-01",
    "AGG-ADL-NORTH-01", "AGG-ADL-SOUTH-01",
    "AGG-PER-CENTRAL-01", "AGG-CBR-CENTRAL-01",
]
BASE_STATIONS = [
    "GNB-SYD-2041", "GNB-SYD-2042", "GNB-SYD-2043",
    "GNB-MEL-3011", "GNB-MEL-3012",
    "GNB-ADL-5011", "GNB-ADL-5012",
    "GNB-PER-6011", "GNB-PER-6012",
    "GNB-CBR-7011",
]
TRANSPORT_LINKS = [
    "LINK-SYD-MEL-FIBRE-01", "LINK-MEL-ADL-FIBRE-01",
    "LINK-ADL-PER-SUBMARINE-01", "LINK-ADL-PER-MICROWAVE-01",
    "LINK-SYD-CBR-FIBRE-01", "LINK-SYD-ADL-FIBRE-01",
    "LINK-SYD-AGG-NORTH-01", "LINK-SYD-AGG-SOUTH-01",
    "LINK-MEL-AGG-EAST-01", "LINK-MEL-AGG-WEST-01",
    "LINK-ADL-AGG-NORTH-01", "LINK-ADL-AGG-SOUTH-01",
    "LINK-PER-AGG-CENTRAL-01", "LINK-CBR-AGG-CENTRAL-01",
]
SERVICES = [
    "VPN-IRONORE-CORP", "VPN-WESTGAS-CORP", "VPN-GOVDEFENCE",
    "VPN-FINSERV-CORP", "VPN-UNILINK",
    "BB-BUNDLE-SYD-NORTH", "BB-BUNDLE-MEL-EAST",
    "BB-BUNDLE-ADL-SOUTH", "BB-BUNDLE-PER-CENTRAL",
    "MOB-5G-SYD-2041", "MOB-5G-MEL-3011", "MOB-5G-ADL-5011",
    "MOB-5G-PER-6011", "MOB-5G-CBR-7011",
]

# --- Root Cause 1: Submarine cable cut (ADL-PER corridor) ---
IMPACTED_BY_CABLE = {
    "routers": ["CORE-ADL-01", "CORE-PER-01"],
    "agg": ["AGG-PER-CENTRAL-01"],
    "gnb": ["GNB-PER-6011", "GNB-PER-6012"],
    "services": ["VPN-IRONORE-CORP", "VPN-WESTGAS-CORP", "BB-BUNDLE-PER-CENTRAL", "MOB-5G-PER-6011"],
}

# --- Root Cause 2: Power failure at DC-ADL-01 (knocks out AGG-ADL-SOUTH-01) ---
IMPACTED_BY_POWER = {
    "agg": ["AGG-ADL-SOUTH-01"],
    "gnb": ["GNB-ADL-5012"],
    "services": ["BB-BUNDLE-ADL-SOUTH"],
}

# Combined impacted nodes (both failures)
ALL_IMPACTED_SERVICES = list(set(IMPACTED_BY_CABLE["services"] + IMPACTED_BY_POWER["services"]))
ALL_IMPACTED_NODES = (
    IMPACTED_BY_CABLE["routers"] + IMPACTED_BY_CABLE["agg"] + IMPACTED_BY_CABLE["gnb"]
    + IMPACTED_BY_POWER["agg"] + IMPACTED_BY_POWER["gnb"]
    + ALL_IMPACTED_SERVICES
)

# Microwave backup link — sees capacity exhaustion
MICROWAVE_BACKUP = "LINK-ADL-PER-MICROWAVE-01"
# Links that see reroute traffic increase
REROUTE_LINKS = ["LINK-SYD-ADL-FIBRE-01", "LINK-MEL-ADL-FIBRE-01"]


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
    Generates ~6,000 alerts: ~3,500 baseline over 54h + ~2,500 storm alerts
    from a compound cascade (submarine cable cut + datacenter power failure).

    IMPORTANT: Every row includes ALL FOUR numeric telemetry columns — no nulls.

    Compound cascade timeline:
      === Root Cause 1: Submarine cable damage ===
      T+0s     SUBMARINE_CABLE_FAULT on LINK-ADL-PER-SUBMARINE-01    (1)
      T+3s     BGP_PEER_LOSS on ADL-PER session                      (2)
      T+5s     Traffic failover to MICROWAVE backup                   (1)
      T+8s     CAPACITY_EXCEEDED on microwave — 10G can't hold 40G   (50)
      === Root Cause 2: Power surge at DC-ADL-01 ===
      T+10s    POWER_FAILURE at DC-ADL-01                             (1)
      T+12s    AGG-ADL-SOUTH-01 goes DOWN                             (1)
      T+15s    OSPF reconvergence across Adelaide                     (4)
      T+20s    ROUTE_WITHDRAWAL for Perth-bound prefixes              (~25)
      T+25s    HIGH_CPU on CORE-ADL-01 (handling both failures)       (~60)
      T+35s    PACKET_LOSS across Perth and Adelaide downstream       (~250)
      T+60s    SERVICE_DEGRADATION on Perth + Adelaide services       (~600)
      T+90s    DUPLICATE_ALERT flapping/repeated                      fills to ~2500
    """
    headers = [
        "AlertId", "Timestamp", "SourceNodeId", "SourceNodeType",
        "AlertType", "Severity", "Description",
        "OpticalPowerDbm", "BitErrorRate", "CPUUtilPct", "PacketLossPct",
    ]

    alerts: list[list] = []
    alert_counter = 0

    def normal_optical() -> float:
        return round(random.uniform(-3.5, -2.5), 1)

    def normal_ber() -> float:
        return round(random.uniform(1e-14, 1e-11), 15)

    def normal_cpu() -> float:
        return round(random.uniform(15, 45), 1)

    def normal_pkt_loss() -> float:
        return round(random.uniform(0.0, 0.05), 3)

    def baseline_snapshot() -> dict:
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
        nonlocal alert_counter
        alert_counter += 1
        snap = baseline_snapshot()
        alerts.append([
            f"ALT-20260312-{alert_counter:06d}",
            ts(offset), node_id, node_type,
            alert_type, severity, description,
            optical if optical is not None else snap["optical"],
            ber if ber is not None else snap["ber"],
            cpu if cpu is not None else snap["cpu"],
            pkt_loss if pkt_loss is not None else snap["pkt_loss"],
        ])

    # ── Baseline: 54 hours of background noise ─────────────────────
    baseline_start = -54 * 3600
    baseline_end = -60
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
    num_baseline_alerts = random.randint(3200, 3800)
    for _ in range(num_baseline_alerts):
        offset = random.uniform(baseline_start, baseline_end)
        node, node_type = random.choice(baseline_nodes)
        alert_def = random.choice(baseline_alerts_by_type[node_type])
        cpu_val = round(random.uniform(55, 75), 1) if "cpu" in alert_def[2] else None
        pkt_val = round(random.uniform(0.1, 0.8), 2) if "pkt" in alert_def[2] else None
        desc = alert_def[2]
        if cpu_val is not None:
            desc = desc.format(cpu=cpu_val, pkt="")
        elif pkt_val is not None:
            desc = desc.format(cpu="", pkt=pkt_val)
        add(offset, node, node_type, alert_def[0],
            alert_def[1], desc, cpu=cpu_val, pkt_loss=pkt_val)

    # ══════════════════════════════════════════════════════════════════
    #  ROOT CAUSE 1: Submarine cable fault (T+0s)
    # ══════════════════════════════════════════════════════════════════

    # T+0: Submarine cable damage — loss of light
    add(0.0, "LINK-ADL-PER-SUBMARINE-01", "TransportLink", "SUBMARINE_CABLE_FAULT",
        "CRITICAL", "Submarine cable signal loss detected — cyclone damage suspected on Great Australian Bight span",
        optical=-42.0, ber=1.0, pkt_loss=100.0, cpu=normal_cpu())

    # T+3: BGP peer loss ADL-PER
    add(3.1, "CORE-ADL-01", "CoreRouter", "BGP_PEER_LOSS",
        "CRITICAL", "BGP peer CORE-PER-01 (AS64515) unreachable via LINK-ADL-PER-SUBMARINE-01",
        cpu=round(random.uniform(78, 88), 1), pkt_loss=round(random.uniform(2, 8), 2))
    add(3.4, "CORE-PER-01", "CoreRouter", "BGP_PEER_LOSS",
        "CRITICAL", "BGP peer CORE-ADL-01 (AS64514) unreachable via LINK-ADL-PER-SUBMARINE-01",
        cpu=round(random.uniform(78, 88), 1), pkt_loss=round(random.uniform(2, 8), 2))

    # T+5: Traffic failover to microwave backup
    add(5.0, "LINK-ADL-PER-MICROWAVE-01", "TransportLink", "LINK_FAILOVER",
        "MAJOR", "Traffic failover initiated — microwave backup link now active for ADL-PER corridor",
        cpu=normal_cpu(), pkt_loss=round(random.uniform(0.5, 2.0), 2))

    # T+8: Capacity exhaustion on microwave (10G backup receiving 40G demand)
    for _ in range(50):
        add(jitter(8.0, 3.0), "LINK-ADL-PER-MICROWAVE-01", "TransportLink", "CAPACITY_EXCEEDED",
            "CRITICAL", "Microwave link utilization >100% — 10G capacity cannot absorb 40G submarine cable traffic",
            cpu=round(random.uniform(50, 70), 1), pkt_loss=round(random.uniform(15, 45), 2))

    # ══════════════════════════════════════════════════════════════════
    #  ROOT CAUSE 2: Power failure at DC-ADL-01 (T+10s)
    # ══════════════════════════════════════════════════════════════════

    # T+10: Power surge detected at Adelaide datacenter
    add(10.0, "AGG-ADL-SOUTH-01", "AggSwitch", "POWER_FAILURE",
        "CRITICAL", "UPS failure at DC-ADL-01 — AGG-ADL-SOUTH-01 lost power, storm surge on mains supply",
        cpu=0.0, pkt_loss=100.0)

    # T+12: Downstream base station lost backhaul
    add(12.0, "GNB-ADL-5012", "BaseStation", "BACKHAUL_DOWN",
        "CRITICAL", "Backhaul lost — upstream AGG-ADL-SOUTH-01 unresponsive after power failure",
        cpu=round(random.uniform(30, 50), 1), pkt_loss=100.0)

    # T+15: OSPF adjacency losses on Adelaide router (both cable + power hitting simultaneously)
    for i, iface in enumerate(["Gi0/0/0/1", "Gi0/0/0/2", "Gi0/0/0/3", "Gi0/0/0/4"]):
        router = ["CORE-ADL-01", "CORE-PER-01"][i % 2]
        add(jitter(15.0, 1.0), router, "CoreRouter", "OSPF_ADJACENCY_DOWN",
            "MAJOR", f"OSPF adjacency lost on interface {iface} — convergence under compound failure",
            cpu=round(random.uniform(80, 92), 1), pkt_loss=round(random.uniform(3, 12), 2))

    # T+20: Route withdrawals for Perth-bound prefixes
    prefixes = [
        "10.50.0.0/16", "10.51.0.0/16", "10.52.0.0/16", "10.53.0.0/16",
        "172.20.0.0/16", "172.21.0.0/16", "172.22.0.0/16",
        "192.168.50.0/24", "192.168.51.0/24", "192.168.52.0/24",
        "10.60.0.0/16", "10.61.0.0/16", "10.62.0.0/16",
        "10.70.0.0/16", "10.71.0.0/16", "10.72.0.0/16",
        "10.80.0.0/16", "10.81.0.0/16",
        "10.90.0.0/16", "10.91.0.0/16", "10.92.0.0/16",
        "10.100.0.0/16", "10.101.0.0/16", "10.102.0.0/16", "10.103.0.0/16",
    ]
    for prefix in prefixes:
        router = random.choice(IMPACTED_BY_CABLE["routers"])
        add(jitter(20.0, 4.0), router, "CoreRouter", "ROUTE_WITHDRAWAL",
            "MAJOR", f"Route {prefix} withdrawn — next-hop unreachable via ADL-PER corridor",
            cpu=round(random.uniform(82, 95), 1), pkt_loss=round(random.uniform(5, 15), 2))

    # T+25: HIGH_CPU on CORE-ADL-01 handling compound failure
    for _ in range(60):
        node = random.choice(IMPACTED_BY_CABLE["routers"] + IMPACTED_BY_CABLE["agg"] + IMPACTED_BY_POWER["agg"])
        cpu = round(random.uniform(85, 99), 1)
        add(jitter(25.0, 5.0), node,
            "CoreRouter" if node.startswith("CORE") else "AggSwitch",
            "HIGH_CPU", "WARNING",
            f"CPU utilization {cpu}% — route reconvergence under compound failure",
            cpu=cpu, pkt_loss=round(random.uniform(1, 10), 2))

    # T+35: Packet loss on downstream Perth + Adelaide south
    all_downstream = (
        IMPACTED_BY_CABLE["agg"] + IMPACTED_BY_CABLE["gnb"]
        + IMPACTED_BY_POWER["agg"] + IMPACTED_BY_POWER["gnb"]
    )
    for _ in range(250):
        node = random.choice(all_downstream)
        node_type = "AggSwitch" if node.startswith("AGG") else "BaseStation"
        pkt = round(random.uniform(0.5, 25.0), 2)
        add(jitter(35.0, 12.0), node, node_type, "PACKET_LOSS_THRESHOLD",
            "MAJOR", f"Packet loss {pkt}% exceeded threshold — upstream path degraded",
            pkt_loss=pkt, cpu=round(random.uniform(50, 80), 1))

    # T+60: Service degradation — Perth services + Adelaide south services
    svc_descriptions = {
        "EnterpriseVPN": "VPN tunnel unreachable — primary and backup MPLS paths degraded",
        "GovernmentVPN": "Secure government VPN degraded — alternate path latency exceeds threshold",
        "Broadband": "Customer broadband degraded — upstream aggregation path impacted",
        "Mobile5G": "Backhaul degradation — voice quality MOS below threshold",
    }
    for _ in range(600):
        svc = random.choice(ALL_IMPACTED_SERVICES)
        if svc.startswith("VPN-GOV"):
            svc_type = "GovernmentVPN"
            severity = "CRITICAL"
        elif svc.startswith("VPN"):
            svc_type = "EnterpriseVPN"
            severity = "CRITICAL"
        elif svc.startswith("BB"):
            svc_type = "Broadband"
            severity = "MAJOR"
        else:
            svc_type = "Mobile5G"
            severity = "WARNING"
        pkt = round(random.uniform(1.0, 30.0), 2)
        add(jitter(60.0, 18.0), svc, "Service", "SERVICE_DEGRADATION",
            severity, svc_descriptions[svc_type],
            pkt_loss=pkt, cpu=round(random.uniform(40, 75), 1))

    # T+70–120: Duplicate / flapping alerts (compound failure = more flapping)
    target_total = 2500
    remaining = target_total - len(alerts)
    dup_types = ["DUPLICATE_ALERT", "PACKET_LOSS_THRESHOLD", "HIGH_CPU",
                 "SERVICE_DEGRADATION", "CAPACITY_EXCEEDED"]
    for _ in range(max(0, remaining)):
        node = random.choice(ALL_IMPACTED_NODES)
        if node.startswith("CORE"):
            node_type = "CoreRouter"
        elif node.startswith("AGG"):
            node_type = "AggSwitch"
        elif node.startswith("GNB"):
            node_type = "BaseStation"
        elif node.startswith("LINK"):
            node_type = "TransportLink"
        else:
            node_type = "Service"
        alert_type = random.choice(dup_types)
        add(jitter(95.0, 25.0), node, node_type, alert_type,
            random.choice(["WARNING", "MAJOR"]),
            f"Repeated alert — {alert_type.lower().replace('_', ' ')} on {node}",
            cpu=round(random.uniform(60, 95), 1),
            pkt_loss=round(random.uniform(0.5, 25), 2))

    # Sort by timestamp
    alerts.sort(key=lambda r: r[1])
    write_csv("AlertStream.csv", headers, alerts)


def generate_link_telemetry() -> None:
    """
    Generate baseline + incident link telemetry for all 14 transport links.
    72h of 5-min samples per link (60h before + 12h after incident).

    After the compound failure:
      - SUBMARINE-01: dead (0% util, loss of light)
      - MICROWAVE-01: maxed out at 100% then degraded (can't absorb load)
      - SYD-ADL + MEL-ADL fibres: increased ~15-20% (reroute traffic)
      - ADL agg south uplink: dead (power failure)
      - Other links: baseline or slight increase
    """
    headers = ["LinkId", "Timestamp", "UtilizationPct", "OpticalPowerDbm", "BitErrorRate", "LatencyMs"]
    rows: list[list] = []

    start_time = INCIDENT_START - timedelta(hours=60)
    interval_minutes = 5
    num_samples = (72 * 60) // interval_minutes  # 864 per link

    baseline_profiles = {
        "LINK-SYD-MEL-FIBRE-01": {"util": 52.0, "latency": (4, 8)},
        "LINK-MEL-ADL-FIBRE-01": {"util": 38.0, "latency": (6, 12)},
        "LINK-ADL-PER-SUBMARINE-01": {"util": 62.0, "latency": (12, 22)},
        "LINK-ADL-PER-MICROWAVE-01": {"util": 15.0, "latency": (18, 35)},
        "LINK-SYD-CBR-FIBRE-01": {"util": 30.0, "latency": (2, 5)},
        "LINK-SYD-ADL-FIBRE-01": {"util": 35.0, "latency": (10, 18)},
        "LINK-SYD-AGG-NORTH-01": {"util": 45.0, "latency": (1, 3)},
        "LINK-SYD-AGG-SOUTH-01": {"util": 40.0, "latency": (1, 3)},
        "LINK-MEL-AGG-EAST-01": {"util": 38.0, "latency": (1, 3)},
        "LINK-MEL-AGG-WEST-01": {"util": 35.0, "latency": (1, 3)},
        "LINK-ADL-AGG-NORTH-01": {"util": 32.0, "latency": (1, 3)},
        "LINK-ADL-AGG-SOUTH-01": {"util": 28.0, "latency": (1, 3)},
        "LINK-PER-AGG-CENTRAL-01": {"util": 42.0, "latency": (1, 3)},
        "LINK-CBR-AGG-CENTRAL-01": {"util": 25.0, "latency": (1, 3)},
    }

    for link in TRANSPORT_LINKS:
        is_submarine = link == "LINK-ADL-PER-SUBMARINE-01"
        is_microwave = link == "LINK-ADL-PER-MICROWAVE-01"
        is_adl_agg_south = link == "LINK-ADL-AGG-SOUTH-01"
        is_reroute = link in REROUTE_LINKS
        profile = baseline_profiles.get(link, {"util": 40.0, "latency": (4, 12)})

        for i in range(num_samples):
            sample_time = start_time + timedelta(minutes=i * interval_minutes)
            sample_ts = sample_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            if is_submarine and sample_time >= INCIDENT_START:
                # Submarine cable: dead
                rows.append([link, sample_ts, 0.0, -42.0, 1.0, 9999.0])

            elif is_microwave and sample_time >= INCIDENT_START:
                # Microwave: overwhelmed — 100%+ utilisation, high latency, packet loss
                rows.append([
                    link, sample_ts,
                    round(random.uniform(95, 100), 1),
                    round(random.uniform(-5.0, -3.5), 1),
                    round(random.uniform(1e-8, 1e-5), 10),
                    round(random.uniform(80, 250), 1),
                ])

            elif is_adl_agg_south and sample_time >= INCIDENT_START + timedelta(seconds=10):
                # ADL AGG South: dead (power failure at DC-ADL-01)
                rows.append([link, sample_ts, 0.0, -40.0, 1.0, 9999.0])

            elif is_reroute and sample_time >= INCIDENT_START:
                # Reroute paths: moderate utilisation increase
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
    print("Generating alert stream and link telemetry (telco-backbone telemetry)...")
    generate_alert_stream()
    generate_link_telemetry()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
