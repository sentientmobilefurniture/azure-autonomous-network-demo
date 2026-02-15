# Return Rate Investigation — Triage Guide

## When to Use
- ReturnRatePct exceeds 10% for any segment (baseline: 1–3%)
- RETURN_RATE_SPIKE alert from any CustomerSegment
- Warehouse RETURN_VOLUME_SPIKE alert

## Step 1: Identify Which Segments Are Affected
Check RecommendationMetrics for segments with elevated return rates.
Normal return rates by segment:
- SEG-VIP: ~1.2%
- SEG-LOYAL: ~2.0%
- SEG-CASUAL: ~3.0%
- SEG-NEW: ~2.5%
- SEG-WINBACK: ~3.5%

## Step 2: Identify Which Products Are Being Returned
Look at FactPurchaseHistory for ReturnedFlag = 'Y':
```
g.V().hasLabel('Customer').outE('purchased').has('returned','Y').inV().valueMap(true)
```

## Step 3: Check Product-Customer Fit
For returned products, verify:
- Is the product price appropriate for the customer's segment?
- Was the customer targeted by a campaign for this product?
- Is this a product quality issue (check supplier ReliabilityScore)?

## Step 4: Assess Warehouse Impact
High return volumes can overwhelm return processing:
- Check warehouse CurrentUtilPct
- Verify return processing capacity
- Escalate to warehouse operations if utilisation > 85%

## Common Root Causes
1. **Model bias** — recommendation engine surfacing wrong products for segment
2. **Campaign targeting error** — campaign reaching wrong segment
3. **Product quality issue** — supplier problem causing defect returns
4. **Price display error** — customers received wrong price information
