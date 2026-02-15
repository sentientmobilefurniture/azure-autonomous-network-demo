# Telemetry Generation Patterns

## AlertStream CSV

### Structure

```
AlertId, Timestamp, SourceNodeId, SourceNodeType,
AlertType, Severity, Description,
<Metric1>, <Metric2>, <Metric3>, <Metric4>
```

The metric columns are domain-specific:

| Domain | Metric Columns |
|--------|----------------|
| Telco | `OpticalPowerDbm`, `BitErrorRate`, `CPUUtilPct`, `PacketLossPct` |
| Cloud | `TemperatureCelsius`, `CPUUtilPct`, `MemoryUtilPct`, `DiskIOPS` |
| E-commerce | `ClickRatePct`, `ConversionRatePct`, `ReturnRatePct`, `AvgOrderValueUSD` |

### The No-Null Rule (CRITICAL)

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

### Normal-Range Value Generators

Define functions that return normal-range values for each metric:

```python
def normal_optical() -> float:
    """Normal optical power: -3.5 to -2.5 dBm."""
    return round(random.uniform(-3.5, -2.5), 1)

def normal_cpu() -> float:
    """Normal CPU: 15-45%."""
    return round(random.uniform(15, 45), 1)

def baseline_snapshot() -> dict:
    """Full telemetry snapshot with all-normal values."""
    return {
        "optical": normal_optical(),
        "ber": normal_ber(),
        "cpu": normal_cpu(),
        "pkt_loss": normal_pkt_loss(),
    }
```

For cloud scenarios:

```python
def normal_temperature() -> float:
    """Normal data center temperature: 22-28°C."""
    return round(random.uniform(22, 28), 1)

def normal_disk_iops() -> int:
    """Normal IOPS: 200-800."""
    return random.randint(200, 800)
```

### Baseline Period

The **baseline** is critical for anomaly detection — without it, the model has
no "normal" to compare against.

```
Duration:   54 hours (2 days 6h) before the incident
Alert rate: ~1 per minute (~3,000 total)
Severity:   WARNING / MINOR only
Types:      Domain-appropriate low-severity alert types
Values:     Slightly elevated but within normal range
```

```python
INCIDENT_START = datetime(2026, 2, 6, 14, 30, 0, tzinfo=timezone.utc)
random.seed(42)

baseline_start = -54 * 3600   # seconds before incident
baseline_end = -60             # stop 1 minute before storm
num_baseline_alerts = random.randint(2800, 3400)

for _ in range(num_baseline_alerts):
    offset = random.uniform(baseline_start, baseline_end)
    node, node_type = random.choice(all_nodes)
    alert_def = random.choice(baseline_alerts_by_type[node_type])
    add(offset, node, node_type, alert_def.type, alert_def.severity, ...)
```

**Define baseline alert types per entity type** — not all alert types make sense
for all node types:

```python
# Telco example
baseline_alerts_by_type = {
    "CoreRouter": [
        ("HIGH_CPU", "WARNING", "CPU utilization {cpu}% — routine process spike"),
        ("PACKET_LOSS_THRESHOLD", "MINOR", "Packet loss {pkt}% — transient microloop"),
    ],
    "AggSwitch": [
        ("HIGH_CPU", "WARNING", "CPU utilization {cpu}% — routine process spike"),
        ("DUPLICATE_ALERT", "MINOR", "Periodic keepalive timeout — auto-recovered"),
    ],
    "TransportLink": [
        ("PACKET_LOSS_THRESHOLD", "MINOR", "Packet loss {pkt}% — transient microloop"),
        ("SERVICE_DEGRADATION", "MINOR", "Brief latency increase — within SLA"),
    ],
}

# Cloud example
baseline_alerts_by_type = {
    "Host": [
        ("HIGH_CPU", "WARNING", "CPU utilization {cpu}% — batch job spike"),
        ("HIGH_MEMORY", "MINOR", "Memory {mem}% — cache pressure"),
    ],
    "VirtualMachine": [
        ("HIGH_CPU", "WARNING", "vCPU utilization {cpu}% — container scaling"),
        ("DISK_IO_HIGH", "MINOR", "IOPS {iops} — log rotation"),
    ],
    "LoadBalancer": [
        ("HEALTH_CHECK_FLAP", "MINOR", "Backend health check timeout — recovered"),
    ],
}
```

### Incident Cascade Timeline

The cascade models how a failure propagates through the infrastructure.
Each tier fires after a realistic delay:

