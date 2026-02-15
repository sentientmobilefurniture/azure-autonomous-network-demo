# Cooling System Failure — Emergency Response Runbook

## Trigger Conditions
- COOLING_FAILURE alert from any AvailabilityZone
- TemperatureCelsius > 35°C on multiple racks in the same AZ

## Immediate Actions (First 5 minutes)

1. **Confirm cooling failure** — check CRAC unit status in DCIM system
2. **Assess blast radius** — query graph for all Racks, Hosts, and VMs in the affected AZ:
   ```
   g.V().has('AvailabilityZone','AZId','AZ-US-EAST-A').out('has_rack').out('hosts_server').out('runs')
   ```
3. **Check HostMetrics** — identify hosts approaching thermal threshold (> 35°C)
4. **Initiate VM live migration** for critical Tier-0 services to healthy AZ

## Escalation Matrix

| Temperature | Action |
|-------------|--------|
| 32–35°C | WARNING — increase monitoring frequency to 1-min samples |
| 35–45°C | MAJOR — begin live migration of non-essential VMs |
| 45–70°C | CRITICAL — initiate orderly host shutdown sequence |
| > 70°C | EMERGENCY — hosts will auto-shutdown via thermal protection |

## Recovery Steps

1. Deploy portable cooling units (pre-staged at each facility)
2. Repair or replace failed CRAC unit
3. Verify ambient temperature below 28°C before powering on hosts
4. Power on hosts in dependency order (DB → API → Web)
5. Verify VM health and service availability
6. Monitor for 2 hours for thermal stability
