"""
Tests for Phase 7B and 7C: Production Deployment Infrastructure targeting OCI Always Free ARM64.

Validates:
1. Terraform HCL structure, Always Free limits, and network security invariants.
2. Production Docker Compose multi-container configuration (6 services, memory limits, port isolation).
3. Caddy reverse proxy configuration, security headers, and TLS termination.
4. Cloud-init initialization and host firewall hardening.
5. Database backup automation, retention rotation, and safe restoration scripts.
6. Automated deployment script and Alembic migration alignment.
7. GitHub Actions manual deployment workflow.
8. ARM64 image compatibility and memory bounds within 12 GB.
"""

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_OCI_DIR = REPO_ROOT / "deploy" / "oci"
TERRAFORM_DIR = DEPLOY_OCI_DIR / "terraform"
SCRIPTS_DIR = DEPLOY_OCI_DIR / "scripts"


def test_terraform_files_exist_and_structure():
    """Verify all required Terraform files exist in deploy/oci/terraform."""
    assert TERRAFORM_DIR.exists()
    required_files = [
        "provider.tf",
        "variables.tf",
        "main.tf",
        "outputs.tf",
        "terraform.tfvars.example",
    ]
    for filename in required_files:
        path = TERRAFORM_DIR / filename
        assert path.exists(), f"Missing required Terraform file: {filename}"
        assert path.stat().st_size > 50, f"Terraform file {filename} is too small or empty"


def test_terraform_hcl_syntax_and_always_free_invariants():
    """Verify Terraform configuration complies with OCI Always Free ARM64 constraints."""
    main_tf = (TERRAFORM_DIR / "main.tf").read_text(encoding="utf-8")
    vars_tf = (TERRAFORM_DIR / "variables.tf").read_text(encoding="utf-8")

    # 1. Instance Shape & Shape Config
    assert 'var.instance_shape' in main_tf
    assert 'default     = "VM.Standard.A1.Flex"' in vars_tf

    # 2. Always Free CPU & Memory bounds (2 OCPUs, 12 GB RAM)
    assert 'default     = 2' in vars_tf, "Default OCPUs must be 2"
    assert 'default     = 12' in vars_tf, "Default memory must be 12 GB"
    assert 'default     = 100' in vars_tf, "Default boot volume must be 100 GB (<= 200 GB limit)"

    # 3. Network Security List Rules: Ports 22, 80, 443 permitted
    assert 'min = 22' in main_tf and 'max = 22' in main_tf, "Must configure SSH port 22 rule"
    assert 'min = 80' in main_tf and 'max = 80' in main_tf, "Must configure HTTP port 80 rule"
    assert 'min = 443' in main_tf and 'max = 443' in main_tf, "Must configure HTTPS port 443 rule"

    # 4. Strict isolation: Ingress security list must NEVER open database or Ollama ports
    for forbidden_port in [5432, 6379, 6380, 8000, 11434]:
        pattern = rf'min\s*=\s*{forbidden_port}'
        assert not re.search(pattern, main_tf), f"Port {forbidden_port} must not be exposed in Terraform security list"


def test_docker_compose_production_services_and_isolation():
    """Verify production compose file services, memory limits, and strict port isolation."""
    compose_path = DEPLOY_OCI_DIR / "docker-compose.production.yml"
    assert compose_path.exists(), "docker-compose.production.yml must exist"

    content = compose_path.read_text(encoding="utf-8")

    # 1. Services Defined
    required_services = ["caddy:", "backend:", "postgres:", "redis:", "redis-rate-limit:", "ollama:"]
    for svc in required_services:
        assert svc in content, f"Missing required service definition: {svc}"

    # 2. Port Exposure Isolation: Only Caddy publishes host ports 80:80 and 443:443
    assert '"80:80"' in content
    assert '"443:443"' in content
    # Assert internal ports are not published in ports blocks
    for forbidden in ['"5432:5432"', '"6379:6379"', '"6380:6379"', '"8000:8000"', '"11434:11434"']:
        assert forbidden not in content, f"Internal port {forbidden} must not be exposed"

    # 3. Redis Authentication & Memory Isolation
    assert "--requirepass" in content, "Redis must enforce requirepass"
    assert "--maxmemory 256mb" in content, "Redis cache must limit memory to 256MB"
    assert "--maxmemory-policy allkeys-lru" in content, "Redis cache must use allkeys-lru eviction"
    assert "--maxmemory 128mb" in content, "Redis rate limit must limit memory to 128MB"
    assert "--maxmemory-policy noeviction" in content, "Redis rate limit must use noeviction"

    # 4. Ollama CPU concurrency on ARM64
    assert "OLLAMA_NUM_PARALLEL: 1" in content, "Ollama must limit parallel inference to 1 for CPU"
    assert "OLLAMA_MAX_LOADED_MODELS: 2" in content, "Ollama must limit loaded models to 2"

    # 5. Resource limits defined
    assert "memory: 6144M" in content, "Ollama must be allocated 6GB"
    assert "memory: 1536M" in content, "Postgres and Backend must be bounded"
    assert "memory: 384M" in content, "Redis cache must be bounded"
    assert "memory: 256M" in content, "Redis rate limit & Caddy must be bounded"


