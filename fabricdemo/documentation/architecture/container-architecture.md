# Unified Container Architecture

All three services run in a **single container** managed by supervisord:

| Process | Bind Address | Role |
|---------|-------------|------|
| nginx | `0.0.0.0:80` (external) | Reverse proxy + React SPA |
| API (uvicorn) | `127.0.0.1:8000` | Agent orchestrator, SSE streaming, config endpoints |
| graph-query-api (uvicorn) | `127.0.0.1:8100` | Graph/telemetry queries, data upload, prompt CRUD |

**CORS configuration (unified post-V8 refactor):**
- Both API (:8000) and graph-query-api (:8100) set `allow_credentials=True`
- Both use environment-driven `CORS_ORIGINS` with consistent defaults

## nginx Routes

| Path | Upstream | Timeout | Notes |
|------|----------|---------|-------|
| `/` | React SPA (`/usr/share/nginx/html`) | — | `try_files $uri $uri/ /index.html` (SPA fallback) |
| `/api/*` | `proxy_pass http://127.0.0.1:8000` | 300s | SSE: `proxy_buffering off`, `proxy_cache off` |
| `/health` | `proxy_pass http://127.0.0.1:8000` | — | Health check |
| `/query/*` | `proxy_pass http://127.0.0.1:8100` | 600s | SSE: `proxy_buffering off`, `proxy_cache off` |

**`client_max_body_size 100m`** is set at **server block level** — applies to ALL routes, not just `/query/*`.

Security headers: `X-Frame-Options SAMEORIGIN`, `X-Content-Type-Options nosniff`.
Gzip enabled for text/CSS/JSON/JS/XML.

## Request Flow Diagram

```
Browser ─── POST /api/alert ──▶ nginx :80 ──▶ API :8000 ──▶ AI Foundry
       ◀── SSE stream ─────────                              (5 agents)
                                                                │
Browser ─── POST /query/upload/graph ──▶ nginx :80 ──▶ graph-query-api :8100
       ◀── SSE progress ──────────                    ├── Cosmos Gremlin
                                                      ├── Cosmos NoSQL
                                                      ├── AI Search
                                                      └── Blob Storage
```

## supervisord Config

3 programs, all `autostart=true`, `autorestart=true`:

| Program | Command | Working Dir | Priority |
|---------|---------|-------------|----------|
| nginx | `nginx -g "daemon off;"` | — | 10 |
| api | `/usr/local/bin/uv run uvicorn app.main:app --host 127.0.0.1 --port 8000` | `/app/api` | 20 |
| graph-query-api | `/usr/local/bin/uv run uvicorn main:app --host 127.0.0.1 --port 8100` | `/app/graph-query-api` | 20 |

All programs log to `stdout`/`stderr` (`logfile_maxbytes=0`). Pid file: `/var/run/supervisord.pid`.
