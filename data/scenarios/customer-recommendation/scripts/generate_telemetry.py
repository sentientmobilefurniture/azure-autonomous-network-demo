"""
Generate telemetry CSV files for the customer-recommendation scenario.

Incident: Recommendation engine model update introduces a bias that pushes
high-price products to new/casual segments, causing return rate spike and
customer satisfaction drop.

Outputs 2 CSV files:
  - AlertStream.csv         (~5000 rows: 54h baseline + 90s incident cascade)
  - RecommendationMetrics.csv (~8640 rows: 72h of 5-min samples per segment)
"""

import csv
import os
import random
from datetime import datetime, timedelta, timezone

random.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "telemetry")

INCIDENT_START = datetime(2026, 2, 6, 14, 30, 0, tzinfo=timezone.utc)

# ── Entity IDs ─────────────────────────────────────────────────────────────
ALL_SEGMENTS = ["SEG-VIP", "SEG-LOYAL", "SEG-CASUAL", "SEG-NEW", "SEG-WINBACK"]
ALL_CAMPAIGNS = ["CAMP-HOLIDAY-2025", "CAMP-VIP-EXCLUS", "CAMP-NEWUSER-Q1",
                 "CAMP-WINBACK-Q4", "CAMP-FLASH-FEB", "CAMP-CROSS-SELL"]
ALL_CUSTOMERS = [f"CUST-{i:03d}" for i in range(1, 13)]
ALL_PRODUCTS = [
    "PROD-PHONE-001", "PROD-PHONE-002", "PROD-PHONE-003",
    "PROD-LAPTOP-001", "PROD-LAPTOP-002",
    "PROD-ACC-001", "PROD-ACC-002",
    "PROD-FURN-001", "PROD-FURN-002",
    "PROD-KITCHEN-001", "PROD-MENS-001", "PROD-WOMENS-001",
]
AFFECTED_SEGMENTS = ["SEG-NEW", "SEG-CASUAL", "SEG-WINBACK"]
AFFECTED_CAMPAIGNS = ["CAMP-NEWUSER-Q1", "CAMP-FLASH-FEB", "CAMP-WINBACK-Q4"]

ALL_NODES = (
    [(s, "CustomerSegment") for s in ALL_SEGMENTS]
    + [(c, "Campaign") for c in ALL_CAMPAIGNS]
    + [(p, "Product") for p in ALL_PRODUCTS]
    + [(cu, "Customer") for cu in ALL_CUSTOMERS]
    + [("WH-US-EAST", "Warehouse"), ("WH-US-WEST", "Warehouse"),
       ("WH-EU-CENTRAL", "Warehouse"), ("WH-APAC-SG", "Warehouse")]
)


