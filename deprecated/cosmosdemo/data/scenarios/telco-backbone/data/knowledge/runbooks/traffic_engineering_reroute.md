# Traffic Engineering & MPLS Reroute Runbook

## Scope

Procedure for MPLS path failover, traffic splitting across alternate paths, and verification of rerouted traffic. Used when primary paths fail and traffic must be engineered onto backup or alternate routes.

## Pre-Reroute Checklist

Before initiating a reroute, verify:

1. **Alternate path exists.** Query the topology graph for SECONDARY or TERTIARY MPLS paths that serve the same corridor.
2. **Alternate path is healthy.** Check LinkTelemetry for the transport links on the alternate path — they should show normal OpticalPowerDbm, BER, and UtilizationPct.
3. **Sufficient capacity.** Compare the failed primary link's capacity (CapacityGbps) with the alternate path's capacity. If there is a capacity shortfall, follow `capacity_exhaustion_runbook.md` for QoS prioritisation.
4. **No concurrent failures on alternate path.** Check for any active alerts on the alternate path's links and routers. If the alternate path is also degraded, consider a multi-hop reroute instead.

## Reroute Procedure

### Automatic failover (MPLS FRR)
Most MPLS paths are configured with Fast Reroute (FRR). When the primary path fails:
1. Traffic automatically shifts to the SECONDARY path within 50 ms.
2. LINK_FAILOVER alert is generated.
3. Verify failover by checking that the SECONDARY path's links show increased UtilizationPct.

### Manual traffic engineering
If automatic failover is insufficient (e.g., SECONDARY path also down or capacity insufficient):
1. Identify TERTIARY paths via the topology graph.
2. Multi-hop TERTIARY paths route through intermediate cities— example: SYD → MEL → ADL → PER instead of ADL → PER directly.
3. Calculate cumulative latency: add 2–5 ms per intermediate hop.
4. Verify each link on the multi-hop path has spare capacity.

## Traffic Splitting

When a single alternate path lacks capacity:
1. Split traffic across multiple paths based on SLA tier.
2. Route PLATINUM/GOLD traffic via the lowest-latency available path.
3. Route SILVER/STANDARD traffic via multi-hop alternate paths (higher latency acceptable).
4. Apply per-service traffic engineering rules rather than link-level load balancing.

## Post-Reroute Verification

1. **Check service reachability.** Verify that affected services (VPNs, broadband, mobile) have restored connectivity.
2. **Monitor latency.** Multi-hop reroutes will have higher latency — confirm latency is within SLA thresholds.
3. **Monitor utilization.** Verify that alternate path utilization is within acceptable bounds (< 80%).
4. **Check for route oscillation.** Monitor for OSPF flaps or BGP route withdrawals/re-announcements. If routing is oscillating, dampen routes.
5. **Verify QoS is applied.** Confirm that traffic prioritisation reflects SLA tiers.

## Rollback Criteria

Rollback to the pre-reroute state when:
1. The failed primary path is restored and verified healthy.
2. OpticalPowerDbm returns to normal range (-8 to -12 dBm).
3. BER returns below 1e-9.
4. BGP session re-establishes and converges.
5. Allow 15-minute soak time with traffic on the restored path before removing the reroute.

## Multi-Hop Latency Reference

| Path | Hops | Estimated Latency | Notes |
|---|---|---|---|
| ADL → PER (submarine) | 3 | 6–10 ms | Normal primary path |
| ADL → PER (microwave) | 3 | 20–40 ms | Higher latency, low capacity |
| SYD → MEL → ADL → PER | 7 | 15–30 ms | Multi-hop, good capacity except ADL→PER leg |
| SYD → ADL → PER | 5 | 12–20 ms | Via inland fibre, bottleneck at ADL→PER |

## Escalation

| Condition | Action | Timeline |
|---|---|---|
| Reroute initiated | Inform NOC Manager | Immediate |
| Reroute failed (no viable alternate) | Escalate to Network Engineering | Within 10 minutes |
| Latency exceeds SLA thresholds post-reroute | Notify affected enterprise customers | Within 15 minutes |
| Route oscillation detected | Escalate to routing team | Within 10 minutes |

## Cross-References

- See `submarine_cable_runbook.md` for submarine cable failure context.
- See `capacity_exhaustion_runbook.md` for handling capacity shortfalls on backup paths.
- See `bgp_peer_loss_runbook.md` for BGP recovery verification.
