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
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

import app.paths  # noqa: F401  # side-effect: loads .env
from app.agent_ids import load_agent_ids, get_agent_names, get_agent_list

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
# SSE event generator (real orchestrator)
# ---------------------------------------------------------------------------

async def run_orchestrator(alert_text: str) -> AsyncGenerator[dict, None]:
    """Run the Foundry Orchestrator agent and yield SSE events.

    Spins up a background thread to drive the synchronous AgentEventHandler,
    bridges events to this async generator via asyncio.Queue.
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

    # -- Handler (runs in background thread) ---------------------------------

    class SSEEventHandler(AgentEventHandler):
        """Converts AgentEventHandler callbacks to SSE events on the queue."""

        def __init__(self):
            super().__init__()
            self.t0 = time.monotonic()
            self.step_starts: dict[str, float] = {}
            self.ui_step = 0
            self.total_tokens = 0
            self.response_text = ""
            self.run_failed = False
            self.run_error_detail = ""

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
                    # Extract structured error info if available
                    code = getattr(err, "code", None) or (err.get("code") if isinstance(err, dict) else None) or "unknown"
                    msg = getattr(err, "message", None) or (err.get("message") if isinstance(err, dict) else str(err))
                self.run_failed = True
                self.run_error_detail = f"[{code}] {msg}"
                logger.error(
                    "Orchestrator run failed: [%s] %s  (steps completed: %d, elapsed: %s)",
                    code, msg, self.ui_step,
                    self._elapsed(),
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
            return tc_type

        def _extract_arguments(self, tc) -> str:
            """Parse and extract arguments from a tool call."""
            tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
            tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)
            if tc_type != "connected_agent":
                return ""
            ca = tc.connected_agent if hasattr(tc, "connected_agent") else tc.get("connected_agent", {})
            args_raw = getattr(ca, "arguments", None) or ca.get("arguments", None)
            if not args_raw:
                return ""
            try:
                obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                return obj if isinstance(obj, str) else json.dumps(obj)
            except Exception:
                return str(args_raw)

        # -- Step lifecycle --------------------------------------------------

        def on_run_step(self, step):
            s = step.status
            status = s.value if hasattr(s, "value") else str(s)
            t = step.type
            step_type = t.value if hasattr(t, "value") else str(t)
            logger.info("on_run_step: id=%s status=%s type=%s", step.id, status, step_type)

            if status == "in_progress" and step.id not in self.step_starts:
                self.step_starts[step.id] = time.monotonic()
                # Emit an early "thinking" event so UI shows activity
                _put("step_thinking", {"agent": "Orchestrator", "status": "calling sub-agent..."})

            elif status == "failed" and step_type == "tool_calls":
                # Capture and log full detail about the failed tool call
                start = self.step_starts.get(step.id, self.t0)
                duration = f"{time.monotonic() - start:.1f}s"
                last_err = step.last_error if hasattr(step, "last_error") else None
                err_code = ""
                err_msg = "(no error detail)"
                if last_err:
                    err_code = getattr(last_err, "code", None) or (last_err.get("code") if isinstance(last_err, dict) else "") or ""
                    err_msg = getattr(last_err, "message", None) or (last_err.get("message") if isinstance(last_err, dict) else str(last_err)) or ""

                # Try to identify which tool/agent failed
                failed_agent = "unknown"
                failed_query = ""
                if hasattr(step, "step_details") and hasattr(step.step_details, "tool_calls"):
                    for tc in step.step_details.tool_calls:
                        failed_agent = self._resolve_agent_name(tc)
                        failed_query = self._extract_arguments(tc)

                logger.error(
                    "Step FAILED: agent=%s  duration=%s  code=%s  error=%s\n  query=%s",
                    failed_agent, duration, err_code, err_msg, failed_query[:500] if failed_query else "(none)",
                )

                self.ui_step += 1
                _put("step_complete", {
                    "step": self.ui_step,
                    "agent": failed_agent,
                    "duration": duration,
                    "query": failed_query[:500] if failed_query else "",
                    "response": f"FAILED: [{err_code}] {err_msg}",
                    "error": True,
                })

            elif status == "completed" and step_type == "tool_calls":
                start = self.step_starts.get(step.id, self.t0)
                duration = f"{time.monotonic() - start:.1f}s"

                if not hasattr(step.step_details, "tool_calls"):
                    return

                for tc in step.step_details.tool_calls:
                    self.ui_step += 1

                    agent_name = self._resolve_agent_name(tc)
                    query = self._extract_arguments(tc)
                    response = ""

                    # Extract response (sub-agent output for connected_agent)
                    tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
                    tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)
                    if tc_type == "connected_agent":
                        ca = (
                            tc.connected_agent
                            if hasattr(tc, "connected_agent")
                            else tc.get("connected_agent", {})
                        )
                        out = getattr(ca, "output", None) or ca.get("output", None)
                        if out:
                            response = str(out)

                    # Truncate for the frontend
                    if len(query) > 500:
                        query = query[:500] + "…"
                    if len(response) > 2000:
                        response = response[:2000] + "…"

                    logger.info("Emitting step %d: agent=%s duration=%s", self.ui_step, agent_name, duration)
                    if query:
                        logger.info("  ↳ query: %s", query[:300])
                    if response:
                        logger.info("  ↳ response (%d chars): %s", len(response), response[:200])

                    _put("step_start", {"step": self.ui_step, "agent": agent_name})
                    _put("step_complete", {
                        "step": self.ui_step,
                        "agent": agent_name,
                        "duration": duration,
                        "query": query,
                        "response": response,
                    })

        # -- Streaming message text ------------------------------------------

        def on_message_delta(self, delta):
            if delta.text:
                self.response_text += delta.text.value

        def on_error(self, data):
            _put("error", {"message": str(data)})

    # -- Thread target -------------------------------------------------------

    MAX_RUN_ATTEMPTS = 2  # initial + 1 retry on failure

    def _thread_target():
        overall_t0 = time.monotonic()
        total_steps = 0
        total_tokens = 0
        error_emitted = False

        try:
            _put("run_start", {
                "run_id": "",
                "alert": alert_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            client = _get_project_client()
            with client:
                agents_client = client.agents
                thread = agents_client.threads.create()
                agents_client.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=alert_text,
                )

                last_error_detail = ""
                for attempt in range(1, MAX_RUN_ATTEMPTS + 1):
                    handler = SSEEventHandler()

                    if attempt > 1:
                        # Post a recovery message so the orchestrator knows
                        # the previous attempt failed and can adjust its approach
                        recovery_msg = (
                            f"[SYSTEM] The previous investigation attempt failed with: "
                            f"{last_error_detail}\n\n"
                            f"Please retry the investigation. If a sub-agent tool call "
                            f"failed, try a different or simpler query, or skip that "
                            f"data source and continue with the information you have."
                        )
                        agents_client.messages.create(
                            thread_id=thread.id,
                            role="user",
                            content=recovery_msg,
                        )
                        _put("step_thinking", {
                            "agent": "Orchestrator",
                            "status": f"Retrying investigation (attempt {attempt}/{MAX_RUN_ATTEMPTS})...",
                        })
                        logger.info(
                            "Orchestrator retry attempt %d/%d after error: %s",
                            attempt, MAX_RUN_ATTEMPTS, last_error_detail[:300],
                        )

                    with agents_client.runs.stream(
                        thread_id=thread.id,
                        agent_id=orchestrator_id,
                        event_handler=handler,
                    ) as stream:
                        stream.until_done()

                    # Accumulate totals across retry attempts
                    total_steps += handler.ui_step
                    total_tokens += handler.total_tokens

                    # Check if the run failed
                    if handler.run_failed:
                        last_error_detail = handler.run_error_detail
                        if attempt < MAX_RUN_ATTEMPTS:
                            logger.warning(
                                "Orchestrator run failed, will retry (attempt %d/%d): %s",
                                attempt, MAX_RUN_ATTEMPTS, last_error_detail[:300],
                            )
                            continue
                        else:
                            # Final attempt also failed — emit the error
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

                    # Check if the run succeeded with response text
                    if handler.response_text:
                        # Success — emit the response and break
                        _put("message", {"text": handler.response_text})
                        break
                    else:
                        # Try to fetch messages — the run may have completed
                        # but streaming didn't capture the text
                        messages = agents_client.messages.list(thread_id=thread.id)
                        text = ""
                        for msg in reversed(list(messages)):
                            if msg.role == "assistant":
                                for block in msg.content:
                                    if hasattr(block, "text"):
                                        text += block.text.value + "\n"
                        if text:
                            _put("message", {"text": text.strip()})
                            break

                        # No response text AND no error means the run died silently
                        # Capture the error for the retry message
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
                            # Final attempt also failed — emit what we have
                            error_emitted = True
                            _put("error", {
                                "message": (
                                    f"Investigation did not produce a final response "
                                    f"after {MAX_RUN_ATTEMPTS} attempts. "
                                    f"{total_steps} steps were completed."
                                ),
                            })

                # Only emit run_complete if no error was emitted
                if not error_emitted:
                    overall_elapsed = f"{time.monotonic() - overall_t0:.1f}s"
                    _put("run_complete", {
                        "steps": total_steps,
                        "tokens": total_tokens,
                        "time": overall_elapsed,
                    })

        except Exception as e:
            logger.exception("Orchestrator run failed")
            _put("error", {"message": str(e)})
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    # -- Launch and yield ----------------------------------------------------

    t = threading.Thread(target=_thread_target, daemon=True)
    t.start()

    # Yield events with a per-event timeout to detect stuck investigations.
    # Normal runs emit events every few seconds; 2 min of silence means
    # the orchestrator or a sub-agent is hung.
    EVENT_TIMEOUT = 120  # seconds
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=EVENT_TIMEOUT)
        except asyncio.TimeoutError:
            yield {
                "event": "error",
                "data": json.dumps({
                    "message": (
                        "Investigation appears stuck — no progress for 2 minutes. "
                        "Try submitting the alert again."
                    ),
                }),
            }
            break
        if item is None:
            break
        yield item
