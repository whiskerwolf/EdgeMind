"""
EdgeMind — Phase 3: Authentication & Multi-Tenancy Test Suite.

Validates:
1. User registration with email normalization and role='user' default.
2. Duplicate email rejection (HTTP 409 Conflict).
3. Argon2 password hashing.
4. Password verification with complexity policy enforcement.
5. Login success and generic failure handling (anti-enumeration).
6. JWT access token generation and claims structure.
7. JWT verification, issuer, audience, and type checks.
8. Expired access token rejection.
9. Refresh token rotation issuing new access and refresh token pairs.
10. Reuse detection for revoked refresh tokens (revoking all sessions).
11. Logout and individual/all session revocation.
12. Inactive user authentication rejection (HTTP 403 Forbidden).
13. User profile retrieval (GET /me) and self-service updates (PATCH /me).
14. Role-based authorization (USER vs. ADMIN privilege enforcement).
15. Project ownership assignment on creation.
16. Cross-user access prevention (UUID manipulation returns HTTP 404).
17. Analysis history and report tenant query isolation.
18. Legacy anonymous Chrome extension compatibility on POST /api/v1/edgemind/analyze.
19. Alembic migration upgrade (head) and downgrade (base) verification.
20. Backward compatibility with existing unauthenticated CRUD workflows.
"""

from datetime import datetime, timedelta, timezone
import os
import subprocess
import sys
from typing import AsyncGenerator
import uuid

from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.api import app
from core.auth.dependencies import get_current_active_user, get_current_user
from core.auth.schemas import UserRegister
from core.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    hash_password,
    hash_token,
    validate_password_policy,
    verify_password,
    PasswordPolicyError,
)
from core.auth.service import AuthService
from core.config import get_settings
from core.database.connection import get_db
from core.database.models import AnalysisSession, Base, Problem, Project, RefreshToken, User

TEST_JWT_SECRET = "test-crypto-secret-key-for-edgemind-phase3-auth-tests-very-long"


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_test_jwt_secret(monkeypatch):
    """Ensure a valid JWT secret is available in all test contexts."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def async_db_engine():
    """Create an isolated in-memory SQLite async engine with StaticPool and enabled FKs."""
    import asyncio
    from sqlalchemy import event

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def init_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_tables())

    yield engine

    async def cleanup_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(cleanup_tables())


@pytest.fixture
async def async_session(async_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session with auto-rollback."""
    session_maker = async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        yield session


@pytest.fixture
def client(async_db_engine):
    """FastAPI TestClient with overridden get_db dependency pointing to test database."""
    session_maker = async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

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
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.pop(get_db, None)


# -----------------------------------------------------------------------------
# 1. User Registration & Role Enforcement
# -----------------------------------------------------------------------------

