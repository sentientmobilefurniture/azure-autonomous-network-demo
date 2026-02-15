# SSE Event Protocols

## Investigation SSE (`POST /api/alert`)

**Library**: `@microsoft/fetch-event-source` (allows POST + named events)

| Event Name | Payload Shape | UI Effect |
|------------|---------------|-----------|
| `run_start` | `{run_id, alert, timestamp}` | Sets `runStarted = true` |
| `step_thinking` | `{agent: string, status: string}` | Shows thinking dots with agent name + status |
| `step_start` | `{step: number, agent: string}` | Sets thinking to `{agent, status: 'processing...'}` |
| `step_complete` | `{step, agent, duration?, query?, response?, error?: boolean}` | Clears thinking; appends to `steps[]`; increments step counter |
| `message` | `{text: string}` | Clears thinking; sets `finalMessage` (markdown diagnosis) |
| `run_complete` | `{steps: number, tokens: number, time: string}` | Clears thinking; sets `runMeta` |
| `error` | `{message: string}` | Clears thinking; sets `errorMessage` |

**Frontend state machine**:
```
idle → submitAlert() → running=true, clear all state
  → run_start → runStarted=true
  → step_thinking (0..n times per agent call)
  → step_start → step_complete (repeats per agent step)
  → message (final markdown diagnosis)
  → run_complete (sets runMeta {steps, time})
  → finally: running=false, runMeta updated from refs
```

Frontend auto-abort timeout: **5 minutes** of total SSE stream time.

## Upload SSE (`POST /query/upload/*`)

Uses raw `ReadableStream` parsing of `data:` lines (not named events).

| Payload Shape | Meaning |
|---------------|---------|
| `{step: string, detail: string, pct: number, category?: string}` | Progress update (0-100%). `category` identifies the upload type (e.g. `"graph"`, `"telemetry"`) |
| `{graph: string, ...}` or `{database: string, ...}` or `{index: string, ...}` | Completion result |
| `{error: string}` | Error (pct = -1 internally) |

**Graph upload completion** includes `scenario_metadata` dict (display_name, description,
use_cases, example_questions, graph_styles, domain) extracted from `scenario.yaml` during
upload. The frontend captures this metadata via `onComplete` and forwards it to the
`saveScenario()` call, allowing scenario metadata to flow from data pack → upload → save
without a separate entry step.

Server-side event types: `progress`, `complete`, `error`.

## Agent Provisioning SSE (`POST /api/config/apply`)

Same raw `ReadableStream` pattern as uploads.

| Event | Payload | Meaning |
|-------|---------|---------|
| `progress` | `{step: string, detail: string}` | Step progress |
| `complete` | `{step: "done", detail: string, result: {...}}` | All agents created (config-driven N agents, or legacy 5-agent fallback) |
| `error` | `{step: "error", detail: string}` | Provisioning failed |

**`needs-provisioning` flow** (frontend-only, no SSE):
When a scenario is activated, `ProvisioningBanner` fetches `GET /api/agents`.
If `agents.length === 0`, banner shows amber ⚠ with "Provision Now" button.
Clicking the button initiates the SSE flow above.

## Log Stream SSE (`GET /api/logs`)

**Library**: Native `EventSource` (GET-only)

| Event Name | Payload Shape | Notes |
|------------|---------------|-------|
| `log` | `{ts: string, level: string, name: string, msg: string}` | `ts` format: `HH:MM:SS.mmm` |

Implementation: Custom `logging.Handler` installed on root logger → broadcasts to all connected subscriber queues. Filter: only `app.*`, `azure.*`, `uvicorn.*` loggers. Buffer: last 100 records replayed to new connections. Thread-safe via `_event_loop.call_soon_threadsafe()`.
