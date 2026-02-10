"""
Provision Fabric Eventhouse — create tables and ingest CSV data.

Automates:
  1. Create Eventhouse (NetworkTelemetryEH_3117) if not exists
  2. Discover the default KQL database and query URI
  3. Create KQL tables (AlertStream, LinkTelemetry)
  4. Ingest CSV data via queued ingestion (azure-kusto-ingest)

Prerequisites:
  - provision_lakehouse.py has run (workspace exists)
  - azure_config.env populated with FABRIC_WORKSPACE_ID, FABRIC_CAPACITY_ID
  - Data files exist in data/eventhouse/

Usage:
  uv run provision_eventhouse.py
"""

import os
import re
import sys
import time

import requests
from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.ingest import QueuedIngestClient, IngestionProperties
from azure.kusto.data.data_format import DataFormat
from dotenv import load_dotenv

load_dotenv("azure_config.env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FABRIC_API = "https://api.fabric.microsoft.com/v1"

WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "AutonomousNetworkDemo")
CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID", "")
EVENTHOUSE_NAME = os.getenv("FABRIC_EVENTHOUSE_NAME", "NetworkTelemetryEH_3117")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "eventhouse")

# Table schemas — column name → KQL type
TABLE_SCHEMAS = {
    "AlertStream": {
        "AlertId": "string",
        "Timestamp": "datetime",
        "SourceNodeId": "string",
        "SourceNodeType": "string",
        "AlertType": "string",
        "Severity": "string",
        "Description": "string",
        "OpticalPowerDbm": "real",
        "BitErrorRate": "real",
        "CPUUtilPct": "real",
        "PacketLossPct": "real",
    },
    "LinkTelemetry": {
        "LinkId": "string",
        "Timestamp": "datetime",
        "UtilizationPct": "real",
        "OpticalPowerDbm": "real",
        "BitErrorRate": "real",
        "LatencyMs": "real",
    },
}


# ---------------------------------------------------------------------------
# Fabric REST API client (subset needed for Eventhouse)
# ---------------------------------------------------------------------------

class FabricClient:
    """Thin wrapper around the Fabric REST API for Eventhouse operations."""

    def __init__(self):
        self.credential = DefaultAzureCredential()

    def _get_token(self) -> str:
        return self.credential.get_token(
            "https://api.fabric.microsoft.com/.default"
        ).token

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _wait_for_lro(
        self, response: requests.Response, label: str, timeout: int = 300
    ):
        """Wait for a Fabric long-running operation to complete."""
        if response.status_code == 201:
            return response.json()

        if response.status_code not in (200, 202):
            print(f"  ✗ {label} failed: {response.status_code} — {response.text}")
            sys.exit(1)

        if response.status_code == 200:
            return response.json()

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
                result_url = f"{url}/result"
                rr = requests.get(result_url, headers=self.headers)
                return rr.json() if rr.status_code == 200 else r.json()
            if status in ("Failed", "Cancelled"):
                print(f"  ✗ {label} {status}: {r.json()}")
                sys.exit(1)

        print(f"  ✗ {label} timed out after {timeout}s")
        sys.exit(1)

    def find_eventhouse(self, workspace_id: str, name: str) -> dict | None:
        r = requests.get(
            f"{FABRIC_API}/workspaces/{workspace_id}/eventhouses",
            headers=self.headers,
        )
        r.raise_for_status()
        for item in r.json().get("value", []):
            if item["displayName"] == name:
                return item
        return None

    def create_eventhouse(self, workspace_id: str, name: str) -> dict:
        body = {
            "displayName": name,
            "description": f"Eventhouse for {WORKSPACE_NAME}",
        }
        r = requests.post(
            f"{FABRIC_API}/workspaces/{workspace_id}/eventhouses",
            headers=self.headers,
            json=body,
        )
        return self._wait_for_lro(r, f"Create Eventhouse '{name}'")

    def find_kql_database(
        self, workspace_id: str, eventhouse_id: str
    ) -> dict | None:
        """Find the default KQL database created with the Eventhouse."""
        r = requests.get(
            f"{FABRIC_API}/workspaces/{workspace_id}/kqlDatabases",
            headers=self.headers,
        )
        r.raise_for_status()
        for db in r.json().get("value", []):
            props = db.get("properties", {})
            if props.get("parentEventhouseItemId") == eventhouse_id:
                return db
        dbs = r.json().get("value", [])
        return dbs[0] if dbs else None


# ---------------------------------------------------------------------------
# KQL table creation via management commands
# ---------------------------------------------------------------------------

