"""
Generate historical incident tickets as .txt files for AI Search.

Outputs:
  - data/knowledge/tickets/{ticket_id}.txt  (12 individual ticket files)
"""

import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge", "tickets")


def generate_tickets() -> list[dict]:
    return [
        {
            "ticket_id": "INC-2025-06-18-0033",
            "title": "Submarine cable partial degradation ADL-PER — anchor drag",
            "severity": "P1",
            "root_cause": "LINK-ADL-PER-SUBMARINE-01",
            "root_cause_type": "SUBMARINE_CABLE_DAMAGE",
            "description": "Fishing trawler anchor drag on the Great Australian Bight submarine cable caused partial fibre strand damage. Signal degradation over 2 hours before automatic failover to microwave backup.",
            "detection_method": "Anomaly detection on optical power time-series — gradual decay pattern",
            "resolution": "Traffic rerouted to LINK-ADL-PER-MICROWAVE-01 (10G backup). Cable repair vessel dispatched — full repair in 14 days.",
            "customer_impact": ["VPN-IRONORE-CORP", "VPN-WESTGAS-CORP", "BB-BUNDLE-PER-CENTRAL"],
            "services_affected": 3,
            "alerts_generated": 1245,
            "alerts_suppressed": 1243,
            "time_to_detect_seconds": 180,
            "time_to_reroute_seconds": 120,
            "time_to_resolve_minutes": 20160,
            "sla_breached": True,
            "created_at": "2025-06-18T05:42:00Z",
            "resolved_at": "2025-07-02T05:42:00Z",
            "lessons_learned": "Microwave backup (10G) insufficient for full submarine cable load (40G). Perth services were degraded for 14 days during cable repair. Need to establish emergency satellite backhaul or negotiate lit fibre from alternate carrier."
        },
        {
            "ticket_id": "INC-2025-07-22-0011",
            "title": "Power surge DC-MEL-01 — lightning strike",
            "severity": "P2",
            "root_cause": "DC-MEL-01",
            "root_cause_type": "POWER_SURGE",
            "description": "Lightning strike on power distribution equipment at DC-MEL-01. UPS absorbed the surge but triggered a protective shutdown of one power bus. AGG-MEL-WEST-01 lost power for 4 minutes.",
            "detection_method": "BMS (Building Management System) alarm integration",
            "resolution": "UPS reset after surge protection verification. AGG-MEL-WEST-01 recovered automatically. Surge arresters replaced.",
            "customer_impact": ["BB-BUNDLE-MEL-EAST"],
            "services_affected": 1,
            "alerts_generated": 567,
            "alerts_suppressed": 566,
            "time_to_detect_seconds": 3,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 4,
            "sla_breached": False,
            "created_at": "2025-07-22T14:18:00Z",
            "resolved_at": "2025-07-22T14:22:00Z",
            "lessons_learned": "Tier 4 2N power redundancy at DC-MEL-01 prevented customer impact. Adelaide DC (Tier 3, N+1) would not have survived the same event. Recommend upgrading DC-ADL-01 surge protection."
        },
        {
            "ticket_id": "INC-2025-08-09-0027",
            "title": "BGP route leak SYD-CBR — maintenance error",
            "severity": "P2",
            "root_cause": "CORE-CBR-01",
            "root_cause_type": "MISCONFIGURATION",
            "description": "During scheduled maintenance, incorrect route-map applied to CORE-CBR-01 leaked internal government network prefixes to public peering. Defence VPN traffic briefly routed through public internet.",
            "detection_method": "Route monitoring system detected unexpected prefix announcements",
            "resolution": "Route-map corrected within 8 minutes. BGP sessions cleared. Full audit of government prefix filters completed.",
            "customer_impact": ["VPN-GOVDEFENCE"],
            "services_affected": 1,
            "alerts_generated": 89,
            "alerts_suppressed": 88,
            "time_to_detect_seconds": 45,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 8,
            "sla_breached": False,
            "created_at": "2025-08-09T22:30:00Z",
            "resolved_at": "2025-08-09T22:38:00Z",
            "lessons_learned": "Government VPN route-maps require mandatory two-person review and pre-deployment simulation. Incident triggered security audit. Implement automated BGP prefix validation before commit."
        },
        {
            "ticket_id": "INC-2025-09-15-0044",
            "title": "Microwave link degradation ADL-PER — atmospheric ducting",
            "severity": "P3",
            "root_cause": "LINK-ADL-PER-MICROWAVE-01",
            "root_cause_type": "ATMOSPHERIC_INTERFERENCE",
            "description": "Temperature inversion caused atmospheric ducting on the ADL-PER microwave link. Signal-to-noise ratio dropped, causing intermittent packet loss of 3-8% over 6 hours. Subsided naturally as weather changed.",
            "detection_method": "Threshold-based alerting on PacketLossPct",
            "resolution": "No action required — atmospheric ducting resolved naturally. Adaptive modulation on microwave reduced throughput to 6G during event.",
            "customer_impact": [],
            "services_affected": 0,
            "alerts_generated": 34,
            "alerts_suppressed": 0,
            "time_to_detect_seconds": 600,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 360,
            "sla_breached": False,
            "created_at": "2025-09-15T08:00:00Z",
            "resolved_at": "2025-09-15T14:00:00Z",
            "lessons_learned": "Microwave link capacity drops significantly during atmospheric events. Current 10G rated capacity may reduce to 6G or lower. Factor this into capacity planning for submarine cable failure scenarios."
        },
        {
            "ticket_id": "INC-2025-10-03-0019",
            "title": "Firewall cluster failover FW-PER-01 — firmware bug",
            "severity": "P2",
            "root_cause": "FW-PER-01",
            "root_cause_type": "SOFTWARE_BUG",
            "description": "Known Fortinet firmware bug caused FW-PER-01 active node to crash during deep packet inspection of encrypted traffic. Passive node took over but with 45-second gap in stateful inspection.",
            "detection_method": "Firewall health monitoring — heartbeat timeout",
            "resolution": "Emergency firmware patch applied (hotfix from vendor). Active/passive roles rebalanced.",
            "customer_impact": ["VPN-IRONORE-CORP", "VPN-WESTGAS-CORP"],
            "services_affected": 2,
            "alerts_generated": 156,
            "alerts_suppressed": 155,
            "time_to_detect_seconds": 10,
            "time_to_reroute_seconds": 45,
            "time_to_resolve_minutes": 90,
            "sla_breached": False,
            "created_at": "2025-10-03T11:20:00Z",
            "resolved_at": "2025-10-03T12:50:00Z",
            "lessons_learned": "Perth firewall is a single cluster — no geographic redundancy. Consider deploying secondary inspection path via Adelaide firewall for critical mining and energy VPN traffic."
        },
        {
            "ticket_id": "INC-2025-10-28-0052",
            "title": "Capacity exhaustion LINK-MEL-ADL-FIBRE-01 — traffic surge",
            "severity": "P2",
            "root_cause": "LINK-MEL-ADL-FIBRE-01",
            "root_cause_type": "CAPACITY_EXHAUSTION",
            "description": "University exam results release drove massive traffic surge from Adelaide campuses. LINK-MEL-ADL-FIBRE-01 hit 92% utilisation. QoS deprioritized residential broadband.",
            "detection_method": "Threshold-based alerting on UtilizationPct",
            "resolution": "Traffic engineering applied — shifted some Adelaide-bound traffic via SYD-ADL inland route. Peak subsided after 3 hours.",
            "customer_impact": ["BB-BUNDLE-ADL-SOUTH"],
            "services_affected": 1,
            "alerts_generated": 28,
            "alerts_suppressed": 27,
            "time_to_detect_seconds": 30,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 180,
            "sla_breached": False,
            "created_at": "2025-10-28T09:00:00Z",
            "resolved_at": "2025-10-28T12:00:00Z",
            "lessons_learned": "SYD-ADL inland route provides useful overflow capacity for MEL-ADL corridor. Consider pre-configured traffic engineering policies for known high-traffic events."
        },
        {
            "ticket_id": "INC-2025-11-14-0008",
            "title": "OSPF flap storm CORE-ADL-01 — interface CRC errors",
            "severity": "P2",
            "root_cause": "CORE-ADL-01",
            "root_cause_type": "HARDWARE_DEGRADATION",
            "description": "Degrading SFP on CORE-ADL-01 Gi0/0/0/2 interface caused intermittent CRC errors, triggering OSPF adjacency flaps every 90 seconds. Generated 800+ alerts per hour.",
            "detection_method": "Alert rate anomaly — periodic pattern detected",
            "resolution": "SFP module replaced during emergency maintenance window. OSPF stabilised immediately.",
            "customer_impact": [],
            "services_affected": 0,
            "alerts_generated": 2400,
            "alerts_suppressed": 2399,
            "time_to_detect_seconds": 120,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 45,
            "sla_breached": False,
            "created_at": "2025-11-14T03:15:00Z",
            "resolved_at": "2025-11-14T04:00:00Z",
            "lessons_learned": "CORE-ADL-01 is a critical convergence point for both east coast and Perth traffic. Hardware degradation at this node has outsized impact. Implement proactive SFP monitoring with optical power trend analysis."
        },
        {
            "ticket_id": "INC-2025-12-01-0036",
            "title": "Base station GNB-PER-6011 hardware failure — radio unit",
            "severity": "P3",
            "root_cause": "GNB-PER-6011",
            "root_cause_type": "HARDWARE_FAILURE",
            "description": "Radio unit failure on GNB-PER-6011 reduced cell capacity by 60%. Mobile subscribers experienced dropped calls and slow data. Replacement scheduled for next maintenance window.",
            "detection_method": "Threshold-based alerting on cell throughput metrics",
            "resolution": "Radio unit replaced during scheduled maintenance. Full capacity restored.",
            "customer_impact": ["MOB-5G-PER-6011"],
            "services_affected": 1,
            "alerts_generated": 18,
            "alerts_suppressed": 0,
            "time_to_detect_seconds": 300,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 2880,
            "sla_breached": False,
            "created_at": "2025-12-01T07:30:00Z",
            "resolved_at": "2025-12-03T07:30:00Z",
            "lessons_learned": "Perth has only 2 base stations — single station failure affects 50% of mobile coverage. Consider adding a third GNB in Perth metro area."
        },
        {
            "ticket_id": "INC-2025-12-20-0014",
            "title": "Defence VPN latency breach — SYD-CBR path congestion",
            "severity": "P1",
            "root_cause": "LINK-SYD-CBR-FIBRE-01",
            "root_cause_type": "CAPACITY_CONGESTION",
            "description": "Holiday traffic surge combined with Defence data transfer saturated LINK-SYD-CBR-FIBRE-01. VPN-GOVDEFENCE latency exceeded PLATINUM SLA threshold (10ms) for 22 minutes.",
            "detection_method": "Real-time SLA monitoring — latency threshold breach",
            "resolution": "Traffic engineering prioritized Defence traffic via QoS reclassification. Capacity upgrade planned for Q1 2026.",
            "customer_impact": ["VPN-GOVDEFENCE"],
            "services_affected": 1,
            "alerts_generated": 67,
            "alerts_suppressed": 66,
            "time_to_detect_seconds": 15,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 22,
            "sla_breached": True,
            "created_at": "2025-12-20T16:45:00Z",
            "resolved_at": "2025-12-20T17:07:00Z",
            "lessons_learned": "PLATINUM SLA (99.999%, 10ms) requires dedicated bandwidth reservation, not just QoS priority. The SYD-CBR corridor needs a dedicated wavelength for government traffic."
        },
        {
            "ticket_id": "INC-2026-01-10-0005",
            "title": "Compound failure drill — simulated submarine cable + power loss",
            "severity": "P2",
            "root_cause": "LINK-ADL-PER-SUBMARINE-01",
            "root_cause_type": "PLANNED_DRILL",
            "description": "Planned disaster recovery drill simulating simultaneous submarine cable failure and Adelaide datacenter power loss. Drill exposed that microwave backup cannot sustain Perth traffic and that no automated failover path exists to bypass Adelaide.",
            "detection_method": "Planned event — change management system",
            "resolution": "Drill completed. Findings documented: (1) microwave backup insufficient, (2) no automated SYD→PER bypass, (3) Adelaide N+1 power is a single point of failure.",
            "customer_impact": [],
            "services_affected": 0,
            "alerts_generated": 0,
            "alerts_suppressed": 0,
            "time_to_detect_seconds": 0,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 240,
            "sla_breached": False,
            "created_at": "2026-01-10T02:00:00Z",
            "resolved_at": "2026-01-10T06:00:00Z",
            "lessons_learned": "CRITICAL FINDING: Compound failure of ADL-PER submarine cable + DC-ADL-01 power would isolate Perth with no adequate backup. Microwave at 10G cannot absorb 40G demand. Recommend: (1) emergency satellite uplink for Perth, (2) upgrade DC-ADL-01 to 2N power, (3) pre-provision traffic engineering for SYD→MEL→ADL→PER via microwave with strict QoS."
        },
        {
            "ticket_id": "INC-2026-02-05-0021",
            "title": "Fibre splice degradation LINK-SYD-ADL-FIBRE-01 — corrosion",
            "severity": "P3",
            "root_cause": "LINK-SYD-ADL-FIBRE-01",
            "root_cause_type": "HARDWARE_DEGRADATION",
            "description": "Gradual optical power degradation on the inland SYD-ADL fibre due to splice corrosion at Broken Hill junction point. Optical power dropped from -3dBm to -18dBm over 3 weeks.",
            "detection_method": "Trend analysis on OpticalPowerDbm time-series",
            "resolution": "Field team dispatched to Broken Hill junction. Corroded splice replaced. Optical power restored to normal.",
            "customer_impact": [],
            "services_affected": 0,
            "alerts_generated": 8,
            "alerts_suppressed": 0,
            "time_to_detect_seconds": 86400,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 1440,
            "sla_breached": False,
            "created_at": "2026-02-05T10:00:00Z",
            "resolved_at": "2026-02-06T10:00:00Z",
            "lessons_learned": "SYD-ADL inland fibre is the last-resort alternate path for Perth-bound traffic. Its degradation wasn't detected for 3 weeks because it's a low-utilisation standby link. Must add proactive optical power monitoring on ALL links, not just high-utilisation ones."
        },
        {
            "ticket_id": "INC-2026-02-28-0017",
            "title": "Scheduled maintenance LINK-MEL-ADL-FIBRE-01 — splice work",
            "severity": "P3",
            "root_cause": "LINK-MEL-ADL-FIBRE-01",
            "root_cause_type": "PLANNED_MAINTENANCE",
            "description": "Planned fibre splice work on MEL-ADL corridor. Traffic pre-arranged to reroute via SYD-ADL inland path. Maintenance window extended by 1 hour due to additional splice points.",
            "detection_method": "Change management system — planned event",
            "resolution": "Maintenance completed. Link restored and tested.",
            "customer_impact": [],
            "services_affected": 0,
            "alerts_generated": 12,
            "alerts_suppressed": 12,
            "time_to_detect_seconds": 0,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 300,
            "sla_breached": False,
            "created_at": "2026-02-28T02:00:00Z",
            "resolved_at": "2026-02-28T07:00:00Z",
            "lessons_learned": "Pre-staged traffic rerouting worked well. Build 50% buffer into fibre maintenance windows. During maintenance, submarine cable is the sole Perth path — avoid concurrent maintenance."
        },
    ]


