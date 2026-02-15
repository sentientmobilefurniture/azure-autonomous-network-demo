# VM Live Migration — Procedure Guide

## When to Use
- Host approaching thermal shutdown
- Planned host maintenance
- Load rebalancing across availability zones

## Pre-Migration Checks

1. **Target host capacity** — verify sufficient CPU, memory, and disk
2. **Network connectivity** — target host must be in same or peered VNet
3. **Storage** — shared storage or replication must be in place
4. **Service dependencies** — check if VM's service has DB connections that
   need re-establishing

## Migration Steps

1. Notify the service owner (automated via Operations channel)
2. Initiate live migration via hypervisor API
3. Monitor migration progress — typical duration: 30–120 seconds
4. Verify VM health checks pass on target host
5. Update load balancer backend pool if needed
6. Confirm service metrics return to baseline

## Rollback

If migration fails at any step:
1. Keep VM running on original host (if still available)
2. Escalate to infrastructure team for manual intervention
3. If original host is down, cold-start VM on target host from last snapshot