def create_kql_tables(kusto_client: KustoClient, db_name: str):
    """Create tables in KQL database if they don't exist."""
    for table_name, schema in TABLE_SCHEMAS.items():
        columns = ", ".join(f"['{col}']: {dtype}" for col, dtype in schema.items())
        cmd = f".create-merge table {table_name} ({columns})"

        print(f"  Creating table: {table_name} ...", end=" ")
        try:
            kusto_client.execute_mgmt(db_name, cmd)
            print("✓")
        except Exception as e:
            print(f"✗ {e}")
            sys.exit(1)

    # Enable CSV ingestion mapping for each table
    for table_name, schema in TABLE_SCHEMAS.items():
        cols = list(schema.keys())
        mapping_name = f"{table_name}_csv_mapping"
        mapping_json = ", ".join(
            f'{{"Name": "{col}", "DataType": "{dtype}", "Ordinal": {i}}}'
            for i, (col, dtype) in enumerate(schema.items())
        )
        cmd = (
            f'.create-or-alter table {table_name} ingestion csv mapping '
            f"'{mapping_name}' '[{mapping_json}]'"
        )
        print(f"  CSV mapping: {mapping_name} ...", end=" ")
        try:
            kusto_client.execute_mgmt(db_name, cmd)
            print("✓")
        except Exception as e:
            print(f"✗ {e}")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Data ingestion via Kusto SDK queued ingestion
# ---------------------------------------------------------------------------

def ingest_csv_files(
    query_uri: str,
    db_name: str,
):
    """Ingest CSV files into KQL tables using queued ingestion."""
    # Queued ingestion uses the ingest- prefixed URI.
    # For Fabric Eventhouses the query URI is typically:
    #   https://<id>.z<n>.kusto.fabric.microsoft.com
    # The ingest URI is:
    #   https://ingest-<id>.z<n>.kusto.fabric.microsoft.com
    ingest_uri = query_uri.replace("https://", "https://ingest-")

    credential = DefaultAzureCredential()

    # Build connection for queued ingestion
    kcsb_ingest = KustoConnectionStringBuilder.with_azure_token_credential(
        ingest_uri, credential
    )

    ingest_client = QueuedIngestClient(kcsb_ingest)

    for table_name in TABLE_SCHEMAS:
        csv_path = os.path.join(DATA_DIR, f"{table_name}.csv")
        if not os.path.exists(csv_path):
            print(f"  ⚠ Skipping {table_name}.csv — file not found")
            continue

        mapping_name = f"{table_name}_csv_mapping"
        props = IngestionProperties(
            database=db_name,
            table=table_name,
            data_format=DataFormat.CSV,
            ingestion_mapping_reference=mapping_name,
            ignore_first_record=True,
        )

        print(f"  Ingesting {table_name}.csv ...", end=" ", flush=True)
        try:
            ingest_client.ingest_from_file(csv_path, ingestion_properties=props)
            print("✓ (queued)")
        except Exception as e:
            # Queued ingestion may not be available on all Fabric SKUs.
            # Fall back to streaming ingestion via management command.
            print(f"⚠ queued ingestion failed: {e}")
            print(f"    Falling back to streaming ingestion...")
            if not _streaming_ingest_fallback(query_uri, db_name, table_name, csv_path):
                sys.exit(1)


def _streaming_ingest_fallback(
    query_uri: str, db_name: str, table_name: str, csv_path: str
) -> bool:
    """Fallback: use .ingest inline for small files via management command."""
    credential = DefaultAzureCredential()
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
        query_uri, credential
    )
    client = KustoClient(kcsb)

    # Read CSV data (skip header)
    with open(csv_path) as f:
        lines = f.readlines()

    if len(lines) < 2:
        print(f"    ⚠ {table_name}.csv is empty")
        return True

    header = lines[0].strip()
    data_lines = [line.strip() for line in lines[1:] if line.strip()]

    # .ingest inline has a ~1MB limit, batch if needed
    batch_size = 500
    total = len(data_lines)

    for start in range(0, total, batch_size):
        batch = data_lines[start : start + batch_size]
        inline_data = "\n".join(batch)
        cmd = f".ingest inline into table {table_name} <|\n{inline_data}"

        try:
            client.execute_mgmt(db_name, cmd)
            end = min(start + batch_size, total)
            print(f"    ✓ Ingested rows {start + 1}–{end} of {total}")
        except Exception as e:
            print(f"    ✗ Inline ingest failed at row {start + 1}: {e}")
            return False

    return True


# ---------------------------------------------------------------------------
# Env file updater
# ---------------------------------------------------------------------------

