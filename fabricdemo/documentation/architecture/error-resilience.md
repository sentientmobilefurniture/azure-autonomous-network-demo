# Error Resilience

## Layer 1: Errors as 200 + Error Payload (OpenApiTool Compatibility)

Graph and telemetry endpoints catch ALL exceptions and return HTTP 200 with an `error` field. This is **required** because Foundry's `OpenApiTool` treats HTTP 4xx/5xx as fatal tool errors — the sub-agent run fails, the `ConnectedAgentTool` returns failure to the orchestrator, and the LLM never sees the error. By returning 200 + error text, the agent reads the error and self-corrects (e.g., fixes Gremlin syntax, adjusts container name).

```python
except Exception as e:
    return GraphQueryResponse(error=f"Graph query error: {e}. Read the error, fix the query, and retry.")
```

## Layer 2: Orchestrator Run Retry

`MAX_RUN_ATTEMPTS = 2`. On failure or no-response:
- Posts `[SYSTEM]` recovery message to thread with error details
- Tells orchestrator to retry with simpler queries or skip failing data sources
- Falls back to `messages.list()` to extract response text if streaming missed it

## Layer 3: Per-Event Timeout

`EVENT_TIMEOUT = 120` seconds. If no SSE event received for 2 minutes, emits stuck error and breaks. Frontend has separate 5-minute total timeout.

## Layer 4: Graceful Degradation (Prompt Rule)

Orchestrator prompt instructs: "If a sub-agent fails, continue with remaining agents and produce a partial report."
