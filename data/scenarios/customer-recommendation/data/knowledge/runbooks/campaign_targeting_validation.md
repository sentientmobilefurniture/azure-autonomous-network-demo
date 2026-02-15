# Campaign Targeting Validation — Operations Guide

## Purpose
Ensure campaigns only target products appropriate for their intended segments.

## Validation Checks

### Price-Segment Alignment
For each campaign, verify that promoted products are within the target
segment's spending range:

| Segment | Typical Order Value | Max Recommended Product Price |
|---------|-------------------|------------------------------|
| SEG-NEW | $50–150 | $300 |
| SEG-CASUAL | $50–200 | $500 |
| SEG-LOYAL | $100–500 | $2,000 |
| SEG-VIP | $200–2,000 | Unlimited |
| SEG-WINBACK | $50–200 | $500 |

### Graph Query for Validation
```
g.V().hasLabel('Campaign').as('c')
  .out('targets').as('seg')
  .select('c').out('promotes').as('prod')
  .select('seg','prod').by(valueMap(true))
```

### Automated Checks
- Run price-segment alignment check after every campaign configuration change
- Alert if any product in a campaign exceeds 2x the target segment's average order value
- Block campaign activation if > 50% of products exceed segment's MaxSpendUSD

## Historical Issues
- INC-2025-07-15-0018: VIP offers sent to casual users due to segment boundary overlap
- Current incident: Model bias pushing $1000+ products to SEG-NEW users
