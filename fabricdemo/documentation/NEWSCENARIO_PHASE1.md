# Phase 1 — New Data Sources: Sensors, Coordinates, Duty Roster

> **Scope:** Data layer only. No agent, prompt, API, or frontend changes.
> **Depends on:** Nothing — this is the foundation.
> **Outcome:** Two new entity types in the graph (Sensor, DutyRoster), one new telemetry table (SensorReadings), GPS coordinates on existing entities. Ready for all downstream phases.
>
> **AUDIT STATUS:** Verified against codebase. All data-driven pipelines (`generate_topology_json.py`, `provision_lakehouse.py`, `provision_ontology.py`, `provision_eventhouse.py`, `provision_cosmos.py`) are fully generic and will pick up new schema entries without code changes.

---

## 1. Why

The requirements call for:

- Individual sensor readings with physical locations (which sensor gave what reading, where is it)
- Physical coordinates for every structure in the network
- A duty roster searchable by date and location (who is on-call, their phone, email)

All downstream features (orchestrator actions, email dispatch, frontend action cards) depend on this data existing first.

---

## 2. New Entity CSVs

All files go in `data/scenarios/telecom-playground/data/entities/`.

### 2.1 `DimSensor.csv` — Individual sensors on infrastructure

Each sensor is a physical device attached to a specific infrastructure node (TransportLink, CoreRouter, AggSwitch, AmplifierSite). It has a type (optical power, BER, temperature, vibration, humidity) and a physical GPS coordinate so field engineers know exactly where to go.

```csv
SensorId,SensorType,MonitoredEntityId,MonitoredEntityType,MountLocation,Latitude,Longitude,InstalledDate,Status
SENS-SYD-MEL-F1-OPT-001,OpticalPower,LINK-SYD-MEL-FIBRE-01,TransportLink,Splice point — 45km south of Sydney CBD near Campbelltown,-34.0650,150.8140,2018-06-15,ACTIVE
SENS-SYD-MEL-F1-OPT-002,OpticalPower,LINK-SYD-MEL-FIBRE-01,TransportLink,Splice point — Goulburn interchange (near AMP-SYD-MEL-GOULBURN),-34.7546,149.7186,2018-06-15,ACTIVE
SENS-SYD-MEL-F1-OPT-003,OpticalPower,LINK-SYD-MEL-FIBRE-01,TransportLink,Splice point — 15km north of Albury (near AMP-SYD-MEL-ALBURY),-36.0237,146.9120,2018-06-15,ACTIVE
SENS-SYD-MEL-F1-BER-001,BitErrorRate,LINK-SYD-MEL-FIBRE-01,TransportLink,Head-end transceiver bay — CORE-SYD-01 rack B3,-33.8688,151.2093,2018-06-15,ACTIVE
SENS-SYD-MEL-F1-BER-002,BitErrorRate,LINK-SYD-MEL-FIBRE-01,TransportLink,Tail-end transceiver bay — CORE-MEL-01 rack A7,-37.8136,144.9631,2018-06-15,ACTIVE
SENS-SYD-MEL-F2-OPT-001,OpticalPower,LINK-SYD-MEL-FIBRE-02,TransportLink,Splice point — 45km south of Sydney CBD near Campbelltown,-34.0650,150.8140,2020-03-10,ACTIVE
SENS-SYD-MEL-F2-OPT-002,OpticalPower,LINK-SYD-MEL-FIBRE-02,TransportLink,Splice point — Goulburn interchange (shared conduit with FIBRE-01),-34.7546,149.7186,2020-03-10,ACTIVE
SENS-SYD-BNE-F1-OPT-001,OpticalPower,LINK-SYD-BNE-FIBRE-01,TransportLink,Splice point — 80km north of Sydney near Gosford,-33.4250,151.3420,2019-04-20,ACTIVE
SENS-SYD-BNE-F1-OPT-002,OpticalPower,LINK-SYD-BNE-FIBRE-01,TransportLink,Splice point — near AMP-SYD-BNE-COFFS (Coffs Harbour),-30.2963,153.1157,2019-04-20,ACTIVE
SENS-MEL-BNE-F1-OPT-001,OpticalPower,LINK-MEL-BNE-FIBRE-01,TransportLink,Splice point — 120km east of Melbourne near Sale,-38.1000,147.0680,2020-03-10,ACTIVE
SENS-MEL-BNE-F1-OPT-002,OpticalPower,LINK-MEL-BNE-FIBRE-01,TransportLink,Splice point — near AMP-MEL-BNE-GRAFTON (Grafton),-29.6900,152.9330,2020-03-10,ACTIVE
SENS-CORE-SYD-01-TEMP-001,Temperature,CORE-SYD-01,CoreRouter,Main chassis — exhaust vent sensor,-33.8688,151.2093,2019-01-10,ACTIVE
SENS-CORE-SYD-01-CPU-001,CPULoad,CORE-SYD-01,CoreRouter,Control plane module,-33.8688,151.2093,2019-01-10,ACTIVE
SENS-CORE-MEL-01-TEMP-001,Temperature,CORE-MEL-01,CoreRouter,Main chassis — exhaust vent sensor,-37.8136,144.9631,2019-01-10,ACTIVE
SENS-CORE-MEL-01-CPU-001,CPULoad,CORE-MEL-01,CoreRouter,Control plane module,-37.8136,144.9631,2019-01-10,ACTIVE
SENS-CORE-BNE-01-TEMP-001,Temperature,CORE-BNE-01,CoreRouter,Main chassis — exhaust vent sensor,-27.4698,153.0251,2019-01-10,ACTIVE
SENS-AMP-GOULBURN-VIB-001,Vibration,AMP-SYD-MEL-GOULBURN,AmplifierSite,Amplifier housing vibration monitor,-34.7546,149.7186,2018-06-15,ACTIVE
SENS-AMP-ALBURY-VIB-001,Vibration,AMP-SYD-MEL-ALBURY,AmplifierSite,Amplifier housing vibration monitor,-36.0737,146.9135,2018-06-15,ACTIVE
```

