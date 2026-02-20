"""Tool bindings for the declarative agent."""

from .graph import graph_topology_query
from .telemetry import telemetry_kql_query
from .search import search_runbooks, search_tickets
from .dispatch import dispatch_field_engineer

TOOL_BINDINGS = {
    "graph_topology_query": graph_topology_query,
    "telemetry_kql_query": telemetry_kql_query,
    "search_runbooks": search_runbooks,
    "search_tickets": search_tickets,
    "dispatch_field_engineer": dispatch_field_engineer,
}
