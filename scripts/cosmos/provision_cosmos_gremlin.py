#!/usr/bin/env python3
"""
Provision Cosmos DB Gremlin graph — load network topology from CSV files.

Reads the dimension & fact CSVs under data/lakehouse/ and creates vertices and
edges in the Azure Cosmos DB for Apache Gremlin graph.

Usage:
    # From project root (ensure azure_config.env is sourced)
    source azure_config.env
    cd scripts && uv run python provision_cosmos_gremlin.py

    # Or with explicit env vars:
    COSMOS_GREMLIN_ENDPOINT=xxx.gremlin.cosmos.azure.com \
    COSMOS_GREMLIN_PRIMARY_KEY=xxx \
    uv run python provision_cosmos_gremlin.py

Requires: gremlinpython>=3.7.0
"""

from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path

from gremlin_python.driver import client, serializer
from gremlin_python.driver.protocol import GremlinServerError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "lakehouse"

ENDPOINT = os.environ.get("COSMOS_GREMLIN_ENDPOINT", "")
PRIMARY_KEY = os.environ.get("COSMOS_GREMLIN_PRIMARY_KEY", "")
DATABASE = os.environ.get("COSMOS_GREMLIN_DATABASE", "networkgraph")
GRAPH = os.environ.get("COSMOS_GREMLIN_GRAPH", "topology")


def get_client() -> client.Client:
    if not ENDPOINT or not PRIMARY_KEY:
        print("ERROR: Set COSMOS_GREMLIN_ENDPOINT and COSMOS_GREMLIN_PRIMARY_KEY")
        sys.exit(1)
    return client.Client(
        url=f"wss://{ENDPOINT}:443/",
        traversal_source="g",
        username=f"/dbs/{DATABASE}/colls/{GRAPH}",
        password=PRIMARY_KEY,
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )


def submit(c: client.Client, query: str, bindings: dict | None = None, retries: int = 3):
    """Submit a Gremlin query with retry on 429."""
    for attempt in range(1, retries + 1):
        try:
            return c.submit(message=query, bindings=bindings or {}).all().result()
        except GremlinServerError as e:
            status = getattr(e, "status_code", 0)
            if status in (429, 408) and attempt < retries:
                wait = 2 ** attempt
                print(f"    ⏳ {status} — retrying in {wait}s (attempt {attempt}/{retries})")
                time.sleep(wait)
                continue
            raise


