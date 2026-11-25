# EdgeMind Production Deployment & Operations Guide

This guide details the production deployment, infrastructure architecture, security invariants, operational procedures, and rollback strategies for the EdgeMind API platform.

---

## 1. Production Architecture Overview

EdgeMind is architected as an isolated, containerized micro-service stack designed for container runtimes (Docker, Docker Compose, AWS ECS, or Kubernetes).

```
                             [ Internet / Clients ]
                                       │
                              HTTPS / TLS 1.3 (443)
                                       │
                      [ Cloud Reverse Proxy / Ingress ]
                      (AWS ALB / Nginx / Cloudflare CDN)
                                       │
                            Internal Docker Bridge
                                       │
       ┌───────────────────────────────┴───────────────────────────────┐
       │                                                               │
┌──────▼──────────────────────────┐                   ┌────────────────▼────────────────┐
│      edgemind-backend           │                   │        Windows / Edge Host      │
│  FastAPI (Uvicorn 2 workers)    │                   │   Ollama Local AI (Port 11434)  │
│  Unprivileged UID 10001         ├──────────────────►│   - qwen3:4b (Reasoning)        │
│  STATIC_ONLY=true               │   host-gateway    │   - all-minilm (384-dim Embed)  │
└──────┬──────────────────┬───────┘                   └─────────────────────────────────┘
       │                  │
       │ Port 5432        │ Port 6379
       │                  ├──────────────────────────────────┐
┌──────▼────────────┐ ┌───▼────────────────────────┐ ┌───────▼──────────────────────────┐
│ edgemind-postgres │ │ edgemind-redis (Cache)     │ │ edgemind-redis-rate-limit        │
│ PostgreSQL 16 +   │ │ Redis 7.2-alpine           │ │ Redis 7.2-alpine                 │
│ pgvector 0.8.7    │ │ Maxmemory 256MB            │ │ Maxmemory 64MB                   │
│ Volume: pgvector  │ │ Policy: allkeys-lru        │ │ Policy: noeviction               │
└───────────────────┘ └────────────────────────────┘ └──────────────────────────────────┘
```

### Key Architectural Invariants
1. **Static-Only Safety**: `STATIC_ONLY=true` is an immutable invariant enforced at both runtime and configuration schema level. EdgeMind performs purely AST-based and cognitive analysis without ever executing untrusted user source code.
2. **Dedicated Rate-Limiting Isolation**: A distinct Redis instance on port 6380 (`noeviction`) guarantees rate limiting memory is never crowded out by document or LLM caching.
3. **Least Privilege**: The container operates under unprivileged user `edgemind:edgemind` (UID 10001, GID 10001) with read-only application code directories.
4. **Port Isolation**: External host mapping for PostgreSQL uses port 5433 (`127.0.0.1:5433:5432`) to avoid port collisions with legacy or co-located databases on default port 5432.

---

## 2. Environment Variables Configuration

In production environments, configure these variables via an orchestration secret manager (AWS Secrets Manager, HashiCorp Vault, Kubernetes Secrets, or a secure `.env` file with `chmod 600`).

| Variable Name | Required | Default / Recommended | Purpose |
| :--- | :---: | :--- | :--- |
| `ENVIRONMENT` | **Yes** | `production` | Enables production validation rules. |
| `DEBUG` | **Yes** | `false` | Must remain `false` in production. |
| `STATIC_ONLY` | **Yes** | `true` | Immutable safety constraint. |
| `DATABASE_URL` | **Yes** | `postgresql+asyncpg://user:pass@postgres:5432/edgemind` | Internal async PostgreSQL connection. |
| `POSTGRES_USER` | **Yes** | `edgemind_admin` | Database administrative username. |
| `POSTGRES_PASSWORD` | **Yes** | *(High-entropy 32+ char secret)* | Database password. |
| `POSTGRES_DB` | **Yes** | `edgemind` | Production database name. |
| `POSTGRES_PORT` | No | `5433` | Host-bound database port mapping. |
| `REDIS_PASSWORD` | **Yes** | *(High-entropy 32+ char secret)* | Master password for Redis Cache instance. |
| `REDIS_URL` | **Yes** | `redis://:pass@redis:6379/0` | Internal Redis Cache connection URL. |
| `REDIS_RATE_LIMIT_PASSWORD`| **Yes** | *(High-entropy secret)* | Password for dedicated Rate Limit Redis. |
| `REDIS_RATE_LIMIT_URL` | **Yes** | `redis://:pass@redis-rate-limit:6379/0` | Internal Redis Rate Limiter connection. |
| `JWT_SECRET_KEY` | **Yes** | *(High-entropy 64+ char secret)* | Signs HMAC-SHA256 authentication tokens. |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | Short-lived access token validity. |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifecycle. |
| `CORS_ORIGINS` | No | `["https://app.yourdomain.com"]` | Trusted production web origin allowlist. |
| `TRUSTED_PROXY_IPS` | No | `["10.0.0.0/8", "172.16.0.0/12"]` | IPs allowed to provide `X-Forwarded-For`. |
| `EDGEMIND_AGENT_PROVIDER` | No | `ollama` | Active provider (`ollama` or `openai`). |
| `OLLAMA_BASE_URL` | No | `http://host.docker.internal:11434` | Endpoint for local reasoning & embeddings. |

