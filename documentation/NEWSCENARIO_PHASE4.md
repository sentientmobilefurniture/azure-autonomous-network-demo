# Phase 4 — Orchestrator Prompt Updates

> **Scope:** Prompt files only — no code changes.
> **Depends on:** Phase 1 (sensor/duty roster data exists), Phase 3 (FunctionTool is wired up).
> **Outcome:** The Orchestrator knows about sensors, duty roster, and the `dispatch_field_engineer` tool. It can reason about sensor localisation and trigger field dispatch during investigation flows.
>
> **AUDIT STATUS:** Verified against actual prompt files. Flow A has 7 steps (1–7), Flow B has 8 steps (1–8). Step renumbering is explicit below. TelemetryAgent uses `query_telemetry` tool for all KQL queries — SensorReadings queries go through the same tool.

---

## 1. Why

The orchestrator prompt currently has no awareness of:
- Per-sensor readings or the `SensorReadings` telemetry table
- Physical GPS coordinates on infrastructure entities
- The duty roster data source
- The `dispatch_field_engineer` function tool

Without prompt updates, the orchestrator will never call the new tool or query sensor data — it simply doesn't know these capabilities exist.

---

## 2. Changes to `foundry_orchestrator_agent.md`

File: `data/scenarios/telecom-playground/data/prompts/foundry_orchestrator_agent.md`

### 2.1 Add sensor awareness to TelemetryAgent description

**In the `### TelemetryAgent` section**, append after the existing description:

```markdown
**NEW — SensorReadings table:** The TelemetryAgent can also query the `SensorReadings` table, which contains per-sensor time-series data. Unlike AlertStream (which records alerts by entity ID), SensorReadings has individual sensor readings with sensor IDs like `SENS-SYD-MEL-F1-OPT-002`. Each sensor has a physical GPS location. Use this to:
- Determine which specific sensor detected the anomaly first
- Triangulate the physical fault location by comparing sensor readings along a link
- Identify gradual degradation trends (wear and tear) vs sudden failure (fibre cut)

**Good queries:** "Get recent SensorReadings for SensorId SENS-SYD-MEL-F1-OPT-002", "Get SensorReadings where SensorType == 'OpticalPower' for the last 72 hours sorted by Timestamp"
**Bad queries:** "Get sensor locations" (that's topology — use GraphExplorerAgent)
```

### 2.2 Add GraphExplorerAgent sensor/duty roster awareness

**In the `### GraphExplorerAgent` section**, append:

```markdown
**NEW — Sensor entities:** The graph now contains `Sensor` vertices with physical GPS coordinates, mount locations, and `monitors` edges to the infrastructure entity they observe. Use this to:
- Find all sensors on a specific link: "What sensors monitor LINK-SYD-MEL-FIBRE-01?"
- Get sensor GPS coordinates for field dispatch: "What are the coordinates of SENS-SYD-MEL-F1-OPT-002?"
- Identify which infrastructure segment a sensor covers

**NEW — DutyRoster lookup:** The graph contains `DutyRoster` vertices with on-call field engineer assignments searchable by city, region, and shift time. Use this to find the nearest on-duty person for field dispatch:
- "Who is on duty in the Goulburn region on 2026-02-06?"
- "What field engineers cover the SYD-MEL corridor?"
```

### 2.3 Add `dispatch_field_engineer` tool documentation

**Add a new section after `### TelemetryAgent`:**