**Design choices:**
- `MonitoredEntityId` + `MonitoredEntityType` = foreign key to any graph entity (TransportLink, CoreRouter, AmplifierSite).
- `Latitude`/`Longitude` = physical GPS coordinates (WGS84). This is what the field engineer needs.
- `MountLocation` = human-readable description of where to find the sensor.
- `SensorType` enum: `OpticalPower`, `BitErrorRate`, `Temperature`, `CPULoad`, `Vibration`, `Humidity`.

### 2.2 `DimDutyRoster.csv` — On-call field engineers

Searchable by date range and location (city/region). Each row is a shift assignment.

```csv
RosterId,PersonName,Email,Phone,City,Region,ShiftStart,ShiftEnd,Role,HomeBase,VehicleId
DUTY-SYD-2026-02-06-DAY,Marcus Chen,marcus.chen@austtelco.com.au,+61-412-555-101,Sydney,NSW,2026-02-06T06:00:00Z,2026-02-06T18:00:00Z,FieldEngineer,Campbelltown Depot,-34.0650 150.8140,VEH-SYD-03
DUTY-SYD-2026-02-06-NIGHT,Sarah O'Brien,sarah.obrien@austtelco.com.au,+61-412-555-102,Sydney,NSW,2026-02-06T18:00:00Z,2026-02-07T06:00:00Z,FieldEngineer,Parramatta Depot,-33.8150 151.0010,VEH-SYD-07
DUTY-MEL-2026-02-06-DAY,James Nguyen,james.nguyen@austtelco.com.au,+61-412-555-201,Melbourne,VIC,2026-02-06T06:00:00Z,2026-02-06T18:00:00Z,FieldEngineer,Clayton Depot,-37.9250 145.1200,VEH-MEL-02
DUTY-MEL-2026-02-06-NIGHT,Priya Sharma,priya.sharma@austtelco.com.au,+61-412-555-202,Melbourne,VIC,2026-02-06T18:00:00Z,2026-02-07T06:00:00Z,FieldEngineer,Footscray Depot,-37.7990 144.8990,VEH-MEL-05
DUTY-BNE-2026-02-06-DAY,Tom Williams,tom.williams@austtelco.com.au,+61-412-555-301,Brisbane,QLD,2026-02-06T06:00:00Z,2026-02-06T18:00:00Z,FieldEngineer,Eagle Farm Depot,-27.4380 153.0780,VEH-BNE-01
DUTY-REGIONAL-SYD-MEL-2026-02-06,Dave Mitchell,dave.mitchell@austtelco.com.au,+61-412-555-401,Goulburn,NSW,2026-02-06T06:00:00Z,2026-02-06T18:00:00Z,RegionalFieldEngineer,Goulburn Office,-34.7546 149.7186,VEH-REG-02
DUTY-REGIONAL-SYD-MEL-2026-02-06-SOUTH,Karen Lee,karen.lee@austtelco.com.au,+61-412-555-402,Albury,NSW,2026-02-06T06:00:00Z,2026-02-06T18:00:00Z,RegionalFieldEngineer,Albury Office,-36.0737 146.9135,VEH-REG-04
DUTY-REGIONAL-SYD-BNE-2026-02-06,Paul Jacobs,paul.jacobs@austtelco.com.au,+61-412-555-501,Coffs Harbour,NSW,2026-02-06T06:00:00Z,2026-02-06T18:00:00Z,RegionalFieldEngineer,Coffs Harbour Office,-30.2963 153.1157,VEH-REG-06
```

