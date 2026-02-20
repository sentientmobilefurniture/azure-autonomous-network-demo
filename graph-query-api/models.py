"""
Pydantic request/response models — shared across routers and backends.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphQueryRequest(BaseModel):
    query: str


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


# ---------------------------------------------------------------------------
# Topology models — used by POST /query/topology (graph viewer)
# ---------------------------------------------------------------------------


class TopologyNode(BaseModel):
    id: str
    label: str  # vertex label (CoreRouter, AggSwitch, etc.)
    properties: dict[str, Any] = {}


class TopologyEdge(BaseModel):
    id: str
    source: str  # source vertex id
    target: str  # target vertex id
    label: str   # edge label (connects_to, aggregates_to, etc.)
    properties: dict[str, Any] = {}


class TopologyMeta(BaseModel):
    node_count: int
    edge_count: int
    query_time_ms: float
    labels: list[str] = []
    cached: bool = False


class TopologyRequest(BaseModel):
    query: str | None = None
    vertex_labels: list[str] | None = None


class TopologyResponse(BaseModel):
    nodes: list[TopologyNode] = []
    edges: list[TopologyEdge] = []
    meta: TopologyMeta | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Interaction models
# ---------------------------------------------------------------------------


class InteractionStep(BaseModel):
    step: int
    agent: str
    duration: str | None = None
    query: str | None = None
    response: str | None = None
    error: bool = False
    visualization: dict[str, Any] | None = None
    reasoning: str | None = None  # Story 2 compatibility


class InteractionRunMeta(BaseModel):
    steps: int
    time: str


class InteractionSaveRequest(BaseModel):
    scenario: str
    query: str
    steps: list[InteractionStep]
    diagnosis: str
    run_meta: InteractionRunMeta | None = None


class ReplayRequest(BaseModel):
    agent: str
    query: str
