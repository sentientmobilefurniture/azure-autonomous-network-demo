# Phase 3 — Orchestrator FunctionTool: `dispatch_field_engineer`

> **Scope:** Backend only — agent provisioning, orchestrator runtime, env config. No frontend changes.
> **Depends on:** Phase 1 (duty roster data exists), Phase 2 (demo flows reference dispatch action).
> **Outcome:** The Orchestrator agent can call `dispatch_field_engineer()`, which is auto-executed at runtime. The SSE stream emits a new `action_executed` event type with the dispatch details.
>
> **AUDIT STATUS:** Multiple corrections applied after SDK source verification. See § Audit Corrections below.
>
> **DEPLOYMENT NOTE:** Phase 3 and Phase 5 should be deployed together. If Phase 3 ships without Phase 5: (1) `action_executed` SSE events are silently dropped by the frontend (no crash), (2) the thinking spinner may not clear during action execution, (3) action steps in saved sessions will be invisible when replayed. No data loss or corruption — just invisible actions until the frontend catches up.

---

## 1. Why

The requirements state:
- "Add simulated Action calls — let orchestrator fire actions during the flow"
- "Fire email to the man stationed at the relay — DUTY ROSTER! MAN, EMAIL, LOCATION, PHONE NUMBER!"
- "Let us add to the orchestrator a tool (Reference: function-calling, OpenAPI)"
- "The email should be viewable by clicking a (View action) button"
- "Maybe we should just have the tool spoof the effect"

This is the **backend plumbing** that makes the orchestrator capable of calling a Python function during its investigation run. The function simulates dispatching a field engineer by composing an email body and returning structured dispatch data. No real email is sent — that's a future enhancement using `PRESENTER_EMAIL`.

---

## 2. Architecture Decision: FunctionTool with Auto-Execution

### Why FunctionTool (not OpenAPI)

The dispatch action is **local logic**, not an external API call:
- It reads duty roster data from the in-memory scenario context
- It composes an email body with sensor locations, physical signs to inspect
- It returns structured data (engineer name, destination GPS, email body)
- No external HTTP call is needed

`FunctionTool` is the right fit. `OpenApiTool` would require standing up a REST endpoint.

### How FunctionTool works with the existing streaming architecture

**Current architecture:**
```
agents_client.runs.stream(thread_id, agent_id, event_handler=handler) as stream
    → stream.until_done()
    → handler.on_run_step() receives completed tool_calls
    → tc.type == "connected_agent" → extract output
    → SSE events emitted
```

**With FunctionTool + ToolSet + auto-execution:**
```
toolset = ToolSet()
toolset.add(FunctionTool(functions=[dispatch_field_engineer]))
agents_client.enable_auto_function_calls(toolset)

# runs.stream() call is UNCHANGED — no toolset parameter needed.
# enable_auto_function_calls() hooks into the RunsOperations instance.
agents_client.runs.stream(thread_id, agent_id, event_handler=handler) as stream
    → stream.until_done()
    → When orchestrator calls dispatch_field_engineer:
        1. SDK intercepts the requires_action status internally
        2. SDK calls dispatch_field_engineer() locally  
        3. SDK submits the function’s return value back to the agent
        4. handler.on_run_step() sees tc.type == "function" (args only, NO output)
```

**Key:** `enable_auto_function_calls(toolset)` modifies the `RunsOperations` instance to auto-intercept function calls during streaming. The `runs.stream()` call itself does **NOT** accept a `toolset` parameter.

> **AUDIT CORRECTION:** The original plan proposed `runs.stream(..., toolset=toolset)`. SDK source verification confirms `stream()` does NOT accept a `toolset` parameter. Only `create_and_process()` does. The correct approach is `enable_auto_function_calls()` called once before the stream loop.

### SDK References

| Source | URL / Path |
|---|---|
| Function calling (Azure Foundry docs) | https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/function-calling?view=foundry&preserve-view=true&pivots=python |
| FunctionTool reference (local) | `~/references/skills/skills/azure-ai-projects-py/references/tools.md` — `FunctionTool` section |
| ToolSet + auto-execution pattern (local) | `~/references/skills/skills/azure-ai-projects-py/references/tools.md` — `ToolSet Pattern` section |
| Agent streaming (local) | `~/references/skills/skills/azure-ai-projects-py/references/agents.md` — `Streaming Run` section |

