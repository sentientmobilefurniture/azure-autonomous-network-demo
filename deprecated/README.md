# Deprecated Scripts

These scripts have been superseded by the V8 Data Management Plane.
They are preserved here for reference but are no longer part of the active
deployment pipeline.

| Script | Replaced By | When |
|--------|-------------|------|
| `scripts/create_runbook_indexer.py` | UI scenario upload → `router_ingest.py` (Phase 2D) | V8 |
| `scripts/create_tickets_indexer.py` | UI scenario upload → `router_ingest.py` (Phase 2D) | V8 |
| `scripts/_indexer_common.py` | `graph-query-api/services/search_indexer.py` (Phase 2D) | V8 |
| `scripts/cosmos/provision_cosmos_gremlin.py` | UI scenario upload → `router_ingest.py` (Phase 1) | V8 |
| `scripts/cosmos/provision_cosmos_telemetry.py` | UI scenario upload → `router_ingest.py` (Phase 1) | V8 |
| `data/shared_prompts/` | Cosmos DB `platform-config.prompts` container (Phase 2B) | V8 |
