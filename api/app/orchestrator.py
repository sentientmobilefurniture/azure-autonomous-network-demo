"""
Orchestrator bridge — runs the Foundry Orchestrator agent in a background
thread and yields SSE events via an async generator.

The Azure AI Agents SDK uses a synchronous callback-based streaming API
(AgentEventHandler). This module bridges it to async SSE by:
  1. Running the agent stream in a daemon thread
  2. Pushing SSE-shaped dicts to an asyncio.Queue from the callbacks
  3. Yielding from the queue in an async generator for EventSourceResponse

Falls back to stub responses when the orchestrator isn't configured
(no agent_ids.json or missing env vars).
"""

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Fabric-perspective log emitter (imported lazily to avoid circular imports)
def _emit_fabric_log(level: str, msg: str) -> None:
    """Emit a synthetic fabric-query-api log to the fabric SSE channel."""
    from app.routers.logs import broadcast_fabric_log
    from datetime import datetime, timezone as _tz
    broadcast_fabric_log({
        "ts": datetime.now(_tz.utc).strftime("%H:%M:%S.%f")[:-3],
        "level": level,
        "name": "fabric-query-api",
        "msg": msg,
    })

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = PROJECT_ROOT / "azure_config.env"
AGENT_IDS_FILE = PROJECT_ROOT / "scripts" / "agent_ids.json"

