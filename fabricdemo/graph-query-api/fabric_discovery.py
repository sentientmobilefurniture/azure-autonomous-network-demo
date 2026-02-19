"""
Runtime Fabric resource discovery.

Queries the Fabric REST API to discover workspace items (Graph Model,
Eventhouse, KQL Database) by convention name, replacing the fragile
env var injection pipeline (azure_config.env → preprovision → Bicep).

The container app only needs FABRIC_WORKSPACE_ID to bootstrap.
Everything else is discovered at runtime via the managed identity.

Results are cached with a configurable TTL (default 10 minutes).
Env var overrides are still honoured — if FABRIC_GRAPH_MODEL_ID etc.
are set, they take precedence over discovery.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger("graph-query-api.fabric-discovery")

# ---------------------------------------------------------------------------
# Convention names — must match what provisioning scripts create
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    """Return env var value or raise with a clear message."""
    val = os.getenv(name)
    if not val:
        raise EnvironmentError(
            f"{name} is not set. Set it in azure_config.env before running."
        )
    return val

ONTOLOGY_NAME_PREFIX = _require_env("FABRIC_ONTOLOGY_NAME")
EVENTHOUSE_NAME_PREFIX = _require_env("FABRIC_EVENTHOUSE_NAME")

# ---------------------------------------------------------------------------
# Fabric API constants — imported from adapters.fabric_config (single source of truth)
# ---------------------------------------------------------------------------

from adapters.fabric_config import FABRIC_API_URL, FABRIC_SCOPE

# ---------------------------------------------------------------------------
# TTL-based cache (thread-safe)
# ---------------------------------------------------------------------------

_CACHE_TTL = float(os.getenv("FABRIC_DISCOVERY_TTL", "600"))  # 10 min default

_cache_lock = threading.Lock()
_discovery_in_progress = False


@dataclass
class FabricConfig:
    """Discovered Fabric resource configuration."""
    workspace_id: str = ""
    graph_model_id: str = ""
    eventhouse_query_uri: str = ""
    kql_db_name: str = ""
    source: str = "unknown"  # "env-vars", "discovery", or "partial"
    workspace_items: list[dict] | None = None  # raw items from Fabric API


_cached_config: FabricConfig | None = None
_cached_at: float = 0.0


# ---------------------------------------------------------------------------
# Credential management — uses shared credential from config module
# ---------------------------------------------------------------------------

def _get_credential():
    from config import get_credential
    return get_credential()


def _get_fabric_token() -> str:
    """Acquire a Fabric API bearer token."""
    cred = _get_credential()
    token = cred.get_token(FABRIC_SCOPE)
    return token.token


# ---------------------------------------------------------------------------
# Fabric API helpers
# ---------------------------------------------------------------------------

def _list_workspace_items(workspace_id: str, token: str) -> list[dict]:
    """List all items in a Fabric workspace."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(
        f"{FABRIC_API_URL}/workspaces/{workspace_id}/items",
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def _get_kql_db_details(workspace_id: str, db_id: str, token: str) -> dict:
    """Get KQL database details including queryServiceUri."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(
        f"{FABRIC_API_URL}/workspaces/{workspace_id}/kqlDatabases/{db_id}",
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Discovery logic
# ---------------------------------------------------------------------------

def _discover_fabric_config(workspace_id: str) -> FabricConfig:
    """Discover Fabric resource IDs by convention name within a workspace.

    Finds:
    - GraphModel whose name contains ONTOLOGY_NAME_PREFIX → graph_model_id
    - KQLDatabase whose parent Eventhouse name contains EVENTHOUSE_NAME_PREFIX
      → eventhouse_query_uri, kql_db_name
    """
    logger.info("Discovering Fabric resources in workspace %s ...", workspace_id)

    try:
        token = _get_fabric_token()
        items = _list_workspace_items(workspace_id, token)
    except Exception as e:
        logger.error("Failed to list workspace items: %s", e)
        return FabricConfig(workspace_id=workspace_id, source="discovery-failed")

    config = FabricConfig(workspace_id=workspace_id, source="discovery")

    # Store raw workspace items for the API to surface
    config.workspace_items = [
        {"id": i.get("id", ""), "type": i.get("type", ""), "displayName": i.get("displayName", "")}
        for i in items
    ]

    # --- Find Graph Model ---
    graph_models = [i for i in items if i.get("type") == "GraphModel"]
    for gm in graph_models:
        if ONTOLOGY_NAME_PREFIX.lower() in gm["displayName"].lower():
            config.graph_model_id = gm["id"]
            logger.info(
                "  ✓ graph_model_id = %s  (%s)",
                gm["id"], gm["displayName"],
            )
            break
    if not config.graph_model_id:
        # Fall back to first GraphModel if only one exists
        if len(graph_models) == 1:
            config.graph_model_id = graph_models[0]["id"]
            logger.info(
                "  ✓ graph_model_id = %s  (only GraphModel: %s)",
                graph_models[0]["id"], graph_models[0]["displayName"],
            )
        else:
            logger.warning(
                "  ✗ No GraphModel matching '%s' found (%d total)",
                ONTOLOGY_NAME_PREFIX, len(graph_models),
            )

    # --- Find KQL Database → query URI + DB name ---
    kql_dbs = [i for i in items if i.get("type") == "KQLDatabase"]
    # Prefer a KQL DB whose Eventhouse parent matches our convention name
    target_db = None
    eventhouses = {i["id"]: i for i in items if i.get("type") == "Eventhouse"}

    for db in kql_dbs:
        # Try to match by eventhouse name or DB name
        db_name = db["displayName"]
        if EVENTHOUSE_NAME_PREFIX.lower() in db_name.lower():
            target_db = db
            break

    if not target_db and len(kql_dbs) == 1:
        target_db = kql_dbs[0]
        logger.info("  Using only KQL database: %s", target_db["displayName"])

    if target_db:
        try:
            details = _get_kql_db_details(workspace_id, target_db["id"], token)
            props = details.get("properties", {})
            config.eventhouse_query_uri = props.get("queryServiceUri", "")
            config.kql_db_name = props.get("databaseName", target_db["displayName"])
            logger.info(
                "  ✓ kql_db_name = %s", config.kql_db_name,
            )
            logger.info(
                "  ✓ eventhouse_query_uri = %s", config.eventhouse_query_uri,
            )
        except Exception as e:
            logger.error("  ✗ Failed to get KQL DB details: %s", e)
    else:
        logger.warning(
            "  ✗ No KQL database matching '%s' found (%d total)",
            EVENTHOUSE_NAME_PREFIX, len(kql_dbs),
        )

    return config


# ---------------------------------------------------------------------------
# Public API — get_fabric_config()
# ---------------------------------------------------------------------------

def get_fabric_config() -> FabricConfig:
    """Return the current Fabric config, discovering if needed.

    Priority:
    1. If all 3 env vars are set → use them directly (no API calls)
    2. Otherwise → discover from Fabric API, cache with TTL
    3. Env var overrides always win over discovered values
    """
    global _cached_config, _cached_at

    # --- Check env var overrides first ---
    env_workspace = os.getenv("FABRIC_WORKSPACE_ID", "")
    env_graph_model = os.getenv("FABRIC_GRAPH_MODEL_ID", "")
    env_query_uri = os.getenv("EVENTHOUSE_QUERY_URI", "")
    env_kql_db = os.getenv("FABRIC_KQL_DB_NAME", "")

    # If all values are provided via env vars, skip discovery entirely
    if env_workspace and env_graph_model and env_query_uri and env_kql_db:
        return FabricConfig(
            workspace_id=env_workspace,
            graph_model_id=env_graph_model,
            eventhouse_query_uri=env_query_uri,
            kql_db_name=env_kql_db,
            source="env-vars",
        )

    # Need workspace ID to discover anything
    if not env_workspace:
        logger.warning("FABRIC_WORKSPACE_ID not set — cannot discover Fabric resources")
        return FabricConfig(source="not-configured")

    # --- Check cache ---
    with _cache_lock:
        if _cached_config is not None and (time.time() - _cached_at) < _CACHE_TTL:
            return _cached_config
        # Check if another thread is already discovering
        global _discovery_in_progress
        if _discovery_in_progress:
            # Another thread is discovering; return stale cache if available
            if _cached_config is not None:
                return _cached_config
        _discovery_in_progress = True

    # --- Discover (outside lock, but guarded by _discovery_in_progress) ---
    try:
        discovered = _discover_fabric_config(env_workspace)

        # Apply env var overrides on top of discovered values
        if env_graph_model:
            discovered.graph_model_id = env_graph_model
            discovered.source = "partial"
        if env_query_uri:
            discovered.eventhouse_query_uri = env_query_uri
            discovered.source = "partial"
        if env_kql_db:
            discovered.kql_db_name = env_kql_db
            discovered.source = "partial"

        # Cache the result
        with _cache_lock:
            _cached_config = discovered
            _cached_at = time.time()
    finally:
        with _cache_lock:
            _discovery_in_progress = False

    return discovered


def invalidate_cache() -> None:
    """Force re-discovery on next call to get_fabric_config()."""
    global _cached_config, _cached_at
    with _cache_lock:
        _cached_config = None
        _cached_at = 0.0


def is_fabric_ready() -> bool:
    """Check whether Fabric graph queries are possible."""
    cfg = get_fabric_config()
    return bool(cfg.workspace_id and cfg.graph_model_id)


def is_kql_ready() -> bool:
    """Check whether KQL telemetry queries are possible."""
    cfg = get_fabric_config()
    return bool(cfg.eventhouse_query_uri and cfg.kql_db_name)
