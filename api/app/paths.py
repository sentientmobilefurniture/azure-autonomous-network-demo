"""
Centralized path and config constants.

All files that need PROJECT_ROOT, CONFIG_FILE, AGENT_IDS_FILE etc.
should import from here instead of computing them independently.
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
AGENT_IDS_FILE = Path(
    os.getenv("AGENT_IDS_PATH", str(PROJECT_ROOT / "scripts" / "agent_ids.json"))
)

# Load config once at import time
load_dotenv(CONFIG_FILE)
