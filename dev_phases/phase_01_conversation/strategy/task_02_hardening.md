# Task 02: Conversation Hardening — Bug & Issue Inventory

> See [phase README](../README.md) for project objective and success criteria.

## Goal

Produce a comprehensive, prioritized inventory of every bug, inefficiency,
fragility, and potential failure in the conversational process — spanning
backend orchestration, session management, SSE transport, frontend state
handling, and user-facing error paths. Each issue must be concrete, traceable
to code, and actionable.

## Desired Outcome

A single execution document (`execution/task_02_hardening_execution_log.md`)
that contains a categorized issue list. Each issue must include:

- **ID**: `H-<category>-<number>` (e.g., `H-BUG-01`, `H-FRAG-03`)
- **Category**: BUG (confirmed defect), FRAGILITY (works but brittle),
  INEFFICIENCY (unnecessary cost/duplication), ERROR-PATH (unhandled or
  poorly handled failure), UX-GAP (user-facing quality issue)
- **Severity**: critical / high / medium / low
- **Location**: file path + line number(s)
- **Description**: what is wrong, in one sentence
- **Impact**: what breaks, what the user experiences, or what debt accumulates
- **Reproduction / Evidence**: how to trigger it, or code evidence
- **Suggested Fix**: concrete fix direction (not a vague recommendation)

### Categories to Cover

1. **Backend Bugs** — logic errors, race conditions, data corruption, type
   mismatches in `orchestrator.py`, `session_manager.py`, `sessions.py`,
   `routers/sessions.py`, `dispatch.py`.

2. **Code Duplication / Inefficiency** — duplicated SSEEventHandler classes,
   repeated parsing logic, unnecessary copies, O(n) operations that could
   be O(1).

3. **Session Lifecycle Fragilities** — in-memory loss on restart, idle timeout
   single-instance limitation, fire-and-forget persistence failures, cancel
   event race conditions, missing state transitions.

4. **SSE Transport Issues** — silent disconnects, no reconnection, no
   client-side timeout, heartbeat gaps, event ordering assumptions.

5. **Error Handling Gaps** — unhandled exceptions, missing `.ok` checks on
   fetch calls, swallowed errors, error messages that don't reach the user,
   malformed data paths.

6. **Frontend State Issues** — stale state, missing loading indicators,
   lost expand/collapse state on session switch, race conditions in
   concurrent state updates.

7. **Data Integrity** — sessions and interactions sharing a container with no
   discriminator, unbounded event_log growth, missing TTL, missing validation.

8. **Conversation Model Limitations** — issues that will cause problems as
   the system scales or adds features (not style preferences — structural
   problems only).

## Prerequisites

- Completed [task_00_understanding](task_00_understanding.md) execution log
- Completed [task_01_current_user_experience](task_01_current_user_experience.md) execution log

## Steps

1. Systematically re-read every file in the conversation path (backend +
   frontend), cross-referencing against the findings from task_00 and
   task_01.
2. For each file, apply the categories above and document every issue found.
3. Deduplicate against issues already noted in task_01 §10 (UX Friction
   Points) — reference them but do not re-describe. Add new issues only.
4. Prioritize by severity.

## Completion Criteria

- Every issue is backed by a file path and line number.
- No issue is speculative — each must be demonstrable from the code.
- A developer could use this document as a backlog and fix each item
  independently without further research.