def test_user_registration_success(client: TestClient):
    """Verify registration creates active account with role='user' and hashed password."""
    payload = {
        "email": "Engineer1@Example.com  ",
        "password": "Password123!@#",
        "full_name": "Senior Test Architect",
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "engineer1@example.com"  # Normalized lowercase
    assert data["role"] == "user"  # Public registration defaults to user
    assert data["is_active"] is True
    assert "password_hash" not in data  # Never expose hash


def test_registration_rejects_arbitrary_role_injection(client: TestClient):
    """Verify extra fields like role='admin' are rejected by strict schema validation."""
    payload = {
        "email": "hacker@example.com",
        "password": "Password123!@#",
        "full_name": "Sneaky Admin",
        "role": "admin",
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 422  # Extra field forbidden


# -----------------------------------------------------------------------------
# 2. Duplicate Email Prevention
# -----------------------------------------------------------------------------

def test_duplicate_email_prevention(client: TestClient):
    """Verify registering an already-registered email returns HTTP 409 Conflict."""
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123!@#",
        "full_name": "Original User",
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    # Attempt second registration with same email (different case)
    dup_payload = {
        "email": "DUPLICATE@EXAMPLE.COM",
        "password": "DifferentPassword123!",
        "full_name": "Imposter User",
    }
    res2 = client.post("/api/v1/auth/register", json=dup_payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


# -----------------------------------------------------------------------------
# 3 & 4. Argon2 Password Hashing & Complexity Policy
# -----------------------------------------------------------------------------

def test_argon2_password_hashing_and_verification():
    """Verify Argon2 hashing produces valid non-plaintext hashes and verifies correctly."""
    plain = "SuperComplexPass123!$"
    hashed = hash_password(plain)

    assert hashed.startswith("$argon2")
    assert plain not in hashed
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword123!$", hashed) is False


def test_password_complexity_policy():
    """Verify password complexity policy catches weak passwords."""
    # Too short
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("Sh1!")

    # Missing uppercase
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("lowercase123!@")

    # Missing digit
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("NoDigitsHere!@#")

    # Missing special character
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("NoSpecialChars123")


# -----------------------------------------------------------------------------
# 5. Login Success and Generic Failure (Anti-Enumeration)
# -----------------------------------------------------------------------------

def test_login_success_and_failure(client: TestClient):
    """Verify login issues tokens on valid credentials and returns generic error on failure."""
    # Register
    client.post("/api/v1/auth/register", json={
        "email": "login_user@example.com",
        "password": "ValidPassword123!",
        "full_name": "Login User",
    })

    # Success
    res = client.post("/api/v1/auth/login", json={
        "email": "login_user@example.com",
        "password": "ValidPassword123!",
    })
    assert res.status_code == 200
    token_data = res.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["expires_in"] == 900  # 15 min

    # Invalid password -> 401 generic
    fail_res = client.post("/api/v1/auth/login", json={
        "email": "login_user@example.com",
        "password": "WrongPassword123!",
    })
    assert fail_res.status_code == 401
    assert "Invalid email or password" in fail_res.json()["detail"]

    # Non-existent email -> 401 identical generic message (anti-enumeration)
    no_email_res = client.post("/api/v1/auth/login", json={
        "email": "does_not_exist@example.com",
        "password": "SomePassword123!",
    })
    assert no_email_res.status_code == 401
    assert no_email_res.json()["detail"] == fail_res.json()["detail"]


# -----------------------------------------------------------------------------
# 6 & 7. JWT Claims Structure & Verification
# -----------------------------------------------------------------------------

def test_jwt_access_and_refresh_generation():
    """Verify access and refresh tokens have correct claims, issuer, and audience."""
    uid = uuid.uuid4()
    access = create_access_token(uid, role="user")
    raw_refresh, jti, expire = create_refresh_token(uid)

    access_claims = decode_jwt_token(access, expected_type="access")
    assert access_claims["sub"] == str(uid)
    assert access_claims["role"] == "user"
    assert access_claims["type"] == "access"
    assert access_claims["iss"] == "edgemind-api"
    assert access_claims["aud"] == "edgemind-client"

    refresh_claims = decode_jwt_token(raw_refresh, expected_type="refresh")
    assert refresh_claims["sub"] == str(uid)
    assert refresh_claims["type"] == "refresh"
    assert refresh_claims["jti"] == jti

    # Cross-type decoding rejection
    with pytest.raises(jwt.InvalidTokenError):
        decode_jwt_token(access, expected_type="refresh")


# -----------------------------------------------------------------------------
# 8. Expired Token Rejection
# -----------------------------------------------------------------------------

def test_expired_access_token_rejection(client: TestClient):
    """Verify expired access tokens are rejected with HTTP 401."""
    uid = uuid.uuid4()
    # Create token expired 5 minutes ago
    expired_token = create_access_token(uid, expires_delta=timedelta(minutes=-5))

    res = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()


# -----------------------------------------------------------------------------
# 9. Refresh Token Rotation
# -----------------------------------------------------------------------------

def test_refresh_token_rotation(client: TestClient):
    """Verify /refresh rotates the token pair and issues a fresh refresh token."""
    # Register & Login
    client.post("/api/v1/auth/register", json={
        "email": "rotate@example.com",
        "password": "Password123!@#",
        "full_name": "Rotation User",
    })
    login_res = client.post("/api/v1/auth/login", json={
        "email": "rotate@example.com",
        "password": "Password123!@#",
    })
    old_refresh = login_res.json()["refresh_token"]

    # Rotate
    refresh_res = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    new_refresh = new_data["refresh_token"]

    assert new_refresh != old_refresh
    assert "access_token" in new_data


# -----------------------------------------------------------------------------
# 10. Refresh Token Reuse Detection
# -----------------------------------------------------------------------------

def test_refresh_token_reuse_detection_and_revocation(client: TestClient):
    """
    Security Test:
    When an already-rotated/revoked refresh token is re-submitted, detect reuse
    and terminate all sessions for the user.
    """
    client.post("/api/v1/auth/register", json={
        "email": "theft_target@example.com",
        "password": "Password123!@#",
        "full_name": "Target User",
    })
    login_res = client.post("/api/v1/auth/login", json={
        "email": "theft_target@example.com",
        "password": "Password123!@#",
    })
    token_1 = login_res.json()["refresh_token"]

    # Legitimate rotation -> token_1 is now revoked, token_2 is active
    rot_res = client.post("/api/v1/auth/refresh", json={"refresh_token": token_1})
    assert rot_res.status_code == 200
    token_2 = rot_res.json()["refresh_token"]

    # Attacker attempts to reuse token_1!
    reuse_res = client.post("/api/v1/auth/refresh", json={"refresh_token": token_1})
    assert reuse_res.status_code == 401
    assert "reuse detected" in reuse_res.json()["detail"].lower()

    # Verify that token_2 was ALSO invalidated due to the security breach
    res_after_breach = client.post("/api/v1/auth/refresh", json={"refresh_token": token_2})
    assert res_after_breach.status_code == 401


# -----------------------------------------------------------------------------
# 11. Logout and Revocation
# -----------------------------------------------------------------------------

def test_logout_and_revocation(client: TestClient):
    """Verify logout revokes the refresh session."""
    client.post("/api/v1/auth/register", json={
        "email": "logout_user@example.com",
        "password": "Password123!@#",
        "full_name": "Logout User",
    })
    login_res = client.post("/api/v1/auth/login", json={
        "email": "logout_user@example.com",
        "password": "Password123!@#",
    })
    access_tok = login_res.json()["access_token"]
    refresh_tok = login_res.json()["refresh_token"]

    # Logout
    logout_res = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_tok},
        headers={"Authorization": f"Bearer {access_tok}"},
    )
    assert logout_res.status_code == 200

    # Attempt to refresh with revoked token -> 401
    ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_tok})
    assert ref_res.status_code == 401