def _format_ticket(t: dict) -> str:
    """Format a ticket dict as human-readable .txt matching indexer expectations."""
    lines = [
        f"Incident: {t['ticket_id']}",
        f"Title: {t['title']}",
        f"Severity: {t['severity']}",
        f"Root Cause: {t['root_cause']}",
        f"Root Cause Type: {t['root_cause_type']}",
        f"Created: {t['created_at']}",
        f"Resolved: {t['resolved_at']}",
        f"SLA Breached: {'Yes' if t['sla_breached'] else 'No'}",
        "",
        "Description:",
        t["description"],
        "",
        "Detection Method:",
        t["detection_method"],
        "",
        "Resolution:",
        t["resolution"],
        "",
    ]
    lines.append("Customer Impact:")
    if t["customer_impact"]:
        for c in t["customer_impact"]:
            lines.append(f"- {c}")
    else:
        lines.append("(None)")
    lines.append("")
    lines.append(f"Services Affected: {t['services_affected']}")
    lines.append(f"Alerts Generated: {t['alerts_generated']}")
    lines.append(f"Alerts Suppressed: {t['alerts_suppressed']}")
    lines.append(f"Time to Detect: {t['time_to_detect_seconds']} seconds")
    lines.append(f"Time to Reroute: {t['time_to_reroute_seconds']} seconds")
    lines.append(f"Time to Resolve: {t['time_to_resolve_minutes']} minutes")
    lines.append("")
    lines.append("Lessons Learned:")
    lines.append(t["lessons_learned"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tickets = generate_tickets()
    for t in tickets:
        path = os.path.join(OUTPUT_DIR, f"{t['ticket_id']}.txt")
        with open(path, "w") as f:
            f.write(_format_ticket(t))
        print(f"  ✓ {t['ticket_id']}.txt")
    print(f"\n{len(tickets)} ticket files written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
