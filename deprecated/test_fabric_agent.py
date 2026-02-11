"""
test_fabric_agent.py — Run test queries against the Fabric Data Agent.

Runs the test suite from data/prompts/data_agent_instructions.md against the
published Data Agent API. Each query checks for expected entity IDs in the
response and reports pass/fail with timing.

Usage:
  uv run python test_fabric_agent.py              # Run all tests
  uv run python test_fabric_agent.py --smoke       # Smoke tests only (Q1-Q3)
  uv run python test_fabric_agent.py --query 7a    # Run a single query by ID
  uv run python test_fabric_agent.py --anti        # Include the Q14 anti-pattern test
"""

import argparse
import os
import sys
import time
import typing as t
import uuid

from azure.identity import DefaultAzureCredential, InteractiveBrowserCredential
from openai import OpenAI
from openai._models import FinalRequestOptions
from openai._types import Omit
from openai._utils import is_given
from dotenv import load_dotenv

load_dotenv("azure_config.env")

# ---------------------------------------------------------------------------
# Config — published Fabric Data Agent endpoint
# ---------------------------------------------------------------------------
_WORKSPACE_ID = os.environ.get("FABRIC_WORKSPACE_ID", "")
_DATA_AGENT_ID = os.environ.get("FABRIC_DATA_AGENT_ID", "")
BASE_URL = (
    f"https://api.fabric.microsoft.com/v1/workspaces/"
    f"{_WORKSPACE_ID}/"
    f"dataagents/{_DATA_AGENT_ID}/"
    f"aiassistant/openai"
)
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

# ---------------------------------------------------------------------------
# Test queries — mirrors data/prompts/data_agent_instructions.md
# ---------------------------------------------------------------------------
# Each entry: (id, group, question, [expected substrings in response])
# Expected strings are entity IDs / values that MUST appear for a pass.

TEST_QUERIES: list[tuple[str, str, str, list[str]]] = [
    # --- Smoke tests ---
    ("Q1", "smoke", "How many core routers exist in the network?",
     ["CORE-SYD-01", "CORE-MEL-01", "CORE-BNE-01"]),

    ("Q2", "smoke", "List all transport links with LinkType DWDM_100G.",
     ["LINK-SYD-MEL-FIBRE-01", "LINK-SYD-MEL-FIBRE-02",
      "LINK-SYD-BNE-FIBRE-01", "LINK-MEL-BNE-FIBRE-01"]),

    ("Q3", "smoke", "What is the capacity of TransportLink LINK-SYD-MEL-FIBRE-01?",
     ["100", "CORE-SYD-01", "CORE-MEL-01"]),

    # --- Single-hop relationship traversals ---
    ("Q4", "single-hop", "Which aggregation switches are in Sydney?",
     ["AGG-SYD-NORTH-01", "AGG-SYD-SOUTH-01"]),

    ("Q5", "single-hop", "Which base stations backhaul via AGG-MEL-EAST-01?",
     ["GNB-MEL-3011", "GNB-MEL-3012"]),

    ("Q6", "single-hop", "What SLA policy governs VPN-BIGBANK?",
     ["SLA-BIGBANK-SILVER"]),

    # --- Demo scenario: fibre cut blast radius (2-step) ---
    ("Q7a", "blast-radius", "Which MPLS paths route via TransportLink LINK-SYD-MEL-FIBRE-01?",
     ["MPLS-PATH-SYD-MEL-PRIMARY"]),

    ("Q7b", "blast-radius", "Which services depend on MPLS-PATH-SYD-MEL-PRIMARY?",
     ["VPN-ACME-CORP", "VPN-BIGBANK"]),

    # --- Alternate path discovery ---
    ("Q8", "alt-path", "Which MPLS paths have PathType SECONDARY?",
     ["MPLS-PATH-SYD-MEL-SECONDARY"]),

    ("Q9", "alt-path", "What transport links does MPLS-PATH-SYD-MEL-SECONDARY route via?",
     ["LINK-SYD-MEL-FIBRE-02"]),

    ("Q10", "alt-path", "What is the SourceRouterId and TargetRouterId of LINK-SYD-MEL-FIBRE-02?",
     ["CORE-SYD-01", "CORE-MEL-01"]),

    # --- SLA exposure ---
    ("Q11", "sla", "Which SLA policies have PenaltyPerHourUSD greater than 0?",
     ["SLA-ACME-GOLD", "SLA-BIGBANK-SILVER", "SLA-OZMINE-GOLD"]),

    ("Q12", "sla", "What service does SLA-ACME-GOLD govern? Include the CustomerName and ActiveUsers.",
     ["VPN-ACME-CORP", "ACME"]),

    # --- BGP impact ---
    ("Q13", "bgp", "Which BGP sessions involve CoreRouter CORE-SYD-01?",
     ["BGP-SYD-MEL-01", "BGP-SYD-BNE-01"]),
]

