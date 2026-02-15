# Customer Recommendation Engine Ontology — Full Schema

## Entity Types

### CustomerSegment (5 instances)

Customer segments based on purchase behavior and lifetime spend.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SegmentId** | String | **Primary key.** | `SEG-VIP` |
| SegmentName | String | Display name. | `VIP Customers` |
| Description | String | Segment description. | `Top 2% by lifetime spend` |
| MinSpendUSD | Integer | Min lifetime spend for segment. | `10000` |
| MaxSpendUSD | Integer | Max lifetime spend for segment. | `999999` |

**All instances:**

| SegmentId | SegmentName | MinSpendUSD | MaxSpendUSD |
|---|---|---|---|
| SEG-VIP | VIP Customers | 10000 | 999999 |
| SEG-LOYAL | Loyal Customers | 2000 | 9999 |
| SEG-CASUAL | Casual Shoppers | 200 | 1999 |
| SEG-NEW | New Customers | 0 | 199 |
| SEG-WINBACK | Win-Back Targets | 0 | 999999 |

---

### Customer (12 instances)

Individual customers.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **CustomerId** | String | **Primary key.** | `CUST-001` |
| CustomerName | String | Display name. | `Alice Chen` |
| SegmentId | String | Customer segment (FK → CustomerSegment.SegmentId). | `SEG-VIP` |
| Region | String | Geographic region. | `US-West` |
| JoinDate | String | Account creation date. | `2022-03-15` |
| LifetimeSpendUSD | Integer | Total lifetime spend. | `28450` |

**All instances:**

| CustomerId | CustomerName | SegmentId | Region | LifetimeSpendUSD |
|---|---|---|---|---|
| CUST-001 | Alice Chen | SEG-VIP | US-West | 28450 |
| CUST-002 | Bob Martinez | SEG-VIP | US-East | 34200 |
| CUST-003 | Carol Johnson | SEG-LOYAL | US-East | 5680 |
| CUST-004 | David Kim | SEG-LOYAL | EU-West | 7230 |
| CUST-005 | Eva Schmidt | SEG-LOYAL | EU-West | 3450 |
| CUST-006 | Frank Williams | SEG-CASUAL | US-West | 890 |
| CUST-007 | Grace Liu | SEG-CASUAL | APAC | 1120 |
| CUST-008 | Henry Brown | SEG-NEW | US-East | 145 |
| CUST-009 | Irene Nakamura | SEG-NEW | APAC | 78 |
| CUST-010 | James O'Brien | SEG-WINBACK | EU-West | 4560 |
| CUST-011 | Karen Patel | SEG-WINBACK | US-East | 2340 |
| CUST-012 | Leo Torres | SEG-CASUAL | US-West | 670 |

---

### ProductCategory (10 instances)

Product categories with optional parent hierarchy.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **CategoryId** | String | **Primary key.** | `CAT-ELECTRONICS` |
| CategoryName | String | Display name. | `Electronics` |
| ParentCategoryId | String | Parent category (FK, nullable). | `` (empty = top level) |
| MarginPct | Integer | Margin percentage. | `18` |

**All instances:**

| CategoryId | CategoryName | ParentCategoryId | MarginPct |
|---|---|---|---|
| CAT-ELECTRONICS | Electronics | | 18 |
| CAT-PHONES | Smartphones | CAT-ELECTRONICS | 22 |
| CAT-LAPTOPS | Laptops | CAT-ELECTRONICS | 15 |
| CAT-ACCESSORIES | Accessories | CAT-ELECTRONICS | 45 |
| CAT-HOME | Home & Garden | | 35 |
| CAT-FURNITURE | Furniture | CAT-HOME | 30 |
| CAT-KITCHEN | Kitchen | CAT-HOME | 40 |
| CAT-FASHION | Fashion | | 55 |
| CAT-MENS | Men's Clothing | CAT-FASHION | 50 |
| CAT-WOMENS | Women's Clothing | CAT-FASHION | 55 |

---

### Product (12 instances)

