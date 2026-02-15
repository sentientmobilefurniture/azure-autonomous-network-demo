# BGP Peer Loss Runbook

## Scope

Response procedure for BGP session drops between core routers. Covers transport-induced, router-induced, and peer-induced BGP failures.

## Detection Criteria

| Indicator | Value | Confidence |
|---|---|---|
| AlertType | BGP_PEER_LOSS | HIGH |
| Both peers reporting session down within seconds of each other | HIGH (transport cause) |
| Only one peer reporting | MODERATE (router or peer issue) |
| Concurrent SUBMARINE_CABLE_FAULT or FIBRE_CUT on same corridor | HIGH (transport cause confirmed) |

## Diagnostic Decision Tree

### Is the underlying transport link down?

1. Check if there is a concurrent SUBMARINE_CABLE_FAULT, FIBRE_CUT, or LINK_FAILOVER alert on the transport link connecting the two BGP peers.
2. If YES → the BGP loss is a **secondary symptom** of the transport failure. Focus remediation on the transport layer (see `submarine_cable_runbook.md`).
3. If NO → proceed to router-level diagnosis.

### Is the router healthy?

1. Check for POWER_FAILURE or HIGH_CPU alerts on both peer routers.
2. If one router has HIGH_CPU (> 90%) → BGP keepalive timers may have expired due to CPU exhaustion. This is a **convergence-induced** BGP flap — typically self-resolving once CPU stabilises.
3. If one router has POWER_FAILURE → the router is offline. All BGP sessions involving that router will be down.

### Is this a configuration issue?

1. If no transport or hardware explanation exists, check for recent maintenance or configuration changes.
2. Incorrect route-maps or prefix filters can cause BGP session teardowns.
3. Review change management records for the affected routers.

## Immediate Actions

1. **Determine the root cause category** using the decision tree above.
2. **If transport-induced:** Follow the appropriate transport runbook. BGP will recover automatically when the transport layer is restored.
3. **If router-induced:** 
   - HIGH_CPU: Monitor for self-recovery. If CPU doesn't drop below 85% within 10 minutes, restart BGP process.
   - POWER_FAILURE: Follow `power_failure_runbook.md`.
4. **Assess route withdrawal impact:** Check how many prefixes were withdrawn and what services rely on those routes. Use the topology graph to trace Service → MPLSPath → TransportLink → CoreRouter to identify all affected services.
5. **Verify alternate routing:** Confirm that traffic is being rerouted via alternate paths (SECONDARY or TERTIARY MPLS paths, or via other BGP sessions on different corridors).

## BGP Recovery Verification

After the root cause is resolved:
1. Confirm BGP session state returns to ESTABLISHED.
2. Verify that all previously withdrawn prefixes are re-announced.
3. Check that convergence is complete — no ongoing OSPF flaps or route oscillation.
4. Monitor for 15 minutes to ensure stability.

## Escalation

| Condition | Action | Timeline |
|---|---|---|
| BGP session down | Notify NOC on-call | Immediate |
| Multiple BGP sessions down | Escalate to Network Engineering | Within 10 minutes |
| Route withdrawals affecting PLATINUM services | Notify Defence liaison | Within 10 minutes |
| No recovery after 15 minutes | Escalate to vendor support | Within 30 minutes |

## Cross-References

- See `submarine_cable_runbook.md` if BGP loss is transport-induced.
- See `power_failure_runbook.md` if BGP loss is due to router power failure.
- See `alert_storm_triage_guide.md` for correlating BGP alerts with other failure indicators.
