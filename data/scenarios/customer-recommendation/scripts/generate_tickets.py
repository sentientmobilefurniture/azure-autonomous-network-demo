"""
Generate historical incident tickets for the customer-recommendation scenario.

Outputs 10 .txt files covering diverse e-commerce/recommendation issues.
"""

import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge", "tickets")

TICKETS = [
    {
        "id": "INC-2025-05-20-0003",
        "title": "Recommendation model cold-start failure for new segment",
        "severity": "P2",
        "root_cause": "SEG-NEW",
        "root_cause_type": "MODEL_COLD_START",
        "created": "2025-05-20T10:15:00Z",
        "resolved": "2025-05-20T14:30:00Z",
        "sla_breached": "No",
        "description": "New customer segment received zero personalized recommendations for 4 hours after segment definition change. Fallback to popularity-based recommendations was not triggered.",
        "detection": "Automated conversion rate monitoring",
        "resolution": "Fixed segment-to-model mapping. Added fallback logic to serve popularity-based recommendations when personalized model has insufficient data.",
        "customer_impact": ["SEG-NEW"],
        "services_affected": 1,
        "alerts_gen": 45,
        "alerts_sup": 30,
        "ttd": 120,
        "ttr": "255 minutes",
        "lessons": "Implement warm-start recommendations using collaborative filtering from similar segments. Add monitoring for recommendation coverage (% of users receiving personalized vs fallback).",
    },
    {
        "id": "INC-2025-06-08-0011",
        "title": "Price feed stale data — wrong prices displayed for 2 hours",
        "severity": "P1",
        "root_cause": "PROD-PHONE-001",
        "root_cause_type": "STALE_PRICE_FEED",
        "created": "2025-06-08T09:00:00Z",
        "resolved": "2025-06-08T11:15:00Z",
        "sla_breached": "Yes",
        "description": "Supplier price feed processing job hung, causing PROD-PHONE-001 and PROD-LAPTOP-001 to display yesterday's promotional prices. 47 orders fulfilled at $200 below intended price.",
        "detection": "Customer report — 'price seems too good to be true'",
        "resolution": "Restarted price feed processor. Honored mispriced orders. Added staleness check with automatic product delisting after 30 minutes of no price update.",
        "customer_impact": ["CUST-001", "CUST-002", "CUST-003"],
        "services_affected": 1,
        "alerts_gen": 12,
        "alerts_sup": 5,
        "ttd": 3600,
        "ttr": "135 minutes",
        "lessons": "Add price feed freshness metric to Product entity. Implement automated delisting when price feed age exceeds threshold.",
    },
    {
        "id": "INC-2025-07-15-0018",
        "title": "Campaign targeting wrong segment — VIP offers sent to casual",
        "severity": "P2",
        "root_cause": "CAMP-VIP-EXCLUS",
        "root_cause_type": "SEGMENT_MISMATCH",
        "created": "2025-07-15T16:00:00Z",
        "resolved": "2025-07-15T17:30:00Z",
        "sla_breached": "No",
        "description": "Campaign CAMP-VIP-EXCLUS sent 12% VIP discount codes to SEG-CASUAL users due to segment boundary overlap in the targeting query. 340 casual users received VIP pricing.",
        "detection": "Automated campaign spend anomaly alert",
        "resolution": "Fixed segment query to use exclusive boundaries. Issued credit to affected casual users and honored VIP pricing for fulfilled orders.",
        "customer_impact": ["SEG-CASUAL", "SEG-VIP"],
        "services_affected": 1,
        "alerts_gen": 23,
        "alerts_sup": 15,
        "ttd": 45,
        "ttr": "90 minutes",
        "lessons": "Add segment-campaign eligibility validation to campaign targeting pipeline. Log segment membership snapshot at targeting time for audit trail.",
    },
    {
        "id": "INC-2025-08-02-0024",
        "title": "Warehouse fulfillment delay — EU orders stuck 5 days",
        "severity": "P1",
        "root_cause": "WH-EU-CENTRAL",
        "root_cause_type": "FULFILLMENT_DELAY",
        "created": "2025-08-02T08:00:00Z",
        "resolved": "2025-08-04T18:00:00Z",
        "sla_breached": "Yes",
        "description": "Warehouse management system upgrade at WH-EU-CENTRAL caused pick-list generation failure. 1,200 EU orders delayed by 3-5 days.",
        "detection": "Manual — customer complaints",
        "resolution": "Rolled back WMS to previous version. Processed backlog with overtime staffing. Completed WMS upgrade in staged rollout 2 weeks later.",
        "customer_impact": ["CUST-004", "CUST-005", "CUST-010"],
        "services_affected": 1,
        "alerts_gen": 156,
        "alerts_sup": 120,
        "ttd": 14400,
        "ttr": "3480 minutes",
        "lessons": "Never deploy warehouse system upgrades during peak hours. Add order-age monitoring with automated escalation when SLA delivery window approaches.",
    },
    {
        "id": "INC-2025-08-28-0029",
        "title": "Search relevance regression — category filters broken",
        "severity": "P2",
        "root_cause": "CAT-ELECTRONICS",
        "root_cause_type": "SEARCH_RELEVANCE_BUG",
        "created": "2025-08-28T14:30:00Z",
        "resolved": "2025-08-28T16:00:00Z",
        "sla_breached": "No",
        "description": "Search index rebuild introduced a bug where CAT-ELECTRONICS subcategory filters returned products from all categories. Users searching for phones saw furniture results.",
        "detection": "Automated click-through rate drop alert",
        "resolution": "Rebuilt search index with correct category mapping. Added integration test for category filter accuracy.",
        "customer_impact": ["SEG-LOYAL", "SEG-CASUAL"],
        "services_affected": 1,
        "alerts_gen": 78,
        "alerts_sup": 60,
        "ttd": 30,
        "ttr": "90 minutes",
        "lessons": "Add search relevance regression test to CI/CD pipeline. Monitor category-specific click-through rates as leading indicator of search quality.",
    },
    {
        "id": "INC-2025-09-15-0034",
        "title": "Recommendation feedback loop — same 5 products promoted",
        "severity": "P2",
        "root_cause": "CAMP-CROSS-SELL",
        "root_cause_type": "FEEDBACK_LOOP",
        "created": "2025-09-15T11:00:00Z",
        "resolved": "2025-09-16T09:00:00Z",
        "sla_breached": "No",
        "description": "Cross-sell campaign created a popularity feedback loop: most-clicked products were promoted more, reducing catalog diversity. Top 5 products received 80% of impressions.",
        "detection": "Weekly diversity audit flagged concentration anomaly",
        "resolution": "Added exploration factor (epsilon-greedy) to recommendation algorithm. Minimum 20% of impressions reserved for diverse product sampling.",
        "customer_impact": ["SEG-LOYAL"],
        "services_affected": 1,
        "alerts_gen": 5,
        "alerts_sup": 0,
        "ttd": 604800,
        "ttr": "1320 minutes",
        "lessons": "Monitor Gini coefficient of product impression distribution. Implement diversity constraints in recommendation model training.",
    },
    {
        "id": "INC-2025-10-22-0038",
        "title": "Payment gateway timeout — 15% checkout failures",
        "severity": "P1",
        "root_cause": "CUST-002",
        "root_cause_type": "PAYMENT_GATEWAY_TIMEOUT",
        "created": "2025-10-22T19:00:00Z",
        "resolved": "2025-10-22T20:15:00Z",
        "sla_breached": "No",
        "description": "Payment provider experienced intermittent timeouts during peak shopping hours. 15% of checkout attempts failed. Cart recovery emails sent to affected users.",
        "detection": "Automated payment success rate alert",
        "resolution": "Payment provider resolved their infrastructure issue. Implemented retry with exponential backoff and fallback to secondary payment provider.",
        "customer_impact": ["CUST-001", "CUST-002", "CUST-003", "CUST-006"],
        "services_affected": 1,
        "alerts_gen": 234,
        "alerts_sup": 200,
        "ttd": 15,
        "ttr": "75 minutes",
        "lessons": "Configure automatic failover to secondary payment provider when primary error rate exceeds 5%. Add cart recovery automation for payment-failed checkouts.",
    },
    {
        "id": "INC-2025-11-30-0045",
        "title": "Black Friday inventory sync failure — overselling 3 products",
        "severity": "P1",
        "root_cause": "WH-US-EAST",
        "root_cause_type": "INVENTORY_SYNC_FAILURE",
        "created": "2025-11-30T06:00:00Z",
        "resolved": "2025-11-30T10:30:00Z",
        "sla_breached": "Yes",
        "description": "Inventory sync between WH-US-EAST and the product database lagged by 45 minutes during Black Friday traffic. PROD-ACC-001, PROD-PHONE-002, and PROD-KITCHEN-001 were oversold by 120, 45, and 80 units respectively.",
        "detection": "Automated stock-level discrepancy alert (delayed)",
        "resolution": "Halted sales of affected products. Sourced additional inventory from WH-US-WEST. Offered affected customers expedited shipping or full refund.",
        "customer_impact": ["SEG-VIP", "SEG-LOYAL", "SEG-CASUAL"],
        "services_affected": 3,
        "alerts_gen": 456,
        "alerts_sup": 400,
        "ttd": 2700,
        "ttr": "270 minutes",
        "lessons": "Implement real-time inventory reservation (not batch sync) for high-traffic periods. Add StockQty real-time field to Product entity for immediate availability checks.",
    },
    {
        "id": "INC-2025-12-18-0051",
        "title": "A/B test data leak — control group received treatment",
        "severity": "P2",
        "root_cause": "CAMP-HOLIDAY-2025",
        "root_cause_type": "AB_TEST_CONTAMINATION",
        "created": "2025-12-18T13:00:00Z",
        "resolved": "2025-12-18T15:30:00Z",
        "sla_breached": "No",
        "description": "Holiday campaign A/B test assignment logic had a hash collision bug. 30% of control group users received the treatment (15% discount). Test results invalidated after 5 days of data collection.",
        "detection": "Data science team noticed unexplained uplift in control group",
        "resolution": "Fixed hash function for user assignment. Restarted A/B test with verified control/treatment split. Extended test duration to compensate for lost data.",
        "customer_impact": ["SEG-LOYAL"],
        "services_affected": 1,
        "alerts_gen": 0,
        "alerts_sup": 0,
        "ttd": 432000,
        "ttr": "150 minutes",
        "lessons": "Add A/B test integrity monitoring — track treatment exposure rate in control group. Use deterministic assignment based on customer ID hash, not session-based.",
    },
    {
        "id": "INC-2026-01-25-0004",
        "title": "Supplier reliability drop — SUPP-ANKER shipments delayed",
        "severity": "P2",
        "root_cause": "SUPP-ANKER",
        "root_cause_type": "SUPPLIER_DELAY",
        "created": "2026-01-25T09:00:00Z",
        "resolved": "2026-02-01T12:00:00Z",
        "sla_breached": "No",
        "description": "Supplier SUPP-ANKER experienced factory delays due to Chinese New Year. Lead time increased from 10 to 25 days. Product PROD-ACC-002 stock dropped below reorder point across all warehouses.",
        "detection": "Automated low-stock alert",
        "resolution": "Placed emergency order via air freight. Temporarily substituted PROD-ACC-002 with alternative supplier product in recommendations.",
        "customer_impact": ["SEG-CASUAL", "SEG-NEW"],
        "services_affected": 1,
        "alerts_gen": 34,
        "alerts_sup": 20,
        "ttd": 60,
        "ttr": "10260 minutes",
        "lessons": "Build seasonal lead time profiles into Supplier entity (holiday periods increase LeadTimeDays). Auto-adjust reorder points 30 days before known supplier holidays.",
    },
]


def format_ticket(t: dict) -> str:
    impact_list = "\n".join(f"- {s}" for s in t["customer_impact"])
    return f"""Incident: {t["id"]}
Title: {t["title"]}
Severity: {t["severity"]}
Root Cause: {t["root_cause"]}
Root Cause Type: {t["root_cause_type"]}
Created: {t["created"]}
Resolved: {t["resolved"]}
SLA Breached: {t["sla_breached"]}

Description:
{t["description"]}

Detection Method:
{t["detection"]}

Resolution:
{t["resolution"]}

Customer Impact:
{impact_list}

Services Affected: {t["services_affected"]}
Alerts Generated: {t["alerts_gen"]}
Alerts Suppressed: {t["alerts_sup"]}
Time to Detect: {t["ttd"]} seconds
Time to Resolve: {t["ttr"]}

Lessons Learned:
{t["lessons"]}
"""


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Generating customer-recommendation tickets ...")
    for t in TICKETS:
        path = os.path.join(OUTPUT_DIR, f"{t['id']}.txt")
        with open(path, "w") as f:
            f.write(format_ticket(t))
        print(f"  ✓ {t['id']}.txt")
    print(f"\n{len(TICKETS)} tickets written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
