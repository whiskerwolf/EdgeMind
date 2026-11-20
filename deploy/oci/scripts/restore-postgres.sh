#!/usr/bin/env bash
# EdgeMind PostgreSQL Database Restoration Script
# Restores a compressed pg_dump archive into the production PostgreSQL pgvector database with safety checks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
    echo "Usage: $0 <path_to_backup.sql.gz> [--confirm]"
    echo ""
    echo "Examples:"
    echo "  $0 /opt/edgemind/backups/edgemind_postgres_20261120_120000.sql.gz"
    echo "  $0 /opt/edgemind/backups/edgemind_postgres_20261120_120000.sql.gz --confirm"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

BACKUP_FILE="$1"
CONFIRM="${2:-}"

# Validation 1: Backup file must exist and be non-empty
if [ ! -f "${BACKUP_FILE}" ] || [ ! -s "${BACKUP_FILE}" ]; then
    echo "ERROR: Specified backup file does not exist or is empty: ${BACKUP_FILE}" >&2
    exit 1
fi

# Validation 2: Verify gzip integrity before touching the database
echo "Verifying gzip archive integrity of ${BACKUP_FILE}..."
if ! gzip -t "${BACKUP_FILE}"; then
    echo "ERROR: Corrupt or invalid gzip archive: ${BACKUP_FILE}" >&2
    exit 1
fi
echo "Gzip archive integrity check passed."

# Validation 3: Confirmation safety gate
if [ "${CONFIRM}" != "--confirm" ]; then
    echo "======================================================================"
    echo "WARNING: Restoring will overwrite existing data in the production database!"
    echo "Target Backup Archive: ${BACKUP_FILE}"
    echo "======================================================================"
    read -r -p "Are you sure you want to proceed with restoration? (yes/NO): " response
    if [ "${response}" != "yes" ]; then
        echo "Restoration aborted by operator."
        exit 0
    fi
fi

COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.production.yml"
ENV_FILE="${DEPLOY_DIR}/.env.production"
if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-edgemind}"

echo "Checking postgres container availability..."
docker compose -f "${COMPOSE_FILE}" exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "Restoring database from ${BACKUP_FILE}..."
gunzip -c "${BACKUP_FILE}" | docker compose -f "${COMPOSE_FILE}" exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "Running Alembic migrations to ensure schema aligns with revision 008 (head)..."
docker compose -f "${COMPOSE_FILE}" run --rm backend alembic upgrade head

echo "Restoration and migration alignment completed successfully at $(date)."