---

## 3. Database & pgvector Configuration

- **Image**: `pgvector/pgvector:0.8.7-pg16`
- **Storage**: Persistent named volume `postgres_pgvector_data` backed by high-IOPS NVMe storage.
- **pgvector Extensions**:
  Migrations `005` through `008` automatically initialize and manage the vector extension:
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  ```
- **Embedding Spaces**:
  - `knowledge_chunks.embedding`: `vector(1536)` indexed via HNSW (`ix_knowledge_chunks_embedding_hnsw`) with `vector_cosine_ops`.
  - `knowledge_chunks.embedding_384`: `vector(384)` indexed via HNSW (`ix_knowledge_chunks_embedding_384_hnsw`) with `vector_cosine_ops`.

---

## 4. Redis Caching & Rate Limiting Configuration

Both Redis services are pinned to `redis:7.2.17-alpine3.21` and command-hardened:

```bash
# Cache Instance (port 6379)
redis-server \
  --requirepass "${REDIS_PASSWORD}" \
  --maxmemory 256mb \
  --maxmemory-policy allkeys-lru \
  --rename-command FLUSHALL "" \
  --rename-command FLUSHDB "" \
  --rename-command CONFIG ""

# Rate Limiter Instance (port 6380)
redis-server \
  --requirepass "${REDIS_RATE_LIMIT_PASSWORD}" \
  --maxmemory 64mb \
  --maxmemory-policy noeviction \
  --rename-command FLUSHALL "" \
  --rename-command FLUSHDB "" \
  --rename-command CONFIG ""
```

---

## 5. HTTPS & TLS Requirements

The EdgeMind container does not terminate TLS directly. Production deployments must place EdgeMind behind a TLS 1.3 terminating reverse proxy (e.g. AWS ALB, Cloudflare, Traefik, or Nginx).

### Recommended Nginx Configuration
```nginx
server {
    listen 443 ssl http2;
    server_name api.edgemind.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.edgemind/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.edgemind/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 180s;
    }
}
```

---

## 6. Step-by-Step Deployment Procedure

### Step 1: Pre-Deployment Validation
Verify all secrets are generated and defined:
```bash
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_hex(32))"
python -c "import secrets; print('REDIS_PASSWORD=' + secrets.token_hex(24))"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24))"
```

### Step 2: Validate Docker Compose
```bash
docker compose config -q
```

### Step 3: Build Production Backend Image
```bash
docker compose build --no-cache backend
```

### Step 4: Launch Database and Cache Services
```bash
docker compose up -d postgres redis redis-rate-limit
```

Wait until all three dependency containers report `healthy`:
```bash
docker compose ps
```

### Step 5: Execute Alembic Database Migrations
```bash
docker compose exec backend alembic upgrade head
```

Verify migration status matches head (`008_fix_knowledge_documents_updated_at`):
```bash
docker compose exec backend alembic current
```

### Step 6: Start API Backend
```bash
docker compose up -d backend
```

Verify backend health check:
```bash
curl -f http://127.0.0.1:8000/health
```

---

## 7. Rollback Procedure

### Application Rollback
If the newly deployed container exhibits an anomaly:
```bash
# 1. Switch back to previous tagged image
docker compose stop backend
docker run -d --name edgemind-backend-rollback ... <previous-image-tag>

# 2. Or revert compose file and restart
git checkout HEAD~1 docker-compose.yml
docker compose up -d backend
```

### Database Migration Rollback
To roll back the most recent migration cleanly:
```bash
docker compose exec backend alembic downgrade -1
```

### Disaster Recovery from Backup
If disaster recovery is required:
```bash
docker exec -i edgemind-postgres psql -U postgres -d edgemind < backup_edgemind.sql
```

For OCI production deployments, automated daily `pg_dump` backups (`/opt/edgemind/backups`, 7-day retention by default) and daily `refresh_tokens` cleanup run via systemd timers installed by `deploy/oci/scripts/install-systemd-timers.sh`. See `deploy/oci/README.md` (Section 6) for schedule overrides, retention variables (`BACKUP_DIR`, `RETENTION_DAYS`, `TOKEN_CLEANUP_GRACE_DAYS`, `TOKEN_CLEANUP_REVOKED_GRACE_DAYS`), `restore-postgres.sh`, and troubleshooting.

---

## 8. Health Checks, Logging and Monitoring

### Health Endpoint
- **URL**: `GET /health`
- **Success Response**: `HTTP 200 OK`
  ```json
  {"status": "healthy", "service": "EdgeMind"}
  ```
- **Interval**: 15 seconds, timeout: 3 seconds, retries: 3.

### Tracing & Request Logging
Every request through the backend contains:
- `X-Request-ID`: UUIDv4 correlation identifier passed across log statements.
- `X-Process-Time`: Nanosecond-accurate execution latency duration in milliseconds.

### Metric Monitoring Suggestions
- **PostgreSQL**: `pg_stat_statements` for query execution latency and index hit ratio.
- **Redis**: Monitor `used_memory`, `connected_clients`, and `evicted_keys` (must remain 0 for rate-limiter).
- **Host System**: CPU utilization, Memory usage, and GPU VRAM utilization when local Ollama inference is active.
