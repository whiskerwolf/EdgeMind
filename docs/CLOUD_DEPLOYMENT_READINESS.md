# EdgeMind â€” Cloud Deployment Readiness Specification & Checklist

## 1. Executive Summary

This document specifies the production cloud deployment architecture for the EdgeMind FastAPI backend, enabling multi-device synchronization, secure cloud multi-tenancy, and high-availability PostgreSQL 16 JSONB report persistence.

### Production Constraints
- **Zero Public Database Exposure:** The PostgreSQL database must **never** be accessible directly over the public internet. Access is strictly confined to the private Virtual Private Cloud (VPC) subnet.
- **Credential Hygiene:** No production secrets or certificates are committed to Git. All secrets are dynamically injected via cloud secret managers.
- **Static Analysis Invariant:** The backend remains 100% static analysis; zero arbitrary code execution is permitted in any environment.

---

## 2. Target Cloud Architecture

```
                                  INTERNET
                                     |
                                     v
                 +---------------------------------------+
                 |    Cloudflare / Cloud Load Balancer   |
                 |      - TLS 1.3 Termination (HTTPS)    |
                 |      - DDoS Protection / Rate Limits  |
                 |      - Strict CORS Enforcement        |
                 +-------------------+-------------------+
                                     |
                                     v [HTTPS / Port 443]
+------------------------------------+---------------------------------------+
|                        Virtual Private Cloud (VPC)                         |
|                                                                            |
|   +--------------------------------------------------------------------+   |
|   |                     Public Subnet (Ingress)                        |   |
|   |  Application Load Balancer (ALB) / Ingress Gateway                |   |
|   +---------------------------------+----------------------------------+   |
|                                     |                                      |
|                                     v (Internal Traffic Only)              |
|   +---------------------------------+----------------------------------+   |
|   |                     Private Application Subnet                     |   |
|   |  FastAPI Backend Containers (AWS ECS Fargate / Cloud Run)          |   |
|   |   - Python 3.12/3.13 Slim Container                                |   |
|   |   - Unprivileged 'appuser' (non-root)                              |   |
|   |   - Health check probe: GET /health                                |   |
|   |   - Asyncpg connection pool with SSL enabled                       |   |
|   +---------------------------------+----------------------------------+   |
|                                     |                                      |
|                                     v (Port 5432 / TLS)                    |
|   +---------------------------------+----------------------------------+   |
|   |                     Isolated Database Subnet                       |   |
|   |  Managed PostgreSQL 16 Database Cluster                           |   |
|   |   - Amazon RDS / Cloud SQL / Neon Private VPC                      |   |
|   |   - Native JSONB & GIN Indexes                                     |   |
|   |   - Automated Daily Backups + 7-Day Point-in-Time Recovery (PITR)  |   |
|   |   - Zero Public IP (Private Subnet Only)                           |   |
|   +--------------------------------------------------------------------+   |
+----------------------------------------------------------------------------+
```

---

## 3. Production Deployment Checklist

### 3.1 Cloud Hosting & Compute
- [ ] Containerized execution via lightweight distroless or Debian slim base image.
- [ ] Process runs as an unprivileged system user (`appuser`, UID 10001), not `root`.
- [ ] Stateless application tier horizontally scalable across availability zones (AZs).
- [ ] Liveness and readiness probes pointing to `GET /health`.

### 3.2 PostgreSQL 16 Database Architecture
- [ ] Managed PostgreSQL engine version `16.x`.
- [ ] Subnet placement: Private database subnets with no internet gateway attachment.
- [ ] Security group ingress strictly restricted to the application container security group on port `5432`.
- [ ] SSL/TLS enforced for all database connections (`sslmode=require` or `sslmode=verify-full`).
- [ ] Alembic migrations executed automatically as a pre-deploy release step:
  ```bash
  alembic upgrade head
  ```
- [ ] Storage auto-scaling and read replicas enabled for high-volume analysis queries.

### 3.3 Environment Variables & Configuration
| Variable | Environment | Purpose | Sensitivity |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `production` | Activates production connection pooling & logging | Low |
| `DATABASE_URL` | Cloud Secret | `postgresql+asyncpg://<user>:<pwd>@<private-db-host>:5432/edgemind?ssl=require` | **Critical** |
| `JWT_SECRET_KEY` | Cloud Secret | High-entropy 256-bit cryptographic secret for token signing | **Critical** |
| `CORS_ORIGINS` | JSON Array | Allowed web client URLs (e.g. `["https://app.edgemind.dev"]`) | Low |
| `CORS_ORIGIN_REGEX` | Regex | Allowed Chrome extension ID: `^chrome-extension://<CHROME_EXT_ID>$` | Medium |
| `EDGEMIND_AI_KEY` | Cloud Secret | AI Reasoning provider key | **Critical** |
| `STATIC_ONLY` | `true` | Enforces static-only analysis invariant | Low (Immutable) |

### 3.4 Secret Management
- [ ] Zero secrets in Docker images, Git history, or plain text configuration files.
- [ ] Dynamic secret resolution via AWS Secrets Manager, GCP Secret Manager, or Azure Key Vault.
- [ ] Automated 90-day secret rotation for database credentials.

### 3.5 HTTPS, TLS & Ingress Security
- [ ] Enforce TLS 1.3 with automated certificate renewal (Let's Encrypt / AWS Certificate Manager).
- [ ] HTTP Strict Transport Security (HSTS) headers enabled (`max-age=31536000; includeSubDomains; preload`).
- [ ] Web Application Firewall (WAF) rate limiting to mitigate DDoS or brute-force requests.

### 3.6 CORS & Browser Extension Security
- [ ] Production CORS strictly whitelists the official Chrome Web Store extension ID and the production dashboard domain.
- [ ] Wildcard origins (`*`) disallowed in production when `allow_credentials=True`.

### 3.7 Authentication & Access Control
- [ ] Short-lived JWT access tokens (15-minute expiration).
- [ ] Refresh tokens persisted in PostgreSQL with cryptographic hashing and rotation on use.
- [ ] Multi-tenant isolation verified via tenant ID filtering on all repository queries.

### 3.8 Database Backup & Disaster Recovery
- [ ] Automated daily full database backups retained for 30 days.
- [ ] Point-in-Time Recovery (PITR) enabled with 5-minute RPO (Recovery Point Objective).
- [ ] Disaster recovery runbook documented for regional failover.

### 3.9 Logging, Monitoring & Observability
- [ ] Structured JSON logging to stdout with correlation IDs (`X-Request-ID`).
- [ ] Latency tracking headers (`X-Process-Time`) exported to monitoring metrics.
- [ ] CloudWatch / Google Cloud Logging / Datadog aggregation for real-time alerting on 5xx errors.
- [ ] Health check alerts triggered if `/health` returns non-200 for 3 consecutive polls.