```markdown
### dispatch_field_engineer (Action Tool)

This is a function tool you can call directly — it is NOT a sub-agent. When you call it, it immediately executes and returns a confirmation with the composed dispatch email.

Use this tool to dispatch an on-duty field engineer to a physical site when your investigation identifies a fault that requires on-site inspection. You MUST have gathered the following information BEFORE calling this tool:

1. **Engineer details** — from the GraphExplorerAgent duty roster query (name, email, phone)
2. **Destination GPS coordinates** — from the GraphExplorerAgent sensor location query
3. **Incident summary** — from your investigation so far
4. **Physical signs to inspect** — from the RunbookKBAgent's SOP

**When to use:**
- After identifying a physical-layer root cause (fibre cut, amplifier degradation, conduit damage)
- When sensor data pinpoints a specific physical location
- After verifying the duty roster has an on-call engineer for the affected area

**When NOT to use:**
- For software/configuration issues (BGP misconfiguration, firmware bugs)
- Before you have a confirmed or highly-probable physical root cause
- Without first querying the duty roster for the correct on-call person

**Required arguments:**
| Parameter | Source | Example |
|---|---|---|
| `engineer_name` | DutyRoster query via GraphExplorerAgent | "Dave Mitchell" |
| `engineer_email` | DutyRoster query via GraphExplorerAgent | "dave.mitchell@austtelco.com.au" |
| `engineer_phone` | DutyRoster query via GraphExplorerAgent | "+61-412-555-401" |
| `incident_summary` | Your investigation synthesis | "Fibre cut on LINK-SYD-MEL-FIBRE-01 between Campbelltown and Goulburn..." |
| `destination_description` | Sensor MountLocation via GraphExplorerAgent | "Goulburn interchange splice point" |
| `destination_latitude` | Sensor Latitude via GraphExplorerAgent | -34.7546 |
| `destination_longitude` | Sensor Longitude via GraphExplorerAgent | 149.7186 |
| `physical_signs_to_inspect` | RunbookKBAgent SOP | "Inspect splice enclosure for damage, check conduit..." |
| `sensor_ids` | SensorReadings / GraphExplorerAgent | "SENS-SYD-MEL-F1-OPT-002,SENS-AMP-GOULBURN-VIB-001" |
| `urgency` | Your assessment | "CRITICAL" or "HIGH" |
```

### 2.4 Update investigation flows to include sensor analysis and dispatch

**In the `### Flow A: Known infrastructure trigger` section**, insert new steps:

After step 3 ("Map the blast radius"):

```markdown
4. **Localise the fault via sensors.** Ask the GraphExplorerAgent for all sensors on the affected component. Then ask the TelemetryAgent for the latest SensorReadings for those sensor IDs. Compare readings to pinpoint which segment of the infrastructure is affected — the first sensor to show anomalous readings, or the sensor with the worst readings, indicates the physical fault location.
5. **Look up the duty roster.** Ask the GraphExplorerAgent for on-duty field engineers covering the region nearest to the fault location (use the city or region from the sensor's graph properties).
6. **Dispatch the field engineer.** Call `dispatch_field_engineer` with the engineer's details, sensor GPS coordinates, and a checklist from the runbook. Include the urgency level based on the severity of the incident.
```

Renumber the remaining steps: old step 4 ("Identify top 3 root causes") becomes new step 7, old 5→8, old 6→9, old 7→10. **Flow A goes from 7 steps to 10 steps.**

**In the `### Flow B: Alert storm / service-level symptoms` section**, insert new steps:

After step 5 ("Get full blast radius"):

```markdown
6. **Localise the fault via sensors.** Using the confirmed root cause component from step 4, ask the GraphExplorerAgent for all sensors monitoring it. Then ask the TelemetryAgent for SensorReadings for those sensors. The sensor with the first or worst anomalous reading pinpoints the physical fault location. For **gradual degradation**, look for downward trends over hours/days, not just current values.
7. **Look up the duty roster.** Ask the GraphExplorerAgent: who is on-duty in the region nearest to the sensor that first detected the issue?
8. **Dispatch the field engineer.** Call `dispatch_field_engineer`. For an acute failure (fibre cut), set urgency to CRITICAL. For gradual degradation (wear and tear), set urgency to HIGH — the dispatch is proactive, before total failure.
```

Renumber the remaining steps: old step 6 ("Retrieve the procedure") becomes new step 9, old 7→10, old 8→11. **Flow B goes from 8 steps to 11 steps.**

### 2.5 Update the situation report format

**In the `## Situation report format` section**, add a new section:

```markdown
### 7. Field Dispatch
If a physical root cause was identified and a field engineer was dispatched:
- Who was dispatched (name, role, phone)
- Where they were sent (GPS coordinates, description)
- What they were told to inspect
- Urgency level and estimated time to arrival
- The dispatch ID for tracking

If no dispatch was needed (software/config issue), state why field dispatch was not applicable.
```

### 2.6 Add SensorReadings telemetry reference

**In the `## Telemetry reference` section**, add after the AlertStream tables:

