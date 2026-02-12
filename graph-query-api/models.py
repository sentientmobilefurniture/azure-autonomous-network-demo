"""
Pydantic request/response models — shared across routers and backends.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraphQueryRequest(BaseModel):
    query: str
    workspace_id: str = ""
    graph_model_id: str = ""


class GraphQueryResponse(BaseModel):
    columns: list[dict] = []
    data: list[dict] = []
    error: str | None = Field(
        default=None,
        description=(
            "If present, the query failed. Contains the error message. "
            "Read the message, fix your query, and retry."
        ),
    )


class TelemetryQueryRequest(BaseModel):
    query: str
    eventhouse_query_uri: str = ""
    kql_db_name: str = ""


class TelemetryQueryResponse(BaseModel):
    columns: list[dict] = []
    rows: list[dict] = []
    error: str | None = Field(
        default=None,
        description=(
            "If present, the query failed. Contains the error message. "
            "Read the message, fix your query, and retry."
        ),
    )


class ErrorResponse(BaseModel):
    error: str