---

## 3. The `dispatch_field_engineer` Function

### 3.1 Function signature and docstring

```python
def dispatch_field_engineer(
    engineer_name: str,
    engineer_email: str,
    engineer_phone: str,
    incident_summary: str,
    destination_description: str,
    destination_latitude: float,
    destination_longitude: float,
    physical_signs_to_inspect: str,
    sensor_ids: str,
    urgency: str = "HIGH",
) -> str:
    """Dispatch a field engineer to a physical site to investigate a network incident.

    Composes and sends a dispatch notification (email) to the specified field
    engineer with incident details, exact GPS coordinates of the fault location,
    and a checklist of physical signs to inspect on arrival.

    Args:
        engineer_name: Full name of the on-duty field engineer from the duty roster.
        engineer_email: Email address of the field engineer.
        engineer_phone: Phone number of the field engineer.
        incident_summary: Brief summary of the incident and why dispatch is needed.
        destination_description: Human-readable description of where to go
            (e.g. "Goulburn interchange splice point — 195km south of Sydney").
        destination_latitude: GPS latitude (WGS84) of the inspection site.
        destination_longitude: GPS longitude (WGS84) of the inspection site.
        physical_signs_to_inspect: Checklist of what to look for on arrival
            (e.g. "Check fibre splice enclosure for physical damage, inspect
            conduit for moisture ingress, verify amplifier LED status").
        sensor_ids: Comma-separated sensor IDs that triggered the dispatch
            (e.g. "SENS-SYD-MEL-F1-OPT-002,SENS-AMP-GOULBURN-VIB-001").
        urgency: Urgency level — "CRITICAL", "HIGH", or "STANDARD".
            Defaults to "HIGH".

    Returns:
        JSON string with dispatch confirmation including a composed email body.
    """
```

### 3.2 Function implementation

File: `api/app/dispatch.py` (new file)

```python
"""
dispatch_field_engineer — FunctionTool callable for the Orchestrator.

Simulates dispatching a field engineer by composing a structured dispatch
notification. Does not actually send email (future: use PRESENTER_EMAIL).
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def dispatch_field_engineer(
    engineer_name: str,
    engineer_email: str,
    engineer_phone: str,
    incident_summary: str,
    destination_description: str,
    destination_latitude: float,
    destination_longitude: float,
    physical_signs_to_inspect: str,
    sensor_ids: str,
    urgency: str = "HIGH",
) -> str:
    """Dispatch a field engineer to investigate a network incident on-site.
    
    [Full docstring as above — omitted for brevity]
    """

    dispatch_time = datetime.now(timezone.utc).isoformat()
    dispatch_id = f"DISPATCH-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    
    # Google Maps link for the GPS coordinates
    maps_link = (
        f"https://www.google.com/maps?q={destination_latitude},{destination_longitude}"
    )

    # Compose the email body
    email_subject = f"[{urgency}] Field Dispatch — {incident_summary[:80]}"
    email_body = f"""FIELD DISPATCH NOTIFICATION
{'=' * 50}

Dispatch ID:  {dispatch_id}
Urgency:      {urgency}
Dispatched:   {dispatch_time}

TO: {engineer_name}
Email: {engineer_email}
Phone: {engineer_phone}

{'─' * 50}
INCIDENT SUMMARY
{'─' * 50}
{incident_summary}

{'─' * 50}
DESTINATION
{'─' * 50}
Location: {destination_description}
GPS:      {destination_latitude}, {destination_longitude}
Map:      {maps_link}

{'─' * 50}
INSPECTION CHECKLIST
{'─' * 50}
{physical_signs_to_inspect}

{'─' * 50}
TRIGGERING SENSORS
{'─' * 50}
{sensor_ids}

{'─' * 50}
INSTRUCTIONS
{'─' * 50}
1. Proceed to the GPS coordinates above immediately.
2. Contact NOC on arrival: +61-2-9555-0100
3. Follow the inspection checklist above.
4. Report findings via the NOC incident channel.
5. Do NOT attempt repairs without L2 engineer authorisation.

{'=' * 50}
This dispatch was generated automatically by the Network AI Orchestrator.
"""

    # Future: Actually send email via PRESENTER_EMAIL
    presenter_email = os.environ.get("PRESENTER_EMAIL", "")
    if presenter_email:
        logger.info(
            "PRESENTER_EMAIL is set (%s) — future: send real email here",
            presenter_email,
        )
        # TODO: Implement real email sending (e.g. via Microsoft Graph API)

    logger.info(
        "Field dispatch executed: %s → %s at (%s, %s)",
        dispatch_id, engineer_name,
        destination_latitude, destination_longitude,
    )

    result = {
        "status": "dispatched",
        "dispatch_id": dispatch_id,
        "dispatch_time": dispatch_time,
        "engineer": {
            "name": engineer_name,
            "email": engineer_email,
            "phone": engineer_phone,
        },
        "destination": {
            "description": destination_description,
            "latitude": destination_latitude,
            "longitude": destination_longitude,
            "maps_link": maps_link,
        },
        "urgency": urgency,
        "sensor_ids": [s.strip() for s in sensor_ids.split(",")],
        "email_subject": email_subject,
        "email_body": email_body,
    }

    return json.dumps(result)
```

