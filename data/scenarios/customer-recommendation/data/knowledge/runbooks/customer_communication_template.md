# Template: Customer Communication — SLA Breach Notification

## Summary
When a recommendation engine incident impacts customer segments with SLA agreements, proactive communication is required. This template provides standard formats for different stages of incident lifecycle.

---

## Template 1: Initial Notification (within 15 minutes of impact detection)

**Subject**: [P1] Service Impact Notification — {SegmentName} — {IncidentId}

**Body**:

Dear {CustomerName},

We are writing to notify you of a service-affecting event impacting your shopping experience.

**Incident Details:**
- **Incident ID**: {IncidentId}
- **Start Time**: {IncidentStartTime} (UTC)
- **Affected Segment**: {SegmentName} ({SegmentId})
- **Current Impact**: {ImpactDescription}
- **Severity**: {SeverityLevel}

**What we know:**
{RootCauseSummary}

**What we are doing:**
Our automated operations system has detected the issue, identified the root cause, and initiated corrective action. {ActionSummary}

**Next update**: We will provide an update within 30 minutes or sooner if there is a material change.

**Escalation contact**: Operations — ops@ecommerce.example.com | 1-800-XXX-XXXX

---

## Template 2: Update Notification (every 30 minutes during active incident)

**Subject**: [UPDATE] {SegmentName} — {IncidentId} — {UpdateNumber}

**Body**:

Dear {CustomerName},

This is update #{UpdateNumber} for incident {IncidentId}.

**Current Status**: {CurrentStatus}
**Elapsed Time**: {ElapsedTime}

**Progress since last update:**
{ProgressSummary}

**Estimated time to resolution**: {ETR}

**SLA Status:**
- Max Delivery Days: {MaxDeliveryDays} target | Current: {CurrentDeliveryDays}
- Return Window: {ReturnWindowDays} days
- Support Tier: {SupportTier}

---

## Template 3: Resolution Notification

**Subject**: [RESOLVED] {SegmentName} — {IncidentId}

**Body**:

Dear {CustomerName},

We are pleased to confirm that incident {IncidentId} has been resolved.

**Resolution Summary:**
- **Incident ID**: {IncidentId}
- **Start Time**: {IncidentStartTime} (UTC)
- **Resolution Time**: {ResolutionTime} (UTC)
- **Total Duration**: {TotalDuration}
- **Root Cause**: {RootCause}
- **Resolution Action**: {ResolutionAction}

**SLA Impact Assessment:**
- Customer satisfaction impact: {SatisfactionImpact}
- Affected customers: {AffectedCustomerCount}
- Estimated revenue impact: {RevenueImpact}

**Compensation:**
As a gesture of goodwill, we are providing the following to affected customers:
- {CompensationDetails}

**Preventive measures:**
{PreventiveMeasures}

A formal Root Cause Analysis (RCA) report will be provided within 5 business days.

---

## Template 4: Apology Credit — Segment-Specific

### SEG-NEW (New Customers)
- 15% discount code on next purchase
- Free shipping on next 3 orders
- Priority support for 30 days

### SEG-CASUAL (Casual Shoppers)
- 10% discount code on next purchase
- Free shipping on next order

### SEG-WINBACK (Win-Back Targets)
- 20% discount code on next purchase
- Free shipping on next 5 orders
- Dedicated account manager for 60 days

### SEG-LOYAL (Loyal Customers)
- 10% loyalty bonus credit
- Early access to next sale event

### SEG-VIP (VIP Customers)
- Personal call from account manager
- 15% credit on next purchase
- Priority access to new product launches

---

## Variable Reference

| Variable | Source | Example |
|---|---|---|
| {SegmentName} | CustomerSegment entity — SegmentName property | New Customers |
| {SegmentId} | CustomerSegment entity — SegmentId key | SEG-NEW |
| {CustomerName} | Customer entity — CustomerName property | Henry Brown |
| {IncidentId} | Ticketing system | INC-2026-02-06-0001 |
| {SeverityLevel} | Alert severity mapping | P1 — Critical |
| {RootCause} | Troubleshooting agent output | Recommendation model v2.4 price-insensitivity bias |
| {MaxDeliveryDays} | SLAPolicy entity — MaxDeliveryDays | 5 |
| {ReturnWindowDays} | SLAPolicy entity — ReturnWindowDays | 30 |
| {SupportTier} | SLAPolicy entity — SupportTier | Gold |
