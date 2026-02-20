"""
Centralized path and config constants.

All files that need PROJECT_ROOT or CONFIG_FILE should import from here.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project structure
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "azure_config.env"

# Load config once at import time (before reading env vars that may be in the file)
load_dotenv(CONFIG_FILE)


def _graph_query_base() -> str:
    """Return the base URL for the graph query endpoints.

    After the merge, graph-query-api routes run in-process at the same port.
    Falls back to external URI if GRAPH_QUERY_API_URI is explicitly set.
    """
    return os.getenv("GRAPH_QUERY_API_URI", "http://localhost:8000")