---

## 4. Agent Provisioner Changes

File: `scripts/agent_provisioner.py`

> **AUDIT CORRECTION:** The provisioner runs from `scripts/` context. It CANNOT import from `api/app/` (`ModuleNotFoundError`). Additionally, the installed SDK’s `FunctionTool` class (`azure.ai.agents.models`) requires actual Python callable objects to introspect signatures — it cannot accept a raw JSON schema dict. The `azure.ai.projects.models.FunctionTool` with schema-only support does not exist in the installed SDK version.
>
> **Solution:** Use `FunctionToolDefinition` + `FunctionDefinition` from `azure.ai.agents.models` to register the tool schema directly, without needing the function object.

### 4.1 Import additions

```python
from azure.ai.agents.models import (
    AzureAISearchTool,
    AzureAISearchQueryType,
    ConnectedAgentTool,
    OpenApiTool,
    OpenApiAnonymousAuthDetails,
    FunctionToolDefinition,    # NEW — raw schema registration
    FunctionDefinition,        # NEW — raw schema registration
)
```

### 4.2 Orchestrator creation — add FunctionTool definition

Currently the Orchestrator is created with only `ConnectedAgentTool` definitions:

```python
# Current code:
connected_tools = []
for sa in sub_agents:
    ct = ConnectedAgentTool(id=sa["id"], name=sa["name"], description=sa["description"])
    connected_tools.extend(ct.definitions)

orch = agents_client.create_agent(
    model=model,
    name="Orchestrator",
    instructions=prompts.get("orchestrator", "..."),
    tools=connected_tools,
)
```

**Change to also include the dispatch function schema:**

```python
# ConnectedAgent tools (existing)
connected_tools = []
for sa in sub_agents:
    ct = ConnectedAgentTool(id=sa["id"], name=sa["name"], description=sa["description"])
    connected_tools.extend(ct.definitions)

# FunctionTool definition for dispatch (NEW)
# Uses FunctionToolDefinition with a raw JSON schema — no Python callable needed.
# The callable is only needed at RUNTIME (in orchestrator.py), not at provisioning time.
dispatch_tool_def = FunctionToolDefinition(
    function=FunctionDefinition(
        name="dispatch_field_engineer",
        description=(
            "Dispatch a field engineer to a physical site to investigate a network "
            "incident. Composes a dispatch notification with incident details, exact "
            "GPS coordinates, and inspection checklist. Call this after identifying "
            "a physical root cause, locating the fault via sensors, and finding the "
            "nearest on-duty engineer from the duty roster."
        ),
        parameters={
            "type": "object",
            "properties": {
                "engineer_name": {"type": "string", "description": "Full name from duty roster"},
                "engineer_email": {"type": "string", "description": "Email address from duty roster"},
                "engineer_phone": {"type": "string", "description": "Phone number from duty roster"},
                "incident_summary": {"type": "string", "description": "Brief incident summary"},
                "destination_description": {"type": "string", "description": "Human-readable location"},
                "destination_latitude": {"type": "number", "description": "GPS latitude (WGS84)"},
                "destination_longitude": {"type": "number", "description": "GPS longitude (WGS84)"},
                "physical_signs_to_inspect": {"type": "string", "description": "Inspection checklist"},
                "sensor_ids": {"type": "string", "description": "Comma-separated triggering sensor IDs"},
                "urgency": {"type": "string", "enum": ["CRITICAL", "HIGH", "STANDARD"], "description": "Urgency level"},
            },
            "required": [
                "engineer_name", "engineer_email", "engineer_phone",
                "incident_summary", "destination_description",
                "destination_latitude", "destination_longitude",
                "physical_signs_to_inspect", "sensor_ids",
            ],
        },
    )
)

all_tools = connected_tools + [dispatch_tool_def]

orch = agents_client.create_agent(
    model=model,
    name="Orchestrator",
    instructions=prompts.get("orchestrator", "..."),
    tools=all_tools,
)
```

