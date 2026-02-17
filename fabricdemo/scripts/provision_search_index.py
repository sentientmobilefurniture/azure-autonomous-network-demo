#!/usr/bin/env python3
"""
Provision AI Search indexes — data source, index, skillset, indexer pipeline.

Generalized AI Search provisioner that creates the full indexing pipeline:
  blob data source → index (HNSW + vectorizer) → skillset → indexer

For the telco-noc demo, creates:
  - runbooks-index:   blob container 'runbooks',  files from knowledge/runbooks/*.md
  - tickets-index:    blob container 'tickets',    files from knowledge/tickets/*.txt

Usage:
    source azure_config.env
    uv run python scripts/provision_search_index.py

    # Also upload local files to blob storage before indexing
    uv run python scripts/provision_search_index.py --upload-files

Requires: azure-search-documents, azure-storage-blob, azure-identity
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient
from azure.search.documents.indexes.models import (
    # Index
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SearchableField,
    SimpleField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
    # Data source
    SearchIndexerDataSourceConnection,
    SearchIndexerDataContainer,
    # Skillset
    SearchIndexerSkillset,
    SplitSkill,
    AzureOpenAIEmbeddingSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjections,
    # Indexer
    SearchIndexer,
    IndexingParameters,
    IndexingParametersConfiguration,
    FieldMapping,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "scenarios" / "telco-noc" / "data" / "knowledge"

# From azure_config.env
SEARCH_SERVICE_NAME = os.environ.get("AI_SEARCH_NAME", "")
STORAGE_ACCOUNT_NAME = os.environ.get("STORAGE_ACCOUNT_NAME", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1536"))
AI_FOUNDRY_NAME = os.environ.get("AI_FOUNDRY_NAME", "")
AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
AZURE_RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "")

# Index definitions: name → config
INDEX_CONFIGS = {
    "runbooks-index": {
        "blob_container": "runbooks",
        "local_dir": KNOWLEDGE_DIR / "runbooks",
        "file_glob": "*.md",
        "description": "Operational runbooks for network incident response",
        "semantic_config_name": "runbooks-semantic",
    },
    "tickets-index": {
        "blob_container": "tickets",
        "local_dir": KNOWLEDGE_DIR / "tickets",
        "file_glob": "*.txt",
        "description": "Historical incident tickets for pattern matching",
        "semantic_config_name": "tickets-semantic",
    },
}

# Chunking parameters
CHUNK_LENGTH = 2000
CHUNK_OVERLAP = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_search_endpoint() -> str:
    return f"https://{SEARCH_SERVICE_NAME}.search.windows.net"


def _get_storage_connection_string_resource_id() -> str:
    """Build ARM resource ID for storage account (used as data source connection)."""
    return (
        f"/subscriptions/{AZURE_SUBSCRIPTION_ID}"
        f"/resourceGroups/{AZURE_RESOURCE_GROUP}"
        f"/providers/Microsoft.Storage"
        f"/storageAccounts/{STORAGE_ACCOUNT_NAME}"
    )


def _get_ai_services_resource_id() -> str:
    """Build ARM resource ID for AI Foundry (used for vectorizer)."""
    return (
        f"/subscriptions/{AZURE_SUBSCRIPTION_ID}"
        f"/resourceGroups/{AZURE_RESOURCE_GROUP}"
        f"/providers/Microsoft.CognitiveServices"
        f"/accounts/{AI_FOUNDRY_NAME}"
    )


def _upload_files_to_blob(credential: DefaultAzureCredential, config: dict, index_name: str) -> int:
    """Upload local files to blob storage container. Returns file count."""
    from azure.storage.blob import BlobServiceClient

    blob_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
    blob_client = BlobServiceClient(blob_url, credential=credential)

    container_name = config["blob_container"]
    local_dir = config["local_dir"]
    file_glob = config["file_glob"]

    # Ensure container exists
    try:
        blob_client.create_container(container_name)
        print(f"    Created blob container: {container_name}")
    except Exception:
        print(f"    Blob container exists: {container_name}")

    # Upload files
    files = list(local_dir.glob(file_glob))
    if not files:
        print(f"    ✗ No files matching {file_glob} in {local_dir}")
        return 0

    container_client = blob_client.get_container_client(container_name)
    uploaded = 0
    for f in files:
        blob_name = f.name
        with open(f, "rb") as data:
            container_client.upload_blob(name=blob_name, data=data, overwrite=True)
            uploaded += 1
    print(f"    ✓ Uploaded {uploaded} files to '{container_name}' container")
    return uploaded


def _create_data_source(
    indexer_client: SearchIndexerClient,
    index_name: str,
    config: dict,
) -> str:
    """Create or update blob data source connection. Returns data source name."""
    ds_name = f"{index_name}-datasource"
    resource_id = _get_storage_connection_string_resource_id()

    data_source = SearchIndexerDataSourceConnection(
        name=ds_name,
        type="azureblob",
        connection_string=f"ResourceId={resource_id};",
        container=SearchIndexerDataContainer(name=config["blob_container"]),
    )

    indexer_client.create_or_update_data_source_connection(data_source)
    print(f"    ✓ Data source: {ds_name}")
    return ds_name


def _create_index(
    index_client: SearchIndexClient,
    index_name: str,
    config: dict,
) -> None:
    """Create or update search index with vector search and semantic config."""
    fields = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="chunk", type=SearchFieldDataType.String),
        SearchableField(name="title", type=SearchFieldDataType.String, filterable=True),
        SearchField(
            name="text_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="hnsw-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="hnsw-config"),
        ],
        profiles=[
            VectorSearchProfile(
                name="hnsw-profile",
                algorithm_configuration_name="hnsw-config",
                vectorizer_name="openai-vectorizer",
            ),
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="openai-vectorizer",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=f"https://{AI_FOUNDRY_NAME}.openai.azure.com",
                    deployment_name=EMBEDDING_MODEL,
                    model_name=EMBEDDING_MODEL,
                ),
            ),
        ],
    )

    semantic_config = SemanticConfiguration(
        name=config["semantic_config_name"],
        prioritized_fields=SemanticPrioritizedFields(
            content_fields=[SemanticField(field_name="chunk")],
            title_field=SemanticField(field_name="title"),
        ),
    )

    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=SemanticSearch(configurations=[semantic_config]),
    )

    index_client.create_or_update_index(index)
    print(f"    ✓ Index: {index_name}")


def _create_skillset(
    indexer_client: SearchIndexerClient,
    index_name: str,
) -> str:
    """Create or update skillset with SplitSkill + AzureOpenAIEmbeddingSkill."""
    skillset_name = f"{index_name}-skillset"
    ai_resource_id = _get_ai_services_resource_id()

    split_skill = SplitSkill(
        name="split-skill",
        description="Split documents into chunks",
        text_split_mode="pages",
        context="/document",
        maximum_page_length=CHUNK_LENGTH,
        page_overlap_length=CHUNK_OVERLAP,
        inputs=[InputFieldMappingEntry(name="text", source="/document/content")],
        outputs=[OutputFieldMappingEntry(name="textItems", target_name="pages")],
    )

    embedding_skill = AzureOpenAIEmbeddingSkill(
        name="embedding-skill",
        description="Generate embeddings for chunks",
        context="/document/pages/*",
        resource_url=f"https://{AI_FOUNDRY_NAME}.openai.azure.com",
        deployment_name=EMBEDDING_MODEL,
        model_name=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
        inputs=[InputFieldMappingEntry(name="text", source="/document/pages/*")],
        outputs=[OutputFieldMappingEntry(name="embedding", target_name="text_vector")],
    )

    # Index projection: project chunks into the target index
    index_projections = SearchIndexerIndexProjections(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=index_name,
                parent_key_field_name="parent_id",
                source_context="/document/pages/*",
                mappings=[
                    InputFieldMappingEntry(name="chunk", source="/document/pages/*"),
                    InputFieldMappingEntry(name="text_vector", source="/document/pages/*/text_vector"),
                    InputFieldMappingEntry(name="title", source="/document/metadata_storage_name"),
                ],
            ),
        ],
    )

    skillset = SearchIndexerSkillset(
        name=skillset_name,
        description=f"Chunking and embedding for {index_name}",
        skills=[split_skill, embedding_skill],
        cognitive_services_account={"@odata.type": "#Microsoft.Azure.Search.AIServicesByIdentity", "subdomainUrl": f"https://{AI_FOUNDRY_NAME}.cognitiveservices.azure.com", "identity": None},
        index_projections=index_projections,
    )

    indexer_client.create_or_update_skillset(skillset)
    print(f"    ✓ Skillset: {skillset_name}")
    return skillset_name


def _create_indexer(
    indexer_client: SearchIndexerClient,
    index_name: str,
    data_source_name: str,
    skillset_name: str,
) -> str:
    """Create or update indexer and run it."""
    indexer_name = f"{index_name}-indexer"

    indexer = SearchIndexer(
        name=indexer_name,
        description=f"Indexer for {index_name}",
        data_source_name=data_source_name,
        skillset_name=skillset_name,
        target_index_name=index_name,
        parameters=IndexingParameters(
            configuration=IndexingParametersConfiguration(
                parsing_mode="default",
            ),
        ),
        field_mappings=[
            FieldMapping(source_field_name="metadata_storage_path", target_field_name="chunk_id"),
        ],
    )

    indexer_client.create_or_update_indexer(indexer)
    print(f"    ✓ Indexer: {indexer_name}")
    return indexer_name


def _poll_indexer(
    indexer_client: SearchIndexerClient,
    indexer_name: str,
    timeout_seconds: int = 300,
) -> bool:
    """Poll indexer status until complete or timeout. Returns True if successful."""
    print(f"    Polling indexer '{indexer_name}'...")

    # Reset / run the indexer
    try:
        indexer_client.run_indexer(indexer_name)
    except Exception as e:
        print(f"    ⚠ Could not start indexer: {e}")

    start = time.time()
    while time.time() - start < timeout_seconds:
        time.sleep(5)
        try:
            status = indexer_client.get_indexer_status(indexer_name)
            last_result = status.last_result
            if last_result is None:
                print("    ... waiting for first run...")
                continue

            exec_status = last_result.status
            if exec_status == "success":
                doc_count = last_result.item_count or 0
                print(f"    ✓ Indexer complete: {doc_count} documents indexed")
                return True
            elif exec_status == "transientFailure":
                print(f"    ⚠ Transient failure, retrying...")
                continue
            elif exec_status == "persistentFailure":
                error_msg = last_result.errors[0].message if last_result.errors else "unknown"
                print(f"    ✗ Persistent failure: {error_msg[:200]}")
                return False
            else:
                print(f"    ... status: {exec_status}")
        except Exception as e:
            print(f"    ⚠ Status check error: {e}")

    print(f"    ✗ Timeout after {timeout_seconds}s")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> None:
    print("=" * 72)
    print("  AI Search — Index Provisioner")
    print("=" * 72)

    # Validate config
    missing = []
    if not SEARCH_SERVICE_NAME:
        missing.append("AI_SEARCH_NAME")
    if not STORAGE_ACCOUNT_NAME:
        missing.append("STORAGE_ACCOUNT_NAME")
    if not AI_FOUNDRY_NAME:
        missing.append("AI_FOUNDRY_NAME")
    if not AZURE_SUBSCRIPTION_ID:
        missing.append("AZURE_SUBSCRIPTION_ID")
    if not AZURE_RESOURCE_GROUP:
        missing.append("AZURE_RESOURCE_GROUP")
    if missing:
        print(f"\n  ✗ Missing required env vars: {', '.join(missing)}")
        print("    Set them in azure_config.env or export them before running.")
        sys.exit(1)

    endpoint = _get_search_endpoint()
    print(f"\n  Search endpoint:   {endpoint}")
    print(f"  Storage account:   {STORAGE_ACCOUNT_NAME}")
    print(f"  Embedding model:   {EMBEDDING_MODEL} ({EMBEDDING_DIMENSIONS}d)")
    print(f"  AI Foundry:        {AI_FOUNDRY_NAME}")
    print(f"  Indexes to create: {', '.join(INDEX_CONFIGS.keys())}")

    credential = DefaultAzureCredential()

    index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
    indexer_client = SearchIndexerClient(endpoint=endpoint, credential=credential)

    total_indexes = len(INDEX_CONFIGS)
    success_count = 0

    for idx, (index_name, config) in enumerate(INDEX_CONFIGS.items(), 1):
        print(f"\n[{idx}/{total_indexes}] {index_name}")
        print(f"  {'-' * 50}")

        try:
            # Optional: upload files to blob storage
            if args.upload_files:
                print("  Uploading files to blob storage...")
                _upload_files_to_blob(credential, config, index_name)

            # Create data source
            print("  Creating data source...")
            ds_name = _create_data_source(indexer_client, index_name, config)

            # Create index
            print("  Creating index...")
            _create_index(index_client, index_name, config)

            # Create skillset
            print("  Creating skillset...")
            skillset_name = _create_skillset(indexer_client, index_name)

            # Create indexer
            print("  Creating indexer...")
            indexer_name = _create_indexer(indexer_client, index_name, ds_name, skillset_name)

            # Poll for completion
            if _poll_indexer(indexer_client, indexer_name):
                success_count += 1
            else:
                print(f"  ⚠ Index '{index_name}' created but indexer did not complete successfully")
                success_count += 1  # Index exists, just indexer hasn't finished

        except Exception as e:
            print(f"  ✗ Failed to create {index_name}: {e}")

    # Summary
    print(f"\n{'=' * 72}")
    if success_count == total_indexes:
        print(f"  ✅ All {total_indexes} indexes created successfully")
    else:
        print(f"  ⚠ {success_count}/{total_indexes} indexes created")
    print("=" * 72)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Create AI Search indexes with vector search and semantic ranking",
    )
    parser.add_argument(
        "--upload-files",
        action="store_true",
        help="Upload local files to blob containers before creating indexes",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
