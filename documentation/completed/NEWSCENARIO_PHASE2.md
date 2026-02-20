# Phase 2 — Scenario Refocus: Two Alert Storm Demo Flows

> **Scope:** Scenario data only — demo flows, alert prompts, use cases. No code changes.
> **Depends on:** Phase 1 (new sensor/duty roster data must exist).
> **Outcome:** Two focused alert-storm demo flows: (1) Fibre Cut and (2) Wear & Tear. All other demo flows removed.
>
> **AUDIT STATUS:** Verified against codebase. `demo_flows` are purely UI — displayed in ScenarioPanel.tsx as expandable cards with a "Use ▸" button that injects prompt text into the chat input. No backend logic depends on them. Safe to replace.

---

## 1. Why

The requirements state: "Focus on TWO ALERT storm scenarios. SCREW THE OTHER DEMO FLOWS."

Currently `telecom-playground` has **three** demo flows:
1. "Fibre Cut Incident — Full Root Cause Analysis" (alert storm — **keep and enhance**)
2. "Shared Conduit Risk Discovery" (topology Q&A — **remove**)
3. "Firmware Advisory & Proactive Risk" (advisory trigger — **remove**)

We replace them with exactly two alert-storm-triggered investigations:
1. **Fibre Cut Alert Storm** — acute failure, sudden onset, field dispatch to the cut location
2. **Wear & Tear Alert Storm** — gradual degradation, sensor trend analysis, proactive field dispatch before failure

Both flows will now culminate in the orchestrator **dispatching a field engineer** using the new duty roster data (Phase 1) and the new FunctionTool (Phase 3).

---

## 2. Demo Flow 1: Fibre Cut Alert Storm (enhanced)

### Narrative

It's 2:31 PM on February 6, 2026. The Fabric Eventhouse anomaly detector fires. Twenty correlated alerts land within a single second — VPN tunnels down, broadband degraded, mobile backhaul failing across both Sydney and Melbourne. The AI receives the raw alert batch and begins investigation.

**Key enhancement over the current flow:** After identifying the fibre cut as root cause, the orchestrator:
- Queries per-sensor readings to pinpoint the physical fault location (between sensor SENS-SYD-MEL-F1-OPT-001 at Campbelltown and SENS-SYD-MEL-F1-OPT-002 at Goulburn)
- Queries the duty roster to find the nearest on-call field engineer (Dave Mitchell, Goulburn Regional)
- **Fires the dispatch_field_engineer action** with the engineer's details and exact sensor coordinates

### Updated alert_storm.md

The existing `alert_storm.md` file stays as-is — it's already a 20-row CSV of the fibre cut alert storm. No changes needed.

### Demo flow steps in scenario.yaml

