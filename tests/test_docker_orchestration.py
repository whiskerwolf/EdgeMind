"""
Automated Validation Suite for EdgeMind Phase 6 Docker Orchestration.

Verifies:
- Production Dockerfile multi-stage build, unprivileged user, healthcheck, static-only invariants
- .dockerignore completeness (preventing credential, cache, database, and venv leakage)
- docker-compose.yml structural validation via client-side docker compose config
- Service topology: backend, postgres (with pgvector), redis cache, and redis rate-limit
- Port mapping: PostgreSQL on 5433 (avoiding 5432 nexus-postgres conflict), Redis on 6379 & 6380
- Internal service name networking (postgres:5432, redis:6379, redis-rate-limit:6379)
- Local Ollama connectivity via host.docker.internal:11434 with extra_hosts gateway
- Persistent volumes and healthcheck dependencies (condition: service_healthy)
- Redis authentication enforcement and security configuration
"""

import json
import os
from pathlib import Path
import subprocess
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def _get_compose_config():
    """Retrieve parsed JSON configuration from docker compose config."""
    env = os.environ.copy()
    env["REDIS_PASSWORD"] = "test_audit_redis_pass_123"
    env["POSTGRES_PASSWORD"] = "test_audit_pg_pass_123"

    res = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode == 0, f"docker compose config failed:\n{res.stderr}\n{res.stdout}"
    return json.loads(res.stdout)


def test_dockerfile_structure_and_security():
    """Verify Dockerfile multi-stage build, non-root user, static-only invariant, and healthcheck."""
    dockerfile_path = REPO_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist at repository root"

    content = dockerfile_path.read_text(encoding="utf-8")

    # Multi-stage build
    assert "FROM python:3.12-slim AS builder" in content
    assert "FROM python:3.12-slim AS runtime" in content
    assert "COPY --from=builder /opt/venv /opt/venv" in content

    # Unprivileged user security (UID/GID 10001)
    assert "useradd -u 10001 -g edgemind" in content
    assert "USER edgemind:edgemind" in content

    # Security & static-only invariant
    assert 'STATIC_ONLY="true"' in content
    assert 'PYTHONUNBUFFERED="1"' in content

    # Application copy
    assert "COPY --chown=edgemind:edgemind core/ /app/core/" in content
    assert "COPY --chown=edgemind:edgemind migrations/ /app/migrations/" in content
    assert "COPY --chown=edgemind:edgemind alembic.ini /app/alembic.ini" in content

    # Healthcheck
    assert "HEALTHCHECK" in content
    assert "http://127.0.0.1:8000/health" in content

    # Port exposure
    assert "EXPOSE 8000" in content


def test_dockerignore_completeness():
    """Verify .dockerignore excludes sensitive files, local databases, venvs, and development tools."""
    dockerignore_path = REPO_ROOT / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist at repository root"

    content = dockerignore_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]

    # Critical security exclusions
    assert ".env" in lines
    assert ".env.*" in lines
    assert ".git" in lines
    assert ".venv/" in lines

    # Caches and tests
    assert "__pycache__/" in lines or "__pycache__" in lines
    assert "tests/" in lines

    # Databases and persistence files
    assert "*.db" in lines
    assert "*.sqlite" in lines
    assert "*.rdb" in lines


def test_docker_compose_yaml_structure_and_services():
    """Verify docker compose parses and defines all 4 required services, networks, and volumes."""
    config = _get_compose_config()

    services = config.get("services", {})
    assert "backend" in services, "FastAPI backend service must be defined"
    assert "postgres" in services, "PostgreSQL service must be defined"
    assert "redis" in services, "Redis cache service must be defined"
    assert "redis-rate-limit" in services, "Dedicated Redis rate-limit service must be defined"

    # Volumes & Networks
    volumes = config.get("volumes", {})
    assert "postgres_pgvector_data" in volumes, "Persistent pgvector volume must be defined"
    assert "redis_data" in volumes, "Persistent Redis cache volume must be defined"
    assert "redis_rate_limit_data" in volumes, "Persistent Redis rate-limit volume must be defined"

    networks = config.get("networks", {})
    assert "edgemind-network" in networks, "Internal bridge network must be defined"


def test_postgres_pgvector_and_port_5433_isolation():
    """Verify PostgreSQL uses pgvector, host port 5433 (avoiding 5432 nexus-postgres conflict), and healthcheck."""
    config = _get_compose_config()
    pg = config["services"]["postgres"]

    # Image should be pgvector
    assert "pgvector" in pg["image"]

    # Host port must be 5433 to avoid collision with nexus-postgres on 5432
    ports = pg.get("ports", [])
    has_5433 = any(p.get("published") == "5433" and p.get("target") == 5432 for p in ports)
    assert has_5433, f"PostgreSQL must map host 5433 to container 5432, got: {ports}"

    # Healthcheck
    assert "healthcheck" in pg
    assert "pg_isready" in str(pg["healthcheck"]["test"])


def test_redis_cache_and_rate_limiting_isolation():
    """Verify separate Redis services on ports 6379 and 6380 with memory limits and authentication."""
    config = _get_compose_config()
    cache = config["services"]["redis"]
    rate_lim = config["services"]["redis-rate-limit"]

    # Cache Redis on 6379 with allkeys-lru
    cache_ports = cache.get("ports", [])
    assert any(p.get("published") == "6379" for p in cache_ports)
    assert "allkeys-lru" in str(cache.get("command", []))

    # Rate Limiting Redis on 6380 with noeviction
    rate_ports = rate_lim.get("ports", [])
    assert any(p.get("published") == "6380" for p in rate_ports)
    assert "noeviction" in str(rate_lim.get("command", []))

    # Both enforce password requirement
    assert "--requirepass" in str(cache.get("command", []))
    assert "--requirepass" in str(rate_lim.get("command", []))


def test_backend_service_dependencies_and_ollama_bridge():
    """Verify backend depends on healthy dependencies and connects to host Ollama via host.docker.internal."""
    config = _get_compose_config()
    backend = config["services"]["backend"]

    # Depends on with condition: service_healthy
    depends = backend.get("depends_on", {})
    assert depends["postgres"]["condition"] == "service_healthy"
    assert depends["redis"]["condition"] == "service_healthy"
    assert depends["redis-rate-limit"]["condition"] == "service_healthy"

    # Ollama bridge via extra_hosts
    extra_hosts = backend.get("extra_hosts", [])
    assert any("host.docker.internal" in h for h in extra_hosts)

    # Internal service name networking
    env = backend.get("environment", {})
    assert "postgres:5432" in str(env.get("DATABASE_URL", ""))
    assert "redis:6379" in str(env.get("REDIS_URL", ""))
    assert "redis-rate-limit:6379" in str(env.get("REDIS_RATE_LIMIT_URL", ""))
    assert "host.docker.internal:11434" in str(env.get("OLLAMA_BASE_URL", ""))


def test_compose_fails_if_redis_password_missing():
    """Verify docker compose config refuses to start if REDIS_PASSWORD is not provided."""
    env = os.environ.copy()
    env.pop("REDIS_PASSWORD", None)

    res = subprocess.run(
        ["docker", "compose", "config", "-q"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode != 0
    assert "REDIS_PASSWORD must be explicitly configured" in (res.stderr + res.stdout)
