"""
test_function_tool.py — Isolated test of the V2 FunctionTool approach.

Proves that a Foundry agent can construct GQL queries and call a Python
function (query_graph) via FunctionTool + ToolSet auto-execution, bypassing
the Fabric Data Agent entirely.

This is a standalone proof-of-concept. It:
  1. Defines query_graph() using the same GQL execution logic as test_gql_query.py
  2. Creates a temporary Foundry agent with FunctionTool
  3. Sends a topology question in natural language
  4. Lets the agent construct the GQL, call the tool, and interpret results
  5. Prints the full conversation (tool calls + final answer)
  6. Cleans up the temporary agent

Prerequisites:
  - azure_config.env populated (PROJECT_ENDPOINT, MODEL_DEPLOYMENT_NAME,
    FABRIC_WORKSPACE_ID, FABRIC_GRAPH_MODEL_ID)
  - Graph Model exists and is responsive (run test_gql_query.py first)

Usage:
  cd /home/hanchoong/projects/autonomous-network-demo
  uv run python scripts/test_function_tool.py
  uv run python scripts/test_function_tool.py "What services depend on LINK-SYD-MEL-FIBRE-01?"
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import FunctionTool, ToolSet
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(str(PROJECT_ROOT / "azure_config.env"), override=True)

FABRIC_API = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")
WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")

# Foundry
PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT", "")
PROJECT_NAME = os.getenv("AI_FOUNDRY_PROJECT_NAME", "")
MODEL = os.getenv("MODEL_DEPLOYMENT_NAME", "")

# Fabric credential (separate from Foundry credential)
_fabric_credential = DefaultAzureCredential()


# ---------------------------------------------------------------------------
# GQL execution (extracted from test_gql_query.py)
# ---------------------------------------------------------------------------

def _get_fabric_headers() -> dict[str, str]:
    token = _fabric_credential.get_token(FABRIC_SCOPE).token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _execute_gql_raw(gql_query: str, max_retries: int = 5) -> dict:
    """Submit a GQL query to the Fabric GraphModel Execute Query (beta) API."""
    url = (
        f"{FABRIC_API}/workspaces/{WORKSPACE_ID}"
        f"/GraphModels/{GRAPH_MODEL_ID}/executeQuery"
    )
    body = {"query": gql_query}

    for attempt in range(1, max_retries + 1):
        headers = _get_fabric_headers()
        r = requests.post(url, headers=headers, json=body, params={"beta": "True"})

        if r.status_code == 200:
            return r.json()

        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", "0"))
            if not retry_after:
                try:
                    msg = r.json().get("message", "")
                    if "until:" in msg:
                        ts_str = msg.split("until:")[1].strip().rstrip(")")
                        ts_str = ts_str.replace("(UTC", "").strip()
                        blocked_until = datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")
                        blocked_until = blocked_until.replace(tzinfo=timezone.utc)
                        wait = (blocked_until - datetime.now(timezone.utc)).total_seconds()
                        retry_after = max(int(wait) + 1, 3)
                except Exception:
                    pass
            retry_after = max(retry_after, 15 * attempt)

            if attempt < max_retries:
                print(f"    ⏳ GQL rate-limited (429). Waiting {retry_after}s (retry {attempt}/{max_retries})...")
                time.sleep(retry_after)
                continue

        return {"error": True, "status_code": r.status_code, "detail": r.text[:500]}

    return {"error": True, "status_code": 429, "detail": "Max retries exceeded"}


# ---------------------------------------------------------------------------
# The FunctionTool callable — this is what the agent will call
# ---------------------------------------------------------------------------

def query_graph(gql_query: str) -> str:
    """Execute a GQL query against the Fabric Graph Model (network topology ontology).

    Args:
        gql_query: A GQL (Graph Query Language) query string using MATCH/RETURN syntax.
            Entity types: CoreRouter, TransportLink, AggSwitch, BaseStation,
            BGPSession, MPLSPath, Service, SLAPolicy.
            Relationships: connects_to, aggregates_to, backhauls_via,
            routes_via, depends_on, governed_by, peers_over.
            Example: MATCH (r:CoreRouter) RETURN r.RouterId, r.City LIMIT 10

    Returns:
        JSON string with query results containing 'status' and 'result'
        (columns + data rows), or an error message if the query fails.
    """
    print(f"    🔧 query_graph called with: {gql_query}")
    result = _execute_gql_raw(gql_query)
    output = json.dumps(result, ensure_ascii=False)
    # Truncate for readability in logs
    preview = output[:300] + "..." if len(output) > 300 else output
    print(f"    📊 Result preview: {preview}")
    return output


# ---------------------------------------------------------------------------
# Agent system prompt (minimal — just enough to test FunctionTool)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a network topology analysis agent. You answer questions about a
telecommunications network by querying a graph database using GQL.

You have access to the `query_graph` tool, which executes GQL queries
against the network topology ontology.

## Ontology schema

Entity types and key properties:
- CoreRouter: RouterId, City, Region, Vendor, Model
- TransportLink: LinkId, LinkType, CapacityGbps, DistanceKm
- AggSwitch: SwitchId, City, Model
- BaseStation: StationId, City, Type, FrequencyBand
- BGPSession: SessionId, ASNumber, State
- MPLSPath: PathId, PathType (PRIMARY/SECONDARY/TERTIARY), SourceCity, DestCity
- Service: ServiceId, ServiceType (EnterpriseVPN/Broadband/Mobile5G), CustomerName
- SLAPolicy: SLAPolicyId, AvailabilityTarget, MaxLatencyMs, PenaltyRate

Relationships:
- TransportLink -[:connects_to]-> CoreRouter
- AggSwitch -[:aggregates_to]-> CoreRouter
- BaseStation -[:backhauls_via]-> AggSwitch
- MPLSPath -[:routes_via]-> TransportLink
- Service -[:depends_on]-> MPLSPath | AggSwitch | BaseStation
- SLAPolicy -[:governed_by]-> Service
- BGPSession -[:peers_over]-> CoreRouter

## Query rules
1. Construct GQL queries using MATCH/RETURN syntax.
2. Use exact entity type names (PascalCase) and relationship names (snake_case).
3. Always include relevant property names in RETURN clauses.
4. For multi-hop queries, chain relationships:
   MATCH (l:TransportLink)<-[:routes_via]-(p:MPLSPath)<-[:depends_on]-(s:Service)
5. Use WHERE clauses with exact entity IDs (uppercase with hyphens).
6. Report raw results — do not invent data.
"""

