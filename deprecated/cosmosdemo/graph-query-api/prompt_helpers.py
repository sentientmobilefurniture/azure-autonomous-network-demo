"""
Shared prompt version-query helper.

Extracts the "query max version and increment" pattern used by both
router_prompts.py (create_prompt) and router_ingest.py (upload_prompts).
"""

from __future__ import annotations


def get_next_version(container, scenario: str, agent: str, name: str) -> int:
    """Query highest existing version for a prompt and return next version number.

    Works with the Cosmos NoSQL container client (synchronous SDK calls).

    Args:
        container: Cosmos container client
        scenario: Scenario name (partition key context)
        agent: Agent role name
        name: Prompt name

    Returns:
        Next version number (1 if no existing versions found)
    """
    existing = list(container.query_items(
        query=(
            "SELECT c.version FROM c "
            "WHERE c.agent = @a AND c.scenario = @s AND c.name = @n "
            "ORDER BY c.version DESC"
        ),
        parameters=[
            {"name": "@a", "value": agent},
            {"name": "@s", "value": scenario},
            {"name": "@n", "value": name},
        ],
        enable_cross_partition_query=False,
    ))
    return (existing[0]["version"] + 1) if existing else 1