```markdown
### SensorReadings — per-sensor time-series

| Column | Description |
|---|---|
| ReadingId | Unique reading ID |
| Timestamp | ISO8601 timestamp |
| SensorId | Individual sensor ID (e.g. SENS-SYD-MEL-F1-OPT-002) |
| SensorType | OpticalPower, BitErrorRate, Temperature, Vibration, CPULoad |
| Value | Numeric reading |
| Unit | dBm, ratio, °C, g, % |
| Status | NORMAL, WARNING, CRITICAL (pre-computed threshold status) |

**Baselines by SensorType:**

| SensorType | Unit | Normal | Degraded | Critical |
|---|---|---|---|---|
| OpticalPower | dBm | -8 to -12 | < -20 | < -30 |
| BitErrorRate | ratio | < 1e-9 | > 1e-6 | > 1e-3 |
| Temperature | °C | 20–45 | > 55 | > 70 |
| Vibration | g | < 0.5 | > 1.0 | > 2.0 |
| CPULoad | % | < 70 | > 85 | > 95 |

**Key analysis pattern — fault localisation:**
When a link is degrading, compare SensorReadings across all sensors on that link. The sensor with the worst reading (or the first to degrade) indicates the physical fault location. Example: if SENS-SYD-MEL-F1-OPT-002 (Goulburn) reads -19 dBm but SENS-SYD-MEL-F1-OPT-001 (Campbelltown) reads -10 dBm, the fault is between Campbelltown and Goulburn.

**Key analysis pattern — acute vs gradual:**
- **Acute failure (fibre cut):** Sensor values drop from normal to critical within seconds. All sensors on the affected segment go to critical simultaneously.
- **Gradual degradation (wear & tear):** Sensor values deteriorate slowly over hours or days. One sensor may degrade faster than others, indicating localised wear (conduit damage, amplifier aging).
```

### 2.7 Update the rules

**In the `## Rules` section**, add:

```markdown
9. **Dispatch only with evidence.** Do not call `dispatch_field_engineer` on speculation. You must have:
   (a) a confirmed or highly-probable physical root cause from topology + telemetry correlation,
   (b) a specific sensor location pinpointing the fault,
   (c) a duty roster match for the affected region,
   (d) a checklist from the relevant runbook.
10. **Sensor triangulation.** When localising a fault, always query sensors on both ends of a link segment.
    If only one end shows degradation, the fault is localised to that segment. If both ends show degradation,
    the fault may be on the link itself (not at a splice point or amplifier).
```

---

## 3. Changes to `foundry_telemetry_agent_v2.md`

File: `data/scenarios/telecom-playground/data/prompts/foundry_telemetry_agent_v2.md`

### 3.1 Add SensorReadings table documentation

Add after the existing AlertStream and LinkTelemetry table docs:

```markdown
## SensorReadings table (~2000 rows)

Per-sensor time-series readings from individual sensors attached to infrastructure.

**Schema:**
| Column | Type | Description |
|---|---|---|
| ReadingId | string | Unique ID (e.g. RD-20260206-001) |
| Timestamp | datetime | ISO8601 |
| SensorId | string | FK to Sensor graph entity (e.g. SENS-SYD-MEL-F1-OPT-002) |
| SensorType | string | OpticalPower, BitErrorRate, Temperature, Vibration, CPULoad |
| Value | real | Numeric reading |
| Unit | string | dBm, ratio, °C, g, % |
| Status | string | NORMAL, WARNING, CRITICAL |

**Example queries:**
```kql
// Latest 20 readings for a specific sensor
SensorReadings
| where SensorId == 'SENS-SYD-MEL-F1-OPT-002'
| top 20 by Timestamp desc
| project Timestamp, SensorId, SensorType, Value, Unit, Status

// All sensors on a link showing degradation in the last 24 hours
SensorReadings
| where SensorId startswith 'SENS-SYD-MEL-F1'
| where Status != 'NORMAL'
| top 50 by Timestamp desc

// Trend analysis — hourly averages for a sensor over 72 hours
SensorReadings
| where SensorId == 'SENS-SYD-MEL-F1-OPT-002'
| summarize AvgValue=avg(Value) by bin(Timestamp, 1h), SensorId, SensorType
| order by Timestamp asc

// All CRITICAL readings across all sensors
SensorReadings
| where Status == 'CRITICAL'
| top 30 by Timestamp desc
```
```

---

## 4. Changes to `graph_explorer/core_schema.md`

File: `data/scenarios/telecom-playground/data/prompts/graph_explorer/core_schema.md`

### 4.1 Add Sensor entity documentation

(See Phase 1 §5 for the full table — include all 18 sensor instances with their IDs, types, monitored entities, and coordinates.)

### 4.2 Add DutyRoster entity documentation

