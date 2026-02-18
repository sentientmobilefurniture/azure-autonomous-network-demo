"""
AI Search indexer service — create indexer pipelines from blob containers.

Adapted from the deprecated scripts/_indexer_common.py for use inside the
Container App (graph-query-api). Uses DefaultAzureCredential (managed identity).

Creates: data source → index (with vector field) → skillset (chunk + embed) → indexer
"""

from __future__ import annotations

import logging
import os
import time

from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexerClient, SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndexerDataContainer,
    SearchIndexerDataSourceConnection,
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    SearchIndexerSkillset,
    SplitSkill,
    AzureOpenAIEmbeddingSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    SearchIndexer,
)

from config import get_credential

logger = logging.getLogger("graph-query-api.indexer")


def _get_search_config() -> dict:
    """Resolve AI Search + Storage + OpenAI config from env vars."""
    search_name = os.getenv("AI_SEARCH_NAME", "")
    storage_account = os.getenv("STORAGE_ACCOUNT_NAME", "")
    foundry_name = os.getenv("AI_FOUNDRY_NAME", "")
    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
    rg = os.getenv("AZURE_RESOURCE_GROUP", "")
    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_dims = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    if not search_name:
        raise RuntimeError("AI_SEARCH_NAME env var not set — cannot create search indexes")
    if not storage_account:
        raise RuntimeError("STORAGE_ACCOUNT_NAME env var not set — cannot create data source")

    return {
        "search_endpoint": f"https://{search_name}.search.windows.net",
        "openai_endpoint": f"https://{foundry_name}.openai.azure.com" if foundry_name else "",
        "storage_connection": (
            f"ResourceId=/subscriptions/{sub_id}"
            f"/resourceGroups/{rg}"
            f"/providers/Microsoft.Storage/storageAccounts/{storage_account}/;"
        ),
        "embedding_model": embedding_model,
        "embedding_dims": embedding_dims,
    }


def create_search_index(
    *,
    index_name: str,
    container_name: str,
    on_progress: callable | None = None,
) -> dict:
    """Create a complete AI Search indexer pipeline and poll until done.

    Args:
        index_name: Search index name (e.g. '<scenario>-runbooks-index')
        container_name: Blob container name (e.g. 'runbooks')
        on_progress: Optional callback(detail: str) for progress updates

    Returns:
        {"index_name": ..., "document_count": ..., "status": ...}
    """
    def emit(msg: str):
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    cfg = _get_search_config()
    credential = get_credential()
    indexer_client = SearchIndexerClient(cfg["search_endpoint"], credential)
    index_client = SearchIndexClient(cfg["search_endpoint"], credential)

    # 1. Data source
    ds_name = f"{index_name}-datasource"
    data_source = SearchIndexerDataSourceConnection(
        name=ds_name,
        type="azureblob",
        connection_string=cfg["storage_connection"],
        container=SearchIndexerDataContainer(name=container_name),
    )
    indexer_client.create_or_update_data_source_connection(data_source)
    emit(f"Data source '{ds_name}' created")

    # 2. Index with vector field
    fields = [
        SearchField(name="chunk_id", type=SearchFieldDataType.String, key=True, analyzer_name="keyword"),
        SearchField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="chunk", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="title", type=SearchFieldDataType.String, searchable=True, filterable=True),
        SearchField(
            name="vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            vector_search_dimensions=cfg["embedding_dims"],
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
                    resource_url=cfg["openai_endpoint"],
                    deployment_name=cfg["embedding_model"],
                    model_name=cfg["embedding_model"],
                ),
            )
        ],
    )
    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    index_client.create_or_update_index(index)
    emit(f"Index '{index_name}' created")

    # 3. Skillset (chunk + embed)
    skillset_name = f"{index_name}-skillset"
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
        resource_url=cfg["openai_endpoint"],
        deployment_name=cfg["embedding_model"],
        model_name=cfg["embedding_model"],
        dimensions=cfg["embedding_dims"],
        inputs=[InputFieldMappingEntry(name="text", source="/document/pages/*")],
        outputs=[OutputFieldMappingEntry(name="embedding", target_name="vector")],
    )
    index_projection = SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=index_name,
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
        name=skillset_name,
        skills=[split_skill, embedding_skill],
        index_projection=index_projection,
    )
    indexer_client.create_or_update_skillset(skillset)
    emit(f"Skillset '{skillset_name}' created")

    # 4. Create and run indexer
    indexer_name = f"{index_name}-indexer"
    indexer = SearchIndexer(
        name=indexer_name,
        data_source_name=ds_name,
        target_index_name=index_name,
        skillset_name=skillset_name,
    )
    indexer_client.create_or_update_indexer(indexer)
    indexer_client.run_indexer(indexer_name)
    emit(f"Indexer '{indexer_name}' started")

    # 5. Poll until complete (max 5 min)
    search_client = SearchClient(cfg["search_endpoint"], index_name, credential)
    for poll in range(60):
        time.sleep(5)
        status = indexer_client.get_indexer_status(indexer_name)
        last = status.last_result
        if last:
            doc_count = search_client.get_document_count()
            emit(f"Indexing: {last.status} | {last.item_count} processed | {doc_count} in index")
            if last.status in ("success", "transientFailure", "persistentFailure"):
                return {
                    "index_name": index_name,
                    "document_count": doc_count,
                    "status": last.status,
                    "items_processed": last.item_count,
                    "items_failed": last.failed_item_count,
                }
        else:
            emit("Indexing: starting...")

    return {"index_name": index_name, "document_count": 0, "status": "timeout"}
