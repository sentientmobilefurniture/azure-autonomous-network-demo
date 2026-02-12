"""
Create AI Search indexer for historical incident ticket .txt files.

Creates: data source → index → skillset (chunk + embed) → indexer

Prerequisites:
  - Azure resources deployed (azd up)
  - Ticket .txt files uploaded to blob storage 'tickets' container
    (done automatically by postprovision hook)
  - azure_config.env populated with resource names

Usage:
  uv run create_tickets_indexer.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _indexer_common import create_search_index  # noqa: E402

if __name__ == "__main__":
    create_search_index(
        index_name=os.getenv("TICKETS_INDEX_NAME", "tickets-index"),
        container_name=os.getenv("TICKETS_CONTAINER_NAME", "tickets"),
    )
