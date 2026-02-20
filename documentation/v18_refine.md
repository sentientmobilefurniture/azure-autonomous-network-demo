# v18 Refinement Plan

Three issues identified after deploying v17 (Depot entity + disambiguated edges).
Ordered by implementation difficulty: B (prompt-only) → C (backend startup) → A (backend + frontend).

---

## Issue A — Multi-query Visualization Capture

### Problem

When an agent (e.g. GraphExplorerAgent, TelemetryAgent) makes **multiple tool calls**
within a single orchestrator turn, only the **last** query's structured data is
captured in the visualization. The "View Graph" / "View Telemetry" button shows
a single result set — all earlier queries are lost.

### Root Cause (3 layers)

| Layer | File | Detail |
|-------|------|--------|
| **Agent prompt** | `graph_explorer/core_instructions.md` L63 | *"If you made multiple tool calls, include only the **last** query…"* — agent is instructed to discard prior query data |
| **Backend parser** | `api/app/orchestrator.py` `_parse_structured_output()` ~L249/~L864 | `re.search()` captures only the **first** `---QUERY---`/`---RESULTS---` match — even if multiple blocks existed, only one would be extracted |
| **Frontend type** | `frontend/src/types/index.ts` L89 | `StepEvent.visualization?: VisualizationData` — single optional value, not an array |

### Design

Change the paradigm from **one viz per step** to **N vizs per step**, rendered
as tabs in the modal.

#### A.1 — Agent prompts (graph_explorer + telemetry)

Replace the "include only the last query" instruction with a **stacked block** format:

```
---QUERY---
<first GQL query, verbatim>
---RESULTS---
<first query's full JSON response, verbatim>
---QUERY---
<second GQL query, verbatim>
---RESULTS---
<second query's full JSON response, verbatim>
---ANALYSIS---
<combined analysis across ALL queries>
```

Rules:
- One `---QUERY---`/`---RESULTS---` pair per tool call, in chronological order.
- If only one tool call was made, the format is the same as today (single block).
- The single `---ANALYSIS---` section still appears last, covering all queries.

Files to edit:
- `data/scenarios/telecom-playground/data/prompts/graph_explorer/core_instructions.md` — L63
- `data/scenarios/telecom-playground/data/prompts/foundry_telemetry_agent_v2.md` — L152

#### A.2 — Backend: `_parse_structured_output()` → extract all blocks

In `api/app/orchestrator.py` (both orchestrator classes — ~L249 and ~L864):

**Both call sites** that unpack the return value must also be updated:
```python
# Before (~L417 / ~L1005):
response, visualization = self._parse_structured_output(agent_name, str(out))
# After:
response, visualizations = self._parse_structured_output(agent_name, str(out))
```

1. Replace `re.search()` with `re.findall()` to capture **all** query/results pairs:
   ```python
   query_blocks = re.findall(
       r'---QUERY---\s*(.+?)\s*---RESULTS---\s*(.+?)\s*(?=---QUERY---|---ANALYSIS---)',
       raw_output, re.DOTALL,
   )
   analysis_match = re.search(r'---ANALYSIS---\s*(.+)', raw_output, re.DOTALL)
   ```

2. Build a **list** of visualization dicts — one per query/results pair:
   ```python
   visualizations = []
   for query_text, results_text in query_blocks:
       # Reuse existing json.loads / ast.literal_eval parsing logic
       results_json = None
       try:
           results_json = json.loads(results_text.strip())
       except (json.JSONDecodeError, ValueError):
           try:
               results_json = ast.literal_eval(results_text.strip())
           except (ValueError, SyntaxError):
               pass
       if results_json and isinstance(results_json, dict):
           results_json.pop("error", None)
           visualizations.append({
               "type": viz_type,
               "data": {**results_json, "query": query_text.strip()},
           })
   ```

3. Change the return type from `tuple[str, dict | None]` to
   `tuple[str, list[dict]]`:
   ```python
   return summary, visualizations   # [] if no structured data
   ```