```yaml
  - title: "Fibre Cut Alert Storm — Root Cause & Field Dispatch"
    description: >
      It's 2:31 PM and the Fabric Eventhouse anomaly detector fires. Twenty
      correlated alerts land within a single second — VPN tunnels down, broadband
      degraded, mobile backhaul failing across both Sydney and Melbourne. The
      anomaly detector groups the burst and triggers the agentic investigation
      flow, passing the raw alert batch as input. The AI must identify the root
      cause, assess blast radius, locate the fault via per-sensor data, find the
      nearest on-duty field engineer, and dispatch them to the site.
    steps:
      - prompt: |
          [AUTOMATED TRIGGER — Fabric Eventhouse Anomaly Detector]
          An anomaly burst has been detected: 20 correlated alerts within 1 second across the SYD-MEL corridor. Raw alert data below.


          14:31:14.077 WARNING MOB-5G-MEL-3011 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS below threshold
          14:31:14.124 WARNING MOB-5G-SYD-2042 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS below threshold
          14:31:14.133 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down
          14:31:14.161 CRITICAL VPN-BIGBANK SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down
          14:31:14.185 WARNING MOB-5G-SYD-2041 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS below threshold
          14:31:14.222 WARNING MOB-5G-MEL-3011 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS below threshold
          14:31:14.259 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down
          14:31:14.289 MAJOR BB-BUNDLE-SYD-NORTH SERVICE_DEGRADATION Customer broadband degraded — upstream path impacted
          14:31:14.518 MAJOR BB-BUNDLE-MEL-EAST SERVICE_DEGRADATION Customer broadband degraded — upstream path impacted
          14:31:14.551 WARNING MOB-5G-MEL-3011 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS below threshold
          14:31:14.558 WARNING MOB-5G-SYD-2042 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS below threshold
          14:31:14.565 WARNING MOB-5G-SYD-2041 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS below threshold
          14:31:14.657 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down
          14:31:14.704 CRITICAL VPN-BIGBANK SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down
          14:31:14.808 MAJOR BB-BUNDLE-MEL-EAST SERVICE_DEGRADATION Customer broadband degraded — upstream path impacted
          14:31:14.847 CRITICAL VPN-BIGBANK SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down
          14:31:14.847 WARNING MOB-5G-SYD-2041 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS below threshold
          14:31:14.902 MAJOR BB-BUNDLE-MEL-EAST SERVICE_DEGRADATION Customer broadband degraded — upstream path impacted
          14:31:14.968 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down
          14:31:14.986 MAJOR BB-BUNDLE-MEL-EAST SERVICE_DEGRADATION Customer broadband degraded — upstream path impacted
        expect: >
          The AI should: (1) parse the alert storm, deduplicate, identify SYD-MEL
          corridor as common factor, (2) trace topology to LINK-SYD-MEL-FIBRE-01
          as root cause, (3) query per-sensor readings to isolate the fault between
          Campbelltown and Goulburn splice points, (4) look up the duty roster for
          the nearest on-call field engineer, and (5) dispatch_field_engineer action
          to send Dave Mitchell (Goulburn Regional) to sensor SENS-SYD-MEL-F1-OPT-002
          at GPS -34.7546, 149.7186 with instructions to inspect for physical fibre damage.
      - prompt: "Which enterprise services are affected and what SLA penalties are we facing?"
        expect: >
          Full blast radius: VPN-ACME-CORP ($50K/hr GOLD SLA), VPN-BIGBANK ($25K/hr
          SILVER SLA), broadband bundles, mobile backhaul. Quantifies total customer
          impact and SLA breach timelines.
      - prompt: "Has the field engineer confirmed the fault location yet?"
        expect: >
          The orchestrator should note that the dispatch action was sent and
          summarize the dispatch details (engineer name, destination coordinates,
          physical signs to look for). If real email were implemented, it would
          check for a response — for demo, it recaps the dispatch action.
```

---

## 3. Demo Flow 2: Wear & Tear Alert Storm (new)

### Narrative

It's 9:15 AM on February 6, 2026. Unlike the sudden fibre cut, this scenario starts with a slow burn. Over the past 72 hours, the Goulburn amplifier site (AMP-SYD-MEL-GOULBURN) has been showing gradually increasing vibration readings and slowly degrading optical power. The degradation escalates until multiple services start reporting intermittent quality issues — not a hard down like the fibre cut, but enough to trigger a burst of WARNING and MAJOR alerts.

The key difference from the fibre cut scenario:
- **Gradual onset** vs sudden failure
- **Intermittent** service impacts (MOS drops, latency spikes) vs hard down (VPN unreachable)
- **Root cause is wear & tear** (amplifier degradation + conduit micro-bending) vs acute fibre cut
- **Sensor trend analysis** reveals the slow progression — individual sensor time-series data is critical
- The orchestrator must **proactively dispatch** before total failure occurs

### New alert file: `data/prompts/alert_storm_wear_tear.md`

Create a new CSV-format alert file with ~15 alerts that look different from the fibre cut:

