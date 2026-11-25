# EdgeMind Production Deployment on Oracle Cloud Infrastructure (OCI) Always Free ARM64

This directory contains the production infrastructure and deployment automation for EdgeMind on an **Oracle Cloud Infrastructure (OCI) Always Free ARM64 Ampere A1** virtual machine.

---

## 1. Architecture Overview

```
                      INTERNET / CLIENTS
                              │
               ┌──────────────┴──────────────┐
               │    Port 80 (HTTP ACME)      │
               │    Port 443 (HTTPS TLS)     │
               └──────────────┬──────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Caddy Reverse   │
                    │   Proxy Container │
                    └─────────┬─────────┘
                              │ Internal Docker Network (edgemind-prod-net)
          ┌───────────────────┼───────────────────┐
          │                   │                   │
┌─────────▼─────────┐ ┌───────▼─────────┐ ┌───────▼─────────┐
│ FastAPI Backend   │ │ Redis Cache     │ │ Redis Rate      │
│ (UID 10001)       │ │ (Port 6379, LRU)│ │ Limiter (6380)  │
└─────────┬─────────┘ └─────────────────┘ └─────────────────┘
          │
    ┌─────┴─────────────────┐
    │                       │
┌───▼─────────────┐   ┌─────▼───────────┐
│ PostgreSQL 16   │   │ Ollama Service  │
│ + pgvector 0.8  │   │ (Qwen3 4B CPU   │
│ (Port 5432)     │   │ + all-minilm)   │
└─────────────────┘   └─────────────────┘
```

- **Target Instance**: OCI `VM.Standard.A1.Flex` (Ampere A1 ARM64).
- **Resource Footprint**: 2 OCPUs, 12 GB RAM, 100 GB Boot Volume (well within Always Free limits of 4 OCPUs, 24 GB RAM, 200 GB volume).
- **Public Ports**: Only ports `80` (HTTP) and `443` (HTTPS) are exposed for Web traffic. Port `22` is restricted to authorized administrator IPs.
- **Internal Ports**: PostgreSQL (`5432`), Redis (`6379`), Redis Rate Limiter (`6380`), Backend (`8000`), and Ollama (`11434`) are strictly private to `edgemind-prod-net`.

---

## 2. Directory Structure

```
deploy/oci/
├── Caddyfile                         # Caddy reverse proxy TLS & security configuration
├── cloud-init.yaml                   # Host VM cloud-init bootstrap (Docker, UFW, sysctl)
├── docker-compose.production.yml     # Production multi-container orchestration
├── .env.production.example           # Production environment variable template
├── README.md                         # This deployment guide
├── scripts/
│   ├── backup-postgres.sh            # Automated pg_dump backup with 7-day retention rotation
│   ├── restore-postgres.sh           # Verified database restoration with safety gates
│   ├── deploy.sh                     # Automated zero-downtime deployment & migration script
│   └── setup-firewall.sh             # Host-level firewall hardening script
└── terraform/
    ├── provider.tf                   # OCI Terraform provider definition
    ├── variables.tf                  # Infrastructure input variables
    ├── main.tf                       # VCN, subnets, security lists, and A1 VM definition
    ├── outputs.tf                    # Public IP, instance OCID, and connection strings
    └── terraform.tfvars.example      # Example Terraform parameters
```

---

## 3. Prerequisites & Manual OCI Account Setup