def update_env_file(updates: dict[str, str]):
    """Update azure_config.env with key=value pairs."""
    env_file = os.path.join(os.path.dirname(__file__), "azure_config.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            content = f.read()
    else:
        content = ""

    for key, value in updates.items():
        pattern = rf"^{re.escape(key)}=.*$"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
        else:
            content = content.rstrip("\n") + f"\n{key}={value}\n"

    with open(env_file, "w") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not WORKSPACE_ID:
        print("✗ FABRIC_WORKSPACE_ID not set. Run provision_lakehouse.py first.")
        sys.exit(1)

    client = FabricClient()

    # ------------------------------------------------------------------
    # 1. Create Eventhouse
    # ------------------------------------------------------------------
    print("=" * 60)
    print(f"Provisioning Eventhouse: {EVENTHOUSE_NAME}")
    print("=" * 60)

    eh = client.find_eventhouse(WORKSPACE_ID, EVENTHOUSE_NAME)
    if eh:
        print(f"  ✓ Eventhouse already exists: {eh['id']}")
    else:
        eh = client.create_eventhouse(WORKSPACE_ID, EVENTHOUSE_NAME)
        print(f"  ✓ Eventhouse created: {eh['id']}")

    eventhouse_id = eh["id"]

    # ------------------------------------------------------------------
    # 2. Discover KQL database and query URI
    # ------------------------------------------------------------------
    print(f"\n--- KQL Database ---")

    kql_db = client.find_kql_database(WORKSPACE_ID, eventhouse_id)
    if not kql_db:
        print("  ✗ No KQL database found — Eventhouse may still be provisioning")
        print("    Wait a minute and re-run.")
        sys.exit(1)

    db_name = kql_db["displayName"]
    db_id = kql_db["id"]
    query_uri = kql_db.get("properties", {}).get("queryServiceUri", "")

    print(f"  ✓ Database: {db_name} ({db_id})")
    print(f"  ✓ Query URI: {query_uri}")

    if not query_uri:
        print("  ✗ Query URI not available — Eventhouse may still be starting up")
        print("    Wait a minute and re-run.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 3. Enable Python 3.11.7 plugin (manual step)
    # ------------------------------------------------------------------
    print(f"\n--- Python Plugin Check ---")
    print("  ⚠  The Python 3.11.7 language extension must be enabled on the")
    print("     Eventhouse before the anomaly detector will work.")
    print()
    print("  To enable it:")
    print("    1. Open Fabric portal → Workspace → select the Eventhouse")
    print("    2. Click 'Eventhouse' in the ribbon → 'Plugins'")
    print("    3. Toggle 'Python language extension' to ON")
    print("    4. Select Python 3.11.7 image → click 'Done'")
    print()
    print("  Note: Enabling the plugin may take a few minutes and consumes")
    print("        additional compute resources.")
    print()
    confirm = input("  Have you enabled the Python 3.11.7 plugin? [y/N/skip]: ").strip().lower()
    if confirm == "skip":
        print("  ⚠ Skipping — anomaly detector queries will fail until enabled.")
    elif confirm not in ("y", "yes"):
        print("  ✗ Please enable the plugin and re-run this script.")
        sys.exit(1)
    else:
        print("  ✓ Python plugin confirmed.")

    # ------------------------------------------------------------------
    # 4. Create KQL tables
    # ------------------------------------------------------------------
    print(f"\n--- Creating KQL tables ---")

    credential = DefaultAzureCredential()
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
        query_uri, credential
    )
    kusto_client = KustoClient(kcsb)

    create_kql_tables(kusto_client, db_name)

    # ------------------------------------------------------------------
    # 5. Ingest CSV data
    # ------------------------------------------------------------------
    print(f"\n--- Ingesting CSV data ---")

    ingest_csv_files(query_uri, db_name)

    # ------------------------------------------------------------------
    # 6. Verify row counts
    # ------------------------------------------------------------------
    print(f"\n--- Verifying ingestion ---")

    # Give queued ingestion a moment to process
    print("  Waiting 15s for queued ingestion to process...")
    time.sleep(15)

    for table_name in TABLE_SCHEMAS:
        try:
            result = kusto_client.execute_query(db_name, f"{table_name} | count")
            for row in result.primary_results[0]:
                count = row[0]
                print(f"  ✓ {table_name}: {count} rows")
        except Exception as e:
            print(f"  ⚠ {table_name}: could not verify — {e}")

    # ------------------------------------------------------------------
    # 7. Update azure_config.env
    # ------------------------------------------------------------------
    env_updates = {
        "FABRIC_EVENTHOUSE_ID": eventhouse_id,
        "FABRIC_KQL_DB_ID": db_id,
        "FABRIC_KQL_DB_NAME": db_name,
        "EVENTHOUSE_QUERY_URI": query_uri,
    }
    update_env_file(env_updates)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("✅ Eventhouse provisioning complete!")
    print(f"   Eventhouse : {EVENTHOUSE_NAME} ({eventhouse_id})")
    print(f"   KQL DB     : {db_name} ({db_id})")
    print(f"   Query URI  : {query_uri}")
    print(f"   Tables     : {', '.join(TABLE_SCHEMAS.keys())}")
    print("=" * 60)

    print("\n  ✓ Updated azure_config.env")
    for key, value in env_updates.items():
        print(f"    {key}={value}")
    print()


if __name__ == "__main__":
    main()
