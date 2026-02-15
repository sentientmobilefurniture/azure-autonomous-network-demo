## Vertex Types

### Server (2 instances)
| ServerId | Hostname | OS | CPUCores | MemoryGB |
|----------|----------|----|----------|----------|
| SRV-ALPHA-01 | alpha-prod-01 | Ubuntu 22.04 | 32 | 128 |
| SRV-BETA-01 | beta-prod-01 | Ubuntu 22.04 | 16 | 64 |

### Application (3 instances)
| AppId | AppName | AppType | ServerId | DatabaseId |
|-------|---------|---------|----------|------------|
| APP-WEB-01 | Web Frontend | web | SRV-ALPHA-01 | DB-REPLICA-01 |
| APP-API-01 | API Backend | api | SRV-ALPHA-01 | DB-PRIMARY-01 |
| APP-WORKER-01 | Background Worker | worker | SRV-BETA-01 | DB-PRIMARY-01 |

### Database (2 instances)
| DatabaseId | DatabaseName | Engine | SizeGB |
|------------|-------------|--------|--------|
| DB-PRIMARY-01 | Primary PostgreSQL | PostgreSQL 16 | 500 |
| DB-REPLICA-01 | Read Replica | PostgreSQL 16 | 500 |

## Edge Types
| Edge Label | Source Type | Target Type | Description |
|-----------|------------|------------|-------------|
| hosts | Server | Application | Server hosts an application |
| connects_to | Application | Database | Application connects to a database |
