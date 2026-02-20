# Task 01: Current User Experience — Step-by-Step

> See [phase README](../README.md) for project objective and success criteria.

## Goal

Produce an exhaustive, chronological walkthrough of the user experience for
every conversation interaction the system supports — from first page load
through multi-turn follow-ups, session switching, cancellation, error states,
and session history browsing. Every click, visual transition, loading state,
and latency gap must be documented.

## Desired Outcome

A single execution document (`execution/task_01_current_user_experience_execution_log.md`)
that contains:

1. **First Load Experience** — what the user sees on initial page load: layout,
   empty states, sidebar loading, scenario config fetch, graph panel, terminal.

2. **Starting a New Investigation** — step-by-step from typing/selecting an
   alert through submission: optimistic UI, placeholder appearance, SSE
   connection, thinking indicators, incremental step cards, reasoning blocks,
   action cards, diagnosis block, run meta footer. Include exact visual
   states and transitions.

3. **Live Investigation Progress** — what the user sees at each SSE event
   type: `step_thinking`, `step_started`, `step_response`, `step_complete`,
   `message`, `run_complete`, `error`, `action_executed`. Map each event to
   the exact UI change it triggers.

4. **Multi-Turn Follow-Up** — the full UX of sending a follow-up message:
   input state, placeholder injection, SSE reconnection with `since` offset,
   how prior turns remain visible, how new steps append below.

5. **Session Sidebar Interactions** — viewing past sessions, switching between
   sessions, session card states (pending/in_progress/completed/failed/cancelled),
   delete flow (confirmation pattern), new session button, refresh.

6. **Cancellation Experience** — what happens when the user cancels: button
   state, "cancelling" feedback, delay until current agent call finishes,
   final state.

7. **Error States** — every error path the user can encounter: orchestrator
   failure, retry exhaustion, capacity errors, stuck investigation timeout,
   SSE disconnect, session not found.

8. **Edge Cases & Micro-Interactions** — long alert text collapse/expand,
   step card expand/collapse, reasoning toggle, diagnosis copy button,
   examples dropdown, Ctrl+Enter shortcut, textarea auto-resize, scroll
   behavior (auto-scroll to bottom, scroll-away detection).

9. **Latency & Perceived Performance** — where the user waits with no
   feedback, where loading indicators appear, what happens during the gap
   between submission and first SSE event, perceived responsiveness.

10. **UX Friction Points** — every moment where the experience is confusing,
    slow, unclear, or broken. Specific observations, not opinions.

## Prerequisites

- Completed [task_00_understanding](task_00_understanding.md) execution log
  (provides the technical substrate for this UX analysis).

## Steps

1. Trace every user-facing code path in `frontend/src/` — components, hooks,
   types — mapping UI state transitions to backend events.
2. Document each interaction chronologically with component names, state
   changes, and visual descriptions.

## Completion Criteria

- A product designer or QA engineer could use the document to reproduce every
  interaction state without access to the running application.
- Every observation references a specific component/hook and line number.
- UX friction points are concrete and actionable (not "could be better").
