#!/usr/bin/env bash
# EdgeMind Production Deployment Script for OCI Always Free ARM64
# Executes automated near-zero-downtime deployment, database migrations, model preloading, and health verification.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.production.yml"
ENV_FILE="${DEPLOY_DIR}/.env.production"

echo "========================================================================"
echo " Starting EdgeMind Production Deployment on OCI ARM64 VM"
echo " Date: $(date)"
echo "========================================================================"

# Step 1: Validate environment configuration file exists
if [ ! -f "${ENV_FILE}" ]; then
    echo "ERROR: Production environment file .env.production not found at ${ENV_FILE}" >&2
    echo "Please copy ${DEPLOY_DIR}/.env.production.example to ${ENV_FILE} and populate production secrets." >&2
    exit 1
fi

# Step 2: Validate that secrets are not placeholder values
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

MISSING_VARS=0
for var in POSTGRES_PASSWORD REDIS_PASSWORD JWT_SECRET_KEY; do
    VAL="${!var:-}"
    if [ -z "${VAL}" ] || [[ "${VAL}" == *"replace_with"* ]]; then
        echo "ERROR: Mandatory production environment variable '${var}' is not securely configured!" >&2
        MISSING_VARS=$((MISSING_VARS + 1))
    fi
done

if [ "${MISSING_VARS}" -gt 0 ]; then
    echo "Aborting deployment: please configure all required production credentials in ${ENV_FILE}." >&2
    exit 1
fi

echo "Configuration validation passed: required production secrets are configured."

# Step 3: Build and verify container images on ARM64
echo "Building / pulling production containers defined in ${COMPOSE_FILE}..."
docker compose -f "${COMPOSE_FILE}" build backend

# Step 4: Launch data stores and wait for health
echo "Starting PostgreSQL pgvector and Redis services..."
docker compose -f "${COMPOSE_FILE}" up -d postgres redis redis-rate-limit

echo "Waiting for PostgreSQL and Redis to become healthy..."
MAX_ATTEMPTS=30
ATTEMPT=0
until docker compose -f "${COMPOSE_FILE}" exec -T postgres pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-edgemind}" > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ "${ATTEMPT}" -ge "${MAX_ATTEMPTS}" ]; then
        echo "ERROR: PostgreSQL service failed to become ready within timeout." >&2
        exit 1
    fi
    sleep 2
done
echo "PostgreSQL pgvector is healthy."

# Step 5: Execute database migrations through revision 008 (head)
echo "Executing forward Alembic database migrations to head..."
docker compose -f "${COMPOSE_FILE}" run --rm backend alembic upgrade head
echo "Alembic migrations completed successfully."

# Step 6: Launch all services (including Ollama and Caddy reverse proxy)
echo "Starting full production container stack..."
docker compose -f "${COMPOSE_FILE}" up -d

# Step 7: Preload Ollama models on the ARM64 host
echo "Preloading required Ollama models for CPU execution..."
echo "Pulling reasoning model: ${OLLAMA_MODEL:-qwen3:4b}..."
docker compose -f "${COMPOSE_FILE}" exec -T ollama ollama pull "${OLLAMA_MODEL:-qwen3:4b}"

echo "Pulling embedding model: ${OLLAMA_EMBEDDING_MODEL:-all-minilm:latest}..."
docker compose -f "${COMPOSE_FILE}" exec -T ollama ollama pull "${OLLAMA_EMBEDDING_MODEL:-all-minilm:latest}"

echo "Ollama models preloaded and cached in persistent volume."

# Step 8: Verify health endpoint through Caddy reverse proxy
echo "Verifying service health through Caddy reverse proxy..."
HEALTH_OK=0
for i in $(seq 1 15); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/health || true)
    if [ "${HTTP_CODE}" = "200" ]; then
        HEALTH_OK=1
        echo "EdgeMind API is healthy! (HTTP 200 returned from /health)"
        break
    fi
    echo "Waiting for API endpoint to become responsive (attempt ${i}/15, code: ${HTTP_CODE})..."
    sleep 3
done

if [ "${HEALTH_OK}" -ne 1 ]; then
    echo "WARNING: /health endpoint did not respond with 200 within timeout." >&2
    echo "Dumping container statuses:"
    docker compose -f "${COMPOSE_FILE}" ps
    exit 1
fi

echo "========================================================================"
echo " EdgeMind Production Deployment Completed Successfully"
echo " Date: $(date)"
echo "========================================================================"
