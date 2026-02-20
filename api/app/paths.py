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
