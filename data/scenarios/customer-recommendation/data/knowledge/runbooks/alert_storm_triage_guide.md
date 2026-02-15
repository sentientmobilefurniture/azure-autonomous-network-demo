# Alert Storm Triage — E-Commerce Recommendation Platform

## What Triggers an Alert Storm?

In the recommendation domain, alert storms cascade through the graph:

```
Model/Algorithm → Campaign → Segment → Customer → Product → Warehouse
```

Unlike infrastructure storms (physical → logical), recommendation storms
flow through the **business logic layer** — model decisions propagate to
customer-facing metrics.

## Triage Process

### Step 1: Find the Root Cause
The **earliest CRITICAL alert** is usually the root cause. Common patterns:
- MODEL_BIAS_DETECTED → recommendation engine issue
- STALE_PRICE_FEED → data pipeline issue
- SEGMENT_MISMATCH → campaign configuration issue

### Step 2: Trace Impact Through the Graph
```
g.V().has('Campaign','CampaignId','<ROOT_CAUSE_CAMPAIGN>')
  .out('targets')           // → affected segments
  .in('belongs_to')         // → affected customers
  .outE('purchased')        // → purchases with returns
  .has('returned','Y')
  .count()                  // → return volume
```

### Step 3: Assess Revenue Impact
- Compare current AvgOrderValueUSD against segment baseline
- Calculate estimated daily revenue loss from return rate spike
- Check SLA breach risk for affected segments

### Step 4: Determine Containment
- Can we disable the affected campaigns without broader impact?
- Can we roll back the recommendation model quickly?
- Do we need to pause specific product recommendations?