```
T+0s     ROOT_CAUSE on the failing component                      (1 alert)
T+2s     PROTOCOL_LOSS / CONNECTIVITY_LOSS                        (~2-4 alerts)
T+5s     SECOND_ORDER_FAILURE (adjacencies/shutdowns)             (~4 alerts)
T+10s    PROPAGATION (withdrawals/VM unreachable)                  (~20 alerts)
T+15s    RESOURCE_EXHAUSTION (CPU/memory/temperature)             (~50 alerts)
T+30s    DOWNSTREAM_IMPACT (packet loss/latency)                   (~200 alerts)
T+60s    SERVICE_DEGRADATION (customer-facing impact)              (~500 alerts)
T+70-90s FLAPPING / DUPLICATE_ALERT (storm tail)                   (fills to ~2000)
```

**Domain-specific cascade examples:**

| Domain | Root Cause | Cascade |
|--------|-----------|---------|
| Telco | Fibre cut | `LINK_DOWN` → `BGP_PEER_LOSS` → `OSPF_ADJACENCY_DOWN` → `ROUTE_WITHDRAWAL` → `HIGH_CPU` → `PACKET_LOSS_THRESHOLD` → `SERVICE_DEGRADATION` |
| Cloud | Cooling failure | `COOLING_FAILURE` → `THERMAL_WARNING` → `THERMAL_SHUTDOWN` → `VM_UNREACHABLE` → `SERVICE_DEGRADATION` → `FAILOVER_TRIGGERED` |
| E-commerce | Model deploy | `MODEL_DEPLOYED` → `RECOMMENDATION_DRIFT` → `CLICK_ANOMALY` → `CONVERSION_DROP` → `RETURN_SPIKE` → `REVENUE_IMPACT` |

**Key implementation details:**

1. **Jitter** — add ±2s random jitter so alerts don't all land on the exact timestamp:
   ```python
   def jitter(base: float, spread: float = 2.0) -> float:
       return base + random.uniform(-spread, spread)
   ```

2. **Escalating severity** — `CRITICAL` at root cause, `MAJOR` for infra, `WARNING` downstream

3. **Escalating metric values** — CPU climbs 78% → 99%, packet loss 2% → 25%

4. **Entity ID lists** — define constants listing impacted nodes per tier:
   ```python
   IMPACTED_CORE_ROUTERS = ["CORE-SYD-01", "CORE-MEL-01"]
   IMPACTED_AGG = ["AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01", ...]
   IMPACTED_SERVICES = ["VPN-ACME-CORP", "VPN-BIGBANK", ...]
   ```

5. **Sort by timestamp** before writing:
   ```python
   alerts.sort(key=lambda r: r[1])
   ```

### Timestamp Helper

```python
INCIDENT_START = datetime(2026, 2, 6, 14, 30, 0, tzinfo=timezone.utc)

def ts(offset_seconds: float) -> str:
    """Return ISO timestamp offset from incident start."""
    return (INCIDENT_START + timedelta(seconds=offset_seconds)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
```

## Per-Component Telemetry CSV (LinkTelemetry / HostMetrics / etc.)

### Structure

Regular time-series samples for infrastructure components:

```
# Telco: LinkTelemetry.csv
LinkId, Timestamp, UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs

# Cloud: HostMetrics.csv
HostId, Timestamp, CPUUtilPct, MemoryUtilPct, TemperatureCelsius, DiskIOPS
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
            rows.append([component, ts, 0.0, -40.0, 1.0, 9999.0])
        elif is_backup_component and sample_time >= INCIDENT_START:
            # Elevated values (absorbing redirected traffic)
            rows.append([component, ts, 75.0, normal(), normal(), elevated()])
        else:
            # Normal baseline with slight random variation (±5%)
            rows.append([component, ts, baseline ± 5%, normal(), normal(), normal()])
```

### Per-Component Baseline Profiles

Define realistic baseline values with variation range:

```python
# Telco link profiles
baseline_profiles = {
    "LINK-SYD-MEL-FIBRE-01": {"util": 55.0, "latency": (4, 8)},   # Primary (higher load)
    "LINK-SYD-MEL-FIBRE-02": {"util": 38.0, "latency": (4, 8)},   # Backup (lower load)
    "LINK-SYD-BNE-FIBRE-01": {"util": 42.0, "latency": (6, 12)},
}

# Cloud host profiles
baseline_profiles = {
    "HOST-USE-A-01-01": {"cpu": 35.0, "mem": 45.0, "temp": 25.0, "iops": 450},
    "HOST-USE-A-02-01": {"cpu": 55.0, "mem": 65.0, "temp": 27.0, "iops": 700},  # Higher load
}
```

Backup/alternate paths should have **lower baseline** than primary — makes the
post-incident spike visually obvious in dashboards.

## Reproducibility

Always seed the random number generator:

```python
random.seed(42)
```

This ensures identical output on every run — essential for consistent demos,
diffing output after code changes, and reliable integration tests.
