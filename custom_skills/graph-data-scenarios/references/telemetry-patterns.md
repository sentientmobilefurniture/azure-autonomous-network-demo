# Telemetry Generation Patterns

Extracted from the reference implementation in
`data/scripts/generate_alert_stream.py` (409 lines).

## AlertStream CSV

### Structure

```
AlertId, Timestamp, SourceNodeId, SourceNodeType,
AlertType, Severity, Description,
<Metric1>, <Metric2>, <Metric3>, <Metric4>
```

The metric columns are domain-specific. For telco-noc:
`OpticalPowerDbm, BitErrorRate, CPUUtilPct, PacketLossPct`

For a cloud scenario these might be:
`TemperatureCelsius, CPUUtilPct, MemoryUtilPct, DiskIOPS`

### The No-Null Rule (Critical)

**Every numeric column must be populated in every row.** The downstream anomaly
detector (`scripts/cosmos/query_anomaly.py`) sends batches of rows to the Azure
Anomaly Detector API, which rejects rows with null/missing values.

Each alert row captures a **full telemetry snapshot** — like an SNMP poll
returning all OIDs simultaneously. The `AlertType` indicates which metric
*triggered* the threshold, but all other metrics still have their current
(normal-range) values.

```python
def add(offset, node_id, node_type, alert_type, severity, description,
        optical=None, ber=None, cpu=None, pkt_loss=None):
    """Add an alert row. Any metric not explicitly set gets a normal-range value."""
    snap = baseline_snapshot()  # All-normal defaults
    alerts.append([
        f"ALT-20260206-{counter:06d}",
        ts(offset), node_id, node_type,
        alert_type, severity, description,
        optical if optical is not None else snap["optical"],  # ← Never null
        ber if ber is not None else snap["ber"],
        cpu if cpu is not None else snap["cpu"],
        pkt_loss if pkt_loss is not None else snap["pkt_loss"],
    ])
```

### Baseline Period

The **baseline** is critical for anomaly detection. Without it, the model has
no "normal" to compare against.

```
Duration:   54 hours (2 days 6h) before the incident
Alert rate: ~1 per minute (~3,000 total)
Severity:   WARNING / MINOR only
Types:      HIGH_CPU, PACKET_LOSS_THRESHOLD, DUPLICATE_ALERT, SERVICE_DEGRADATION
Values:     Slightly elevated but within normal range (e.g. CPU 55-75%)
```

Implementation pattern:

```python
baseline_start = -54 * 3600   # seconds before incident
baseline_end = -60             # stop 1 minute before storm
num_baseline_alerts = random.randint(2800, 3400)

for _ in range(num_baseline_alerts):
    offset = random.uniform(baseline_start, baseline_end)
    node, node_type = random.choice(all_nodes)
    # Select a random low-severity alert type appropriate for this node type
    alert_def = random.choice(baseline_alerts_by_type[node_type])
    add(offset, node, node_type, alert_def.type, alert_def.severity, ...)
```

**Define baseline alert types per entity type** — not all alert types make sense
for all node types:

```python
baseline_alerts_by_type = {
    "CoreRouter": [
        ("HIGH_CPU", "WARNING", "CPU utilization {cpu}% — routine process spike"),
        ("PACKET_LOSS_THRESHOLD", "MINOR", "Packet loss {pkt}% — transient microloop"),
    ],
    "AggSwitch": [
        ("HIGH_CPU", "WARNING", "CPU utilization {cpu}% — routine process spike"),
        ("DUPLICATE_ALERT", "MINOR", "Periodic keepalive timeout — auto-recovered"),
    ],
    # ...
}
```

### Incident Cascade Timeline

The cascade models how a physical failure propagates through the network stack.
Each tier fires after a realistic delay:

```
T+0s     ROOT_CAUSE on the failing component                      (1 alert)
T+2s     PROTOCOL_LOSS (BGP/OSPF/connectivity)                    (~2-4 alerts)
T+5s     ADJACENCY_DOWN (routing protocol adjacencies)            (~4 alerts)
T+10s    ROUTE_WITHDRAWAL (prefix withdrawals)                    (~20 alerts)
T+15s    HIGH_CPU (reconvergence processing)                      (~50 alerts)
T+30s    PACKET_LOSS_THRESHOLD (downstream propagation)           (~200 alerts)
T+60s    SERVICE_DEGRADATION (customer-facing impact)             (~500 alerts)
T+70-90s DUPLICATE_ALERT + flapping (alert storm tail)            (fills to ~2000)
```

