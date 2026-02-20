## Gremlin Query Examples

### List all servers
```gremlin
g.V().hasLabel('Server').valueMap(true)
```

### Find applications hosted on SRV-ALPHA-01
```gremlin
g.V().has('Server', 'ServerId', 'SRV-ALPHA-01').out('hosts').valueMap(true)
```

### Find the database for APP-API-01
```gremlin
g.V().has('Application', 'AppId', 'APP-API-01').out('connects_to').valueMap(true)
```

### Full path: server → apps → databases
```gremlin
g.V().has('Server', 'ServerId', 'SRV-ALPHA-01').out('hosts').out('connects_to').path().by(valueMap(true))
```

### Find all apps connected to a database
```gremlin
g.V().has('Database', 'DatabaseId', 'DB-PRIMARY-01').in('connects_to').valueMap(true)
```

### Count entities by type
```gremlin
g.V().groupCount().by(label)
```