```csv
AlertId,Timestamp,SourceNodeId,SourceNodeType,AlertType,Severity,Description,OpticalPowerDbm,BitErrorRate,CPUUtilPct,PacketLossPct
ALT-20260206-004101,2026-02-06T09:15:02.112Z,LINK-SYD-MEL-FIBRE-01,TransportLink,OPTICAL_DEGRADATION,MAJOR,Optical power degrading — approaching maintenance threshold,-18.7,4.2e-7,42.1,2.8
ALT-20260206-004102,2026-02-06T09:15:03.445Z,LINK-SYD-MEL-FIBRE-01,TransportLink,HIGH_BER,MAJOR,Bit error rate above acceptable threshold — link quality degrading,-18.9,6.1e-7,43.5,3.1
ALT-20260206-004103,2026-02-06T09:15:05.201Z,VPN-ACME-CORP,Service,SERVICE_DEGRADATION,WARNING,VPN tunnel quality degraded — increased jitter and packet loss on primary MPLS path,-18.7,4.2e-7,55.3,4.2
ALT-20260206-004104,2026-02-06T09:15:05.892Z,VPN-BIGBANK,Service,SERVICE_DEGRADATION,WARNING,VPN tunnel quality degraded — latency spikes on primary MPLS path,-18.9,6.1e-7,48.7,3.5
ALT-20260206-004105,2026-02-06T09:15:07.334Z,MOB-5G-MEL-3011,Service,SERVICE_DEGRADATION,WARNING,Backhaul degradation — intermittent voice quality drops,-19.1,5.8e-7,51.2,2.9
ALT-20260206-004106,2026-02-06T09:15:08.712Z,BB-BUNDLE-MEL-EAST,Service,SERVICE_DEGRADATION,WARNING,Customer broadband quality degraded — upstream jitter above threshold,-18.5,3.9e-7,44.8,3.8
ALT-20260206-004107,2026-02-06T09:15:12.003Z,LINK-SYD-MEL-FIBRE-01,TransportLink,OPTICAL_DEGRADATION,MAJOR,Optical power continuing to degrade — now below -19 dBm,-19.3,7.2e-7,43.1,4.5
ALT-20260206-004108,2026-02-06T09:15:14.556Z,VPN-ACME-CORP,Service,SERVICE_DEGRADATION,MAJOR,VPN tunnel experiencing sustained packet loss above 4% — escalating severity,-19.3,7.2e-7,58.4,5.1
ALT-20260206-004109,2026-02-06T09:15:15.889Z,MOB-5G-SYD-2041,Service,SERVICE_DEGRADATION,WARNING,Backhaul degradation — voice quality MOS dropping below threshold,-18.8,5.5e-7,53.6,3.3
ALT-20260206-004110,2026-02-06T09:15:18.223Z,LINK-SYD-MEL-FIBRE-01,TransportLink,HIGH_BER,MAJOR,Bit error rate accelerating — 7.2e-7 and rising,-19.6,8.8e-7,44.2,5.8
ALT-20260206-004111,2026-02-06T09:15:20.445Z,VPN-BIGBANK,Service,SERVICE_DEGRADATION,MAJOR,VPN tunnel latency exceeding 45ms — approaching SLA threshold,-19.6,8.8e-7,50.1,4.7
ALT-20260206-004112,2026-02-06T09:15:22.778Z,BB-BUNDLE-SYD-NORTH,Service,SERVICE_DEGRADATION,WARNING,Customer broadband quality degraded — bufferbloat detected on upstream path,-19.1,6.3e-7,47.3,3.9
ALT-20260206-004113,2026-02-06T09:15:25.112Z,MOB-5G-SYD-2042,Service,SERVICE_DEGRADATION,WARNING,Backhaul degradation — video call quality below acceptable threshold,-19.3,7.1e-7,52.8,4.1
ALT-20260206-004114,2026-02-06T09:15:28.334Z,LINK-SYD-MEL-FIBRE-01,TransportLink,CAPACITY_EXCEEDED,WARNING,Link utilization spiking as traffic fails over to backup capacity,-19.8,9.4e-7,45.6,6.2
ALT-20260206-004115,2026-02-06T09:15:31.667Z,BB-BUNDLE-MEL-EAST,Service,SERVICE_DEGRADATION,MAJOR,Customer broadband service degradation — sustained packet loss above 5%,-19.8,9.4e-7,46.2,5.4
```

**Key differences from fibre cut alerts:**
- Severity is mostly WARNING/MAJOR (not CRITICAL) — services are degrading, not down
- Alert types include `OPTICAL_DEGRADATION`, `HIGH_BER`, `CAPACITY_EXCEEDED` (not just `SERVICE_DEGRADATION`)
- Optical power readings are in the -18 to -20 dBm range (degraded, not dead)
- BER is in the 1e-7 range (degraded, not failed)
- Packet loss is 2–6% (problematic but not total failure)
- The alerts span ~30 seconds instead of 1 second — indicating a progression, not instantaneous failure

### Demo flow steps in scenario.yaml

