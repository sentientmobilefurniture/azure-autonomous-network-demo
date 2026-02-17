"""
Provision Fabric Workspace with Lakehouse, upload data.

Automates Step 1.4 from the implementation plan:
  1. Create Fabric workspace and attach capacity
  2. Create Lakehouse (NetworkTopologyLH)
  3. Upload CSVs to Lakehouse Files via OneLake
  4. Load each CSV into a managed delta table via Lakehouse Tables API

For Eventhouse provisioning, see provision_eventhouse.py.

Prerequisites:
  - Fabric capacity deployed (Step 1.3 via azd up)
  - Tenant settings enabled (Step 1.1)
  - Data files generated (Step 1.2)
  - azure_config.env populated

Usage:
  uv run provision_lakehouse.py
"""

import os
import re
import sys
import time

import requests
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

from _config import (
    FABRIC_API, PROJECT_ROOT, DATA_DIR,
    WORKSPACE_NAME, CAPACITY_ID, LAKEHOUSE_NAME,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ONELAKE_ACCOUNT = "onelake"
ONELAKE_URL = f"https://{ONELAKE_ACCOUNT}.dfs.fabric.microsoft.com"

SCENARIO = os.environ.get("DEFAULT_SCENARIO", "telco-noc")
LAKEHOUSE_CSV_DIR = str(DATA_DIR / "scenarios" / SCENARIO / "data" / "entities")

# CSV files to upload to Lakehouse → load as delta tables
LAKEHOUSE_TABLES = [
    "DimCoreRouter",
    "DimTransportLink",
    "DimAggSwitch",
    "DimBaseStation",
    "DimBGPSession",
    "DimMPLSPath",
    "DimService",
    "DimSLAPolicy",
    "FactMPLSPathHops",
    "FactServiceDependency",
]


class FabricClient:
    """Thin wrapper around the Fabric REST API."""

    def __init__(self):
        self.credential = DefaultAzureCredential()
        self._token = None

    def _get_token(self) -> str:
        token = self.credential.get_token("https://api.fabric.microsoft.com/.default")
        return token.token

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _wait_for_lro(self, response: requests.Response, label: str, timeout: int = 300):
        """Wait for a Fabric long-running operation to complete."""
        if response.status_code == 201:
            return response.json()

        if response.status_code != 202:
            print(f"  ✗ {label} failed: {response.status_code} — {response.text}")
            sys.exit(1)

        operation_id = response.headers.get("x-ms-operation-id")
        if not operation_id:
            print(f"  ✗ {label}: no operation ID in 202 response")
            sys.exit(1)

        url = f"{FABRIC_API}/operations/{operation_id}"
        retry_after = int(response.headers.get("Retry-After", "5"))

        elapsed = 0
        while elapsed < timeout:
            time.sleep(retry_after)
            elapsed += retry_after
            r = requests.get(url, headers=self.headers)
            if r.status_code != 200:
                continue
            status = r.json().get("status", "")
            if status == "Succeeded":
                # Try to get result
                result_url = f"{url}/result"
                rr = requests.get(result_url, headers=self.headers)
                if rr.status_code == 200:
                    return rr.json()
                return r.json()
            elif status in ("Failed", "Cancelled"):
                print(f"  ✗ {label} {status}: {r.json()}")
                sys.exit(1)

        print(f"  ✗ {label} timed out after {timeout}s")
        sys.exit(1)

    # --- Workspace ---

    def find_workspace(self, name: str) -> dict | None:
        """Find workspace by display name."""
        r = requests.get(
            f"{FABRIC_API}/workspaces",
            headers=self.headers,
            params={"$filter": f"displayName eq '{name}'"},  # OData filter may not work; fallback to list
        )
        if r.status_code != 200:
            # Fallback: list all and filter
            r = requests.get(f"{FABRIC_API}/workspaces", headers=self.headers)
            r.raise_for_status()
        for ws in r.json().get("value", []):
            if ws["displayName"] == name:
                return ws
        return None

    def create_workspace(self, name: str, capacity_id: str = "") -> dict:
        """Create a Fabric workspace, optionally attach to capacity."""
        body = {"displayName": name}
        if capacity_id:
            body["capacityId"] = capacity_id
        r = requests.post(f"{FABRIC_API}/workspaces", headers=self.headers, json=body)
        if r.status_code == 201:
            return r.json()
        r.raise_for_status()
        return r.json()

    def assign_capacity(self, workspace_id: str, capacity_id: str):
        """Assign capacity to an existing workspace."""
        r = requests.post(
            f"{FABRIC_API}/workspaces/{workspace_id}/assignToCapacity",
            headers=self.headers,
            json={"capacityId": capacity_id},
        )
        if r.status_code not in (200, 202):
            print(f"  ⚠ Assign capacity: {r.status_code} — {r.text}")

    # --- Lakehouse ---

    def find_lakehouse(self, workspace_id: str, name: str) -> dict | None:
        r = requests.get(f"{FABRIC_API}/workspaces/{workspace_id}/lakehouses", headers=self.headers)
        r.raise_for_status()
        for item in r.json().get("value", []):
            if item["displayName"] == name:
                return item
        return None

    def create_lakehouse(self, workspace_id: str, name: str) -> dict:
        body = {"displayName": name, "description": f"Lakehouse for {WORKSPACE_NAME}"}
        r = requests.post(
            f"{FABRIC_API}/workspaces/{workspace_id}/lakehouses", headers=self.headers, json=body
        )
        return self._wait_for_lro(r, f"Create Lakehouse '{name}'")

    # --- Lakehouse Table Loading ---

    def load_table(
        self, workspace_id: str, lakehouse_id: str, table_name: str, relative_path: str
    ):
        """Load a CSV from Lakehouse Files/ into a managed delta table."""
        body = {
            "relativePath": relative_path,
            "pathType": "File",
            "mode": "Overwrite",
            "formatOptions": {"format": "Csv", "header": True, "delimiter": ","},
        }
        r = requests.post(
            f"{FABRIC_API}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/tables/{table_name}/load",
            headers=self.headers,
            json=body,
        )
        self._wait_for_lro(r, f"Load table '{table_name}'")


def upload_csvs_to_onelake(
    workspace_name: str, lakehouse_name: str, csv_dir: str, file_names: list[str]
):
    """Upload CSV files to Lakehouse Files/ folder via OneLake ADLS Gen2 API."""
    credential = DefaultAzureCredential()
    service_client = DataLakeServiceClient(ONELAKE_URL, credential=credential)
    fs_client = service_client.get_file_system_client(workspace_name)
    data_path = f"{lakehouse_name}.Lakehouse/Files"

    for name in file_names:
        file_path = os.path.join(csv_dir, f"{name}.csv")
        if not os.path.exists(file_path):
            print(f"  ⚠ Skipping {name}.csv — file not found")
            continue

        remote_path = f"{data_path}/{name}.csv"
        dir_client = fs_client.get_directory_client(data_path)
        file_client = dir_client.get_file_client(f"{name}.csv")

        with open(file_path, "rb") as f:
            file_client.upload_data(f, overwrite=True)
        print(f"  ✓ Uploaded {name}.csv → OneLake Files/")


def main():
    client = FabricClient()

    # ------------------------------------------------------------------
    # 1. Workspace
    # ------------------------------------------------------------------
    print("=" * 60)
    print(f"Provisioning Fabric workspace: {WORKSPACE_NAME}")
    print("=" * 60)

    ws = client.find_workspace(WORKSPACE_NAME)
    if ws:
        print(f"  ✓ Workspace already exists: {ws['id']}")
    else:
        ws = client.create_workspace(WORKSPACE_NAME, CAPACITY_ID)
        print(f"  ✓ Workspace created: {ws['id']}")

    workspace_id = ws["id"]

    if CAPACITY_ID and not ws.get("capacityId"):
        client.assign_capacity(workspace_id, CAPACITY_ID)
        print(f"  ✓ Capacity assigned: {CAPACITY_ID}")

    # ------------------------------------------------------------------
    # 2. Lakehouse
    # ------------------------------------------------------------------
    print(f"\n--- Lakehouse: {LAKEHOUSE_NAME} ---")

    lh = client.find_lakehouse(workspace_id, LAKEHOUSE_NAME)
    if lh:
        print(f"  ✓ Lakehouse already exists: {lh['id']}")
    else:
        lh = client.create_lakehouse(workspace_id, LAKEHOUSE_NAME)
        print(f"  ✓ Lakehouse created: {lh['id']}")

    lakehouse_id = lh["id"]

    # ------------------------------------------------------------------
    # 3. Upload CSVs to Lakehouse Files/
    # ------------------------------------------------------------------
    print(f"\n--- Uploading CSVs to Lakehouse OneLake ---")
    upload_csvs_to_onelake(WORKSPACE_NAME, LAKEHOUSE_NAME, LAKEHOUSE_CSV_DIR, LAKEHOUSE_TABLES)

    # ------------------------------------------------------------------
    # 4. Load each CSV into managed delta table
    # ------------------------------------------------------------------
    print(f"\n--- Loading CSVs into managed delta tables ---")
    for table_name in LAKEHOUSE_TABLES:
        relative_path = f"Files/{table_name}.csv"
        client.load_table(workspace_id, lakehouse_id, table_name, relative_path)
        print(f"  ✓ Loaded table: {table_name}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("=" * 60)
    print("✅ Fabric provisioning complete!")
    print(f"   Workspace : {WORKSPACE_NAME} ({workspace_id})")
    print(f"   Lakehouse : {LAKEHOUSE_NAME} ({lakehouse_id})")
    print("=" * 60)
    print("\n  Next: run 'uv run provision_eventhouse.py' for Eventhouse setup")

    # Save IDs to azure_config.env
    env_file = str(PROJECT_ROOT / "azure_config.env")
    env_additions = {
        "FABRIC_WORKSPACE_ID": workspace_id,
        "FABRIC_LAKEHOUSE_ID": lakehouse_id,
    }

    if os.path.exists(env_file):
        with open(env_file) as f:
            content = f.read()
    else:
        content = ""

    for key, value in env_additions.items():
        pattern = rf"^{re.escape(key)}=.*$"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
        else:
            content = content.rstrip("\n") + f"\n{key}={value}\n"

    with open(env_file, "w") as f:
        f.write(content)

    print("\n  ✓ Updated azure_config.env:")
    for key, value in env_additions.items():
        print(f"    {key}={value}")


if __name__ == "__main__":
    main()
