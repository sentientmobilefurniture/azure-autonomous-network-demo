"""
Blob Storage upload service — upload files to Azure Blob Storage.

Extracted from router_ingest.py to decouple blob operations from ingest routing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

from config import get_credential

logger = logging.getLogger("graph-query-api.blob")


def upload_files_to_blob(
    container_name: str,
    files: list[Path],
    *,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Upload files to Azure Blob Storage (synchronous).

    Creates the blob container if it doesn't exist. Uploads each file,
    overwriting existing blobs.

    Args:
        container_name: Target blob container name (e.g. 'runbooks')
        files: List of local file paths to upload
        on_progress: Optional callback(message) for progress updates

    Returns:
        Blob container URL (e.g. 'https://<account>.blob.core.windows.net/<container>')

    Raises:
        RuntimeError: If STORAGE_ACCOUNT_NAME env var is not set
    """
    storage_account = os.getenv("STORAGE_ACCOUNT_NAME", "")
    if not storage_account:
        raise RuntimeError("STORAGE_ACCOUNT_NAME not configured")

    def emit(msg: str) -> None:
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    from azure.storage.blob import BlobServiceClient

    account_url = f"https://{storage_account}.blob.core.windows.net"
    blob_svc = BlobServiceClient(account_url, credential=get_credential())

    # Create container if needed
    try:
        blob_svc.create_container(container_name)
        emit(f"Created blob container '{container_name}'")
    except Exception:
        logger.debug("Blob container '%s' may already exist", container_name)

    # Upload files
    for f in files:
        bc = blob_svc.get_blob_client(container_name, f.name)
        with open(f, "rb") as fh:
            bc.upload_blob(fh, overwrite=True)
    emit(f"Uploaded {len(files)} files to blob '{container_name}'")

    return f"{account_url}/{container_name}"
