"""
Orchestrator bridge — runs the Foundry Orchestrator agent in a background
thread and yields SSE events via an async generator.

The Azure AI Agents SDK uses a synchronous callback-based streaming API
(AgentEventHandler). This module bridges it to async SSE by:
  1. Running the agent stream in a daemon thread
  2. Pushing SSE-shaped dicts to an asyncio.Queue from the callbacks
  3. Yielding from the queue in an async generator for EventSourceResponse

Falls back to stub responses when the orchestrator isn't configured
(missing env vars or no agents provisioned in Foundry).
"""

import asyncio
import ast
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import app.paths  # noqa: F401  # side-effect: loads .env
from app.agent_ids import load_agent_ids, get_agent_names

logger = logging.getLogger(__name__)

# Cached credential singleton — shared with agent_ids module
_credential = None

def _get_credential():
    global _credential
    if _credential is None:
        from azure.identity import DefaultAzureCredential
        _credential = DefaultAzureCredential()
    return _credential


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Check whether the Foundry orchestrator is ready to use."""
    if not os.environ.get("PROJECT_ENDPOINT"):
        return False
    if not os.environ.get("AI_FOUNDRY_PROJECT_NAME"):
        return False
    try:
        data = load_agent_ids()
        if not data.get("orchestrator", {}).get("id"):
            return False
    except Exception:
        return False
    return True


def _load_orchestrator_id() -> str:
    return load_agent_ids()["orchestrator"]["id"]


def _load_agent_names() -> dict[str, str]:
    """Map of agent_id → display name for resolving connected-agent calls."""
    return get_agent_names()


def _get_project_client():
    """Create an AIProjectClient with the project-scoped endpoint."""
    from azure.ai.projects import AIProjectClient

    endpoint = os.environ.get("PROJECT_ENDPOINT", "")
    project_name = os.environ.get("AI_FOUNDRY_PROJECT_NAME", "")
    if not endpoint or not project_name:
        raise RuntimeError(
            "PROJECT_ENDPOINT and AI_FOUNDRY_PROJECT_NAME must be set"
        )
    endpoint = endpoint.rstrip("/")
    # Ensure endpoint uses services.ai.azure.com and has /api/projects/ path
    if "/api/projects/" not in endpoint:
        endpoint = endpoint.replace("cognitiveservices.azure.com", "services.ai.azure.com")
        endpoint = f"{endpoint}/api/projects/{project_name}"
    return AIProjectClient(endpoint=endpoint, credential=_get_credential())


# ---------------------------------------------------------------------------
# SSE event generator — unified handler + single entry point
# ---------------------------------------------------------------------------

async def run_orchestrator_session(
    alert_text: str,
    cancel_event: threading.Event = None,
    existing_thread_id: str = None,
) -> AsyncGenerator[dict, None]:
    """Run the Foundry Orchestrator agent and yield new-schema SSE events.

    Single entry point for both initial and follow-up turns.
    Supports cancel_event and thread reuse for multi-turn sessions.
    """
    from azure.ai.agents.models import AgentEventHandler

    orchestrator_id = _load_orchestrator_id()
    agent_names = _load_agent_names()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _put(event: str, data: dict):
        """Thread-safe enqueue of an SSE event dict."""
        asyncio.run_coroutine_threadsafe(
            queue.put({"event": event, "data": json.dumps(data)}),
            loop,
        )

    # -- Handler (single unified class) --------------------------------------

    class SSEEventHandler(AgentEventHandler):
        """Converts AgentEventHandler callbacks to new-schema SSE events."""

        def __init__(self):
            super().__init__()
            self.t0 = time.monotonic()
            self.step_starts: dict[str, float] = {}
            self._pending_steps: dict[str, dict] = {}  # step_id → {tc_id → metadata}
            self.ui_step = 0
            self.total_tokens = 0
            self.response_text = ""
            self.run_failed = False
            self.run_error_detail = ""
            self._last_fn_output: dict[str, str] = {}
            self._message_id: str | None = None
            self._message_started = False

        def _elapsed(self) -> str:
            return f"{time.monotonic() - self.t0:.1f}s"

        # -- Run lifecycle ---------------------------------------------------

        def on_thread_run(self, run):
            s = run.status
            status = s.value if hasattr(s, "value") else str(s)
            logger.info("on_thread_run: status=%s", status)

            if status == "completed" and run.usage:
                self.total_tokens = getattr(run.usage, "total_tokens", 0) or 0
            elif status == "failed":
                err = run.last_error
                if err is None:
                    code = "unknown"
                    msg = "Run failed with no error details"
                else:
                    code = getattr(err, "code", None) or (err.get("code") if isinstance(err, dict) else None) or "unknown"
                    msg = getattr(err, "message", None) or (err.get("message") if isinstance(err, dict) else str(err))
                self.run_failed = True
                self.run_error_detail = f"[{code}] {msg}"
                logger.error(
                    "Orchestrator run failed: [%s] %s  (steps completed: %d, elapsed: %s)",
                    code, msg, self.ui_step, self._elapsed(),
                )

        # -- Helpers for tool call resolution --------------------------------

        def _resolve_agent_name(self, tc) -> str:
            """Resolve agent name from a tool call object."""
            tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
            tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)
            if tc_type == "connected_agent":
                ca = tc.connected_agent if hasattr(tc, "connected_agent") else tc.get("connected_agent", {})
                name = getattr(ca, "name", None) or ca.get("name", None)
                if not name:
                    aid = getattr(ca, "agent_id", None) or ca.get("agent_id", "?")
                    name = agent_names.get(aid, aid)
                return name
            elif tc_type == "azure_ai_search":
                return "AzureAISearch"
            elif tc_type == "function":
                fn = tc.function if hasattr(tc, "function") else tc.get("function", {})
                name = getattr(fn, "name", None) or fn.get("name", "function")
                return name
            return tc_type

        _THINKING_RE = re.compile(
            r'\[ORCHESTRATOR_THINKING\](.*?)\[/ORCHESTRATOR_THINKING\]',
            flags=re.DOTALL,
        )

        def _extract_arguments(self, tc) -> tuple[str, str]:
            """Parse and extract arguments from a tool call.

            Returns (query, reasoning) tuple.
            """
            tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
            tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)
            if tc_type == "function":
                fn = tc.function if hasattr(tc, "function") else tc.get("function", {})
                args_raw = getattr(fn, "arguments", None) or fn.get("arguments", "")
                try:
                    obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    raw = json.dumps(obj, indent=2) if isinstance(obj, dict) else str(obj)
                except Exception:
                    raw = str(args_raw)
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
            if tc_type != "connected_agent":
                return "", ""
            ca = tc.connected_agent if hasattr(tc, "connected_agent") else tc.get("connected_agent", {})
            args_raw = getattr(ca, "arguments", None) or ca.get("arguments", None)
            if not args_raw:
                return "", ""
            try:
                obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                if isinstance(obj, str):
                    raw = obj
                elif isinstance(obj, dict):
                    raw = None
                    for key in ("query", "input"):
                        if key in obj and len(obj) == 1:
                            raw = str(obj[key])
                            break
                    if raw is None:
                        raw = json.dumps(obj)
                else:
                    raw = json.dumps(obj)
            except Exception:
                raw = str(args_raw)

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

        def _parse_structured_output(self, agent_name: str, raw_output: str) -> tuple:
            """Parse sub-agent output into (summary, visualizations, sub_steps).

            Returns:
                (response_text, list_of_visualization_dicts, list_of_sub_step_dicts)
            """
            if not raw_output:
                return "", [], []

            query_blocks = re.findall(
                r'---QUERY---\s*(.+?)\s*---RESULTS---\s*(.+?)\s*(?=---QUERY---|---ANALYSIS---|$)',
                raw_output, re.DOTALL,
            )
            analysis_match = re.search(
                r'---ANALYSIS---\s*(.+)',
                raw_output, re.DOTALL,
            )
            citations_match = re.search(
                r'---CITATIONS---\s*(.+?)\s*---ANALYSIS---',
                raw_output, re.DOTALL,
            )

            viz_type = {
                "GraphExplorerAgent": "graph",
                "TelemetryAgent": "table",
            }.get(agent_name, "documents")

            summary = analysis_match.group(1).strip() if analysis_match else raw_output

            if query_blocks:
                visualizations = []
                sub_steps = []
                for idx, (query_text, results_text) in enumerate(query_blocks):
                    results_json = None
                    try:
                        results_json = json.loads(results_text.strip())
                    except (json.JSONDecodeError, ValueError):
                        try:
                            results_json = ast.literal_eval(results_text.strip())
                        except (ValueError, SyntaxError):
                            logger.warning(
                                "Failed to parse structured results for %s", agent_name,
                            )

                    # Build sub-step entry
                    result_summary = ""
                    if results_json and isinstance(results_json, dict):
                        results_json.pop("error", None)
                        visualizations.append({
                            "type": viz_type,
                            "data": {**results_json, "query": query_text.strip()},
                        })
                        row_count = len(results_json.get("data", results_json.get("rows", [])))
                        result_summary = f"{row_count} results"
                    else:
                        result_summary = results_text.strip()[:200]

                    sub_steps.append({
                        "index": idx,
                        "query": query_text.strip(),
                        "result_summary": result_summary,
                        "agent": agent_name,
                    })

                if visualizations:
                    return summary, visualizations, sub_steps

                return summary, [{
                    "type": "documents",
                    "data": {"content": summary, "agent": agent_name},
                }], sub_steps

            if citations_match and analysis_match:
                citations = citations_match.group(1).strip()
                summary = analysis_match.group(1).strip()
                return summary, [{
                    "type": "documents",
                    "data": {
                        "content": summary,
                        "citations": citations,
                        "agent": agent_name,
                    },
                }], []

            if agent_name in (
                "RunbookKBAgent", "HistoricalTicketAgent", "AzureAISearch",
            ):
                return raw_output, [{
                    "type": "documents",
                    "data": {"content": raw_output, "agent": agent_name},
                }], []

            logger.warning(
                "Agent %s did not emit structured delimiters — "
                "falling back to documents view",
                agent_name,
            )
            return raw_output, [{
                "type": "documents",
                "data": {"content": raw_output, "agent": agent_name},
            }], []

        # -- Step lifecycle --------------------------------------------------

        def on_run_step(self, step):
            s = step.status
            status = s.value if hasattr(s, "value") else str(s)
            t = step.type
            step_type = t.value if hasattr(t, "value") else str(t)
            logger.info("on_run_step: id=%s status=%s type=%s", step.id, status, step_type)

            if status == "in_progress" and step.id not in self.step_starts:
                self.step_starts[step.id] = time.monotonic()

                if step_type == "tool_calls" and hasattr(step, "step_details"):
                    tool_calls = getattr(step.step_details, "tool_calls", None)
                    if tool_calls:
                        for tc in tool_calls:
                            self.ui_step += 1
                            tc_id = getattr(tc, "id", None) or str(id(tc))
                            tool_call_id = str(uuid.uuid4())
                            agent_name = self._resolve_agent_name(tc)
                            query, reasoning = self._extract_arguments(tc)
                            if step.id not in self._pending_steps:
                                self._pending_steps[step.id] = {}
                            self._pending_steps[step.id][tc_id] = {
                                "ui_step": self.ui_step,
                                "tool_call_id": tool_call_id,
                                "agent": agent_name,
                                "query": query[:500] if query else "",
                                "reasoning": reasoning,
                            }
                            event = {
                                "id": tool_call_id,
                                "step": self.ui_step,
                                "agent": agent_name,
                                "query": query[:500] if query else "",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                            if reasoning:
                                event["reasoning"] = reasoning
                            _put("tool_call.start", event)
                        return

                # Fallback: tool_calls not yet available
                _put("status", {"message": "Calling sub-agent..."})

            elif status == "failed" and step_type == "tool_calls":
                start = self.step_starts.get(step.id, self.t0)
                duration = f"{time.monotonic() - start:.1f}s"
                last_err = step.last_error if hasattr(step, "last_error") else None
                err_code = ""
                err_msg = "(no error detail)"
                if last_err:
                    err_code = getattr(last_err, "code", None) or (last_err.get("code") if isinstance(last_err, dict) else "") or ""
                    err_msg = getattr(last_err, "message", None) or (last_err.get("message") if isinstance(last_err, dict) else str(last_err)) or ""

                failed_agent = "unknown"
                failed_query = ""
                if hasattr(step, "step_details") and hasattr(step.step_details, "tool_calls"):
                    for tc in step.step_details.tool_calls:
                        failed_agent = self._resolve_agent_name(tc)
                        failed_query, _ = self._extract_arguments(tc)

                logger.error(
                    "Step FAILED: agent=%s  duration=%s  code=%s  error=%s\n  query=%s",
                    failed_agent, duration, err_code, err_msg, failed_query[:500] if failed_query else "(none)",
                )

                pending = self._pending_steps.pop(step.id, None)
                if pending:
                    first = next(iter(pending.values()))
                    ui_step = first["ui_step"]
                    tool_call_id = first["tool_call_id"]
                else:
                    self.ui_step += 1
                    ui_step = self.ui_step
                    tool_call_id = str(uuid.uuid4())

                _put("tool_call.complete", {
                    "id": tool_call_id,
                    "step": ui_step,
                    "agent": failed_agent,
                    "duration": duration,
                    "query": failed_query[:500] if failed_query else "",
                    "response": f"FAILED: [{err_code}] {err_msg}",
                    "error": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            elif status == "completed" and step_type == "tool_calls":
                start = self.step_starts.get(step.id, self.t0)
                duration = f"{time.monotonic() - start:.1f}s"
                pending = self._pending_steps.pop(step.id, None)

                if not hasattr(step.step_details, "tool_calls"):
                    return

                for tc in step.step_details.tool_calls:
                    tc_id = getattr(tc, "id", None) or str(id(tc))

                    if pending and tc_id in pending:
                        ui_step = pending[tc_id]["ui_step"]
                        tool_call_id = pending[tc_id]["tool_call_id"]
                    else:
                        self.ui_step += 1
                        ui_step = self.ui_step
                        tool_call_id = str(uuid.uuid4())

                    agent_name = self._resolve_agent_name(tc)
                    query, reasoning = self._extract_arguments(tc)
                    response = ""
                    visualizations = []
                    sub_steps = []

                    tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
                    tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)

                    # ── Handle function tool calls (actions) ──
                    if tc_type == "function":
                        fn = tc.function if hasattr(tc, "function") else tc.get("function", {})
                        fn_name = getattr(fn, "name", None) or fn.get("name", "function")
                        fn_output = self._last_fn_output.get(fn_name, "")

                        action_data = {}
                        try:
                            action_data = json.loads(fn_output) if isinstance(fn_output, str) and fn_output else {}
                        except (json.JSONDecodeError, TypeError):
                            action_data = {"raw_output": str(fn_output)}

                        event_data = {
                            "id": tool_call_id,
                            "step": ui_step,
                            "agent": agent_name,
                            "duration": duration,
                            "query": query[:500] if query else "",
                            "response": f"Action executed: {agent_name}",
                            "action": action_data,
                            "is_action": True,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        if reasoning:
                            event_data["reasoning"] = reasoning
                        _put("tool_call.complete", event_data)
                        continue

                    # ── Handle connected_agent and other tool calls ──
                    if tc_type == "connected_agent":
                        ca = (
                            tc.connected_agent
                            if hasattr(tc, "connected_agent")
                            else tc.get("connected_agent", {})
                        )
                        out = getattr(ca, "output", None) or ca.get("output", None)
                        if out:
                            response, visualizations, sub_steps = self._parse_structured_output(
                                agent_name, str(out),
                            )
                            if not response:
                                response = str(out)

                    if len(query) > 500:
                        query = query[:500] + "…"
                    if len(response) > 2000:
                        response = response[:2000] + "…"

                    logger.info("Emitting tool_call.complete step %d: agent=%s duration=%s", ui_step, agent_name, duration)
                    if query:
                        logger.info("  ↳ query: %s", query[:300])
                    if response:
                        logger.info("  ↳ response (%d chars): %s", len(response), response[:200])

                    event_data = {
                        "id": tool_call_id,
                        "step": ui_step,
                        "agent": agent_name,
                        "duration": duration,
                        "query": query,
                        "response": response,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    if visualizations:
                        event_data["visualizations"] = visualizations
                    if sub_steps:
                        event_data["sub_steps"] = sub_steps
                    if reasoning:
                        event_data["reasoning"] = reasoning
                    _put("tool_call.complete", event_data)

        # -- Streaming message text ------------------------------------------

        def on_message_delta(self, delta):
            if delta.text:
                text_chunk = delta.text.value
                self.response_text += text_chunk

                # Emit message.start on the first chunk
                if not self._message_started:
                    self._message_id = str(uuid.uuid4())
                    self._message_started = True
                    _put("message.start", {"id": self._message_id})

                _put("message.delta", {
                    "id": self._message_id,
                    "text": text_chunk,
                })

        def on_error(self, data):
            _put("error", {"message": str(data)})

    # -- Thread target -------------------------------------------------------

    MAX_RUN_ATTEMPTS = 2

    def _is_capacity_error(error_text: str) -> bool:
        """Check if an error message indicates Fabric capacity exhaustion."""
        capacity_markers = [
            "429", "capacity", "circuit breaker", "throttl",
            "Fabric capacity", "too many requests", "503",
        ]
        lower = error_text.lower()
        return any(m.lower() in lower for m in capacity_markers)

    def _run_in_thread():
        overall_t0 = time.monotonic()
        total_steps = 0
        total_tokens = 0
        error_emitted = False

        try:
            # Check cancellation before starting
            if cancel_event and cancel_event.is_set():
                _put("status", {"message": "Cancelling..."})
                _put("error", {"message": "Investigation cancelled by user."})
                return

            _put("run.start", {
                "run_id": "",
                "alert": alert_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            client = _get_project_client()
            with client:
                agents_client = client.agents

                # Set up FunctionTool auto-execution for dispatch actions
                from azure.ai.agents.models import FunctionTool as _FnTool, ToolSet
                from app.dispatch import dispatch_field_engineer

                _fn_output_cache: dict[str, str] = {}

                def _wrapped_dispatch(**kwargs):
                    result = dispatch_field_engineer(**kwargs)
                    _fn_output_cache["dispatch_field_engineer"] = result
                    return result

                _wrapped_dispatch.__name__ = "dispatch_field_engineer"
                _wrapped_dispatch.__doc__ = dispatch_field_engineer.__doc__

                _dispatch_fn = _FnTool(functions=[_wrapped_dispatch])
                _toolset = ToolSet()
                _toolset.add(_dispatch_fn)
                agents_client.enable_auto_function_calls(_toolset)

                # Thread reuse for multi-turn follow-ups
                if existing_thread_id:
                    thread_id = existing_thread_id
                else:
                    thread = agents_client.threads.create()
                    thread_id = thread.id

                # Emit session.created so SessionManager can track the thread
                _put("session.created", {"session_id": "", "thread_id": thread_id})

                agents_client.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=alert_text,
                )

                last_error_detail = ""
                for attempt in range(1, MAX_RUN_ATTEMPTS + 1):
                    # Check cancellation between retry attempts
                    if cancel_event and cancel_event.is_set():
                        _put("status", {"message": "Cancelling..."})
                        _put("error", {"message": "Investigation cancelled by user."})
                        error_emitted = True
                        break

                    handler = SSEEventHandler()
                    handler._last_fn_output = _fn_output_cache

                    if attempt > 1:
                        recovery_msg = (
                            f"[SYSTEM] The previous investigation attempt failed with: "
                            f"{last_error_detail}\n\n"
                            f"Please retry the investigation. If a sub-agent tool call "
                            f"failed, try a different or simpler query, or skip that "
                            f"data source and continue with the information you have."
                        )
                        agents_client.messages.create(
                            thread_id=thread_id,
                            role="user",
                            content=recovery_msg,
                        )
                        _put("status", {
                            "message": f"Retrying investigation (attempt {attempt}/{MAX_RUN_ATTEMPTS})...",
                        })
                        logger.info(
                            "Orchestrator retry attempt %d/%d after error: %s",
                            attempt, MAX_RUN_ATTEMPTS, last_error_detail[:300],
                        )

                    with agents_client.runs.stream(
                        thread_id=thread_id,
                        agent_id=orchestrator_id,
                        event_handler=handler,
                    ) as stream:
                        stream.until_done()

                    total_steps += handler.ui_step
                    total_tokens += handler.total_tokens

                    if handler.run_failed:
                        last_error_detail = handler.run_error_detail
                        if _is_capacity_error(last_error_detail):
                            logger.warning(
                                "Skipping orchestrator retry — Fabric capacity error: %s",
                                last_error_detail[:200],
                            )
                            error_emitted = True
                            _put("error", {
                                "message": (
                                    f"Investigation stopped — Fabric capacity exhausted. "
                                    f"{total_steps} steps completed.\n\n"
                                    f"{last_error_detail}"
                                ),
                            })
                            break
                        if attempt < MAX_RUN_ATTEMPTS:
                            logger.warning(
                                "Orchestrator run failed, will retry (attempt %d/%d): %s",
                                attempt, MAX_RUN_ATTEMPTS, last_error_detail[:300],
                            )
                            continue
                        else:
                            error_emitted = True
                            _put("error", {
                                "message": (
                                    f"Agent run interrupted — A backend query returned an error. "
                                    f"{total_steps} steps completed before the error. "
                                    f"Retried {MAX_RUN_ATTEMPTS} times.\n\n"
                                    f"Error detail: {last_error_detail}"
                                ),
                            })
                            break

                    if handler.response_text:
                        clean = SSEEventHandler._THINKING_RE.sub('', handler.response_text).strip()
                        # Emit message.complete with the full text
                        msg_id = handler._message_id or str(uuid.uuid4())
                        _put("message.complete", {"id": msg_id, "text": clean})
                        break
                    else:
                        # Fetch from thread — streaming may not have captured text
                        messages = agents_client.messages.list(thread_id=thread_id)
                        text = ""
                        for msg in messages:
                            if msg.role == "assistant":
                                text = ""
                                for block in msg.content:
                                    if hasattr(block, "text"):
                                        text += block.text.value + "\n"
                                break  # first item is the most recent
                        if text:
                            clean = SSEEventHandler._THINKING_RE.sub('', text).strip()
                            msg_id = handler._message_id or str(uuid.uuid4())
                            _put("message.complete", {"id": msg_id, "text": clean})
                            break

                        last_error_detail = (
                            f"Run produced no response after {handler.ui_step} steps."
                        )
                        if attempt < MAX_RUN_ATTEMPTS:
                            logger.warning(
                                "Orchestrator run produced no response, will retry (attempt %d/%d)",
                                attempt, MAX_RUN_ATTEMPTS,
                            )
                            continue
                        else:
                            error_emitted = True
                            _put("error", {
                                "message": (
                                    f"Investigation did not produce a final response "
                                    f"after {MAX_RUN_ATTEMPTS} attempts. "
                                    f"{total_steps} steps were completed."
                                ),
                            })

                if not error_emitted:
                    overall_elapsed = f"{time.monotonic() - overall_t0:.1f}s"
                    _put("run.complete", {
                        "steps": total_steps,
                        "time": overall_elapsed,
                    })

        except Exception as e:
            logger.exception("Orchestrator session run failed")
            _put("error", {"message": str(e)})
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    # -- Launch and yield (no EVENT_TIMEOUT — session manager owns lifecycle) --

    t = threading.Thread(target=_run_in_thread, daemon=True)
    t.start()

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item
