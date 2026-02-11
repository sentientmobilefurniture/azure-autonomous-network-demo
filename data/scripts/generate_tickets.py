"""
Generate historical incident tickets as .txt files for AI Search.

Outputs:
  - data/tickets/{ticket_id}.txt  (10 individual ticket files)
"""

import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "tickets")


def generate_tickets() -> list[dict]:
    return [
        {
            "ticket_id": "INC-2025-08-14-0042",
            "title": "Fibre cut SYD-MEL corridor - contractor damage",
            "severity": "P1",
            "root_cause": "LINK-SYD-MEL-FIBRE-01",
            "root_cause_type": "FIBRE_CUT",
            "description": "Third-party contractor struck fibre conduit during road works on Hume Highway. Complete loss of light on LINK-SYD-MEL-FIBRE-01. 1,847 downstream alerts generated.",
            "detection_method": "Automated alert storm detection",
            "resolution": "Traffic rerouted to LINK-SYD-MEL-FIBRE-02 within 45 seconds. Physical repair completed in 6 hours by field team.",
            "customer_impact": ["VPN-ACME-CORP", "VPN-BIGBANK", "BB-BUNDLE-SYD-NORTH"],
            "services_affected": 3,
            "alerts_generated": 1847,
            "alerts_suppressed": 1846,
            "time_to_detect_seconds": 8,
            "time_to_reroute_seconds": 45,
            "time_to_resolve_minutes": 360,
            "sla_breached": False,
            "created_at": "2025-08-14T03:22:15Z",
            "resolved_at": "2025-08-14T09:22:15Z",
            "lessons_learned": "Alternate path FIBRE-02 had sufficient capacity (38% utilisation). Consider pre-provisioned automatic failover for enterprise VPN customers."
        },
        {
            "ticket_id": "INC-2025-09-02-0018",
            "title": "DWDM amplifier failure MEL-BNE link",
            "severity": "P1",
            "root_cause": "LINK-MEL-BNE-FIBRE-01",
            "root_cause_type": "AMPLIFIER_FAILURE",
            "description": "Erbium-doped fibre amplifier (EDFA) failure at Albury repeater site. Gradual signal degradation over 15 minutes before complete loss.",
            "detection_method": "Anomaly detection on optical power time-series",
            "resolution": "Spare EDFA module swapped by field team. Link restored after 4 hours.",
            "customer_impact": ["BB-BUNDLE-MEL-EAST"],
            "services_affected": 1,
            "alerts_generated": 423,
            "alerts_suppressed": 422,
            "time_to_detect_seconds": 120,
            "time_to_reroute_seconds": 90,
            "time_to_resolve_minutes": 240,
            "sla_breached": False,
            "created_at": "2025-09-02T11:45:00Z",
            "resolved_at": "2025-09-02T15:45:00Z",
            "lessons_learned": "Pre-positioned spare amplifier modules at major repeater sites. Optical power degradation trend was detectable 10 minutes before failure — consider proactive alerting."
        },
        {
            "ticket_id": "INC-2025-10-19-0007",
            "title": "BGP misconfiguration - route leak SYD-BNE",
            "severity": "P2",
            "root_cause": "CORE-BNE-01",
            "root_cause_type": "MISCONFIGURATION",
            "description": "Incorrect route-map applied during maintenance window caused BNE router to advertise internal prefixes to external peers. Traffic blackholed for 12 minutes.",
            "detection_method": "Route withdrawal anomaly detection",
            "resolution": "Route-map corrected, BGP sessions cleared. Traffic restored within 2 minutes of fix.",
            "customer_impact": [],
            "services_affected": 0,
            "alerts_generated": 156,
            "alerts_suppressed": 155,
            "time_to_detect_seconds": 180,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 14,
            "sla_breached": False,
            "created_at": "2025-10-19T22:15:00Z",
            "resolved_at": "2025-10-19T22:29:00Z",
            "lessons_learned": "Mandatory pre-change peer review for BGP route-map modifications. Implement automated config validation before commit."
        },
        {
            "ticket_id": "INC-2025-11-05-0031",
            "title": "Power outage AGG-SYD-NORTH-01 - UPS failure",
            "severity": "P1",
            "root_cause": "AGG-SYD-NORTH-01",
            "root_cause_type": "POWER_FAILURE",
            "description": "UPS battery failure at Sydney North aggregation site. Switch lost power for 8 minutes before generator kicked in. All downstream base stations lost backhaul.",
            "detection_method": "Automated alert storm detection — correlated with power monitoring",
            "resolution": "Generator provided interim power. UPS battery replaced within 2 hours. No lasting impact.",
            "customer_impact": ["BB-BUNDLE-SYD-NORTH", "MOB-5G-SYD-2041", "MOB-5G-SYD-2042"],
            "services_affected": 3,
            "alerts_generated": 892,
            "alerts_suppressed": 891,
            "time_to_detect_seconds": 5,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 8,
            "sla_breached": False,
            "created_at": "2025-11-05T06:12:00Z",
            "resolved_at": "2025-11-05T06:20:00Z",
            "lessons_learned": "UPS battery age exceeded manufacturer recommendation. Implement proactive UPS health monitoring. Add battery age to ontology as a property on AggSwitch entity."
        },
        {
            "ticket_id": "INC-2025-11-22-0055",
            "title": "Fibre cut SYD-MEL corridor - storm damage",
            "severity": "P1",
            "root_cause": "LINK-SYD-MEL-FIBRE-01",
            "root_cause_type": "FIBRE_CUT",
            "description": "Severe thunderstorm caused tree fall on aerial fibre section near Goulburn. Both FIBRE-01 and FIBRE-02 impacted (same conduit route). No alternate direct path available.",
            "detection_method": "Automated alert storm detection",
            "resolution": "Emergency traffic rerouted via SYD-BNE-MEL indirect path (higher latency). Physical repair took 18 hours due to access issues.",
            "customer_impact": ["VPN-ACME-CORP", "VPN-BIGBANK", "BB-BUNDLE-SYD-NORTH", "BB-BUNDLE-MEL-EAST"],
            "services_affected": 4,
            "alerts_generated": 3241,
            "alerts_suppressed": 3239,
            "time_to_detect_seconds": 6,
            "time_to_reroute_seconds": 180,
            "time_to_resolve_minutes": 1080,
            "sla_breached": True,
            "created_at": "2025-11-22T14:05:00Z",
            "resolved_at": "2025-11-23T08:05:00Z",
            "lessons_learned": "Both SYD-MEL fibre pairs share a common conduit for 12km near Goulburn. Diversely routed third path required for true redundancy. REDUNDANT_PAIR relationship in ontology should include route-diversity metadata."
        },
        {
            "ticket_id": "INC-2025-12-03-0012",
            "title": "Base station backhaul degradation GNB-MEL-3011",
            "severity": "P3",
            "root_cause": "GNB-MEL-3011",
            "root_cause_type": "HARDWARE_DEGRADATION",
            "description": "Ethernet interface on GNB-MEL-3011 showing increasing CRC errors. Packet loss reached 2.3% causing voice quality degradation for mobile users.",
            "detection_method": "Threshold-based alerting on PacketLossPct",
            "resolution": "SFP module replaced during next maintenance window. No emergency action required.",
            "customer_impact": ["MOB-5G-MEL-3011"],
            "services_affected": 1,
            "alerts_generated": 12,
            "alerts_suppressed": 0,
            "time_to_detect_seconds": 300,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 4320,
            "sla_breached": False,
            "created_at": "2025-12-03T09:30:00Z",
            "resolved_at": "2025-12-06T09:30:00Z",
            "lessons_learned": "Gradual hardware degradation is harder to detect than binary failures. Consider trend-based anomaly detection on interface error counters."
        },
        {
            "ticket_id": "INC-2026-01-08-0003",
            "title": "OSPF flap storm SYD core - software bug",
            "severity": "P2",
            "root_cause": "CORE-SYD-01",
            "root_cause_type": "SOFTWARE_BUG",
            "description": "Known IOS-XR bug caused OSPF adjacencies to flap every 30 seconds on CORE-SYD-01. Generated 500+ alerts per hour. BGP sessions remained stable.",
            "detection_method": "Alert rate anomaly — periodic pattern detected",
            "resolution": "Applied vendor hotfix SMU. OSPF stabilised within 5 minutes of patch.",
            "customer_impact": [],
            "services_affected": 0,
            "alerts_generated": 2100,
            "alerts_suppressed": 2099,
            "time_to_detect_seconds": 60,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 45,
            "sla_breached": False,
            "created_at": "2026-01-08T01:15:00Z",
            "resolved_at": "2026-01-08T02:00:00Z",
            "lessons_learned": "Maintain vendor bug tracker integration. Periodic alert patterns (fixed interval flapping) should be flagged as potential software bugs, not hardware failures."
        },
        {
            "ticket_id": "INC-2026-01-15-0021",
            "title": "Capacity exhaustion LINK-SYD-MEL-FIBRE-02",
            "severity": "P2",
            "root_cause": "LINK-SYD-MEL-FIBRE-02",
            "root_cause_type": "CAPACITY_EXHAUSTION",
            "description": "LINK-SYD-MEL-FIBRE-02 utilisation reached 95% during evening peak after FIBRE-01 was taken offline for scheduled maintenance. QoS started dropping lower-priority traffic.",
            "detection_method": "Threshold-based alerting on UtilizationPct",
            "resolution": "Maintenance window on FIBRE-01 shortened. Traffic restored to both links. Capacity planning initiated for 400G upgrade.",
            "customer_impact": ["BB-BUNDLE-SYD-NORTH"],
            "services_affected": 1,
            "alerts_generated": 34,
            "alerts_suppressed": 33,
            "time_to_detect_seconds": 15,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 120,
            "sla_breached": False,
            "created_at": "2026-01-15T18:30:00Z",
            "resolved_at": "2026-01-15T20:30:00Z",
            "lessons_learned": "Maintenance scheduling must account for remaining capacity on alternate paths. Add capacity-aware maintenance window validation to change management process."
        },
        {
            "ticket_id": "INC-2026-01-28-0009",
            "title": "DNS resolution failure impacting VPN-ACME-CORP",
            "severity": "P2",
            "root_cause": "VPN-ACME-CORP",
            "root_cause_type": "SERVICE_MISCONFIGURATION",
            "description": "Customer-side DNS configuration change caused internal name resolution to fail. VPN tunnel was up and healthy but customer reported complete service outage.",
            "detection_method": "Customer-reported — no network-side alerts generated",
            "resolution": "Customer corrected their DNS configuration. No network action required.",
            "customer_impact": ["VPN-ACME-CORP"],
            "services_affected": 1,
            "alerts_generated": 0,
            "alerts_suppressed": 0,
            "time_to_detect_seconds": 900,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 60,
            "sla_breached": False,
            "created_at": "2026-01-28T10:00:00Z",
            "resolved_at": "2026-01-28T11:00:00Z",
            "lessons_learned": "Customer-side issues produce no network alerts. Consider end-to-end service probes that test at the application layer, not just network layer."
        },
        {
            "ticket_id": "INC-2026-02-01-0015",
            "title": "Scheduled fibre maintenance SYD-BNE - extended window",
            "severity": "P3",
            "root_cause": "LINK-SYD-BNE-FIBRE-01",
            "root_cause_type": "PLANNED_MAINTENANCE",
            "description": "Planned fibre splice work on SYD-BNE corridor. Maintenance window extended by 2 hours due to additional splice points found during inspection.",
            "detection_method": "Change management system — planned event",
            "resolution": "Maintenance completed. Link restored and tested. No customer impact due to pre-arranged traffic rerouting.",
            "customer_impact": [],
            "services_affected": 0,
            "alerts_generated": 8,
            "alerts_suppressed": 8,
            "time_to_detect_seconds": 0,
            "time_to_reroute_seconds": 0,
            "time_to_resolve_minutes": 360,
            "sla_breached": False,
            "created_at": "2026-02-01T02:00:00Z",
            "resolved_at": "2026-02-01T08:00:00Z",
            "lessons_learned": "Build 50% buffer into fibre maintenance windows. Pre-stage traffic rerouting for all planned transport link outages."
        }
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
