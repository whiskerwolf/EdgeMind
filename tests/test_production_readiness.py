"""
Tests for Phase 7A: Production Readiness, Security Invariants, and GitHub Actions CI/CD.

Validates:
1. Production environment safety invariants (DEBUG=False, STATIC_ONLY=True).
2. Production Redis security enforcement (password required in production).
3. Production JWT secret configuration validation.
4. GitHub Actions CI pipeline structure (.github/workflows/ci.yml).
5. Least-privilege permissions, triggers, and service dependencies in CI.
6. Completeness of production deployment documentation (docs/deployment/production.md).
7. Repository secret hygiene and ignore patterns.
"""

import os
from pathlib import Path
import pytest
from pydantic import ValidationError

from core.config import Settings


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_production_mode_requires_debug_false():
    """Verify that Settings rejects DEBUG=True when ENVIRONMENT=production."""
    # When debug is False in production, Settings instantiation must succeed
    prod_valid = Settings(
        environment="production",
        debug=False,
        static_only=True,
        jwt_secret_key="mock_secret_key_32chars_minimum",
    )
    assert prod_valid.environment == "production"
    assert prod_valid.debug is False
    assert prod_valid.static_only is True

    # When debug is True in production, Settings must raise ValidationError
    with pytest.raises((ValidationError, ValueError)) as exc_info:
        Settings(
            environment="production",
            debug=True,
            static_only=True,
            jwt_secret_key="mock_secret_key_32chars_minimum",
        )
    assert "DEBUG must be False in production environment" in str(exc_info.value)


def test_static_only_cannot_be_disabled():
    """Verify that static_only=False is strictly prohibited across all environments."""
    with pytest.raises((ValidationError, ValueError)) as exc_info:
        Settings(
            environment="development",
            debug=False,
            static_only=False,
        )
    assert "static_only must remain True" in str(exc_info.value)


def test_production_redis_requires_explicit_password():
    """Verify that validate_redis_security raises RuntimeError in production without passwords."""
    prod_no_pass = Settings(
        environment="production",
        debug=False,
        redis_url="redis://127.0.0.1:6379/0",
        redis_password=None,
        jwt_secret_key="mock_secret_key_32chars_minimum",
    )
    with pytest.raises(RuntimeError) as exc_info:
        prod_no_pass.validate_redis_security()
    assert "REDIS_PASSWORD must be explicitly configured in production" in str(exc_info.value)

    prod_valid_pass = Settings(
        environment="production",
        debug=False,
        redis_url="redis://:super_secret@127.0.0.1:6379/0",
        redis_password="super_secret",
        jwt_secret_key="mock_secret_key_32chars_minimum",
    )
    # Must not raise when password is provided
    prod_valid_pass.validate_redis_security()


def test_jwt_secret_key_required_in_production():
    """Verify get_jwt_secret_key fails fast if secret key is missing or blank."""
    settings_no_jwt = Settings(
        environment="testing",
        debug=False,
        jwt_secret_key=None,
    )
    with pytest.raises(RuntimeError) as exc_info:
        settings_no_jwt.get_jwt_secret_key()
    assert "JWT secret key is not configured" in str(exc_info.value)

    settings_with_jwt = Settings(
        environment="testing",
        debug=False,
        jwt_secret_key="valid_production_secret_key_32chars",
    )
    assert settings_with_jwt.get_jwt_secret_key() == "valid_production_secret_key_32chars"


def test_github_actions_ci_workflow_structure():
    """Verify .github/workflows/ci.yml triggers, permissions, and service topology."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_path.exists(), ".github/workflows/ci.yml must exist"

    content = ci_path.read_text(encoding="utf-8")

    # 1. Triggers
    assert "feature/assessment-score-6" in content, "Must trigger on push to feature/assessment-score-6"
    assert "pull_request:" in content, "Must trigger on pull_request"
    assert "main" in content, "Must target main branch"
    assert "workflow_dispatch:" in content, "Must support manual workflow_dispatch"

    # 2. Least privilege
    assert "permissions:" in content
    assert "contents: read" in content

    # 3. Services configured
    assert "pgvector/pgvector:0.8.7-pg16" in content, "Must use pgvector image"
    assert "redis:7.2.17-alpine3.21" in content, "Must use pinned Redis LTS image"
    assert "5433:5432" in content or "5432" in content, "Postgres port mapping"
    assert "6379:6379" in content, "Redis cache port"
    assert "6380:6379" in content, "Redis rate limit port"

    # 4. Migration & testing steps
    assert "alembic upgrade head" in content, "Must run migrations"
    assert "pytest" in content, "Must run test suite"

    # 5. Docker build & no-push constraint
    assert "docker compose config" in content, "Must validate compose config"
    assert "push: false" in content, "Must NOT push images to any registry"

    # 6. Security & audit tooling
    assert "pip-audit" in content, "Must include pip-audit vulnerability scan"
    assert "fetch-depth: 0" in content, "Must fetch complete history for event diff checking"
    assert "actionlint" in content, "Must include actionlint workflow validation"

    # 7. Frontend CI job (reproducible install, test, typecheck, production build)
    assert "frontend-ci:" in content, "Must include frontend-ci job"
    assert "npm ci" in content, "Frontend CI must use reproducible npm ci"
    assert "npm test" in content, "Frontend CI must execute frontend tests"
    assert "tsc -b" in content, "Frontend CI must validate TypeScript"
    assert "npm run build" in content, "Frontend CI must build Vite production bundle"


def test_production_deployment_documentation_completeness():
    """Verify docs/deployment/production.md covers all production requirements."""
    doc_path = REPO_ROOT / "docs" / "deployment" / "production.md"
    assert doc_path.exists(), "docs/deployment/production.md must exist"

    content = doc_path.read_text(encoding="utf-8")

    required_sections = [
        "Production Architecture",
        "Environment Variables",
        "Database",
        "pgvector",
        "Redis",
        "HTTPS",
        "Deployment Procedure",
        "Rollback Procedure",
        "Health Checks",
        "Logging and Monitoring",
        "STATIC_ONLY",
    ]

    for section in required_sections:
        assert section.lower() in content.lower(), f"Missing required section: {section}"


def test_gitignore_and_dockerignore_security_exclusions():
    """Verify .gitignore and .dockerignore exclude sensitive local and environment files."""
    gitignore_path = REPO_ROOT / ".gitignore"
    dockerignore_path = REPO_ROOT / ".dockerignore"

    assert gitignore_path.exists()
    assert dockerignore_path.exists()

    gi_content = gitignore_path.read_text(encoding="utf-8")
    di_content = dockerignore_path.read_text(encoding="utf-8")

    # .env must be excluded everywhere
    assert ".env" in gi_content
    assert ".env" in di_content

    # Local databases and caches must be excluded
    for pattern in ["*.db", "*.sqlite", "*.rdb", "__pycache__"]:
        assert pattern in gi_content
        assert pattern in di_content
