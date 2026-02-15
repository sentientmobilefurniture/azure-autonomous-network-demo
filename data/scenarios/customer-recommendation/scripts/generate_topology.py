"""
Generate static topology CSV files for customer recommendation entity tables.

Domain: E-commerce recommendation engine — customers, products, categories,
campaigns, segments, suppliers, warehouses, and SLA policies.

Incident scenario: Recommendation engine anomaly causes wrong products to be
surfaced, spiking return rates and customer complaints. The AI investigates
which segments, campaigns, and product categories are affected.

Outputs 8 CSV files:
  - DimCustomerSegment.csv
  - DimCustomer.csv
  - DimProductCategory.csv
  - DimProduct.csv
  - DimCampaign.csv
  - DimSupplier.csv
  - DimWarehouse.csv
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


# ── Customer Segments ──────────────────────────────────────────────────────
def generate_customer_segments() -> None:
    headers = ["SegmentId", "SegmentName", "Description", "MinSpendUSD", "MaxSpendUSD"]
    rows = [
        ["SEG-VIP", "VIP Customers", "Top 2% by lifetime spend — white-glove service", 10000, 999999],
        ["SEG-LOYAL", "Loyal Customers", "Regular buyers — 12+ orders per year", 2000, 9999],
        ["SEG-CASUAL", "Casual Shoppers", "Occasional buyers — 2-11 orders per year", 200, 1999],
        ["SEG-NEW", "New Customers", "First 90 days — onboarding experience", 0, 199],
        ["SEG-WINBACK", "Win-Back Targets", "Lapsed customers — no order in 6+ months", 0, 999999],
    ]
    write_csv("DimCustomerSegment.csv", headers, rows)


# ── Customers ──────────────────────────────────────────────────────────────
def generate_customers() -> None:
    headers = ["CustomerId", "CustomerName", "SegmentId", "Region", "JoinDate", "LifetimeSpendUSD"]
    rows = [
        ["CUST-001", "Alice Chen", "SEG-VIP", "US-West", "2022-03-15", 28450],
        ["CUST-002", "Bob Martinez", "SEG-VIP", "US-East", "2021-11-02", 34200],
        ["CUST-003", "Carol Johnson", "SEG-LOYAL", "US-East", "2023-01-20", 5680],
        ["CUST-004", "David Kim", "SEG-LOYAL", "EU-West", "2022-08-10", 7230],
        ["CUST-005", "Eva Schmidt", "SEG-LOYAL", "EU-West", "2023-05-14", 3450],
        ["CUST-006", "Frank Williams", "SEG-CASUAL", "US-West", "2024-02-28", 890],
        ["CUST-007", "Grace Liu", "SEG-CASUAL", "APAC", "2024-06-15", 1120],
        ["CUST-008", "Henry Brown", "SEG-NEW", "US-East", "2025-11-01", 145],
        ["CUST-009", "Irene Nakamura", "SEG-NEW", "APAC", "2025-12-10", 78],
        ["CUST-010", "James O'Brien", "SEG-WINBACK", "EU-West", "2022-04-20", 4560],
        ["CUST-011", "Karen Patel", "SEG-WINBACK", "US-East", "2023-02-14", 2340],
        ["CUST-012", "Leo Torres", "SEG-CASUAL", "US-West", "2024-09-05", 670],
    ]
    write_csv("DimCustomer.csv", headers, rows)


# ── Product Categories ─────────────────────────────────────────────────────
def generate_product_categories() -> None:
    headers = ["CategoryId", "CategoryName", "ParentCategoryId", "MarginPct"]
    rows = [
        ["CAT-ELECTRONICS", "Electronics", "", 18],
        ["CAT-PHONES", "Smartphones", "CAT-ELECTRONICS", 22],
        ["CAT-LAPTOPS", "Laptops", "CAT-ELECTRONICS", 15],
        ["CAT-ACCESSORIES", "Accessories", "CAT-ELECTRONICS", 45],
        ["CAT-HOME", "Home & Garden", "", 35],
        ["CAT-FURNITURE", "Furniture", "CAT-HOME", 30],
        ["CAT-KITCHEN", "Kitchen", "CAT-HOME", 40],
        ["CAT-FASHION", "Fashion", "", 55],
        ["CAT-MENS", "Men's Clothing", "CAT-FASHION", 50],
        ["CAT-WOMENS", "Women's Clothing", "CAT-FASHION", 55],
    ]
    write_csv("DimProductCategory.csv", headers, rows)


# ── Products ───────────────────────────────────────────────────────────────
def generate_products() -> None:
    headers = ["ProductId", "ProductName", "CategoryId", "SupplierId", "PriceUSD", "StockQty", "Rating"]
    rows = [
        ["PROD-PHONE-001", "Galaxy Ultra S25", "CAT-PHONES", "SUPP-SAMSUNG", 1199, 500, 4.7],
        ["PROD-PHONE-002", "iPhone 16 Pro", "CAT-PHONES", "SUPP-APPLE", 1099, 800, 4.8],
        ["PROD-PHONE-003", "Pixel 10", "CAT-PHONES", "SUPP-GOOGLE", 899, 300, 4.5],
        ["PROD-LAPTOP-001", "MacBook Pro M4", "CAT-LAPTOPS", "SUPP-APPLE", 2499, 200, 4.9],
        ["PROD-LAPTOP-002", "ThinkPad X1 Carbon", "CAT-LAPTOPS", "SUPP-LENOVO", 1649, 350, 4.6],
        ["PROD-ACC-001", "AirPods Pro 3", "CAT-ACCESSORIES", "SUPP-APPLE", 249, 1200, 4.7],
        ["PROD-ACC-002", "USB-C Hub 12-in-1", "CAT-ACCESSORIES", "SUPP-ANKER", 79, 2000, 4.4],
        ["PROD-FURN-001", "Ergonomic Standing Desk", "CAT-FURNITURE", "SUPP-UPLIFT", 699, 150, 4.6],
        ["PROD-FURN-002", "Mesh Office Chair", "CAT-FURNITURE", "SUPP-HERMANM", 1295, 80, 4.8],
        ["PROD-KITCHEN-001", "Smart Coffee Maker", "CAT-KITCHEN", "SUPP-BREVILLE", 299, 400, 4.3],
        ["PROD-MENS-001", "Merino Wool Sweater", "CAT-MENS", "SUPP-EVERLANE", 98, 600, 4.5],
        ["PROD-WOMENS-001", "Cashmere Wrap Scarf", "CAT-WOMENS", "SUPP-EVERLANE", 148, 250, 4.6],
    ]
    write_csv("DimProduct.csv", headers, rows)


# ── Campaigns ──────────────────────────────────────────────────────────────
def generate_campaigns() -> None:
    headers = ["CampaignId", "CampaignName", "CampaignType", "TargetSegmentId", "StartDate", "EndDate", "BudgetUSD"]
    rows = [
        ["CAMP-HOLIDAY-2025", "Holiday Gift Guide 2025", "Seasonal", "SEG-LOYAL", "2025-11-15", "2025-12-31", 50000],
        ["CAMP-VIP-EXCLUS", "VIP Early Access", "Loyalty", "SEG-VIP", "2025-10-01", "2026-03-31", 25000],
        ["CAMP-NEWUSER-Q1", "New User Welcome Q1", "Onboarding", "SEG-NEW", "2026-01-01", "2026-03-31", 30000],
        ["CAMP-WINBACK-Q4", "Win-Back Q4 2025", "Re-engagement", "SEG-WINBACK", "2025-10-01", "2025-12-31", 15000],
        ["CAMP-FLASH-FEB", "Flash Sale Feb 2026", "Promotional", "SEG-CASUAL", "2026-02-01", "2026-02-14", 20000],
        ["CAMP-CROSS-SELL", "Cross-Sell Electronics", "Cross-Sell", "SEG-LOYAL", "2025-09-01", "2026-02-28", 10000],
    ]
    write_csv("DimCampaign.csv", headers, rows)


# ── Suppliers ──────────────────────────────────────────────────────────────
def generate_suppliers() -> None:
    headers = ["SupplierId", "SupplierName", "Country", "LeadTimeDays", "ReliabilityScore"]
    rows = [
        ["SUPP-APPLE", "Apple Inc.", "United States", 3, 98],
        ["SUPP-SAMSUNG", "Samsung Electronics", "South Korea", 5, 95],
        ["SUPP-GOOGLE", "Google LLC", "United States", 4, 96],
        ["SUPP-LENOVO", "Lenovo Group", "China", 7, 92],
        ["SUPP-ANKER", "Anker Innovations", "China", 10, 90],
        ["SUPP-UPLIFT", "Uplift Desk", "United States", 14, 88],
        ["SUPP-HERMANM", "Herman Miller", "United States", 21, 97],
        ["SUPP-BREVILLE", "Breville Group", "Australia", 12, 91],
        ["SUPP-EVERLANE", "Everlane", "United States", 5, 93],
    ]
    write_csv("DimSupplier.csv", headers, rows)


# ── Warehouses ─────────────────────────────────────────────────────────────
def generate_warehouses() -> None:
    headers = ["WarehouseId", "WarehouseName", "Region", "CapacityUnits", "CurrentUtilPct"]
    rows = [
        ["WH-US-EAST", "East Coast DC", "US-East", 100000, 72],
        ["WH-US-WEST", "West Coast DC", "US-West", 80000, 65],
        ["WH-EU-CENTRAL", "EU Central DC", "EU-West", 60000, 58],
        ["WH-APAC-SG", "APAC Singapore DC", "APAC", 40000, 45],
    ]
    write_csv("DimWarehouse.csv", headers, rows)


# ── SLA Policies ───────────────────────────────────────────────────────────
def generate_sla_policies() -> None:
    headers = ["SLAId", "SLAName", "SegmentId", "MaxDeliveryDays", "ReturnWindowDays", "SupportTier"]
    rows = [
        ["SLA-VIP-PREMIUM", "VIP Premium Service", "SEG-VIP", 1, 90, "Dedicated"],
        ["SLA-LOYAL-STANDARD", "Loyal Customer Standard", "SEG-LOYAL", 3, 60, "Priority"],
        ["SLA-CASUAL-BASIC", "Casual Basic", "SEG-CASUAL", 5, 30, "Standard"],
        ["SLA-NEW-WELCOME", "New Customer Welcome", "SEG-NEW", 3, 45, "Priority"],
        ["SLA-WINBACK-OFFER", "Win-Back Special", "SEG-WINBACK", 3, 60, "Priority"],
    ]
    write_csv("DimSLAPolicy.csv", headers, rows)


def main() -> None:
    print("Generating customer-recommendation topology data ...")
    generate_customer_segments()
    generate_customers()
    generate_product_categories()
    generate_products()
    generate_campaigns()
    generate_suppliers()
    generate_warehouses()
    generate_sla_policies()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
