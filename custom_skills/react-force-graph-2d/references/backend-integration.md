# Backend Integration

FastAPI backend, Pydantic models, graph database queries, and proxy configuration for the topology API.

---

## API Contract

| Method | Endpoint | Request Body | Response |
|--------|----------|-------------|----------|
| POST | `/query/topology` | `{ "vertex_labels": string[] }` | `{ "nodes": [], "edges": [], "meta": {} }` |

The frontend calls this via a Vite dev proxy (or nginx in production). The API returns the full topology or a subset filtered by vertex labels.

---

## Pydantic Models

All request/response types are defined in a shared `models.py`:

```python
from pydantic import BaseModel

class TopologyNode(BaseModel):
    id: str
    label: str
    properties: dict = {}

class TopologyEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    properties: dict = {}

class TopologyMeta(BaseModel):
    node_count: int
    edge_count: int
    query_time_ms: float
    labels: list[str]

class TopologyRequest(BaseModel):
    vertex_labels: list[str] | None = None

class TopologyResponse(BaseModel):
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    meta: TopologyMeta
    error: str | None = None
```

### TypeScript Mirror Types (frontend)

Keep these in sync with the Pydantic models:

```typescript
interface TopologyNode {
  id: string;
  label: string;
  properties: Record<string, unknown>;
}

interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  properties: Record<string, unknown>;
}

interface TopologyMeta {
  node_count: number;
  edge_count: number;
  query_time_ms: number;
  labels: string[];
}
```

---

## FastAPI Router

The topology endpoint delegates to a pluggable backend (mock or cosmosdb). The backend is selected at startup via environment configuration:

```python
from fastapi import APIRouter
from models import TopologyRequest, TopologyResponse

router = APIRouter(prefix="/query")

# Backend selection — set during app startup
from backends.mock import get_topology
# from backends.cosmosdb import get_topology

@router.post("/topology", response_model=TopologyResponse)
async def topology(request: TopologyRequest):
    try:
        result = await get_topology(vertex_labels=request.vertex_labels)
        return result
    except Exception as e:
        return TopologyResponse(
            nodes=[], edges=[],
            meta=TopologyMeta(node_count=0, edge_count=0, query_time_ms=0, labels=[]),
            error=str(e),
        )
```

---

## Mock Backend

A static graph for development and testing. Returns immediately with deterministic data:

```python
import time
from models import TopologyNode, TopologyEdge, TopologyMeta, TopologyResponse

# Static node/edge data — 50 nodes across 5 label types
MOCK_NODES = [
    TopologyNode(id="router-core-01", label="Router",
                 properties={"vendor": "Cisco", "model": "ASR-9000", "status": "active"}),
    TopologyNode(id="switch-dist-01", label="Switch",
                 properties={"vendor": "Arista", "model": "7050X", "status": "active"}),
    TopologyNode(id="firewall-01", label="Firewall",
                 properties={"vendor": "Palo Alto", "model": "PA-5260", "zone": "dmz"}),
    # ... 47 more nodes
]

MOCK_EDGES = [
    TopologyEdge(id="e1", source="router-core-01", target="switch-dist-01",
                 label="CONNECTS_TO", properties={"bandwidth": "100Gbps"}),
    TopologyEdge(id="e2", source="switch-dist-01", target="firewall-01",
                 label="CONNECTS_TO", properties={"bandwidth": "40Gbps"}),
    # ... 48 more edges
]

async def get_topology(vertex_labels: list[str] | None = None) -> TopologyResponse:
    start = time.time()
    nodes = MOCK_NODES
    if vertex_labels:
        nodes = [n for n in MOCK_NODES if n.label in vertex_labels]
    node_ids = {n.id for n in nodes}
    edges = [e for e in MOCK_EDGES if e.source in node_ids and e.target in node_ids]
    elapsed = (time.time() - start) * 1000
    labels = sorted(set(n.label for n in nodes))
    return TopologyResponse(
        nodes=nodes,
        edges=edges,
        meta=TopologyMeta(
            node_count=len(nodes), edge_count=len(edges),
            query_time_ms=round(elapsed, 2), labels=labels,
        ),
    )
```