# Anti-pattern query — only run with --anti flag
ANTI_PATTERN_QUERY = (
    "Q14", "anti-pattern",
    "What services and SLA policies are affected if LINK-SYD-MEL-FIBRE-01 fails?",
    ["VPN-ACME-CORP", "VPN-BIGBANK", "SLA-ACME-GOLD", "SLA-BIGBANK-SILVER"],
)

# Group labels for display
GROUP_LABELS = {
    "smoke": "Smoke Tests",
    "single-hop": "Single-Hop Traversals",
    "blast-radius": "Blast Radius (Demo Flow)",
    "alt-path": "Alternate Path Discovery",
    "sla": "SLA Exposure",
    "bgp": "BGP Impact",
    "anti-pattern": "Anti-Pattern (Expected Failure)",
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def get_fabric_token() -> str:
    """Get a bearer token for the Fabric API."""
    try:
        credential = DefaultAzureCredential()
        token = credential.get_token(FABRIC_SCOPE)
        print("  ✅ Authenticated via DefaultAzureCredential")
        return token.token
    except Exception:
        print("  ⚠️  Falling back to interactive browser login...")
        credential = InteractiveBrowserCredential()
        token = credential.get_token(FABRIC_SCOPE)
        print("  ✅ Authenticated via browser")
        return token.token


# ---------------------------------------------------------------------------
# Custom OpenAI client for Fabric Data Agent
# ---------------------------------------------------------------------------
class FabricOpenAI(OpenAI):
    def __init__(
        self,
        bearer_token: str,
        api_version: str = os.environ.get("FABRIC_DATA_AGENT_API_VERSION", "2024-05-01-preview"),
        **kwargs: t.Any,
    ) -> None:
        self._bearer_token = bearer_token
        self.api_version = api_version
        default_query = kwargs.pop("default_query", {})
        default_query["api-version"] = self.api_version
        super().__init__(
            api_key="not-used",
            base_url=BASE_URL,
            default_query=default_query,
            **kwargs,
        )

    def _prepare_options(self, options: FinalRequestOptions) -> None:
        headers: dict[str, str | Omit] = (
            {**options.headers} if is_given(options.headers) else {}
        )
        options.headers = headers
        headers["Authorization"] = f"Bearer {self._bearer_token}"
        if "Accept" not in headers:
            headers["Accept"] = "application/json"
        if "ActivityId" not in headers:
            headers["ActivityId"] = str(uuid.uuid4())
        return super()._prepare_options(options)


# ---------------------------------------------------------------------------
# Run a single query and return (response_text, elapsed_seconds, status)
# ---------------------------------------------------------------------------
def run_query(
    client: FabricOpenAI,
    assistant_id: str,
    question: str,
    timeout: int = 120,
    poll_interval: int = 3,
) -> tuple[str, float, str]:
    """Send a question, poll for completion, return (answer, seconds, status)."""
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=question
    )
    run = client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id=assistant.id
    )

    terminal = {"completed", "failed", "cancelled", "requires_action", "expired"}
    start = time.time()

    while run.status not in terminal:
        if time.time() - start > timeout:
            break
        time.sleep(poll_interval)
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id, run_id=run.id
        )

    elapsed = time.time() - start
    answer = ""

    if run.status == "completed":
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="asc")
        for m in msgs:
            if m.role == "assistant" and m.content:
                for block in m.content:
                    if hasattr(block, "text"):
                        answer += block.text.value + "\n"

    # Cleanup thread
    try:
        client.beta.threads.delete(thread_id=thread.id)
    except Exception:
        pass

    return answer.strip(), elapsed, run.status


