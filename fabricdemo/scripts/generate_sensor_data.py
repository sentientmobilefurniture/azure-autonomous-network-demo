#!/usr/bin/env python3
"""
generate_sensor_data.py — Generate realistic SensorReadings.csv

Produces ~2000 rows of time-series sensor data covering a 48-hour window
(2026-02-04 to 2026-02-06) with two distinct patterns:

1. WEAR & TEAR (gradual degradation) — Goulburn sensors degrade slowly
   over 72 hours, reaching alert thresholds around Feb 6 09:15.
2. FIBRE CUT (acute failure) — Sensors on LINK-SYD-MEL-FIBRE-01 near
   Goulburn drop to critical in seconds around Feb 6 14:31.

Usage:
    python scripts/generate_sensor_data.py

Output:
    data/scenarios/telecom-playground/data/telemetry/SensorReadings.csv
"""

import csv
import math
import os
import random
from datetime import datetime, timedelta, timezone

random.seed(42)

# ─── Output path ────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_PATH = os.path.join(
    PROJECT_ROOT,
    "data", "scenarios", "telecom-playground", "data", "telemetry",
    "SensorReadings.csv",
)

# ─── Time window ────────────────────────────────────────────────────
T_START = datetime(2026, 2, 4, 0, 0, 0, tzinfo=timezone.utc)
T_END = datetime(2026, 2, 6, 18, 0, 0, tzinfo=timezone.utc)
INCIDENT_WEAR = datetime(2026, 2, 6, 9, 15, 0, tzinfo=timezone.utc)
INCIDENT_CUT = datetime(2026, 2, 6, 14, 31, 0, tzinfo=timezone.utc)

# ─── Sensor definitions ────────────────────────────────────────────
SENSORS = {
    # Optical power sensors on LINK-SYD-MEL-FIBRE-01
    "SENS-SYD-MEL-F1-OPT-001": {"type": "OpticalPower", "unit": "dBm", "baseline": -10.2, "location": "Campbelltown"},
    "SENS-SYD-MEL-F1-OPT-002": {"type": "OpticalPower", "unit": "dBm", "baseline": -11.8, "location": "Goulburn"},
    "SENS-SYD-MEL-F1-OPT-003": {"type": "OpticalPower", "unit": "dBm", "baseline": -11.5, "location": "Albury"},
    # BER sensors on LINK-SYD-MEL-FIBRE-01
    "SENS-SYD-MEL-F1-BER-001": {"type": "BitErrorRate", "unit": "ratio", "baseline": 2e-12, "location": "SYD head-end"},
    "SENS-SYD-MEL-F1-BER-002": {"type": "BitErrorRate", "unit": "ratio", "baseline": 3e-12, "location": "MEL tail-end"},
    # Optical power on FIBRE-02
    "SENS-SYD-MEL-F2-OPT-001": {"type": "OpticalPower", "unit": "dBm", "baseline": -10.0, "location": "Campbelltown F2"},
    "SENS-SYD-MEL-F2-OPT-002": {"type": "OpticalPower", "unit": "dBm", "baseline": -10.5, "location": "Goulburn F2"},
    # Sydney-Brisbane sensors
    "SENS-SYD-BNE-F1-OPT-001": {"type": "OpticalPower", "unit": "dBm", "baseline": -10.8, "location": "Gosford"},
    "SENS-SYD-BNE-F1-OPT-002": {"type": "OpticalPower", "unit": "dBm", "baseline": -11.2, "location": "Coffs Harbour"},
    # Melbourne-Brisbane sensors
    "SENS-MEL-BNE-F1-OPT-001": {"type": "OpticalPower", "unit": "dBm", "baseline": -10.5, "location": "Sale"},
    "SENS-MEL-BNE-F1-OPT-002": {"type": "OpticalPower", "unit": "dBm", "baseline": -11.0, "location": "Grafton"},
    # Temperature sensors on routers
    "SENS-CORE-SYD-01-TEMP-001": {"type": "Temperature", "unit": "°C", "baseline": 38.5, "location": "SYD router"},
    "SENS-CORE-MEL-01-TEMP-001": {"type": "Temperature", "unit": "°C", "baseline": 37.2, "location": "MEL router"},
    "SENS-CORE-BNE-01-TEMP-001": {"type": "Temperature", "unit": "°C", "baseline": 39.1, "location": "BNE router"},
    # CPU sensors on routers
    "SENS-CORE-SYD-01-CPU-001": {"type": "CPULoad", "unit": "%", "baseline": 42.0, "location": "SYD router"},
    "SENS-CORE-MEL-01-CPU-001": {"type": "CPULoad", "unit": "%", "baseline": 38.0, "location": "MEL router"},
    # Vibration sensors on amplifier sites
    "SENS-AMP-GOULBURN-VIB-001": {"type": "Vibration", "unit": "g", "baseline": 0.15, "location": "Goulburn amp"},
    "SENS-AMP-ALBURY-VIB-001": {"type": "Vibration", "unit": "g", "baseline": 0.12, "location": "Albury amp"},
}

