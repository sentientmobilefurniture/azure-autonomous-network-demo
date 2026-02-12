# Current UI Wireframe & Structure

## Overview

The frontend is a single-page React app (`App.tsx`, no component directory).
Dark glassmorphism theme using Tailwind CSS + Framer Motion. All state is local
(`useState`). SSE streaming via `@microsoft/fetch-event-source`.

---

## Layout: Full Page

```
┌─────────────────────────────────────────────────────────────────────────┐
│  body: bg-neutral-bg1 (hsl 240 6% 10%) — near-black                   │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  max-w-4xl mx-auto p-8  (centered column, 896px max)             │  │
│  │                                                                   │  │
│  │  ┌───────────────────────────────────────────────────────────┐   │  │
│  │  │ HEADER                                                    │   │  │
│  │  │ h1: "Autonomous Network NOC"  text-2xl font-semibold     │   │  │
│  │  │ p:  "Multi-agent diagnosis system"  text-sm text-muted   │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                          mb-8    │  │
│  │  ┌───────────────────────────────────────────────────────────┐   │  │
│  │  │ ALERT INPUT CARD                          glass-card p-6  │   │  │
│  │  │ ...                                                       │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                          mb-6    │  │
│  │  ┌───────────────────────────────────────────────────────────┐   │  │
│  │  │ RUNNING INDICATOR (conditional)                           │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                          mb-6    │  │
│  │  ┌───────────────────────────────────────────────────────────┐   │  │
│  │  │ AGENT STEPS TIMELINE (conditional)        glass-card p-6  │   │  │
│  │  │ ...                                                       │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                          mb-6    │  │
│  │  ┌───────────────────────────────────────────────────────────┐   │  │
│  │  │ THINKING INDICATOR (conditional)          glass-card p-4  │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                          mb-6    │  │
│  │  ┌───────────────────────────────────────────────────────────┐   │  │
│  │  │ ERROR BANNER (conditional)                glass-card p-5  │   │  │
│  │  │ ...                                                       │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                          mb-6    │  │
│  │  ┌───────────────────────────────────────────────────────────┐   │  │
│  │  │ FINAL DIAGNOSIS CARD (conditional)        glass-card p-6  │   │  │
│  │  │ ...                                                       │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                                   │  │
│  │  HEALTH DOT                                            mt-8      │  │
│  │  "API: ● Connected"   text-xs text-muted                        │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Card 1: Alert Input

**Visibility**: Always visible

```
┌─────────────────────────────────────────────────────────────────┐
│  glass-card  (bg-white/5  backdrop-blur-md  border-white/10)    │
│  rounded-xl  p-6                                                │
│                                                                 │
│  label: "Alert"                                                 │
│  text-sm font-medium text-text-secondary                        │
│                                                          mb-2   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  textarea: glass-input  3 rows                            │  │
│  │  bg-white/5  border-white/10  rounded-lg  p-3  text-sm    │  │
│  │                                                           │  │
│  │  "14:31:14.259 CRITICAL VPN-ACME-CORP                     │  │
│  │   SERVICE_DEGRADATION VPN tunnel unreachable —            │  │
│  │   primary MPLS path down"                                 │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                          mt-4   │
│  ┌──────────────┐                                               │
│  │  Send Alert   │  bg-brand (#8251EE)  text-white  rounded-lg │
│  │               │  px-6 py-2  text-sm font-medium             │
│  └──────────────┘  hover: bg-brand-hover (#9366F5)             │
│                    disabled: opacity-50 when running            │
│                    Shows "Running..." when active               │
│                                                                 │
│  Button animations:                                             │
│  • whileHover: scale(1.02)                                      │
│  • whileTap: scale(0.98)                                        │
│  • spring stiffness=400 damping=17                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Card 2: Running Indicator

**Visibility**: When `running && runStarted && steps.length === 0 && !thinking`
(only during the brief window after run starts but before any step/thinking
events arrive)

```
┌─────────────────────────────────────────────────────────────────┐
│  glass-card  p-6                                                │
│                                                                 │
│  ┌─────────────────────────────────────────────────────┐       │
│  │  ●  "Orchestrator is starting..."                   │       │
│  │  animate-pulse h-2 w-2 rounded-full bg-brand        │       │
│  │  text-sm text-text-secondary                        │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                 │
│  AnimatePresence: fadeSlideUp in, slide-up-10 out               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Card 3: Agent Steps Timeline

**Visibility**: When `steps.length > 0` (persists after run completes)

```
┌─────────────────────────────────────────────────────────────────┐
│  glass-card  p-6                                                │
│                                                                 │
│  h2: "Agent Steps"                                              │
│  text-lg font-semibold text-text-primary               mb-4    │
│                                                                 │
│  ┌── stagger container (delay 0.1s, stagger 0.05s) ─────────┐ │
│  │                                                            │ │
│  │  ╎  Step 1  GraphExplorerAgent              4.2s          │ │
│  │  ╎  ├─ border-l-2 border-brand (#8251EE)  pl-4           │ │
│  │  ╎  ├─ step number: text-sm font-medium text-brand        │ │
│  │  ╎  ├─ agent name: text-sm text-text-primary              │ │
│  │  ╎  ├─ duration: text-xs text-text-muted                  │ │
│  │  ╎  │                                                      │ │
│  │  ╎  ├─ Query: (text-xs text-text-muted)                   │ │
│  │  ╎  │  "font-medium" label, then ReactMarkdown of query   │ │
│  │  ╎  │  rendered in prose prose-xs prose-invert             │ │
│  │  ╎  │                                                      │ │
│  │  ╎  └─ Response: (text-xs text-text-secondary)            │ │
│  │  ╎     ReactMarkdown of response                           │ │
│  │  ╎     prose prose-xs prose-invert max-w-none              │ │
│  │  ╎                                                   mt-2  │ │
│  │  │                                                  gap-3  │ │
│  │  ╎  Step 2  TelemetryAgent                  3.5s          │ │
│  │  ╎  ├─ Query: "AlertStream | where EntityId == ..."       │ │
│  │  ╎  └─ Response: "Found 12 alerts for LINK-SYD-..."       │ │
│  │  │                                                         │ │
│  │  ╎  Step 3  RunbookKBAgent                  2.1s          │ │
│  │  ╎  ├─ Query: "fibre cut runbook procedures"              │ │
│  │  ╎  └─ Response: "## Fibre Cut Runbook ..."               │ │
│  │  │                                                         │ │
│  │  ╎  Step 4  HistoricalTicketAgent           1.8s          │ │
│  │  ╎  ├─ Query: "fibre cut Sydney Melbourne precedent"      │ │
│  │  ╎  └─ Response: "INC-2025-0847: Similar fibre..."        │ │
│  │  │                                                         │ │
│  │  ╎  Step 5  GraphExplorerAgent              3.9s          │ │
│  │  ╎  └─ (second call — blast radius check)                 │ │
│  │  │                                                         │ │
│  │  ╎  Step 6  TelemetryAgent                  2.7s          │ │
│  │  ╎  └─ (second call — latency metrics)                    │ │
│  │  │                                                         │ │
│  │  └────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Step card structure (per step):**

```
  border-l-2 border-brand  pl-4

  ┌─────────────────────────────────────────────────────┐
  │  flex items-center gap-2                             │
  │  ┌──────────┐ ┌────────────────────┐ ┌──────┐      │
  │  │ Step {n}  │ │ {agent name}       │ │{dur} │      │
  │  │ text-brand│ │ text-text-primary  │ │muted │      │
  │  │ font-med  │ │                    │ │text-xs│     │
  │  └──────────┘ └────────────────────┘ └──────┘      │
  │                                                      │
  │  Query: {query text}                       mt-1     │
  │  text-xs text-text-muted                             │
  │  label is font-medium, content is ReactMarkdown      │
  │                                                      │
  │  Response:                                 mt-2     │
  │  {response text — rendered as markdown}              │
  │  text-xs text-text-secondary                         │
  │  prose prose-xs prose-invert max-w-none              │
  └─────────────────────────────────────────────────────┘
```

---

## Card 4: Thinking Indicator

**Visibility**: When `thinking !== null` (transient — appears between steps,
disappears when `step_complete` arrives)

```
┌─────────────────────────────────────────────────────────────────┐
│  glass-card  p-4                                                │
│                                                                 │
│  ┌─────────────────────────────────────────────────────┐       │
│  │  ● ● ●  "{agent} — {status}"                       │       │
│  │                                                     │       │
│  │  Three bouncing dots:                               │       │
│  │    h-1.5 w-1.5 rounded-full bg-brand                │       │
│  │    animate-bounce with staggered delays             │       │
│  │    0ms / 150ms / 300ms                              │       │
│  │                                                     │       │
│  │  Text: text-sm text-text-secondary                  │       │
│  │  e.g. "Orchestrator — calling sub-agent..."         │       │
│  │  e.g. "GraphExplorerAgent — processing..."          │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                 │
│  AnimatePresence: fast transition 0.2s                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Card 5: Error Banner

**Visibility**: When `errorMessage` is non-empty (persists until next submission)

```
┌─────────────────────────────────────────────────────────────────┐
│  glass-card  p-5  border border-status-error/30                 │
│  (red-tinted border on top of glassmorphism)                    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────┐       │
│  │  flex items-start gap-3                             │       │
│  │                                                     │       │
│  │  !   "Agent run interrupted"                        │       │
│  │  │    text-status-error text-lg                     │       │
│  │  │    (red exclamation, 0.5 top offset)             │       │
│  │  │                                                  │       │
│  │  │    Error message (smart contextual text):        │       │
│  │  │    • 404 → "Fabric graph model may still be      │       │
│  │  │            refreshing after ontology update..."   │       │
│  │  │    • 429 → "Rate-limited by Azure AI..."         │       │
│  │  │    • 400 → "Backend query returned an error..."  │       │
│  │  │    • else → first 200 chars of raw error         │       │
│  │  │                                                  │       │
│  │  │    text-xs text-text-muted                       │       │
│  │  │                                                  │       │
│  │  │    "{n} step(s) completed before the error —     │       │
│  │  │     results shown above."                        │       │
│  │  │    (only if steps.length > 0)                    │       │
│  │  │                                                  │       │
│  │  │    ┌────────┐                                    │       │
│  │  │    │ Retry  │  bg-brand text-white rounded-md   │       │
│  │  │    └────────┘  px-4 py-1.5 text-xs font-medium  │       │
│  │  │                                                  │       │
│  │  └──────────────────────────────────────────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Card 6: Final Diagnosis

**Visibility**: When `finalMessage` is non-empty (persists until next submission)

```
┌─────────────────────────────────────────────────────────────────┐
│  glass-card  p-6                                                │
│                                                                 │
│  h2: "Diagnosis"                                                │
│  text-lg font-semibold text-text-primary               mb-4    │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ReactMarkdown content                                    │  │
│  │  prose prose-sm prose-invert max-w-none                   │  │
│  │  text-sm text-text-secondary                              │  │
│  │                                                           │  │
│  │  Typical rendered content:                                │  │
│  │                                                           │  │
│  │  ## Situation Report                                      │  │
│  │                                                           │  │
│  │  ### 1. Incident Summary                                  │  │
│  │  Primary fibre link LINK-SYD-MEL-FIBRE-01 is down...     │  │
│  │                                                           │  │
│  │  ### 2. Blast Radius                                      │  │
│  │  - MPLS-PATH-SYD-MEL-PRIMARY affected                    │  │
│  │  - Services: VPN-ACME-CORP, VPN-BIGBANK, ...             │  │
│  │  - Total customers: ~5,650                                │  │
│  │                                                           │  │
│  │  ### 3. Top 3 Probable Root Causes                        │  │
│  │  1. Fibre cut on SYD→MEL backbone                        │  │
│  │  2. DWDM amplifier failure                               │  │
│  │  3. Scheduled maintenance not communicated               │  │
│  │                                                           │  │
│  │  ### 4. Recommended Actions                               │  │
│  │  - Verify MPLS-PATH-SYD-MEL-SECONDARY is active          │  │
│  │  - Initiate traffic engineering reroute                   │  │
│  │  - Dispatch fibre crew to splice point                    │  │
│  │                                                           │  │
│  │  ### 5. Historical Precedents                             │  │
│  │  - INC-2025-0847 (similar fibre cut, 4h TTR)             │  │
│  │                                                           │  │
│  │  ### 6. Risk Assessment                                   │  │
│  │  SLA breach risk: HIGH (VPN-ACME-CORP GOLD SLA,          │  │
│  │  $50k/hr penalty)                                         │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Health Dot (Footer)

**Visibility**: Always visible

```
  mt-8  text-xs text-text-muted

  "API: ● Connected"     text-status-success (#10B981) — green
  "API: ● Disconnected"  text-status-error   (#EF4444) — red
  "API: ..."             text-text-muted     (#71717A) — loading

  Checked once on mount: fetch('/health')
```

---

## State Machine

```
                     ┌──────────┐
                     │   IDLE   │  All cards hidden except Alert Input + Health
                     └────┬─────┘
                          │ user clicks "Send Alert"
                          ▼
                 ┌─────────────────┐
                 │  RUNNING START  │  Running indicator visible
                 │  button: disabled│  "Orchestrator is starting…"
                 └────────┬────────┘
                          │ SSE: step_thinking
                          ▼
                 ┌─────────────────┐
                 │    THINKING     │  Thinking indicator: "● ● ● agent — status"
                 │                 │  Running indicator hidden
                 └────────┬────────┘
                          │ SSE: step_complete
                          ▼
          ┌───────────────────────────────┐
          │       STEPS ACCUMULATING      │  Steps timeline grows
          │  (cycles back to THINKING     │  Thinking appears between steps
          │   for each sub-agent call)    │
          └───────────────┬───────────────┘
                          │ SSE: message
                          ▼
                 ┌─────────────────┐
                 │  DIAGNOSIS SHOWN │  Final diagnosis card rendered
                 │  button: enabled │  Steps timeline persists above
                 └─────────────────┘

          At any point: SSE error → ERROR state (banner shown, retry button)
```

**State variables:**

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `alert` | `string` | Pre-filled sample | Textarea value |
| `steps` | `StepEvent[]` | `[]` | Accumulated completed steps |
| `thinking` | `ThinkingState \| null` | `null` | Current thinking indicator |
| `finalMessage` | `string` | `''` | Diagnosis markdown |
| `errorMessage` | `string` | `''` | Error message text |
| `running` | `boolean` | `false` | SSE stream active |
| `runStarted` | `boolean` | `false` | `run_start` event received |

---

## SSE Event → State Mapping

| SSE Event | State Changes |
|-----------|---------------|
| `run_start` | `runStarted = true` |
| `step_thinking` | `thinking = {agent, status}` |
| `step_start` | `thinking = {agent, status: "processing..."}` |
| `step_complete` | `thinking = null`, `steps = [...prev, data]` |
| `message` | `thinking = null`, `finalMessage = data.text` |
| `run_complete` | `thinking = null` |
| `error` | `thinking = null`, `errorMessage = data.message` |
| Stream ends | `running = false` |

---

## Visual Theme

### Color Palette

```
Background layers:
  bg1: hsl(240, 6%, 10%)    ████  near-black (body)
  bg2: hsl(240, 5%, 12%)    ████  slightly lighter
  bg3: hsl(240, 5%, 14%)    ████  card hover
  bg4: hsl(240, 4%, 18%)    ████
  bg5: hsl(240, 4%, 22%)    ████  scrollbar thumb
  bg6: hsl(240, 4%, 26%)    ████

Brand:
  brand:       #8251EE      ████  purple (buttons, accents, step borders)
  brand-hover: #9366F5      ████  lighter purple (hover states)
  brand-light: #A37EF5      ████
  brand-subtle: rgba(130,81,238,0.15)

Text:
  primary:   #FFFFFF         ████  headings, agent names
  secondary: #A1A1AA         ████  body text, responses
  muted:     #71717A         ████  labels, durations, queries

Status:
  success: #10B981          ████  green (health OK)
  warning: #F59E0B          ████  amber
  error:   #EF4444          ████  red (error banner, health fail)
  info:    #3B82F6          ████  blue
```

### Glassmorphism Classes

| Class | Properties |
|-------|------------|
| `.glass-card` | `backdrop-blur-md bg-white/5 border border-white/10 rounded-xl` |
| `.glass-panel` | `backdrop-blur-lg bg-black/40 border border-white/5` |
| `.glass-overlay` | `backdrop-blur-sm bg-black/60` |
| `.glass-input` | `backdrop-blur-sm bg-white/5 border border-white/10 focus:border-brand focus:bg-white/10` |

### Typography

- Font: `Segoe UI`, `system-ui`, `sans-serif`
- Headings: `text-text-primary` (#FFF), `font-semibold`
- Body: `text-text-secondary` (#A1A1AA)
- Labels/metadata: `text-text-muted` (#71717A), `text-xs`
- Markdown: Tailwind Typography plugin (`prose prose-invert`)

### Animations

| Element | Animation | Params |
|---------|-----------|--------|
| Cards appear | fadeSlideUp | `opacity 0→1, y 20→0, 300ms easeOut` |
| Cards exit | fadeSlideUp exit | `opacity 1→0, y 0→20` |
| Steps stagger | staggerContainer | `stagger 50ms, delay 100ms` |
| Each step | staggerItem | `opacity 0→1, y 10→0, 200ms easeOut` |
| Submit button | spring | `scale hover 1.02, tap 0.98, stiffness 400, damping 17` |
| Thinking dots | bounce | `3 dots, stagger 150ms` |
| Running dot | pulse | `h-2 w-2 bg-brand` |
| Thinking card | fast transition | `200ms` |

---

## Architecture Notes

### Single-File Frontend

Everything lives in `App.tsx` (~250 lines). No component extraction, no stores,
no routing. This was appropriate for the prototype but is the first thing that
needs to change for V3 enhancements (graph viz, sub-agent detail, fault
injection panel).

### SSE Connection

```
POST /api/alert  →  {text: string}
      ↓
Server: EventSourceResponse (sse-starlette)
      ↓
Client: @microsoft/fetch-event-source
      ↓
Events processed in onmessage callback
```

- `openWhenHidden: true` — keeps stream alive if browser tab loses focus
- Abort via `AbortController` — previous run cancelled on resubmit
- Error handling: `onerror` throws to close stream; catch block in outer try

### No Routing

Single page. No React Router. The entire app is one vertical scroll of cards.
A router would be needed if we add separate pages (e.g., graph explorer, config,
history) but for a dashboard-style demo, single-page is appropriate.

### No State Management Library

All state is `useState` in the root `App` component. No Zustand, no context
providers. V3 should introduce Zustand (per `zustand-store-ts` skill) when:
- Graph topology state needs to be shared across graph panel + step cards
- Sub-agent enrichment data needs async updates after initial render
- Multiple panels need coordinated state (alert input, graph viz, timeline)

### Proxy Configuration

Vite dev server proxies `/api/*` and `/health` to `http://localhost:8000`
(the FastAPI backend). No CORS needed in dev mode.
