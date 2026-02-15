# Load Balancer Failover — Operations Guide

## Automatic Failover Behaviour

Load balancers detect unhealthy backends via health checks:
- **Application LBs** (LB-USE-WEB, LB-USE-API): HTTP health checks every 10s,
  3 consecutive failures = mark unhealthy
- **Network LBs** (LB-USE-DB): TCP health checks every 5s,
  2 consecutive failures = mark unhealthy
- **DNS LBs** (LB-GLOBAL): region-level health via synthetic probes every 30s

## When Automatic Failover Triggers

1. LB removes unhealthy backend from rotation
2. Traffic routes to remaining healthy backends
3. If all backends in an AZ are unhealthy, cross-AZ failover activates
4. FAILOVER_TRIGGERED alert fires

## Manual Intervention Scenarios

- **All backends unhealthy**: Check if issue is LB-side (certificate, config)
  or backend-side (host/VM down)
- **Uneven load after failover**: Manually adjust backend weights
- **Database failover**: Promote read replica to primary, update connection
  strings if not using DNS-based service discovery

## Monitoring During Failover

Track these metrics for 30 minutes post-failover:
- Backend response time (P50, P95, P99)
- Error rate (5xx)
- Active connection count on failover targets
- CPU/Memory on failover-target hosts (watch for overload)