Individual products.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **ProductId** | String | **Primary key.** | `PROD-PHONE-001` |
| ProductName | String | Display name. | `Galaxy Ultra S25` |
| CategoryId | String | Category (FK → ProductCategory.CategoryId). | `CAT-PHONES` |
| SupplierId | String | Supplier (FK → Supplier.SupplierId). | `SUPP-SAMSUNG` |
| PriceUSD | Integer | Price in USD. | `1199` |
| StockQty | Integer | Current stock quantity. | `500` |
| Rating | Double | Customer rating (0–5). | `4.7` |

**All instances:**

| ProductId | ProductName | CategoryId | PriceUSD | Rating |
|---|---|---|---|---|
| PROD-PHONE-001 | Galaxy Ultra S25 | CAT-PHONES | 1199 | 4.7 |
| PROD-PHONE-002 | iPhone 16 Pro | CAT-PHONES | 1099 | 4.8 |
| PROD-PHONE-003 | Pixel 10 | CAT-PHONES | 899 | 4.5 |
| PROD-LAPTOP-001 | MacBook Pro M4 | CAT-LAPTOPS | 2499 | 4.9 |
| PROD-LAPTOP-002 | ThinkPad X1 Carbon | CAT-LAPTOPS | 1649 | 4.6 |
| PROD-ACC-001 | AirPods Pro 3 | CAT-ACCESSORIES | 249 | 4.7 |
| PROD-ACC-002 | USB-C Hub 12-in-1 | CAT-ACCESSORIES | 79 | 4.4 |
| PROD-FURN-001 | Ergonomic Standing Desk | CAT-FURNITURE | 699 | 4.6 |
| PROD-FURN-002 | Mesh Office Chair | CAT-FURNITURE | 1295 | 4.8 |
| PROD-KITCHEN-001 | Smart Coffee Maker | CAT-KITCHEN | 299 | 4.3 |
| PROD-MENS-001 | Merino Wool Sweater | CAT-MENS | 98 | 4.5 |
| PROD-WOMENS-001 | Cashmere Wrap Scarf | CAT-WOMENS | 148 | 4.6 |

---

### Campaign (6 instances)

Marketing campaigns targeting segments.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **CampaignId** | String | **Primary key.** | `CAMP-NEWUSER-Q1` |
| CampaignName | String | Display name. | `New User Welcome Q1` |
| CampaignType | String | Type. Values: `Seasonal`, `Loyalty`, `Onboarding`, `Re-engagement`, `Promotional`, `Cross-Sell`. | `Onboarding` |
| TargetSegmentId | String | Target segment (FK → CustomerSegment.SegmentId). | `SEG-NEW` |
| StartDate | String | Start date. | `2026-01-01` |
| EndDate | String | End date. | `2026-03-31` |
| BudgetUSD | Integer | Campaign budget. | `30000` |

**All instances:**

| CampaignId | CampaignName | CampaignType | TargetSegmentId | BudgetUSD |
|---|---|---|---|---|
| CAMP-HOLIDAY-2025 | Holiday Gift Guide 2025 | Seasonal | SEG-LOYAL | 50000 |
| CAMP-VIP-EXCLUS | VIP Early Access | Loyalty | SEG-VIP | 25000 |
| CAMP-NEWUSER-Q1 | New User Welcome Q1 | Onboarding | SEG-NEW | 30000 |
| CAMP-WINBACK-Q4 | Win-Back Q4 2025 | Re-engagement | SEG-WINBACK | 15000 |
| CAMP-FLASH-FEB | Flash Sale Feb 2026 | Promotional | SEG-CASUAL | 20000 |
| CAMP-CROSS-SELL | Cross-Sell Electronics | Cross-Sell | SEG-LOYAL | 10000 |

---

### Supplier (9 instances)

Product suppliers.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SupplierId** | String | **Primary key.** | `SUPP-APPLE` |
| SupplierName | String | Display name. | `Apple Inc.` |
| Country | String | Country of origin. | `United States` |
| LeadTimeDays | Integer | Shipping lead time in days. | `3` |
| ReliabilityScore | Integer | Reliability percentage (0–100). | `98` |

