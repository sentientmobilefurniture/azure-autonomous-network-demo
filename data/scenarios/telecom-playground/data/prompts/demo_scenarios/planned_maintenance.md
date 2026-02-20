# Planned Maintenance Risk Assessment

You are the NOC AI Orchestrator. A maintenance window has been scheduled:

**Target:** LINK-SYD-MEL-FIBRE-01 (fibre splice work)
**Window:** Saturday 02:00–08:00 UTC
**Requestor:** Network Engineering team

Your task:
1. Map ALL services, customers, and SLA policies that depend on this link (or on MPLS paths that traverse it)
2. Verify that backup paths have sufficient capacity to absorb rerouted traffic during the maintenance window
3. Check for any conflicting maintenance events or known risks on backup paths
4. Review historical incidents on this corridor — has anything gone wrong during previous maintenance?
5. Identify any shared physical infrastructure risks (conduit co-routing) that could compound the exposure
6. Produce a risk assessment with: affected services, SLA exposure, backup path readiness, and recommended safeguards
