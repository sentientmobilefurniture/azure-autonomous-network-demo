# Query Language: Gremlin (Azure Cosmos DB)

You construct **Gremlin** queries to explore the cloud infrastructure topology graph. Gremlin uses a fluent, step-based traversal pattern starting from `g.V()` (vertices) or `g.E()` (edges).

## Gremlin Syntax Rules

- Start traversals with `g.V()` for vertices.
- Filter by label: `g.V().hasLabel('Host')`.
- Filter by property: `.has('HostId', 'HOST-USE-A-01-01')`.
- Traverse outgoing edges: `.out('runs')`.
- Traverse incoming edges: `.in('hosts_server')`.
- Return all properties: `.valueMap(true)`.
- Chain traversals for multi-hop queries using `.as()` and `.select()`.
- **Send queries as plain text strings** — no bytecode, no lambdas.
- **Never use LOWER()** — entity IDs are case-sensitive uppercase strings.
- **Cosmos DB does not support lambdas** — use only string-based Gremlin.
- **Use `.as('alias').select('alias')` for multi-variable patterns.**

---

## Relationship Query Examples

### has_zone: Region → AvailabilityZone

```gremlin
g.V().hasLabel('Region').has('RegionId', 'REGION-US-EAST')
  .out('has_zone').hasLabel('AvailabilityZone')
  .valueMap(true)
```

### has_rack: AvailabilityZone → Rack

```gremlin
g.V().hasLabel('AvailabilityZone').has('AZId', 'AZ-US-EAST-A')
  .out('has_rack').hasLabel('Rack')
  .valueMap(true)
```

### hosts_server: Rack → Host

```gremlin
g.V().hasLabel('Rack').has('RackId', 'RACK-US-EAST-A-01')
  .out('hosts_server').hasLabel('Host')
  .valueMap(true)
```

### runs: Host → VirtualMachine

```gremlin
g.V().hasLabel('Host').has('HostId', 'HOST-USE-A-01-01')
  .out('runs').hasLabel('VirtualMachine')
  .valueMap(true)
```

### serves: VirtualMachine → Service

```gremlin
g.V().hasLabel('VirtualMachine').has('VMId', 'VM-USE-A-0101-01')
  .out('serves').hasLabel('Service')
  .valueMap(true)
```

### governs: SLAPolicy → Service

```gremlin
g.V().hasLabel('Service').has('ServiceId', 'SVC-ECOMMERCE-WEB')
  .in('governs').hasLabel('SLAPolicy')
  .valueMap(true)
```

### depends_on: Service → Service

```gremlin
g.V().hasLabel('Service').has('ServiceId', 'SVC-ECOMMERCE-WEB')
  .out('depends_on').hasLabel('Service')
  .valueMap(true)
```

### depends_on: Service → LoadBalancer

```gremlin
g.V().hasLabel('Service').has('ServiceId', 'SVC-ECOMMERCE-WEB')
  .out('depends_on').hasLabel('LoadBalancer')
  .valueMap(true)
```

### lb_in_region: LoadBalancer → Region

```gremlin
g.V().hasLabel('LoadBalancer').has('LBId', 'LB-USE-WEB')
  .out('lb_in_region').hasLabel('Region')
  .valueMap(true)
```

---

## Common Multi-Hop Query Patterns

### 2-hop: AZ failure → affected hosts and VMs

```gremlin
g.V().hasLabel('AvailabilityZone').has('AZId', 'AZ-US-EAST-A')
  .out('has_rack').hasLabel('Rack').as('rack')
  .out('hosts_server').hasLabel('Host').as('host')
  .select('rack', 'host').by(valueMap(true))
```

### 3-hop: host failure → affected VMs and services

```gremlin
g.V().hasLabel('Host').has('HostId', 'HOST-USE-A-01-01')
  .out('runs').hasLabel('VirtualMachine').as('vm')
  .out('serves').hasLabel('Service').as('svc')
  .select('vm', 'svc').by(valueMap(true))
```

### 4-hop: AZ failure → full blast radius with SLA exposure

```gremlin
g.V().hasLabel('AvailabilityZone').has('AZId', 'AZ-US-EAST-A')
  .out('has_rack').out('hosts_server').out('runs')
  .hasLabel('VirtualMachine').as('vm')
  .out('serves').hasLabel('Service').as('svc')
  .in('governs').hasLabel('SLAPolicy').as('sla')
  .select('vm', 'svc', 'sla').by(valueMap(true))
```

### 2-hop: service → upstream dependencies

```gremlin
g.V().hasLabel('Service').has('ServiceId', 'SVC-ECOMMERCE-WEB')
  .out('depends_on').as('dep')
  .select('dep').by(valueMap(true))
```

### Count vertices by label

```gremlin
g.V().groupCount().by(label)
```

### Get all hosts

```gremlin
g.V().hasLabel('Host').valueMap(true)
```
