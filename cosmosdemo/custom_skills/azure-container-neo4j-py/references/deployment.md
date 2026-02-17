# Neo4j on Azure Container Apps — Deployment Reference

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Azure Container Apps Managed Environment                          │
│                                                                     │
│  ┌──────────────────────┐       ┌────────────────────────────────┐ │
│  │  graph-query-api     │       │  neo4j (Container App)         │ │
│  │  Container App       │ Bolt  │  Image: neo4j:2026.01.4-       │ │
│  │                      │──────>│         community              │ │
│  │  FastAPI + neo4j     │ 7687  │                                │ │
│  │  Python driver       │       │  Volume: Azure Files → /data   │ │
│  └──────────────────────┘       │  Ingress: internal only        │ │
│                                  └────────────────────────────────┘ │
│                                          │                          │
│                                  ┌───────┴───────┐                 │
│                                  │  Azure Files  │                 │
│                                  │  Share        │                 │
│                                  │  (neo4j-data) │                 │
│                                  └───────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Deployment Checklist

| Step | Action | Details |
|------|--------|---------|
| 1 | Create Azure Files share | Storage account + file share for `/data` persistence |
| 2 | Link storage to managed environment | `Microsoft.App/managedEnvironments/storages` resource |
| 3 | Deploy Neo4j Container App | Internal ingress, Bolt 7687, volume mounted to `/data` |
| 4 | Set Neo4j password | Via `NEO4J_AUTH` env var (from Key Vault in production) |
| 5 | Configure memory | `pagecache_size` and `heap_max__size` env vars |
| 6 | Verify connectivity | `driver.verify_connectivity()` from graph-query-api |
| 7 | Load initial data | Run data loading script (Cypher MERGE/CREATE) |
| 8 | Create indexes | Uniqueness constraints on primary key properties |

---

## Container App Networking

### Internal DNS Resolution

Within a Container Apps managed environment, apps communicate via internal FQDN:

```
bolt://<app-name>.<managed-env-default-domain>:7687
```

For example:
```
bolt://neo4j.internal.kindmeadow-abc123.eastus.azurecontainerapps.io:7687
```

The `graph-query-api` container app reads this URI from the `NEO4J_BOLT_URI`
environment variable.

### Port Mapping

| Port | Protocol | Purpose | Exposure |
|------|----------|---------|----------|
| 7687 | Bolt (TCP) | Driver communication | Internal only (Container Apps) |
| 7474 | HTTP | Neo4j Browser UI | **Not exposed** in production |
| 7473 | HTTPS | Neo4j Browser UI (TLS) | Not used |

> **Security**: Only expose port 7687 (Bolt) via internal ingress. Neo4j Browser
> (7474) should only be accessible during development, via port-forwarding or a
> separate dev Container App revision.

---

## Persistent Storage

### Why Azure Files?

Azure Container Apps supports two volume types:

| Volume Type | Persistence | Use Case |
|-------------|-------------|----------|
| `AzureFile` | Survives restarts/redeployments | **Neo4j `/data`** — graph database files |
| `EmptyDir` | Ephemeral — lost on restart | Temporary scratch space |

### Azure Files Considerations

- **Performance**: Standard SMB share is adequate for demo-sized graphs
  (50–200 nodes). For larger graphs, use Premium File Shares.
- **Access mode**: `ReadWrite` — Neo4j needs read+write access to `/data`.
- **Quota**: 5 GiB is generous for a demo graph. Neo4j Community with 50 nodes
  uses <100 MB.
- **Latency**: Azure Files has higher latency than local SSD. For a small demo
  graph this is negligible. For production, consider managed disks.

### Volume Mount Configuration

In the Bicep template, three resources are needed:

1. **Storage Account** with a file share
2. **Managed Environment Storage** — links the Azure Files share to the
   Container Apps environment
3. **Volume Mount** on the Neo4j container — maps the share to `/data`

```bicep
// 1. Storage link on managed environment
resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  name: '${environmentName}/neo4jdata'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: 'neo4j-data'
      accessMode: 'ReadWrite'
    }
  }
}

// 2. Volume + mount in the container app template
template: {
  containers: [{
    volumeMounts: [{ volumeName: 'neo4j-data', mountPath: '/data' }]
  }]
  volumes: [{
    name: 'neo4j-data'
    storageType: 'AzureFile'
    storageName: envStorage.name  // references the env storage
  }]
}
```