```markdown
## DutyRoster (8 instances)

On-call field engineer assignments. Searchable by city/region and shift time (ShiftStart/ShiftEnd).

| RosterId | PersonName | City | Region | Role | ShiftStart | ShiftEnd |
|---|---|---|---|---|---|---|
| DUTY-SYD-2026-02-06-DAY | Marcus Chen | Sydney | NSW | FieldEngineer | 06:00 | 18:00 |
| DUTY-SYD-2026-02-06-NIGHT | Sarah O'Brien | Sydney | NSW | FieldEngineer | 18:00 | 06:00+1 |
| DUTY-MEL-2026-02-06-DAY | James Nguyen | Melbourne | VIC | FieldEngineer | 06:00 | 18:00 |
| DUTY-MEL-2026-02-06-NIGHT | Priya Sharma | Melbourne | VIC | FieldEngineer | 18:00 | 06:00+1 |
| DUTY-BNE-2026-02-06-DAY | Tom Williams | Brisbane | QLD | FieldEngineer | 06:00 | 18:00 |
| DUTY-REGIONAL-SYD-MEL-2026-02-06 | Dave Mitchell | Goulburn | NSW | RegionalFieldEngineer | 06:00 | 18:00 |
| DUTY-REGIONAL-SYD-MEL-2026-02-06-SOUTH | Karen Lee | Albury | NSW | RegionalFieldEngineer | 06:00 | 18:00 |
| DUTY-REGIONAL-SYD-BNE-2026-02-06 | Paul Jacobs | Coffs Harbour | NSW | RegionalFieldEngineer | 06:00 | 18:00 |

### Properties
- `Email`, `Phone` — contact details for dispatch
- `HomeBase` — depot location with lat/long for proximity matching
- `VehicleId` — assigned vehicle ID

### Key query patterns
- "Who is on duty in Goulburn region?" → filter by City or Region
- "What field engineers cover the SYD-MEL corridor?" → filter by Role == RegionalFieldEngineer and Region == NSW
- "Who is on duty at 14:31 on 2026-02-06?" → filter ShiftStart <= timestamp <= ShiftEnd
```

### 4.3 Add coordinates to existing entity docs

Update the CoreRouter, AggSwitch, and AmplifierSite sections to include the Latitude/Longitude columns.

---

## 5. Changes to `foundry_runbook_kb_agent.md` and `foundry_historical_ticket_agent.md`

### Minimal — no changes required

These agents don't need to know about sensors or duty roster directly. The orchestrator queries them for SOPs and precedents as before. The runbook agent already has the `fibre_cut_runbook.md` which includes physical inspection steps — the orchestrator extracts the checklist from there for the dispatch.

---

## 6. Files to Modify — Summary

| Action | File | Description |
|---|---|---|
| **MODIFY** | `data/scenarios/telecom-playground/data/prompts/foundry_orchestrator_agent.md` | Add sensor awareness, duty roster awareness, dispatch_field_engineer tool docs, update Flow A/B, update situation report format, add SensorReadings baselines, add dispatch rules |
| **MODIFY** | `data/scenarios/telecom-playground/data/prompts/foundry_telemetry_agent_v2.md` | Add SensorReadings table schema and example KQL queries |
| **MODIFY** | `data/scenarios/telecom-playground/data/prompts/graph_explorer/core_schema.md` | Add Sensor (18 instances) and DutyRoster (8 instances) entity docs, add coordinates to existing entities |

---

## 7. Validation Checklist

- [ ] Orchestrator prompt references `dispatch_field_engineer` with correct parameter names matching `api/app/dispatch.py`
- [ ] Flow A and Flow B include sensor localisation + duty roster + dispatch steps in correct order
- [ ] Situation report format includes §7 Field Dispatch
- [ ] TelemetryAgent prompt documents SensorReadings table with correct column names matching CSV schema
- [ ] Example KQL queries use correct column names and valid KQL syntax
- [ ] core_schema.md has all 18 sensor instances with correct MonitoredEntityId references
- [ ] core_schema.md DutyRoster entries match DimDutyRoster.csv exactly (names, cities, shift times)
- [ ] SensorReadings baselines in orchestrator prompt are consistent with telemetry_baselines in scenario.yaml
- [ ] No references to removed demo flows (Shared Conduit, Firmware Advisory) remain in any prompt
- [ ] Prompts don't exceed reasonable context length (orchestrator <300 lines, telemetry <150 lines)
