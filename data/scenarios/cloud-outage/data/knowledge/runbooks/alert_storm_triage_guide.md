# Alert Storm Triage — Cloud Infrastructure

## What Is an Alert Storm?

A burst of 500+ alerts within 90 seconds, typically triggered by a single
root cause propagating through the infrastructure dependency chain.

## Triage Process

### Step 1: Identify the Root Cause Tier

Alert storms cascade **upward** through the stack:

```
Physical (Cooling/Power) → Rack → Host → VM → Service → LoadBalancer
```

The **earliest CRITICAL alert** is usually the root cause. Sort alerts by
timestamp and look for the first non-WARNING alert.

### Step 2: Determine Blast Radius

Use the graph to trace from the root cause entity:
```
g.V().has('<EntityType>','<IdProp>','<RootCauseId>')
  .repeat(out()).until(hasLabel('Service'))
  .dedup().valueMap(true)
```

### Step 3: Check SLA Impact

For each impacted service, check its SLA:
```
g.V().has('Service','ServiceId','<SVC_ID>').in('governs').valueMap(true)
```

### Step 4: Verify Failover Status

Check if load balancers have activated failover:
- Look for FAILOVER_TRIGGERED alerts
- Verify healthy backend count per LB
- Confirm AZ-B is absorbing traffic (HostMetrics CPU/Memory elevation)

### Step 5: Suppress Duplicate Alerts

Once root cause is identified, suppress all downstream alerts. The platform
should suppress ~95% of alert storm alerts automatically.
