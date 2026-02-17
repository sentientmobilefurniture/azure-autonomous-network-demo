# V3 Proposed UI: NOC Dashboard Layout

## Design Philosophy

The current UI is a vertical scroll of cards — functional but not "demo-ready".
A NOC dashboard should feel like a **command centre**: information-dense, always
visible, no scrolling the whole page. The operator sees everything at a glance.

Key principles:
- **Full viewport** — no page scroll, panels fill the screen
- **Three zones** — metrics bar (top), investigation panel (left), diagnosis panel (right)
- **Always-on context** — alert chart and counters visible throughout investigation
- **Progressive disclosure** — sub-agent steps are scrollable within their panel

---

## Full-Screen Layout

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  HEADER BAR                                                          h-12      │
│  "Autonomous Network NOC"                              ● API  ● Agents  theme │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  METRICS BAR                                                         h-24      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────────────┐  │
│  │ Active   │ │ Services │ │ SLA At   │ │ Anomalies│ │  ALERT CHART        │  │
│  │ Alerts   │ │ Impacted │ │ Risk     │ │ (24h)    │ │  (image / embed)    │  │
│  │   12     │ │    3     │ │  $115k   │ │   231    │ │                     │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────────────────┘  │
│                                                                                 │
├────────────────────────────────────┬────────────────────────────────────────────┤
│                                    │                                            │
│  INVESTIGATION PANEL         ~50%  │  DIAGNOSIS PANEL                     ~50% │
│  (scrollable)                      │  (scrollable)                              │
│                                    │                                            │
│  ┌──────────────────────────────┐  │  ┌──────────────────────────────────────┐  │
│  │ Alert Input                  │  │  │                                      │  │
│  │ ┌──────────────────────────┐ │  │  │  (empty state)                       │  │
│  │ │ textarea (2 rows)       │ │  │  │                                      │  │
│  │ └──────────────────────────┘ │  │  │  "Submit an alert to begin           │  │
│  │ [Send Alert]                 │  │  │   investigation"                     │  │
│  └──────────────────────────────┘  │  │                                      │  │
│                                    │  │  — or —                              │  │
│  ┌──────────────────────────────┐  │  │                                      │  │
│  │ Agent Steps (scrollable)     │  │  │  (after investigation completes)     │  │
│  │                              │  │  │                                      │  │
│  │  ● Step 1 GraphExplorer 4.2s│  │  │  ## Situation Report                 │  │
│  │  ● Step 2 Telemetry    3.5s │  │  │                                      │  │
│  │  ● Step 3 RunbookKB    2.1s │  │  │  ### 1. Incident Summary             │  │
│  │  ● Step 4 Historical   1.8s │  │  │  Primary fibre link...              │  │
│  │  ● Step 5 GraphExplorer 3.9s│  │  │                                      │  │
│  │  ● Step 6 Telemetry    2.7s │  │  │  ### 2. Blast Radius                 │  │
│  │  ● ● ● thinking...         │  │  │  - MPLS-PATH-SYD-MEL-PRIMARY...      │  │
│  │                              │  │  │                                      │  │
│  └──────────────────────────────┘  │  │  ### 3. Root Causes                  │  │
│                                    │  │  1. Fibre cut on SYD→MEL             │  │
│                                    │  │                                      │  │
│                                    │  │  ### 4. Recommended Actions           │  │
│                                    │  │  ...                                 │  │
│                                    │  │                                      │  │
│                                    │  └──────────────────────────────────────┘  │
│                                    │                                            │
└────────────────────────────────────┴────────────────────────────────────────────┘
```

---

## Zone 1: Header Bar

Fixed top bar. Minimal — just branding and status indicators.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  h-12  bg-neutral-bg2  border-b border-white/10                            │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  flex items-center justify-between px-6                               │ │
│  │                                                                        │ │
│  │  LEFT:                                                                 │ │
│  │    ◆ Autonomous Network NOC                                           │ │
│  │    brand icon (or just ◆)  text-lg font-semibold text-text-primary    │ │
│  │    "Multi-agent diagnosis"  text-xs text-text-muted  ml-3             │ │
│  │                                                                        │ │
│  │  RIGHT:                                                                │ │
│  │    ● API Connected     text-xs text-status-success                    │ │
│  │    ● 5 Agents Active   text-xs text-status-success                    │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Zone 2: Metrics Bar

A horizontal strip of KPI cards + an alert chart thumbnail. This gives the
"command centre" feel and provides context throughout the investigation.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  h-24  px-6  py-3  flex gap-4  items-stretch                               │
│                                                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │ glass-card   │ │ glass-card   │ │ glass-card   │ │ glass-card   │        │
│  │ p-3 flex-1   │ │ p-3 flex-1   │ │ p-3 flex-1   │ │ p-3 flex-1   │      │
│  │              │ │              │ │              │ │              │         │
│  │ ACTIVE       │ │ SERVICES     │ │ SLA AT       │ │ ANOMALIES    │        │
│  │ ALERTS       │ │ IMPACTED     │ │ RISK         │ │ (24h)        │        │
│  │ text-xs      │ │ text-xs      │ │ text-xs      │ │ text-xs      │        │
│  │ text-muted   │ │ text-muted   │ │ text-muted   │ │ text-muted   │       │
│  │              │ │              │ │              │ │              │         │
│  │     12       │ │      3       │ │   $115k/hr   │ │     231      │        │
│  │ text-2xl     │ │ text-2xl     │ │ text-2xl     │ │ text-2xl     │        │
│  │ font-bold    │ │ font-bold    │ │ font-bold    │ │ font-bold    │        │
│  │ text-error   │ │ text-warning │ │ text-error   │ │ text-brand   │        │
│  │              │ │              │ │              │ │              │         │
│  │ ▲ 4 vs 1h   │ │              │ │              │ │ ▲ 87 vs avg  │        │
│  │ text-xs red  │ │              │ │              │ │ text-xs red  │         │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │  ALERT CHART                                    flex-[2]       │        │
│  │  glass-card  p-3  overflow-hidden                              │        │
│  │                                                                │        │
│  │  Phase 1: static <img> of the anomaly detection chart          │        │
│  │           (the LinkTelemetry detector screenshot)               │        │
│  │           object-cover  rounded-lg  opacity-90                 │        │
│  │                                                                │        │
│  │  Phase 2: live embed from Fabric Real-Time Dashboard           │        │
│  │           or a Recharts/D3 mini-chart fed from /query/telemetry│        │
│  │                                                                │        │
│  │  Bottom-left overlay:                                          │        │
│  │    "LinkTelemetry · 231 anomalies"  text-xs text-muted        │        │
│  │    absolute bottom-2 left-3  bg-black/60 px-2 py-0.5 rounded │        │
│  │                                                                │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Metric Card Component

```
┌─────────────────────────┐
│  glass-card  p-3         │
│  min-w-[140px]  flex-1   │
│                          │
│  "ACTIVE ALERTS"         │  ← text-[10px] uppercase tracking-wider
│  text-text-muted         │     font-medium  letter-spacing: 0.1em
│                          │
│       12                 │  ← text-2xl font-bold
│  text-status-error       │     color varies by metric severity
│                          │
│  ▲ 4 vs 1h ago           │  ← text-[10px] text-status-error
│  (optional trend line)   │     delta indicator (optional)
│                          │
└─────────────────────────┘
```

**Metric values** (hardcoded for Phase 1, later fed from backend):

| Metric | Value | Color | Delta |
|--------|-------|-------|-------|
| Active Alerts | 12 | `text-status-error` (red) | ▲ 4 vs 1h |
| Services Impacted | 3 | `text-status-warning` (amber) | — |
| SLA At Risk | $115k/hr | `text-status-error` (red) | — |
| Anomalies (24h) | 231 | `text-brand` (purple) | ▲ 87 vs avg |

These numbers come from the demo scenario: 3 services (VPN-ACME-CORP,
VPN-BIGBANK, BB-BUNDLE-SYD-NORTH) impacted by the LINK-SYD-MEL-FIBRE-01
failure, with total SLA penalty of $50k + $25k + ... per hour.

---

## Zone 3: Main Content — Two-Panel Split

The remaining viewport height is split into two side-by-side panels. Both are
independently scrollable.

```
┌────────────────────────────────┬────────────────────────────────────────┐
│  INVESTIGATION PANEL           │  DIAGNOSIS PANEL                       │
│  w-1/2 (or w-[45%])           │  w-1/2 (or w-[55%])                   │
│  flex flex-col                 │  flex flex-col                         │
│  h-[calc(100vh-h_header-h_bar)]│  h-[calc(100vh-h_header-h_bar)]       │
│  overflow-y-auto               │  overflow-y-auto                       │
│  p-4                           │  p-4                                   │
│  border-r border-white/10      │                                        │
└────────────────────────────────┴────────────────────────────────────────┘
```

### Left Panel: Investigation

This panel contains the alert input and the live agent execution timeline.
It scrolls independently.

```
┌──────────────────────────────────────┐
│  INVESTIGATION PANEL                  │
│  p-4  overflow-y-auto                 │
│  border-r border-white/10             │
│                                       │
│  ┌────────────────────────────────┐  │
│  │  ALERT INPUT                    │  │
│  │  glass-card  p-4                │  │
│  │                                 │  │
│  │  "Submit Alert"                 │  │
│  │  text-xs uppercase tracking-w   │  │
│  │  text-text-muted font-medium    │  │
│  │                                 │  │
│  │  ┌───────────────────────────┐  │  │
│  │  │ textarea  2 rows          │  │  │
│  │  │ glass-input  text-sm      │  │  │
│  │  │ "14:31:14.259 CRITICAL    │  │  │
│  │  │  VPN-ACME-CORP ..."       │  │  │
│  │  └───────────────────────────┘  │  │
│  │                          mt-3   │  │
│  │  ┌────────────┐                 │  │
│  │  │ Investigate │ bg-brand  w-full │ │
│  │  └────────────┘ rounded-lg      │  │
│  │                                 │  │
│  └────────────────────────────────┘  │
│                              mb-4    │
│  ┌────────────────────────────────┐  │
│  │  AGENT TIMELINE                 │  │
│  │  (appears after submit)         │  │
│  │                                 │  │
│  │  "Investigation"                │  │
│  │  text-xs uppercase text-muted   │  │
│  │                                 │  │
│  │  ┌─ step ──────────────────┐   │  │
│  │  │ ● GraphExplorerAgent    │   │  │
│  │  │   4.2s                  │   │  │
│  │  │   ▸ Query: {...}        │   │  │
│  │  │   ▸ Response: (trunc)   │   │  │
│  │  └─────────────────────────┘   │  │
│  │  ┌─ step ──────────────────┐   │  │
│  │  │ ● TelemetryAgent       │   │  │
│  │  │   3.5s                  │   │  │
│  │  │   ▸ Query: {...}        │   │  │
│  │  │   ▸ Response: (trunc)   │   │  │
│  │  └─────────────────────────┘   │  │
│  │  ┌─ step ──────────────────┐   │  │
│  │  │ ● RunbookKBAgent       │   │  │
│  │  │   2.1s                  │   │  │
│  │  └─────────────────────────┘   │  │
│  │  ┌─ step ──────────────────┐   │  │
│  │  │ ● HistoricalTicketAgent│   │  │
│  │  │   1.8s                  │   │  │
│  │  └─────────────────────────┘   │  │
│  │                                 │  │
│  │  ● ● ●  thinking...            │  │
│  │  (bouncing dots, appears       │  │
│  │   between steps)               │  │
│  │                                 │  │
│  │  ┌─ step ──────────────────┐   │  │
│  │  │ ● GraphExplorerAgent    │   │  │
│  │  │   3.9s                  │   │  │
│  │  └─────────────────────────┘   │  │
│  │  ┌─ step ──────────────────┐   │  │
│  │  │ ● TelemetryAgent       │   │  │
│  │  │   2.7s                  │   │  │
│  │  └─────────────────────────┘   │  │
│  │                                 │  │
│  │  ── Run complete ──             │  │
│  │  6 steps · 4,200 tokens · 35s  │  │
│  │  text-xs text-text-muted        │  │
│  │                                 │  │
│  └────────────────────────────────┘  │
│                                       │
│  ┌────────────────────────────────┐  │
│  │  ERROR BANNER (if error)       │  │
│  │  glass-card border-error/30    │  │
│  │  ! Agent run interrupted       │  │
│  │  [Retry]                       │  │
│  └────────────────────────────────┘  │
│                                       │
└──────────────────────────────────────┘
```

### Step Card (Compact Timeline Style)

For the investigation panel, steps should be **compact** — detailed expansion
is a later enhancement (V3UIENHANCEMENT.md). Default: collapsed with key info.

```
┌─────────────────────────────────────────┐
│  glass-card  p-3  mb-2                   │
│                                          │
│  flex items-center justify-between       │
│  ┌────────────────────────────┐ ┌─────┐ │
│  │ ● GraphExplorerAgent       │ │4.2s │ │
│  │ h-2 w-2 bg-brand rounded   │ │muted│ │
│  │ text-sm text-text-primary   │ └─────┘ │
│  └────────────────────────────┘          │
│                                          │
│  ▸ Query:  {"question": "What links...  │  ← collapsed by default
│  text-xs text-text-muted  truncate       │     click ▸ to expand
│                                          │
│  ▸ Response: "Two transport links..."    │  ← collapsed by default
│  text-xs text-text-muted  truncate       │     click ▸ to expand
│                                          │
└─────────────────────────────────────────┘
```

Expanded state (click on a step):
```
┌─────────────────────────────────────────┐
│  glass-card  p-3  mb-2                   │
│  border border-brand/30                  │  ← highlighted when expanded
│                                          │
│  ● GraphExplorerAgent              4.2s  │
│                                          │
│  ▾ Query:                                │
│  ┌───────────────────────────────────┐   │
│  │ {"question": "What transport      │   │
│  │  links connect Sydney to          │   │
│  │  Melbourne?"}                     │   │
│  └───────────────────────────────────┘   │
│  text-xs  bg-white/5 rounded p-2         │
│                                          │
│  ▾ Response:                             │
│  ┌───────────────────────────────────┐   │
│  │ There are two transport links     │   │
│  │ between Sydney and Melbourne:     │   │
│  │ LINK-SYD-MEL-FIBRE-01 (DWDM_100G)│   │
│  │ LINK-SYD-MEL-FIBRE-02 (DWDM_100G)│   │
│  └───────────────────────────────────┘   │
│  text-xs  prose prose-xs prose-invert    │
│                                          │
└─────────────────────────────────────────┘
```

---

### Right Panel: Diagnosis

Displays the orchestrator's final markdown response. Large, readable, scrollable.
This is the "deliverable" — what the NOC operator would read, screenshot, or
hand to a manager.

```
┌──────────────────────────────────────────┐
│  DIAGNOSIS PANEL                          │
│  p-4  overflow-y-auto                     │
│                                           │
│  ── BEFORE INVESTIGATION ──               │
│                                           │
│  ┌──────────────────────────────────────┐│
│  │  glass-card  p-6                      ││
│  │  flex flex-col items-center           ││
│  │  justify-center  h-full  text-center  ││
│  │                                       ││
│  │  ◇                                    ││
│  │  (subtle icon, brand color, opacity)  ││
│  │                                       ││
│  │  "Submit an alert to begin"           ││
│  │  text-sm text-text-muted              ││
│  │                                       ││
│  │  "The orchestrator will coordinate"   ││
│  │  "specialist agents to diagnose"      ││
│  │  "the incident."                      ││
│  │  text-xs text-text-muted mt-2         ││
│  │                                       ││
│  └──────────────────────────────────────┘│
│                                           │
│  ── DURING INVESTIGATION ──               │
│                                           │
│  ┌──────────────────────────────────────┐│
│  │  glass-card  p-6                      ││
│  │                                       ││
│  │  "Diagnosis"                          ││
│  │  text-xs uppercase tracking-wider     ││
│  │  text-text-muted font-medium          ││
│  │                                       ││
│  │  ┌────────────────────────────────┐   ││
│  │  │                                │   ││
│  │  │  Streaming dots or skeleton    │   ││
│  │  │  "Agents are investigating..." │   ││
│  │  │                                │   ││
│  │  └────────────────────────────────┘   ││
│  │                                       ││
│  └──────────────────────────────────────┘│
│                                           │
│  ── AFTER INVESTIGATION ──                │
│                                           │
│  ┌──────────────────────────────────────┐│
│  │  glass-card  p-6                      ││
│  │                                       ││
│  │  "Diagnosis"         [Copy] [Export]  ││
│  │  text-xs uppercase    text-xs buttons ││
│  │                                       ││
│  │  ┌────────────────────────────────┐   ││
│  │  │                                │   ││
│  │  │  ## Situation Report           │   ││
│  │  │                                │   ││
│  │  │  ### 1. Incident Summary       │   ││
│  │  │  Primary fibre link            │   ││
│  │  │  LINK-SYD-MEL-FIBRE-01 is      │   ││
│  │  │  experiencing a total failure  │   ││
│  │  │  affecting traffic between     │   ││
│  │  │  Sydney and Melbourne...       │   ││
│  │  │                                │   ││
│  │  │  ### 2. Blast Radius           │   ││
│  │  │  **Affected MPLS Paths:**      │   ││
│  │  │  - MPLS-PATH-SYD-MEL-PRIMARY  │   ││
│  │  │                                │   ││
│  │  │  **Affected Services:**        │   ││
│  │  │  | Service | Type | Users |    │   ││
│  │  │  |---------|------|-------|    │   ││
│  │  │  | VPN-ACME | VPN | 450  |    │   ││
│  │  │  | VPN-BIGBANK | VPN | 1200|  │   ││
│  │  │                                │   ││
│  │  │  ### 3. Top 3 Root Causes      │   ││
│  │  │  1. Fibre cut between SYD-MEL  │   ││
│  │  │  2. DWDM amplifier failure     │   ││
│  │  │  3. Unannounced maintenance    │   ││
│  │  │                                │   ││
│  │  │  ### 4. Recommended Actions    │   ││
│  │  │  1. Verify secondary MPLS path │   ││
│  │  │  2. Initiate TE reroute        │   ││
│  │  │  3. Dispatch fibre crew        │   ││
│  │  │                                │   ││
│  │  │  ### 5. Historical Precedents  │   ││
│  │  │  - INC-2025-0847 (4h TTR)     │   ││
│  │  │                                │   ││
│  │  │  ### 6. Risk Assessment        │   ││
│  │  │  SLA breach: HIGH              │   ││
│  │  │  $115,000/hr combined penalty  │   ││
│  │  │                                │   ││
│  │  └────────────────────────────────┘   ││
│  │                                       ││
│  │  prose prose-sm prose-invert          ││
│  │  max-w-none                           ││
│  │                                       ││
│  │  ── Footer ──                         ││
│  │  "6 agent steps · 4,200 tokens · 35s"││
│  │  text-xs text-text-muted border-t     ││
│  │  border-white/5 pt-3 mt-6            ││
│  │                                       ││
│  └──────────────────────────────────────┘│
│                                           │
└──────────────────────────────────────────┘
```

---

## Responsive Behaviour

The dashboard is optimised for **widescreen demo** (1920×1080 or larger).
On smaller viewports, the two-panel split stacks vertically.

```
Breakpoints:
  lg (≥1024px):  Side-by-side panels, metrics bar with chart
  md (768-1023): Side-by-side panels, chart hidden (metrics only)
  sm (<768px):   Stacked vertically (investigation → diagnosis)
```

```
┌─────────────────────────── sm / mobile ───────────────────────────┐
│  HEADER BAR                                                       │
├───────────────────────────────────────────────────────────────────┤
│  METRICS (2×2 grid, no chart)                                     │
│  ┌──────────┐ ┌──────────┐                                       │
│  │ Alerts:12│ │ Svc: 3   │                                       │
│  └──────────┘ └──────────┘                                       │
│  ┌──────────┐ ┌──────────┐                                       │
│  │ SLA:$115k│ │ Anom:231 │                                       │
│  └──────────┘ └──────────┘                                       │
├───────────────────────────────────────────────────────────────────┤
│  INVESTIGATION PANEL (full width, scrollable)                     │
│  Alert input → Agent steps                                        │
├───────────────────────────────────────────────────────────────────┤
│  DIAGNOSIS PANEL (full width, scrollable)                         │
│  Final response markdown                                          │
└───────────────────────────────────────────────────────────────────┘
```

---

## CSS Grid Structure

```tsx
<div className="h-screen flex flex-col bg-neutral-bg1">
  {/* Zone 1: Header */}
  <header className="h-12 bg-neutral-bg2 border-b border-white/10 ...">
    ...
  </header>

  {/* Zone 2: Metrics Bar */}
  <div className="h-24 px-6 py-3 flex gap-4 border-b border-white/10">
    <MetricCard ... />
    <MetricCard ... />
    <MetricCard ... />
    <MetricCard ... />
    <AlertChart ... />
  </div>

  {/* Zone 3: Two-panel split — fills remaining height */}
  <div className="flex-1 flex min-h-0">

    {/* Left: Investigation */}
    <div className="w-1/2 border-r border-white/10 overflow-y-auto p-4">
      <AlertInput ... />
      <AgentTimeline ... />
    </div>

    {/* Right: Diagnosis */}
    <div className="w-1/2 overflow-y-auto p-4">
      <DiagnosisPanel ... />
    </div>

  </div>
</div>
```

Key CSS:
- `h-screen flex flex-col` — viewport-filling, no page scroll
- `flex-1 min-h-0` on the main content area — critical for nested scroll
- `overflow-y-auto` on each panel — independent scrolling
- `w-1/2` split (adjustable to `w-[45%]` / `w-[55%]` if diagnosis needs more room)

---

## Component Extraction Plan

The current monolithic `App.tsx` needs to be split into components:

```
frontend/src/
├── App.tsx                    # Layout shell (grid, zones)
├── main.tsx                   # ReactDOM entry
├── components/
│   ├── Header.tsx             # Zone 1: branding + status dots
│   ├── MetricsBar.tsx         # Zone 2: container for metric cards + chart
│   ├── MetricCard.tsx         # Individual KPI card
│   ├── AlertChart.tsx         # Chart thumbnail (img for now)
│   ├── InvestigationPanel.tsx # Zone 3 left: alert input + timeline
│   ├── AlertInput.tsx         # Textarea + submit button
│   ├── AgentTimeline.tsx      # List of step cards + thinking indicator
│   ├── StepCard.tsx           # Individual step (collapsible)
│   ├── ThinkingDots.tsx       # Bouncing dots indicator
│   ├── ErrorBanner.tsx        # Error display with retry
│   ├── DiagnosisPanel.tsx     # Zone 3 right: markdown response
│   └── HealthDot.tsx          # Status indicator (reused in header)
├── hooks/
│   └── useInvestigation.ts    # SSE connection + state management
├── stores/
│   └── investigationStore.ts  # Zustand store (when ready)
├── types/
│   └── index.ts               # StepEvent, ThinkingState, etc.
└── styles/
    └── globals.css             # Unchanged
```

### State Management Migration

Phase 1 (immediate): Keep `useState` in `InvestigationPanel`, pass props down.

Phase 2 (with Zustand): Move to a store for cross-panel state:

```typescript
// stores/investigationStore.ts
interface InvestigationState {
  alert: string;
  steps: StepEvent[];
  thinking: ThinkingState | null;
  finalMessage: string;
  errorMessage: string;
  running: boolean;
  runMeta: { steps: number; tokens: number; time: string } | null;

  setAlert: (text: string) => void;
  addStep: (step: StepEvent) => void;
  setThinking: (state: ThinkingState | null) => void;
  setFinalMessage: (text: string) => void;
  setError: (message: string) => void;
  reset: () => void;
}
```

The diagnosis panel reads `finalMessage` and `runMeta` from the store. The
investigation panel reads `steps` and `thinking`. Both subscribe independently —
no unnecessary re-renders.

---

## Interaction Flow (Demo Walkthrough)

```
1. DASHBOARD LOADS
   ├─ Metrics bar shows static KPIs (hardcoded for demo)
   ├─ Alert chart shows the LinkTelemetry anomaly screenshot
   ├─ Investigation panel: alert pre-filled, button ready
   └─ Diagnosis panel: empty state placeholder

2. PRESENTER CLICKS "INVESTIGATE"
   ├─ Button → "Running..." (disabled)
   ├─ Investigation panel: steps appear one by one
   │   ├─ Step 1: GraphExplorerAgent → queries topology
   │   ├─ Step 2: TelemetryAgent → queries alerts
   │   ├─ Step 3: RunbookKBAgent → searches procedures
   │   ├─ Step 4: HistoricalTicketAgent → finds precedents
   │   ├─ Step 5: GraphExplorerAgent → blast radius check
   │   └─ Step 6: TelemetryAgent → latency metrics
   ├─ Thinking dots animate between steps
   └─ Diagnosis panel: "Agents are investigating..."

3. INVESTIGATION COMPLETES (~35s)
   ├─ Diagnosis panel: full Situation Report renders
   │   (markdown with headers, tables, lists)
   ├─ Investigation panel: "Run complete — 6 steps · 4,200 tokens · 35s"
   └─ Presenter can expand individual steps to show queries/responses

4. PRESENTER NARRATES THE DIAGNOSIS
   ├─ Points to blast radius section
   ├─ Points to SLA exposure ($115k/hr)
   ├─ Points to recommended actions
   └─ Clicks "Copy" to grab the report
```

---

## Metrics Bar: Future Integration

The metrics are hardcoded for Phase 1. Later integration options:

| Metric | Source | API |
|--------|--------|-----|
| Active Alerts | Fabric Eventhouse | `POST /query/telemetry` with KQL: `AlertStream \| where Severity in ("CRITICAL","MAJOR") \| where Timestamp > ago(1h) \| count` |
| Services Impacted | Agent response parsing | Extract from diagnosis text or dedicated backend endpoint |
| SLA At Risk | Graph query | `MATCH (s:SLAPolicy)-[:GOVERNS]->(svc:Service) WHERE svc.ServiceId IN [...] RETURN sum(s.PenaltyPerHourUSD)` |
| Anomalies (24h) | Fabric Eventhouse | KQL anomaly count from LinkTelemetry |
| Alert Chart | Fabric Real-Time Dashboard embed or Recharts | Live telemetry feed |

For the demo, hardcoded values matching the scenario data are more reliable
and avoid the Fabric capacity issues that motivated the Neo4j migration.

---

## Comparison: Current vs Proposed

| Aspect | Current (V2) | Proposed (V3) |
|--------|-------------|---------------|
| Layout | Vertical scroll, single column | Full-viewport, 3-zone grid |
| Metrics | None | 4 KPI cards + alert chart |
| Alert input | Full-width card | Compact, left panel top |
| Steps display | Full-width, all details shown | Left panel, compact, collapsible |
| Diagnosis | Below steps, easy to miss | Right panel, prominent, persistent |
| Error handling | Full-width banner | Left panel, inline |
| Health check | Footer dot | Header bar integrated |
| Page scroll | Entire page scrolls | Panels scroll independently |
| Components | Single App.tsx (~250 lines) | 12+ focused components |
| State | Local useState | Zustand store (Phase 2) |
| Feel | Prototype / form | Command centre / dashboard |