**Design choices:**
- `ShiftStart`/`ShiftEnd` = ISO8601 timestamps. Roster is searchable by date overlap.
- `City`/`Region` = location. The orchestrator can find the nearest on-duty person to a sensor's coordinates.
- `HomeBase` = human-readable depot location with lat/long for proximity matching.
- `Role` enum: `FieldEngineer` (city depot), `RegionalFieldEngineer` (covers inter-city corridors).
- Date range covers the demo's incident date (2026-02-06).

### 2.3 Physical coordinates on existing entities

Three existing CSVs need a `Latitude,Longitude` column added:

**`DimCoreRouter.csv`** — add coordinates for each data centre:
```csv
RouterId,City,Region,Vendor,Model,FirmwareVersion,Latitude,Longitude
CORE-SYD-01,Sydney,NSW,Cisco,ASR-9922,IOS-XR-7.9.2,-33.8688,151.2093
CORE-MEL-01,Melbourne,VIC,Cisco,ASR-9922,IOS-XR-7.9.2,-37.8136,144.9631
CORE-BNE-01,Brisbane,QLD,Juniper,MX10008,JUNOS-23.4R1,-27.4698,153.0251
```

**`DimAggSwitch.csv`** — add coordinates for each PoP:
```csv
SwitchId,City,UplinkRouterId,Latitude,Longitude
AGG-SYD-NORTH-01,Sydney,CORE-SYD-01,-33.7960,151.1840
AGG-SYD-SOUTH-01,Sydney,CORE-SYD-01,-33.9410,151.1730
AGG-MEL-EAST-01,Melbourne,CORE-MEL-01,-37.8200,145.0650
AGG-MEL-WEST-01,Melbourne,CORE-MEL-01,-37.8100,144.8850
AGG-BNE-CENTRAL-01,Brisbane,CORE-BNE-01,-27.4700,153.0230
AGG-BNE-SOUTH-01,Brisbane,CORE-BNE-01,-27.5540,153.0480
```

**`DimAmplifierSite.csv`** — add coordinates for each amplifier:
```csv
SiteId,Location,InstalledYear,LastCalibration,Latitude,Longitude
AMP-SYD-MEL-GOULBURN,Goulburn NSW — 195km from Sydney,2018,2025-09-15,-34.7546,149.7186
AMP-SYD-MEL-ALBURY,Albury NSW — 460km from Sydney,2018,2025-06-20,-36.0737,146.9135
AMP-SYD-BNE-COFFS,Coffs Harbour NSW — 540km from Sydney,2019,2025-11-01,-30.2963,153.1157
AMP-MEL-BNE-GRAFTON,Grafton NSW — 340km from Melbourne via coastal route,2020,2025-03-10,-29.6900,152.9330
```

---

## 3. Graph Schema Updates

Add to `graph_schema.yaml` in `telecom-playground`:

### 3.1 New vertex types

```yaml
  - label: Sensor
    csv_file: DimSensor.csv
    id_column: SensorId
    partition_key: sensor
    properties: [SensorId, SensorType, MonitoredEntityId, MonitoredEntityType, MountLocation, Latitude, Longitude, InstalledDate, Status]
    property_types:
      Latitude: Double
      Longitude: Double

  - label: DutyRoster
    csv_file: DimDutyRoster.csv
    id_column: RosterId
    partition_key: dutyroster
    properties: [RosterId, PersonName, Email, Phone, City, Region, ShiftStart, ShiftEnd, Role, HomeBase, VehicleId]
```

