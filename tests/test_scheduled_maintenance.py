"""
EdgeMind Scheduled Backups & Database Maintenance Test Suite.

Covers:
1. Safe, idempotent cleanup of expired and aged revoked refresh tokens.
2. Strict preservation of active unexpired sessions and recently revoked tokens
   inside the token reuse-detection window.
3. Dry-run inspection without mutating database state.
4. Graceful stateless / DB-unconfigured behavior and sanitized DB-failure handling.
5. Settings binding for grace-window configuration variables.
6. OCI systemd unit/timer configuration, locking scripts, compose wiring, and docs.
"""

from datetime import datetime, timedelta, timezone
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.auth.maintenance import main as maintenance_main, run_maintenance
from core.auth.security import hash_password, hash_token
from core.auth.service import AuthService
from core.config import get_settings
from core.database.models import Base, RefreshToken, User

REPO_ROOT = Path(__file__).resolve().parent.parent
OCI_DIR = REPO_ROOT / "deploy" / "oci"
SCRIPTS_DIR = OCI_DIR / "scripts"
SYSTEMD_DIR = OCI_DIR / "systemd"


@pytest.fixture(autouse=True)
def reset_settings_cache(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-scheduled-maintenance-suite-very-long")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def sqlite_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def init_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_tables())

    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    yield factory

    async def drop_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(drop_tables())


async def _seed_refresh_token_scenarios(session: AsyncSession, now: datetime) -> dict[str, uuid.UUID]:
    user = User(
        email="maintenance-test@edgemind.local",
        password_hash=hash_password("StrongPass!123"),
        full_name="Maintenance Test User",
        role="user",
        is_active=True,
    )
    session.add(user)
    await session.flush()

    specs = {
        # Active unexpired session -> MUST NEVER BE DELETED
        "active": RefreshToken(
            user_id=user.id,
            token_hash=hash_token("raw-active-token"),
            jti=str(uuid.uuid4()),
            expires_at=now + timedelta(days=6),
            is_revoked=False,
        ),
        # Expired 6 hours ago (inside default 1-day grace window) -> PRESERVED with grace=1
        "expired_within_grace": RefreshToken(
            user_id=user.id,
            token_hash=hash_token("raw-expired-recent"),
            jti=str(uuid.uuid4()),
            expires_at=now - timedelta(hours=6),
            is_revoked=False,
        ),
        # Expired 3 days ago (past 1-day grace window) -> DELETED
        "expired_old": RefreshToken(
            user_id=user.id,
            token_hash=hash_token("raw-expired-old"),
            jti=str(uuid.uuid4()),
            expires_at=now - timedelta(days=3),
            is_revoked=False,
        ),
        # Revoked 2 hours ago, not yet expired -> PRESERVED for reuse detection!
        "revoked_recent_unexpired": RefreshToken(
            user_id=user.id,
            token_hash=hash_token("raw-revoked-recent"),
            jti=str(uuid.uuid4()),
            expires_at=now + timedelta(days=5),
            is_revoked=True,
            revoked_at=now - timedelta(hours=2),
        ),
        # Revoked 10 days ago -> DELETED (past 7-day revoked retention window)
        "revoked_aged": RefreshToken(
            user_id=user.id,
            token_hash=hash_token("raw-revoked-aged"),
            jti=str(uuid.uuid4()),
            expires_at=now + timedelta(days=1),
            is_revoked=True,
            revoked_at=now - timedelta(days=10),
        ),
        # Revoked AND expired -> DELETED
        "revoked_and_expired": RefreshToken(
            user_id=user.id,
            token_hash=hash_token("raw-revoked-expired"),
            jti=str(uuid.uuid4()),
            expires_at=now - timedelta(minutes=15),
            is_revoked=True,
            revoked_at=now - timedelta(hours=4),
        ),
    }

    for token in specs.values():
        session.add(token)
    await session.flush()
    ids = {name: tok.id for name, tok in specs.items()}
    await session.commit()
    return ids


@pytest.mark.anyio
async def test_cleanup_preserves_active_and_recent_reuse_tokens_and_is_idempotent(sqlite_session_factory):
    now = datetime.now(timezone.utc)
    async with sqlite_session_factory() as session:
        ids = await _seed_refresh_token_scenarios(session, now)

    async with sqlite_session_factory() as session:
        service = AuthService(session)
        dry_summary = await service.cleanup_expired_refresh_tokens(
            expired_grace_days=1,
            revoked_grace_days=7,
            dry_run=True,
            now=now,
        )
        await session.rollback()

    assert dry_summary["dry_run"] is True
    assert dry_summary["deleted_count"] == 0
    assert dry_summary["eligible_count"] == 3  # expired_old, revoked_aged, revoked_and_expired

    async with sqlite_session_factory() as session:
        service = AuthService(session)
        first_summary = await service.cleanup_expired_refresh_tokens(
            expired_grace_days=1,
            revoked_grace_days=7,
            dry_run=False,
            now=now,
        )
        await session.commit()

    assert first_summary["deleted_count"] == 3

    async with sqlite_session_factory() as session:
        remaining_ids = set(
            (await session.execute(select(RefreshToken.id))).scalars().all()
        )
        remaining_users = (await session.execute(select(User))).scalars().all()

    assert ids["active"] in remaining_ids
    assert ids["expired_within_grace"] in remaining_ids
    assert ids["revoked_recent_unexpired"] in remaining_ids
    assert ids["expired_old"] not in remaining_ids
    assert ids["revoked_aged"] not in remaining_ids
    assert ids["revoked_and_expired"] not in remaining_ids
    assert len(remaining_users) == 1

    # Idempotent repeat run deletes 0 rows cleanly
    async with sqlite_session_factory() as session:
        second_summary = await AuthService(session).cleanup_expired_refresh_tokens(
            expired_grace_days=1,
            revoked_grace_days=7,
            dry_run=False,
            now=now,
        )
        await session.commit()

    assert second_summary["deleted_count"] == 0


@pytest.mark.anyio
async def test_run_maintenance_skips_cleanly_when_database_unconfigured():
    with patch("core.auth.maintenance.get_session_factory", return_value=None):
        result = await run_maintenance()

    assert result["status"] == "skipped"
    assert result["reason"] == "database_not_configured"
    assert result["deleted_count"] == 0


@pytest.mark.anyio
async def test_run_maintenance_executes_against_session_factory_and_respects_env_config(
    sqlite_session_factory, monkeypatch
):
    monkeypatch.setenv("TOKEN_CLEANUP_GRACE_DAYS", "0")
    monkeypatch.setenv("TOKEN_CLEANUP_REVOKED_GRACE_DAYS", "7")
    get_settings.cache_clear()

    now = datetime.now(timezone.utc)
    async with sqlite_session_factory() as session:
        ids = await _seed_refresh_token_scenarios(session, now)

    with patch("core.auth.maintenance.get_session_factory", return_value=sqlite_session_factory):
        dry_res = await run_maintenance(dry_run=True)
        assert dry_res["status"] == "ok"
        assert dry_res["deleted_count"] == 0
        # With expired_grace_days=0, expired_within_grace (6h old) is also eligible -> 4 total
        assert dry_res["eligible_count"] == 4

        live_res = await run_maintenance(dry_run=False)
        assert live_res["status"] == "ok"
        assert live_res["deleted_count"] == 4

    async with sqlite_session_factory() as session:
        remaining_ids = set(
            (await session.execute(select(RefreshToken.id))).scalars().all()
        )

    assert remaining_ids == {ids["active"], ids["revoked_recent_unexpired"]}


@pytest.mark.anyio
async def test_run_maintenance_sanitizes_database_credentials_on_failure(monkeypatch):
    secret_pw = "SuperSecretPgPass12345"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql+asyncpg://edgemind_admin:{secret_pw}@postgres:5432/edgemind",
    )
    get_settings.cache_clear()

    class BrokenSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *_args, **_kwargs):
            raise RuntimeError(
                f"could not connect postgresql+asyncpg://edgemind_admin:{secret_pw}@postgres:5432/edgemind"
            )

        async def rollback(self):
            pass

    with patch("core.auth.maintenance.get_session_factory", return_value=lambda: BrokenSession()):
        with pytest.raises(RuntimeError) as exc_info:
            await run_maintenance()

    assert secret_pw not in str(exc_info.value)