---

## Cosmos DB (Gremlin) Backend

Production backend querying Azure Cosmos DB via the Apache TinkerPop Gremlin WebSocket protocol:

```python
import time
import os
from gremlin_python.driver import client, serializer
from models import TopologyNode, TopologyEdge, TopologyMeta, TopologyResponse

COSMOS_ENDPOINT = os.environ["COSMOS_GREMLIN_ENDPOINT"]   # wss://<account>.gremlin.cosmos.azure.com:443/
COSMOS_KEY = os.environ["COSMOS_GREMLIN_KEY"]
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "networkdb")
COSMOS_CONTAINER = os.environ.get("COSMOS_CONTAINER", "topology")

def _get_client():
    return client.Client(
        COSMOS_ENDPOINT,
        "g",
        username=f"/dbs/{COSMOS_DATABASE}/colls/{COSMOS_CONTAINER}",
        password=COSMOS_KEY,
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )

async def get_topology(vertex_labels: list[str] | None = None) -> TopologyResponse:
    start = time.time()
    gremlin_client = _get_client()
    try:
        # Fetch vertices
        if vertex_labels:
            labels_str = ",".join(f"'{l}'" for l in vertex_labels)
            v_query = f"g.V().has('label', within({labels_str}))"
        else:
            v_query = "g.V()"
        vertices = gremlin_client.submit(v_query).all().result()

        # Build node list
        nodes = []
        node_ids = set()
        for v in vertices:
            props = {k: v["properties"][k][0]["value"]
                     for k in v.get("properties", {}) if k != "pk"}
            nodes.append(TopologyNode(
                id=v["id"], label=v["label"], properties=props,
            ))
            node_ids.add(v["id"])

        # Fetch edges between found vertices
        e_query = "g.E()"
        raw_edges = gremlin_client.submit(e_query).all().result()
        edges = []
        for e in raw_edges:
            src = e["outV"]
            tgt = e["inV"]
            if src in node_ids and tgt in node_ids:
                props = {k: e["properties"][k]
                         for k in e.get("properties", {})}
                edges.append(TopologyEdge(
                    id=e["id"], source=src, target=tgt,
                    label=e["label"], properties=props,
                ))

        elapsed = (time.time() - start) * 1000
        labels = sorted(set(n.label for n in nodes))
        return TopologyResponse(
            nodes=nodes, edges=edges,
            meta=TopologyMeta(
                node_count=len(nodes), edge_count=len(edges),
                query_time_ms=round(elapsed, 2), labels=labels,
            ),
        )
    finally:
        gremlin_client.close()
```

---

## GraphBackend Protocol

To make switching backends type-safe, define a Protocol:

```python
from typing import Protocol

class GraphBackend(Protocol):
    async def get_topology(
        self, vertex_labels: list[str] | None = None,
    ) -> TopologyResponse: ...
```

Register the active backend via dependency injection or a simple factory:

```python
def get_backend() -> GraphBackend:
    mode = os.environ.get("GRAPH_BACKEND", "mock")
    if mode == "cosmosdb":
        from backends.cosmosdb import CosmosBackend
        return CosmosBackend()
    from backends.mock import MockBackend
    return MockBackend()
```

---

## Proxy Configuration

### Vite Dev Proxy

In `vite.config.ts`, proxy `/query` requests to the graph-query-api:

```typescript
export default defineConfig({
  server: {
    proxy: {
      '/query': {
        target: 'http://localhost:8100',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

The graph-query-api runs on port **8100**, separate from the main API on port **8000**.

### Nginx Production Proxy

In production, nginx routes `/query/` to the graph-query-api container:

```nginx
location /query/ {
    proxy_pass http://graph-query-api:8100;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}

location /api/ {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
}
```

---

## Adding a New Backend

1. Create `backends/newbackend.py` implementing the `GraphBackend` protocol
2. Implement `async get_topology(vertex_labels) → TopologyResponse`
3. Register in the factory function
4. Set `GRAPH_BACKEND=newbackend` in your environment
5. No frontend changes required — the API contract is the same
