"""
Mock graph backend — static responses for offline/disconnected demos.

Set GRAPH_BACKEND=mock to select this backend. Returns canned topology
data without any external dependency.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("graph-query-api")

# ---------------------------------------------------------------------------
# Canned topology data (subset of the full ontology)
# ---------------------------------------------------------------------------

_CORE_ROUTERS = [
    {"RouterId": "CORE-SYD-01", "City": "Sydney", "Region": "NSW", "Vendor": "Cisco", "Model": "ASR-9922"},
    {"RouterId": "CORE-MEL-01", "City": "Melbourne", "Region": "VIC", "Vendor": "Cisco", "Model": "ASR-9922"},
    {"RouterId": "CORE-BNE-01", "City": "Brisbane", "Region": "QLD", "Vendor": "Juniper", "Model": "MX10008"},
]

_CORE_ROUTER_COLUMNS = [
    {"name": "RouterId", "type": "string"},
    {"name": "City", "type": "string"},
    {"name": "Region", "type": "string"},
    {"name": "Vendor", "type": "string"},
    {"name": "Model", "type": "string"},
]


# ---------------------------------------------------------------------------
# Full topology data for graph viewer (used by get_topology)
# ---------------------------------------------------------------------------

_TOPOLOGY_NODES: list[dict] = [
    # CoreRouters
    {"id": "CORE-SYD-01", "label": "CoreRouter", "properties": {"RouterId": "CORE-SYD-01", "City": "Sydney", "Region": "NSW", "Vendor": "Cisco", "Model": "ASR-9922"}},
    {"id": "CORE-MEL-01", "label": "CoreRouter", "properties": {"RouterId": "CORE-MEL-01", "City": "Melbourne", "Region": "VIC", "Vendor": "Cisco", "Model": "ASR-9922"}},
    {"id": "CORE-BNE-01", "label": "CoreRouter", "properties": {"RouterId": "CORE-BNE-01", "City": "Brisbane", "Region": "QLD", "Vendor": "Juniper", "Model": "MX10008"}},
    # AggSwitches
    {"id": "AGG-SYD-NORTH-01", "label": "AggSwitch", "properties": {"SwitchId": "AGG-SYD-NORTH-01", "City": "Sydney", "UplinkRouterId": "CORE-SYD-01"}},
    {"id": "AGG-SYD-SOUTH-01", "label": "AggSwitch", "properties": {"SwitchId": "AGG-SYD-SOUTH-01", "City": "Sydney", "UplinkRouterId": "CORE-SYD-01"}},
    {"id": "AGG-MEL-EAST-01", "label": "AggSwitch", "properties": {"SwitchId": "AGG-MEL-EAST-01", "City": "Melbourne", "UplinkRouterId": "CORE-MEL-01"}},
    {"id": "AGG-MEL-WEST-01", "label": "AggSwitch", "properties": {"SwitchId": "AGG-MEL-WEST-01", "City": "Melbourne", "UplinkRouterId": "CORE-MEL-01"}},
    {"id": "AGG-BNE-CENTRAL-01", "label": "AggSwitch", "properties": {"SwitchId": "AGG-BNE-CENTRAL-01", "City": "Brisbane", "UplinkRouterId": "CORE-BNE-01"}},
    {"id": "AGG-BNE-SOUTH-01", "label": "AggSwitch", "properties": {"SwitchId": "AGG-BNE-SOUTH-01", "City": "Brisbane", "UplinkRouterId": "CORE-BNE-01"}},
    # BaseStations
    {"id": "GNB-SYD-2041", "label": "BaseStation", "properties": {"StationId": "GNB-SYD-2041", "StationType": "5G_NR", "AggSwitchId": "AGG-SYD-NORTH-01", "City": "Sydney"}},
    {"id": "GNB-SYD-2042", "label": "BaseStation", "properties": {"StationId": "GNB-SYD-2042", "StationType": "5G_NR", "AggSwitchId": "AGG-SYD-NORTH-01", "City": "Sydney"}},
    {"id": "GNB-SYD-2043", "label": "BaseStation", "properties": {"StationId": "GNB-SYD-2043", "StationType": "5G_NR", "AggSwitchId": "AGG-SYD-SOUTH-01", "City": "Sydney"}},
    {"id": "GNB-MEL-3011", "label": "BaseStation", "properties": {"StationId": "GNB-MEL-3011", "StationType": "5G_NR", "AggSwitchId": "AGG-MEL-EAST-01", "City": "Melbourne"}},
    {"id": "GNB-MEL-3012", "label": "BaseStation", "properties": {"StationId": "GNB-MEL-3012", "StationType": "5G_NR", "AggSwitchId": "AGG-MEL-EAST-01", "City": "Melbourne"}},
    {"id": "GNB-MEL-3021", "label": "BaseStation", "properties": {"StationId": "GNB-MEL-3021", "StationType": "5G_NR", "AggSwitchId": "AGG-MEL-WEST-01", "City": "Melbourne"}},
    {"id": "GNB-BNE-4011", "label": "BaseStation", "properties": {"StationId": "GNB-BNE-4011", "StationType": "5G_NR", "AggSwitchId": "AGG-BNE-CENTRAL-01", "City": "Brisbane"}},
    {"id": "GNB-BNE-4012", "label": "BaseStation", "properties": {"StationId": "GNB-BNE-4012", "StationType": "5G_NR", "AggSwitchId": "AGG-BNE-SOUTH-01", "City": "Brisbane"}},
    # TransportLinks
    {"id": "LINK-SYD-MEL-FIBRE-01", "label": "TransportLink", "properties": {"LinkId": "LINK-SYD-MEL-FIBRE-01", "LinkType": "DWDM_100G", "CapacityGbps": "100", "SourceRouterId": "CORE-SYD-01", "TargetRouterId": "CORE-MEL-01"}},
    {"id": "LINK-SYD-MEL-FIBRE-02", "label": "TransportLink", "properties": {"LinkId": "LINK-SYD-MEL-FIBRE-02", "LinkType": "DWDM_100G", "CapacityGbps": "100", "SourceRouterId": "CORE-SYD-01", "TargetRouterId": "CORE-MEL-01"}},
    {"id": "LINK-SYD-BNE-FIBRE-01", "label": "TransportLink", "properties": {"LinkId": "LINK-SYD-BNE-FIBRE-01", "LinkType": "DWDM_100G", "CapacityGbps": "100", "SourceRouterId": "CORE-SYD-01", "TargetRouterId": "CORE-BNE-01"}},
    {"id": "LINK-MEL-BNE-FIBRE-01", "label": "TransportLink", "properties": {"LinkId": "LINK-MEL-BNE-FIBRE-01", "LinkType": "DWDM_100G", "CapacityGbps": "100", "SourceRouterId": "CORE-MEL-01", "TargetRouterId": "CORE-BNE-01"}},
    {"id": "LINK-SYD-AGG-NORTH-01", "label": "TransportLink", "properties": {"LinkId": "LINK-SYD-AGG-NORTH-01", "LinkType": "100GE", "CapacityGbps": "100", "SourceRouterId": "CORE-SYD-01", "TargetRouterId": "CORE-SYD-01"}},
    {"id": "LINK-SYD-AGG-SOUTH-01", "label": "TransportLink", "properties": {"LinkId": "LINK-SYD-AGG-SOUTH-01", "LinkType": "100GE", "CapacityGbps": "100", "SourceRouterId": "CORE-SYD-01", "TargetRouterId": "CORE-SYD-01"}},
    {"id": "LINK-MEL-AGG-EAST-01", "label": "TransportLink", "properties": {"LinkId": "LINK-MEL-AGG-EAST-01", "LinkType": "100GE", "CapacityGbps": "100", "SourceRouterId": "CORE-MEL-01", "TargetRouterId": "CORE-MEL-01"}},
    {"id": "LINK-MEL-AGG-WEST-01", "label": "TransportLink", "properties": {"LinkId": "LINK-MEL-AGG-WEST-01", "LinkType": "100GE", "CapacityGbps": "100", "SourceRouterId": "CORE-MEL-01", "TargetRouterId": "CORE-MEL-01"}},
    {"id": "LINK-BNE-AGG-CENTRAL-01", "label": "TransportLink", "properties": {"LinkId": "LINK-BNE-AGG-CENTRAL-01", "LinkType": "100GE", "CapacityGbps": "100", "SourceRouterId": "CORE-BNE-01", "TargetRouterId": "CORE-BNE-01"}},
    {"id": "LINK-BNE-AGG-SOUTH-01", "label": "TransportLink", "properties": {"LinkId": "LINK-BNE-AGG-SOUTH-01", "LinkType": "100GE", "CapacityGbps": "100", "SourceRouterId": "CORE-BNE-01", "TargetRouterId": "CORE-BNE-01"}},
    # MPLSPaths
    {"id": "MPLS-PATH-SYD-MEL-PRIMARY", "label": "MPLSPath", "properties": {"PathId": "MPLS-PATH-SYD-MEL-PRIMARY", "PathType": "PRIMARY"}},
    {"id": "MPLS-PATH-SYD-MEL-SECONDARY", "label": "MPLSPath", "properties": {"PathId": "MPLS-PATH-SYD-MEL-SECONDARY", "PathType": "SECONDARY"}},
    {"id": "MPLS-PATH-SYD-BNE-PRIMARY", "label": "MPLSPath", "properties": {"PathId": "MPLS-PATH-SYD-BNE-PRIMARY", "PathType": "PRIMARY"}},
    {"id": "MPLS-PATH-MEL-BNE-PRIMARY", "label": "MPLSPath", "properties": {"PathId": "MPLS-PATH-MEL-BNE-PRIMARY", "PathType": "PRIMARY"}},
    {"id": "MPLS-PATH-SYD-MEL-VIA-BNE", "label": "MPLSPath", "properties": {"PathId": "MPLS-PATH-SYD-MEL-VIA-BNE", "PathType": "TERTIARY"}},
    # Services
    {"id": "VPN-ACME-CORP", "label": "Service", "properties": {"ServiceId": "VPN-ACME-CORP", "ServiceType": "EnterpriseVPN", "CustomerName": "ACME Corporation", "CustomerCount": "1", "ActiveUsers": "450"}},
    {"id": "VPN-BIGBANK", "label": "Service", "properties": {"ServiceId": "VPN-BIGBANK", "ServiceType": "EnterpriseVPN", "CustomerName": "BigBank Financial", "CustomerCount": "1", "ActiveUsers": "1200"}},
    {"id": "VPN-OZMINE", "label": "Service", "properties": {"ServiceId": "VPN-OZMINE", "ServiceType": "EnterpriseVPN", "CustomerName": "OzMine Resources", "CustomerCount": "1", "ActiveUsers": "680"}},
    {"id": "BB-BUNDLE-SYD-NORTH", "label": "Service", "properties": {"ServiceId": "BB-BUNDLE-SYD-NORTH", "ServiceType": "Broadband", "CustomerName": "Residential - Sydney North", "CustomerCount": "3200", "ActiveUsers": "3200"}},
    {"id": "BB-BUNDLE-MEL-EAST", "label": "Service", "properties": {"ServiceId": "BB-BUNDLE-MEL-EAST", "ServiceType": "Broadband", "CustomerName": "Residential - Melbourne East", "CustomerCount": "2800", "ActiveUsers": "2800"}},
    {"id": "BB-BUNDLE-BNE-CENTRAL", "label": "Service", "properties": {"ServiceId": "BB-BUNDLE-BNE-CENTRAL", "ServiceType": "Broadband", "CustomerName": "Residential - Brisbane Central", "CustomerCount": "2400", "ActiveUsers": "2400"}},
    {"id": "MOB-5G-SYD-2041", "label": "Service", "properties": {"ServiceId": "MOB-5G-SYD-2041", "ServiceType": "Mobile5G", "CustomerName": "Mobile Subscribers - SYD 2041", "CustomerCount": "4200", "ActiveUsers": "4200"}},
    {"id": "MOB-5G-SYD-2042", "label": "Service", "properties": {"ServiceId": "MOB-5G-SYD-2042", "ServiceType": "Mobile5G", "CustomerName": "Mobile Subscribers - SYD 2042", "CustomerCount": "4300", "ActiveUsers": "4300"}},
    {"id": "MOB-5G-MEL-3011", "label": "Service", "properties": {"ServiceId": "MOB-5G-MEL-3011", "ServiceType": "Mobile5G", "CustomerName": "Mobile Subscribers - MEL 3011", "CustomerCount": "3800", "ActiveUsers": "3800"}},
    {"id": "MOB-5G-BNE-4011", "label": "Service", "properties": {"ServiceId": "MOB-5G-BNE-4011", "ServiceType": "Mobile5G", "CustomerName": "Mobile Subscribers - BNE 4011", "CustomerCount": "3600", "ActiveUsers": "3600"}},
    # SLAPolicies
    {"id": "SLA-ACME-GOLD", "label": "SLAPolicy", "properties": {"SLAPolicyId": "SLA-ACME-GOLD", "ServiceId": "VPN-ACME-CORP", "AvailabilityPct": "99.99", "MaxLatencyMs": "15", "PenaltyPerHourUSD": "50000", "Tier": "GOLD"}},
    {"id": "SLA-BIGBANK-SILVER", "label": "SLAPolicy", "properties": {"SLAPolicyId": "SLA-BIGBANK-SILVER", "ServiceId": "VPN-BIGBANK", "AvailabilityPct": "99.95", "MaxLatencyMs": "20", "PenaltyPerHourUSD": "25000", "Tier": "SILVER"}},
    {"id": "SLA-OZMINE-GOLD", "label": "SLAPolicy", "properties": {"SLAPolicyId": "SLA-OZMINE-GOLD", "ServiceId": "VPN-OZMINE", "AvailabilityPct": "99.99", "MaxLatencyMs": "18", "PenaltyPerHourUSD": "40000", "Tier": "GOLD"}},
    {"id": "SLA-BB-SYD-STANDARD", "label": "SLAPolicy", "properties": {"SLAPolicyId": "SLA-BB-SYD-STANDARD", "ServiceId": "BB-BUNDLE-SYD-NORTH", "AvailabilityPct": "99.5", "MaxLatencyMs": "50", "PenaltyPerHourUSD": "0", "Tier": "STANDARD"}},
    {"id": "SLA-BB-BNE-STANDARD", "label": "SLAPolicy", "properties": {"SLAPolicyId": "SLA-BB-BNE-STANDARD", "ServiceId": "BB-BUNDLE-BNE-CENTRAL", "AvailabilityPct": "99.5", "MaxLatencyMs": "50", "PenaltyPerHourUSD": "0", "Tier": "STANDARD"}},
    # BGPSessions
    {"id": "BGP-SYD-MEL-01", "label": "BGPSession", "properties": {"SessionId": "BGP-SYD-MEL-01", "PeerARouterId": "CORE-SYD-01", "PeerBRouterId": "CORE-MEL-01", "ASNumberA": "64512", "ASNumberB": "64513"}},
    {"id": "BGP-SYD-BNE-01", "label": "BGPSession", "properties": {"SessionId": "BGP-SYD-BNE-01", "PeerARouterId": "CORE-SYD-01", "PeerBRouterId": "CORE-BNE-01", "ASNumberA": "64512", "ASNumberB": "64514"}},
    {"id": "BGP-MEL-BNE-01", "label": "BGPSession", "properties": {"SessionId": "BGP-MEL-BNE-01", "PeerARouterId": "CORE-MEL-01", "PeerBRouterId": "CORE-BNE-01", "ASNumberA": "64513", "ASNumberB": "64514"}},
]

_TOPOLOGY_EDGES: list[dict] = [
    # connects_to: TransportLink → CoreRouter (source side)
    {"id": "e-ct-FIBRE01-SYD", "source": "LINK-SYD-MEL-FIBRE-01", "target": "CORE-SYD-01", "label": "connects_to", "properties": {"direction": "source"}},
    {"id": "e-ct-FIBRE01-MEL", "source": "LINK-SYD-MEL-FIBRE-01", "target": "CORE-MEL-01", "label": "connects_to", "properties": {"direction": "target"}},
    {"id": "e-ct-FIBRE02-SYD", "source": "LINK-SYD-MEL-FIBRE-02", "target": "CORE-SYD-01", "label": "connects_to", "properties": {"direction": "source"}},
    {"id": "e-ct-FIBRE02-MEL", "source": "LINK-SYD-MEL-FIBRE-02", "target": "CORE-MEL-01", "label": "connects_to", "properties": {"direction": "target"}},
    {"id": "e-ct-BNE01-SYD", "source": "LINK-SYD-BNE-FIBRE-01", "target": "CORE-SYD-01", "label": "connects_to", "properties": {"direction": "source"}},
    {"id": "e-ct-BNE01-BNE", "source": "LINK-SYD-BNE-FIBRE-01", "target": "CORE-BNE-01", "label": "connects_to", "properties": {"direction": "target"}},
    {"id": "e-ct-MELBNE01-MEL", "source": "LINK-MEL-BNE-FIBRE-01", "target": "CORE-MEL-01", "label": "connects_to", "properties": {"direction": "source"}},
    {"id": "e-ct-MELBNE01-BNE", "source": "LINK-MEL-BNE-FIBRE-01", "target": "CORE-BNE-01", "label": "connects_to", "properties": {"direction": "target"}},
    # aggregates_to: AggSwitch → CoreRouter
    {"id": "e-ag-SYDN01", "source": "AGG-SYD-NORTH-01", "target": "CORE-SYD-01", "label": "aggregates_to", "properties": {}},
    {"id": "e-ag-SYDS01", "source": "AGG-SYD-SOUTH-01", "target": "CORE-SYD-01", "label": "aggregates_to", "properties": {}},
    {"id": "e-ag-MELE01", "source": "AGG-MEL-EAST-01", "target": "CORE-MEL-01", "label": "aggregates_to", "properties": {}},
    {"id": "e-ag-MELW01", "source": "AGG-MEL-WEST-01", "target": "CORE-MEL-01", "label": "aggregates_to", "properties": {}},
    {"id": "e-ag-BNEC01", "source": "AGG-BNE-CENTRAL-01", "target": "CORE-BNE-01", "label": "aggregates_to", "properties": {}},
    {"id": "e-ag-BNES01", "source": "AGG-BNE-SOUTH-01", "target": "CORE-BNE-01", "label": "aggregates_to", "properties": {}},
    # backhauls_via: BaseStation → AggSwitch
    {"id": "e-bh-2041", "source": "GNB-SYD-2041", "target": "AGG-SYD-NORTH-01", "label": "backhauls_via", "properties": {}},
    {"id": "e-bh-2042", "source": "GNB-SYD-2042", "target": "AGG-SYD-NORTH-01", "label": "backhauls_via", "properties": {}},
    {"id": "e-bh-2043", "source": "GNB-SYD-2043", "target": "AGG-SYD-SOUTH-01", "label": "backhauls_via", "properties": {}},
    {"id": "e-bh-3011", "source": "GNB-MEL-3011", "target": "AGG-MEL-EAST-01", "label": "backhauls_via", "properties": {}},
    {"id": "e-bh-3012", "source": "GNB-MEL-3012", "target": "AGG-MEL-EAST-01", "label": "backhauls_via", "properties": {}},
    {"id": "e-bh-3021", "source": "GNB-MEL-3021", "target": "AGG-MEL-WEST-01", "label": "backhauls_via", "properties": {}},
    {"id": "e-bh-4011", "source": "GNB-BNE-4011", "target": "AGG-BNE-CENTRAL-01", "label": "backhauls_via", "properties": {}},
    {"id": "e-bh-4012", "source": "GNB-BNE-4012", "target": "AGG-BNE-SOUTH-01", "label": "backhauls_via", "properties": {}},
    # routes_via: MPLSPath → TransportLink
    {"id": "e-rv-P1-F01", "source": "MPLS-PATH-SYD-MEL-PRIMARY", "target": "LINK-SYD-MEL-FIBRE-01", "label": "routes_via", "properties": {"HopOrder": "2"}},
    {"id": "e-rv-P2-F02", "source": "MPLS-PATH-SYD-MEL-SECONDARY", "target": "LINK-SYD-MEL-FIBRE-02", "label": "routes_via", "properties": {"HopOrder": "2"}},
    {"id": "e-rv-P3-BNE01", "source": "MPLS-PATH-SYD-BNE-PRIMARY", "target": "LINK-SYD-BNE-FIBRE-01", "label": "routes_via", "properties": {"HopOrder": "2"}},
    {"id": "e-rv-P4-MELBNE01", "source": "MPLS-PATH-MEL-BNE-PRIMARY", "target": "LINK-MEL-BNE-FIBRE-01", "label": "routes_via", "properties": {"HopOrder": "2"}},
    {"id": "e-rv-P5-BNE01", "source": "MPLS-PATH-SYD-MEL-VIA-BNE", "target": "LINK-SYD-BNE-FIBRE-01", "label": "routes_via", "properties": {"HopOrder": "2"}},
    {"id": "e-rv-P5-MELBNE01", "source": "MPLS-PATH-SYD-MEL-VIA-BNE", "target": "LINK-MEL-BNE-FIBRE-01", "label": "routes_via", "properties": {"HopOrder": "4"}},
    # depends_on: Service → MPLSPath / AggSwitch / BaseStation
    {"id": "e-do-ACME-P1", "source": "VPN-ACME-CORP", "target": "MPLS-PATH-SYD-MEL-PRIMARY", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    {"id": "e-do-ACME-P2", "source": "VPN-ACME-CORP", "target": "MPLS-PATH-SYD-MEL-SECONDARY", "label": "depends_on", "properties": {"DependencyStrength": "SECONDARY"}},
    {"id": "e-do-ACME-P5", "source": "VPN-ACME-CORP", "target": "MPLS-PATH-SYD-MEL-VIA-BNE", "label": "depends_on", "properties": {"DependencyStrength": "TERTIARY"}},
    {"id": "e-do-BIGB-P1", "source": "VPN-BIGBANK", "target": "MPLS-PATH-SYD-MEL-PRIMARY", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    {"id": "e-do-BIGB-P2", "source": "VPN-BIGBANK", "target": "MPLS-PATH-SYD-MEL-SECONDARY", "label": "depends_on", "properties": {"DependencyStrength": "SECONDARY"}},
    {"id": "e-do-BIGB-P5", "source": "VPN-BIGBANK", "target": "MPLS-PATH-SYD-MEL-VIA-BNE", "label": "depends_on", "properties": {"DependencyStrength": "TERTIARY"}},
    {"id": "e-do-OZMINE-P3", "source": "VPN-OZMINE", "target": "MPLS-PATH-SYD-BNE-PRIMARY", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    {"id": "e-do-OZMINE-P5", "source": "VPN-OZMINE", "target": "MPLS-PATH-SYD-MEL-VIA-BNE", "label": "depends_on", "properties": {"DependencyStrength": "SECONDARY"}},
    {"id": "e-do-BBSYD-AGG", "source": "BB-BUNDLE-SYD-NORTH", "target": "AGG-SYD-NORTH-01", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    {"id": "e-do-BBMEL-AGG", "source": "BB-BUNDLE-MEL-EAST", "target": "AGG-MEL-EAST-01", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    {"id": "e-do-BBBNE-AGG", "source": "BB-BUNDLE-BNE-CENTRAL", "target": "AGG-BNE-CENTRAL-01", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    {"id": "e-do-MOB2041", "source": "MOB-5G-SYD-2041", "target": "GNB-SYD-2041", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    {"id": "e-do-MOB2042", "source": "MOB-5G-SYD-2042", "target": "GNB-SYD-2042", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    {"id": "e-do-MOB3011", "source": "MOB-5G-MEL-3011", "target": "GNB-MEL-3011", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    {"id": "e-do-MOB4011", "source": "MOB-5G-BNE-4011", "target": "GNB-BNE-4011", "label": "depends_on", "properties": {"DependencyStrength": "PRIMARY"}},
    # governed_by: SLAPolicy → Service
    {"id": "e-gb-ACME", "source": "SLA-ACME-GOLD", "target": "VPN-ACME-CORP", "label": "governed_by", "properties": {}},
    {"id": "e-gb-BIGB", "source": "SLA-BIGBANK-SILVER", "target": "VPN-BIGBANK", "label": "governed_by", "properties": {}},
    {"id": "e-gb-OZMINE", "source": "SLA-OZMINE-GOLD", "target": "VPN-OZMINE", "label": "governed_by", "properties": {}},
    {"id": "e-gb-BBSYD", "source": "SLA-BB-SYD-STANDARD", "target": "BB-BUNDLE-SYD-NORTH", "label": "governed_by", "properties": {}},
    {"id": "e-gb-BBBNE", "source": "SLA-BB-BNE-STANDARD", "target": "BB-BUNDLE-BNE-CENTRAL", "label": "governed_by", "properties": {}},
    # peers_over: BGPSession → CoreRouter (both peers)
    {"id": "e-po-SYDMEL-A", "source": "BGP-SYD-MEL-01", "target": "CORE-SYD-01", "label": "peers_over", "properties": {"ASNumber": "64512"}},
    {"id": "e-po-SYDMEL-B", "source": "BGP-SYD-MEL-01", "target": "CORE-MEL-01", "label": "peers_over", "properties": {"ASNumber": "64513"}},
    {"id": "e-po-SYDBNE-A", "source": "BGP-SYD-BNE-01", "target": "CORE-SYD-01", "label": "peers_over", "properties": {"ASNumber": "64512"}},
    {"id": "e-po-SYDBNE-B", "source": "BGP-SYD-BNE-01", "target": "CORE-BNE-01", "label": "peers_over", "properties": {"ASNumber": "64514"}},
    {"id": "e-po-MELBNE-A", "source": "BGP-MEL-BNE-01", "target": "CORE-MEL-01", "label": "peers_over", "properties": {"ASNumber": "64513"}},
    {"id": "e-po-MELBNE-B", "source": "BGP-MEL-BNE-01", "target": "CORE-BNE-01", "label": "peers_over", "properties": {"ASNumber": "64514"}},
]


class MockGraphBackend:
    """Graph backend returning static topology data for offline demos."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Return static topology data for any query.

        Pattern-matches a few common queries; returns a generic info
        row for anything unrecognised.
        """
        q_lower = query.lower()
        logger.info("Mock backend received query: %.200s", query)

        # Simple pattern matching for common demo queries
        if "corerouter" in q_lower or "core router" in q_lower or "all routers" in q_lower:
            return {"columns": _CORE_ROUTER_COLUMNS, "data": _CORE_ROUTERS}

        # Default: echo the query back
        return {
            "columns": [{"name": "info", "type": "string"}],
            "data": [{"info": f"Mock backend received query: {query[:200]}"}],
        }

    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Return full or filtered static topology data."""
        logger.info("Mock get_topology — vertex_labels=%s", vertex_labels)
        nodes = _TOPOLOGY_NODES
        edges = _TOPOLOGY_EDGES

        if vertex_labels:
            label_set = set(vertex_labels)
            nodes = [n for n in nodes if n["label"] in label_set]
            node_ids = {n["id"] for n in nodes}
            edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

        return {"nodes": nodes, "edges": edges}

    async def ingest(self, vertices, edges, **kwargs):
        """Mock ingest — just return counts without storing."""
        return {"vertices_loaded": len(vertices), "edges_loaded": len(edges), "errors": []}

    def close(self) -> None:
        pass
