# Ticket Format

## Ticket `.txt` Format

Historical incident tickets are indexed into Azure AI Search for RAG retrieval.
Each ticket is a `.txt` file with structured fields that the search indexer
parses. The AI agent uses these during investigation to find precedent incidents.

### File Naming

```
{TICKET_ID}.txt
```

Example: `INC-2025-08-14-0042.txt`

Ticket IDs: `INC-{YYYY}-{MM}-{DD}-{NNNN}`

### Required Fields

```
Incident: INC-2025-08-14-0042
Title: Fibre cut SYD-MEL corridor - contractor damage
Severity: P1
Root Cause: LINK-SYD-MEL-FIBRE-01
Root Cause Type: FIBRE_CUT
Created: 2025-08-14T03:22:15Z
Resolved: 2025-08-14T09:22:15Z
SLA Breached: No

Description:
Third-party contractor struck fibre conduit during road works on Hume Highway.
Complete loss of light on LINK-SYD-MEL-FIBRE-01. 1,847 downstream alerts generated.

Detection Method:
Automated alert storm detection

Resolution:
Traffic rerouted to LINK-SYD-MEL-FIBRE-02 within 45 seconds. Physical repair
completed in 6 hours by field team.

Customer Impact:
- VPN-ACME-CORP
- VPN-BIGBANK
- BB-BUNDLE-SYD-NORTH

Services Affected: 3
Alerts Generated: 1847
Alerts Suppressed: 1846
Time to Detect: 8 seconds
Time to Reroute: 45 seconds
Time to Resolve: 360 minutes

Lessons Learned:
Alternate path FIBRE-02 had sufficient capacity (38% utilisation). Consider
pre-provisioned automatic failover for enterprise VPN customers.
```

### Generation Pattern

```python
"""
Generate historical incident tickets as .txt files for AI Search.
Outputs: data/knowledge/tickets/{ticket_id}.txt (8-12 files)
"""
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge", "tickets")


def generate_tickets() -> list[dict]:
    return [
        {
            "ticket_id": "INC-2025-08-14-0042",
            "title": "Fibre cut SYD-MEL corridor - contractor damage",
            "severity": "P1",
            "root_cause": "LINK-SYD-MEL-FIBRE-01",     # ← Must match entity ID
            "root_cause_type": "FIBRE_CUT",
            "description": "...",
            "detection_method": "Automated alert storm detection",
            "resolution": "...",
            "customer_impact": ["VPN-ACME-CORP", "VPN-BIGBANK"],  # ← Must match entity IDs
            "services_affected": 2,
            "alerts_generated": 1847,
            "alerts_suppressed": 1846,
            "time_to_detect_seconds": 8,
            "time_to_reroute_seconds": 45,
            "time_to_resolve_minutes": 360,
            "sla_breached": False,
            "created_at": "2025-08-14T03:22:15Z",
            "resolved_at": "2025-08-14T09:22:15Z",
            "lessons_learned": "..."
        },
        # ... 8-12 total tickets
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
```

### Entity ID Cross-References

Every ticket must reference real entity IDs:

| Field | References |
|-------|-----------|
| `root_cause` | A vertex ID from any `Dim*.csv` |
| `customer_impact` | Service IDs from `DimService.csv` (or equivalent) |
| `root_cause_type` | Should align with `AlertType` values in AlertStream.csv |

### Ticket Diversity Guidelines

Cover a variety of root cause types across 8–12 tickets:

| Category | Telco examples | Cloud examples | E-commerce examples |
|----------|---------------|----------------|---------------------|
| Physical failure | `FIBRE_CUT`, `AMPLIFIER_FAILURE` | `DISK_FAILURE`, `NIC_FAILURE` | — |
| Hardware degradation | `HARDWARE_DEGRADATION` | `MEMORY_ECC_ERROR` | — |
| Software bug | `SOFTWARE_BUG` | `KERNEL_PANIC`, `OOM_KILL` | `MODEL_BUG`, `CACHE_CORRUPTION` |
| Misconfiguration | `MISCONFIGURATION` | `SECURITY_GROUP_MISCONFIGURATION` | `SEGMENT_MISCONFIGURATION` |
| Capacity | `CAPACITY_EXHAUSTION` | `CPU_THROTTLE`, `DISK_FULL` | `INVENTORY_OVERSELL` |
| External | `POWER_FAILURE` | `COOLING_FAILURE`, `POWER_FAILURE` | `SUPPLIER_DELIVERY_FAILURE` |
| Planned | `PLANNED_MAINTENANCE` | `ROLLING_UPDATE` | `MODEL_RETRAIN` |
| Customer-side | `SERVICE_MISCONFIGURATION` | `DNS_MISCONFIGURATION` | `CAMPAIGN_MISMATCH` |

### Lessons Learned

Each ticket's `lessons_learned` field should:
1. Reference specific entity IDs or entity types from the topology
2. Suggest improvements (monitoring, redundancy, process)
3. Occasionally suggest ontology changes ("add X property to Y entity")

These lessons are surfaced by the ticket agent during investigation, providing
the AI with historical context for similar incidents.
