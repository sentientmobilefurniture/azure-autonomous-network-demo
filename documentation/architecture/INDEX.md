# Architecture — AI Incident Investigator

> **Last updated:** 2026-02-17 — reflects V10 config-driven architecture
> (V10generalflow.md phases 0-13), including: config-driven N-agent
> provisioning from `scenario.yaml`, `DocumentStore` Protocol + registry,
> `GraphBackend` registry, OpenAPI spec templates, `_normalize_manifest()`
> v1→v2 backward compatibility, config store + validator, resource graph
> API, frontend `EmptyState` + `ResourceVisualizer`, and all prior work
> (V8 refactor, scenario management, V9.5 fixes, V10 interaction history).
>
> This document has been split into focused sections for targeted referencing.
> See the individual files in [`architecture/`](architecture/) below.

---

## Table of Contents

| # | Section | File | Description |
|---|---------|------|-------------|
| 1 | [System Overview](architecture/overview.md) | `overview.md` | Platform description, available scenarios |
| 2 | [Container Architecture](architecture/container-architecture.md) | `container-architecture.md` | Unified container (nginx + supervisord), request flow |
| 3 | [Project Structure](architecture/project-structure.md) | `project-structure.md` | Full annotated file tree |
| 4 | [API Surface](architecture/api-surface.md) | `api-surface.md` | All endpoints for both :8000 and :8100 services |
| 5 | [Data Flow](architecture/data-flow.md) | `data-flow.md` | Upload, provisioning, and investigation flows |
| 6 | [SSE Protocols](architecture/sse-protocols.md) | `sse-protocols.md` | SSE event formats for investigation, upload, provisioning, logs |
| 7 | [Key Components](architecture/key-components.md) | `key-components.md` | Detailed docs for all backend modules and routers |
| 8 | [Frontend Architecture](architecture/frontend-architecture.md) | `frontend-architecture.md` | Provider tree, hooks, API calls, graph viewer, patterns |
| 9 | [Data Schema](architecture/data-schema.md) | `data-schema.md` | Scenario data packs, scenario.yaml, graph_schema.yaml, tarballs |
| 10 | [Infrastructure](architecture/infrastructure.md) | `infrastructure.md` | Bicep modules, Dockerfile, container build, RBAC roles |
| 11 | [Deployment](architecture/deployment.md) | `deployment.md` | deploy.sh, azd hooks, post-deployment, teardown |
| 12 | [Error Resilience](architecture/error-resilience.md) | `error-resilience.md` | 4-layer error handling strategy |
| 13 | [Critical Patterns](architecture/critical-patterns.md) | `critical-patterns.md` | 23 lessons learned (async, Cosmos, VNet, OpenAPI, RBAC, etc.) |
| 14 | [Known Issues](architecture/known-issues.md) | `known-issues.md` | Bugs, gotchas, and workarounds |
| 15 | [Configuration](architecture/configuration.md) | `configuration.md` | All env vars reference + local development commands |
| 16 | [Troubleshooting](architecture/troubleshooting.md) | `troubleshooting.md` | Problem → file mapping table |
| 17 | [Scenario Management](architecture/scenario-management.md) | `scenario-management.md` | Scenario CRUD, architecture, key files, validation |
| 18 | [Backlog & Future](architecture/backlog-and-future.md) | `backlog-and-future.md` | QOL backlog, Fabric integration, SDK versions, related docs |
