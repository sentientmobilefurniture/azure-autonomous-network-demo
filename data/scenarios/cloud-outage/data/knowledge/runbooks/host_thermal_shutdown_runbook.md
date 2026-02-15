# Host Thermal Shutdown — Recovery Runbook

## Trigger Conditions
- THERMAL_SHUTDOWN alert from any Host
- Host CPUUtilPct drops to 0% with TemperatureCelsius > 85°C

## Immediate Actions

1. **Identify the affected host** and its rack location
2. **Check what VMs were running** on the host:
   ```
   g.V().has('Host','HostId','<HOST_ID>').out('runs').valueMap(true)
   ```
3. **Check which services are impacted**:
   ```
   g.V().has('Host','HostId','<HOST_ID>').out('runs').out('serves').valueMap(true)
   ```
4. **Verify failover** — check load balancer health for affected services

## VM Recovery Priority

| Service Tier | Recovery Priority | Action |
|-------------|-------------------|--------|
| Tier-0 (DB, Auth, Monitoring) | Immediate | Live migrate to AZ-B if not already |  
| Tier-1 (Web, API, Cache, CDN) | High | Failover via load balancer |
| Tier-2 (ML, Batch) | Low | Wait for host recovery |

## Host Power-On Procedure

1. Verify rack ambient temperature < 28°C
2. Power on via IPMI/BMC
3. Wait for POST and OS boot (typically 3–5 minutes)
4. Verify host agent check-in and resource reporting
5. Allow VM scheduler to re-place workloads