### 3.2 Updated vertex types (add Latitude/Longitude)

Add `Latitude, Longitude` to the `properties` list and add `property_types` for:

```yaml
  # CoreRouter — ADD Latitude, Longitude to properties list
  - label: CoreRouter
    csv_file: DimCoreRouter.csv
    id_column: RouterId
    partition_key: router
    properties: [RouterId, City, Region, Vendor, Model, FirmwareVersion, Latitude, Longitude]
    property_types:
      Latitude: Double
      Longitude: Double

  # AggSwitch — ADD Latitude, Longitude to properties list  
  - label: AggSwitch
    csv_file: DimAggSwitch.csv
    id_column: SwitchId
    partition_key: switch
    properties: [SwitchId, City, UplinkRouterId, Latitude, Longitude]
    property_types:
      Latitude: Double
      Longitude: Double

  # AmplifierSite — ADD Latitude, Longitude to properties list
  - label: AmplifierSite
    csv_file: DimAmplifierSite.csv
    id_column: SiteId
    partition_key: amplifier
    properties: [SiteId, Location, InstalledYear, LastCalibration, Latitude, Longitude]
    property_types:
      Latitude: Double
      Longitude: Double
```

### 3.3 New edges

```yaml
  # Sensor monitors_entity → target entity (polymorphic via MonitoredEntityType)
  # We need separate edge definitions per target type to satisfy the schema's
  # typed source/target requirement.

  # Sensor monitors TransportLink
  - label: monitors
    csv_file: DimSensor.csv
    filter:
      column: MonitoredEntityType
      value: TransportLink
    source:
      label: Sensor
      property: SensorId
      column: SensorId
    target:
      label: TransportLink
      property: LinkId
      column: MonitoredEntityId

  # Sensor monitors CoreRouter
  - label: monitors
    csv_file: DimSensor.csv
    filter:
      column: MonitoredEntityType
      value: CoreRouter
    source:
      label: Sensor
      property: SensorId
      column: SensorId
    target:
      label: CoreRouter
      property: RouterId
      column: MonitoredEntityId

  # Sensor monitors AmplifierSite
  - label: monitors
    csv_file: DimSensor.csv
    filter:
      column: MonitoredEntityType
      value: AmplifierSite
    source:
      label: Sensor
      property: SensorId
      column: SensorId
    target:
      label: AmplifierSite
      property: SiteId
      column: MonitoredEntityId
```

**Note on DutyRoster:** DutyRoster IS a graph vertex (loaded into Lakehouse/Ontology automatically via `graph_schema.yaml`). It has no edges because it's a lookup table, not a topology entity — but being in the graph means the **GraphExplorerAgent can query it directly via GQL** (e.g., `MATCH (d:DutyRoster) WHERE d.City = 'Goulburn' RETURN d`). No separate data source or tool is needed for querying it. It will appear as disconnected nodes in the topology visualisation — add CSS to `graph_styles` to make them visually distinct (smaller, different colour) so they don't clutter the graph.

### 3.4 Scenario YAML updates for new telemetry container

Add to `scenario.yaml` `data_sources.telemetry.config.containers`:

```yaml
        - name: SensorReadings
          partition_key: /SensorId
          csv_file: SensorReadings.csv
          id_field: ReadingId
          numeric_fields: [Value]
```

> **AUDIT NOTE:** The codebase has no `cosmos-nosql` connector. The `provision_cosmos.py` and `provision_eventhouse.py` scripts both read exclusively from `data_sources.telemetry.config.containers`. A custom `duty_roster` data source would be **silently ignored** — no code exists to provision or query it. DutyRoster is loaded into the graph via `graph_schema.yaml` instead, which is the correct path.

---

## 4. New Telemetry CSV: `SensorReadings.csv`

Goes in `data/scenarios/telecom-playground/data/telemetry/SensorReadings.csv`.