def read_csv(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Vertex loaders
# ---------------------------------------------------------------------------


def load_core_routers(c: client.Client):
    print("Loading CoreRouters...")
    for row in read_csv("DimCoreRouter.csv"):
        submit(c,
            "g.addV(label_val)"
            ".property('id', id_val)"
            ".property('partitionKey', pk_val)"
            ".property('RouterId', router_id)"
            ".property('City', city)"
            ".property('Region', region)"
            ".property('Vendor', vendor)"
            ".property('Model', model)",
            {
                "label_val": "CoreRouter",
                "id_val": row["RouterId"],
                "pk_val": "router",
                "router_id": row["RouterId"],
                "city": row["City"],
                "region": row["Region"],
                "vendor": row["Vendor"],
                "model": row["Model"],
            },
        )
        print(f"  ✓ CoreRouter {row['RouterId']}")


def load_agg_switches(c: client.Client):
    print("Loading AggSwitches...")
    for row in read_csv("DimAggSwitch.csv"):
        submit(c,
            "g.addV(label_val)"
            ".property('id', id_val)"
            ".property('partitionKey', pk_val)"
            ".property('SwitchId', switch_id)"
            ".property('City', city)"
            ".property('UplinkRouterId', uplink)",
            {
                "label_val": "AggSwitch",
                "id_val": row["SwitchId"],
                "pk_val": "switch",
                "switch_id": row["SwitchId"],
                "city": row["City"],
                "uplink": row["UplinkRouterId"],
            },
        )
        print(f"  ✓ AggSwitch {row['SwitchId']}")


def load_base_stations(c: client.Client):
    print("Loading BaseStations...")
    for row in read_csv("DimBaseStation.csv"):
        submit(c,
            "g.addV(label_val)"
            ".property('id', id_val)"
            ".property('partitionKey', pk_val)"
            ".property('StationId', station_id)"
            ".property('StationType', station_type)"
            ".property('AggSwitchId', agg_switch)"
            ".property('City', city)",
            {
                "label_val": "BaseStation",
                "id_val": row["StationId"],
                "pk_val": "basestation",
                "station_id": row["StationId"],
                "station_type": row["StationType"],
                "agg_switch": row["AggSwitchId"],
                "city": row["City"],
            },
        )
        print(f"  ✓ BaseStation {row['StationId']}")


def load_transport_links(c: client.Client):
    print("Loading TransportLinks...")
    for row in read_csv("DimTransportLink.csv"):
        submit(c,
            "g.addV(label_val)"
            ".property('id', id_val)"
            ".property('partitionKey', pk_val)"
            ".property('LinkId', link_id)"
            ".property('LinkType', link_type)"
            ".property('CapacityGbps', capacity)"
            ".property('SourceRouterId', source_router)"
            ".property('TargetRouterId', target_router)",
            {
                "label_val": "TransportLink",
                "id_val": row["LinkId"],
                "pk_val": "link",
                "link_id": row["LinkId"],
                "link_type": row["LinkType"],
                "capacity": row["CapacityGbps"],
                "source_router": row["SourceRouterId"],
                "target_router": row["TargetRouterId"],
            },
        )
        print(f"  ✓ TransportLink {row['LinkId']}")


def load_mpls_paths(c: client.Client):
    print("Loading MPLSPaths...")
    for row in read_csv("DimMPLSPath.csv"):
        submit(c,
            "g.addV(label_val)"
            ".property('id', id_val)"
            ".property('partitionKey', pk_val)"
            ".property('PathId', path_id)"
            ".property('PathType', path_type)",
            {
                "label_val": "MPLSPath",
                "id_val": row["PathId"],
                "pk_val": "path",
                "path_id": row["PathId"],
                "path_type": row["PathType"],
            },
        )
        print(f"  ✓ MPLSPath {row['PathId']}")


def load_services(c: client.Client):
    print("Loading Services...")
    for row in read_csv("DimService.csv"):
        submit(c,
            "g.addV(label_val)"
            ".property('id', id_val)"
            ".property('partitionKey', pk_val)"
            ".property('ServiceId', service_id)"
            ".property('ServiceType', service_type)"
            ".property('CustomerName', customer_name)"
            ".property('CustomerCount', customer_count)"
            ".property('ActiveUsers', active_users)",
            {
                "label_val": "Service",
                "id_val": row["ServiceId"],
                "pk_val": "service",
                "service_id": row["ServiceId"],
                "service_type": row["ServiceType"],
                "customer_name": row["CustomerName"],
                "customer_count": row["CustomerCount"],
                "active_users": row["ActiveUsers"],
            },
        )
        print(f"  ✓ Service {row['ServiceId']}")


def load_sla_policies(c: client.Client):
    print("Loading SLAPolicies...")
    for row in read_csv("DimSLAPolicy.csv"):
        submit(c,
            "g.addV(label_val)"
            ".property('id', id_val)"
            ".property('partitionKey', pk_val)"
            ".property('SLAPolicyId', policy_id)"
            ".property('ServiceId', service_id)"
            ".property('AvailabilityPct', availability)"
            ".property('MaxLatencyMs', max_latency)"
            ".property('PenaltyPerHourUSD', penalty)"
            ".property('Tier', tier)",
            {
                "label_val": "SLAPolicy",
                "id_val": row["SLAPolicyId"],
                "pk_val": "policy",
                "policy_id": row["SLAPolicyId"],
                "service_id": row["ServiceId"],
                "availability": row["AvailabilityPct"],
                "max_latency": row["MaxLatencyMs"],
                "penalty": row["PenaltyPerHourUSD"],
                "tier": row["Tier"],
            },
        )
        print(f"  ✓ SLAPolicy {row['SLAPolicyId']}")


def load_bgp_sessions(c: client.Client):
    print("Loading BGPSessions...")
    for row in read_csv("DimBGPSession.csv"):
        submit(c,
            "g.addV(label_val)"
            ".property('id', id_val)"
            ".property('partitionKey', pk_val)"
            ".property('SessionId', session_id)"
            ".property('PeerARouterId', peer_a)"
            ".property('PeerBRouterId', peer_b)"
            ".property('ASNumberA', asn_a)"
            ".property('ASNumberB', asn_b)",
            {
                "label_val": "BGPSession",
                "id_val": row["SessionId"],
                "pk_val": "session",
                "session_id": row["SessionId"],
                "peer_a": row["PeerARouterId"],
                "peer_b": row["PeerBRouterId"],
                "asn_a": row["ASNumberA"],
                "asn_b": row["ASNumberB"],
            },
        )
        print(f"  ✓ BGPSession {row['SessionId']}")


# ---------------------------------------------------------------------------
# Edge loaders  (derived from FK columns and fact tables)
# ---------------------------------------------------------------------------


def load_connects_to_edges(c: client.Client):
    """TransportLink connects_to CoreRouter (source & target)."""
    print("Loading connects_to edges (TransportLink → CoreRouter)...")
    for row in read_csv("DimTransportLink.csv"):
        # Source edge
        submit(c,
            "g.V().has('TransportLink', 'LinkId', link_id)"
            ".addE('connects_to')"
            ".to(g.V().has('CoreRouter', 'RouterId', router_id))"
            ".property('direction', dir_val)",
            {
                "link_id": row["LinkId"],
                "router_id": row["SourceRouterId"],
                "dir_val": "source",
            },
        )
        # Target edge
        submit(c,
            "g.V().has('TransportLink', 'LinkId', link_id)"
            ".addE('connects_to')"
            ".to(g.V().has('CoreRouter', 'RouterId', router_id))"
            ".property('direction', dir_val)",
            {
                "link_id": row["LinkId"],
                "router_id": row["TargetRouterId"],
                "dir_val": "target",
            },
        )
        print(f"  ✓ {row['LinkId']} connects_to {row['SourceRouterId']} + {row['TargetRouterId']}")


def load_aggregates_to_edges(c: client.Client):
    """AggSwitch aggregates_to CoreRouter (from UplinkRouterId FK)."""
    print("Loading aggregates_to edges (AggSwitch → CoreRouter)...")
    for row in read_csv("DimAggSwitch.csv"):
        submit(c,
            "g.V().has('AggSwitch', 'SwitchId', switch_id)"
            ".addE('aggregates_to')"
            ".to(g.V().has('CoreRouter', 'RouterId', router_id))",
            {
                "switch_id": row["SwitchId"],
                "router_id": row["UplinkRouterId"],
            },
        )
        print(f"  ✓ {row['SwitchId']} aggregates_to {row['UplinkRouterId']}")


def load_backhauls_via_edges(c: client.Client):
    """BaseStation backhauls_via AggSwitch (from AggSwitchId FK)."""
    print("Loading backhauls_via edges (BaseStation → AggSwitch)...")
    for row in read_csv("DimBaseStation.csv"):
        submit(c,
            "g.V().has('BaseStation', 'StationId', station_id)"
            ".addE('backhauls_via')"
            ".to(g.V().has('AggSwitch', 'SwitchId', switch_id))",
            {
                "station_id": row["StationId"],
                "switch_id": row["AggSwitchId"],
            },
        )
        print(f"  ✓ {row['StationId']} backhauls_via {row['AggSwitchId']}")


def load_routes_via_edges(c: client.Client):
    """MPLSPath routes_via TransportLink (from FactMPLSPathHops where NodeType=TransportLink)."""
    print("Loading routes_via edges (MPLSPath → TransportLink)...")
    for row in read_csv("FactMPLSPathHops.csv"):
        if row["NodeType"] != "TransportLink":
            continue  # Only create edges for transport link hops
        submit(c,
            "g.V().has('MPLSPath', 'PathId', path_id)"
            ".addE('routes_via')"
            ".to(g.V().has('TransportLink', 'LinkId', link_id))"
            ".property('HopOrder', hop_order)",
            {
                "path_id": row["PathId"],
                "link_id": row["NodeId"],
                "hop_order": row["HopOrder"],
            },
        )
        print(f"  ✓ {row['PathId']} routes_via {row['NodeId']} (hop {row['HopOrder']})")


def load_depends_on_edges(c: client.Client):
    """Service depends_on MPLSPath|AggSwitch|BaseStation (from FactServiceDependency)."""
    print("Loading depends_on edges (Service → dependency)...")
    # Map DependsOnType to vertex label and ID field
    type_map = {
        "MPLSPath": ("MPLSPath", "PathId"),
        "AggSwitch": ("AggSwitch", "SwitchId"),
        "BaseStation": ("BaseStation", "StationId"),
    }
    for row in read_csv("FactServiceDependency.csv"):
        dep_type = row["DependsOnType"]
        if dep_type not in type_map:
            print(f"  ⚠ Unknown DependsOnType: {dep_type} — skipping")
            continue
        label, id_field = type_map[dep_type]
        submit(c,
            f"g.V().has('Service', 'ServiceId', svc_id)"
            f".addE('depends_on')"
            f".to(g.V().has('{label}', '{id_field}', dep_id))"
            f".property('DependencyStrength', strength)",
            {
                "svc_id": row["ServiceId"],
                "dep_id": row["DependsOnId"],
                "strength": row["DependencyStrength"],
            },
        )
        print(f"  ✓ {row['ServiceId']} depends_on {row['DependsOnId']} ({row['DependencyStrength']})")


def load_governed_by_edges(c: client.Client):
    """SLAPolicy governed_by Service (from DimSLAPolicy.ServiceId FK)."""
    print("Loading governed_by edges (SLAPolicy → Service)...")
    for row in read_csv("DimSLAPolicy.csv"):
        submit(c,
            "g.V().has('SLAPolicy', 'SLAPolicyId', policy_id)"
            ".addE('governed_by')"
            ".to(g.V().has('Service', 'ServiceId', service_id))",
            {
                "policy_id": row["SLAPolicyId"],
                "service_id": row["ServiceId"],
            },
        )
        print(f"  ✓ {row['SLAPolicyId']} governed_by {row['ServiceId']}")


def load_peers_over_edges(c: client.Client):
    """BGPSession peers_over CoreRouter (both PeerA and PeerB)."""
    print("Loading peers_over edges (BGPSession → CoreRouter)...")
    for row in read_csv("DimBGPSession.csv"):
        # Peer A
        submit(c,
            "g.V().has('BGPSession', 'SessionId', session_id)"
            ".addE('peers_over')"
            ".to(g.V().has('CoreRouter', 'RouterId', router_id))"
            ".property('ASNumber', asn)",
            {
                "session_id": row["SessionId"],
                "router_id": row["PeerARouterId"],
                "asn": row["ASNumberA"],
            },
        )
        # Peer B
        submit(c,
            "g.V().has('BGPSession', 'SessionId', session_id)"
            ".addE('peers_over')"
            ".to(g.V().has('CoreRouter', 'RouterId', router_id))"
            ".property('ASNumber', asn)",
            {
                "session_id": row["SessionId"],
                "router_id": row["PeerBRouterId"],
                "asn": row["ASNumberB"],
            },
        )
        print(f"  ✓ {row['SessionId']} peers_over {row['PeerARouterId']} + {row['PeerBRouterId']}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(c: client.Client):
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    vertex_counts = submit(c, "g.V().groupCount().by(label)")
    print(f"  Vertices by label: {vertex_counts}")

    edge_counts = submit(c, "g.E().groupCount().by(label)")
    print(f"  Edges by label:    {edge_counts}")

    total_v = submit(c, "g.V().count()")
    total_e = submit(c, "g.E().count()")
    print(f"  Total: {total_v[0]} vertices, {total_e[0]} edges")

    # Sample traversal: routers → switches
    result = submit(c,
        "g.V().hasLabel('CoreRouter')"
        ".project('router','switches')"
        ".by('RouterId')"
        ".by(__.in('aggregates_to').values('SwitchId').fold())"
    )
    print(f"\n  Router→Switch mapping:")
    for r in result:
        print(f"    {r['router']}: {r['switches']}")

    # Check for orphan switches (no uplink)
    orphans = submit(c,
        "g.V().hasLabel('AggSwitch').not(__.out('aggregates_to')).values('SwitchId')"
    )
    if orphans:
        print(f"  ⚠ Orphan switches (no uplink): {orphans}")
    else:
        print("  ✓ All switches have uplink edges")

    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print(f"Cosmos DB Gremlin: {ENDPOINT} / {DATABASE} / {GRAPH}")
    print(f"Data dir: {DATA_DIR}")
    print()

    c = get_client()

    try:
        # 1. Clear existing data (idempotent reload)
        print("Clearing existing graph data...")
        submit(c, "g.V().drop()")
        print("  ✓ Graph cleared\n")

        # 2. Load all vertices (must be before edges)
        t0 = time.time()
        load_core_routers(c)
        load_agg_switches(c)
        load_base_stations(c)
        load_transport_links(c)
        load_mpls_paths(c)
        load_services(c)
        load_sla_policies(c)
        load_bgp_sessions(c)
        vertex_time = time.time() - t0
        print(f"\n  Vertices loaded in {vertex_time:.1f}s\n")

        # 3. Load all edges
        t1 = time.time()
        load_connects_to_edges(c)
        load_aggregates_to_edges(c)
        load_backhauls_via_edges(c)
        load_routes_via_edges(c)
        load_depends_on_edges(c)
        load_governed_by_edges(c)
        load_peers_over_edges(c)
        edge_time = time.time() - t1
        print(f"\n  Edges loaded in {edge_time:.1f}s\n")

        # 4. Verify
        verify(c)

        total = time.time() - t0
        print(f"\nDone in {total:.1f}s")

    finally:
        c.close()


if __name__ == "__main__":
    main()
