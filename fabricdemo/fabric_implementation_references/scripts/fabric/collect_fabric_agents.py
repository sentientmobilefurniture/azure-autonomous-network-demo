"""
collect_fabric_agents.py — Discover Fabric Data Agent artifact IDs and populate azure_config.env.

Queries the Fabric REST API to list all items in the workspace and find
Data Agent artifacts. The user can assign each Data Agent to a role:
  - GRAPH_DATA_AGENT_ID   → used by GraphExplorerAgent (ontology/Lakehouse)
  - TELEMETRY_DATA_AGENT_ID → used by TelemetryAgent (Eventhouse)

Prerequisites:
  - azure_config.env with FABRIC_WORKSPACE_ID populated
    (run populate_fabric_config.py first)
  - An Azure identity with Viewer role on the Fabric workspace

Usage:
  uv run python collect_fabric_agents.py
"""

import os
import re
import sys

import requests

from _config import FABRIC_API, ENV_FILE, get_fabric_headers

# Item types that could represent a Data Agent in Fabric.
# The official type may vary — we search broadly and also show unrecognised types.
DATA_AGENT_TYPES = {"DataAgent", "DataAgentDefinition", "Agent", "AISkill"}


def list_workspace_items(headers: dict, workspace_id: str) -> list[dict]:
    """List all items in the workspace, handling pagination."""
    items = []
    url = f"{FABRIC_API}/workspaces/{workspace_id}/items"
    while url:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("value", []))
        url = data.get("continuationUri")
    return items


def find_data_agents(items: list[dict]) -> list[dict]:
    """Find items that look like Data Agents."""
    agents = []
    for item in items:
        item_type = item.get("type", "")
        name = item.get("displayName", "").lower()
        # Match by type or by name heuristic (contains "agent" or "data agent")
        if item_type in DATA_AGENT_TYPES or "agent" in name:
            agents.append(item)
    return agents


def update_env_file(updates: dict[str, str]):
    """Update key=value pairs in azure_config.env, preserving structure."""
    with open(ENV_FILE, "r") as f:
        content = f.read()

    for key, value in updates.items():
        pattern = rf"^({re.escape(key)}=)(.*)$"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, rf"\g<1>{value}", content, flags=re.MULTILINE)
        else:
            content = content.rstrip("\n") + f"\n{key}={value}\n"

    with open(ENV_FILE, "w") as f:
        f.write(content)


def select_agent(agents: list[dict], role: str, exclude_id: str | None = None) -> dict | None:
    """Prompt the user to select a Data Agent for a given role."""
    candidates = [a for a in agents if a["id"] != exclude_id] if exclude_id else agents

    if not candidates:
        print(f"\n  No remaining Data Agent candidates for {role}.")
        return None

    print(f"\n  Select the Data Agent for {role}:")
    for i, agent in enumerate(candidates, 1):
        print(f"    [{i}] {agent['displayName']}  (type: {agent.get('type', '?')}, id: {agent['id']})")
    print(f"    [0] Skip — don't assign a Data Agent for {role}")

    while True:
        try:
            choice = int(input(f"  Choice [1-{len(candidates)}, or 0 to skip]: ").strip())
            if choice == 0:
                return None
            if 1 <= choice <= len(candidates):
                return candidates[choice - 1]
        except (ValueError, EOFError):
            pass
        print("  Invalid selection, try again.")


def main():
    workspace_id = os.getenv("FABRIC_WORKSPACE_ID", "")
    if not workspace_id:
        print("ERROR: FABRIC_WORKSPACE_ID not set in azure_config.env")
        print("  Run 'uv run python populate_fabric_config.py' first.")
        sys.exit(1)

    print("=" * 72)
    print("  Fabric Data Agent Discovery")
    print("=" * 72)
    print(f"\n  Workspace ID: {workspace_id}")

    # 1. List all items
    print("\n[1/3] Listing workspace items...")
    headers = get_fabric_headers()
    items = list_workspace_items(headers, workspace_id)
    print(f"  Found {len(items)} items total")

    # Show item type distribution
    type_counts: dict[str, int] = {}
    for item in items:
        t = item.get("type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print("  Item types:")
    for t, count in sorted(type_counts.items()):
        marker = " ←" if t in DATA_AGENT_TYPES or "agent" in t.lower() else ""
        print(f"    {t:30s} {count}{marker}")

    # 2. Find Data Agents
    print("\n[2/3] Searching for Data Agent artifacts...")
    agents = find_data_agents(items)

    if not agents:
        print("  No Data Agent artifacts found.")
        print("\n  Possible reasons:")
        print("    - Data Agents haven't been created yet in Fabric portal")
        print(f"    - The Data Agent uses an unrecognised item type")
        print("\n  All items in this workspace:")
        for item in items:
            print(f"    {item['displayName']:40s} type={item.get('type', '?'):20s} id={item['id']}")

        print("\n  If you can see your Data Agent above, enter its ID manually.")
        manual_id = input("  Graph Data Agent ID (or Enter to skip): ").strip()
        if manual_id:
            updates = {"GRAPH_DATA_AGENT_ID": manual_id}
            manual_id2 = input("  Telemetry Data Agent ID (or Enter to skip): ").strip()
            if manual_id2:
                updates["TELEMETRY_DATA_AGENT_ID"] = manual_id2
            update_env_file(updates)
            print(f"\n  ✓ Updated {len(updates)} values in azure_config.env")
        return

    print(f"  Found {len(agents)} Data Agent candidate(s):")
    for agent in agents:
        print(f"    - {agent['displayName']}  (type: {agent.get('type', '?')}, id: {agent['id']})")

    # 3. Assign agents to roles
    print("\n[3/3] Assigning Data Agents to roles...")

    graph_agent = select_agent(
        agents,
        "GraphExplorerAgent (ontology / Lakehouse)",
    )

    telemetry_agent = select_agent(
        agents,
        "TelemetryAgent (Eventhouse / telemetry)",
        exclude_id=graph_agent["id"] if graph_agent else None,
    )

    # 4. Update config
    updates = {}
    if graph_agent:
        updates["GRAPH_DATA_AGENT_ID"] = graph_agent["id"]
        print(f"\n  ✓ GRAPH_DATA_AGENT_ID = {graph_agent['id']}  ({graph_agent['displayName']})")
    if telemetry_agent:
        updates["TELEMETRY_DATA_AGENT_ID"] = telemetry_agent["id"]
        print(f"  ✓ TELEMETRY_DATA_AGENT_ID = {telemetry_agent['id']}  ({telemetry_agent['displayName']})")

    # Preserve legacy FABRIC_DATA_AGENT_ID for backwards compat
    if graph_agent and not telemetry_agent:
        updates["FABRIC_DATA_AGENT_ID"] = graph_agent["id"]
    elif telemetry_agent and not graph_agent:
        updates["FABRIC_DATA_AGENT_ID"] = telemetry_agent["id"]

    if updates:
        update_env_file(updates)
        print(f"\n  ✓ Updated {len(updates)} values in azure_config.env")
    else:
        print("\n  No agents selected — nothing to update.")

    print()


if __name__ == "__main__":
    main()
