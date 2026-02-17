# Customer Communication Template

## Scope

Templates and guidelines for customer communication during SLA-impacting network incidents. Covers PLATINUM (government/defence), GOLD (enterprise), SILVER (enterprise), and STANDARD (residential) tiers.

## Communication Priority Order

During a compound failure, communicate in SLA tier order:

| Priority | Tier | Contact Method | Timeline |
|---|---|---|---|
| 1 | PLATINUM | Phone call to designated liaison + secure email | Within 10 minutes |
| 2 | GOLD | Phone call to account manager + email | Within 20 minutes |
| 3 | SILVER | Email to account manager | Within 30 minutes |
| 4 | STANDARD | Status page update | Within 1 hour |

---

## PLATINUM Tier — Government / Defence

### Initial Notification (phone + secure email)

```
SUBJECT: [URGENT] Network Incident Affecting {ServiceId} — {IncidentTimestamp}

{CustomerName},

We are experiencing a network incident affecting your service {ServiceId}. 

Current Status: {Status — e.g., "Primary connectivity path is down, traffic has been rerouted to backup path"}
Impact: {Impact — e.g., "Increased latency on VPN tunnel, potential for intermittent connectivity"}
Estimated Resolution: {ETA or "Under investigation"}

Your service is classified as PLATINUM priority. A dedicated incident manager has been assigned. We will provide updates every 15 minutes until resolution.

Dedicated Incident Line: +61-2-XXXX-XXXX
Incident Reference: {IncidentId}
```

### Defence-Specific Protocol
- Federal government and defence VPN incidents require notification to the designated security liaison.
- If the incident involves a route leak or path change affecting defence traffic, invoke the security incident process.
- All communications must be via approved secure channels.

---

## GOLD Tier — Enterprise

### Initial Notification (phone + email)

```
SUBJECT: Network Incident Notification — {ServiceId} — {IncidentTimestamp}

Dear {CustomerName} Account Team,

We are currently investigating a network incident that is impacting service {ServiceId}.

Impact Summary:
- Service: {ServiceType}
- Status: {Status}
- Affected Path: {AffectedPath}
- SLA Status: {SLAStatus — e.g., "SLA timer started at {Timestamp}"}

We are actively working to restore full service. Next update in 30 minutes.

Account Manager: {AccountManager}
Incident Reference: {IncidentId}
```

### SLA Breach Notification

If the SLA breach window has been exceeded:

```
SUBJECT: SLA Breach Notification — {ServiceId} — {SLAPolicyId}

Dear {CustomerName},

We regret to inform you that service {ServiceId} has been in a degraded state beyond the SLA threshold.

SLA Commitment: {AvailabilityPct}% uptime
SLA Breach Time: {BreachDuration}
Penalty Rate: ${PenaltyPerHourUSD}/hour

A formal incident report will be provided within 5 business days of resolution.
```

---

## SILVER Tier — Enterprise

### Initial Notification (email)

```
SUBJECT: Service Advisory — {ServiceId}

Dear {CustomerName},

We are aware of a network issue affecting service {ServiceId}. Our team is investigating and working toward resolution.

Impact: {BriefImpact}
Expected Resolution: {ETA}

We will provide an update when the issue is resolved or within 1 hour.

Support: support@telco.example.com
Reference: {IncidentId}
```

---

## STANDARD Tier — Residential

### Status Page Update

```
TITLE: Service Disruption — {Region} Area

We are currently experiencing a service disruption affecting broadband services in the {City} area.

Impact: Some customers may experience slow speeds or intermittent connectivity.
Cause: Under investigation.
Estimated Resolution: {ETA}

We apologise for the inconvenience and are working to restore full service.

Last Updated: {Timestamp}
```

---

## Compound Failure Communication

When multiple root causes are in play:
1. **Do not speculate** about the number of root causes in customer-facing communications.
2. **Use neutral language:** "We are experiencing a complex network event" rather than "Two simultaneous failures occurred."
3. **Focus on impact and ETA**, not technical details.
4. **Update more frequently** during compound failures — every 15 minutes for PLATINUM, every 30 minutes for GOLD.
5. **POST-incident:** The formal incident report should detail the compound failure for enterprise customers.

## Escalation

| Condition | Action |
|---|---|
| PLATINUM customer impacted for > 10 minutes | VP Operations notified |
| GOLD customer impacted for > 30 minutes | Service Delivery Manager notified |
| Public media attention | PR/Communications team engaged |
| Defence/government security concern | CISO notified |

## Cross-References

- See `capacity_exhaustion_runbook.md` for QoS prioritisation that determines service impact levels.
- See relevant failure runbooks for technical details to inform customer communication.
