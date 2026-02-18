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

### connects_to: TransportLink → CoreRouter

```gremlin
g.V().hasLabel('TransportLink').has('LinkId', 'LINK-SYD-MEL-FIBRE-01')
  .out('connects_to').hasLabel('CoreRouter')
  .valueMap(true)
```

### aggregates_to: AggSwitch → CoreRouter

```gremlin
g.V().hasLabel('CoreRouter').has('RouterId', 'CORE-SYD-01')
  .in('aggregates_to').hasLabel('AggSwitch')
  .valueMap(true)
```

### backhauls_via: BaseStation → AggSwitch

```gremlin
g.V().hasLabel('AggSwitch').has('SwitchId', 'AGG-MEL-EAST-01')
  .in('backhauls_via').hasLabel('BaseStation')
  .valueMap(true)
```

### routes_via: MPLSPath → TransportLink

```gremlin
g.V().hasLabel('TransportLink').has('LinkId', 'LINK-SYD-MEL-FIBRE-01')
  .in('routes_via').hasLabel('MPLSPath')
  .valueMap(true)
```

### depends_on_mplspath: Service → MPLSPath

```gremlin
g.V().hasLabel('MPLSPath').has('PathId', 'MPLS-PATH-SYD-MEL-PRIMARY')
  .in('depends_on_mplspath').hasLabel('Service')
  .valueMap(true)
```

### depends_on_aggswitch: Service → AggSwitch

```gremlin
g.V().hasLabel('AggSwitch').has('SwitchId', 'AGG-SYD-NORTH-01')
  .in('depends_on_aggswitch').hasLabel('Service')
  .valueMap(true)
```

### depends_on_basestation: Service → BaseStation

```gremlin
g.V().hasLabel('BaseStation').has('StationId', 'GNB-SYD-2041')
  .in('depends_on_basestation').hasLabel('Service')
  .valueMap(true)
```

### governed_by: SLAPolicy → Service

```gremlin
g.V().hasLabel('Service').has('ServiceId', 'VPN-ACME-CORP')
  .in('governed_by').hasLabel('SLAPolicy')
  .valueMap(true)
```

### peers_over: BGPSession → CoreRouter

```gremlin
g.V().hasLabel('CoreRouter').has('RouterId', 'CORE-SYD-01')
  .in('peers_over').hasLabel('BGPSession')
  .valueMap(true)
```

---

## Common Multi-Hop Query Patterns

### 2-hop: link failure → affected paths and services

```gremlin
g.V().hasLabel('TransportLink').has('LinkId', 'LINK-SYD-MEL-FIBRE-01')
  .in('routes_via').hasLabel('MPLSPath').as('mp')
  .in('depends_on_mplspath').hasLabel('Service').as('svc')
  .select('mp', 'svc').by(valueMap(true))
```

### 3-hop: full blast radius with SLA exposure

```gremlin
g.V().hasLabel('TransportLink').has('LinkId', 'LINK-SYD-MEL-FIBRE-01')
  .in('routes_via').hasLabel('MPLSPath').as('mp')
  .in('depends_on_mplspath').hasLabel('Service').as('svc')
  .in('governed_by').hasLabel('SLAPolicy').as('sla')
  .select('mp', 'svc', 'sla').by(valueMap(true))
```

### 2-hop: router → switches → base stations

```gremlin
g.V().hasLabel('CoreRouter').has('RouterId', 'CORE-SYD-01')
  .in('aggregates_to').hasLabel('AggSwitch').as('agg')
  .in('backhauls_via').hasLabel('BaseStation').as('bs')
  .select('agg', 'bs').by(valueMap(true))
```

### Count vertices by label

```gremlin
g.V().groupCount().by(label)
```

### Get all core routers

```gremlin
g.V().hasLabel('CoreRouter').valueMap(true)
```
