# Firmware Advisory Correlation — OSPF Flap Investigation

You are the NOC AI Orchestrator. A NOC operator has noticed a pattern:

**Observation:** CORE-SYD-01 and CORE-MEL-01 have been experiencing intermittent OSPF adjacency flaps during peak BGP reconvergence events. The flaps are not associated with any physical link failures — all transport links show healthy optical power and BER.

The operator suspects a software bug. Your task:
1. Check what firmware versions CORE-SYD-01 and CORE-MEL-01 are running (FirmwareVersion property)
2. Query the Advisory entities — are there any known vendor advisories affecting this firmware version?
3. If an advisory matches: explain the bug, its severity, and the recommended fix version
4. Assess the operational risk: which services and SLA policies are exposed through these routers?
5. Check if CORE-BNE-01 (the third backbone router) is also affected by any advisories
6. Look up the firmware upgrade procedure runbook
7. Recommend: upgrade schedule, considering SLA windows and traffic rerouting requirements