**Key:** The `FunctionToolDefinition` registers the tool schema on the Foundry service so the agent knows the function signature. The actual Python function is only loaded at **runtime** in `orchestrator.py`.

---

## 5. Orchestrator Runtime Changes

File: `api/app/orchestrator.py`

### 5.1 ToolSet setup in `_thread_target()`

Both `run_orchestrator()` and `run_orchestrator_session()` need the same change. In the `_thread_target()` function, **before the streaming loop**:

```python
from azure.ai.agents.models import FunctionTool, ToolSet
from app.dispatch import dispatch_field_engineer

# Create ToolSet with the dispatch function for auto-execution
dispatch_fn = FunctionTool(functions=[dispatch_field_engineer])
toolset = ToolSet()
toolset.add(dispatch_fn)
agents_client.enable_auto_function_calls(toolset)
```

> **AUDIT CORRECTION:** The `runs.stream()` call is **NOT changed** — it does not accept a `toolset` parameter. `enable_auto_function_calls(toolset)` modifies the `agents_client.runs` operations instance to auto-intercept `requires_action` events during streaming.

```python
# The runs.stream() call remains UNCHANGED:
with agents_client.runs.stream(
    thread_id=thread_id,
    agent_id=orchestrator_id,
    event_handler=handler,
) as stream:
    stream.until_done()
```

### 5.2 SSE handler — handle `function` tool call type

In `_resolve_agent_name()`, add handling for `function` type:

```python
def _resolve_agent_name(self, tc) -> str:
    tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
    tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)
    if tc_type == "connected_agent":
        # ... existing code ...
    elif tc_type == "azure_ai_search":
        return "AzureAISearch"
    elif tc_type == "function":                       # NEW
        fn = tc.function if hasattr(tc, "function") else tc.get("function", {})
        name = getattr(fn, "name", None) or fn.get("name", "function")
        return name
    return tc_type
```

In `_extract_arguments()`, add handling for `function` type:

```python
def _extract_arguments(self, tc) -> tuple[str, str]:
    tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
    tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)
    if tc_type == "connected_agent":
        # ... existing code ...
    elif tc_type == "function":                       # NEW
        fn = tc.function if hasattr(tc, "function") else tc.get("function", {})
        args_raw = getattr(fn, "arguments", None) or fn.get("arguments", "")
        try:
            obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            raw = json.dumps(obj, indent=2) if isinstance(obj, dict) else str(obj)
        except Exception:
            raw = str(args_raw)
        # Extract reasoning if present
        reasoning = ""
        query = raw
        match = self._THINKING_RE.search(raw)
        if match:
            reasoning = match.group(1).strip()
            if len(reasoning) > 500:
                reasoning = reasoning[:500] + "…"
            query = raw[:match.start()] + raw[match.end():]
            query = query.strip()
        return query, reasoning
    return "", ""
```

In the `on_run_step()` completed handler, add a branch for **function tool calls** to emit a new `action_executed` event type:

```python
elif status == "completed" and step_type == "tool_calls":
    start = self.step_starts.get(step.id, self.t0)
    duration = f"{time.monotonic() - start:.1f}s"

    if not hasattr(step.step_details, "tool_calls"):
        return

    for tc in step.step_details.tool_calls:
        self.ui_step += 1

        agent_name = self._resolve_agent_name(tc)
        query, reasoning = self._extract_arguments(tc)

        tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
        tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)

        # ──── NEW: Handle function tool calls (actions) ────
        if tc_type == "function":
            fn = tc.function if hasattr(tc, "function") else tc.get("function", {})
            
            # AUDIT CORRECTION: RunStepFunctionToolCallDetails has name + arguments
            # but NO output field. The function output was already submitted back
            # to the agent by enable_auto_function_calls() and is not available
            # on the step object.
            #
            # To capture the output, we must intercept it BEFORE submission.
            # Strategy: Store the last function output in a dict on the handler,
            # keyed by function name. The dispatch_field_engineer function is
            # deterministic from its args, so we can reconstruct the output
            # from the arguments, OR we wrap the function to cache its output.
            #
            # Recommended approach: Wrap dispatch_field_engineer in a closure
            # that caches its last return value on the handler instance:
            #
            #   handler._last_fn_output = {}  # set in __init__
            #   def _wrapped_dispatch(**kwargs):
            #       result = dispatch_field_engineer(**kwargs)
            #       handler._last_fn_output["dispatch_field_engineer"] = result
            #       return result
            #
            # Then read from handler._last_fn_output here.
            
            fn_name = getattr(fn, "name", None) or fn.get("name", "function")
            fn_output = self._last_fn_output.get(fn_name, "")
            
            # Parse the function's JSON return value
            action_data = {}
            try:
                action_data = json.loads(fn_output) if isinstance(fn_output, str) else fn_output
            except (json.JSONDecodeError, TypeError):
                action_data = {"raw_output": str(fn_output)}

            # Emit both step_complete (for step tracking) AND action_executed (for frontend)
            event_data = {
                "step": self.ui_step,
                "agent": agent_name,
                "duration": duration,
                "query": query[:500] if query else "",
                "response": f"Action executed: {agent_name}",
                "action": action_data,                    # Full dispatch payload
                "is_action": True,                        # Flag for frontend
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if reasoning:
                event_data["reasoning"] = reasoning

            _put("step_start", {"step": self.ui_step, "agent": agent_name})
            _put("step_complete", event_data)
            _put("action_executed", {                     # NEW event type
                "step": self.ui_step,
                "action_name": agent_name,
                "action_data": action_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        # ──── Existing: Handle connected_agent and other tool calls ────
        response = ""
        visualization = None
        if tc_type == "connected_agent":
            # ... existing code unchanged ...
```

### 5.3 Important: Apply to BOTH handler classes

The `SSEEventHandler` class is **duplicated** in the file — once in `run_orchestrator()` (line ~115) and once in `run_orchestrator_session()` (line ~665). Both must receive identical changes.

**Better approach:** Extract the handler into a factory function to avoid duplication:

```python
def _make_sse_handler_class(agent_names: dict, put_fn: callable):
    """Factory to create SSEEventHandler with the correct closure."""
    # ... single definition of SSEEventHandler ...
    return SSEEventHandler
```

This refactor is optional but strongly recommended to avoid the current code duplication problem getting worse.

---

## 6. Environment Variable: `PRESENTER_EMAIL`

### 6.1 `azure_config.env.template` — add at the end

```env
# --- Presenter / Demo Settings ---
# Email address for the demo presenter. When set, the dispatch_field_engineer
# action will send real notification emails to this address (future feature).
# Leave empty to use simulated dispatch only.
PRESENTER_EMAIL=
```

### 6.2 No code reads it yet

The `dispatch_field_engineer` function logs a message if `PRESENTER_EMAIL` is set, but does not act on it. This is intentional — real email sending is a future enhancement. The variable is defined now so it shows up in the admin panel and is ready when needed.

---

## 7. Files to Create / Modify — Summary

| Action | File | Description |
|---|---|---|
| **CREATE** | `api/app/dispatch.py` | `dispatch_field_engineer()` function implementation |
| **MODIFY** | `scripts/agent_provisioner.py` | Add `FunctionToolDefinition`/`FunctionDefinition` import, add dispatch schema to Orchestrator's tool list (no function import needed) |
| **MODIFY** | `api/app/orchestrator.py` | (1) Add `ToolSet` setup with wrapped `dispatch_field_engineer`, (2) Call `enable_auto_function_calls(toolset)` before streaming (stream call UNCHANGED), (3) Handle `tc_type == "function"` in `_resolve_agent_name`, `_extract_arguments`, and `on_run_step`, (4) Emit `action_executed` SSE event |
| **MODIFY** | `azure_config.env.template` | Add `PRESENTER_EMAIL=` variable |

---

## 8. SSE Event Schema Update

### New event type: `action_executed`