# ---------------------------------------------------------------------------
# Check expected strings in response
# ---------------------------------------------------------------------------
def check_expected(response: str, expected: list[str]) -> tuple[list[str], list[str]]:
    """Return (found, missing) lists from expected substrings."""
    upper_response = response.upper()
    found = [e for e in expected if e.upper() in upper_response]
    missing = [e for e in expected if e.upper() not in upper_response]
    return found, missing


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Test Fabric Data Agent queries")
    p.add_argument("--smoke", action="store_true", help="Run smoke tests only (Q1-Q3)")
    p.add_argument("--query", type=str, help="Run a single query by ID (e.g. 7a, Q7a)")
    p.add_argument("--anti", action="store_true", help="Include Q14 anti-pattern test")
    p.add_argument("--timeout", type=int, default=120, help="Per-query timeout in seconds")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    args = parse_args()

    # Build query list based on flags
    queries = list(TEST_QUERIES)
    if args.anti:
        queries.append(ANTI_PATTERN_QUERY)

    if args.smoke:
        queries = [q for q in queries if q[1] == "smoke"]
    elif args.query:
        qid = args.query.upper() if args.query.upper().startswith("Q") else f"Q{args.query.upper()}"
        queries = [q for q in queries if q[0] == qid]
        if not queries:
            print(f"❌ Unknown query ID: {args.query}")
            print(f"   Valid IDs: {', '.join(q[0] for q in TEST_QUERIES)}")
            sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  Fabric Data Agent Test Suite — {len(queries)} queries")
    print(f"  Endpoint: {BASE_URL[:70]}...")
    print(f"  Timeout:  {args.timeout}s per query")
    print(f"{'='*70}\n")

    # Auth
    token = get_fabric_token()
    client = FabricOpenAI(bearer_token=token)

    # Create a shared assistant (reused across queries)
    assistant = client.beta.assistants.create(model="not used")
    print(f"  Assistant ID: {assistant.id}\n")

    # Run queries
    results: list[dict] = []
    current_group = ""

    for qid, group, question, expected in queries:
        # Print group header on change
        if group != current_group:
            current_group = group
            label = GROUP_LABELS.get(group, group)
            print(f"\n── {label} {'─' * (55 - len(label))}")

        print(f"\n  [{qid}] {question}")
        answer, elapsed, status = run_query(
            client, assistant.id, question, timeout=args.timeout
        )

        if status == "completed":
            found, missing = check_expected(answer, expected)
            passed = len(missing) == 0

            icon = "✅" if passed else "❌"
            print(f"  {icon}  {elapsed:.1f}s | {status}")

            if not passed:
                print(f"       Missing: {', '.join(missing)}")

            # Show a truncated response
            preview = answer[:200].replace("\n", " ")
            if len(answer) > 200:
                preview += "..."
            print(f"       Response: {preview}")

            results.append({
                "id": qid, "group": group, "passed": passed,
                "elapsed": elapsed, "status": status,
                "found": found, "missing": missing,
            })
        else:
            print(f"  ⚠️   {elapsed:.1f}s | {status}")
            if status == "failed":
                print(f"       Error: (see Fabric portal for details)")
            results.append({
                "id": qid, "group": group, "passed": False,
                "elapsed": elapsed, "status": status,
                "found": [], "missing": expected,
            })

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    total_time = sum(r["elapsed"] for r in results)

    print(f"\n{'='*70}")
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"  Total time: {total_time:.1f}s ({total_time/total:.1f}s avg per query)")
    print(f"{'='*70}")

    if failed > 0:
        print(f"\n  Failed queries:")
        for r in results:
            if not r["passed"]:
                reason = f"missing: {', '.join(r['missing'])}" if r["status"] == "completed" else r["status"]
                print(f"    {r['id']}: {reason}")

    print()
    sys.exit(0 if failed == 0 else 1)