# Thresholds for status determination
THRESHOLDS = {
    "OpticalPower": {"warning": -20.0, "critical": -30.0, "direction": "below"},
    "BitErrorRate": {"warning": 1e-6, "critical": 1e-3, "direction": "above"},
    "Temperature": {"warning": 55.0, "critical": 70.0, "direction": "above"},
    "CPULoad": {"warning": 85.0, "critical": 95.0, "direction": "above"},
    "Vibration": {"warning": 1.0, "critical": 2.0, "direction": "above"},
}


def get_status(sensor_type: str, value: float) -> str:
    """Determine NORMAL/WARNING/CRITICAL based on thresholds."""
    t = THRESHOLDS[sensor_type]
    if t["direction"] == "below":
        if value < t["critical"]:
            return "CRITICAL"
        elif value < t["warning"]:
            return "WARNING"
        return "NORMAL"
    else:
        if value > t["critical"]:
            return "CRITICAL"
        elif value > t["warning"]:
            return "WARNING"
        return "NORMAL"


def noise(scale: float = 0.1) -> float:
    """Small random noise."""
    return random.gauss(0, scale)


def generate_baseline_reading(sensor_id: str, timestamp: datetime) -> float:
    """Generate a normal baseline reading with minor noise."""
    s = SENSORS[sensor_id]
    base = s["baseline"]
    stype = s["type"]

    if stype == "OpticalPower":
        return base + noise(0.3)
    elif stype == "BitErrorRate":
        return max(1e-13, base * (1 + noise(0.2)))
    elif stype == "Temperature":
        # Small diurnal variation
        hour = timestamp.hour
        diurnal = 2.0 * math.sin(2 * math.pi * (hour - 6) / 24)
        return base + diurnal + noise(0.5)
    elif stype == "CPULoad":
        # Slight variation with time
        return max(10, min(75, base + noise(3.0)))
    elif stype == "Vibration":
        return max(0.01, base + noise(0.02))
    return base


def generate_wear_tear_reading(sensor_id: str, timestamp: datetime) -> float:
    """
    Generate readings that show gradual degradation for the wear-and-tear scenario.
    Degradation starts from Feb 4 00:00 and accelerates toward Feb 6 09:15.
    """
    s = SENSORS[sensor_id]
    base = s["baseline"]
    stype = s["type"]

    # Hours since start of degradation window
    hours_elapsed = (timestamp - T_START).total_seconds() / 3600
    total_hours = (INCIDENT_WEAR - T_START).total_seconds() / 3600
    progress = min(1.0, max(0, hours_elapsed / total_hours))
    # Exponential acceleration — slow start, fast end
    degradation_factor = progress ** 2.5

    # Goulburn optical sensor — primary degradation target
    if sensor_id == "SENS-SYD-MEL-F1-OPT-002":
        # -11.8 → -19.6 over 57 hours
        return base - (7.8 * degradation_factor) + noise(0.2)

    # Albury optical sensor — secondary degradation (less severe)
    elif sensor_id == "SENS-SYD-MEL-F1-OPT-003":
        return base - (6.4 * degradation_factor) + noise(0.2)

    # BER sensors — degrade as optical power drops
    elif sensor_id == "SENS-SYD-MEL-F1-BER-001":
        # 2e-12 → 9e-7
        ber_increase = (9e-7 - base) * degradation_factor
        return max(1e-13, base + ber_increase + base * noise(0.15))

    elif sensor_id == "SENS-SYD-MEL-F1-BER-002":
        ber_increase = (5e-7 - base) * degradation_factor
        return max(1e-13, base + ber_increase + base * noise(0.15))

    # Goulburn vibration — slow upward trend
    elif sensor_id == "SENS-AMP-GOULBURN-VIB-001":
        # 0.15 → 0.95
        return base + (0.80 * degradation_factor) + noise(0.02)

    # Campbelltown optical — stays normal (proves fault is between C'town and Goulburn)
    elif sensor_id == "SENS-SYD-MEL-F1-OPT-001":
        return base + noise(0.3)

    # All other sensors — normal readings
    return generate_baseline_reading(sensor_id, timestamp)


