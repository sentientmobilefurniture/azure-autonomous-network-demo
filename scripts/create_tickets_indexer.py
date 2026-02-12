"""
Create AI Search indexer for historical incident ticket .txt files.

Creates: data source → index → skillset (chunk + embed) → indexer

Mirror of create_indexer.py (runbooks) but targeting the 'tickets' blob
container and 'tickets-index' search index.

Prerequisites:
  - Azure resources deployed (azd up)
  - Ticket .txt files uploaded to blob storage 'tickets' container
    (done automatically by postprovision hook)
  - azure_config.env populated with resource names

Usage:
  uv run create_tickets_indexer.py
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexerClient, SearchIndexClient
from azure.search.documents.indexes.models import (
    # Data source
    SearchIndexerDataContainer,
    SearchIndexerDataSourceConnection,
    # Index
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    # Skillset
    SearchIndexerSkillset,
    SplitSkill,
    AzureOpenAIEmbeddingSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    # Indexer
    SearchIndexer,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "azure_config.env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
credential = DefaultAzureCredential()

SEARCH_ENDPOINT = f"https://{os.getenv('AI_SEARCH_NAME')}.search.windows.net"
OPENAI_ENDPOINT = f"https://{os.getenv('AI_FOUNDRY_NAME')}.openai.azure.com"
STORAGE_CONNECTION = (
    f"ResourceId=/subscriptions/{os.getenv('AZURE_SUBSCRIPTION_ID')}"
    f"/resourceGroups/{os.getenv('AZURE_RESOURCE_GROUP')}"
    f"/providers/Microsoft.Storage/storageAccounts/{os.getenv('STORAGE_ACCOUNT_NAME')}/;"
)

INDEX_NAME = os.getenv("TICKETS_INDEX_NAME", "tickets-index")
CONTAINER_NAME = os.getenv("TICKETS_CONTAINER_NAME", "tickets")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))


def main():
    indexer_client = SearchIndexerClient(SEARCH_ENDPOINT, credential)
    index_client = SearchIndexClient(SEARCH_ENDPOINT, credential)

    # 1. Data source — blob container with ticket .txt files
    data_source = SearchIndexerDataSourceConnection(
        name=f"{INDEX_NAME}-datasource",
        type="azureblob",
        connection_string=STORAGE_CONNECTION,
        container=SearchIndexerDataContainer(name=CONTAINER_NAME),
    )
    indexer_client.create_or_update_data_source_connection(data_source)
    print(f"✓ Data source '{data_source.name}' created")

    # 2. Index with vector field
    fields = [
        SearchField(
            name="chunk_id",
            type=SearchFieldDataType.String,
            key=True,
            analyzer_name="keyword",
        ),
        SearchField(
            name="parent_id",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="chunk",
            type=SearchFieldDataType.String,
            searchable=True,
        ),
        SearchField(
            name="title",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
        ),
        SearchField(
            name="vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="vector-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw",
                vectorizer_name="openai",
            )
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="openai",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=OPENAI_ENDPOINT,
                    deployment_name=EMBEDDING_MODEL,
                    model_name=EMBEDDING_MODEL,
                ),
            )
        ],
    )

    index = SearchIndex(name=INDEX_NAME, fields=fields, vector_search=vector_search)
    index_client.create_or_update_index(index)
    print(f"✓ Index '{index.name}' created")

    # 3. Skillset — chunk ticket content + embed
    split_skill = SplitSkill(
        name="split",
        text_split_mode="pages",
        context="/document",
        maximum_page_length=2000,
        page_overlap_length=500,
        inputs=[InputFieldMappingEntry(name="text", source="/document/content")],
        outputs=[OutputFieldMappingEntry(name="textItems", target_name="pages")],
    )

    embedding_skill = AzureOpenAIEmbeddingSkill(
        name="embed",
        context="/document/pages/*",
        resource_url=OPENAI_ENDPOINT,
        deployment_name=EMBEDDING_MODEL,
        model_name=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
        inputs=[InputFieldMappingEntry(name="text", source="/document/pages/*")],
        outputs=[OutputFieldMappingEntry(name="embedding", target_name="vector")],
    )

    index_projection = SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=INDEX_NAME,
                parent_key_field_name="parent_id",
                source_context="/document/pages/*",
                mappings=[
                    InputFieldMappingEntry(name="chunk", source="/document/pages/*"),
                    InputFieldMappingEntry(name="vector", source="/document/pages/*/vector"),
                    InputFieldMappingEntry(name="title", source="/document/metadata_storage_name"),
                ],
            )
        ],
        parameters=SearchIndexerIndexProjectionsParameters(
            projection_mode="skipIndexingParentDocuments"
        ),
    )

    skillset = SearchIndexerSkillset(
        name=f"{INDEX_NAME}-skillset",
        skills=[split_skill, embedding_skill],
        index_projection=index_projection,
    )
    indexer_client.create_or_update_skillset(skillset)
    print(f"✓ Skillset '{skillset.name}' created")

    # 4. Create and run indexer
    indexer = SearchIndexer(
        name=f"{INDEX_NAME}-indexer",
        data_source_name=data_source.name,
        target_index_name=INDEX_NAME,
        skillset_name=skillset.name,
    )
    indexer_client.create_or_update_indexer(indexer)
    indexer_client.run_indexer(indexer.name)
    print(f"✓ Indexer '{indexer.name}' created and running")

    # 5. Wait for completion
    search_client = SearchClient(SEARCH_ENDPOINT, INDEX_NAME, credential)
    print("\nWaiting for indexer to complete...")
    MAX_POLL_ITERATIONS = 120  # 120 × 5s = 10 min timeout

    for poll_iter in range(1, MAX_POLL_ITERATIONS + 1):
        time.sleep(5)
        status = indexer_client.get_indexer_status(indexer.name)
        last = status.last_result

        if last:
            doc_count = search_client.get_document_count()
            print(
                f"  Status: {last.status} | Docs processed: {last.item_count} | "
                f"Failed: {last.failed_item_count} | Index docs: {doc_count}"
            )

            if last.status in ("success", "transientFailure", "persistentFailure"):
                if last.errors:
                    print("\nErrors:")
                    for e in last.errors[:5]:
                        print(f"  - {e.message[:200]}")
                if last.warnings:
                    print("\nWarnings:")
                    for w in last.warnings[:5]:
                        print(f"  - {w.message[:200]}")
                break
        else:
            print("  Status: starting...")
    else:
        print(f"\n⚠ Timed out after {MAX_POLL_ITERATIONS * 5}s waiting for indexer. Check status manually.")

    print(f"\n✅ Indexing complete! {search_client.get_document_count()} chunks in index.")


if __name__ == "__main__":
    main()
