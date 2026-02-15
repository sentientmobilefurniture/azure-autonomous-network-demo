"""
Generate historical incident tickets for the cloud-outage scenario.

Outputs 10 .txt files to data/knowledge/tickets/, covering diverse
root cause types across cloud infrastructure.
"""

import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge", "tickets")

TICKETS = [
    {
        "id": "INC-2025-06-12-0008",
        "title": "Cooling unit failure AZ-US-EAST-A — 3 hosts thermal shutdown",
        "severity": "P1",
        "root_cause": "AZ-US-EAST-A",
        "root_cause_type": "COOLING_FAILURE",
        "created": "2025-06-12T02:15:30Z",
        "resolved": "2025-06-12T06:45:30Z",
        "sla_breached": "No",
        "description": "CRAC Unit A1 compressor failure caused ambient temperature to exceed 45°C in AZ-US-EAST-A. Three hosts triggered thermal protection shutdown. 847 downstream alerts generated.",
        "detection": "Automated thermal threshold alert",
        "resolution": "Emergency portable cooling deployed within 40 minutes. Failed compressor replaced. Hosts powered back on after cool-down period. VMs live-migrated to AZ-B during outage.",
        "customer_impact": ["SVC-ECOMMERCE-WEB", "SVC-ECOMMERCE-API", "SVC-ECOMMERCE-DB"],
        "services_affected": 6,
        "alerts_gen": 847,
        "alerts_sup": 846,
        "ttd": 12,
        "ttr": "270 minutes",
        "lessons": "Install secondary CRAC units with automatic failover. Add pre-emptive thermal trend alerts at 32°C (current threshold is 35°C). Pre-stage portable cooling units at each facility.",
    },
    {
        "id": "INC-2025-07-03-0015",
        "title": "NIC firmware bug on HPE hosts — intermittent packet loss",
        "severity": "P2",
        "root_cause": "HOST-USE-A-02-01",
        "root_cause_type": "NIC_FIRMWARE_BUG",
        "created": "2025-07-03T14:22:00Z",
        "resolved": "2025-07-03T18:10:00Z",
        "sla_breached": "No",
        "description": "NIC firmware v2.8.3 on HPE hosts introduced a race condition causing 2-5% packet loss under sustained TCP connections above 10Gbps. Affected 2 database hosts.",
        "detection": "Automated error rate monitoring",
        "resolution": "Rolled back NIC firmware to v2.8.1. Scheduled maintenance window for firmware v2.8.4 (patched).",
        "customer_impact": ["SVC-ECOMMERCE-DB"],
        "services_affected": 1,
        "alerts_gen": 234,
        "alerts_sup": 220,
        "ttd": 45,
        "ttr": "228 minutes",
        "lessons": "Add NIC firmware version tracking to Host entity properties. Create canary deployment process for firmware updates — test on non-production hosts first.",
    },
    {
        "id": "INC-2025-07-28-0022",
        "title": "OOM kill cascade on cache nodes — Redis cluster partition",
        "severity": "P1",
        "root_cause": "VM-USE-A-0202-01",
        "root_cause_type": "OOM_KILL",
        "created": "2025-07-28T09:05:15Z",
        "resolved": "2025-07-28T10:30:15Z",
        "sla_breached": "No",
        "description": "Memory leak in Redis 7.2.1 caused OOM kills on cache-node-1 and cache-node-2. Without cache, database query volume spiked 12x, degrading all API responses.",
        "detection": "Automated OOM alert from kernel",
        "resolution": "Restarted Redis processes with memory limit enforcement. Upgraded to Redis 7.2.3 (memory leak fix) during next maintenance window.",
        "customer_impact": ["SVC-CACHE-CLUSTER", "SVC-ECOMMERCE-API", "SVC-ECOMMERCE-WEB"],
        "services_affected": 3,
        "alerts_gen": 1523,
        "alerts_sup": 1500,
        "ttd": 5,
        "ttr": "85 minutes",
        "lessons": "Add memory utilization trend monitoring with 24h projection. Implement circuit breaker pattern between API and cache to gracefully degrade without cascading to DB.",
    },
    {
        "id": "INC-2025-08-15-0031",
        "title": "Security group misconfiguration — payment service isolated",
        "severity": "P1",
        "root_cause": "SVC-PAYMENT",
        "root_cause_type": "SECURITY_GROUP_MISCONFIGURATION",
        "created": "2025-08-15T16:42:00Z",
        "resolved": "2025-08-15T17:15:00Z",
        "sla_breached": "Yes",
        "description": "Infrastructure-as-code change accidentally restricted inbound rules on the payment service security group. All payment processing halted for 33 minutes.",
        "detection": "Customer complaint and automated health check failure",
        "resolution": "Reverted security group rules to previous known-good state. Added pre-deploy validation for security group changes.",
        "customer_impact": ["SVC-PAYMENT", "SVC-ECOMMERCE-API"],
        "services_affected": 2,
        "alerts_gen": 89,
        "alerts_sup": 50,
        "ttd": 180,
        "ttr": "33 minutes",
        "lessons": "Implement security group change validation in CI/CD pipeline. Add synthetic transaction monitoring for payment flow (not just health checks).",
    },
    {
        "id": "INC-2025-09-02-0005",
        "title": "Disk full on monitoring VM — observability blackout",
        "severity": "P2",
        "root_cause": "VM-USE-A-0301-01",
        "root_cause_type": "DISK_FULL",
        "created": "2025-09-02T08:30:00Z",
        "resolved": "2025-09-02T09:45:00Z",
        "sla_breached": "No",
        "description": "Log volume spike from a noisy deployment filled the monitoring VM disk. Metrics ingestion stopped, creating a 75-minute observability blind spot.",
        "detection": "Manual discovery — team noticed missing dashboards",
        "resolution": "Cleared old log files, expanded disk, implemented log rotation with max file size limits.",
        "customer_impact": ["SVC-MONITORING"],
        "services_affected": 1,
        "alerts_gen": 3,
        "alerts_sup": 0,
        "ttd": 2700,
        "ttr": "75 minutes",
        "lessons": "The monitoring system must monitor itself. Add disk usage alerts for observability infrastructure. Implement aggressive log rotation defaults.",
    },
    {
        "id": "INC-2025-09-20-0019",
        "title": "Kernel panic on Dell hosts after security patch — rolling restart",
        "severity": "P2",
        "root_cause": "HOST-USE-A-01-01",
        "root_cause_type": "KERNEL_PANIC",
        "created": "2025-09-20T22:15:00Z",
        "resolved": "2025-09-21T01:30:00Z",
        "sla_breached": "No",
        "description": "Kernel 5.15.0-87 security patch caused panic on boot for Dell PowerEdge hosts with specific BIOS version. 3 hosts failed to restart after planned maintenance.",
        "detection": "Automated host health check — no heartbeat after reboot window",
        "resolution": "Booted affected hosts from rescue image, rolled back kernel to 5.15.0-86. Blacklisted BIOS+kernel combination in deployment matrix.",
        "customer_impact": ["SVC-ECOMMERCE-WEB", "SVC-ECOMMERCE-API"],
        "services_affected": 2,
        "alerts_gen": 456,
        "alerts_sup": 440,
        "ttd": 15,
        "ttr": "195 minutes",
        "lessons": "Add BIOS version to Host entity properties for compatibility matrix. Test kernel patches on representative hardware profiles before fleet-wide rollout.",
    },
    {
        "id": "INC-2025-10-08-0027",
        "title": "DNS misconfiguration — CDN cache miss storm",
        "severity": "P2",
        "root_cause": "SVC-CDN",
        "root_cause_type": "DNS_MISCONFIGURATION",
        "created": "2025-10-08T11:00:00Z",
        "resolved": "2025-10-08T12:20:00Z",
        "sla_breached": "No",
        "description": "DNS TTL set to 0 during migration caused all CDN caches to miss, directing 100% of traffic to origin. Origin servers saturated at 5x normal load.",
        "detection": "Automated latency alert — P99 exceeded 2000ms",
        "resolution": "Corrected DNS TTL to 3600s. CDN caches repopulated within 30 minutes.",
        "customer_impact": ["SVC-CDN", "SVC-ECOMMERCE-WEB"],
        "services_affected": 2,
        "alerts_gen": 312,
        "alerts_sup": 280,
        "ttd": 30,
        "ttr": "80 minutes",
        "lessons": "Add DNS TTL validation to deployment pipeline. Monitor CDN cache hit ratio as a leading indicator.",
    },
    {
        "id": "INC-2025-11-14-0033",
        "title": "PDU overload RACK-US-EAST-A-02 — partial power loss",
        "severity": "P1",
        "root_cause": "RACK-US-EAST-A-02",
        "root_cause_type": "POWER_OVERLOAD",
        "created": "2025-11-14T03:15:00Z",
        "resolved": "2025-11-14T05:00:00Z",
        "sla_breached": "No",
        "description": "Adding 2 GPU servers to RACK-US-EAST-A-02 exceeded PDU capacity (22kW on 20kW circuit). Breaker tripped, powering down all 4 hosts in the rack.",
        "detection": "Automated power monitoring alert",
        "resolution": "Redistributed GPU servers across racks. Upgraded PDU to 30kW rating during next maintenance window.",
        "customer_impact": ["SVC-ECOMMERCE-DB", "SVC-ML-PIPELINE", "SVC-CACHE-CLUSTER"],
        "services_affected": 3,
        "alerts_gen": 1205,
        "alerts_sup": 1180,
        "ttd": 8,
        "ttr": "105 minutes",
        "lessons": "Add MaxPowerKW tracking to Rack entity and enforce capacity checks before server placement. Create a rack power budget dashboard.",
    },
    {
        "id": "INC-2025-12-01-0041",
        "title": "Load balancer certificate expiry — HTTPS failures",
        "severity": "P1",
        "root_cause": "LB-USE-WEB",
        "root_cause_type": "CERTIFICATE_EXPIRY",
        "created": "2025-12-01T00:05:00Z",
        "resolved": "2025-12-01T00:40:00Z",
        "sla_breached": "Yes",
        "description": "TLS certificate on LB-USE-WEB expired at midnight UTC. All HTTPS connections received certificate errors. HTTP-only clients unaffected.",
        "detection": "Customer complaints and synthetic monitoring failure",
        "resolution": "Emergency certificate renewal and deployment. Added certificate expiry monitoring with 30-day, 14-day, and 7-day alerts.",
        "customer_impact": ["SVC-ECOMMERCE-WEB"],
        "services_affected": 1,
        "alerts_gen": 67,
        "alerts_sup": 30,
        "ttd": 300,
        "ttr": "35 minutes",
        "lessons": "Implement automated certificate rotation. Add certificate expiry date as a LoadBalancer entity property for proactive alerting.",
    },
    {
        "id": "INC-2026-01-18-0007",
        "title": "Rolling update gone wrong — API gateway version mismatch",
        "severity": "P2",
        "root_cause": "SVC-ECOMMERCE-API",
        "root_cause_type": "ROLLING_UPDATE_FAILURE",
        "created": "2026-01-18T15:30:00Z",
        "resolved": "2026-01-18T16:45:00Z",
        "sla_breached": "No",
        "description": "Rolling update deployed API v3.2.0 alongside v3.1.8 instances. Breaking schema change in v3.2.0 caused 50% of requests to fail depending on which instance handled them.",
        "detection": "Automated error rate spike alert",
        "resolution": "Rolled back to v3.1.8. Implemented blue-green deployment for breaking changes.",
        "customer_impact": ["SVC-ECOMMERCE-API", "SVC-ECOMMERCE-WEB", "SVC-PAYMENT"],
        "services_affected": 3,
        "alerts_gen": 543,
        "alerts_sup": 500,
        "ttd": 20,
        "ttr": "75 minutes",
        "lessons": "Enforce semantic versioning — major version bumps require blue-green deployment. Add API schema compatibility checks to CI pipeline.",
    },
]


def format_ticket(t: dict) -> str:
    impact_list = "\n".join(f"- {s}" for s in t["customer_impact"])
    return f"""Incident: {t["id"]}
Title: {t["title"]}
Severity: {t["severity"]}
Root Cause: {t["root_cause"]}
Root Cause Type: {t["root_cause_type"]}
Created: {t["created"]}
Resolved: {t["resolved"]}
SLA Breached: {t["sla_breached"]}

Description:
{t["description"]}

Detection Method:
{t["detection"]}

Resolution:
{t["resolution"]}

Customer Impact:
{impact_list}

Services Affected: {t["services_affected"]}
Alerts Generated: {t["alerts_gen"]}
Alerts Suppressed: {t["alerts_sup"]}
Time to Detect: {t["ttd"]} seconds
Time to Resolve: {t["ttr"]}

Lessons Learned:
{t["lessons"]}
"""


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Generating cloud-outage tickets ...")
    for t in TICKETS:
        path = os.path.join(OUTPUT_DIR, f"{t['id']}.txt")
        with open(path, "w") as f:
            f.write(format_ticket(t))
        print(f"  ✓ {t['id']}.txt")
    print(f"\n{len(TICKETS)} tickets written to {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