def generate_fibre_cut_reading(sensor_id: str, timestamp: datetime) -> float:
    """
    Generate readings for the fibre cut scenario.
    Before cut time: wear-and-tear values (already degraded).
    After cut time:  sudden cliff-edge to critical.
    """
    cut_time = INCIDENT_CUT
    seconds_after = (timestamp - cut_time).total_seconds()

    if seconds_after < 0:
        # Before the cut — use the wear-and-tear values
        return generate_wear_tear_reading(sensor_id, timestamp)

    s = SENSORS[sensor_id]
    stype = s["type"]

    # Campbelltown stays normal (upstream of cut)
    if sensor_id == "SENS-SYD-MEL-F1-OPT-001":
        return s["baseline"] + noise(0.3)

    # Goulburn optical — drops to dead
    elif sensor_id == "SENS-SYD-MEL-F1-OPT-002":
        if seconds_after < 60:
            return -19.6 - (15.4 * (seconds_after / 60)) + noise(0.5)  # -19.6 → -35
        return -35.0 + noise(0.5)

    # Albury optical — drops 2 minutes after Goulburn
    elif sensor_id == "SENS-SYD-MEL-F1-OPT-003":
        if seconds_after < 120:
            # Still at pre-cut degraded value for first 2 minutes
            return generate_wear_tear_reading(sensor_id, timestamp)
        elif seconds_after < 180:
            progress = (seconds_after - 120) / 60
            return -17.9 - (17.1 * progress) + noise(0.5)  # -17.9 → -35
        return -35.0 + noise(0.5)

    # BER sensors spike to ~1 (total failure)
    elif sensor_id in ("SENS-SYD-MEL-F1-BER-001", "SENS-SYD-MEL-F1-BER-002"):
        if seconds_after < 30:
            progress = seconds_after / 30
            return 9e-7 + (0.1 - 9e-7) * progress
        return min(1.0, 0.1 + noise(0.01))

    # Goulburn vibration — spikes during cut event
    elif sensor_id == "SENS-AMP-GOULBURN-VIB-001":
        if seconds_after < 300:  # 5 minutes of high vibration
            return 2.5 + noise(0.3)
        return 0.95 + noise(0.05)  # Returns to elevated baseline

    # Other sensors — normal
    return generate_baseline_reading(sensor_id, timestamp)


def format_value(sensor_type: str, value: float) -> str:
    """Format the value appropriately for the sensor type."""
    if sensor_type == "BitErrorRate":
        return f"{value:.2e}"
    elif sensor_type == "OpticalPower":
        return f"{value:.1f}"
    elif sensor_type == "Temperature":
        return f"{value:.1f}"
    elif sensor_type == "CPULoad":
        return f"{value:.1f}"
    elif sensor_type == "Vibration":
        return f"{value:.2f}"
    return f"{value:.4f}"


def main():
    rows = []
    reading_counter = 0

    # ── Interval strategy ────────────────────────────────────────
    # Coarse interval (30 min) for baseline periods
    # Medium interval (5 min) during degradation ramp-up
    # Fine interval (1 min) near incidents
    # Very fine (10 sec) during actual incident windows

    for sensor_id, sensor_info in SENSORS.items():
        stype = sensor_info["type"]
        unit = sensor_info["unit"]

        # Generate time points with adaptive resolution
        t = T_START
        while t <= T_END:
            reading_counter += 1
            reading_id = f"RD-{t.strftime('%Y%m%d')}-{reading_counter:06d}"

            # Determine which generator to use based on time
            if t >= INCIDENT_CUT - timedelta(minutes=5):
                value = generate_fibre_cut_reading(sensor_id, t)
            elif t >= T_START:
                value = generate_wear_tear_reading(sensor_id, t)
            else:
                value = generate_baseline_reading(sensor_id, t)

            status = get_status(stype, value)
            formatted_value = format_value(stype, value)

            rows.append({
                "ReadingId": reading_id,
                "Timestamp": t.isoformat(),
                "SensorId": sensor_id,
                "SensorType": stype,
                "Value": formatted_value,
                "Unit": unit,
                "Status": status,
            })

            # Adaptive time step
            minutes_to_wear = (INCIDENT_WEAR - t).total_seconds() / 60
            minutes_to_cut = (INCIDENT_CUT - t).total_seconds() / 60

            if -5 <= minutes_to_cut <= 15:
                # Very fine resolution during fibre cut window
                step = timedelta(seconds=10)
            elif -30 <= minutes_to_wear <= 10:
                # Fine resolution near wear-and-tear incident
                step = timedelta(minutes=1)
            elif abs(minutes_to_wear) < 360 or abs(minutes_to_cut) < 360:
                # Medium resolution within 6 hours of incidents
                step = timedelta(minutes=5)
            else:
                # Coarse resolution for baseline periods
                step = timedelta(minutes=30)

            t += step

    # Sort by timestamp
    rows.sort(key=lambda r: r["Timestamp"])

    # Write output
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["ReadingId", "Timestamp", "SensorId", "SensorType",
                         "Value", "Unit", "Status"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} sensor readings → {OUTPUT_PATH}")

    # Summary stats
    statuses = {}
    for r in rows:
        statuses[r["Status"]] = statuses.get(r["Status"], 0) + 1
    for status, count in sorted(statuses.items()):
        print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