load_dotenv(CONFIG_FILE)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Check whether the Foundry orchestrator is ready to use."""
    if not AGENT_IDS_FILE.exists():
        return False
    if not os.environ.get("PROJECT_ENDPOINT"):
        return False
    if not os.environ.get("AI_FOUNDRY_PROJECT_NAME"):
        return False
    try:
        data = json.loads(AGENT_IDS_FILE.read_text())
        if not data.get("orchestrator", {}).get("id"):
            return False
    except (json.JSONDecodeError, KeyError):
        return False
    return True


def _load_orchestrator_id() -> str:
    data = json.loads(AGENT_IDS_FILE.read_text())
    return data["orchestrator"]["id"]


def _load_agent_names() -> dict[str, str]:
    """Map of agent_id → display name for resolving connected-agent calls."""
    data = json.loads(AGENT_IDS_FILE.read_text())
    names: dict[str, str] = {}
    orch = data.get("orchestrator", {})
    if orch.get("id"):
        names[orch["id"]] = orch.get("name", "Orchestrator")
    for sa in data.get("sub_agents", {}).values():
        if sa.get("id"):
            names[sa["id"]] = sa.get("name", sa["id"])
    return names


def _get_project_client():
    """Create an AIProjectClient with the project-scoped endpoint."""
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient

    base_endpoint = os.environ["PROJECT_ENDPOINT"].rstrip("/")
    project_name = os.environ["AI_FOUNDRY_PROJECT_NAME"]
    endpoint = f"{base_endpoint}/api/projects/{project_name}"
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


def load_agents_from_file() -> list[dict] | None:
    """Load agent list from agent_ids.json. Returns None if unavailable."""
    if not AGENT_IDS_FILE.exists():
        return None
    try:
        data = json.loads(AGENT_IDS_FILE.read_text())
        agents = []
        orch = data.get("orchestrator", {})
        if orch.get("id"):
            agents.append({"name": orch.get("name", "Orchestrator"), "id": orch["id"], "status": "active"})
        for sa in data.get("sub_agents", {}).values():
            if sa.get("id"):
                agents.append({"name": sa.get("name", "Unknown"), "id": sa["id"], "status": "active"})
        return agents if agents else None
    except Exception as e:
        logger.warning("Failed to load agent_ids.json: %s", e)
        return None


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
            self.t0 = time.time()
            self.step_starts: dict[str, float] = {}
            self.ui_step = 0
            self.total_tokens = 0
            self.response_text = ""

        def _elapsed(self) -> str:
            return f"{time.time() - self.t0:.1f}s"

        # -- Run lifecycle ---------------------------------------------------

        def on_thread_run(self, run):
            s = run.status
            status = s.value if hasattr(s, "value") else str(s)
            logger.info("on_thread_run: status=%s", status)

            if status == "completed" and run.usage:
                self.total_tokens = getattr(run.usage, "total_tokens", 0) or 0
            elif status == "failed":
                err = run.last_error
                # Extract structured error info if available
                code = getattr(err, "code", None) or (err.get("code") if isinstance(err, dict) else None) or "unknown"
                msg = getattr(err, "message", None) or (err.get("message") if isinstance(err, dict) else str(err))
                logger.error(
                    "Orchestrator run failed: [%s] %s  (steps completed: %d, elapsed: %s)",
                    code, msg, handler.ui_step if hasattr(handler, 'ui_step') else '?',
                    handler._elapsed() if hasattr(handler, '_elapsed') else '?',
                )
                _put("error", {
                    "message": (
                        f"Agent run interrupted \u2014 A backend query returned an error. "
                        f"The graph schema or data may not match the query. "
                        f"{handler.ui_step} steps completed before the error.\n\n"
                        f"Error detail: [{code}] {msg}"
                    ),
                })

        # -- Step lifecycle --------------------------------------------------

        def on_run_step(self, step):
            s = step.status
            status = s.value if hasattr(s, "value") else str(s)
            t = step.type
            step_type = t.value if hasattr(t, "value") else str(t)
            logger.info("on_run_step: id=%s status=%s type=%s", step.id, status, step_type)

            if status == "in_progress" and step.id not in self.step_starts:
                self.step_starts[step.id] = time.time()
                # Emit an early "thinking" event so UI shows activity
                _put("step_thinking", {"agent": "Orchestrator", "status": "calling sub-agent..."})

            elif status == "failed" and step_type == "tool_calls":
                # Capture and log full detail about the failed tool call
                start = self.step_starts.get(step.id, self.t0)
                duration = f"{time.time() - start:.1f}s"
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
                        tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
                        tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)
                        if tc_type == "connected_agent":
                            ca = tc.connected_agent if hasattr(tc, "connected_agent") else tc.get("connected_agent", {})
                            agent_id = getattr(ca, "agent_id", None) or ca.get("agent_id", "?")
                            failed_agent = agent_names.get(agent_id, getattr(ca, "name", None) or ca.get("name", agent_id))
                            args_raw = getattr(ca, "arguments", None) or ca.get("arguments", None)
                            if args_raw:
                                try:
                                    obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                                    failed_query = obj if isinstance(obj, str) else json.dumps(obj)
                                except Exception:
                                    failed_query = str(args_raw)
                        elif tc_type == "fabric_dataagent":
                            failed_agent = "FabricDataAgent"
                        elif tc_type == "azure_ai_search":
                            failed_agent = "AzureAISearch"

                logger.error(
                    "Step FAILED: agent=%s  duration=%s  code=%s  error=%s\n  query=%s",
                    failed_agent, duration, err_code, err_msg, failed_query[:500] if failed_query else "(none)",
                )

                # Emit fabric-perspective logs for failed Graph/Telemetry calls
                if failed_agent and ("Graph" in failed_agent or "Telemetry" in failed_agent):
                    endpoint = "/query/graph" if "Graph" in failed_agent else "/query/telemetry"
                    query_type = "GQL" if "Graph" in failed_agent else "KQL"
                    _emit_fabric_log("INFO", f"▶ POST {endpoint}  (from {failed_agent})")
                    if failed_query:
                        try:
                            q_obj = json.loads(failed_query) if failed_query.startswith("{") else None
                            q_body = q_obj.get("query", failed_query) if q_obj else failed_query
                        except Exception:
                            q_body = failed_query
                        _emit_fabric_log("DEBUG", f"{query_type} query:\n{q_body[:500]}")
                    _emit_fabric_log("ERROR", f"◀ POST {endpoint} FAILED [{err_code}]: {err_msg}")

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
                duration = f"{time.time() - start:.1f}s"

                if not hasattr(step.step_details, "tool_calls"):
                    return

                for tc in step.step_details.tool_calls:
                    self.ui_step += 1

                    tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
                    tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)

                    agent_name = tc_type
                    query = ""
                    response = ""

                    if tc_type == "connected_agent":
                        ca = (
                            tc.connected_agent
                            if hasattr(tc, "connected_agent")
                            else tc.get("connected_agent", {})
                        )
                        agent_name = getattr(ca, "name", None) or ca.get("name", None)
                        if not agent_name:
                            aid = getattr(ca, "agent_id", None) or ca.get("agent_id", "?")
                            agent_name = agent_names.get(aid, aid)

                        # Extract query (arguments sent to sub-agent)
                        args_raw = getattr(ca, "arguments", None) or ca.get("arguments", None)
                        if args_raw:
                            try:
                                obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                                query = obj if isinstance(obj, str) else json.dumps(obj)
                            except (json.JSONDecodeError, TypeError):
                                query = str(args_raw)

                        # Extract response (sub-agent output)
                        out = getattr(ca, "output", None) or ca.get("output", None)
                        if out:
                            response = str(out)

                    elif tc_type == "fabric_dataagent":
                        agent_name = "FabricDataAgent"
                    elif tc_type == "azure_ai_search":
                        agent_name = "AzureAISearch"

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

                    # Emit fabric-perspective logs for Graph/Telemetry agents
                    if agent_name and ("Graph" in agent_name or "Telemetry" in agent_name):
                        endpoint = "/query/graph" if "Graph" in agent_name else "/query/telemetry"
                        query_type = "GQL" if "Graph" in agent_name else "KQL"
                        _emit_fabric_log("INFO", f"▶ POST {endpoint}  (from {agent_name})")
                        if query:
                            # Try to extract the actual query string
                            try:
                                q_obj = json.loads(query) if query.startswith("{") else None
                                q_body = q_obj.get("query", query) if q_obj else query
                            except Exception:
                                q_body = query
                            _emit_fabric_log("DEBUG", f"{query_type} query:\n{q_body[:500]}")
                        if response:
                            resp_preview = response[:300].replace("\n", " ")
                            _emit_fabric_log("INFO", f"{query_type} response ({len(response)} chars, {duration}): {resp_preview}")
                        else:
                            _emit_fabric_log("WARNING", f"{query_type} returned empty response ({duration})")
                        _emit_fabric_log("INFO", f"◀ POST {endpoint} → 200  ({duration})")

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

    def _thread_target():
        handler = SSEEventHandler()
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

                with agents_client.runs.stream(
                    thread_id=thread.id,
                    agent_id=orchestrator_id,
                    event_handler=handler,
                ) as stream:
                    stream.until_done()

                # Emit the full response text
                if handler.response_text:
                    _put("message", {"text": handler.response_text})
                else:
                    # Fallback: fetch messages if streaming didn't capture text
                    messages = agents_client.messages.list(thread_id=thread.id)
                    text = ""
                    for msg in reversed(list(messages)):
                        if msg.role == "assistant":
                            for block in msg.content:
                                if hasattr(block, "text"):
                                    text += block.text.value + "\n"
                    if text:
                        _put("message", {"text": text.strip()})

                _put("run_complete", {
                    "steps": handler.ui_step,
                    "tokens": handler.total_tokens,
                    "time": handler._elapsed(),
                })

        except Exception as e:
            logger.exception("Orchestrator run failed")
            _put("error", {"message": str(e)})
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    # -- Launch and yield ----------------------------------------------------

    t = threading.Thread(target=_thread_target, daemon=True)
    t.start()

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item
