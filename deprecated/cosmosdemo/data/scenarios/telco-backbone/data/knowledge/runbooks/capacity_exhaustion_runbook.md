# Capacity Exhaustion Runbook

## Scope

Response procedure when backup or alternate paths exceed their capacity during failover. Applies when primary path failures force traffic onto lower-capacity backup links.

## Detection Criteria

| Indicator | Value | Confidence |
|---|---|---|
| AlertType | CAPACITY_EXCEEDED | HIGH |
| UtilizationPct | > 90% on backup link | HIGH |
| PacketLossPct | > 5% on backup link (congestion-induced) | CORROBORATING |
| LatencyMs | > 100 ms on microwave link (congestion queueing) | CORROBORATING |

## Common Capacity Mismatch Scenarios

| Primary Link | Capacity | Backup Link | Capacity | Shortfall |
|---|---|---|---|---|
| SUBMARINE_40G | 40 Gbps | MICROWAVE_10G | 10 Gbps | 75% |
| DWDM_100G | 100 Gbps | MICROWAVE_10G | 10 Gbps | 90% |

## Immediate Actions

### Step 1: Confirm capacity situation

1. Query LinkTelemetry for the backup link — check UtilizationPct, LatencyMs, PacketLossPct.
2. Calculate the capacity gap: `(primary_capacity - backup_capacity) / primary_capacity * 100`.
3. Determine how much traffic is actually being attempted vs how much the backup can carry.

### Step 2: Enable QoS traffic prioritisation

Apply strict QoS classification to shed low-priority traffic:

| Priority | SLA Tier | Action | Bandwidth Allocation |
|---|---|---|---|
| 1 (highest) | PLATINUM | Guaranteed bandwidth | Up to 40% of backup capacity |
| 2 | GOLD | Priority queuing | Up to 30% of backup capacity |
| 3 | SILVER | Best-effort priority | Up to 20% of backup capacity |
| 4 (lowest) | STANDARD | Shed first | Remaining capacity |

### Step 3: Assess alternate routing options

1. Check if multi-hop reroute paths exist that avoid the capacity-constrained backup.
2. Multi-hop paths will have higher latency but may provide additional capacity.
3. Split traffic across multiple paths if possible — GOLD traffic via backup directly, STANDARD traffic via multi-hop.

### Step 4: Consider temporary capacity augmentation

- Emergency satellite uplink (for isolated sites like Perth)
- Carrier interconnect (negotiate temporary capacity with alternate carrier)
- Wavelength purchase on existing dark fibre (if available in the corridor)

## Microwave-Specific Considerations

MICROWAVE_10G links have additional constraints:
- **Atmospheric ducting:** Temperature inversions can reduce effective capacity to 6 Gbps or lower.
- **Latency:** Microwave links have inherently higher latency than fibre (typically 20–40 ms additional per hop).
- **Rain fade:** Heavy rain can cause signal degradation and further capacity reduction.
- Factor these environmental conditions into capacity planning.

## Escalation

| Condition | Action | Timeline |
|---|---|---|
| Backup at >90% utilization | Notify NOC Manager | Immediate |
| PLATINUM traffic impacted | Notify Customer Success (Defence liaison) | Within 10 minutes |
| No alternate paths available | Escalate to VP Operations | Within 30 minutes |
| Capacity shortfall > 50% | Initiate emergency capacity procurement | Within 1 hour |

## Cross-References

- See `submarine_cable_runbook.md` for the primary failure that caused the failover.
- See `traffic_engineering_reroute.md` for multi-path traffic splitting.
- See `customer_communication_template.md` for customer impact notification.