This is the per-sensor time-series data. Unlike the existing `AlertStream` (which records alerts from entity IDs like `LINK-SYD-MEL-FIBRE-01`), this table records raw readings from **individual sensors**. The orchestrator can ask "which specific sensor detected the anomaly first?" and then tell the field engineer exactly where to go.

**Schema:**
```csv
ReadingId,Timestamp,SensorId,SensorType,Value,Unit,Status
```

**Fields:**
| Column | Description |
|---|---|
| `ReadingId` | Unique reading ID (e.g. `RD-20260206-001`) |
| `Timestamp` | ISO8601 timestamp |
| `SensorId` | FK to DimSensor (e.g. `SENS-SYD-MEL-F1-OPT-002`) |
| `SensorType` | Denormalized from DimSensor for query efficiency |
| `Value` | Numeric reading value |
| `Unit` | Unit of measurement (dBm, ratio, °C, g, %) |
| `Status` | `NORMAL`, `WARNING`, `CRITICAL` (pre-computed threshold status) |

**Data generation strategy:** Generate ~2000 rows covering the 48-hour window around the incident (2026-02-04 to 2026-02-06). Pattern:

- **Normal baseline (Feb 4–5):** All sensors read within normal thresholds with minor noise.
- **Degradation onset (Feb 6 ~14:00):** Sensors on `LINK-SYD-MEL-FIBRE-01` start showing optical power dropping:
  - `SENS-SYD-MEL-F1-OPT-002` (Goulburn splice point) drops first: −12 → −20 → −35 dBm over 15 minutes
  - `SENS-SYD-MEL-F1-OPT-003` (Albury splice point) drops 2 minutes later
  - `SENS-SYD-MEL-F1-OPT-001` (Campbelltown) stays normal → pinpoints the fault between Campbelltown and Goulburn
  - BER sensors spike after optical power drops
- **Wear-and-tear pattern (background):** `SENS-AMP-GOULBURN-VIB-001` vibration readings show a slow upward trend over days, not spiking like the fibre cut sensors. This creates a second scenario where gradual degradation is distinguishable from acute failure.

> **Note:** The actual CSV will be generated programmatically (a Python script should be created to generate realistic time-series data with these patterns). The script should go in `scripts/generate_sensor_data.py`.

---

## 5. Graph Explorer Schema Doc Updates

File: `data/scenarios/telecom-playground/data/prompts/graph_explorer/core_schema.md`

Add a new section documenting the Sensor and DutyRoster entity types with all instances, properties, and relationships. This is what the GraphExplorerAgent uses to understand what it can query.

### Add after the existing entity sections:

```markdown
## Sensor (18 instances)

Physical sensors attached to infrastructure nodes. Each sensor has a specific type,
monitors a specific entity, and has GPS coordinates for field dispatch.

| SensorId | SensorType | MonitoredEntityId | MonitoredEntityType | MountLocation | Lat/Long |
|---|---|---|---|---|---|
| SENS-SYD-MEL-F1-OPT-001 | OpticalPower | LINK-SYD-MEL-FIBRE-01 | TransportLink | Campbelltown splice | -34.065, 150.814 |
| SENS-SYD-MEL-F1-OPT-002 | OpticalPower | LINK-SYD-MEL-FIBRE-01 | TransportLink | Goulburn interchange | -34.755, 149.719 |
| SENS-SYD-MEL-F1-OPT-003 | OpticalPower | LINK-SYD-MEL-FIBRE-01 | TransportLink | North of Albury | -36.024, 146.912 |
| ... (all 18 sensors) | | | | | |

### Relationships
- `(Sensor)-[monitors]->(TransportLink|CoreRouter|AmplifierSite)` — which infrastructure this sensor observes

### Key query patterns
- "What sensors are on LINK-SYD-MEL-FIBRE-01?" → find all Sensor nodes with `monitors` edge to that link
- "Where is sensor SENS-SYD-MEL-F1-OPT-002 located?" → return Latitude, Longitude, MountLocation
- "What sensors are near Goulburn?" → filter by Latitude/Longitude proximity or MountLocation text
```

---

## 6. scenario.yaml Updates (telecom-playground)

### 6.1 Add Sensor to graph_styles

```yaml
    Sensor:          { color: "#22D3EE", size: 10, icon: "sensor" }
    DutyRoster:      { color: "#F97316", size: 14, icon: "person" }
```

### 6.2 Update telemetry_baselines