```typescript
// Emitted when the orchestrator calls a FunctionTool action
interface ActionExecutedEvent {
  event: "action_executed";
  data: {
    step: number;
    action_name: string;    // "dispatch_field_engineer"
    action_data: {
      status: string;       // "dispatched"
      dispatch_id: string;  // "DISPATCH-20260206-143215"
      dispatch_time: string;
      engineer: {
        name: string;
        email: string;
        phone: string;
      };
      destination: {
        description: string;
        latitude: number;
        longitude: number;
        maps_link: string;
      };
      urgency: string;
      sensor_ids: string[];
      email_subject: string;
      email_body: string;     // The full composed email text
    };
    timestamp: string;
  };
}
```

### Existing `step_complete` event — new fields

When `is_action: true`, the `step_complete` event carries additional fields:

```typescript
interface StepCompleteEvent {
  // ... existing fields (step, agent, duration, query, response) ...
  is_action?: boolean;     // NEW — true when this step is a function tool call
  action?: object;         // NEW — parsed output of the function (same as action_data)
}
```

The frontend (Phase 5) will check `step.is_action` to decide whether to render a `StepCard` or an `ActionCard`.

---

## 9. Validation Checklist

- [ ] `dispatch_field_engineer()` returns valid JSON with all expected fields
- [ ] `agent_provisioner.py` creates Orchestrator with both ConnectedAgent and FunctionToolDefinition entries
- [ ] `enable_auto_function_calls(toolset)` works with `runs.stream()` (function is called automatically)
- [ ] `on_run_step` correctly processes `tc_type == "function"` tool calls
- [ ] Function output is captured via the wrapper closure before auto-submission to the agent
- [ ] `action_executed` SSE event is emitted and received by the frontend SSE handler
- [ ] `step_complete` event has `is_action: true` and `action` data for function tool calls
- [ ] `PRESENTER_EMAIL` appears in `azure_config.env.template` (and in admin panel if deployed)
- [ ] Existing connected_agent and azure_ai_search tool calls are unaffected
- [ ] Re-provisioning agents (`provision_agents.py --force`) succeeds with the new FunctionToolDefinition

---

## 10. Risk: FunctionTool with Streaming — UPDATED

> **AUDIT CORRECTION:** The original plan incorrectly proposed passing `toolset` to `runs.stream()`. SDK source confirms `stream()` does NOT accept this parameter.

The correct approach is `enable_auto_function_calls(toolset)` called once on the `agents_client` before streaming. The SDK’s internal `_handle_submit_tool_outputs` method auto-executes functions during the stream.

**Remaining risk:** `RunStepFunctionToolCallDetails` has `name` and `arguments` but NO `output` field. The function output is submitted back by the SDK but not stored on the step object.

**Mitigation — function wrapper pattern:**
```python
# In SSEEventHandler.__init__:
self._last_fn_output = {}

# When creating the ToolSet:
def _wrapped_dispatch(**kwargs):
    result = dispatch_field_engineer(**kwargs)
    handler._last_fn_output["dispatch_field_engineer"] = result
    return result

dispatch_fn = FunctionTool(functions=[_wrapped_dispatch])
```

This captures the output before the SDK submits it, making it available in `on_run_step`.

**Fallback (if `enable_auto_function_calls` doesn’t work with streaming):**
Manually handle the `requires_action` status in `on_thread_run`:
1. Detect `status == "requires_action"` in `on_thread_run`
2. Extract function call arguments from `run.required_action.submit_tool_outputs.tool_calls`
3. Execute the function locally, cache the output
4. Submit output via `agents_client.runs.submit_tool_outputs()`
5. The stream resumes automatically

---

## 11. References

| Source | URL / Path |
|---|---|
| Azure Foundry function calling guide | https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/function-calling?view=foundry&preserve-view=true&pivots=python |
| Azure Foundry OpenAPI tool guide | https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/openapi?view=foundry&pivots=python |
| Local SDK tools reference | `~/references/skills/skills/azure-ai-projects-py/references/tools.md` |
| Local SDK agents reference | `~/references/skills/skills/azure-ai-projects-py/references/agents.md` |
| Existing orchestrator.py | `api/app/orchestrator.py` (lines 1–1113) |
| Existing agent_provisioner.py | `scripts/agent_provisioner.py` |
