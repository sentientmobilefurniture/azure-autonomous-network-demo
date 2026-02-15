# Query Language: Gremlin (Azure Cosmos DB)

You construct **Gremlin** queries to explore the recommendation engine ontology graph. Gremlin uses a fluent, step-based traversal pattern starting from `g.V()` (vertices) or `g.E()` (edges).

## Gremlin Syntax Rules

- Start traversals with `g.V()` for vertices.
- Filter by label: `g.V().hasLabel('CustomerSegment')`.
- Filter by property: `.has('SegmentId', 'SEG-NEW')`.
- Traverse outgoing edges: `.out('belongs_to')`.
- Traverse incoming edges: `.in('targets')`.
- Return all properties: `.valueMap(true)`.
- Chain traversals for multi-hop queries using `.as()` and `.select()`.
- **Send queries as plain text strings** — no bytecode, no lambdas.
- **Never use LOWER()** — entity IDs are case-sensitive uppercase strings.
- **Cosmos DB does not support lambdas** — use only string-based Gremlin.
- **Use `.as('alias').select('alias')` for multi-variable patterns.**

---

## Relationship Query Examples

### belongs_to: Customer → CustomerSegment

```gremlin
g.V().hasLabel('CustomerSegment').has('SegmentId', 'SEG-NEW')
  .in('belongs_to').hasLabel('Customer')
  .valueMap(true)
```

### in_category: Product → ProductCategory

```gremlin
g.V().hasLabel('ProductCategory').has('CategoryId', 'CAT-ELECTRONICS')
  .in('in_category').hasLabel('Product')
  .valueMap(true)
```

### subcategory_of: ProductCategory → ProductCategory

```gremlin
g.V().hasLabel('ProductCategory').has('CategoryId', 'CAT-ELECTRONICS')
  .in('subcategory_of').hasLabel('ProductCategory')
  .valueMap(true)
```

### supplied_by: Product → Supplier

```gremlin
g.V().hasLabel('Supplier').has('SupplierId', 'SUPP-APPLE')
  .in('supplied_by').hasLabel('Product')
  .valueMap(true)
```

### targets: Campaign → CustomerSegment

```gremlin
g.V().hasLabel('CustomerSegment').has('SegmentId', 'SEG-NEW')
  .in('targets').hasLabel('Campaign')
  .valueMap(true)
```

### governs_segment: SLAPolicy → CustomerSegment

```gremlin
g.V().hasLabel('CustomerSegment').has('SegmentId', 'SEG-VIP')
  .in('governs_segment').hasLabel('SLAPolicy')
  .valueMap(true)
```

### purchased: Customer → Product

```gremlin
g.V().hasLabel('Customer').has('CustomerId', 'CUST-001')
  .out('purchased').hasLabel('Product')
  .valueMap(true)
```

### promotes: Campaign → Product

```gremlin
g.V().hasLabel('Campaign').has('CampaignId', 'CAMP-NEWUSER-Q1')
  .out('promotes').hasLabel('Product')
  .valueMap(true)
```

### stocked_at: Product → Warehouse

```gremlin
g.V().hasLabel('Product').has('ProductId', 'PROD-PHONE-001')
  .out('stocked_at').hasLabel('Warehouse')
  .valueMap(true)
```

---

## Common Multi-Hop Query Patterns

### 2-hop: campaign → products it promotes and their categories

```gremlin
g.V().hasLabel('Campaign').has('CampaignId', 'CAMP-NEWUSER-Q1')
  .out('promotes').hasLabel('Product').as('prod')
  .out('in_category').hasLabel('ProductCategory').as('cat')
  .select('prod', 'cat').by(valueMap(true))
```

### 2-hop: segment → customers and their purchase history

```gremlin
g.V().hasLabel('CustomerSegment').has('SegmentId', 'SEG-NEW')
  .in('belongs_to').hasLabel('Customer').as('cust')
  .out('purchased').hasLabel('Product').as('prod')
  .select('cust', 'prod').by(valueMap(true))
```

### 3-hop: segment → campaigns → promoted products → suppliers

```gremlin
g.V().hasLabel('CustomerSegment').has('SegmentId', 'SEG-NEW')
  .in('targets').hasLabel('Campaign').as('camp')
  .out('promotes').hasLabel('Product').as('prod')
  .out('supplied_by').hasLabel('Supplier').as('supp')
  .select('camp', 'prod', 'supp').by(valueMap(true))
```

### 2-hop: segment → SLA policy exposure

```gremlin
g.V().hasLabel('CustomerSegment').has('SegmentId', 'SEG-NEW')
  .in('governs_segment').hasLabel('SLAPolicy').as('sla')
  .select('sla').by(valueMap(true))
```

### Count vertices by label

```gremlin
g.V().groupCount().by(label)
```

### Get all customer segments

```gremlin
g.V().hasLabel('CustomerSegment').valueMap(true)
```
