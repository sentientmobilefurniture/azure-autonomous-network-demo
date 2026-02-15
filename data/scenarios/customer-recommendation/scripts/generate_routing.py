"""
Generate junction/routing CSV files for the customer-recommendation scenario.

Outputs 3 CSV files:
  - FactPurchaseHistory.csv       — customer-product purchase relationships
  - FactCampaignTargeting.csv     — campaign-product promotion links
  - FactProductWarehouse.csv      — product-warehouse stocking relationships
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


def generate_purchase_history() -> None:
    """Which customers bought which products — drives recommendation edges."""
    headers = ["CustomerId", "ProductId", "PurchaseDate", "Quantity", "RevenueUSD", "ReturnedFlag"]
    rows = [
        # VIP customers — diverse purchase history
        ["CUST-001", "PROD-PHONE-001", "2025-06-15", 1, 1199, "N"],
        ["CUST-001", "PROD-ACC-001", "2025-06-15", 1, 249, "N"],
        ["CUST-001", "PROD-LAPTOP-001", "2025-09-20", 1, 2499, "N"],
        ["CUST-001", "PROD-FURN-001", "2025-11-10", 1, 699, "N"],
        ["CUST-002", "PROD-PHONE-002", "2025-05-01", 1, 1099, "N"],
        ["CUST-002", "PROD-LAPTOP-001", "2025-07-22", 1, 2499, "N"],
        ["CUST-002", "PROD-FURN-002", "2025-10-05", 1, 1295, "N"],
        ["CUST-002", "PROD-ACC-002", "2025-12-20", 2, 158, "N"],
        # Loyal customers
        ["CUST-003", "PROD-PHONE-003", "2025-08-12", 1, 899, "N"],
        ["CUST-003", "PROD-ACC-001", "2025-08-12", 1, 249, "N"],
        ["CUST-003", "PROD-KITCHEN-001", "2025-11-25", 1, 299, "N"],
        ["CUST-004", "PROD-LAPTOP-002", "2025-04-18", 1, 1649, "N"],
        ["CUST-004", "PROD-MENS-001", "2025-09-30", 2, 196, "N"],
        ["CUST-005", "PROD-WOMENS-001", "2025-07-14", 1, 148, "N"],
        ["CUST-005", "PROD-KITCHEN-001", "2025-12-01", 1, 299, "N"],
        # Casual shoppers
        ["CUST-006", "PROD-ACC-002", "2025-06-10", 1, 79, "N"],
        ["CUST-007", "PROD-PHONE-003", "2025-10-22", 1, 899, "N"],
        # New customers — anomalous returns (the incident)
        ["CUST-008", "PROD-WOMENS-001", "2026-01-15", 1, 148, "Y"],  # Wrong recommendation!
        ["CUST-008", "PROD-KITCHEN-001", "2026-01-20", 1, 299, "Y"],  # Wrong recommendation!
        ["CUST-009", "PROD-FURN-002", "2026-01-18", 1, 1295, "Y"],  # Way too expensive for new user
        # Win-back customers
        ["CUST-010", "PROD-MENS-001", "2025-01-10", 1, 98, "N"],
        ["CUST-011", "PROD-ACC-001", "2024-11-30", 1, 249, "N"],
        # More casual
        ["CUST-012", "PROD-ACC-002", "2025-10-15", 1, 79, "N"],
    ]
    write_csv("FactPurchaseHistory.csv", headers, rows)


def generate_campaign_targeting() -> None:
    """Which campaigns promote which products."""
    headers = ["CampaignId", "ProductId", "DiscountPct", "Priority"]
    rows = [
        # Holiday campaign — wide product range
        ["CAMP-HOLIDAY-2025", "PROD-PHONE-001", 10, "HIGH"],
        ["CAMP-HOLIDAY-2025", "PROD-PHONE-002", 5, "HIGH"],
        ["CAMP-HOLIDAY-2025", "PROD-LAPTOP-001", 8, "MEDIUM"],
        ["CAMP-HOLIDAY-2025", "PROD-ACC-001", 15, "HIGH"],
        ["CAMP-HOLIDAY-2025", "PROD-KITCHEN-001", 20, "MEDIUM"],
        # VIP exclusive
        ["CAMP-VIP-EXCLUS", "PROD-LAPTOP-001", 12, "HIGH"],
        ["CAMP-VIP-EXCLUS", "PROD-FURN-002", 10, "HIGH"],
        ["CAMP-VIP-EXCLUS", "PROD-PHONE-001", 15, "MEDIUM"],
        # New user welcome — LOW price items
        ["CAMP-NEWUSER-Q1", "PROD-ACC-002", 25, "HIGH"],
        ["CAMP-NEWUSER-Q1", "PROD-MENS-001", 20, "MEDIUM"],
        ["CAMP-NEWUSER-Q1", "PROD-WOMENS-001", 20, "MEDIUM"],
        # Win-back — high-value items to re-engage
        ["CAMP-WINBACK-Q4", "PROD-PHONE-003", 15, "HIGH"],
        ["CAMP-WINBACK-Q4", "PROD-LAPTOP-002", 10, "MEDIUM"],
        # Flash sale — accessories
        ["CAMP-FLASH-FEB", "PROD-ACC-001", 30, "HIGH"],
        ["CAMP-FLASH-FEB", "PROD-ACC-002", 40, "HIGH"],
        ["CAMP-FLASH-FEB", "PROD-KITCHEN-001", 25, "MEDIUM"],
        # Cross-sell electronics
        ["CAMP-CROSS-SELL", "PROD-ACC-001", 10, "HIGH"],
        ["CAMP-CROSS-SELL", "PROD-ACC-002", 15, "HIGH"],
    ]
    write_csv("FactCampaignTargeting.csv", headers, rows)


def generate_product_warehouse() -> None:
    """Which warehouses stock which products."""
    headers = ["ProductId", "WarehouseId", "StockQty", "ReorderPoint"]
    rows = [
        ["PROD-PHONE-001", "WH-US-EAST", 200, 50],
        ["PROD-PHONE-001", "WH-US-WEST", 150, 40],
        ["PROD-PHONE-001", "WH-APAC-SG", 100, 30],
        ["PROD-PHONE-002", "WH-US-EAST", 300, 80],
        ["PROD-PHONE-002", "WH-US-WEST", 250, 60],
        ["PROD-PHONE-002", "WH-EU-CENTRAL", 150, 40],
        ["PROD-PHONE-003", "WH-US-EAST", 120, 30],
        ["PROD-PHONE-003", "WH-APAC-SG", 80, 20],
        ["PROD-LAPTOP-001", "WH-US-EAST", 80, 20],
        ["PROD-LAPTOP-001", "WH-US-WEST", 60, 15],
        ["PROD-LAPTOP-002", "WH-US-EAST", 150, 40],
        ["PROD-LAPTOP-002", "WH-EU-CENTRAL", 100, 25],
        ["PROD-ACC-001", "WH-US-EAST", 500, 100],
        ["PROD-ACC-001", "WH-US-WEST", 400, 80],
        ["PROD-ACC-001", "WH-EU-CENTRAL", 200, 50],
        ["PROD-ACC-002", "WH-US-EAST", 800, 200],
        ["PROD-ACC-002", "WH-US-WEST", 600, 150],
        ["PROD-FURN-001", "WH-US-EAST", 60, 15],
        ["PROD-FURN-001", "WH-US-WEST", 50, 12],
        ["PROD-FURN-002", "WH-US-EAST", 30, 8],
        ["PROD-KITCHEN-001", "WH-US-EAST", 150, 40],
        ["PROD-KITCHEN-001", "WH-EU-CENTRAL", 100, 25],
        ["PROD-MENS-001", "WH-US-EAST", 250, 60],
        ["PROD-MENS-001", "WH-EU-CENTRAL", 200, 50],
        ["PROD-WOMENS-001", "WH-US-EAST", 100, 25],
        ["PROD-WOMENS-001", "WH-EU-CENTRAL", 80, 20],
    ]
    write_csv("FactProductWarehouse.csv", headers, rows)


def main() -> None:
    print("Generating customer-recommendation routing/junction data ...")
    generate_purchase_history()
    generate_campaign_targeting()
    generate_product_warehouse()
    print(f"\nAll files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
