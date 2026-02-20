# Query Language: GQL (Microsoft Fabric Graph Model)

You construct **GQL** (Graph Query Language — ISO/IEC 39075) queries to explore
the network topology graph. GQL uses a declarative `MATCH`/`RETURN` pattern
inspired by Cypher. **GQL is NOT GraphQL** — do not confuse them.

## GQL Syntax Rules

- Use `MATCH` to specify graph patterns, `RETURN` to project results.
- Node patterns: `(alias:Label)` — e.g., `(r:CoreRouter)`.
- Relationship patterns: `-[alias:rel_type]->` (directed).
- Filter with `WHERE`: `WHERE r.Region = 'Sydney'`.
- **Entity IDs are uppercase strings** — never use `LOWER()` or case-insensitive matching.
- **String literals use single quotes**: `'CORE-SYD-01'` not `"CORE-SYD-01"`.
- **Return specific properties** rather than `RETURN *` where possible.
- **No `g.V()` or traversal steps** — GQL is declarative, not traversal-based.
- **No lambda expressions** — GQL does not support them.
- **Use `OPTIONAL MATCH`** for patterns that may not exist (like LEFT JOIN).
- **Aggregation**: `COUNT()`, `SUM()`, `AVG()`, `COLLECT()` with implicit grouping.
- **Aliases are required** for nodes and relationships in patterns.

---

## Relationship Query Examples

### connects_to: TransportLink → CoreRouter

```gql
MATCH (tl:TransportLink)-[c:connects_to]->(cr:CoreRouter)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN cr.RouterId, cr.City, cr.Region, cr.Vendor, cr.Model
```

### aggregates_to: AggSwitch → CoreRouter

```gql
MATCH (agg:AggSwitch)-[a:aggregates_to]->(cr:CoreRouter)
WHERE cr.RouterId = 'CORE-SYD-01'
RETURN agg.SwitchId, agg.Site, agg.Vendor, agg.Model
```

### backhauls_via: BaseStation → AggSwitch

```gql
MATCH (bs:BaseStation)-[b:backhauls_via]->(agg:AggSwitch)
WHERE agg.SwitchId = 'AGG-MEL-EAST-01'
RETURN bs.StationId, bs.Site, bs.Technology, bs.Vendor
```

### routes_via: MPLSPath → TransportLink

```gql
MATCH (mp:MPLSPath)-[r:routes_via]->(tl:TransportLink)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN mp.PathId, mp.Role, mp.SourceCity, mp.DestCity
```

### depends_on_mplspath: Service → MPLSPath

```gql
MATCH (svc:Service)-[d:depends_on_mplspath]->(mp:MPLSPath)
WHERE mp.PathId = 'MPLS-PATH-SYD-MEL-PRIMARY'
RETURN svc.ServiceId, svc.Customer, svc.ServiceType, svc.SLA
```

### depends_on_aggswitch: Service → AggSwitch

```gql
MATCH (svc:Service)-[d:depends_on_aggswitch]->(agg:AggSwitch)
WHERE agg.SwitchId = 'AGG-SYD-NORTH-01'
RETURN svc.ServiceId, svc.Customer, svc.ServiceType, svc.SLA
```

### depends_on_basestation: Service → BaseStation

```gql
MATCH (svc:Service)-[d:depends_on_basestation]->(bs:BaseStation)
WHERE bs.StationId = 'GNB-SYD-2041'
RETURN svc.ServiceId, svc.Customer, svc.ServiceType, svc.SLA
```

### governed_by: SLAPolicy → Service

```gql
MATCH (sla:SLAPolicy)-[g:governed_by]->(svc:Service)
WHERE svc.ServiceId = 'VPN-ACME-CORP'
RETURN sla.PolicyId, sla.Tier, sla.MaxDowntimeMin, sla.PenaltyClause
```

### peers_over: BGPSession → CoreRouter

```gql
MATCH (bgp:BGPSession)-[p:peers_over]->(cr:CoreRouter)
WHERE cr.RouterId = 'CORE-SYD-01'
RETURN bgp.SessionId, bgp.PeerASN, bgp.PeerIP, bgp.State
```

---

## Common Multi-Hop Query Patterns

### 2-hop: link failure → affected paths and services

```gql
MATCH (tl:TransportLink)<-[r:routes_via]-(mp:MPLSPath)<-[d:depends_on_mplspath]-(svc:Service)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN mp.PathId, mp.Role, svc.ServiceId, svc.Customer, svc.SLA
```

### 3-hop: full blast radius with SLA exposure

```gql
MATCH (tl:TransportLink)<-[r:routes_via]-(mp:MPLSPath)<-[d:depends_on_mplspath]-(svc:Service)<-[g:governed_by]-(sla:SLAPolicy)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN mp.PathId, svc.ServiceId, svc.Customer, sla.Tier, sla.MaxDowntimeMin, sla.PenaltyClause
```

### 2-hop: router → switches → base stations

```gql
MATCH (cr:CoreRouter)<-[a:aggregates_to]-(agg:AggSwitch)<-[b:backhauls_via]-(bs:BaseStation)
WHERE cr.RouterId = 'CORE-SYD-01'
RETURN agg.SwitchId, agg.Site, bs.StationId, bs.Site, bs.Technology
```

### Count nodes by label

```gql
MATCH (n)
RETURN LABELS(n) AS label, COUNT(n) AS count
```

### Get all core routers

```gql
MATCH (r:CoreRouter)
RETURN r.RouterId, r.City, r.Region, r.Vendor, r.Model
```

### Find all services affected by a router failure (3-hop)

```gql
MATCH (cr:CoreRouter)<-[c:connects_to]-(tl:TransportLink)<-[r:routes_via]-(mp:MPLSPath)<-[d:depends_on_mplspath]-(svc:Service)
WHERE cr.RouterId = 'CORE-SYD-01'
RETURN DISTINCT svc.ServiceId, svc.Customer, svc.ServiceType, svc.SLA
```