def test_maintenance_cli_exit_codes_and_json_output(capsys):
    # Stateless unconfigured database exits 0
    with (
        patch("core.auth.maintenance.get_session_factory", return_value=None),
        patch("core.auth.maintenance.close_db", new_callable=AsyncMock),
    ):
        rc = maintenance_main(["--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["status"] == "skipped"

    # Error exit code 1 with sanitized stderr
    with (
        patch("core.auth.maintenance.get_session_factory", side_effect=RuntimeError("db offline")),
        patch("core.auth.maintenance.close_db", new_callable=AsyncMock),
    ):
        err_rc = maintenance_main(["--json"])
    assert err_rc == 1
    err_payload = json.loads(capsys.readouterr().err.strip())
    assert err_payload["status"] == "error"


def test_oci_backup_maintenance_scripts_and_systemd_units():
    backup_script = (SCRIPTS_DIR / "backup-postgres.sh").read_text(encoding="utf-8")
    maint_script = (SCRIPTS_DIR / "run-db-maintenance.sh").read_text(encoding="utf-8")
    install_script = (SCRIPTS_DIR / "install-systemd-timers.sh").read_text(encoding="utf-8")

    # Backup script hardening + reuse
    assert "set -euo pipefail" in backup_script
    assert "flock -n" in backup_script
    assert "cleanup_partial_backup" in backup_script
    assert "RETENTION_DAYS" in backup_script
    assert "POSTGRES_PASSWORD" not in backup_script

    # Maintenance wrapper script
    assert "set -euo pipefail" in maint_script
    assert "flock -n" in maint_script
    assert "python -m core.auth.maintenance" in maint_script
    assert "--dry-run" in maint_script
    assert "TOKEN_CLEANUP_GRACE_DAYS" in maint_script
    assert "TOKEN_CLEANUP_REVOKED_GRACE_DAYS" in maint_script

    # Installer script
    assert "set -euo pipefail" in install_script
    assert "edgemind-backup.timer" in install_script
    assert "edgemind-maintenance.timer" in install_script
    assert "maintenance.env" in install_script

    # Systemd units
    backup_srv = (SYSTEMD_DIR / "edgemind-backup.service").read_text(encoding="utf-8")
    backup_tmr = (SYSTEMD_DIR / "edgemind-backup.timer").read_text(encoding="utf-8")
    maint_srv = (SYSTEMD_DIR / "edgemind-maintenance.service").read_text(encoding="utf-8")
    maint_tmr = (SYSTEMD_DIR / "edgemind-maintenance.timer").read_text(encoding="utf-8")
    env_example = (SYSTEMD_DIR / "maintenance.env.example").read_text(encoding="utf-8")

    assert "Type=oneshot" in backup_srv
    assert "EnvironmentFile=-/etc/edgemind/maintenance.env" in backup_srv
    assert "/opt/edgemind/deploy/oci/scripts/backup-postgres.sh" in backup_srv
    assert "Persistent=true" in backup_tmr
    assert "02:00:00 UTC" in backup_tmr

    assert "Type=oneshot" in maint_srv
    assert "EnvironmentFile=-/etc/edgemind/maintenance.env" in maint_srv
    assert "/opt/edgemind/deploy/oci/scripts/run-db-maintenance.sh" in maint_srv
    assert "Persistent=true" in maint_tmr
    assert "03:00:00 UTC" in maint_tmr

    assert "RETENTION_DAYS=" in env_example
    assert "BACKUP_DIR=" in env_example
    assert "TOKEN_CLEANUP_GRACE_DAYS=" in env_example
    assert "TOKEN_CLEANUP_REVOKED_GRACE_DAYS=" in env_example


def test_compose_env_cloud_init_and_documentation_for_scheduled_maintenance():
    compose = (OCI_DIR / "docker-compose.production.yml").read_text(encoding="utf-8")
    prod_env = (OCI_DIR / ".env.production.example").read_text(encoding="utf-8")
    cloud_init = (OCI_DIR / "cloud-init.yaml").read_text(encoding="utf-8")
    oci_readme = (OCI_DIR / "README.md").read_text(encoding="utf-8")

    assert "REFRESH_TOKEN_CLEANUP_GRACE_DAYS" in compose
    assert "REFRESH_TOKEN_REVOKED_GRACE_DAYS" in compose
    assert "BACKUP_DIR=" in prod_env
    assert "RETENTION_DAYS=" in prod_env
    assert "TOKEN_CLEANUP_GRACE_DAYS=" in prod_env
    assert "/opt/edgemind/deploy/oci/systemd" in cloud_init
    assert "/etc/edgemind" in cloud_init

    assert "edgemind-backup.timer" in oci_readme
    assert "edgemind-maintenance.timer" in oci_readme
    assert "RETENTION_DAYS" in oci_readme
    assert "/opt/edgemind/backups" in oci_readme
    assert "restore-postgres.sh" in oci_readme
    assert "journalctl" in oci_readme
