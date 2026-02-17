# Server Crash Recovery Runbook

## Scope
This runbook covers investigation and recovery for a server crash (kernel panic,
hardware failure, or unresponsive host) in the hello-world infrastructure.

## Symptoms
- `SERVER_DOWN` alerts with CPU/Memory/Disk all at 0%
- Hosted applications reporting `APP_UNREACHABLE`
- Downstream dependency failures and connection drops

## Investigation Steps

### 1. Confirm Server Status
- Check IPMI/BMC console for hardware errors
- Verify network connectivity to management interface
- Review kernel logs (`/var/log/kern.log`) if accessible

### 2. Assess Blast Radius
- Identify all applications hosted on the failed server
- Check database connection pools for dropped connections
- Verify downstream workers and background jobs

### 3. Immediate Mitigation
- If hardware failure: initiate failover to standby server
- If kernel panic: attempt remote reboot via IPMI
- Notify dependent application owners

### 4. Recovery
1. Reboot server (hard reset if soft reboot fails)
2. Verify OS boot and service startup
3. Confirm application health checks pass
4. Monitor database connection pool recovery
5. Clear any queued retry backlogs on workers

### 5. Post-Incident
- Collect crash dump for root cause analysis
- Update monitoring thresholds if early warning was missed
- Schedule hardware diagnostics if recurrent