def baseline_snapshot():
    return {
        "click_rate": round(random.uniform(2.0, 8.0), 2),
        "conversion_rate": round(random.uniform(1.0, 5.0), 2),
        "return_rate": round(random.uniform(0.5, 3.0), 2),
        "avg_order_value": round(random.uniform(50, 200), 2),
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
    dt = INCIDENT_START + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def jitter(base: float, spread: float = 2.0) -> float:
    return base + random.uniform(-spread, spread)


def generate_alert_stream() -> None:
    alerts = []
    counter = 0

    def add(offset, node_id, node_type, alert_type, severity, description,
            click_rate=None, conversion_rate=None, return_rate=None, avg_order_value=None):
        nonlocal counter
        counter += 1
        snap = baseline_snapshot()
        alerts.append([
            f"ALT-20260206-{counter:06d}",
            ts(offset), node_id, node_type,
            alert_type, severity, description,
            click_rate if click_rate is not None else snap["click_rate"],
            conversion_rate if conversion_rate is not None else snap["conversion_rate"],
            return_rate if return_rate is not None else snap["return_rate"],
            avg_order_value if avg_order_value is not None else snap["avg_order_value"],
        ])

    # ── Baseline: 54h of normal e-commerce noise ───────────────────────────
    baseline_start = -54 * 3600
    baseline_end = -60
    num_baseline = random.randint(2800, 3400)

    baseline_alerts_by_type = {
        "CustomerSegment": [
            ("CONVERSION_DIP", "WARNING", "Segment {node} conversion rate slightly below target"),
            ("HIGH_CART_ABANDON", "MINOR", "Cart abandonment rate elevated for {node}"),
        ],
        "Campaign": [
            ("LOW_CTR", "WARNING", "Campaign click-through rate below 2% threshold"),
            ("BUDGET_WARNING", "MINOR", "Campaign spend at 80% of budget"),
        ],
        "Product": [
            ("LOW_STOCK", "WARNING", "Product stock below reorder point"),
            ("PRICE_MISMATCH", "MINOR", "Competitor price delta > 10%"),
        ],
        "Customer": [
            ("UNUSUAL_ACTIVITY", "MINOR", "Unusual browsing pattern detected"),
            ("PAYMENT_RETRY", "WARNING", "Payment method retry — possibly declined"),
        ],
        "Warehouse": [
            ("FULFILLMENT_DELAY", "WARNING", "Fulfillment time exceeding SLA for some orders"),
            ("CAPACITY_WARNING", "MINOR", "Warehouse approaching 85% capacity"),
        ],
    }

    for _ in range(num_baseline):
        offset = random.uniform(baseline_start, baseline_end)
        node_id, node_type = random.choice(ALL_NODES)
        alert_defs = baseline_alerts_by_type.get(node_type, baseline_alerts_by_type["Product"])
        atype, sev, desc_tmpl = random.choice(alert_defs)
        desc = desc_tmpl.format(node=node_id)
        add(offset, node_id, node_type, atype, sev, desc)

    # ── Incident Cascade ───────────────────────────────────────────────────
    # T+0s: MODEL_BIAS_DETECTED — recommendation engine model update goes wrong
    add(0, "CAMP-NEWUSER-Q1", "Campaign", "MODEL_BIAS_DETECTED", "CRITICAL",
        "Recommendation model v2.4 showing price-insensitive bias — high-value products "
        "being surfaced to price-sensitive segments (SEG-NEW, SEG-CASUAL)",
        click_rate=12.5, conversion_rate=0.8, return_rate=18.5, avg_order_value=850)

    # T+5s: Return rate spike on affected segments
    for seg_id in AFFECTED_SEGMENTS:
        add(jitter(5), seg_id, "CustomerSegment", "RETURN_RATE_SPIKE", "CRITICAL",
            f"Segment {seg_id} return rate spiked to 22% (baseline: 2.5%)",
            return_rate=round(random.uniform(18, 25), 1),
            conversion_rate=round(random.uniform(0.3, 0.8), 2))

    # T+10s: Wrong product recommendations flagged
    wrong_products = ["PROD-LAPTOP-001", "PROD-FURN-002", "PROD-PHONE-001"]
    for prod_id in wrong_products:
        add(jitter(10), prod_id, "Product", "WRONG_SEGMENT_RECOMMENDATION", "MAJOR",
            f"Product {prod_id} (>$1000) being recommended to SEG-NEW and SEG-CASUAL users",
            return_rate=round(random.uniform(15, 30), 1),
            avg_order_value=round(random.uniform(800, 2500), 2))

    # T+15s: Customer complaints spike
    for cust_id in ["CUST-008", "CUST-009", "CUST-006", "CUST-012"]:
        add(jitter(15), cust_id, "Customer", "CUSTOMER_COMPLAINT", "MAJOR",
            f"Customer {cust_id} filed complaint — 'recommended products far outside my budget'",
            return_rate=round(random.uniform(20, 35), 1))

    # T+20s: Conversion rate crash on affected campaigns
    for camp_id in AFFECTED_CAMPAIGNS:
        add(jitter(20), camp_id, "Campaign", "CONVERSION_CRASH", "CRITICAL",
            f"Campaign {camp_id} conversion rate dropped to 0.3% (target: 4%)",
            conversion_rate=round(random.uniform(0.1, 0.5), 2),
            return_rate=round(random.uniform(15, 25), 1))

    # T+25s: Revenue anomaly detection
    add(jitter(25), "SEG-NEW", "CustomerSegment", "REVENUE_ANOMALY", "CRITICAL",
        "New customer segment showing 85% return rate on recommended products — "
        "model bias confirmed. Estimated revenue impact: -$45,000/day",
        return_rate=85.0, conversion_rate=0.2, avg_order_value=1250)

    # T+30s: SLA breach warnings
    add(jitter(30), "SEG-NEW", "CustomerSegment", "SLA_BREACH_WARNING", "CRITICAL",
        "SLA-NEW-WELCOME: customer satisfaction score dropped below threshold",
        return_rate=30.0)
    add(jitter(31), "SEG-CASUAL", "CustomerSegment", "SLA_BREACH_WARNING", "MAJOR",
        "SLA-CASUAL-BASIC: return processing SLA at risk due to volume",
        return_rate=22.0)

    # T+35s: Warehouse impact — returns flooding in
    add(jitter(35), "WH-US-EAST", "Warehouse", "RETURN_VOLUME_SPIKE", "MAJOR",
        "Return processing queue 5x normal — warehouse approaching capacity",
        return_rate=25.0)
    add(jitter(36), "WH-US-WEST", "Warehouse", "RETURN_VOLUME_SPIKE", "WARNING",
        "Return volume elevated — 2x normal baseline",
        return_rate=12.0)

    # T+40s: Supplier impact — returned inventory
    add(jitter(40), "PROD-LAPTOP-001", "Product", "EXCESS_RETURNS", "MAJOR",
        "Product PROD-LAPTOP-001 return rate 45% on new-user purchases — investigating",
        return_rate=45.0, avg_order_value=2499)

    # T+50-90s: Flapping and follow-on alerts
    for i in range(1500):
        offset = jitter(50 + random.uniform(0, 40), spread=3.0)
        node_id, node_type = random.choice(
            [(s, "CustomerSegment") for s in AFFECTED_SEGMENTS]
            + [(c, "Campaign") for c in AFFECTED_CAMPAIGNS]
            + [(p, "Product") for p in wrong_products]
            + [(cu, "Customer") for cu in ALL_CUSTOMERS[:6]]
        )
        alert_types = ["DUPLICATE_ALERT", "RETURN_RATE_SPIKE", "CONVERSION_DIP",
                       "CUSTOMER_COMPLAINT", "WRONG_SEGMENT_RECOMMENDATION"]
        atype = random.choice(alert_types)
        sev = random.choice(["WARNING", "MINOR", "MAJOR"])
        add(offset, node_id, node_type, atype, sev,
            f"[Storm] {atype} on {node_id} — correlates with model v2.4 bias",
            return_rate=round(random.uniform(5, 35), 1),
            conversion_rate=round(random.uniform(0.2, 2.0), 2))

    alerts.sort(key=lambda r: r[1])

    headers = [
        "AlertId", "Timestamp", "SourceNodeId", "SourceNodeType",
        "AlertType", "Severity", "Description",
        "ClickRatePct", "ConversionRatePct", "ReturnRatePct", "AvgOrderValueUSD",
    ]
    write_csv("AlertStream.csv", headers, alerts)


def generate_recommendation_metrics() -> None:
    """72h of 5-min samples per segment — recommendation engine performance."""
    start_time = INCIDENT_START - timedelta(hours=60)
    interval_minutes = 5
    num_samples = (72 * 60) // interval_minutes  # 864 per segment

    baseline_profiles = {
        "SEG-VIP": {"click": 8.5, "conv": 5.2, "ret": 1.2, "aov": 450},
        "SEG-LOYAL": {"click": 6.2, "conv": 4.0, "ret": 2.0, "aov": 180},
        "SEG-CASUAL": {"click": 4.0, "conv": 2.5, "ret": 3.0, "aov": 85},
        "SEG-NEW": {"click": 5.5, "conv": 3.0, "ret": 2.5, "aov": 65},
        "SEG-WINBACK": {"click": 3.5, "conv": 1.8, "ret": 3.5, "aov": 120},
    }

    rows = []
    metric_counter = 0
    for seg_id in ALL_SEGMENTS:
        profile = baseline_profiles[seg_id]
        is_affected = seg_id in AFFECTED_SEGMENTS
        for i in range(num_samples):
            metric_counter += 1
            sample_time = start_time + timedelta(minutes=i * interval_minutes)
            sample_ts = sample_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            is_post_incident = sample_time >= INCIDENT_START

            if is_affected and is_post_incident:
                rows.append([
                    f"RM-{metric_counter:08d}", seg_id, sample_ts,
                    round(profile["click"] + random.uniform(3, 8), 2),  # inflated clicks (curiosity)
                    round(max(0.1, profile["conv"] - random.uniform(1.5, 2.5)), 2),  # crashed conversion
                    round(profile["ret"] + random.uniform(10, 25), 2),  # spiked returns
                    round(profile["aov"] + random.uniform(300, 800), 2),  # inflated AOV (wrong products)
                ])
            else:
                rows.append([
                    f"RM-{metric_counter:08d}", seg_id, sample_ts,
                    round(profile["click"] + random.uniform(-1, 1), 2),
                    round(profile["conv"] + random.uniform(-0.5, 0.5), 2),
                    round(profile["ret"] + random.uniform(-0.5, 0.5), 2),
                    round(profile["aov"] + random.uniform(-15, 15), 2),
                ])

    headers = [
        "MetricId", "SegmentId", "Timestamp",
        "ClickRatePct", "ConversionRatePct", "ReturnRatePct", "AvgOrderValueUSD",
    ]
    write_csv("RecommendationMetrics.csv", headers, rows)


def main() -> None:
    print("Generating customer-recommendation telemetry data ...")
    generate_alert_stream()
    generate_recommendation_metrics()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