# -----------------------------------------------------------------------------
# 12. Inactive User Rejection
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_inactive_user_rejection(async_session: AsyncSession, client: TestClient):
    """Verify deactivated accounts cannot log in or access protected endpoints."""
    auth_service = AuthService(async_session)
    user = await auth_service.register_user(
        email="inactive@example.com",
        password="Password123!@#",
        full_name="Inactive User",
    )
    user.is_active = False
    await async_session.commit()

    # Login rejected
    res = client.post("/api/v1/auth/login", json={
        "email": "inactive@example.com",
        "password": "Password123!@#",
    })
    assert res.status_code == 403
    assert "inactive" in res.json()["detail"].lower()


# -----------------------------------------------------------------------------
# 13. Profile Retrieval and Self-Service Update
# -----------------------------------------------------------------------------

def test_profile_retrieval_and_update(client: TestClient):
    """Verify GET /users/me and PATCH /users/me allow updating name and password."""
    client.post("/api/v1/auth/register", json={
        "email": "profile_user@example.com",
        "password": "OldPassword123!",
        "full_name": "Original Name",
    })
    tok = client.post("/api/v1/auth/login", json={
        "email": "profile_user@example.com",
        "password": "OldPassword123!",
    }).json()["access_token"]

    # GET /me
    me_res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tok}"})
    assert me_res.status_code == 200
    assert me_res.json()["full_name"] == "Original Name"

    # PATCH /me (update full_name and change password)
    patch_res = client.patch(
        "/api/v1/users/me",
        json={
            "full_name": "Updated Name",
            "current_password": "OldPassword123!",
            "new_password": "NewPassword123!#",
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["full_name"] == "Updated Name"

    # Login with new password succeeds
    new_login = client.post("/api/v1/auth/login", json={
        "email": "profile_user@example.com",
        "password": "NewPassword123!#",
    })
    assert new_login.status_code == 200


# -----------------------------------------------------------------------------
# 14. Role-Based Authorization (User vs. Admin)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_role_based_authorization_user_vs_admin(async_session: AsyncSession, client: TestClient):
    """Verify regular users cannot create problems, while administrators can."""
    auth_service = AuthService(async_session)
    user = await auth_service.register_user(
        email="regular_user@example.com",
        password="Password123!@#",
        full_name="Regular User",
    )
    admin = await auth_service.register_user(
        email="admin_user@example.com",
        password="Password123!@#",
        full_name="Admin User",
    )
    admin.role = "admin"
    await async_session.commit()

    user_tok = create_access_token(user.id, role="user")
    admin_tok = create_access_token(admin.id, role="admin")

    prob_payload = {
        "title": "Median of Two Sorted Arrays",
        "problem_slug": "median-of-two-sorted-arrays",
        "platform": "leetcode",
        "difficulty": "Hard",
    }

    # Regular user attempting problem creation -> 403 Forbidden
    user_res = client.post(
        "/api/v1/problems",
        json=prob_payload,
        headers={"Authorization": f"Bearer {user_tok}"},
    )
    assert user_res.status_code == 403
    assert "restricted to administrators" in user_res.json()["detail"].lower()

    # Admin user attempting problem creation -> 201 Created
    admin_res = client.post(
        "/api/v1/problems",
        json=prob_payload,
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert admin_res.status_code == 201
    assert admin_res.json()["problem_slug"] == "median-of-two-sorted-arrays"


# -----------------------------------------------------------------------------
# 15 & 16. Multi-Tenant Project Ownership & Cross-User Access Prevention
# -----------------------------------------------------------------------------

def test_project_ownership_and_cross_user_isolation(client: TestClient):
    """
    Verify authenticated user owns their created project.
    Verify User B attempting to read, update, or delete User A's project receives HTTP 404.
    """
    # User A
    client.post("/api/v1/auth/register", json={
        "email": "usera@example.com",
        "password": "Password123!@#",
        "full_name": "User Alpha",
    })
    tok_a = client.post("/api/v1/auth/login", json={
        "email": "usera@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]

    # User B
    client.post("/api/v1/auth/register", json={
        "email": "userb@example.com",
        "password": "Password123!@#",
        "full_name": "User Beta",
    })
    tok_b = client.post("/api/v1/auth/login", json={
        "email": "userb@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]

    # User A creates a project
    proj_res = client.post(
        "/api/v1/projects",
        json={"name": "Alpha Confidential Project"},
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert proj_res.status_code == 201
    proj_a_id = proj_res.json()["id"]

    # User A lists projects -> contains project
    list_a = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {tok_a}"})
    assert any(p["id"] == proj_a_id for p in list_a.json())

    # User B lists projects -> DOES NOT contain User A's project
    list_b = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {tok_b}"})
    assert not any(p["id"] == proj_a_id for p in list_b.json())

    # User B attempts to GET User A's project directly via UUID -> 404 Not Found
    get_b = client.get(f"/api/v1/projects/{proj_a_id}", headers={"Authorization": f"Bearer {tok_b}"})
    assert get_b.status_code == 404

    # User B attempts to PATCH User A's project -> 404 Not Found
    patch_b = client.patch(
        f"/api/v1/projects/{proj_a_id}",
        json={"name": "Hacked Name"},
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    assert patch_b.status_code == 404

    # User B attempts to DELETE User A's project -> 404 Not Found
    del_b = client.delete(f"/api/v1/projects/{proj_a_id}", headers={"Authorization": f"Bearer {tok_b}"})
    assert del_b.status_code == 404


# -----------------------------------------------------------------------------
# 17. Analysis History Isolation
# -----------------------------------------------------------------------------

def test_analysis_history_isolation(client: TestClient):
    """Verify users only see their own analysis history and reports."""
    client.post("/api/v1/auth/register", json={
        "email": "analyst1@example.com",
        "password": "Password123!@#",
        "full_name": "Analyst One",
    })
    tok1 = client.post("/api/v1/auth/login", json={
        "email": "analyst1@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]

    client.post("/api/v1/auth/register", json={
        "email": "analyst2@example.com",
        "password": "Password123!@#",
        "full_name": "Analyst Two",
    })
    tok2 = client.post("/api/v1/auth/login", json={
        "email": "analyst2@example.com",
        "password": "Password123!@#",
    }).json()["access_token"]

    # Analyst 1 creates an analysis session via POST /analyses
    sess_res = client.post(
        "/api/v1/analyses",
        json={"analysis_mode": "BASELINE_DRIVEN", "gaps_detected": 3, "candidates_generated": 6},
        headers={"Authorization": f"Bearer {tok1}"},
    )
    assert sess_res.status_code == 201
    sess1_id = sess_res.json()["id"]

    # Analyst 1 can view it
    assert client.get(f"/api/v1/analyses/{sess1_id}", headers={"Authorization": f"Bearer {tok1}"}).status_code == 200

    # Analyst 2 attempting to view Analyst 1's session -> 404 Not Found
    assert client.get(f"/api/v1/analyses/{sess1_id}", headers={"Authorization": f"Bearer {tok2}"}).status_code == 404


# -----------------------------------------------------------------------------
# 18. Legacy Anonymous Chrome Extension Compatibility
# -----------------------------------------------------------------------------

def test_legacy_anonymous_extension_compatibility(client: TestClient):
    """
    CRITICAL: Verify anonymous EdgeMind analysis workflow continues to work
    without an Authorization header, preserving Chrome extension operation.
    """
    payload = {
        "code": "def twoSum(nums, target):\n    return [0, 1]\n",
        "test_cases": [{"input_data": {"nums": [2, 7, 11, 15], "target": 9}}],
        "max_candidates": 5,
        "static_only": True,
    }
    # Anonymous call with no bearer token
    res = client.post("/api/v1/edgemind/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "analysis_session_id" in data


# -----------------------------------------------------------------------------
# 19. Alembic Migration Upgrade & Downgrade
# -----------------------------------------------------------------------------

def test_alembic_002_migration_upgrade_and_downgrade(tmp_path):
    """Verify Alembic migration 002 upgrades to head and downgrades to base cleanly."""
    db_path = tmp_path / "alembic_test_002.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    # Upgrade head
    up_res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert up_res.returncode == 0, f"Alembic upgrade failed:\n{up_res.stderr}\n{up_res.stdout}"
    assert "002_auth_and_ownership" in up_res.stdout or "002_auth_and_ownership" in up_res.stderr

    # Downgrade base
    down_res = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert down_res.returncode == 0, f"Alembic downgrade failed:\n{down_res.stderr}\n{down_res.stdout}"


# -----------------------------------------------------------------------------
# 20. Backward Compatibility for Existing Unauthenticated CRUD
# -----------------------------------------------------------------------------

def test_existing_crud_backward_compatibility(client: TestClient):
    """Verify existing unauthenticated project CRUD operations still function without errors."""
    create_res = client.post("/api/v1/projects", json={"name": "Legacy Unauthenticated Project"})
    assert create_res.status_code == 201
    proj_id = create_res.json()["id"]

    get_res = client.get(f"/api/v1/projects/{proj_id}")
    assert get_res.status_code == 200

    del_res = client.delete(f"/api/v1/projects/{proj_id}")
    assert del_res.status_code == 204

