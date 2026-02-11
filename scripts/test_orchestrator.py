"""
test_orchestrator.py — Send a NOC alert to the Orchestrator agent and stream progress.

Sends a simulated network alert to the Orchestrator, which delegates to its
sub-agents (GraphExplorer, Telemetry, RunbookKB, HistoricalTicket) via
ConnectedAgentTool, then returns a consolidated diagnosis.

Streams live progress showing each run step, which sub-agent is being called,
timing, and token usage — suitable for piping into a UI.

Usage:
  uv run python test_orchestrator.py                  # Default VPN alert
  uv run python test_orchestrator.py "custom alert"   # Custom alert text
  uv run python test_orchestrator.py --quiet           # Only show final response
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import AgentEventHandler

# ── Config ──────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / "azure_config.env", override=True)

AGENT_IDS_FILE = PROJECT_ROOT / "agent_ids.json"

DEFAULT_ALERT = (
    "14:31:14.259 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION "
    "VPN tunnel unreachable — primary MPLS path down"
)

# ANSI colors for terminal output
C_DIM = "\033[2m"
C_BOLD = "\033[1m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_RESET = "\033[0m"


def load_orchestrator_id() -> str:
    """Load the Orchestrator agent ID from agent_ids.json."""
    if not AGENT_IDS_FILE.exists():
        print(f"ERROR: {AGENT_IDS_FILE.name} not found. Run provision_agents.py first.")
        sys.exit(1)

    data = json.loads(AGENT_IDS_FILE.read_text())
    agent_id = data.get("orchestrator", {}).get("id")
    if not agent_id:
        print("ERROR: No orchestrator ID in agent_ids.json.")
        sys.exit(1)

    return agent_id


def load_agent_names() -> dict[str, str]:
    """Load a map of agent_id -> name from agent_ids.json."""
    data = json.loads(AGENT_IDS_FILE.read_text())
    names = {}
    orch = data.get("orchestrator", {})
    if orch.get("id"):
        names[orch["id"]] = orch.get("name", "Orchestrator")
    for sa in data.get("sub_agents", {}).values():
        if sa.get("id"):
            names[sa["id"]] = sa.get("name", sa["id"])
    return names


def get_project_client() -> AIProjectClient:
    """Create an AIProjectClient with the project-scoped endpoint."""
    base_endpoint = os.environ["PROJECT_ENDPOINT"].rstrip("/")
    project_name = os.environ["AI_FOUNDRY_PROJECT_NAME"]
    endpoint = f"{base_endpoint}/api/projects/{project_name}"

    credential = DefaultAzureCredential()
    return AIProjectClient(endpoint=endpoint, credential=credential)


# ── Streaming Event Handler ─────────────────────────────────────────

class OrchestratorEventHandler(AgentEventHandler):
    """Streams run progress to the terminal, showing each step and sub-agent call."""

    def __init__(self, agent_names: dict[str, str]):
        super().__init__()
        self.agent_names = agent_names
        self.t0 = time.time()
        self.step_starts: dict[str, float] = {}
        self.step_count = 0
        self.total_tokens = 0
        self.response_text = ""

    def _elapsed(self) -> str:
        return f"{time.time() - self.t0:.1f}s"

    def _step_elapsed(self, step_id: str) -> str:
        start = self.step_starts.get(step_id, self.t0)
        return f"{time.time() - start:.1f}s"

    def on_thread_run(self, run):
        """Called when the run starts or changes status."""
        status = run.status if hasattr(run.status, 'value') else run.status
        status_str = status.value if hasattr(status, 'value') else str(status)

        if status_str == "in_progress":
            print(f"\n  {C_CYAN}Run{C_RESET} {run.id}")
            print(f"  {C_DIM}Status: {status_str}{C_RESET}")
        elif status_str == "completed":
            tokens = ""
            if run.usage:
                total = getattr(run.usage, 'total_tokens', None)
                if total:
                    self.total_tokens = total
                    tokens = f"  ({total:,} tokens)"
            print(f"\n  {C_GREEN}Run completed{C_RESET} in {self._elapsed()}{tokens}")
        elif status_str == "failed":
            error = run.last_error or "unknown error"
            print(f"\n  {C_RED}Run failed{C_RESET}: {error}")

    def on_run_step(self, step):
        """Called when a run step starts or completes."""
        status = step.status if hasattr(step.status, 'value') else step.status
        status_str = status.value if hasattr(status, 'value') else str(status)
        step_type = step.type if hasattr(step.type, 'value') else step.type
        type_str = step_type.value if hasattr(step_type, 'value') else str(step_type)

        if status_str == "in_progress":
            # Only count new steps (not re-fires)
            if step.id not in self.step_starts:
                self.step_count += 1
                self.step_starts[step.id] = time.time()

                if type_str == "tool_calls":
                    print(f"\n  {C_YELLOW}Step {self.step_count}{C_RESET} {C_DIM}[{self._elapsed()}]{C_RESET} calling sub-agent...", end="", flush=True)
                elif type_str == "message_creation":
                    print(f"\n  {C_YELLOW}Step {self.step_count}{C_RESET} {C_DIM}[{self._elapsed()}]{C_RESET} composing response...", end="", flush=True)

        elif status_str == "completed":
            duration = self._step_elapsed(step.id)
            tokens = ""
            if step.usage:
                total = getattr(step.usage, 'total_tokens', None)
                if total:
                    tokens = f" ({total:,}t)"

            if type_str == "tool_calls" and hasattr(step.step_details, 'tool_calls'):
                for tc in step.step_details.tool_calls:
                    tc_type = tc.type if hasattr(tc, 'type') else tc.get('type', '?')
                    tc_type_str = tc_type.value if hasattr(tc_type, 'value') else str(tc_type)

                    if tc_type_str == "connected_agent":
                        ca = tc.connected_agent if hasattr(tc, 'connected_agent') else tc.get('connected_agent', {})
                        # RunStepConnectedAgent uses 'agent_id' and 'name'
                        agent_name = getattr(ca, 'name', None) or ca.get('name', None)
                        if not agent_name:
                            agent_id = getattr(ca, 'agent_id', None) or ca.get('agent_id', '?')
                            agent_name = self.agent_names.get(agent_id, agent_id)
                        print(f"\n    {C_CYAN}↳ {agent_name}{C_RESET} {C_DIM}({duration}{tokens}){C_RESET}", flush=True)

                        # Show input (arguments) — the query sent to the sub-agent
                        args_raw = getattr(ca, 'arguments', None) or ca.get('arguments', None)
                        if args_raw:
                            try:
                                args_obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                                query = args_obj if isinstance(args_obj, str) else json.dumps(args_obj, indent=2)
                            except (json.JSONDecodeError, TypeError):
                                query = str(args_raw)
                            # Truncate long queries
                            if len(query) > 300:
                                query = query[:300] + "…"
                            print(f"      {C_DIM}Query:{C_RESET} {query}", flush=True)

                        # Show output (response) — the sub-agent's reply
                        output_raw = getattr(ca, 'output', None) or ca.get('output', None)
                        if output_raw:
                            output_str = str(output_raw)
                            if len(output_str) > 1500:
                                output_str = output_str[:1500] + "…"
                            print(f"      {C_DIM}Response:{C_RESET} {output_str}", flush=True)
                    elif tc_type_str == "fabric_dataagent":
                        print(f"\n    {C_CYAN}↳ FabricDataAgent{C_RESET} {C_DIM}({duration}{tokens}){C_RESET}", flush=True)
                    elif tc_type_str == "azure_ai_search":
                        print(f"\n    {C_CYAN}↳ AzureAISearch{C_RESET} {C_DIM}({duration}{tokens}){C_RESET}", flush=True)
                    else:
                        print(f"\n    {C_CYAN}↳ {tc_type_str}{C_RESET} {C_DIM}({duration}{tokens}){C_RESET}", flush=True)
            elif type_str == "message_creation":
                print(f" {C_DIM}({duration}{tokens}){C_RESET}", flush=True)

    def on_message_delta(self, delta):
        """Called for each chunk of the assistant's response."""
        if delta.text:
            self.response_text += delta.text.value

    def on_error(self, data):
        print(f"\n  {C_RED}Error: {data}{C_RESET}")


