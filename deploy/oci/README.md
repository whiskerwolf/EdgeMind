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

## 6. Database Backups & Restoration

### Automated Daily Backups
Add a cron job on the host VM:
```bash
crontab -e
```
Add the following entry to execute backups daily at 02:00 UTC:
```cron
0 2 * * * /opt/edgemind/deploy/oci/scripts/backup-postgres.sh >> /var/log/edgemind-backup.log 2>&1
```

### Database Restoration
To restore from a backup:
```bash
./scripts/restore-postgres.sh /opt/edgemind/backups/edgemind_postgres_YYYYMMDD_HHMMSS.sql.gz --confirm
```

---

## 7. AI Inference on ARM64 CPU

- EdgeMind runs **Qwen 3 4B** and **all-minilm:latest** embeddings natively on ARM64 Ampere A1 Neoverse N1 cores.
- `OLLAMA_NUM_PARALLEL=1` guarantees predictable, bounded CPU utilization without context thrashing.
- Models persist in the Docker volume `ollama_prod_data` across container restarts.
