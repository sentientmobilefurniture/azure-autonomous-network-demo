````markdown
# Query Language: Gremlin (Azure Cosmos DB)

You construct **Gremlin** queries to explore the network topology graph. Gremlin uses a fluent, step-based traversal pattern starting from `g.V()` (vertices) or `g.E()` (edges).

## Gremlin Syntax Rules

- Start traversals with `g.V()` for vertices.
- Filter by label: `g.V().hasLabel('CoreRouter')`.
- Filter by property: `.has('RouterId', 'CORE-SYD-01')`.
- Traverse outgoing edges: `.out('connects_to')`.
- Traverse incoming edges: `.in('routes_via')`.
- Return all properties: `.valueMap(true)`.
- Chain traversals for multi-hop queries using `.as()` and `.select()`.
- **Send queries as plain text strings** — no bytecode, no lambdas.
- **Never use LOWER()** — entity IDs are case-sensitive uppercase strings.
- **Cosmos DB does not support lambdas** — use only string-based Gremlin.
- **Use `.as('alias').select('alias')` for multi-variable patterns.**

---

## Relationship Query Examples

### housed_in: CoreRouter → DataCenter

```gremlin
g.V().hasLabel('CoreRouter').has('RouterId', 'CORE-ADL-01')
  .out('housed_in').hasLabel('DataCenter')
  .valueMap(true)
```

### located_at: FirewallCluster → DataCenter

```gremlin
g.V().hasLabel('FirewallCluster').has('FirewallId', 'FW-ADL-01')
  .out('located_at').hasLabel('DataCenter')
  .valueMap(true)
```

### Reverse: what equipment is in a datacenter?

```gremlin
g.V().hasLabel('DataCenter').has('DataCenterId', 'DC-ADL-01')
  .in('housed_in').hasLabel('CoreRouter').as('r')
  .select('r').by(valueMap(true))
```

### connects_to: TransportLink → CoreRouter

```gremlin
g.V().hasLabel('TransportLink').has('LinkId', 'LINK-ADL-PER-SUBMARINE-01')
  .out('connects_to').hasLabel('CoreRouter')
  .valueMap(true)
```

### aggregates_to: AggSwitch → CoreRouter

```gremlin
g.V().hasLabel('CoreRouter').has('RouterId', 'CORE-ADL-01')
  .in('aggregates_to').hasLabel('AggSwitch')
  .valueMap(true)
```

### backhauls_via: BaseStation → AggSwitch

```gremlin
g.V().hasLabel('AggSwitch').has('SwitchId', 'AGG-ADL-SOUTH-01')
  .in('backhauls_via').hasLabel('BaseStation')
  .valueMap(true)
```

### routes_via: MPLSPath → TransportLink

```gremlin
g.V().hasLabel('TransportLink').has('LinkId', 'LINK-ADL-PER-SUBMARINE-01')
  .in('routes_via').hasLabel('MPLSPath')
  .valueMap(true)
```

### traverses: MPLSPath → CoreRouter

```gremlin
g.V().hasLabel('MPLSPath').has('PathId', 'MPLS-PATH-ADL-PER-PRIMARY')
  .out('traverses').hasLabel('CoreRouter')
  .valueMap(true)
```

### depends_on: Service → MPLSPath

```gremlin
g.V().hasLabel('MPLSPath').has('PathId', 'MPLS-PATH-ADL-PER-PRIMARY')
  .in('depends_on').hasLabel('Service')
  .valueMap(true)
```

### protects: FirewallCluster → Service

```gremlin
g.V().hasLabel('Service').has('ServiceId', 'VPN-IRONORE-CORP')
  .in('protects').hasLabel('FirewallCluster')
  .valueMap(true)
```

### governed_by: SLAPolicy → Service

```gremlin
g.V().hasLabel('Service').has('ServiceId', 'VPN-IRONORE-CORP')
  .in('governed_by').hasLabel('SLAPolicy')
  .valueMap(true)
```

### peers_over: BGPSession → CoreRouter

```gremlin
g.V().hasLabel('CoreRouter').has('RouterId', 'CORE-ADL-01')
  .in('peers_over').hasLabel('BGPSession')
  .valueMap(true)
```

---

## Common Multi-Hop Query Patterns

### 2-hop: link failure → affected paths and services

```gremlin
g.V().hasLabel('TransportLink').has('LinkId', 'LINK-ADL-PER-SUBMARINE-01')
  .in('routes_via').hasLabel('MPLSPath').as('mp')
  .in('depends_on').hasLabel('Service').as('svc')
  .select('mp', 'svc').by(valueMap(true))
```

### 3-hop: full blast radius with SLA exposure

```gremlin
g.V().hasLabel('TransportLink').has('LinkId', 'LINK-ADL-PER-SUBMARINE-01')
  .in('routes_via').hasLabel('MPLSPath').as('mp')
  .in('depends_on').hasLabel('Service').as('svc')
  .in('governed_by').hasLabel('SLAPolicy').as('sla')
  .select('mp', 'svc', 'sla').by(valueMap(true))
```

### 2-hop: router → switches → base stations

```gremlin
g.V().hasLabel('CoreRouter').has('RouterId', 'CORE-ADL-01')
  .in('aggregates_to').hasLabel('AggSwitch').as('agg')
  .in('backhauls_via').hasLabel('BaseStation').as('bs')
  .select('agg', 'bs').by(valueMap(true))
```

### 2-hop: datacenter → routers → links

```gremlin
g.V().hasLabel('DataCenter').has('DataCenterId', 'DC-ADL-01')
  .in('housed_in').hasLabel('CoreRouter').as('r')
  .in('connects_to').hasLabel('TransportLink').as('link')
  .select('r', 'link').by(valueMap(true))
```

### 2-hop: firewall → services → SLAs

```gremlin
g.V().hasLabel('FirewallCluster').has('FirewallId', 'FW-PER-01')
  .out('protects').hasLabel('Service').as('svc')
  .in('governed_by').hasLabel('SLAPolicy').as('sla')
  .select('svc', 'sla').by(valueMap(true))
```

### Count vertices by label

```gremlin
g.V().groupCount().by(label)
```

### Get all datacenters

```gremlin
g.V().hasLabel('DataCenter').valueMap(true)
```

### Get all core routers

```gremlin
g.V().hasLabel('CoreRouter').valueMap(true)
```

### Get all MPLS paths with type

```gremlin
g.V().hasLabel('MPLSPath').valueMap(true)
```

````
