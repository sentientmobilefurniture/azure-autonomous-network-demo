# Runbook: Fibre Cut — Detection, Verification, and Recovery

## Summary
A fibre cut is a physical-layer failure on a DWDM or dark-fibre transport link, typically caused by third-party dig activity, severe weather, or equipment failure at an amplifier site. It results in total loss of light on the affected span and cascading failures across all logical resources routed over that fibre.

## Detection Criteria
| Indicator | Threshold | Source |
|---|---|---|
| Optical power | < −30 dBm (loss of light) | TransportLink entity — OpticalPowerDbm |
| Bit error rate | = 1.0 (total) | TransportLink entity — BitErrorRate |
| Link status | DOWN | LINK_DOWN alert in Eventhouse |
| BGP peer loss | Peer unreachable within 3s of link alarm | BGP_PEER_LOSS alert correlated by time |
| OSPF adjacency | Lost within 5s of link alarm | OSPF_ADJACENCY_DOWN alert |

## Verification Steps
1. **Confirm loss of light** — Query ontology for the TransportLink entity instance. Check time-series OpticalPowerDbm property. If < −30 dBm, loss of light is confirmed.
2. **Rule out transceiver failure** — Check if both ends report loss of light. Query both SourceRouterId and TargetRouterId CoreRouter entities for interface alarm status. If both ends are dark → fibre cut (not single-end transceiver failure).
3. **Check for maintenance window** — Query change management system. If a planned maintenance window is active on this link, this may be expected. Escalate to change coordinator.
4. **Confirm no loopback** — Verify the link is not in a loopback test configuration.

## Immediate Actions
1. **Suppress downstream alerts** — All alerts from nodes downstream of the cut link are symptoms, not independent faults. Suppress to reduce noise.
2. **Assess alternate path** — Query ontology for TransportLink entities between the same SourceRouterId and TargetRouterId. Check UtilizationPct time-series on alternate links.
3. **Initiate traffic reroute** — If alternate path utilisation < 80%, initiate MPLS path failover to secondary path. See: `traffic_engineering_reroute.md`.
4. **Raise P1 incident** — Create priority-1 incident with root cause, blast radius, and estimated SLA impact.

## Escalation
- **L1**: NOC operator verifies and initiates reroute (automated in autonomous mode)
- **L2**: Transport engineering team dispatched for physical repair
- **L3**: Vendor engagement if amplifier or ROADM failure suspected
- **External**: Field team dispatched to fibre route for physical inspection

## Expected Resolution Time
| Scenario | Typical MTTR |
|---|---|
| Reroute to alternate path (automated) | < 1 minute |
| Physical fibre repair (urban) | 4–8 hours |
| Physical fibre repair (rural) | 12–24 hours |
| Amplifier/ROADM replacement | 2–6 hours |

## Related Runbooks
- `bgp_peer_loss_runbook.md`
- `traffic_engineering_reroute.md`
- `alert_storm_triage_guide.md`
- `customer_communication_template.md`
