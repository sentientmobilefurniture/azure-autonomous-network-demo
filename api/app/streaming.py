"""Stream agent.run() events → SSE events matching the frontend schema.

Translates the agent-framework's AgentResponseUpdate objects into the same
SSE event format that the frontend already consumes (tool_call.start,
message.delta, etc.), so no frontend changes are needed.

The framework streams function_call content items token-by-token (each
argument token is a separate update). This module accumulates them and only
emits tool_call.start once the function_result arrives (which signals the
call is complete).
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from agent_framework import AgentSession

logger = logging.getLogger(__name__)


async def stream_agent_to_sse(
    agent,
    alert_text: str,
    session: AgentSession | None = None,
) -> AsyncGenerator[dict, None]:
    """Run agent.run(stream=True) and translate to SSE event dicts.

    Yields dicts with ``event`` and ``data`` keys matching the existing
    frontend SSE schema:
      - run.start
      - tool_call.start / tool_call.complete
      - message.start / message.delta / message.complete
      - run.complete
      - error
    """
    msg_id = str(uuid.uuid4())
    step_counter = 0
    accumulated_text = ""
    message_started = False

    # Track pending function calls being streamed token-by-token
    # Key: call_id, Value: {name, arguments_parts: list[str]}
    pending_calls: dict[str, dict] = {}

    yield {
        "event": "run.start",
        "data": json.dumps({
            "run_id": "",
            "alert": alert_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    }

    # Track session creation for thread_id propagation
    agent_session = session
    if agent_session is None:
        agent_session = agent.create_session()

    yield {
        "event": "session.created",
        "data": json.dumps({
            "thread_id": agent_session.session_id,
        }),
    }

    try:
        stream = agent.run(alert_text, stream=True, session=agent_session)
        async for update in stream:
            for content in (update.contents or []):
                if content.type == "text" and content.text:
                    if not message_started:
                        message_started = True
                        yield {
                            "event": "message.start",
                            "data": json.dumps({"id": msg_id}),
                        }
                    accumulated_text += content.text
                    yield {
                        "event": "message.delta",
                        "data": json.dumps({
                            "id": msg_id,
                            "text": content.text,
                        }),
                    }

                elif content.type == "function_call":
                    # Function calls are streamed token-by-token.
                    # Accumulate arguments until function_result arrives.
                    call_id = getattr(content, "call_id", "") or ""
                    name = getattr(content, "name", "") or ""
                    args_raw = getattr(content, "arguments", "") or ""
                    if isinstance(args_raw, dict):
                        args_str = json.dumps(args_raw)
                    else:
                        args_str = str(args_raw)

                    if call_id not in pending_calls:
                        pending_calls[call_id] = {
                            "name": name,
                            "arguments_parts": [],
                        }
                    if name and not pending_calls[call_id]["name"]:
                        pending_calls[call_id]["name"] = name
                    if args_str:
                        pending_calls[call_id]["arguments_parts"].append(args_str)

                elif content.type == "function_result":
                    call_id = getattr(content, "call_id", "") or ""
                    name = getattr(content, "name", "") or ""

                    # Extract result text
                    result_text = ""
                    if hasattr(content, "result") and content.result is not None:
                        result_text = str(content.result)
                    elif hasattr(content, "text") and content.text:
                        result_text = content.text

                    # Emit the accumulated tool_call.start
                    step_counter += 1
                    pending = pending_calls.pop(call_id, None)
                    tool_name = name or (pending["name"] if pending else "unknown")
                    full_args = "".join(pending["arguments_parts"]) if pending else ""

                    # Try to parse JSON arguments for display
                    display_query = full_args
                    try:
                        parsed = json.loads(full_args)
                        if isinstance(parsed, dict):
                            # Extract the most useful field for display
                            display_query = parsed.get("query", json.dumps(parsed, indent=2))
                    except (json.JSONDecodeError, ValueError):
                        pass

                    yield {
                        "event": "tool_call.start",
                        "data": json.dumps({
                            "id": call_id or str(uuid.uuid4()),
                            "step": step_counter,
                            "agent": tool_name,
                            "query": str(display_query)[:500],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }),
                    }

                    yield {
                        "event": "tool_call.complete",
                        "data": json.dumps({
                            "id": call_id or "",
                            "step": step_counter,
                            "agent": tool_name,
                            "duration": "",
                            "query": str(display_query)[:500],
                            "response": result_text[:2000],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }),
                    }

                elif content.type == "usage":
                    # Usage info — include in run.complete
                    pass

        if accumulated_text:
            yield {
                "event": "message.complete",
                "data": json.dumps({
                    "id": msg_id,
                    "text": accumulated_text,
                }),
            }

        yield {
            "event": "run.complete",
            "data": json.dumps({
                "steps": step_counter,
                "time": "",
            }),
        }

    except Exception as e:
        logger.exception("Agent streaming error")
        yield {
            "event": "error",
            "data": json.dumps({"message": str(e)}),
        }