```yaml
  - title: "Wear & Tear Alert Storm — Gradual Degradation & Proactive Dispatch"
    description: >
      It's 9:15 AM. Unlike the sudden fibre cut, this alert storm has been
      building slowly. Optical power on the SYD-MEL corridor has been dropping
      over the past 72 hours — now it's crossed the degradation threshold and
      services are experiencing intermittent quality issues. The Fabric Eventhouse
      anomaly detector fires a burst of 15 correlated WARNING/MAJOR alerts. The
      AI must distinguish this gradual wear-and-tear pattern from an acute
      failure, use per-sensor trend data to identify the degrading component,
      and proactively dispatch a field engineer before total failure occurs.
    steps:
      - prompt: |
          [AUTOMATED TRIGGER — Fabric Eventhouse Anomaly Detector]
          An anomaly burst has been detected: 15 correlated alerts within 30 seconds on the SYD-MEL corridor. Mixed OPTICAL_DEGRADATION, HIGH_BER, and SERVICE_DEGRADATION alerts. Severity: mostly WARNING/MAJOR (no CRITICAL). Raw alert data below.


          09:15:02.112 MAJOR LINK-SYD-MEL-FIBRE-01 OPTICAL_DEGRADATION Optical power degrading — approaching maintenance threshold
          09:15:03.445 MAJOR LINK-SYD-MEL-FIBRE-01 HIGH_BER Bit error rate above acceptable threshold — link quality degrading
          09:15:05.201 WARNING VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel quality degraded — increased jitter and packet loss
          09:15:05.892 WARNING VPN-BIGBANK SERVICE_DEGRADATION VPN tunnel quality degraded — latency spikes on primary MPLS path
          09:15:07.334 WARNING MOB-5G-MEL-3011 SERVICE_DEGRADATION Backhaul degradation — intermittent voice quality drops
          09:15:08.712 WARNING BB-BUNDLE-MEL-EAST SERVICE_DEGRADATION Customer broadband quality degraded — upstream jitter
          09:15:12.003 MAJOR LINK-SYD-MEL-FIBRE-01 OPTICAL_DEGRADATION Optical power continuing to degrade — now below -19 dBm
          09:15:14.556 MAJOR VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel experiencing sustained packet loss above 4%
          09:15:15.889 WARNING MOB-5G-SYD-2041 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS dropping
          09:15:18.223 MAJOR LINK-SYD-MEL-FIBRE-01 HIGH_BER Bit error rate accelerating — 7.2e-7 and rising
          09:15:20.445 MAJOR VPN-BIGBANK SERVICE_DEGRADATION VPN tunnel latency exceeding 45ms — approaching SLA threshold
          09:15:22.778 WARNING BB-BUNDLE-SYD-NORTH SERVICE_DEGRADATION Customer broadband quality degraded — bufferbloat
          09:15:25.112 WARNING MOB-5G-SYD-2042 SERVICE_DEGRADATION Backhaul degradation — video call quality below threshold
          09:15:28.334 WARNING LINK-SYD-MEL-FIBRE-01 CAPACITY_EXCEEDED Link utilization spiking as traffic fails over
          09:15:31.667 MAJOR BB-BUNDLE-MEL-EAST SERVICE_DEGRADATION Customer broadband — sustained packet loss above 5%
        expect: >
          The AI should: (1) recognise this as a DEGRADATION pattern (not acute
          failure) based on severity levels and alert types, (2) trace to
          LINK-SYD-MEL-FIBRE-01 as the degrading component, (3) query per-sensor
          trend data for LINK-SYD-MEL-FIBRE-01 sensors to identify the specific
          segment showing the worst degradation (Goulburn area — correlating with
          the amplifier site AMP-SYD-MEL-GOULBURN), (4) check amplifier
          calibration dates (AMP-SYD-MEL-GOULBURN last calibrated 2025-09-15 —
          5 months ago), (5) look up duty roster for nearest regional field
          engineer, and (6) fire dispatch_field_engineer to send them to
          inspect the Goulburn amplifier site and the fibre segment for signs
          of vibration damage, conduit wear, or amplifier degradation — BEFORE
          total failure occurs.
      - prompt: "Show me the sensor trend data for LINK-SYD-MEL-FIBRE-01 over the past 72 hours"
        expect: >
          TelemetryAgent queries SensorReadings table for all sensors on
          LINK-SYD-MEL-FIBRE-01. Shows the gradual optical power decline at
          the Goulburn splice point (SENS-SYD-MEL-F1-OPT-002) from -12 dBm
          to -19+ dBm over 72 hours, while the Campbelltown sensor
          (SENS-SYD-MEL-F1-OPT-001) stayed normal — proving the degradation
          is localised to the Goulburn-Albury segment. Also shows rising
          vibration readings at AMP-SYD-MEL-GOULBURN.
      - prompt: "What should the field engineer look for when they arrive?"
        expect: >
          The orchestrator should synthesise from: (1) runbook for optical
          degradation / amplifier maintenance, (2) sensor location data
          (GPS coordinates, mount location descriptions), and (3) the specific
          metrics indicating what's wrong. Should produce a checklist:
          inspect amplifier housing for physical damage, check fibre splice
          points for moisture ingress, measure vibration at the conduit,
          clean optical connectors, re-run amplifier self-test.
```

---

## 4. Updated scenario.yaml Fields

### 4.1 Replace use_cases

```yaml
use_cases:
  - "Fibre cut alert storm investigation with per-sensor fault localisation"
  - "Wear-and-tear degradation detection via sensor trend analysis"
  - "Automated field engineer dispatch based on duty roster and sensor GPS"
  - "Alert storm triage — distinguishing acute failure from gradual degradation"
  - "SLA breach risk assessment with quantified customer impact"
```