---

## Health Probes

### Liveness Probe

Checks that the Neo4j HTTP endpoint is responsive:

```bicep
{
  type: 'Liveness'
  httpGet: {
    port: 7474
    path: '/'
  }
  initialDelaySeconds: 30    // Neo4j needs time for JVM startup
  periodSeconds: 15
  failureThreshold: 3
}
```

### Readiness Probe

Checks that the Bolt port is accepting TCP connections:

```bicep
{
  type: 'Readiness'
  tcpSocket: {
    port: 7687
  }
  initialDelaySeconds: 20
  periodSeconds: 10
  failureThreshold: 3
}
```

### Startup Timing

Neo4j Community Edition in Docker typically takes 15–30 seconds to start:
- JVM initialization: ~5s
- Database recovery (if data exists): ~5–15s
- Plugin loading (APOC): ~5s
- Bolt listener ready: after all above complete

Set `initialDelaySeconds` >= 20 for readiness, >= 30 for liveness.

---

## Security

### Credentials Management

| Approach | When to Use |
|----------|-------------|
| Environment variable (`NEO4J_AUTH=neo4j/pass`) | Local dev, demos |
| Azure Key Vault secret reference | Production |
| Container Apps secrets | Production (alternative) |

#### Key Vault Integration

```bicep
// Reference a Key Vault secret in Container App
env: [
  {
    name: 'NEO4J_AUTH'
    secretRef: 'neo4j-auth'    // references Container App secret
  }
]

configuration: {
  secrets: [
    {
      name: 'neo4j-auth'
      keyVaultUrl: 'https://myvault.vault.azure.net/secrets/neo4j-auth'
      identity: managedIdentityResourceId
    }
  ]
}
```

### Network Isolation

- Neo4j Container App uses **internal-only ingress** (`external: false`)
- Only containers within the same managed environment can reach it
- No public IP or external load balancer
- For additional isolation, use a custom VNET with the managed environment

---

## Resource Sizing

### Demo / Development

| Resource | Value | Rationale |
|----------|-------|-----------|
| CPU | 1.0 cores | Adequate for <100 concurrent queries |
| Memory | 2Gi | 512M page cache + 512M heap + OS overhead |
| Azure Files | 5 GiB Standard | <100 MB actual usage for demo graph |
| Replicas | 1 | Community Edition is single-instance |

### Larger Demos (500+ nodes)

| Resource | Value |
|----------|-------|
| CPU | 2.0 cores |
| Memory | 4Gi |
| Page cache | 1G |
| Heap max | 1G |
| Azure Files | 10 GiB Premium |

---

## Troubleshooting

### Common Issues

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `ServiceUnavailable: Unable to retrieve routing information` | Using `neo4j://` scheme with single instance | Use `bolt://` instead of `neo4j://` |
| `AuthError: The client is unauthorized` | Wrong password or `NEO4J_AUTH` not set | Check `NEO4J_AUTH` env var matches driver auth |
| Container restart loop | OOM — insufficient memory | Increase container memory; set `pagecache_size` and `heap_max__size` |
| `LOAD CSV` file not found | CSV not mounted to `/import` | Mount CSV directory to `/var/lib/neo4j/import` |
| Slow startup (>60s) | Recovery of unclean shutdown | Normal after crash; increase probe `initialDelaySeconds` |
| Data lost after restart | No volume mounted to `/data` | Add Azure Files volume mount |

### Useful Diagnostic Cypher Queries

```cypher
// Check database status
CALL dbms.listDatabases()

// Check installed procedures (verify APOC)
CALL dbms.procedures() YIELD name WHERE name STARTS WITH 'apoc' RETURN name LIMIT 5

// Count all nodes and relationships
MATCH (n) RETURN count(n) AS nodes
UNION ALL
MATCH ()-[r]->() RETURN count(r) AS relationships

// Check indexes and constraints
SHOW INDEXES
SHOW CONSTRAINTS

// Memory usage
CALL dbms.queryJmx('java.lang:type=Memory')
```
