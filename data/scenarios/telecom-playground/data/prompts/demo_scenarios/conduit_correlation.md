# Dual-Fibre Failure — Conduit Shared Risk Investigation

You are the NOC AI Orchestrator. An unusual situation has occurred:

**Incident:** BOTH LINK-SYD-MEL-FIBRE-01 and LINK-SYD-MEL-FIBRE-02 have gone down simultaneously.
**This should not happen** — these are supposed to be redundant/diverse paths.

Your task:
1. Confirm both links are truly down (check telemetry: optical power, BER, utilisation)
2. **Investigate WHY both failed:** Do these links share a physical conduit? Query the PhysicalConduit mapping.
3. If they share a conduit: explain the shared-risk group to the operator. This was NOT true redundancy.
4. Assess the blast radius: what services are affected now that BOTH primary AND secondary paths are down?
5. Find the tertiary path (SYD-MEL-VIA-BNE) — is it available? What is its current utilisation and latency?
6. Look for historical precedent — has this dual-failure happened before? Reference INC-2025-11-22-0055.
7. Recommend: immediate reroute to tertiary + long-term recommendation for conduit route diversity.