# ── Main ────────────────────────────────────────────────────────────

def run_alert(alert_text: str, quiet: bool = False):
    """Send an alert to the Orchestrator and stream progress."""
    orchestrator_id = load_orchestrator_id()
    agent_names = load_agent_names()
    client = get_project_client()

    print("=" * 72)
    print("  Autonomous Network NOC — Orchestrator Test")
    print("=" * 72)
    print(f"\n  Orchestrator: {orchestrator_id}")
    print(f"\n  {C_BOLD}Alert:{C_RESET}")
    print(f"    {alert_text}")

    with client:
        agents = client.agents

        # Create a thread
        thread = agents.threads.create()
        print(f"\n  Thread: {thread.id}")

        # Send the alert as a user message
        agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=alert_text,
        )

        # Stream the run
        handler = OrchestratorEventHandler(agent_names)
        print(f"\n{'-' * 72}")

        with agents.runs.stream(
            thread_id=thread.id,
            agent_id=orchestrator_id,
            event_handler=handler,
        ) as stream:
            stream.until_done()

        # Print the full response
        print(f"\n{'=' * 72}")
        print(f"  {C_BOLD}ORCHESTRATOR RESPONSE{C_RESET}")
        print(f"{'=' * 72}\n")

        if handler.response_text:
            print(handler.response_text)
        else:
            # Fallback: fetch messages if streaming didn't capture text
            messages = agents.messages.list(thread_id=thread.id)
            for msg in reversed(list(messages)):
                if msg.role == "assistant":
                    for block in msg.content:
                        if hasattr(block, "text"):
                            print(block.text.value)
                            print()

        # Summary
        print(f"\n{'-' * 72}")
        print(f"  Steps: {handler.step_count}  |  "
              f"Tokens: {handler.total_tokens:,}  |  "
              f"Time: {handler._elapsed()}")
        print()


def main():
    quiet = "--quiet" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    alert_text = " ".join(args) if args else DEFAULT_ALERT

    run_alert(alert_text, quiet=quiet)


if __name__ == "__main__":
    main()
