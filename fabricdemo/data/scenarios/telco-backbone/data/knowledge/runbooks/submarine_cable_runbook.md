# Submarine Cable Failure Runbook

## Scope

Response procedure for submarine cable faults affecting the APAC backbone network. Applies to SUBMARINE_40G link types.

## Detection Criteria

| Indicator | Value | Confidence |
|---|---|---|
| OpticalPowerDbm | ≤ -30 dBm (typically -42 dBm for total loss of light) | HIGH |
| BitErrorRate | ≈ 1 (total failure) or > 1e-3 (severe degradation) | HIGH |
| AlertType | SUBMARINE_CABLE_FAULT | HIGH |
| BGP session drop on same corridor within 5 seconds of optical alert | CORROBORATING |

## Verification Steps

1. **Confirm loss of light.** Check LinkTelemetry for the submarine link — OpticalPowerDbm should be at or below -42 dBm with BER ≈ 1.
2. **Check BGP impact.** Verify whether the BGP session between the endpoint routers has dropped. If so, routing is affected.
3. **Verify failover.** Check if traffic has automatically failed over to the backup path (e.g., microwave). Look for LINK_FAILOVER alerts.
4. **Assess backup capacity.** If failover occurred, check if the backup path has sufficient capacity. A MICROWAVE_10G link cannot absorb 40 Gbps of submarine cable traffic — expect CAPACITY_EXCEEDED alerts.
5. **Rule out transient fault.** If OpticalPowerDbm is between -20 and -30 dBm (degraded but not dead), monitor for 5 minutes before declaring a full cable fault. Gradual degradation may indicate anchor drag rather than a clean cut.

## Immediate Actions

1. **Confirm traffic rerouting.** Verify that MPLS path failover has activated the SECONDARY path (microwave backup).
2. **Enable QoS prioritisation.** Given the capacity mismatch (40G demand on 10G backup), enable strict QoS:
   - PLATINUM traffic (government/defence): highest priority, guaranteed bandwidth
   - GOLD traffic (enterprise VPN): second priority
   - SILVER traffic (education, financial): best-effort priority
   - STANDARD traffic (residential broadband): shed first if necessary
3. **Request satellite backhaul.** For Perth isolation scenarios, initiate emergency satellite uplink procurement. Contact emergency satellite partner.
4. **Notify cable repair coordination.** Contact submarine cable operator to dispatch repair vessel. Typical repair time: 10–21 days.

## Multi-Hop Reroute Assessment

If the submarine cable corridor has no adequate direct backup:

1. Query alternate MPLS paths (TERTIARY type) that reach the same destination via intermediate cities.
2. Calculate cumulative capacity. The bottleneck is the lowest-capacity link on the alternate path.
3. Multi-hop paths (e.g., SYD → MEL → ADL → PER) add latency — each intermediate hop adds 2–5 ms.
4. Verify that intermediate links have spare capacity for the additional traffic.

## Escalation

| Condition | Action | Timeline |
|---|---|---|
| Loss of light confirmed | Notify NOC Manager | Immediate |
| Backup capacity insufficient | Escalate to Network Engineering | Within 15 minutes |
| PLATINUM SLA at risk | Notify Customer Success (Defence liaison) | Within 10 minutes |
| Perth isolation (no viable alternate) | Escalate to VP Operations | Within 30 minutes |
| Cable repair needed | Engage submarine cable operator | Within 1 hour |

## Cross-References

- See `capacity_exhaustion_runbook.md` for QoS prioritisation during backup overload.
- See `traffic_engineering_reroute.md` for MPLS path failover procedure.
- See `customer_communication_template.md` for PLATINUM/GOLD customer notification.
