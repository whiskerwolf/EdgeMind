#!/usr/bin/env bash
# EdgeMind Scheduled Database Maintenance Wrapper
# Executes safe, idempotent cleanup of expired/aged-revoked refresh tokens
# inside the running production backend container without exposing credentials.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.production.yml"
ENV_FILE="${DEPLOY_DIR}/.env.production"
MAINTENANCE_LOCK_FILE="${MAINTENANCE_LOCK_FILE:-/tmp/edgemind-db-maintenance.lock}"
TOKEN_CLEANUP_GRACE_DAYS="${TOKEN_CLEANUP_GRACE_DAYS:-1}"
TOKEN_CLEANUP_REVOKED_GRACE_DAYS="${TOKEN_CLEANUP_REVOKED_GRACE_DAYS:-7}"
MAINTENANCE_DRY_RUN="${MAINTENANCE_DRY_RUN:-false}"

for arg in "$@"; do
    case "${arg}" in
        --dry-run)
            MAINTENANCE_DRY_RUN="true"
            ;;
        *)
            echo "ERROR: Unsupported argument '${arg}' (supported: --dry-run)" >&2
            exit 2
            ;;
    esac
done

for numeric_var in TOKEN_CLEANUP_GRACE_DAYS TOKEN_CLEANUP_REVOKED_GRACE_DAYS; do
    val="${!numeric_var}"
    if ! [[ "${val}" =~ ^[0-9]+$ ]]; then
        echo "ERROR: ${numeric_var} must be a non-negative integer (got '${val}')" >&2
        exit 1
    fi
done

if [ ! -f "${COMPOSE_FILE}" ]; then
    echo "ERROR: Production compose file not found at ${COMPOSE_FILE}" >&2
    exit 1
fi

if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

echo "=== EdgeMind Database Maintenance Started: $(date -u +'%Y-%m-%dT%H:%M:%SZ') ==="

# Prevent overlapping maintenance runs when triggered concurrently
if command -v flock >/dev/null 2>&1; then
    exec 9>"${MAINTENANCE_LOCK_FILE}"
    if ! flock -n 9; then
        echo "WARNING: Another EdgeMind database maintenance instance is already running; exiting cleanly." >&2
        exit 0
    fi
fi

if ! docker compose -f "${COMPOSE_FILE}" ps --status running --services | grep -qx "backend"; then
    echo "ERROR: Production 'backend' service is not running; skipping database maintenance." >&2
    exit 1
fi

MAINTENANCE_ARGS=(
    python -m core.auth.maintenance
    --expired-grace-days "${TOKEN_CLEANUP_GRACE_DAYS}"
    --revoked-grace-days "${TOKEN_CLEANUP_REVOKED_GRACE_DAYS}"
)
if [ "${MAINTENANCE_DRY_RUN}" = "true" ]; then
    MAINTENANCE_ARGS+=(--dry-run)
fi

docker compose -f "${COMPOSE_FILE}" exec -T backend "${MAINTENANCE_ARGS[@]}"

echo "=== EdgeMind Database Maintenance Finished: $(date -u +'%Y-%m-%dT%H:%M:%SZ') ==="