def test_caddyfile_security_headers_and_reverse_proxy():
    """Verify Caddyfile reverse proxy to backend, security headers, and request limits."""
    caddy_path = DEPLOY_OCI_DIR / "Caddyfile"
    assert caddy_path.exists(), "Caddyfile must exist"

    content = caddy_path.read_text(encoding="utf-8")
    assert "reverse_proxy backend:8000" in content, "Caddy must reverse proxy to backend:8000"
    assert "Strict-Transport-Security" in content, "Must configure HSTS"
    assert "X-Content-Type-Options" in content
    assert "X-Frame-Options" in content
    assert "max_size 10MB" in content, "Must limit request body size"
    assert "encode zstd gzip" in content, "Must enable compression"


def test_cloud_init_security_and_sysctl_hardening():
    """Verify cloud-init installs Docker, tunes sysctl for Redis, and configures UFW."""
    cloud_init_path = DEPLOY_OCI_DIR / "cloud-init.yaml"
    assert cloud_init_path.exists(), "cloud-init.yaml must exist"

    content = cloud_init_path.read_text(encoding="utf-8")
    assert "vm.overcommit_memory = 1" in content, "Must configure memory overcommit for Redis BGSAVE"
    assert "net.core.somaxconn = 1024" in content, "Must increase socket backlog"
    assert "ufw default deny incoming" in content, "Must default deny incoming traffic"
    assert "ufw allow 22/tcp" in content
    assert "ufw allow 80/tcp" in content
    assert "ufw allow 443/tcp" in content
    assert "docker-compose-plugin" in content


def test_backup_and_restore_scripts_integrity():
    """Verify PostgreSQL backup, rotation, and restoration scripts."""
    backup_sh = (SCRIPTS_DIR / "backup-postgres.sh").read_text(encoding="utf-8")
    restore_sh = (SCRIPTS_DIR / "restore-postgres.sh").read_text(encoding="utf-8")

    # Safety: strict error handling
    assert "set -euo pipefail" in backup_sh
    assert "set -euo pipefail" in restore_sh

    # Backup: pg_dump, gzip, rotation
    assert "pg_dump" in backup_sh
    assert "gzip" in backup_sh
    assert "RETENTION_DAYS" in backup_sh
    assert "-mtime" in backup_sh

    # Restore: safety checks, gzip verification, confirmation gate, migration alignment
    assert "gzip -t" in restore_sh, "Restore script must verify gzip archive integrity"
    assert "--confirm" in restore_sh, "Restore script must provide confirmation safety gate"
    assert "alembic upgrade head" in restore_sh, "Restore script must align migrations post-restoration"


