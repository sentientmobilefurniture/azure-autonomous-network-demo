"""
Create AI Search indexer for troubleshooting runbook markdown files.

Creates: data source → index → skillset (chunk + embed) → indexer

Prerequisites:
  - Azure resources deployed (azd up)
  - Runbook .md files uploaded to blob storage 'runbooks' container
    (done automatically by postprovision hook)
  - azure_config.env populated with resource names

Usage:
  uv run create_runbook_indexer.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _indexer_common import create_search_index  # noqa: E402

if __name__ == "__main__":
    create_search_index(
        index_name=os.getenv("RUNBOOKS_INDEX_NAME", "runbooks-index"),
        container_name=os.getenv("RUNBOOKS_CONTAINER_NAME", "runbooks"),
    )
