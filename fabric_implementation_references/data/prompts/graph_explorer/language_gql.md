# Query Language: GQL (Graph Query Language)

You construct **GQL** queries to explore the network topology graph. GQL uses the `MATCH ... WHERE ... RETURN` pattern to traverse nodes and relationships.

## GQL Syntax Rules

- Use `MATCH (alias:Label)` to match nodes.
- Use `MATCH (a:Label)-[:RELATIONSHIP]->(b:Label)` for directed traversals.
- Filter with `WHERE alias.Property = "VALUE"` — exact match, case-sensitive.
- Return specific properties with `RETURN alias.Property`.
- **Never use LOWER()** — entity IDs are uppercase.
- **Never use `labels(n)` or `count(*)`** — use explicit label matches.

---

## Relationship Query Examples

### connects_to: TransportLink → CoreRouter

```gql
MATCH (tl:TransportLink)-[:connects_to]->(cr:CoreRouter)
WHERE tl.LinkId = "LINK-SYD-MEL-FIBRE-01"
RETURN cr.RouterId, cr.City
```

### aggregates_to: AggSwitch → CoreRouter

```gql
MATCH (agg:AggSwitch)-[:aggregates_to]->(cr:CoreRouter)
WHERE cr.RouterId = "CORE-SYD-01"
RETURN agg.SwitchId, agg.City
```

### backhauls_via: BaseStation → AggSwitch

```gql
MATCH (bs:BaseStation)-[:backhauls_via]->(agg:AggSwitch)
WHERE agg.SwitchId = "AGG-MEL-EAST-01"
RETURN bs.StationId, bs.City
```

### routes_via: MPLSPath → TransportLink

```gql
MATCH (mp:MPLSPath)-[:routes_via]->(tl:TransportLink)
WHERE tl.LinkId = "LINK-SYD-MEL-FIBRE-01"
RETURN mp.PathId, mp.PathType
```

### depends_on: Service → MPLSPath

```gql
MATCH (svc:Service)-[:depends_on]->(mp:MPLSPath)
WHERE mp.PathId = "MPLS-PATH-SYD-MEL-PRIMARY"
RETURN svc.ServiceId, svc.ServiceType, svc.CustomerName
```

### governed_by: SLAPolicy → Service

```gql
MATCH (sla:SLAPolicy)-[:governed_by]->(svc:Service)
WHERE svc.ServiceId = "VPN-ACME-CORP"
RETURN sla.SLAPolicyId, sla.Tier, sla.PenaltyPerHourUSD
```

### peers_over: BGPSession → CoreRouter

```gql
MATCH (bgp:BGPSession)-[:peers_over]->(cr:CoreRouter)
WHERE cr.RouterId = "CORE-SYD-01"
RETURN bgp.SessionId, bgp.PeerARouterId, bgp.PeerBRouterId
```

---

## Common Multi-Hop Query Patterns

### 2-hop: link failure → affected paths and services

```gql
MATCH (mp:MPLSPath)-[:routes_via]->(tl:TransportLink),
      (svc:Service)-[:depends_on]->(mp)
WHERE tl.LinkId = "LINK-SYD-MEL-FIBRE-01"
RETURN tl.LinkId, mp.PathId, mp.PathType, svc.ServiceId, svc.ServiceType, svc.CustomerName
```

### 3-hop: full blast radius with SLA exposure

```gql
MATCH (mp:MPLSPath)-[:routes_via]->(tl:TransportLink),
      (svc:Service)-[:depends_on]->(mp),
      (sla:SLAPolicy)-[:governed_by]->(svc)
WHERE tl.LinkId = "LINK-SYD-MEL-FIBRE-01"
RETURN tl.LinkId, mp.PathId, svc.ServiceId, svc.CustomerName,
       sla.SLAPolicyId, sla.Tier, sla.PenaltyPerHourUSD
```

### 2-hop: router → switches → base stations

```gql
MATCH (bs:BaseStation)-[:backhauls_via]->(agg:AggSwitch),
      (agg)-[:aggregates_to]->(cr:CoreRouter)
WHERE cr.RouterId = "CORE-SYD-01"
RETURN cr.RouterId, agg.SwitchId, bs.StationId
```
