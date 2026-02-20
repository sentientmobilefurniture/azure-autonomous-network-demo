# Implementation Plan Template

> **Purpose:** Guide agents and developers to produce thorough, high-quality
> implementation plans for new features and refactors. Plans following this
> template should be self-contained — an implementer who reads only the plan
> should have everything they need to build, verify, and ship the feature.
>
> **Usage:** Copy this template, replace all `{PLACEHOLDER}` values and
> `<!-- INSTRUCTION -->` blocks with real content. Delete sections that
> genuinely don't apply (e.g., "Migration" for greenfield features), but
> err on the side of keeping sections — most apply more often than you think.
>
> **Quality bar:** The reference plans (QOLimprovements.md, SCENARIOHANDLING.md)
> demonstrate the expected level of detail. Every section below explains *what*
> to write and *why* it matters.

---

# {Feature Name} — Implementation Plan

> **Created:** {YYYY-MM-DD}
> **Last audited:** {YYYY-MM-DD}
> **Status:** ⬜ Not Started
> **Goal:** {One to three sentences describing the user-visible outcome.
> Focus on *what changes for the user*, not implementation details.
> Example: "Let users create, save, and switch between complete scenarios
> from the UI — one form to name a scenario, upload all 5 tarballs, and
> persist it."}

---

## Requirements (Original)

<!-- Paste the raw requirements exactly as the user/stakeholder stated them.
     Number each one. Do NOT paraphrase or interpret yet — that comes later.
     This section is the source of truth for "what was actually asked for"
     and is used to validate that the plan covers everything. -->

1. {Requirement 1 — verbatim from stakeholder}
2. {Requirement 2}
3. ...

---

## Implementation Status

<!-- A quick-glance table showing where each phase stands. Update this as
     work progresses. Use these status markers consistently:
     ⬜ Not started | 🔶 Partial | ✅ Complete -->

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 1:** {Phase name} | ⬜ Not started | {Key files affected} |
| **Phase 2:** {Phase name} | ⬜ Not started | {Key files affected} |
| **Phase 3:** {Phase name} | ⬜ Not started | {Key files affected} |

### Deviations From Plan

<!-- Fill this in DURING implementation. Track every place where the actual
     implementation diverges from the plan, with rationale. This is critical
     for future maintainers who read the plan and find the code doesn't match.
     If nothing has been implemented yet, leave this as a placeholder. -->

| # | Plan Said | What Was Done | Rationale |
|---|-----------|---------------|-----------|
| D-1 | — | — | — |

### Extra Work Not In Plan

<!-- Track bug fixes, refactors, or additions discovered during implementation
     that weren't part of the original plan. -->

- {None yet}

---

## Table of Contents

<!-- Generate after the plan is written. Include all H2 and key H3 sections.
     Readers use this to jump directly to the item they're implementing. -->

- [Requirements (Original)](#requirements-original)
- [Codebase Conventions & Context](#codebase-conventions--context)
- [Overview of Changes](#overview-of-changes)
- [Item 1: {Name}](#item-1-name)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)

---

## Codebase Conventions & Context

<!-- ⚠️ THIS SECTION IS CRITICAL. Read the actual codebase and document the
     conventions that an implementer MUST follow. Every plan that touches
     routing, naming, imports, or data formats should have this section.
     
     The goal is to prevent the #1 failure mode: an implementer writes
     correct-looking code that breaks because they didn't know about an
     implicit convention (e.g., aliased imports, proxy routing, header
     formats, naming derivations).
     
     Audit the codebase for these categories and document what you find: -->

### Request Routing

<!-- How do requests flow from frontend to backend? Which URL prefixes
     map to which services? What proxy/nginx config is relevant?
     Document the routing so new endpoints are placed correctly. -->

| URL prefix | Proxied to | Config |
|------------|-----------|--------|
| `{/prefix/*}` | {Service on port X} | {Config file + line numbers} |

### Naming Conventions

<!-- How are entities named across the system? How are names derived from
     each other (e.g., scenario name → graph name → telemetry DB name)?
     Document the derivation chain so implementers don't break it. -->

| Concept | Example | Derivation |
|---------|---------|-----------|
| {Entity name} | `"{example}"` | {How it's derived, where it's stored} |

### Import & Code Style Conventions

<!-- Document any non-obvious import patterns, aliases, or style rules
     that the codebase uses. Include examples of correct and incorrect usage. -->

```
{Example of correct import/usage pattern}
```

### Data Format Conventions

<!-- SSE event formats, API response shapes, header conventions, etc.
     Anything where "it looks like it should work but doesn't because
     the format is slightly different than expected." -->

| Convention | Format | Where Used |
|-----------|--------|------------|
| {e.g., SSE events} | {e.g., `event: log\ndata: ...\n\n`} | {Components/endpoints that depend on this} |

---

## Overview of Changes

<!-- High-level summary table showing ALL items in the plan with their
     category, impact, and effort. This gives readers the full picture
     before diving into details. -->

| # | Item | Category | Impact | Effort |
|---|------|----------|--------|--------|
| 1 | {Item name} | {Backend/Frontend/Infra/Full-stack} | {High/Medium/Low — why} | {Large/Medium/Small} |
| 2 | {Item name} | ... | ... | ... |

### Dependency Graph

<!-- Show which phases depend on each other. Use ASCII art or a simple
     list. This determines implementation order and parallelization. -->

```
Phase 1 ──┐
           ├──▶ Phase 3 (depends on 1)
Phase 2 ──┘    
Phase 4        (independent)
```

<!-- State clearly which phases can be parallelized and which must be sequential. -->

### UX Audit Summary

<!-- If the feature has user-facing changes, audit the plan against the
     actual frontend codebase. Cross-reference each feature against:
     - Micro-interactions and feedback loops
     - Visual cues and state indicators
     - Edge-case behaviors (empty states, error states, loading states)
     - Consistency with existing UI patterns
     
     Summarize findings in a table. Detailed fixes go in per-item sections. -->

| Area | Finding | Severity |
|------|---------|----------|
| {Feature area} | {What's missing or could be better} | {High/Medium/Low} |

---

## Item {N}: {Item Name}

<!-- Repeat this section structure for each item/feature in the plan.
     This is the core of the document — where the actual design lives. -->

### Current State

<!-- Describe exactly how things work TODAY. Include:
     - Which files/components are involved (with line numbers if helpful)
     - What the user currently sees/experiences
     - What data flows where
     - Code snippets showing the current implementation pattern
     
     This is NOT optional. Without a clear "before" picture, the implementer
     can't understand the "after" or verify they didn't break anything. -->

{Description of current behavior, referencing specific files and code patterns.}

**Problem:** {One sentence stating what's wrong or missing. This connects
the current state to the need for change.}

### Target State

<!-- Describe the desired end state. For UI changes, include ASCII wireframes.
     For data changes, include schema examples. For API changes, include
     endpoint signatures. Be concrete — "improved UX" is not a target state. -->

{Description + wireframe/schema/endpoint of the desired behavior.}

```
┌──────────────────────────────────────────────────┐
│ {ASCII wireframe showing the target UI state}    │
│ {Label key interactive elements}                 │
└──────────────────────────────────────────────────┘
```

### Backend Changes

<!-- For each backend file that changes, show:
     1. The current code pattern (brief snippet)
     2. What changes (new pattern)
     3. Why (if not obvious)
     
     Use before/after code blocks. Call out implementation traps with ⚠️ warnings. -->

#### `{file/path.py}` — {Brief description of change}

```python
# Current:
{current pattern}

# New:
{new pattern}
```

> **⚠️ Implementation note:** {Any trap, gotcha, or non-obvious detail.
> E.g., "This function is a nested closure — extract it first."
> E.g., "This ARM call takes 20-30s — don't await it in the request handler."}

### Frontend Changes

<!-- Same structure as backend. For components, include:
     - Props interface changes
     - State additions
     - JSX structure changes (with code snippets)
     - CSS/styling notes referencing existing class conventions -->

#### `{ComponentName}.tsx` — {Brief description}

```tsx
// New/changed JSX:
{code snippet}
```

### UX Enhancements

<!-- Sub-items (numbered as Na, Nb, Nc) for UX polish beyond the basic
     implementation. Each should be independently implementable.
     Include: what, why, and how (implementation sketch). -->

#### {N}a. {Enhancement Name}

**Problem:** {What's rough about the basic implementation}

**Fix:** {Concrete solution with code sketch if needed}

**Why:** {User impact — connects to observed behavior or UX principle}

#### {N}b. {Enhancement Name}

...

---

<!-- Repeat "Item N" sections for all items -->

---

## Implementation Phases

<!-- Break the work into ordered phases. Each phase should be:
     - Independently deployable (or at least testable)
     - Small enough to review as one PR
     - Clear about its dependencies
     
     For each phase, list: files to create, files to modify, and
     verification steps (how to confirm the phase works). -->

### Phase {N}: {Phase Name}

> {Dependency note: "Prerequisite for Phase X" or "Independent" or "Depends on Phase Y"}

**Files to create:**
- `{path/to/new_file}` — {purpose} (~{estimated lines})

**Files to modify:**
- `{path/to/existing_file}` — {what changes}

**Verification:**
- {Concrete test step — what to do and what to observe}
- {Include both happy-path and edge-case verification}
- {Bold critical verification steps that catch common mistakes}

---

## File Change Inventory

<!-- Comprehensive table of EVERY file that changes, grouped by action type.
     This is the implementer's checklist — they should be able to go through
     this table and confirm every file was handled.
     
     Also list files explicitly NOT changed, with reasons. This prevents
     an implementer from making unnecessary changes to adjacent code. -->

| File | Action | Phase | Changes |
|------|--------|-------|---------|
| `{path/to/file}` | **CREATE** | {N} | {Brief description} (~{est. lines}) |
| `{path/to/file}` | MODIFY | {N} | {Brief description of what changes} |

### Files NOT Changed

<!-- Explicitly listing unchanged files prevents unnecessary modifications
     and helps reviewers confirm the change boundary is correct. -->

- `{path/to/file}` — {reason it doesn't need changes despite seeming related}

---

## Cross-Cutting UX Gaps

<!-- System-wide UX issues discovered during the audit that aren't tied to
     a specific item but affect the overall feel. These may be out of scope
     but should be documented so they're not lost.
     
     For each gap: current state, recommendation, and scope note. -->

### Gap {N}: {Gap Name}

**Current state:** {What exists today}

**Where this matters for the current plan:** {Which items are affected}

**Recommendation:** {What to do about it}

**Scope:** {In scope for this plan / Fast-follow / Backlog}

---

## UX Priority Matrix

<!-- Rank ALL UX enhancements (from per-item sections and cross-cutting gaps)
     by impact relative to effort. This helps implementers triage when time
     is limited.
     
     Priority levels:
     P0 — Required for the feature to feel complete. Implement in the same phase.
     P1 — Small polish that should be included if possible. Low effort, medium impact.
     P2 — Nice-to-have. Include if time permits.
     P3 — Post-launch polish. Log as follow-up issues.
     Backlog — Separate work stream. Out of scope. -->

| Priority | Enhancement | Item | Effort | Impact |
|----------|------------|------|--------|--------|
| **P0** | {Enhancement name} | {N} | {Tiny/Small/Medium} | {High/Medium} |
| **P1** | {Enhancement name} | {N} | ... | ... |
| **P2** | {Enhancement name} | {N} | ... | ... |
| **P3** | {Enhancement name} | {N} | ... | ... |

### Implementation Notes

- **P0 items** should be implemented alongside their respective phases. They
  prevent UX regressions or are essential for feature comprehension.
- **P1 items** are small polish additions that can be included without
  architecture changes.
- **P2 items** enhance the feature but don't block a good initial experience.
- **P3 items** are polish for post-launch iteration.

---

## Edge Cases & Validation

<!-- For EACH item, enumerate edge cases and how they're handled.
     Categories to consider:
     - Invalid/unexpected input
     - Concurrent operations (race conditions)
     - Empty/null/missing data
     - Network failures and partial failures
     - Browser/device variations
     - Backwards compatibility with existing data
     - Resource limits (name lengths, payload sizes, timeouts)
     - Security/access control edge cases
     
     Be specific: "container name max 256 chars — worst case is ~45 chars, 
     well within limits" is better than "names should be fine." -->

### {Item Name} (Item {N})

**{Edge case name}:** {How it's handled. Include specific numbers, limits,
and code references where relevant.}

**{Edge case name}:** {How it's handled.}

---

## Migration & Backwards Compatibility

<!-- Almost every change has migration implications. Even "new feature" plans
     need to consider:
     - What happens to existing data?
     - What happens to existing API consumers?
     - What happens on first deploy to an existing environment?
     - Can users opt in gradually or is it all-or-nothing?
     - What if someone reads old docs and tries the old approach?
     
     If this is truly a greenfield feature with zero migration concerns,
     say so explicitly and explain why. Don't just skip the section. -->

### Existing Data

{What happens to data that exists before this change deploys.}

### API Surface Compatibility

{Are any API contracts changing? Are changes additive or breaking?
New optional fields on existing types should be marked with `?` for
back-compat.}

### Gradual Adoption

{Can the feature be adopted incrementally? Is there a transition period
where both old and new approaches work?}

### Rollback Plan

{What happens if we need to revert? Is the data format change reversible?
Do we need feature flags?}

---

---

# Appendix: Template Writing Guidelines

> **Delete this entire appendix when using the template.** It exists to
> explain the *principles* behind the template structure.

## What Makes an Excellent Implementation Plan

The reference plans (QOLimprovements.md, SCENARIOHANDLING.md) share these
qualities. A good plan should hit all of them:

### 1. Self-Contained Context

An implementer should not need to ask clarifying questions. The plan provides:
- **Codebase conventions** — routing, naming, import patterns, data formats
- **Current state** — exactly how things work today, with file references
- **Target state** — exactly how things should work, with wireframes and schemas
- **Code snippets** — before/after patterns showing the actual change

### 2. Concrete Over Abstract

Every claim is grounded in specifics:
- ❌ "The upload is slow" → ✅ "ARM `begin_create_update_sql_database()` takes 20-30 seconds"
- ❌ "Update the component" → ✅ "Add `cooldownTicks={frozen ? 0 : Infinity}` prop to `<ForceGraph2D>`"
- ❌ "Add error handling" → ✅ "Catch `CosmosResourceNotFoundError` (not bare `except:`) to avoid swallowing `ServiceRequestError`"

### 3. Implementation Traps Flagged

The most valuable parts of a plan are the warnings about things that *seem*
like they should work but don't:
- "⚠️ This function is a nested closure — extract it before refactoring"
- "⚠️ `pauseAnimation()` stops the entire render loop, breaking node drag"
- "⚠️ The SSE endpoint is shadowed by nginx routing — use `/query/logs` instead"

### 4. Exhaustive File Inventory

Every file that changes (and key files that DON'T change) is listed. This serves as:
- A checklist during implementation
- A review guide for code reviewers
- A scope boundary preventing unnecessary changes

### 5. Phased With Dependencies

Work is broken into phases that are:
- **Independently verifiable** — each phase has concrete verification steps
- **Dependency-aware** — which phases block others vs. can be parallelized
- **Right-sized** — small enough for one PR, large enough to be meaningful

### 6. UX Depth

For user-facing features, the plan:
- **Audits the existing UI** — reads the actual component code, not just screenshots
- **Specifies states** — idle, loading, success, error, empty, edge cases
- **Includes wireframes** — ASCII art showing exact layout and content
- **Cross-references patterns** — "use the same `bg-white/10 backdrop-blur-sm` as GraphTooltip"
- **Prioritizes enhancements** — P0 through P3, with effort/impact reasoning

### 7. Edge Cases Are Enumerated

Not just "handle errors" but:
- What specific errors can occur?
- What's the user-visible impact of each?
- What's the recovery path?
- What are the resource limits and how close do we get?

### 8. Migration Is Planned

Even additive changes need migration thinking:
- New optional fields on existing types (use `?` for back-compat)
- Fallback logic for old data formats
- Gradual adoption paths
- Explicit rollback considerations

## Process for Writing a Plan

1. **Read the requirements** — paste them verbatim into the Requirements section
2. **Audit the codebase** — read every file that will be touched. Note conventions,
   patterns, gotchas. Fill the "Codebase Conventions" section.
3. **Document current state** — for each item, write the "Current State" section
   first. You can't design a change you don't understand.
4. **Design the target state** — wireframes, schemas, endpoints. Be concrete.
5. **Plan the implementation** — code snippets showing actual changes.
   Flag traps with ⚠️ warnings.
6. **UX audit** — cross-reference each feature against the live frontend.
   Identify missing states, feedback loops, and polish opportunities.
7. **Enumerate edge cases** — systematically go through failure modes.
8. **Phase the work** — order by dependencies, write verification steps.
9. **Build the file inventory** — comprehensive list of all changes.
10. **Review for completeness** — could an implementer build this with ONLY
    this document? If not, add what's missing.

## Common Mistakes to Avoid

| Mistake | Why It's Bad | Fix |
|---------|-------------|-----|
| Skipping "Current State" | Implementer doesn't know what to change | Always document the before picture |
| Vague target ("improve perf") | No definition of done | Concrete metrics or behaviors |
| Missing wireframes for UI | Implementer guesses the layout | ASCII art for every visible change |
| No code snippets | Implementer reinvents the pattern | Show before/after code |
| No edge cases | Bugs ship to production | Enumerate failure modes systematically |
| No file inventory | Scope creep or missed files | List every file, including unchanged ones |
| Missing convention docs | Implementer breaks implicit rules | Audit the codebase and document patterns |
| Monolithic phases | PRs are too large to review | Break into independently verifiable phases |
| No verification steps | No way to confirm a phase works | Write concrete "do X, observe Y" steps |
| Skipping migration | Existing deployments break | Plan for old data, old APIs, rollback |
