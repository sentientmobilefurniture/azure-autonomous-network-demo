# Graph Schema Format — `graph_schema.yaml` Quick Reference

This is a standalone quick reference for the `graph_schema.yaml` format.
The full specification with examples is in `ticket-format.md` (second half).

## Purpose

`graph_schema.yaml` is the **single source of truth** for the Cosmos DB Gremlin
graph. The generic loader reads this manifest to:

1. Create vertices from CSV files (one `addV()` per CSV row)
2. Create edges from CSV files (one `addE()` per CSV row, with optional filtering)
3. Attach properties to vertices and edges

No loader code changes are needed for new scenarios — only a new YAML file.

## Minimal Template

```yaml
data_dir: data/scenarios/<scenario>/data/entities

vertices:
  - label: <EntityType>
    csv_file: Dim<EntityType>.csv
    id_column: <IdColumn>
    partition_key: <static_string>
    properties: [<IdColumn>, <Prop1>, <Prop2>]

edges:
  - label: <relationship>
    csv_file: Dim<SourceEntity>.csv
    source:
      label: <SourceEntity>
      property: <SourceIdProp>
      column: <SourceIdColumn>
    target:
      label: <TargetEntity>
      property: <TargetIdProp>
      column: <ForeignKeyColumn>
```

## Vertex Checklist

- [ ] Every entity type in topology CSVs has a vertex definition
- [ ] `csv_file` exists in `data_dir`
- [ ] `id_column` is listed in `properties`
- [ ] `partition_key` is a short static string (e.g. `router`, `host`, `service`)
- [ ] All CSV columns needed for graph queries/display are in `properties`
- [ ] `label` is unique — no two vertex definitions share the same label

## Edge Checklist

- [ ] Every relationship in the domain has an edge definition
- [ ] `source.label` and `target.label` match existing vertex labels
- [ ] `source.column` and `target.column` are real CSV column names
- [ ] Bidirectional connections have two separate edge entries
- [ ] Junction tables with multiple target types use `filter` per type
- [ ] Edge `properties` use either `column` or `value`, never both

## Edge Count Guide

The telco-noc reference has 8 vertex types and 11 edge definitions. A good rule:

```
edge_definitions ≈ 1.2 × vertex_types + bidirectional_pairs + filtered_variants
```

For a cloud scenario with 8 entity types, expect ~12–15 edge definitions.