def test_deploy_script_flow_and_migrations():
    """Verify deploy.sh checks production secrets, runs migrations, and preloads models."""
    deploy_sh = (SCRIPTS_DIR / "deploy.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in deploy_sh
    assert ".env.production" in deploy_sh
    assert "POSTGRES_PASSWORD" in deploy_sh
    assert "REDIS_PASSWORD" in deploy_sh
    assert "JWT_SECRET_KEY" in deploy_sh
    assert "alembic upgrade head" in deploy_sh, "Must run migrations to head"
    assert "ollama pull" in deploy_sh, "Must preload Ollama models"
    assert "/health" in deploy_sh, "Must verify health endpoint"


def test_github_actions_oci_deploy_workflow():
    """Verify .github/workflows/deploy-oci.yml triggers, inputs, and secret handling."""
    deploy_wf_path = REPO_ROOT / ".github" / "workflows" / "deploy-oci.yml"
    assert deploy_wf_path.exists(), "deploy-oci.yml must exist"

    content = deploy_wf_path.read_text(encoding="utf-8")
    # Must only trigger on workflow_dispatch (manual trigger)
    assert "workflow_dispatch:" in content, "Must be manually triggered"
    assert "push:" not in content, "Must NOT trigger on automatic push"
    assert "pull_request:" not in content, "Must NOT trigger on pull_request"

    # Least privilege permissions
    assert "permissions:" in content
    assert "contents: read" in content

    # Uses deployment secrets
    assert "secrets.OCI_HOST" in content
    assert "secrets.OCI_SSH_USER" in content
    assert "secrets.OCI_SSH_KEY" in content


def test_arm64_image_compatibility():
    """Verify that all configured images natively support the linux/arm64 architecture."""
    compose_path = DEPLOY_OCI_DIR / "docker-compose.production.yml"
    content = compose_path.read_text(encoding="utf-8")

    # Pinning and multi-arch image tags
    assert "caddy:2.9.1-alpine" in content, "Caddy multi-arch image"
    assert "pgvector/pgvector:0.8.7-pg16" in content, "pgvector official arm64 image"
    assert "redis:7.2.17-alpine3.21" in content, "Redis 7.2 LTS arm64 image"
    assert "ollama/ollama:0.5.7" in content, "Ollama official arm64 image"

    dockerfile_path = REPO_ROOT / "Dockerfile"
    df_content = dockerfile_path.read_text(encoding="utf-8")
    assert "python:3.12-slim" in df_content, "Python 3.12-slim is official multi-arch Debian Bookworm image"


def test_extension_manifest_development_and_production_domain_generation():
    """Verify base manifest has localhost permissions and production manifest generates exact domain."""
    import json
    from scripts.package_extension import generate_manifest

    manifest_path = REPO_ROOT / "extension" / "edgemind" / "manifest.json"
    assert manifest_path.exists()
    base_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 1. Base Development Manifest: strictly localhost, no broad wildcards
    dev_perms = base_manifest.get("host_permissions", [])
    assert "http://127.0.0.1:8000/*" in dev_perms
    assert "http://localhost:8000/*" in dev_perms
    assert "https://*/*" not in dev_perms, "Broad https wildcard must not be in base manifest"
    assert "*://*/*" not in dev_perms
    assert "<all_urls>" not in dev_perms

    # 2. Production Manifest Generation: exact configured domain
    prod_manifest = generate_manifest(base_manifest, mode="production", api_domain="edgemind.example.com")
    prod_perms = prod_manifest.get("host_permissions", [])
    assert prod_perms == ["https://edgemind.example.com/*"]

    # 3. Rejection of broad wildcards in production manifest generation
    import pytest
    with pytest.raises(ValueError, match="Broad or invalid domain wildcard prohibited"):
        generate_manifest(base_manifest, mode="production", api_domain="*")


def test_cors_exact_extension_id_production_security():
    """Verify CORS accepts only the configured production extension ID and rejects arbitrary origins."""
    import pytest
    from core.config import Settings

    valid_id = "abcdefghijklmnopabcdefghijklmnop"
    other_id = "ponmlkjihgfedcbaponmlkjihgfedcba"

    # 1. Production with exact extension ID configured
    prod_settings = Settings(
        environment="production",
        debug=False,
        jwt_secret_key="mock_secret_key_32chars_minimum",
        edgemind_chrome_extension_id=valid_id,
    )
    assert prod_settings.cors_origin_regex is not None
    # Must accept configured ID
    assert re.match(prod_settings.cors_origin_regex, f"chrome-extension://{valid_id}")
    # Must reject other extension IDs
    assert not re.match(prod_settings.cors_origin_regex, f"chrome-extension://{other_id}")
    # Must reject arbitrary web origins
    assert not re.match(prod_settings.cors_origin_regex, "https://malicious.com")

    # 2. Production WITHOUT extension ID configured (unrestricted regex eliminated)
    prod_no_ext = Settings(
        environment="production",
        debug=False,
        jwt_secret_key="mock_secret_key_32chars_minimum",
        edgemind_chrome_extension_id=None,
    )
    assert prod_no_ext.cors_origin_regex is None, "In production without extension ID, regex must be disabled"

    # 3. Development environment keeps separate default unpacked extension support
    dev_settings = Settings(
        environment="development",
        debug=True,
        edgemind_chrome_extension_id=None,
    )
    assert dev_settings.cors_origin_regex == r"^chrome-extension://[a-p]{32}$"
    assert re.match(dev_settings.cors_origin_regex, f"chrome-extension://{valid_id}")
    assert re.match(dev_settings.cors_origin_regex, f"chrome-extension://{other_id}")

    # 4. Invalid extension ID format rejected fast
    with pytest.raises(ValueError, match="Invalid EDGEMIND_CHROME_EXTENSION_ID"):
        Settings(
            environment="production",
            debug=False,
            jwt_secret_key="mock_secret_key_32chars_minimum",
            edgemind_chrome_extension_id="invalid-id-too-short",
        )
