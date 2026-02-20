# Project: Azure Autonomous Network Demo — Conversation Revamp

## Objective

Redesign the end-to-end conversational flow so that every orchestrator step, sub-agent call, and API interaction is **streamed live to the UI** in a clear, hierarchical structure, and sessions are managed efficiently with robust persistence.

### Target User Experience

1. **User submits a message** — UI immediately renders a thought bubble ("Orchestrator initializing").
2. **Orchestrator reasoning step** — The orchestrator produces a thought justification for its next action. UI renders this as a collapsible top-level thought bubble.
3. **Sub-agent invocation** — Orchestrator calls a sub-agent. UI renders a collapsible bubble nested under the orchestrator thought, showing: agent name, query sent, timestamp.
4. **Sub-agent internal calls** — The sub-agent's own API queries and responses are streamed live and rendered indented under the sub-agent bubble (tree structure, collapsible at each level).
5. **Iteration** — The orchestrator proceeds to additional agent calls, actions, or tools. Each follows the same nested rendering pattern.
6. **Final diagnosis** — The orchestrator's conclusion appears. The user can send another message; previous prompt + diagnosis are carried forward as conversational context.

Every step above must be **streamed** to provide continuous visual feedback — no waiting for a full response before rendering begins.

### Session Management Requirements

- **Async sessions** — Starting a "New Scenario" launches a new conversation flow without blocking the current one. The prior session appears in the sessions sidebar.
- **In-memory caching** — Each active session is held in memory first for fast access.
- **Manual save** — Sessions are explicitly saved by the user (e.g., a button on the session card). No auto-persist on every message.
- **Chunked persistence** — When saving, the session is split into chunks, sent asynchronously to Cosmos DB, and persisted. Retrieval reconstructs the session from chunks.
- **Graceful degradation** — A session must render even if some chunks are missing. Partial data should never crash the UI or block loading.

### Success Criteria

- The orchestrator → sub-agent → API call hierarchy is visually clear and collapsible at every level.
- All reasoning steps and API responses stream to the UI in real time.
- Multiple sessions can run concurrently without interference.
- Session save/load round-trips through Cosmos DB without data loss.
- The UI remains responsive and renders partial sessions gracefully.

## General Instructions

You are a senior principal software engineer. No nonsense. Outcome focused. Obsessed with excellence.
Be extremely comprehensive, careful, thorough, and detailed. Maximize the
possibility of one-shot success with every refactor. Keep your language concise
and direct — no filler, focused entirely on outcomes.

## Task Index

| Task | File | Output |
|------|------|--------|
| 01 — Feasibility Validation | `strategy/task_01_validation.md` | `planning/task_01_validation_plan.md` |
| 02 — Implementation Plan | — | `planning/task_02_implementation_plan.md` |
