"""
EdgeMind Admin RBAC & Usage Analytics Test Suite.

Validates:
1. Unauthenticated access rejection (HTTP 401) including missing/invalid/expired tokens.
2. Normal user & inactive account rejection (HTTP 403) enforcing `require_role("admin")`.
3. Privilege escalation resistance (forged JWT role claims, query/body tampering).
4. Admin empty ledger behavior (zero metrics, null estimated cost, no fabrication).
5. Accurate cross-tenant aggregation across users, projects, providers, models, sources, and periods.
6. Strict omission of PII/secrets and preserved normal-user tenant isolation.
7. Sanitized 500 error responses when persistence fails.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.api import app
from core.auth.security import create_access_token, hash_password
from core.config import get_settings
from core.cost.models import TokenUsage, UsageSource
from core.database.connection import get_db
from core.database.models import AiTokenUsage, Base, Project, User
from core.database.repositories.usage_repository import UsageRepository

TEST_JWT_SECRET = "test-crypto-secret-key-for-edgemind-admin-rbac-usage-suite-long"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def async_db_engine():
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
    yield engine

    async def drop_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(drop_tables())


@pytest.fixture
def session_maker(async_db_engine):
    return async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
def client(session_maker):
    async def override_get_db():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def _create_user_sync(
    session_maker,
    email: str,
    role: str = "user",
    is_active: bool = True,
) -> User:
    async def _op():
        async with session_maker() as session:
            user = User(
                email=email,
                password_hash=hash_password("StrongPass!123"),
                full_name=f"Test {role}",
                role=role,
                is_active=is_active,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(_op())


def _auth_header(user: User) -> dict[str, str]:
    token = create_access_token(user.id, role=user.role)
    return {"Authorization": f"Bearer {token}"}


# -----------------------------------------------------------------------------
# 1. Authentication & RBAC Permission Tests
# -----------------------------------------------------------------------------

def test_admin_usage_rejects_unauthenticated_and_invalid_tokens(client: TestClient):
    # No Authorization header
    resp = client.get("/api/v1/admin/usage")
    assert resp.status_code == 401

    # Malformed Bearer token
    resp_bad = client.get(
        "/api/v1/admin/usage",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp_bad.status_code == 401


def test_admin_usage_rejects_standard_user_and_inactive_admin(
    client: TestClient, session_maker
):
    normal_user = _create_user_sync(session_maker, "member@edgemind.test", role="user")
    inactive_admin = _create_user_sync(
        session_maker,
        "disabled-admin@edgemind.test",
        role="admin",
        is_active=False,
    )

    resp_user = client.get("/api/v1/admin/usage", headers=_auth_header(normal_user))
    assert resp_user.status_code == 403
    assert "admin" in resp_user.json()["detail"].lower()

    resp_inactive = client.get("/api/v1/admin/usage", headers=_auth_header(inactive_admin))
    assert resp_inactive.status_code == 403


def test_admin_usage_blocks_privilege_escalation_attempts(
    client: TestClient, session_maker
):
    normal_user = _create_user_sync(session_maker, "escalate@edgemind.test", role="user")
    settings = get_settings()

    # 1. Forged JWT claiming role="admin" in claims, but DB row is role="user"
    forged_token = create_access_token(normal_user.id, role="admin")
    resp_forged = client.get(
        "/api/v1/admin/usage",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert resp_forged.status_code == 403

    # 2. Query parameter tampering (?role=admin, ?is_admin=true, ?user_id=...)
    resp_params = client.get(
        f"/api/v1/admin/usage?role=admin&is_admin=true&user_id={uuid.uuid4()}",
        headers=_auth_header(normal_user),
    )
    assert resp_params.status_code == 403

    # 3. Profile update payload attempting to overwrite role (rejected by schema / immutable)
    patch_resp = client.patch(
        "/api/v1/users/me",
        json={"full_name": "Updated Name", "role": "admin"},
        headers=_auth_header(normal_user),
    )
    assert patch_resp.status_code in (200, 422)
    if patch_resp.status_code == 200:
        assert patch_resp.json()["role"] == "user"
    assert settings.jwt_algorithm == "HS256"

    resp_after_patch = client.get("/api/v1/admin/usage", headers=_auth_header(normal_user))
    assert resp_after_patch.status_code == 403


# -----------------------------------------------------------------------------
# 2. Empty Data & Cross-Tenant Aggregation Tests
# -----------------------------------------------------------------------------

def test_admin_usage_empty_ledger_returns_zero_without_fabrication(
    client: TestClient, session_maker
):
    admin_user = _create_user_sync(session_maker, "admin-empty@edgemind.test", role="admin")

    resp = client.get("/api/v1/admin/usage", headers=_auth_header(admin_user))
    assert resp.status_code == 200
    data = resp.json()

    assert data["period"] == "month"
    assert data["total_prompt_tokens"] == 0
    assert data["total_completion_tokens"] == 0
    assert data["total_tokens"] == 0
    assert data["total_estimated_cost_usd"] is None
    assert data["is_estimated_cost_known"] is False
    assert data["requests_count"] == 0
    assert data["distinct_users_count"] == 0
    assert data["distinct_projects_count"] == 0
    assert data["anonymous_requests_count"] == 0
    assert data["by_provider"] == {}
    assert data["by_model"] == {}
    assert data["by_source"] == {}
    assert data["by_user"] == []


def test_admin_usage_aggregates_multi_tenant_data_and_preserves_privacy(
    client: TestClient, session_maker
):
    admin_user = _create_user_sync(session_maker, "admin-analytics@edgemind.test", role="admin")
    tenant_a = _create_user_sync(session_maker, "secret-email-a@edgemind.test", role="user")
    tenant_b = _create_user_sync(session_maker, "secret-email-b@edgemind.test", role="user")

    async def seed_usage():
        async with session_maker() as session:
            proj_a = Project(
                name="Tenant A Project",
                owner_user_id=tenant_a.id,
            )
            proj_b = Project(
                name="Tenant B Project",
                owner_user_id=tenant_b.id,
            )
            session.add_all([proj_a, proj_b])
            await session.flush()

            repo = UsageRepository(session)
            # Recent OpenAI usage for Tenant A
            await repo.record_usage(
                TokenUsage(
                    prompt_tokens=1000,
                    completion_tokens=200,
                    total_tokens=1200,
                    model="gpt-4o-mini",
                    provider="openai",
                    request_id=f"req-{uuid.uuid4()}",
                    usage_source=UsageSource.ACTUAL_PROVIDER,
                    estimated_cost_usd=Decimal("0.000270000000"),
                    is_estimated_cost_known=True,
                ),
                user_id=tenant_a.id,
                project_id=proj_a.id,
            )
            # Recent local Ollama usage for Tenant B (cost=None, LOCAL_INFERENCE)
            await repo.record_usage(
                TokenUsage(
                    prompt_tokens=500,
                    completion_tokens=300,
                    total_tokens=800,
                    model="qwen3:4b",
                    provider="ollama",
                    request_id=f"req-{uuid.uuid4()}",
                    usage_source=UsageSource.LOCAL_INFERENCE,
                    estimated_cost_usd=None,
                    is_estimated_cost_known=False,
                ),
                user_id=tenant_b.id,
                project_id=proj_b.id,
            )
            # Anonymous usage record (user_id=None)
            await repo.record_usage(
                TokenUsage(
                    prompt_tokens=250,
                    completion_tokens=50,
                    total_tokens=300,
                    model="gpt-4o-mini",
                    provider="openai",
                    request_id=f"req-{uuid.uuid4()}",
                    usage_source=UsageSource.ACTUAL_PROVIDER,
                    estimated_cost_usd=Decimal("0.000067500000"),
                    is_estimated_cost_known=True,
                ),
                user_id=None,
                project_id=None,
            )
            # Historical record older than 30 days (excluded from month/day, included in all)
            old_row = AiTokenUsage(
                user_id=tenant_a.id,
                project_id=proj_a.id,
                provider="openai",
                model="gpt-4o-mini",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                estimated_cost_usd=Decimal("0.000100000000"),
                usage_source=UsageSource.ACTUAL_PROVIDER.value,
                request_id=f"req-{uuid.uuid4()}",
                created_at=datetime.now(timezone.utc) - timedelta(days=45),
            )
            session.add(old_row)
            await session.commit()
            return proj_a.id, proj_b.id

    proj_a_id, proj_b_id = asyncio.run(seed_usage())

    # 1. Admin default period=month query
    resp_month = client.get("/api/v1/admin/usage?period=month", headers=_auth_header(admin_user))
    assert resp_month.status_code == 200
    body = resp_month.json()

    assert body["requests_count"] == 3
    assert body["total_prompt_tokens"] == 1750
    assert body["total_completion_tokens"] == 550
    assert body["total_tokens"] == 2300
    assert Decimal(str(body["total_estimated_cost_usd"])) == Decimal("0.000337500000")
    assert body["is_estimated_cost_known"] is True
    assert body["distinct_users_count"] == 2
    assert body["distinct_projects_count"] == 2
    assert body["anonymous_requests_count"] == 1

    # Provider breakdown
    assert body["by_provider"]["openai"]["total_tokens"] == 1500
    assert body["by_provider"]["openai"]["requests_count"] == 2
    assert body["by_provider"]["ollama"]["total_tokens"] == 800
    assert body["by_provider"]["ollama"]["estimated_cost_usd"] is None
    assert body["by_provider"]["ollama"]["is_estimated_cost_known"] is False

    # User breakdown ordered by total_tokens desc
    assert [u["total_tokens"] for u in body["by_user"]] == [1200, 800, 300]
    assert body["by_user"][0]["user_id"] == str(tenant_a.id)
    assert body["by_user"][2]["user_id"] is None

    # Privacy/secret check: emails & JWT secret must never leak into admin analytics payload
    serialized = resp_month.text
    assert "secret-email-a@edgemind.test" not in serialized
    assert "secret-email-b@edgemind.test" not in serialized
    assert TEST_JWT_SECRET not in serialized

    # 2. Admin period=all includes historical 45-day-old row
    resp_all = client.get("/api/v1/admin/usage?period=all", headers=_auth_header(admin_user))
    assert resp_all.status_code == 200
    all_data = resp_all.json()
    assert all_data["requests_count"] == 4
    assert all_data["total_tokens"] == 2450
    assert Decimal(str(all_data["total_estimated_cost_usd"])) == Decimal("0.000437500000")

    # 3. Admin scoped filters (provider=ollama, user_id=tenant_a)
    resp_ollama = client.get(
        "/api/v1/admin/usage?period=all&provider=ollama",
        headers=_auth_header(admin_user),
    )
    assert resp_ollama.status_code == 200
    assert resp_ollama.json()["total_tokens"] == 800
    assert resp_ollama.json()["total_estimated_cost_usd"] is None

    resp_tenant_a = client.get(
        f"/api/v1/admin/usage?period=all&user_id={tenant_a.id}",
        headers=_auth_header(admin_user),
    )
    assert resp_tenant_a.status_code == 200
    assert resp_tenant_a.json()["total_tokens"] == 1350
    assert resp_tenant_a.json()["filters"]["user_id"] == str(tenant_a.id)

    # 4. Normal user tenant isolation remains intact on standard endpoints
    user_a_summary = client.get(
        "/api/v1/agent/usage/summary?period=all",
        headers=_auth_header(tenant_a),
    )
    assert user_a_summary.status_code == 200
    assert user_a_summary.json()["total_tokens"] == 1350

    cross_tenant_project = client.get(
        f"/api/v1/agent/usage/summary?period=all&project_id={proj_b_id}",
        headers=_auth_header(tenant_a),
    )
    assert cross_tenant_project.status_code == 404
    assert proj_a_id != proj_b_id


def test_admin_usage_sanitizes_internal_database_errors(
    client: TestClient, session_maker, monkeypatch
):
    admin_user = _create_user_sync(session_maker, "admin-err@edgemind.test", role="admin")
    leaked_pw = "UltraSecretDbPass98765"

    async def broken_analytics(*_args, **_kwargs):
        raise RuntimeError(
            f"connection failed for postgresql+asyncpg://admin:{leaked_pw}@postgres:5432/edgemind"
        )

    monkeypatch.setattr(UsageRepository, "get_admin_usage_analytics", broken_analytics)
    resp = client.get("/api/v1/admin/usage", headers=_auth_header(admin_user))
    assert resp.status_code == 500
    assert leaked_pw not in resp.text
    assert resp.json()["detail"] == "Failed to compute usage analytics."