4. **Preserve all existing fallback paths.** When `query_blocks` is empty (agent
   didn't follow the multi-block format, or returned no delimiters), fall through
   to the existing `citations_match`, documents-agent, and no-delimiters branches
   exactly as today — but wrap the single `viz_data` dict in a list before returning:
   ```python
   return summary, [viz_data] if viz_data else []
   ```
   This keeps the return type uniform (`list[dict]`) regardless of path.

5. **Edge case: `query_blocks` is non-empty but all JSON parses fail.** In this
   scenario `visualizations` will be `[]` after the for-loop. The code should
   detect this and fall through to the existing documents-fallback (Return Path 3
   in the current code) rather than returning an empty list:
   ```python
   if query_blocks and not visualizations:
       # Structured delimiters were present but every parse failed.
       # Fall through to documents-fallback below.
       pass
   elif query_blocks:
       return summary, visualizations
   ```

6. At the emission site (~L490 / ~L1081), change the key name:
   ```python
   if visualizations:
       event_data["visualizations"] = visualizations   # plural
   ```

#### A.3 — Frontend types

In `frontend/src/types/index.ts`:

```diff
 export interface StepEvent {
   …
-  visualization?: VisualizationData;
+  visualizations?: VisualizationData[];
   …
 }
```

#### A.4 — Frontend `useVisualization.ts` hook

Adapt the resolution cascade to work with the array:

```typescript
// Priority 1: pre-attached structured viz (graph/table) from backend
if (step.visualizations?.length) {
  const structured = step.visualizations.filter(v => v.type !== 'documents');
  if (structured.length) { setData(structured); return; }
}
// Priority 2-4: search-agent fetch, fallback doc, etc. — wrap in array
```

Return type changes from `VisualizationData | null` to `VisualizationData[]`.

#### A.5 — Frontend `components/visualization/StepVisualizationModal.tsx`

Accept array and render **tabs**:

```tsx
interface StepVisualizationModalProps {
  vizData: VisualizationData[];   // was: VisualizationData | null
  …
}
```

When `vizData.length > 1`, render a tab bar above the viz area:

```
┌──────────────────────────────────────────┐
│ [Query 1]  [Query 2]  [Query 3]         │  ← tab header
├──────────────────────────────────────────┤
│                                          │
│   <GraphResultView /> or                 │
│   <TableResultView /> or                 │
│   <DocumentResultView />                 │
│                                          │
└──────────────────────────────────────────┘
```

- Tab label: truncated query string (e.g. `MATCH (tl:TransportLink)…`), max ~40 chars.
- Active tab state: `useState<number>(0)`.
- Only render GraphResultView / TableResultView for the active tab's data.
- When `vizData.length === 1`, hide the tab bar entirely (identical to today).

#### A.6 — Frontend `StepCard` + `useSession`

- `StepCard.tsx` passes the array to the modal: `vizData={vizData}` (already works if
  `useVisualization` returns the array).
- `useSession.ts` SSE handler: no change needed — it already pushes `step_complete`
  payloads verbatim into `ChatMessage.steps[]`. The new `visualizations` key will
  be stored automatically.
- `useSession.ts` replay from `event_log`: similarly transparent.

#### A.7 — Cosmos DB / session persistence

`SessionManager._persist_to_cosmos()` persists `session.to_dict()` which includes
`steps[]` and `event_log[]`. Both will automatically carry the new `visualizations`
array — no schema migration needed.

**Backward compat:** Old sessions have `visualization` (singular). The frontend
hook should check both:
```typescript
const vizArray = step.visualizations ?? (step.visualization ? [step.visualization] : []);
```

### Testing

1. Ask: *"Show me all TransportLinks and their source/target routers, then show all
   Sensors monitoring TransportLinks"* — should produce 2 graph viz tabs in the modal.
2. Ask: *"What are the latest alerts for LINK-SYD-MEL-FIBRE-01 and also show
   utilization for the last 24 hours"* — 2 table tabs (TelemetryAgent).
3. Verify single-query scenarios still show no tab bar.
4. Verify old sessions (pre-migration) still render correctly via backward compat.

---

## Issue B — Depot → TransportLink Traversal Gap

### Problem

The orchestrator dispatches with flow: *"Which Depot services LINK-SYD-MEL-FIBRE-01?"*
But **no direct edge** exists between Depot and TransportLink. The Depot entity only
has `services_corerouter` and `services_amplifiersite` edges. When the
GraphExplorerAgent receives this query, it either hallucinates a `services_transportlink`
edge (which doesn't exist) or returns empty results.

### Graph Path Analysis

Two valid multi-hop paths exist:

```
Path 1 (via CoreRouter — 2 hops):
  TransportLink ─[connects_to]─▶ CoreRouter ◀─[services_corerouter]─ Depot

Path 2 (via AmplifierSite — 2 hops):
  Depot ─[services_amplifiersite]─▶ AmplifierSite ─[amplifies]─▶ TransportLink
```

GQL examples (Fabric GQL uses `MATCH`/`RETURN`, **NOT** Gremlin traversal syntax):

**Path 1 — via CoreRouter:**
```gql
MATCH (tl:TransportLink)-[:connects_to]->(cr:CoreRouter)<-[:services_corerouter]-(d:Depot)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN d.DepotId, d.DepotName, d.City, cr.RouterId
```

**Path 2 — via AmplifierSite:**
```gql
MATCH (d:Depot)-[:services_amplifiersite]->(a:AmplifierSite)-[:amplifies]->(tl:TransportLink)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN d.DepotId, d.DepotName, d.City, a.SiteId
```

> **Note:** Fabric GQL does not support `UNION`. The agent should run these as
> **two separate tool calls** and combine findings in the ANALYSIS section. This
> aligns with Issue A (multi-query viz tabs).

### Fix — Prompt Updates

#### B.1 — `core_schema.md` — Depot traversal pattern section

Add a new subsection under the Depot section:

```markdown
### Depot ↔ TransportLink (multi-hop — no direct edge)

There is **no direct edge** between Depot and TransportLink. To find which
Depot(s) service infrastructure along a TransportLink, traverse via the
intermediate nodes. Run these as **two separate queries** (Fabric GQL has no UNION).

**Query 1 — Via CoreRouter (TransportLink → connects_to → CoreRouter ← services_corerouter ← Depot):**
```gql
MATCH (tl:TransportLink)-[:connects_to]->(cr:CoreRouter)<-[:services_corerouter]-(d:Depot)
WHERE tl.LinkId = '<LINK_ID>'
RETURN d.DepotId, d.DepotName, d.City, cr.RouterId
```

**Query 2 — Via AmplifierSite (Depot → services_amplifiersite → AmplifierSite → amplifies → TransportLink):**
```gql
MATCH (d:Depot)-[:services_amplifiersite]->(a:AmplifierSite)-[:amplifies]->(tl:TransportLink)
WHERE tl.LinkId = '<LINK_ID>'
RETURN d.DepotId, d.DepotName, d.City, a.SiteId
```

The agent runs both queries and deduplicates Depots in the ANALYSIS section.
```

#### B.2 — `core_instructions.md` — Add rule about multi-hop traversal

Add to the numbered rules list:

```markdown
7. **Depot ↔ TransportLink requires multi-hop traversal.** There is no direct edge
   between Depot and TransportLink. To find which depots service a link, traverse
   via the CoreRouter (connects_to) or AmplifierSite (amplifies) intermediate nodes.
   See the "Depot ↔ TransportLink" section in core_schema.md for the two GQL query patterns.
```

#### B.3 — `foundry_orchestrator_agent.md` — Fix Flow A step 5 / Flow B step 7

In both flows, the orchestrator asks GraphExplorerAgent to find the relevant Depot.
Add an explicit instruction that for TransportLink-related faults, the depot lookup
should use the multi-hop traversal:

**Flow A step 5** (currently L160-165):
```markdown
5. **Look up the duty roster via depot.** Ask the GraphExplorerAgent: which Depot has a
   `services_corerouter` or `services_amplifiersite` edge to the affected infrastructure?
   **If the affected entity is a TransportLink**, the agent must traverse via CoreRouter
   (connects_to) or AmplifierSite (amplifies) first — there is no direct Depot→TransportLink
   edge. Then: which DutyRoster entries are `stationed_at` that depot and currently on shift?
```

**Flow B step 7** (currently L196-198): same addition about TransportLink multi-hop.

### Testing

1. Ask: *"Which depot services LINK-SYD-MEL-FIBRE-01?"* — should return Depot(s)
   connected to that link's CoreRouters and/or AmplifierSites.
2. Run a full Flow A scenario with a TransportLink fault — verify dispatch finds the
   correct depot and engineer.

---

## Issue C — Sessions Lost on Deploy

### Problem (as reported)

The interactions/sessions list appears empty after every `azd deploy app`. The user
perceives this as "Cosmos DB gets cleared with every deploy."

### Root Cause Analysis

| Hypothesis | Verdict |
|------------|---------|
| `deploy.sh` clears the Cosmos container | **No** — no `provision_cosmos.py` call or Cosmos delete logic in deploy.sh |
| `provision_cosmos.py` clears interactions | **No** — only touches telemetry containers (LinkTelemetry, RouterTelemetry, etc.) |
| Bicep redeploy recreates the container | **No** — ARM is idempotent; partition key is unchanged between deploys |
| `postprovision.sh` hook clears data | **No** — only uploads blobs and updates azure_config.env |
| App startup code clears the container | **No** — `_arm_ensure_container()` is idempotent (checks if exists, skips) |
| **`SessionManager` is purely in-memory** | **YES** — `_active` and `_recent` dicts are lost on container restart |

**The data is _usually_ in Cosmos DB — but not always.** The primary issue is that
it's never loaded back. When the Container App restarts (any deploy triggers a restart),
`SessionManager.__init__()` creates empty dicts. The `list_sessions()` endpoint calls
`session_manager.list_all()` which only reads from these in-memory dicts.

However, there is a **secondary timing issue**: `_persist_to_cosmos()` is only called
from `_move_to_recent()`, and `_finalize_turn()` only calls `_move_to_recent()` for
CANCELLED or FAILED sessions. For COMPLETED sessions, `_finalize_turn()` calls
`_schedule_idle_timeout()` instead — the session stays in `_active` and is only moved
to `_recent` (triggering the Cosmos write) when the **idle timeout fires (600 s)**.
If the app is restarted within that 600 s window, the completed session is **never
persisted to Cosmos at all**.

Additionally, even when `_move_to_recent()` fires, the Cosmos write is
fire-and-forget (`asyncio.create_task()`). If the process is killed while the write
is in-flight, that session is also lost.

### Fix

#### C.1 — Add `list_all()` Cosmos DB fallback

When the in-memory cache returns no sessions (or when explicitly requested),
query Cosmos DB for historical sessions:

In `api/app/session_manager.py`:

```python
async def list_all_with_history(self, scenario: str = None, limit: int = 50) -> list[dict]:
    """Return sessions from in-memory cache + Cosmos DB (for history)."""
    # In-memory first (active + recent)
    mem_sessions = self.list_all(scenario)
    mem_ids = {s["id"] for s in mem_sessions}

    # Backfill from Cosmos DB (skip anything already in memory)
    try:
        from stores import get_document_store
        store = get_document_store(
            "interactions", "interactions", "/scenario",
            ensure_created=True,
        )
        query = "SELECT * FROM c"
        params = []
        if scenario:
            query += " WHERE c.scenario = @scenario"
            params.append({"name": "@scenario", "value": scenario})
        # Cosmos DB SQL requires literal integers for OFFSET/LIMIT (no parameters)
        query += f" ORDER BY c.created_at DESC OFFSET 0 LIMIT {int(limit)}"

        cosmos_items = await store.list(query=query, parameters=params or None)
        for item in cosmos_items:
            if item.get("id") not in mem_ids:
                mem_sessions.append({
                    "id": item["id"],
                    "scenario": item.get("scenario", ""),
                    "alert_text": (item.get("alert_text", "") or "")[:100],
                    "status": item.get("status", "completed"),
                    "step_count": len(item.get("steps", [])),
                    "created_at": item.get("created_at", ""),
                    "updated_at": item.get("updated_at", ""),
                })
    except Exception:
        logger.exception("Failed to load historical sessions from Cosmos")

    return mem_sessions
```

#### C.2 — Update the `list_sessions` router endpoint

In `api/app/routers/sessions.py`:

```python
@router.get("")
async def list_sessions(scenario: str = Query(default=None)):
    """List all sessions (active + recent + Cosmos DB history)."""
    sessions = await session_manager.list_all_with_history(scenario)
    return {"sessions": sessions}
```

#### C.3 — Update `get_session` to load from Cosmos if not in memory

```python
@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get full session state — checks memory first, then Cosmos DB."""
    session = session_manager.get(session_id)
    if session:
        return session.to_dict()

    # Fallback: load from Cosmos DB (cross-partition query by ID)
    try:
        from stores import get_document_store
        store = get_document_store(
            "interactions", "interactions", "/scenario",
            ensure_created=True,
        )
        items = await store.list(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": session_id}],
        )
        if items:
            return items[0]  # Already a dict from Cosmos
    except Exception:
        pass

    raise HTTPException(404, "Session not found")
```

**Note:** `store.list()` with no `partition_key` kwarg automatically sets
`enable_cross_partition_query=True`, so a query-by-ID works without knowing
the session's scenario value. This is acceptable at low volume.

#### C.4 — Persist immediately on completion (fix the 600 s gap)

`_finalize_turn()` only calls `_move_to_recent()` (and thus `_persist_to_cosmos()`)
for CANCELLED or FAILED sessions. COMPLETED sessions stay in `_active` until the
idle timeout fires 600 s later. If the app restarts in that window, the session is
never written to Cosmos.

**Fix:** Add an explicit persist call in `_finalize_turn()` for the COMPLETED path:

```python
def _finalize_turn(self, session: Session):
    if session._cancel_event.is_set():
        session.status = SessionStatus.CANCELLED
        self._move_to_recent(session)
    elif session.error_detail and not session.diagnosis:
        session.status = SessionStatus.FAILED
        self._move_to_recent(session)
    else:
        session.status = SessionStatus.COMPLETED
        asyncio.create_task(self._persist_to_cosmos(session))   # <── NEW
        self._schedule_idle_timeout(session)
```

This ensures the session is written to Cosmos immediately on completion, even though
it stays in `_active` for potential follow-up turns. The idle timeout still fires
later and calls `_move_to_recent()` → second persist (an upsert, so idempotent).

#### C.5 — (Optional) Hydrate `_recent` on startup

For faster subsequent lookups, load the N most recent sessions into `_recent`
when the app starts:

```python
class SessionManager:
    async def hydrate_from_cosmos(self, scenario: str = None, limit: int = 50):
        """Load recent sessions from Cosmos into _recent for fast lookups."""
        # ... query Cosmos, reconstruct Session objects, populate _recent ...
```

Call from FastAPI's `startup` event or `lifespan` context manager.

**Caveat:** Reconstructing full `Session` objects requires the `event_log`, which
could be large. For the session list, the summary dict approach (C.1) is lighter.
Full hydration is only needed if users need to **replay SSE streams** for old sessions.

### What NOT to Change

- **Bicep template** — The Cosmos container definition is correct and idempotent.
  No changes needed.
- **`defaultTtl: 7776000`** (90 days) — Reasonable for demo purposes. Old sessions
  auto-expire. No change needed unless the user wants permanent storage.
- **`provision_cosmos.py`** — Only targets telemetry containers. Leave as-is.

### Testing

1. Create a session, verify it appears in the list.
2. Restart the container app (`az containerapp revision restart ...`) **immediately**
   (within a few seconds — don't wait 600 s for the idle timeout).
3. Refresh the frontend — verify the session still appears in the list (loaded from Cosmos).
4. Click into the session — verify full step data loads (from Cosmos).
5. Verify a session that completed > 600 s ago also survives a restart (double-persist:
   once on completion via C.4, once on idle timeout via existing `_move_to_recent`).

---

## Implementation Order

| Priority | Issue | Effort | Risk |
|----------|-------|--------|------|
| 1 | **B** — Depot→TransportLink traversal | ~30 min | Low (prompt-only, no code changes) |
| 2 | **C** — Session persistence across deploys | ~2 hr | Medium (backend changes, needs Cosmos query testing) |
| 3 | **A** — Multi-query visualization tabs | ~4 hr | Medium-High (backend + frontend + prompt changes, backward compat) |

Issues B and C are independent and can be deployed separately. Issue A spans all
layers and should be tested end-to-end before deploying.
