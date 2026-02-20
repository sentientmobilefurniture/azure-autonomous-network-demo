# Task 00: Understanding Current Conversation Handling

> See [phase README](../README.md) for project objective and success criteria.

## Goal

Produce a comprehensive map of how conversations are currently handled in the
azure-autonomous-network-demo codebase — covering API endpoints, data models,
storage, session management, agent interactions, and frontend integration.

## Desired Outcome

A single execution document (`execution/task_00_understanding_execution_log.md`)
that contains:

1. **Conversation Data Model** — all models/schemas related to conversations,
   messages, sessions, and threads (file paths, field names, relationships).
2. **API Surface** — every endpoint that creates, reads, updates, or participates
   in a conversation (route, method, handler, request/response shape).
3. **Storage Layer** — how and where conversations are persisted (Cosmos DB
   collections, partition keys, TTLs, indexing).
4. **Session / Thread Management** — how sessions are created, resumed, and
   expired; relationship between sessions, threads, and agent runs.
5. **Agent Interaction Flow** — how user messages reach agents, how agent
   responses flow back, streaming vs. polling, tool-call lifecycle.
6. **Frontend Integration** — how the React/TypeScript frontend initiates and
   renders conversations (components, hooks, API calls, WebSocket usage).
7. **Gaps & Pain Points** — any obvious issues, inconsistencies, or missing
   capabilities observed during the analysis.

## Prerequisites

- Access to the full `azure-autonomous-network-demo` codebase.

## Steps

1. Read all relevant source files in `graph-query-api/`, `api/app/`, and
   `frontend/src/` to trace the conversation flow end-to-end.
2. Document findings in the execution log following the structure above.

## Completion Criteria

- The execution document is comprehensive enough that a new engineer could
  understand the full conversation lifecycle without reading the source code.
- Every claim is backed by a file path and line number reference.