# ---------------------------------------------------------------------------
# Default test questions
# ---------------------------------------------------------------------------

DEFAULT_QUESTIONS = [
    "List all core routers and their cities.",
    "What MPLS paths route via LINK-SYD-MEL-FIBRE-01, and what services depend on those paths?",
    "What SLA policies govern VPN-ACME-CORP?",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Validate config
    missing = []
    if not WORKSPACE_ID:
        missing.append("FABRIC_WORKSPACE_ID")
    if not GRAPH_MODEL_ID:
        missing.append("FABRIC_GRAPH_MODEL_ID")
    if not PROJECT_ENDPOINT:
        missing.append("PROJECT_ENDPOINT")
    if not PROJECT_NAME:
        missing.append("AI_FOUNDRY_PROJECT_NAME")
    if not MODEL:
        missing.append("MODEL_DEPLOYMENT_NAME")
    if missing:
        print(f"✗ Missing required config: {', '.join(missing)}")
        sys.exit(1)

    # Determine question(s) to test
    if len(sys.argv) > 1:
        questions = [" ".join(sys.argv[1:])]
    else:
        questions = DEFAULT_QUESTIONS

    # Build project-scoped endpoint
    endpoint = f"{PROJECT_ENDPOINT.rstrip('/')}/api/projects/{PROJECT_NAME}"

    print("=" * 72)
    print("  V2 FunctionTool Test — Direct GQL via Foundry Agent")
    print("=" * 72)
    print(f"  Foundry endpoint: {endpoint}")
    print(f"  Model: {MODEL}")
    print(f"  Workspace: {WORKSPACE_ID}")
    print(f"  Graph Model: {GRAPH_MODEL_ID}")
    print(f"  Questions: {len(questions)}")
    print()

    # Connect to Foundry
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=endpoint, credential=credential)

    # Build ToolSet with our query_graph function
    functions = FunctionTool(functions=[query_graph])
    toolset = ToolSet()
    toolset.add(functions)

    agent = None
    try:
        with project_client:
            agents_client = project_client.agents

            # Enable auto function calls (SDK will execute query_graph automatically)
            agents_client.enable_auto_function_calls(toolset)

            # Create a temporary test agent
            print("[1/4] Creating temporary test agent...")
            agent = agents_client.create_agent(
                model=MODEL,
                name="V2-FunctionTool-Test",
                instructions=SYSTEM_PROMPT,
                toolset=toolset,
            )
            print(f"  ✓ Agent created: {agent.id}")

            # Run each question
            for i, question in enumerate(questions, 1):
                print(f"\n{'━' * 72}")
                print(f"  Question {i}/{len(questions)}: {question}")
                print(f"{'━' * 72}")

                # Create thread
                thread = agents_client.threads.create()
                print(f"  Thread: {thread.id}")

                # Send user message
                agents_client.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=question,
                )

                # Run with auto function execution
                print(f"\n  Running agent (auto-executing tool calls)...")
                run = agents_client.runs.create_and_process(
                    thread_id=thread.id,
                    agent_id=agent.id,
                    toolset=toolset,
                )

                print(f"\n  Run status: {run.status}")
                if run.status == "failed":
                    print(f"  ✗ Error: {run.last_error}")
                    continue

                # Print token usage if available
                if hasattr(run, "usage") and run.usage:
                    print(f"  Tokens: prompt={run.usage.prompt_tokens}, "
                          f"completion={run.usage.completion_tokens}, "
                          f"total={run.usage.total_tokens}")

                # Get final messages
                messages = agents_client.messages.list(thread_id=thread.id)
                print(f"\n  {'─' * 60}")
                print(f"  Agent response:")
                print(f"  {'─' * 60}")
                for msg in reversed(list(messages)):
                    if msg.role == "assistant":
                        for content in msg.content:
                            if hasattr(content, "text"):
                                # Indent the response for readability
                                for line in content.text.value.splitlines():
                                    print(f"  {line}")
                        break  # Only print the last assistant message

                # Pause between questions to avoid rate-limiting
                if i < len(questions):
                    print(f"\n  (pausing 5s before next question...)")
                    time.sleep(5)

    except Exception as exc:
        print(f"\n  ✗ Unexpected error: {exc}")
        raise
    finally:
        # Clean up the temporary agent
        if agent:
            print(f"\n[4/4] Cleaning up test agent {agent.id}...")
            try:
                cleanup_client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
                with cleanup_client:
                    cleanup_client.agents.delete_agent(agent.id)
                print("  ✓ Agent deleted.")
            except Exception as e:
                print(f"  ⚠ Could not delete agent: {e}")

    print(f"\n{'═' * 72}")
    print("  Test complete.")
    print("═" * 72)


if __name__ == "__main__":
    main()