**Key implementation details:**

1. **Jitter** — add ±2s random jitter to each tier's offset so alerts don't
   all land on the exact same timestamp:
   ```python
   def jitter(base: float, spread: float = 2.0) -> float:
       return base + random.uniform(-spread, spread)
   ```

2. **Escalating severity** — `CRITICAL` at the root cause, `MAJOR` for
   infrastructure, `WARNING` for downstream, `MINOR` for flapping.

3. **Escalating metric values** — CPU climbs from 78% → 99%, packet loss
   from 2% → 25% as you move down the cascade.

4. **Entity ID lists** — define constants at the top of the file listing
   which nodes are impacted per tier:
   ```python
   IMPACTED_CORE_ROUTERS = ["CORE-SYD-01", "CORE-MEL-01"]
   IMPACTED_AGG = ["AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01", ...]
   IMPACTED_SERVICES = ["VPN-ACME-CORP", "VPN-BIGBANK", ...]
   REROUTE_LINKS = ["LINK-SYD-BNE-FIBRE-01", "LINK-MEL-BNE-FIBRE-01"]
   ```

5. **Sort by timestamp** before writing — the anomaly detector expects
   chronological order:
   ```python
   alerts.sort(key=lambda r: r[1])
   ```

### Adapting the Cascade for Other Domains

| Domain | Root Cause | Cascade Pattern |
|--------|-----------|-----------------|
| Telco | Fibre cut | LINK_DOWN → BGP_PEER_LOSS → OSPF_DOWN → ROUTE_WITHDRAWAL → HIGH_CPU → PACKET_LOSS → SERVICE_DEGRADATION |
| Cloud | Cooling failure | COOLING_FAILURE → THERMAL_WARNING → THERMAL_SHUTDOWN → VM_UNREACHABLE → SERVICE_DEGRADATION → FAILOVER_TRIGGERED |
| Power grid | Transformer failure | TRANSFORMER_TRIP → BREAKER_OPEN → LOAD_SHED → FREQUENCY_DEVIATION → GENERATOR_RAMP → ISLAND_DETECTED |

The cascade structure is the same — only the alert types and metric names change.

## LinkTelemetry CSV (or equivalent per-component metrics)

### Structure

Regular time-series samples for infrastructure components:

```
LinkId, Timestamp, UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs
```

### Baseline + Anomaly Pattern

```python
# 72 hours of data at 5-min intervals (60h before + 12h after incident)
start_time = INCIDENT_START - timedelta(hours=60)
interval_minutes = 5
num_samples = (72 * 60) // interval_minutes  # 864 per component

for component in ALL_COMPONENTS:
    for i in range(num_samples):
        sample_time = start_time + timedelta(minutes=i * interval_minutes)

        if is_failed_component and sample_time >= INCIDENT_START:
            # Anomalous values (dead/degraded)
            rows.append([component, sample_ts, 0.0, -40.0, 1.0, 9999.0])
        elif is_backup_component and sample_time >= INCIDENT_START:
            # Elevated values (absorbing redirected traffic)
            rows.append([component, sample_ts, 75.0, normal(), normal(), elevated()])
        else:
            # Normal baseline with slight random variation
            rows.append([component, sample_ts, baseline ± 5%, normal(), normal(), normal()])
```

### Per-Component Baseline Profiles

Define realistic baseline values per component:

```python
baseline_profiles = {
    "LINK-SYD-MEL-FIBRE-01": {"util": 55.0, "latency": (4, 8)},
    "LINK-SYD-MEL-FIBRE-02": {"util": 38.0, "latency": (4, 8)},
    # ...
}
```

The backup/alternate paths should have **lower baseline utilisation** than the
primary path — this makes the post-incident spike visually obvious.

## Reproducibility

Always seed the random number generator:

```python
random.seed(42)
```

This ensures identical output on every run, which is essential for:
- Consistent demo experiences
- Diffing output after code changes
- Reliable integration tests
