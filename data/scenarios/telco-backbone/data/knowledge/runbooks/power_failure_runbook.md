# Datacenter Power Failure Runbook

## Scope

Response procedure for datacenter power failures affecting network equipment. Covers UPS failures, generator failures, and power bus faults.

## Detection Criteria

| Indicator | Value | Confidence |
|---|---|---|
| AlertType | POWER_FAILURE on DataCenter or AggSwitch entity | HIGH |
| Multiple equipment in same datacenter going offline simultaneously | CORROBORATING |
| BMS (Building Management System) alarm | HIGH |

## Verification Steps

1. **Identify the datacenter.** Use the DataCenterId from the alert to determine which facility is affected.
2. **Check power redundancy tier.** Tier4/2N datacenters have redundant power buses — a single bus failure should not cause equipment outage. Tier3/N+1 datacenters are vulnerable to single power bus failures.
3. **Enumerate affected equipment.** Query the topology graph for all equipment housed in or located at the affected datacenter:
   - CoreRouters (via `housed_in` relationship)
   - FirewallClusters (via `located_at` relationship)
   - AggSwitches (check if the core router in that datacenter has downstream agg switches)
4. **Determine blast radius.** For each affected AggSwitch, check:
   - What base stations backhaul through it (via `backhauls_via`)
   - What services depend on it (via `depends_on`)
5. **Check if core router survived.** If the datacenter has 2N power, the core router may still be running on the surviving power bus. If N+1, the core router itself may be down.

## Immediate Actions

1. **Contact facility management.** Request UPS/generator status update. Determine expected repair time.
2. **Assess partial vs total failure.**
   - Partial: Some equipment down (e.g., one AggSwitch) while core router survives.
   - Total: Core router also offline — all downstream infrastructure isolated.
3. **For partial failure (AggSwitch down):**
   - Affected services: broadband and mobile subscribers on that switch.
   - No path rerouting needed — these are access-layer failures.
   - Notify affected residential and mobile customers.
4. **For total failure (CoreRouter down):**
   - All transit traffic through this datacenter is disrupted.
   - BGP sessions involving this router will drop.
   - MPLS paths traversing this router will fail.
   - Initiate full rerouting procedure (see `traffic_engineering_reroute.md`).

## Power Redundancy Reference

| Tier | Redundancy | Single Bus Failure | Expected Recovery |
|---|---|---|---|
| Tier4 / 2N | Fully redundant power | No equipment impact | Automatic failover |
| Tier3 / N+1 | One backup module | Equipment may be impacted | Manual intervention required |

## Compound Failure Considerations

If a power failure occurs simultaneously with another failure (e.g., submarine cable fault):
1. Assess whether the compound effect isolates any city or corridor.
2. The capacity impact of rerouting around one failure may be exacerbated by equipment lost to the power failure.
3. Example: submarine cable down + Adelaide power failure = Perth isolated with degraded Adelaide, no adequate reroute capacity.

## Escalation

| Condition | Action | Timeline |
|---|---|---|
| Power failure confirmed | Notify NOC Manager + Facilities | Immediate |
| Core router offline | Escalate to Network Engineering | Within 10 minutes |
| Compound failure detected | Escalate to VP Operations | Within 15 minutes |
| SLA breach imminent | Notify affected enterprise customers | Within 20 minutes |

## Cross-References

- See `submarine_cable_runbook.md` if concurrent with submarine cable fault.
- See `alert_storm_triage_guide.md` for compound failure correlation.
- See `customer_communication_template.md` for customer notification.
