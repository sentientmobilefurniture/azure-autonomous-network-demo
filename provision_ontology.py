"""
Provision Fabric IQ Ontology — automates Day 2 Steps 2.1–2.5.

Creates the NetworkTopologyOntology item with:
  - 8 entity types (CoreRouter, TransportLink, AggSwitch, BaseStation,
    BGPSession, MPLSPath, Service, SLAPolicy)
  - Static data bindings to Lakehouse tables
  - Time-series data binding to Eventhouse (LinkTelemetry)
  - 7 relationship types with contextualizations (edge data bindings)

Prerequisites:
  - provision_fabric.py has run (workspace, lakehouse, eventhouse exist)
  - azure_config.env populated with FABRIC_WORKSPACE_ID, FABRIC_LAKEHOUSE_ID, etc.
  - Lakehouse tables loaded (managed delta tables)
  - Eventhouse tables created and ingested (AlertStream, LinkTelemetry)

Usage:
  uv run provision_ontology.py
"""

import base64
import json
import os
import sys
import time
import uuid

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv("azure_config.env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FABRIC_API = "https://api.fabric.microsoft.com/v1"
WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
LAKEHOUSE_ID = os.getenv("FABRIC_LAKEHOUSE_ID", "")
EVENTHOUSE_ID = os.getenv("FABRIC_EVENTHOUSE_ID", "")
KQL_DB_NAME = os.getenv("FABRIC_KQL_DB_NAME", "")

ONTOLOGY_NAME = "NetworkTopologyOntologyAuto2"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def b64(obj: dict) -> str:
    """Base64-encode a dict as compact JSON."""
    return base64.b64encode(json.dumps(obj).encode()).decode()


def duuid(seed: str) -> str:
    """Deterministic UUID5 from a seed string."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


def prop(pid: int, name: str, vtype: str = "String") -> dict:
    """Build an EntityTypeProperty."""
    return {
        "id": str(pid),
        "name": name,
        "redefines": None,
        "baseTypeNamespaceType": None,
        "valueType": vtype,
    }


# ---------------------------------------------------------------------------
# ID allocation — positive 64-bit integers, unique across the ontology
# ---------------------------------------------------------------------------

# Entity type IDs
ET_CORE_ROUTER = 1000000000001
ET_TRANSPORT_LINK = 1000000000002
ET_AGG_SWITCH = 1000000000003
ET_BASE_STATION = 1000000000004
ET_BGP_SESSION = 1000000000005
ET_MPLS_PATH = 1000000000006
ET_SERVICE = 1000000000007
ET_SLA_POLICY = 1000000000008

# Property IDs — CoreRouter
P_ROUTER_ID = 2000000000001
P_ROUTER_NAME = 2000000000002
P_ROUTER_CITY = 2000000000003
P_ROUTER_REGION = 2000000000004
P_ROUTER_VENDOR = 2000000000005
P_ROUTER_MODEL = 2000000000006
P_ROUTER_STATUS = 2000000000007

# Property IDs — TransportLink (static)
P_LINK_ID = 2000000000011
P_LINK_NAME = 2000000000012
P_LINK_TYPE = 2000000000013
P_CAPACITY_GBPS = 2000000000014
P_SOURCE_ROUTER_ID = 2000000000015
P_TARGET_ROUTER_ID = 2000000000016
P_LINK_STATUS = 2000000000017
# TransportLink (time-series)
P_TL_TIMESTAMP = 2000000000018
P_TL_UTIL_PCT = 2000000000019
P_TL_OPT_POWER = 2000000000020
P_TL_BER = 2000000000021
P_TL_LATENCY = 2000000000022

# Property IDs — AggSwitch
P_SWITCH_ID = 2000000000031
P_SWITCH_NAME = 2000000000032
P_SWITCH_CITY = 2000000000033
P_UPLINK_ROUTER_ID = 2000000000034
P_SWITCH_STATUS = 2000000000035

# Property IDs — BaseStation
P_STATION_ID = 2000000000041
P_STATION_NAME = 2000000000042
P_STATION_TYPE = 2000000000043
P_STATION_AGG_SWITCH = 2000000000044
P_STATION_CITY = 2000000000045
P_STATION_STATUS = 2000000000046

# Property IDs — BGPSession
P_SESSION_ID = 2000000000051
P_PEER_A_ROUTER = 2000000000052
P_PEER_B_ROUTER = 2000000000053
P_AS_NUMBER_A = 2000000000054
P_AS_NUMBER_B = 2000000000055
P_BGP_STATUS = 2000000000056

# Property IDs — MPLSPath
P_PATH_ID = 2000000000061
P_PATH_NAME = 2000000000062
P_PATH_TYPE = 2000000000063
P_PATH_STATUS = 2000000000064

# Property IDs — Service
P_SERVICE_ID = 2000000000071
P_SERVICE_NAME = 2000000000072
P_SERVICE_TYPE = 2000000000073
P_CUSTOMER_NAME = 2000000000074
P_CUSTOMER_COUNT = 2000000000075
P_ACTIVE_USERS = 2000000000076
P_SERVICE_STATUS = 2000000000077

# Property IDs — SLAPolicy
P_SLA_POLICY_ID = 2000000000081
P_SLA_SERVICE_ID = 2000000000082
P_AVAILABILITY_PCT = 2000000000083
P_MAX_LATENCY_MS = 2000000000084
P_PENALTY_PER_HOUR = 2000000000085
P_SLA_TIER = 2000000000086

# Relationship type IDs
R_CONNECTS_TO = 3000000000001
R_AGGREGATES_TO = 3000000000002
R_BACKHAULS_VIA = 3000000000003
R_ROUTES_VIA = 3000000000004
R_DEPENDS_ON = 3000000000005
R_GOVERNED_BY = 3000000000006
R_PEERS_OVER = 3000000000007

# ---------------------------------------------------------------------------
# Entity type definitions
# ---------------------------------------------------------------------------

ENTITY_TYPES = [
    {
        "id": str(ET_CORE_ROUTER),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "CoreRouter",
        "entityIdParts": [str(P_ROUTER_ID)],
        "displayNamePropertyId": str(P_ROUTER_NAME),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_ROUTER_ID, "RouterId"),
            prop(P_ROUTER_NAME, "RouterName"),
            prop(P_ROUTER_CITY, "RouterCity"),
            prop(P_ROUTER_REGION, "RouterRegion"),
            prop(P_ROUTER_VENDOR, "RouterVendor"),
            prop(P_ROUTER_MODEL, "RouterModel"),
            prop(P_ROUTER_STATUS, "RouterStatus"),
        ],
        "timeseriesProperties": [],
    },
    {
        "id": str(ET_TRANSPORT_LINK),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "TransportLink",
        "entityIdParts": [str(P_LINK_ID)],
        "displayNamePropertyId": str(P_LINK_NAME),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_LINK_ID, "LinkId"),
            prop(P_LINK_NAME, "LinkName"),
            prop(P_LINK_TYPE, "LinkType"),
            prop(P_CAPACITY_GBPS, "CapacityGbps", "BigInt"),
            prop(P_SOURCE_ROUTER_ID, "SourceRouterId"),
            prop(P_TARGET_ROUTER_ID, "TargetRouterId"),
            prop(P_LINK_STATUS, "LinkStatus"),
        ],
        "timeseriesProperties": [
            prop(P_TL_TIMESTAMP, "TLTimestamp", "DateTime"),
            prop(P_TL_UTIL_PCT, "UtilizationPct", "Double"),
            prop(P_TL_OPT_POWER, "TLOpticalPowerDbm", "Double"),
            prop(P_TL_BER, "TLBitErrorRate", "Double"),
            prop(P_TL_LATENCY, "TLLatencyMs", "Double"),
        ],
    },
    {
        "id": str(ET_AGG_SWITCH),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "AggSwitch",
        "entityIdParts": [str(P_SWITCH_ID)],
        "displayNamePropertyId": str(P_SWITCH_NAME),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_SWITCH_ID, "SwitchId"),
            prop(P_SWITCH_NAME, "SwitchName"),
            prop(P_SWITCH_CITY, "SwitchCity"),
            prop(P_UPLINK_ROUTER_ID, "UplinkRouterId"),
            prop(P_SWITCH_STATUS, "SwitchStatus"),
        ],
        "timeseriesProperties": [],
    },
    {
        "id": str(ET_BASE_STATION),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "BaseStation",
        "entityIdParts": [str(P_STATION_ID)],
        "displayNamePropertyId": str(P_STATION_NAME),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_STATION_ID, "StationId"),
            prop(P_STATION_NAME, "StationName"),
            prop(P_STATION_TYPE, "StationType"),
            prop(P_STATION_AGG_SWITCH, "StationAggSwitchId"),
            prop(P_STATION_CITY, "StationCity"),
            prop(P_STATION_STATUS, "StationStatus"),
        ],
        "timeseriesProperties": [],
    },
    {
        "id": str(ET_BGP_SESSION),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "BGPSession",
        "entityIdParts": [str(P_SESSION_ID)],
        "displayNamePropertyId": str(P_SESSION_ID),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_SESSION_ID, "SessionId"),
            prop(P_PEER_A_ROUTER, "PeerARouterId"),
            prop(P_PEER_B_ROUTER, "PeerBRouterId"),
            prop(P_AS_NUMBER_A, "ASNumberA", "BigInt"),
            prop(P_AS_NUMBER_B, "ASNumberB", "BigInt"),
            prop(P_BGP_STATUS, "BGPStatus"),
        ],
        "timeseriesProperties": [],
    },
    {
        "id": str(ET_MPLS_PATH),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "MPLSPath",
        "entityIdParts": [str(P_PATH_ID)],
        "displayNamePropertyId": str(P_PATH_NAME),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_PATH_ID, "PathId"),
            prop(P_PATH_NAME, "PathName"),
            prop(P_PATH_TYPE, "PathType"),
            prop(P_PATH_STATUS, "PathStatus"),
        ],
        "timeseriesProperties": [],
    },
    {
        "id": str(ET_SERVICE),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "Service",
        "entityIdParts": [str(P_SERVICE_ID)],
        "displayNamePropertyId": str(P_SERVICE_NAME),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_SERVICE_ID, "ServiceId"),
            prop(P_SERVICE_NAME, "ServiceName"),
            prop(P_SERVICE_TYPE, "ServiceType"),
            prop(P_CUSTOMER_NAME, "CustomerName"),
            prop(P_CUSTOMER_COUNT, "CustomerCount", "BigInt"),
            prop(P_ACTIVE_USERS, "ActiveUsers", "BigInt"),
            prop(P_SERVICE_STATUS, "ServiceStatus"),
        ],
        "timeseriesProperties": [],
    },
    {
        "id": str(ET_SLA_POLICY),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": "SLAPolicy",
        "entityIdParts": [str(P_SLA_POLICY_ID)],
        "displayNamePropertyId": str(P_SLA_POLICY_ID),
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": [
            prop(P_SLA_POLICY_ID, "SLAPolicyId"),
            prop(P_SLA_SERVICE_ID, "SLAServiceId"),
            prop(P_AVAILABILITY_PCT, "AvailabilityPct", "Double"),
            prop(P_MAX_LATENCY_MS, "MaxLatencyMs", "BigInt"),
            prop(P_PENALTY_PER_HOUR, "PenaltyPerHourUSD", "BigInt"),
            prop(P_SLA_TIER, "SLATier"),
        ],
        "timeseriesProperties": [],
    },
]

# ---------------------------------------------------------------------------
# Static data bindings — Lakehouse tables → entity types
# ---------------------------------------------------------------------------

def lakehouse_binding(seed: str, table: str, bindings: list[tuple[str, int]]) -> dict:
    """Build a NonTimeSeries Lakehouse data binding.

    bindings: list of (sourceColumnName, targetPropertyId) tuples
    """
    return {
        "id": duuid(seed),
        "dataBindingConfiguration": {
            "dataBindingType": "NonTimeSeries",
            "propertyBindings": [
                {"sourceColumnName": col, "targetPropertyId": str(pid)}
                for col, pid in bindings
            ],
            "sourceTableProperties": {
                "sourceType": "LakehouseTable",
                "workspaceId": WORKSPACE_ID,
                "itemId": LAKEHOUSE_ID,
                "sourceTableName": table,
                "sourceSchema": "dbo",
            },
        },
    }


def eventhouse_binding(
    seed: str,
    table: str,
    cluster_uri: str,
    db_name: str,
    timestamp_col: str,
    bindings: list[tuple[str, int]],
) -> dict:
    """Build a TimeSeries Eventhouse data binding."""
    return {
        "id": duuid(seed),
        "dataBindingConfiguration": {
            "dataBindingType": "TimeSeries",
            "timestampColumnName": timestamp_col,
            "propertyBindings": [
                {"sourceColumnName": col, "targetPropertyId": str(pid)}
                for col, pid in bindings
            ],
            "sourceTableProperties": {
                "sourceType": "KustoTable",
                "workspaceId": WORKSPACE_ID,
                "itemId": EVENTHOUSE_ID,
                "clusterUri": cluster_uri,
                "databaseName": db_name,
                "sourceTableName": table,
            },
        },
    }


def build_static_bindings() -> dict[int, list[dict]]:
    """Return entity_type_id → [binding, ...] for all static bindings."""
    return {
        ET_CORE_ROUTER: [
            lakehouse_binding("CoreRouter-static", "DimCoreRouter", [
                ("RouterId", P_ROUTER_ID),
                ("RouterName", P_ROUTER_NAME),
                ("City", P_ROUTER_CITY),
                ("Region", P_ROUTER_REGION),
                ("Vendor", P_ROUTER_VENDOR),
                ("Model", P_ROUTER_MODEL),
                ("Status", P_ROUTER_STATUS),
            ]),
        ],
        ET_TRANSPORT_LINK: [
            lakehouse_binding("TransportLink-static", "DimTransportLink", [
                ("LinkId", P_LINK_ID),
                ("LinkName", P_LINK_NAME),
                ("LinkType", P_LINK_TYPE),
                ("CapacityGbps", P_CAPACITY_GBPS),
                ("SourceRouterId", P_SOURCE_ROUTER_ID),
                ("TargetRouterId", P_TARGET_ROUTER_ID),
                ("Status", P_LINK_STATUS),
            ]),
        ],
        ET_AGG_SWITCH: [
            lakehouse_binding("AggSwitch-static", "DimAggSwitch", [
                ("SwitchId", P_SWITCH_ID),
                ("SwitchName", P_SWITCH_NAME),
                ("City", P_SWITCH_CITY),
                ("UplinkRouterId", P_UPLINK_ROUTER_ID),
                ("Status", P_SWITCH_STATUS),
            ]),
        ],
        ET_BASE_STATION: [
            lakehouse_binding("BaseStation-static", "DimBaseStation", [
                ("StationId", P_STATION_ID),
                ("StationName", P_STATION_NAME),
                ("StationType", P_STATION_TYPE),
                ("AggSwitchId", P_STATION_AGG_SWITCH),
                ("City", P_STATION_CITY),
                ("Status", P_STATION_STATUS),
            ]),
        ],
        ET_BGP_SESSION: [
            lakehouse_binding("BGPSession-static", "DimBGPSession", [
                ("SessionId", P_SESSION_ID),
                ("PeerARouterId", P_PEER_A_ROUTER),
                ("PeerBRouterId", P_PEER_B_ROUTER),
                ("ASNumberA", P_AS_NUMBER_A),
                ("ASNumberB", P_AS_NUMBER_B),
                ("Status", P_BGP_STATUS),
            ]),
        ],
        ET_MPLS_PATH: [
            lakehouse_binding("MPLSPath-static", "DimMPLSPath", [
                ("PathId", P_PATH_ID),
                ("PathName", P_PATH_NAME),
                ("PathType", P_PATH_TYPE),
                ("Status", P_PATH_STATUS),
            ]),
        ],
        ET_SERVICE: [
            lakehouse_binding("Service-static", "DimService", [
                ("ServiceId", P_SERVICE_ID),
                ("ServiceName", P_SERVICE_NAME),
                ("ServiceType", P_SERVICE_TYPE),
                ("CustomerName", P_CUSTOMER_NAME),
                ("CustomerCount", P_CUSTOMER_COUNT),
                ("ActiveUsers", P_ACTIVE_USERS),
                ("Status", P_SERVICE_STATUS),
            ]),
        ],
        ET_SLA_POLICY: [
            lakehouse_binding("SLAPolicy-static", "DimSLAPolicy", [
                ("SLAPolicyId", P_SLA_POLICY_ID),
                ("ServiceId", P_SLA_SERVICE_ID),
                ("AvailabilityPct", P_AVAILABILITY_PCT),
                ("MaxLatencyMs", P_MAX_LATENCY_MS),
                ("PenaltyPerHourUSD", P_PENALTY_PER_HOUR),
                ("Tier", P_SLA_TIER),
            ]),
        ],
    }


def build_timeseries_binding(cluster_uri: str, db_name: str) -> dict:
    """LinkTelemetry → TransportLink time-series binding."""
    return eventhouse_binding(
        seed="TransportLink-timeseries",
        table="LinkTelemetry",
        cluster_uri=cluster_uri,
        db_name=db_name,
        timestamp_col="Timestamp",
        bindings=[
            ("Timestamp", P_TL_TIMESTAMP),
            ("UtilizationPct", P_TL_UTIL_PCT),
            ("OpticalPowerDbm", P_TL_OPT_POWER),
            ("BitErrorRate", P_TL_BER),
            ("LatencyMs", P_TL_LATENCY),
            # Map LinkId to static entity key so system matches rows → entities
            ("LinkId", P_LINK_ID),
        ],
    )


# ---------------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------------

RELATIONSHIP_TYPES = [
    {
        "id": str(R_CONNECTS_TO),
        "namespace": "usertypes",
        "name": "connects_to",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_TRANSPORT_LINK)},
        "target": {"entityTypeId": str(ET_CORE_ROUTER)},
    },
    {
        "id": str(R_AGGREGATES_TO),
        "namespace": "usertypes",
        "name": "aggregates_to",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_AGG_SWITCH)},
        "target": {"entityTypeId": str(ET_CORE_ROUTER)},
    },
    {
        "id": str(R_BACKHAULS_VIA),
        "namespace": "usertypes",
        "name": "backhauls_via",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_BASE_STATION)},
        "target": {"entityTypeId": str(ET_AGG_SWITCH)},
    },
    {
        "id": str(R_ROUTES_VIA),
        "namespace": "usertypes",
        "name": "routes_via",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_MPLS_PATH)},
        "target": {"entityTypeId": str(ET_TRANSPORT_LINK)},
    },
    {
        "id": str(R_DEPENDS_ON),
        "namespace": "usertypes",
        "name": "depends_on",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_SERVICE)},
        "target": {"entityTypeId": str(ET_MPLS_PATH)},
    },
    {
        "id": str(R_GOVERNED_BY),
        "namespace": "usertypes",
        "name": "governed_by",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_SLA_POLICY)},
        "target": {"entityTypeId": str(ET_SERVICE)},
    },
    {
        "id": str(R_PEERS_OVER),
        "namespace": "usertypes",
        "name": "peers_over",
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(ET_BGP_SESSION)},
        "target": {"entityTypeId": str(ET_CORE_ROUTER)},
    },
]

# ---------------------------------------------------------------------------
# Contextualizations — bind relationship types to Lakehouse junction tables
# ---------------------------------------------------------------------------


def ctx(seed: str, table: str, src_bindings: list, tgt_bindings: list) -> dict:
    """Build a Contextualization (relationship data binding)."""
    return {
        "id": duuid(seed),
        "dataBindingTable": {
            "sourceType": "LakehouseTable",
            "workspaceId": WORKSPACE_ID,
            "itemId": LAKEHOUSE_ID,
            "sourceTableName": table,
        },
        "sourceKeyRefBindings": [
            {"sourceColumnName": col, "targetPropertyId": str(pid)}
            for col, pid in src_bindings
        ],
        "targetKeyRefBindings": [
            {"sourceColumnName": col, "targetPropertyId": str(pid)}
            for col, pid in tgt_bindings
        ],
    }


def build_contextualizations() -> dict[int, list[dict]]:
    """Return rel_type_id → [contextualization, ...]."""
    return {
        # connects_to: TransportLink → CoreRouter
        # Two contextualizations — one for each endpoint of the link
        R_CONNECTS_TO: [
            ctx("connects_to-source", "DimTransportLink",
                [("LinkId", P_LINK_ID)],
                [("SourceRouterId", P_ROUTER_ID)]),
            ctx("connects_to-target", "DimTransportLink",
                [("LinkId", P_LINK_ID)],
                [("TargetRouterId", P_ROUTER_ID)]),
        ],
        # aggregates_to: AggSwitch → CoreRouter
        R_AGGREGATES_TO: [
            ctx("aggregates_to", "DimAggSwitch",
                [("SwitchId", P_SWITCH_ID)],
                [("UplinkRouterId", P_ROUTER_ID)]),
        ],
        # backhauls_via: BaseStation → AggSwitch
        R_BACKHAULS_VIA: [
            ctx("backhauls_via", "DimBaseStation",
                [("StationId", P_STATION_ID)],
                [("AggSwitchId", P_SWITCH_ID)]),
        ],
        # routes_via: MPLSPath → TransportLink (via FactMPLSPathHops)
        # Rows where NodeType != TransportLink will not match any LinkId → ignored
        R_ROUTES_VIA: [
            ctx("routes_via", "FactMPLSPathHops",
                [("PathId", P_PATH_ID)],
                [("NodeId", P_LINK_ID)]),
        ],
        # depends_on: Service → MPLSPath (via FactServiceDependency)
        # Rows where DependsOnType != MPLSPath will not match any PathId → ignored
        R_DEPENDS_ON: [
            ctx("depends_on", "FactServiceDependency",
                [("ServiceId", P_SERVICE_ID)],
                [("DependsOnId", P_PATH_ID)]),
        ],
        # governed_by: SLAPolicy → Service
        R_GOVERNED_BY: [
            ctx("governed_by", "DimSLAPolicy",
                [("SLAPolicyId", P_SLA_POLICY_ID)],
                [("ServiceId", P_SERVICE_ID)]),
        ],
        # peers_over: BGPSession → CoreRouter
        # Two contextualizations — PeerA and PeerB
        R_PEERS_OVER: [
            ctx("peers_over-a", "DimBGPSession",
                [("SessionId", P_SESSION_ID)],
                [("PeerARouterId", P_ROUTER_ID)]),
            ctx("peers_over-b", "DimBGPSession",
                [("SessionId", P_SESSION_ID)],
                [("PeerBRouterId", P_ROUTER_ID)]),
        ],
    }


# ---------------------------------------------------------------------------
# Assemble ontology definition parts
# ---------------------------------------------------------------------------

def build_definition_parts(
    bindings: dict[int, list[dict]],
    contextualizations: dict[int, list[dict]],
) -> list[dict]:
    """Build the full parts array for the ontology definition."""
    parts = [
        {
            "path": ".platform",
            "payload": b64({
                "metadata": {
                    "type": "Ontology",
                    "displayName": ONTOLOGY_NAME,
                },
            }),
            "payloadType": "InlineBase64",
        },
        {
            "path": "definition.json",
            "payload": b64({}),
            "payloadType": "InlineBase64",
        },
    ]

    # Entity types + data bindings
    for et in ENTITY_TYPES:
        et_id = et["id"]
        parts.append({
            "path": f"EntityTypes/{et_id}/definition.json",
            "payload": b64(et),
            "payloadType": "InlineBase64",
        })
        for binding in bindings.get(int(et_id), []):
            parts.append({
                "path": f"EntityTypes/{et_id}/DataBindings/{binding['id']}.json",
                "payload": b64(binding),
                "payloadType": "InlineBase64",
            })

    # Relationship types + contextualizations
    for rel in RELATIONSHIP_TYPES:
        rel_id = rel["id"]
        parts.append({
            "path": f"RelationshipTypes/{rel_id}/definition.json",
            "payload": b64(rel),
            "payloadType": "InlineBase64",
        })
        for c in contextualizations.get(int(rel_id), []):
            parts.append({
                "path": f"RelationshipTypes/{rel_id}/Contextualizations/{c['id']}.json",
                "payload": b64(c),
                "payloadType": "InlineBase64",
            })

    return parts


# ---------------------------------------------------------------------------
# Fabric API client (reuses pattern from provision_fabric.py)
# ---------------------------------------------------------------------------

class FabricClient:
    def __init__(self):
        self.credential = DefaultAzureCredential()

    def _token(self) -> str:
        return self.credential.get_token("https://api.fabric.microsoft.com/.default").token

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
        }

    def wait_for_lro(self, resp: requests.Response, label: str, timeout: int = 300):
        """Wait for a long-running operation to complete."""
        if resp.status_code == 201:
            return resp.json()
        if resp.status_code not in (200, 202):
            print(f"  ✗ {label}: {resp.status_code} — {resp.text}")
            sys.exit(1)
        if resp.status_code == 200:
            return resp.json()

        op_id = resp.headers.get("x-ms-operation-id")
        if not op_id:
            print(f"  ✗ {label}: 202 but no operation ID")
            sys.exit(1)

        retry = int(resp.headers.get("Retry-After", "5"))
        elapsed = 0
        while elapsed < timeout:
            time.sleep(retry)
            elapsed += retry
            r = requests.get(f"{FABRIC_API}/operations/{op_id}", headers=self.headers)
            if r.status_code != 200:
                continue
            status = r.json().get("status", "")
            if status == "Succeeded":
                rr = requests.get(f"{FABRIC_API}/operations/{op_id}/result", headers=self.headers)
                return rr.json() if rr.status_code == 200 else r.json()
            if status in ("Failed", "Cancelled"):
                print(f"  ✗ {label} {status}: {r.text}")
                sys.exit(1)

        print(f"  ✗ {label} timed out after {timeout}s")
        sys.exit(1)

    def find_ontology(self, workspace_id: str, name: str) -> dict | None:
        r = requests.get(
            f"{FABRIC_API}/workspaces/{workspace_id}/ontologies",
            headers=self.headers,
        )
        r.raise_for_status()
        for item in r.json().get("value", []):
            if item["displayName"] == name:
                return item
        return None

    def create_ontology(self, workspace_id: str, name: str, parts: list[dict]) -> dict:
        body = {
            "displayName": name,
            "description": "Network topology ontology for autonomous NOC demo",
            "definition": {"parts": parts},
        }
        r = requests.post(
            f"{FABRIC_API}/workspaces/{workspace_id}/ontologies",
            headers=self.headers,
            json=body,
        )
        return self.wait_for_lro(r, f"Create Ontology '{name}'")

    def update_ontology_definition(
        self, workspace_id: str, ontology_id: str, parts: list[dict]
    ) -> dict:
        body = {"definition": {"parts": parts}}
        r = requests.post(
            f"{FABRIC_API}/workspaces/{workspace_id}/ontologies/{ontology_id}/updateDefinition",
            headers=self.headers,
            json=body,
        )
        return self.wait_for_lro(r, "Update Ontology definition")

    def get_kql_cluster_uri(self, workspace_id: str) -> str | None:
        """Get the query service URI for the first KQL database in the workspace."""
        r = requests.get(
            f"{FABRIC_API}/workspaces/{workspace_id}/kqlDatabases",
            headers=self.headers,
        )
        if r.status_code != 200:
            return None
        for db in r.json().get("value", []):
            uri = db.get("properties", {}).get("queryServiceUri", "")
            if uri:
                return uri
        return None

    def find_graph_model(self, workspace_id: str, ontology_name: str) -> dict | None:
        """Find the Graph in Microsoft Fabric child item created by an ontology.

        When an ontology is created, Fabric auto-creates a graph model item
        in the same workspace. Its displayName typically matches or contains
        the ontology name.
        """
        r = requests.get(
            f"{FABRIC_API}/workspaces/{workspace_id}/items",
            headers=self.headers,
            params={"type": "GraphModel"},
        )
        if r.status_code != 200:
            # Fallback: list all items and filter
            r = requests.get(
                f"{FABRIC_API}/workspaces/{workspace_id}/items",
                headers=self.headers,
            )
            r.raise_for_status()
        for item in r.json().get("value", []):
            # Match by type and name containing ontology name
            if item.get("type") in ("GraphModel", "Graph"):
                if ontology_name.lower() in item["displayName"].lower():
                    return item
        # Fallback: return first graph item if any
        for item in r.json().get("value", []):
            if item.get("type") in ("GraphModel", "Graph"):
                return item
        return None

    def refresh_graph(self, workspace_id: str, graph_item_id: str, timeout: int = 600):
        """Trigger an on-demand graph refresh via the Job Scheduler API.

        Tries multiple job type names since the Graph item type doesn't use
        'DefaultJob'. Falls back to listing existing job instances to discover
        the correct job type.
        """
        # Try to discover the correct job type from existing job instances
        job_type = None
        r = requests.get(
            f"{FABRIC_API}/workspaces/{workspace_id}/items/{graph_item_id}/jobs/instances",
            headers=self.headers,
        )
        if r.status_code == 200:
            for inst in r.json().get("value", []):
                jt = inst.get("jobType", "")
                if jt:
                    job_type = jt
                    print(f"  Discovered job type from history: {job_type}")
                    break

        # If no history, try common job type names
        candidates = [job_type] if job_type else []
        candidates += ["Refresh", "GraphRefresh", "RunGraph", "Ingestion", "DefaultJob"]
        # Deduplicate while preserving order
        seen = set()
        candidates = [c for c in candidates if c and c not in seen and not seen.add(c)]

        for jt in candidates:
            r = requests.post(
                f"{FABRIC_API}/workspaces/{workspace_id}/items/{graph_item_id}/jobs/{jt}/instances",
                headers=self.headers,
            )
            if r.status_code == 202:
                print(f"  Job type '{jt}' accepted (202)")
                location = r.headers.get("Location", "")
                retry_after = int(r.headers.get("Retry-After", "30"))
                if location:
                    elapsed = 0
                    while elapsed < timeout:
                        time.sleep(retry_after)
                        elapsed += retry_after
                        pr = requests.get(location, headers=self.headers)
                        if pr.status_code == 200:
                            status = pr.json().get("status", "")
                            if status == "Completed":
                                return pr.json()
                            if status in ("Failed", "Cancelled"):
                                print(f"  ✗ Graph refresh {status}: {pr.text}")
                                return None
                        elif pr.status_code == 404:
                            pass
                    print(f"  ⚠ Graph refresh still running after {timeout}s — check status in portal")
                return r.headers
            elif r.status_code == 400 and "InvalidJobType" in r.text:
                continue  # Try next candidate
            elif r.status_code in (200, 201):
                return r.json() if r.text else {}
            else:
                print(f"  ✗ Job type '{jt}': {r.status_code} — {r.text}")
                return None

        print(f"  ✗ Could not find a valid job type for graph refresh")
        print(f"    Tried: {candidates}")
        print(f"    Manually refresh: Workspace → graph model → ... → Schedule → Refresh now")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Validate config
    missing = []
    if not WORKSPACE_ID:
        missing.append("FABRIC_WORKSPACE_ID")
    if not LAKEHOUSE_ID:
        missing.append("FABRIC_LAKEHOUSE_ID")
    if not EVENTHOUSE_ID:
        missing.append("FABRIC_EVENTHOUSE_ID")
    if missing:
        print(f"✗ Missing env vars: {', '.join(missing)}")
        print("  Run provision_fabric.py first and populate azure_config.env")
        sys.exit(1)

    client = FabricClient()

    print("=" * 60)
    print(f"Provisioning Fabric IQ Ontology: {ONTOLOGY_NAME}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Build static data bindings
    # ------------------------------------------------------------------
    print("\n--- Building ontology definition ---")
    bindings = build_static_bindings()
    print(f"  ✓ {sum(len(v) for v in bindings.values())} static data bindings")

    # ------------------------------------------------------------------
    # 2. Build time-series binding (optional — needs Eventhouse ingested)
    # ------------------------------------------------------------------
    # cluster_uri = client.get_kql_cluster_uri(WORKSPACE_ID)
    # db_name = KQL_DB_NAME or "NetworkTelemetryEH_3117"

    # if cluster_uri:
    #     ts_binding = build_timeseries_binding(cluster_uri, db_name)
    #     bindings.setdefault(ET_TRANSPORT_LINK, []).append(ts_binding)
    #     print(f"  ✓ Time-series binding: LinkTelemetry → TransportLink")
    #     print(f"    Cluster: {cluster_uri}")
    # else:
    #     print("  ⚠ Skipping time-series binding — KQL cluster URI not found")
    #     print("    Ingest Eventhouse data first, then re-run to add binding")

    # ------------------------------------------------------------------
    # 3. Build contextualizations (relationship bindings)
    # ------------------------------------------------------------------
    contextualizations = build_contextualizations()
    print(f"  ✓ {sum(len(v) for v in contextualizations.values())} relationship contextualizations")

    # ------------------------------------------------------------------
    # 4. Assemble definition parts
    # ------------------------------------------------------------------
    parts = build_definition_parts(bindings, contextualizations)
    print(f"  ✓ {len(parts)} definition parts total")

    # ------------------------------------------------------------------
    # 5. Create or update ontology
    # ------------------------------------------------------------------
    print(f"\n--- Creating ontology item ---")

    existing = client.find_ontology(WORKSPACE_ID, ONTOLOGY_NAME)
    if existing:
        print(f"  Ontology already exists: {existing['id']}")
        print(f"  Updating definition...")
        client.update_ontology_definition(WORKSPACE_ID, existing["id"], parts)
        ontology_id = existing["id"]
        print(f"  ✓ Ontology definition updated")
    else:
        result = client.create_ontology(WORKSPACE_ID, ONTOLOGY_NAME, parts)
        ontology_id = result.get("id", "unknown")
        print(f"  ✓ Ontology created: {ontology_id}")

    # ------------------------------------------------------------------
    # 6. Refresh the underlying graph model
    # ------------------------------------------------------------------
    print("\n--- Refreshing graph model ---")
    graph_item = client.find_graph_model(WORKSPACE_ID, ONTOLOGY_NAME)
    if graph_item:
        graph_id = graph_item["id"]
        graph_name = graph_item["displayName"]
        print(f"  Found graph model: {graph_name} ({graph_id})")
        print(f"  Triggering refresh (this may take a few minutes)...")
        result = client.refresh_graph(WORKSPACE_ID, graph_id)
        if result is not None:
            print(f"  ✓ Graph refresh completed")
        else:
            print(f"  ⚠ Graph refresh may have failed — check Fabric portal")
            print(f"    Workspace → graph model → ... → Schedule → Refresh now")
    else:
        print(f"  ⚠ Could not find graph model item in workspace")
        print(f"    Manually refresh: Workspace → graph model → ... → Schedule → Refresh now")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("✅ Ontology provisioning complete!")
    print(f"   Name       : {ONTOLOGY_NAME}")
    print(f"   ID         : {ontology_id}")
    print(f"   Workspace  : {WORKSPACE_ID}")
    print(f"   Entity types: {len(ENTITY_TYPES)}")
    print(f"     CoreRouter, TransportLink, AggSwitch, BaseStation,")
    print(f"     BGPSession, MPLSPath, Service, SLAPolicy")
    print(f"   Relationships: {len(RELATIONSHIP_TYPES)}")
    print(f"     connects_to, aggregates_to, backhauls_via, routes_via,")
    print(f"     depends_on, governed_by, peers_over")
    print("=" * 60)

    print("\n  Next steps (manual — Step 2.6):")
    print("    1. Open Fabric portal → workspace → + New item → Data agent")
    print("    2. Name: NetworkOntologyAgent")
    print("    3. Add data source → select NetworkTopologyOntology")
    print("    4. Paste instructions from data/prompts/data_agent_instructions.md")
    print("    5. Test: 'What services depend on LINK-SYD-MEL-FIBRE-01?'")
    print()


if __name__ == "__main__":
    main()
