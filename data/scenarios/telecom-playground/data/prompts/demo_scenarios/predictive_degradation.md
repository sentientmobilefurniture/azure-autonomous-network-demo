# Predictive Degradation — Optical Amplifier Aging

You are the NOC AI Orchestrator. A gradual anomaly has been detected:

**Observation:** Optical power on LINK-MEL-BNE-FIBRE-01 has been slowly dropping over the past 2 weeks:
- 14 days ago: -3 dBm (normal)
- 7 days ago: -8 dBm (still within spec)
- 3 days ago: -15 dBm (degraded)
- Today: -20 dBm (approaching critical threshold at -30 dBm)

This is NOT a sudden fibre cut — it's a gradual degradation pattern consistent with amplifier aging.

Your task:
1. Confirm the degradation trend in LinkTelemetry data for this link
2. Identify which AmplifierSites service this link — query the amplifies relationship
3. Check LastCalibration dates for these amplifiers — are any overdue?
4. Calculate the degradation rate and predict when the link will hit the critical threshold (-30 dBm)
5. Assess the impact if this link fails: what services depend on it? What paths route through it?
6. Look up the amplifier maintenance runbook for the recommended procedure
7. Recommend: proactive maintenance before failure occurs, with priority based on predicted time-to-failure