Add a new section:

```yaml
  sensor_readings:
    - metric: OpticalPower (dBm)
      normal: "-8 to -12 dBm"
      degraded: "< -20 dBm"
      critical: "< -30 dBm"
    - metric: BitErrorRate (ratio)
      normal: "< 1e-9"
      degraded: "> 1e-6"
      critical: "> 1e-3"
    - metric: Temperature (°C)
      normal: "20–45 °C"
      degraded: "> 55 °C"
      critical: "> 70 °C"
    - metric: Vibration (g)
      normal: "< 0.5 g"
      degraded: "> 1.0 g"
      critical: "> 2.0 g"
```

---

## 7. telco-noc Scenario Parity

The `telco-noc` scenario is the simpler version. Apply the same changes:

1. Create identical `DimSensor.csv` and `DimDutyRoster.csv` (or a subset)
2. Add `Latitude,Longitude` columns to `DimCoreRouter.csv` and `DimAggSwitch.csv`
3. Update its `graph_schema.yaml` with Sensor vertex + monitors edges
4. Update its `scenario.yaml` with the SensorReadings container
5. Generate `SensorReadings.csv` for its telemetry directory
6. Update its `core_schema.md`

**However** — per the requirements ("SCREW THE OTHER DEMO FLOWS"), all Phase 2–5 changes should target `telecom-playground` first. The `telco-noc` scenario gets parity at the end or in a follow-up.

---

## 8. Files to Create / Modify — Summary

| Action | File | Description |
|---|---|---|
| **CREATE** | `data/scenarios/telecom-playground/data/entities/DimSensor.csv` | 18 sensor records |
| **CREATE** | `data/scenarios/telecom-playground/data/entities/DimDutyRoster.csv` | 8 duty roster records |
| **CREATE** | `data/scenarios/telecom-playground/data/telemetry/SensorReadings.csv` | ~2000 sensor time-series readings |
| **CREATE** | `scripts/generate_sensor_data.py` | Script to generate realistic SensorReadings.csv |
| **MODIFY** | `data/scenarios/telecom-playground/data/entities/DimCoreRouter.csv` | Add Latitude,Longitude columns |
| **MODIFY** | `data/scenarios/telecom-playground/data/entities/DimAggSwitch.csv` | Add Latitude,Longitude columns |
| **MODIFY** | `data/scenarios/telecom-playground/data/entities/DimAmplifierSite.csv` | Add Latitude,Longitude columns |
| **MODIFY** | `data/scenarios/telecom-playground/graph_schema.yaml` | Add Sensor + DutyRoster vertices, monitors edges, Lat/Long properties |
| **MODIFY** | `data/scenarios/telecom-playground/scenario.yaml` | Add SensorReadings container, duty_roster data source, graph_styles, telemetry_baselines |
| **MODIFY** | `data/scenarios/telecom-playground/data/prompts/graph_explorer/core_schema.md` | Document Sensor and DutyRoster entities |

---

## 9. Validation Checklist

- [ ] `DimSensor.csv` parses correctly with `provision_cosmos.py` / graph ingest
- [ ] `DimDutyRoster.csv` loads into Cosmos DB container
- [ ] `SensorReadings.csv` ingests into Fabric Eventhouse / Cosmos DB
- [ ] Lat/Long columns on `DimCoreRouter`, `DimAggSwitch`, `DimAmplifierSite` don't break existing graph queries
- [ ] `graph_schema.yaml` validates — `generate_topology_json.py` succeeds
- [ ] `core_schema.md` accurately reflects all new entities and relationships
- [ ] Existing scenario functionality (demo flows, agent provisioning, telemetry queries) is unaffected

---

## 10. References

| Source | URL / Path |
|---|---|
| Existing graph_schema.yaml | `data/scenarios/telecom-playground/graph_schema.yaml` |
| Existing scenario.yaml | `data/scenarios/telecom-playground/scenario.yaml` |
| provision_cosmos.py (data loader) | `scripts/provision_cosmos.py` |
| generate_topology_json.py | `scripts/generate_topology_json.py` |
| Graph ingest endpoint | `graph-query-api/routers/router_ingest.py` |
| Core schema prompt | `data/scenarios/telecom-playground/data/prompts/graph_explorer/core_schema.md` |
