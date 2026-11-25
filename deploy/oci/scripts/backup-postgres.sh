#!/usr/bin/env bash
# EdgeMind PostgreSQL Backup Script
# Creates a compressed, timestamped pg_dump of the PostgreSQL pgvector database and rotates old backups.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/opt/edgemind/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
BACKUP_LOCK_FILE="${BACKUP_LOCK_FILE:-${BACKUP_DIR}/.edgemind-backup.lock}"
TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
BACKUP_FILE="${BACKUP_DIR}/edgemind_postgres_${TIMESTAMP}.sql.gz"

cleanup_partial_backup() {
    local exit_code=$?
    if [ "${exit_code}" -ne 0 ] && [ -f "${BACKUP_FILE}" ]; then
        rm -f "${BACKUP_FILE}"
        echo "ERROR: PostgreSQL backup failed (exit ${exit_code}); removed incomplete file ${BACKUP_FILE}" >&2
    fi
}
trap cleanup_partial_backup EXIT

if ! [[ "${RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: RETENTION_DAYS must be a non-negative integer (got '${RETENTION_DAYS}')" >&2
    exit 1
fi

echo "=== EdgeMind PostgreSQL Backup Started: $(date -u +'%Y-%m-%dT%H:%M:%SZ') ==="

# Ensure backup directory exists with restricted permissions (0700)
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

# Prevent overlapping backup runs when invoked concurrently
if command -v flock >/dev/null 2>&1; then
    exec 9>"${BACKUP_LOCK_FILE}"
    if ! flock -n 9; then
        echo "WARNING: Another EdgeMind PostgreSQL backup instance is already running; exiting cleanly." >&2
        exit 0
    fi
fi

# Verify production docker-compose file exists
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.production.yml"
if [ ! -f "${COMPOSE_FILE}" ]; then
    echo "ERROR: Production compose file not found at ${COMPOSE_FILE}" >&2
    exit 1
fi

# Load environment variables from .env.production if present
ENV_FILE="${DEPLOY_DIR}/.env.production"
if [ -f "${ENV_FILE}" ]; then
    # Export environment variables for docker compose interpolation
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-edgemind}"

echo "Creating compressed pg_dump from container 'edgemind-prod-postgres' (Database: ${POSTGRES_DB}, User: ${POSTGRES_USER})..."

# Execute pg_dump inside container and stream directly to gzip
docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists --no-owner --no-privileges \
    | gzip -9 > "${BACKUP_FILE}"

# Verify backup integrity
if [ ! -s "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file was created but is empty: ${BACKUP_FILE}" >&2
    rm -f "${BACKUP_FILE}"
    exit 1
fi

gzip -t "${BACKUP_FILE}"
BACKUP_SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
echo "SUCCESS: Backup completed and verified. File: ${BACKUP_FILE} (Size: ${BACKUP_SIZE})"

# Backup Rotation: Purge backups older than RETENTION_DAYS
echo "Applying backup retention policy: deleting backups older than ${RETENTION_DAYS} days in ${BACKUP_DIR}..."
DELETED_COUNT=0
while IFS= read -r old_backup; do
    if [ -n "${old_backup}" ]; then
        echo "Removing expired backup: ${old_backup}"
        rm -f "${old_backup}"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    fi
done < <(find "${BACKUP_DIR}" -type f -name "edgemind_postgres_*.sql.gz" -mtime +"${RETENTION_DAYS}")

echo "Backup rotation complete. Expired backups removed: ${DELETED_COUNT}"
echo "=== EdgeMind PostgreSQL Backup Finished: $(date) ==="
