#!/usr/bin/env bash
# Install and enable EdgeMind OCI systemd backup & database maintenance timers.
# Safe to re-run idempotently.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SYSTEMD_SRC_DIR="${DEPLOY_DIR}/systemd"
SYSTEMD_DEST_DIR="${SYSTEMD_DEST_DIR:-/etc/systemd/system}"
MAINTENANCE_ENV_DIR="${MAINTENANCE_ENV_DIR:-/etc/edgemind}"
MAINTENANCE_ENV_FILE="${MAINTENANCE_ENV_DIR}/maintenance.env"
SKIP_SYSTEMCTL="${SKIP_SYSTEMCTL:-false}"

for arg in "$@"; do
    case "${arg}" in
        --no-enable)
            SKIP_SYSTEMCTL="true"
            ;;
        *)
            echo "ERROR: Unsupported argument '${arg}' (supported: --no-enable)" >&2
            exit 2
            ;;
    esac
done

if [ ! -d "${SYSTEMD_SRC_DIR}" ]; then
    echo "ERROR: Systemd unit directory not found at ${SYSTEMD_SRC_DIR}" >&2
    exit 1
fi

mkdir -p "${SYSTEMD_DEST_DIR}" "${MAINTENANCE_ENV_DIR}"
chmod 750 "${MAINTENANCE_ENV_DIR}"

if [ ! -f "${MAINTENANCE_ENV_FILE}" ] && [ -f "${SYSTEMD_SRC_DIR}/maintenance.env.example" ]; then
    cp "${SYSTEMD_SRC_DIR}/maintenance.env.example" "${MAINTENANCE_ENV_FILE}"
    chmod 600 "${MAINTENANCE_ENV_FILE}"
    echo "Created default maintenance override file at ${MAINTENANCE_ENV_FILE}"
fi

for unit in \
    edgemind-backup.service \
    edgemind-backup.timer \
    edgemind-maintenance.service \
    edgemind-maintenance.timer; do
    src="${SYSTEMD_SRC_DIR}/${unit}"
    dest="${SYSTEMD_DEST_DIR}/${unit}"
    if [ ! -f "${src}" ]; then
        echo "ERROR: Missing systemd unit template: ${src}" >&2
        exit 1
    fi
    sed "s|/opt/edgemind/deploy/oci|${DEPLOY_DIR}|g" "${src}" > "${dest}"
    chmod 644 "${dest}"
    echo "Installed ${dest}"
done

if [ "${SKIP_SYSTEMCTL}" != "true" ] && command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl enable --now edgemind-backup.timer edgemind-maintenance.timer
    echo "Enabled and started edgemind-backup.timer and edgemind-maintenance.timer"
else
    echo "Skipped systemctl activation (SKIP_SYSTEMCTL=${SKIP_SYSTEMCTL})."
fi