1. **Create an Oracle Cloud Account**:
   - Register at [https://www.oracle.com/cloud/free/](https://www.oracle.com/cloud/free/).
   - Ensure an Always Free eligible home region is selected (e.g., `us-ashburn-1`, `us-phoenix-1`, `eu-frankfurt-1`).

2. **Generate API Signing Key**:
   - In the OCI Console, navigate to **Profile > User Settings > API Keys > Add API Key**.
   - Download the private key (`oci_api_key.pem`) and copy the configuration snippet (containing `tenancy_ocid`, `user_ocid`, `fingerprint`, and `region`).

3. **Generate SSH Key Pair**:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/edgemind_oci -C "edgemind-oci-admin"
   ```

---

## 4. Terraform Provisioning

1. Navigate to the Terraform directory:
   ```bash
   cd deploy/oci/terraform
   cp terraform.tfvars.example terraform.tfvars
   ```
2. Populate `terraform.tfvars` with your OCI tenancy credentials and SSH public key.
3. Validate and preview the plan:
   ```bash
   terraform init
   terraform plan
   ```
4. Deploy the infrastructure:
   ```bash
   terraform apply
   ```
5. Note the outputs:
   - `instance_public_ip`
   - `ssh_connection_command`

---

## 5. Application Configuration & Deployment

1. SSH into the provisioned instance:
   ```bash
   ssh ubuntu@<INSTANCE_PUBLIC_IP>
   ```
2. Clone or synchronize the EdgeMind repository to `/opt/edgemind`:
   ```bash
   sudo git clone https://github.com/whiskerwolf/EdgeMind.git /opt/edgemind
   sudo chown -R ubuntu:ubuntu /opt/edgemind
   cd /opt/edgemind/deploy/oci
   ```
3. Create the production environment file:
   ```bash
   cp .env.production.example .env.production
   ```
4. Generate secure 32-byte cryptographic hex tokens on the server:
   ```bash
   # Generate PostgreSQL password
   openssl rand -hex 32
   # Generate Redis password
   openssl rand -hex 32
   # Generate JWT Secret Key
   openssl rand -hex 32
   ```
   Paste these tokens into `.env.production`.
5. Execute the deployment script:
   ```bash
   ./scripts/deploy.sh
   ```

### Deployment Downtime Characteristics & Blue-Green Path
- **Standard Compose Transition**: The automated script uses `docker compose up -d`, which provides **near-zero-downtime** with a brief service transition window (~2–5 seconds) while the backend container restarts and initializes Uvicorn.
- **Mission-Critical Zero-Downtime**: To achieve strict 0-millisecond downtime, configure a blue-green upstream topology in `Caddyfile` with two backend container instances (`backend_blue:8000` and `backend_green:8000`) and use active health-checking (`health_uri /health`) before traffic cutover.

---

## 6. Automated Backups, Database Maintenance & Restoration

EdgeMind uses host-level **systemd timers** (`deploy/oci/systemd/`) rather than an in-process Python scheduler daemon. Running backups and database maintenance as `Type=oneshot` units eliminates background memory overhead on ARM64 nodes, ensures single-instance execution (`flock` + systemd serialization), and routes sanitized logs directly to `systemd-journald`.

### Enabling Scheduled Timers (Recommended)

Install and enable both daily timers on the OCI host:
```bash
sudo /opt/edgemind/deploy/oci/scripts/install-systemd-timers.sh
systemctl list-timers 'edgemind-*'
```

### Schedules & Retention Policies

| Job | Systemd Timer | Default Schedule | Persistent Storage / Target | Retention / Policy |
| --- | --- | --- | --- | --- |
| **PostgreSQL Backup** | `edgemind-backup.timer` | `*-*-* 02:00:00 UTC` (+5m jitter) | `/opt/edgemind/backups` (`0700` permissions) | Keeps `RETENTION_DAYS=7` days of verified `edgemind_postgres_*.sql.gz` dumps |
| **DB Token Maintenance** | `edgemind-maintenance.timer` | `*-*-* 03:00:00 UTC` (+5m jitter) | `refresh_tokens` table via `python -m core.auth.maintenance` | Prunes tokens expired `> TOKEN_CLEANUP_GRACE_DAYS` (`1`d) or revoked `> TOKEN_CLEANUP_REVOKED_GRACE_DAYS` (`7`d) |

- **Backup Safety**: `scripts/backup-postgres.sh` reuses `docker compose exec -T postgres pg_dump`, verifies archive integrity (`gzip -t`), cleans up incomplete files on failure, enforces `flock` single-instance locking, and never prints database passwords.
- **Maintenance Safety**: `core.auth.maintenance` never deletes active unexpired refresh tokens (`is_revoked=False`), user accounts, or historical analysis reports. Recently revoked tokens remain within their reuse-detection window until expired or older than `TOKEN_CLEANUP_REVOKED_GRACE_DAYS`.

### Configuration Variables & Schedule Overrides

Runtime policy variables can be configured in `/etc/edgemind/maintenance.env` (created automatically from `deploy/oci/systemd/maintenance.env.example`) or `deploy/oci/.env.production`:
- `BACKUP_DIR` (default: `/opt/edgemind/backups`)
- `RETENTION_DAYS` (default: `7`)
- `TOKEN_CLEANUP_GRACE_DAYS` (default: `1`)
- `TOKEN_CLEANUP_REVOKED_GRACE_DAYS` (default: `7`)

To customize a timer schedule cleanly without modifying tracked files:
```bash
sudo systemctl edit edgemind-backup.timer
# Example drop-in override for twice-daily backups:
# [Timer]
# OnCalendar=
# OnCalendar=*-*-* 02,14:00:00 UTC
```

For environments without systemd, you can trigger the same wrappers via root/ubuntu crontab:
```cron
0 2 * * * /opt/edgemind/deploy/oci/scripts/backup-postgres.sh >> /var/log/edgemind-backup.log 2>&1
0 3 * * * /opt/edgemind/deploy/oci/scripts/run-db-maintenance.sh >> /var/log/edgemind-maintenance.log 2>&1
```

### Dry-Run & Manual Verification

```bash
# Preview eligible expired/revoked refresh tokens without deleting anything
./scripts/run-db-maintenance.sh --dry-run

# Trigger an immediate on-demand backup or maintenance run
sudo systemctl start edgemind-backup.service
sudo systemctl start edgemind-maintenance.service
```

### Database Restoration

Verify and restore any backup archive cleanly:
```bash
gzip -t /opt/edgemind/backups/edgemind_postgres_YYYYMMDD_HHMMSS.sql.gz
./scripts/restore-postgres.sh /opt/edgemind/backups/edgemind_postgres_YYYYMMDD_HHMMSS.sql.gz --confirm
```

### Troubleshooting Scheduled Jobs

- **Inspect execution history and failures**:
  ```bash
  journalctl -u edgemind-backup.service -n 50 --no-pager
  journalctl -u edgemind-maintenance.service -n 50 --no-pager
  systemctl status edgemind-backup.timer edgemind-maintenance.timer
  ```
- **Maintenance exited non-zero ("backend service is not running")**: Confirm the stack is healthy with `docker compose -f docker-compose.production.yml ps` and rerun `./scripts/deploy.sh` if containers are stopped.
- **Database unconfigured in local/stateless tests**: `python -m core.auth.maintenance` exits `0` cleanly with a warning log instead of crashing.
- **Lock contention warning (`Another ... instance is already running`)**: A prior run is still executing; check `ps aux` or remove a stale lock file only after verifying no job is active.

---

## 7. AI Inference on ARM64 CPU

- EdgeMind runs **Qwen 3 4B** and **all-minilm:latest** embeddings natively on ARM64 Ampere A1 Neoverse N1 cores.
- `OLLAMA_NUM_PARALLEL=1` guarantees predictable, bounded CPU utilization without context thrashing.
- Models persist in the Docker volume `ollama_prod_data` across container restarts.