### 4.2 Replace example_questions

```yaml
example_questions:
  - "What caused the alert storm on the Sydney-Melbourne corridor?"
  - "Which specific sensor detected the fault first and where is it located?"
  - "Who is the nearest on-duty field engineer to the fault location?"
  - "Show me the sensor trend data for LINK-SYD-MEL-FIBRE-01 over the past 72 hours"
  - "Which enterprise services are affected and what SLA penalties are we facing?"
  - "Is this an acute failure or gradual degradation — what's the evidence?"
```

### 4.3 Replace demo_flows

Remove all three existing demo flows. Replace with the two defined above (§2 and §3).

### 4.4 paths — add wear_tear_alert

> **AUDIT NOTE:** `paths.default_alert` is never consumed by any runtime code — no backend or frontend reads it. The actual alert text is embedded directly in each demo flow step's `prompt` field (which is what the user submits). Adding `wear_tear_alert` here is for documentation/completeness only. The real mechanism for presenting the wear-and-tear scenario is the demo_flow step prompt in §3 above.

```yaml
paths:
  # ... existing paths ...
  default_alert: data/prompts/alert_storm.md
  wear_tear_alert: data/prompts/alert_storm_wear_tear.md
```

---

## 5. Telemetry Data: SensorReadings for Wear & Tear Pattern

The `SensorReadings.csv` data (generated by `scripts/generate_sensor_data.py` from Phase 1) must include a clear **wear-and-tear signature** for the Goulburn segment sensors.

### Required patterns in generated data:

**Sensors on LINK-SYD-MEL-FIBRE-01 (Goulburn area):**

| Sensor | Metric | Feb 4 00:00 | Feb 5 00:00 | Feb 6 00:00 | Feb 6 09:00 | Feb 6 09:15 |
|---|---|---|---|---|---|---|
| SENS-SYD-MEL-F1-OPT-001 (Campbelltown) | OpticalPower (dBm) | -10.2 | -10.3 | -10.1 | -10.2 | -10.3 |
| SENS-SYD-MEL-F1-OPT-002 (Goulburn) | OpticalPower (dBm) | -11.8 | -13.5 | -15.8 | -18.2 | -19.6 |
| SENS-SYD-MEL-F1-OPT-003 (Albury) | OpticalPower (dBm) | -11.5 | -12.8 | -14.1 | -16.5 | -17.9 |
| SENS-SYD-MEL-F1-BER-001 (SYD head-end) | BitErrorRate | 2e-12 | 5e-11 | 1e-8 | 3e-7 | 9e-7 |
| AMP-GOULBURN-VIB-001 | Vibration (g) | 0.15 | 0.22 | 0.45 | 0.78 | 0.95 |

**Key:** The Goulburn sensor (OPT-002) degrades fastest. Campbelltown (OPT-001) stays normal. This allows the orchestrator to triangulate the fault location to the segment between Campbelltown and Goulburn.

**For the fibre cut scenario (Feb 6 ~14:31):**
- Same sensors show a sudden cliff-edge: OPT-002 drops from -12 to -35 dBm in <1 minute
- OPT-001 stays normal
- BER goes to ~1 (total link failure)
- This is distinguishable from the gradual wear pattern

---

## 6. Files to Create / Modify — Summary

| Action | File | Description |
|---|---|---|
| **CREATE** | `data/scenarios/telecom-playground/data/prompts/alert_storm_wear_tear.md` | 15-row CSV of wear-and-tear alert storm |
| **MODIFY** | `data/scenarios/telecom-playground/scenario.yaml` | Replace use_cases, example_questions, demo_flows; add wear_tear_alert path |
| **VERIFY** | `data/scenarios/telecom-playground/data/prompts/alert_storm.md` | Existing fibre cut alert storm — no changes needed |

---

## 7. Validation Checklist

- [ ] `alert_storm_wear_tear.md` has valid CSV format matching AlertStream schema
- [ ] Both demo flows reference only entities that exist in the graph (entity IDs match CSVs)
- [ ] Wear-and-tear alerts have distinct characteristics from fibre cut alerts (severity, types, timing)
- [ ] `scenario.yaml` parses correctly after changes
- [ ] Example questions reference capabilities that the agents actually have
- [ ] Removed demo flows (Shared Conduit, Firmware Advisory) don't leave orphaned references
- [ ] SensorReadings.csv data (Phase 1) aligns with the wear-and-tear timeline described here