**All instances:**

| SupplierId | SupplierName | Country | LeadTimeDays | ReliabilityScore |
|---|---|---|---|---|
| SUPP-APPLE | Apple Inc. | United States | 3 | 98 |
| SUPP-SAMSUNG | Samsung Electronics | South Korea | 5 | 95 |
| SUPP-GOOGLE | Google LLC | United States | 4 | 96 |
| SUPP-LENOVO | Lenovo Group | China | 7 | 92 |
| SUPP-ANKER | Anker Innovations | China | 10 | 90 |
| SUPP-UPLIFT | Uplift Desk | United States | 14 | 88 |
| SUPP-HERMANM | Herman Miller | United States | 21 | 97 |
| SUPP-BREVILLE | Breville Group | Australia | 12 | 91 |
| SUPP-EVERLANE | Everlane | United States | 5 | 93 |

---

### Warehouse (4 instances)

Fulfillment centers.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **WarehouseId** | String | **Primary key.** | `WH-US-EAST` |
| WarehouseName | String | Display name. | `East Coast DC` |
| Region | String | Geographic region. | `US-East` |
| CapacityUnits | Integer | Total capacity. | `100000` |
| CurrentUtilPct | Integer | Current utilization percentage. | `72` |

**All instances:**

| WarehouseId | WarehouseName | Region | CapacityUnits | CurrentUtilPct |
|---|---|---|---|---|
| WH-US-EAST | East Coast DC | US-East | 100000 | 72 |
| WH-US-WEST | West Coast DC | US-West | 80000 | 65 |
| WH-EU-CENTRAL | EU Central DC | EU-West | 60000 | 58 |
| WH-APAC-SG | APAC Singapore DC | APAC | 40000 | 45 |

---

### SLAPolicy (5 instances)

SLA commitments governing customer segments.

| Column | Type | Purpose | Example Value |
|---|---|---|---|
| **SLAId** | String | **Primary key.** | `SLA-VIP-PREMIUM` |
| SLAName | String | Display name. | `VIP Premium Service` |
| SegmentId | String | Governed segment (FK → CustomerSegment.SegmentId). | `SEG-VIP` |
| MaxDeliveryDays | Integer | Max delivery days. | `1` |
| ReturnWindowDays | Integer | Return window in days. | `90` |
| SupportTier | String | Support tier. Values: `Dedicated`, `Priority`, `Standard`. | `Dedicated` |

**All instances:**

| SLAId | SegmentId | MaxDeliveryDays | ReturnWindowDays | SupportTier |
|---|---|---|---|---|
| SLA-VIP-PREMIUM | SEG-VIP | 1 | 90 | Dedicated |
| SLA-LOYAL-STANDARD | SEG-LOYAL | 3 | 60 | Priority |
| SLA-CASUAL-BASIC | SEG-CASUAL | 5 | 30 | Standard |
| SLA-NEW-WELCOME | SEG-NEW | 3 | 45 | Priority |
| SLA-WINBACK-OFFER | SEG-WINBACK | 3 | 60 | Priority |

---

## Relationships

### belongs_to: Customer → CustomerSegment

A customer belongs to a segment.

### in_category: Product → ProductCategory

A product belongs to a category.

### subcategory_of: ProductCategory → ProductCategory

A category is a subcategory of a parent category.

### supplied_by: Product → Supplier

A product is supplied by a supplier.

### targets: Campaign → CustomerSegment

A campaign targets a customer segment.

### governs_segment: SLAPolicy → CustomerSegment

An SLA policy governs a customer segment.

### purchased: Customer → Product

A customer has purchased a product. Edge properties: `purchase_date`, `quantity`, `revenue_usd`, `returned`.

### promotes: Campaign → Product

A campaign promotes a product. Edge properties: `discount_pct`, `priority`.

### stocked_at: Product → Warehouse

A product is stocked at a warehouse. Edge properties: `stock_qty`, `reorder_point`.
