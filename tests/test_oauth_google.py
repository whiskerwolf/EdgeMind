"""
EdgeMind Secure Google OAuth 2.0 / OIDC Authentication Test Suite.

Covers all 20 required verification checks using httpx.MockTransport and
an isolated in-memory SQLite database (no external Google credentials required).
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse
import uuid

from fastapi.testclient import TestClient
import httpx
import jwt
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.api import app
from core.auth.oauth import (
    GOOGLE_TOKEN_ENDPOINT,
    GOOGLE_USERINFO_ENDPOINT,
    GoogleOAuthService,
)
from core.auth.router import get_google_oauth_service
from core.auth.security import create_access_token, hash_password, hash_token
from core.config import get_settings
from core.database.connection import get_db
from core.database.models import Base, OAuthAccount, OAuthState, User

TEST_JWT_SECRET = "test-crypto-secret-key-for-edgemind-oauth-google-suite-long"
TEST_CLIENT_ID = "test-google-client-id.apps.googleusercontent.com"
TEST_CLIENT_SECRET = "GOCSPX-TestGoogleSecretDoNotExpose999"
TEST_REDIRECT_URI = "http://127.0.0.1:8000/api/v1/auth/oauth/google/callback"


def _make_unsigned_id_token(
    sub: str = "google-sub-12345",
    email: str = "oauthuser@example.com",
    nonce: Optional[str] = None,
    aud: str = TEST_CLIENT_ID,
    iss: str = "https://accounts.google.com",
    exp_offset_sec: int = 300,
) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    payload: Dict[str, Any] = {
        "sub": sub,
        "email": email,
        "email_verified": True,
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + exp_offset_sec,
    }
    if nonce is not None:
        payload["nonce"] = nonce
    return jwt.encode(payload, "mock-oidc-signing-key", algorithm="HS256")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def configure_oauth_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_SECRET", TEST_CLIENT_SECRET)
    monkeypatch.setenv("OAUTH_GOOGLE_REDIRECT_URI", TEST_REDIRECT_URI)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


def _make_client(session_maker, transport: Optional[httpx.AsyncBaseTransport] = None):
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

    async def override_oauth_service():
        async with session_maker() as session:
            try:
                yield GoogleOAuthService(db=session, settings=get_settings(), transport=transport)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_google_oauth_service] = override_oauth_service
    return TestClient(app)


def _extract_state_and_nonce(session_maker, auth_url: str) -> tuple[str, str]:
    qs = parse_qs(urlparse(auth_url).query)
    state = qs["state"][0]

    async def _fetch():
        async with session_maker() as s:
            rec = (
                await s.execute(select(OAuthState).where(OAuthState.state_hash == hash_token(state)))
            ).scalar_one()
            return rec.nonce

    return state, asyncio.run(_fetch())


# =============================================================================
# Tests 1-10: Configuration, State Security, Provider Errors, OIDC Validation
# =============================================================================

def test_oauth_missing_config_fails_safely_and_preserves_jwt(session_maker, monkeypatch):
    monkeypatch.delenv("OAUTH_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("OAUTH_GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OAUTH_GOOGLE_REDIRECT_URI", raising=False)
    get_settings.cache_clear()

    with _make_client(session_maker) as client:
        try:
            res_auth = client.get("/api/v1/auth/oauth/google")
            assert res_auth.status_code == 503
            assert "not configured" in res_auth.json()["detail"].lower()

            res_cb = client.get("/api/v1/auth/oauth/google/callback?code=abc&state=xyz")
            assert res_cb.status_code == 503

            # Existing JWT registration & login remain fully operational
            reg = client.post(
                "/api/v1/auth/register",
                json={"email": "local@example.com", "password": "Password123!", "full_name": "Local User"},
            )
            assert reg.status_code == 201
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "local@example.com", "password": "Password123!"},
            )
            assert login.status_code == 200
        finally:
            app.dependency_overrides.clear()


def test_authorization_url_pkce_state_hashing_and_redirect_mode(session_maker):
    with _make_client(session_maker) as client:
        try:
            r1 = client.get("/api/v1/auth/oauth/google")
            r2 = client.get("/api/v1/auth/oauth/google")
            assert r1.status_code == 200 and r2.status_code == 200
            data1 = r1.json()
            data2 = r2.json()
            assert data1["provider"] == "google"
            assert data1["expires_in"] == 600

            parsed1 = urlparse(data1["authorization_url"])
            qs1 = parse_qs(parsed1.query)
            qs2 = parse_qs(urlparse(data2["authorization_url"]).query)

            assert parsed1.netloc == "accounts.google.com"
            assert qs1["response_type"] == ["code"]
            assert qs1["code_challenge_method"] == ["S256"]
            assert qs1["scope"] == ["openid email profile"]
            assert qs1["state"][0] != qs2["state"][0]  # Cryptographically distinct states
            assert TEST_CLIENT_SECRET not in data1["authorization_url"]

            # Raw state must be stored hashed, never plaintext
            async def check_hashed():
                async with session_maker() as s:
                    rows = (await s.execute(select(OAuthState))).scalars().all()
                    assert len(rows) == 2
                    hashes = {r.state_hash for r in rows}
                    assert hash_token(qs1["state"][0]) in hashes
                    assert qs1["state"][0] not in hashes

            asyncio.run(check_hashed())

            # Optional HTTP 302 redirect mode
            r_redir = client.get("/api/v1/auth/oauth/google?redirect=true", follow_redirects=False)
            assert r_redir.status_code == 302
            assert r_redir.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        finally:
            app.dependency_overrides.clear()


def test_invalid_expired_and_replayed_oauth_states_rejected(session_maker):
    # Note: handler cannot use asyncio.run inside running loop, so use async helper cleanly below
    with _make_client(session_maker) as client:
        try:
            # Missing / invalid state
            assert client.get("/api/v1/auth/oauth/google/callback?code=c").status_code == 400
            assert client.get("/api/v1/auth/oauth/google/callback?code=c&state=bogus").status_code == 400

            # Expired state
            init_resp = client.get("/api/v1/auth/oauth/google").json()
            expired_state, _ = _extract_state_and_nonce(session_maker, init_resp["authorization_url"])

            async def expire_it():
                async with session_maker() as s:
                    rec = (
                        await s.execute(select(OAuthState).where(OAuthState.state_hash == hash_token(expired_state)))
                    ).scalar_one()
                    rec.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
                    await s.commit()

            asyncio.run(expire_it())
            exp_res = client.get(f"/api/v1/auth/oauth/google/callback?code=ok&state={expired_state}")
            assert exp_res.status_code == 400
            assert "expired" in exp_res.json()["detail"].lower()

            # Replayed state (consumed once above even though expired!)
            replay_res = client.get(f"/api/v1/auth/oauth/google/callback?code=ok&state={expired_state}")
            assert replay_res.status_code == 400
            assert "already been consumed" in replay_res.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()


def _sync_token_userinfo_transport(
    sub: str = "google-sub-001",
    email: str = "alice.oauth@example.com",
    email_verified: Any = True,
    name: str = "Alice OAuth",
    nonce: Optional[str] = None,
    id_token_sub: Optional[str] = None,
    token_status: int = 200,
    token_body: Optional[Dict[str, Any]] = None,
    userinfo_status: int = 200,
    raise_connect: bool = False,
) -> httpx.AsyncBaseTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        if raise_connect:
            raise httpx.ConnectError(f"failed connecting with secret={TEST_CLIENT_SECRET}")
        url = str(request.url)
        if url.startswith(GOOGLE_TOKEN_ENDPOINT):
            if token_status != 200:
                return httpx.Response(token_status, json={"error": "invalid_grant", "detail": TEST_CLIENT_SECRET})
            if token_body is not None:
                return httpx.Response(200, json=token_body)
            payload = {
                "access_token": "ya29.mock-google-token-secret",
                "token_type": "Bearer",
                "expires_in": 3599,
            }
            if nonce is not None:
                payload["id_token"] = _make_unsigned_id_token(
                    sub=id_token_sub or sub,
                    email=email,
                    nonce=nonce,
                )
            return httpx.Response(200, json=payload)
        if url.startswith(GOOGLE_USERINFO_ENDPOINT):
            if userinfo_status != 200:
                return httpx.Response(userinfo_status, text=f"error {TEST_CLIENT_SECRET}")
            return httpx.Response(
                200,
                json={
                    "sub": sub,
                    "email": email,
                    "email_verified": email_verified,
                    "name": name,
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_provider_errors_invalid_code_bad_token_and_secret_redaction(session_maker):
    # 1. Invalid authorization code / provider 400 + secret never leaked
    t_bad_code = _sync_token_userinfo_transport(token_status=400)
    with _make_client(session_maker, transport=t_bad_code) as client:
        try:
            init_url = client.get("/api/v1/auth/oauth/google").json()["authorization_url"]
            state, _ = _extract_state_and_nonce(session_maker, init_url)
            res = client.get(f"/api/v1/auth/oauth/google/callback?code=badcode&state={state}")
            assert res.status_code == 502
            assert TEST_CLIENT_SECRET not in res.text
        finally:
            app.dependency_overrides.clear()

    # 2. User declined consent (?error=access_denied)
    with _make_client(session_maker) as client:
        try:
            init_url = client.get("/api/v1/auth/oauth/google").json()["authorization_url"]
            state, _ = _extract_state_and_nonce(session_maker, init_url)
            res = client.get(f"/api/v1/auth/oauth/google/callback?error=access_denied&state={state}")
            assert res.status_code == 502
            # State was consumed, cannot be replayed
            res_replay = client.get(f"/api/v1/auth/oauth/google/callback?code=valid&state={state}")
            assert res_replay.status_code == 400
        finally:
            app.dependency_overrides.clear()

    # 3. Missing access_token in token response + network failure
    t_missing_tok = _sync_token_userinfo_transport(token_body={"token_type": "Bearer"})
    with _make_client(session_maker, transport=t_missing_tok) as client:
        try:
            init_url = client.get("/api/v1/auth/oauth/google").json()["authorization_url"]
            state, _ = _extract_state_and_nonce(session_maker, init_url)
            assert client.get(f"/api/v1/auth/oauth/google/callback?code=c&state={state}").status_code == 502
        finally:
            app.dependency_overrides.clear()

    t_net_err = _sync_token_userinfo_transport(raise_connect=True)
    with _make_client(session_maker, transport=t_net_err) as client:
        try:
            init_url = client.get("/api/v1/auth/oauth/google").json()["authorization_url"]
            state, _ = _extract_state_and_nonce(session_maker, init_url)
            res_net = client.get(f"/api/v1/auth/oauth/google/callback?code=c&state={state}")
            assert res_net.status_code == 502
            assert TEST_CLIENT_SECRET not in res_net.text
        finally:
            app.dependency_overrides.clear()

    # 4. OIDC id_token sub/nonce mismatch rejected
    with _make_client(session_maker) as client_init:
        init_url = client_init.get("/api/v1/auth/oauth/google").json()["authorization_url"]
        state, nonce = _extract_state_and_nonce(session_maker, init_url)
        app.dependency_overrides.clear()

    t_mismatch = _sync_token_userinfo_transport(
        sub="google-sub-real",
        id_token_sub="google-sub-different",
        nonce=nonce,
    )
    with _make_client(session_maker, transport=t_mismatch) as client:
        try:
            res_mm = client.get(f"/api/v1/auth/oauth/google/callback?code=ok&state={state}")
            assert res_mm.status_code == 401
        finally:
            app.dependency_overrides.clear()


def test_unverified_google_email_rejected_and_user_not_created(session_maker):
    with _make_client(session_maker) as client_init:
        init_url = client_init.get("/api/v1/auth/oauth/google").json()["authorization_url"]
        state, nonce = _extract_state_and_nonce(session_maker, init_url)
        app.dependency_overrides.clear()

    t_unverified = _sync_token_userinfo_transport(
        sub="google-unverified-sub",
        email="unverified@example.com",
        email_verified=False,
        nonce=nonce,
    )
    with _make_client(session_maker, transport=t_unverified) as client:
        try:
            res = client.get(f"/api/v1/auth/oauth/google/callback?code=ok&state={state}")
            assert res.status_code == 401
            assert "verified" in res.json()["detail"].lower()

            async def count_users():
                async with session_maker() as s:
                    return (await s.execute(select(User))).scalars().all()

            assert asyncio.run(count_users()) == []
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Tests 11-19: User Provisioning, Linked Login, RBAC, Linking, HTTPS & Open Redirect
# =============================================================================

def test_new_oauth_user_creation_returning_login_jwt_rbac_and_disabled_user(session_maker):
    # 1. First login creates User(role='user') + OAuthAccount and issues EdgeMind JWT pair
    with _make_client(session_maker) as client_init:
        init_url = client_init.get("/api/v1/auth/oauth/google").json()["authorization_url"]
        state, nonce = _extract_state_and_nonce(session_maker, init_url)
        app.dependency_overrides.clear()

    t_google = _sync_token_userinfo_transport(
        sub="google-sub-alice-777",
        email="Alice.OAuth@Example.com",
        email_verified=True,
        name="Alice OAuth",
        nonce=nonce,
    )
    with _make_client(session_maker, transport=t_google) as client:
        try:
            cb = client.get(f"/api/v1/auth/oauth/google/callback?code=authcode1&state={state}")
            assert cb.status_code == 200
            tokens = cb.json()
            assert tokens["token_type"] == "bearer"
            assert "access_token" in tokens and "refresh_token" in tokens
            assert "ya29." not in cb.text  # Google provider access token not returned/stored

            # Verify EdgeMind /users/me + RBAC /admin/usage enforcement
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            me = client.get("/api/v1/users/me", headers=headers)
            assert me.status_code == 200
            assert me.json()["email"] == "alice.oauth@example.com"
            assert me.json()["role"] == "user"

            admin_check = client.get("/api/v1/admin/usage", headers=headers)
            assert admin_check.status_code == 403

            # Verify refresh rotation works cleanly for OAuth-created session
            refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
            assert refreshed.status_code == 200

            # Replay of same OAuth callback state rejected
            replay = client.get(f"/api/v1/auth/oauth/google/callback?code=authcode1&state={state}")
            assert replay.status_code == 400
        finally:
            app.dependency_overrides.clear()

    # 2. Returning login via same OAuth identity authenticates same User without duplicate row
    with _make_client(session_maker) as client_init:
        init_url2 = client_init.get("/api/v1/auth/oauth/google").json()["authorization_url"]
        state2, nonce2 = _extract_state_and_nonce(session_maker, init_url2)
        app.dependency_overrides.clear()

    t_google2 = _sync_token_userinfo_transport(
        sub="google-sub-alice-777",
        email="alice.oauth@example.com",
        email_verified=True,
        nonce=nonce2,
    )
    with _make_client(session_maker, transport=t_google2) as client:
        try:
            cb2 = client.get(f"/api/v1/auth/oauth/google/callback?code=authcode2&state={state2}")
            assert cb2.status_code == 200

            async def check_counts():
                async with session_maker() as s:
                    users = (await s.execute(select(User))).scalars().all()
                    links = (await s.execute(select(OAuthAccount))).scalars().all()
                    return len(users), len(links), users[0].id

            u_cnt, l_cnt, alice_id = asyncio.run(check_counts())
            assert u_cnt == 1 and l_cnt == 1
        finally:
            app.dependency_overrides.clear()

    # 3. Disable user account -> OAuth login rejected with 403 Forbidden
    async def disable_user():
        async with session_maker() as s:
            u = (await s.execute(select(User).where(User.id == alice_id))).scalar_one()
            u.is_active = False
            await s.commit()

    asyncio.run(disable_user())
    with _make_client(session_maker) as client_init:
        init_url3 = client_init.get("/api/v1/auth/oauth/google").json()["authorization_url"]
        state3, nonce3 = _extract_state_and_nonce(session_maker, init_url3)
        app.dependency_overrides.clear()

    t_google3 = _sync_token_userinfo_transport(
        sub="google-sub-alice-777",
        email="alice.oauth@example.com",
        email_verified=True,
        nonce=nonce3,
    )
    with _make_client(session_maker, transport=t_google3) as client:
        try:
            cb3 = client.get(f"/api/v1/auth/oauth/google/callback?code=authcode3&state={state3}")
            assert cb3.status_code == 403
        finally:
            app.dependency_overrides.clear()


def test_account_linking_prevents_takeover_and_allows_authenticated_link(session_maker):
    # Create an existing password-registered user
    with _make_client(session_maker) as client:
        try:
            reg = client.post(
                "/api/v1/auth/register",
                json={"email": "bob@example.com", "password": "Password123!", "full_name": "Bob"},
            )
            assert reg.status_code == 201
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "bob@example.com", "password": "Password123!"},
            )
            bob_token = login.json()["access_token"]

            # 1. Unauthenticated linking (?link=true without Bearer token) -> 401
            assert client.get("/api/v1/auth/oauth/google?link=true").status_code == 401

            # 2. Unauthenticated OAuth login attempting to claim bob@example.com -> 409 Conflict!
            init_url = client.get("/api/v1/auth/oauth/google").json()["authorization_url"]
            state, nonce = _extract_state_and_nonce(session_maker, init_url)
        finally:
            app.dependency_overrides.clear()

    t_hijack = _sync_token_userinfo_transport(
        sub="google-sub-attacker",
        email="bob@example.com",
        email_verified=True,
        nonce=nonce,
    )
    with _make_client(session_maker, transport=t_hijack) as client:
        try:
            res_hijack = client.get(f"/api/v1/auth/oauth/google/callback?code=ok&state={state}")
            assert res_hijack.status_code == 409
        finally:
            app.dependency_overrides.clear()

    # 3. Authenticated link with mismatched email -> 401 Unauthorized
    with _make_client(session_maker) as client:
        try:
            init_mismatch = client.get(
                "/api/v1/auth/oauth/google?link=true",
                headers={"Authorization": f"Bearer {bob_token}"},
            ).json()["authorization_url"]
            st_mm, nonce_mm = _extract_state_and_nonce(session_maker, init_mismatch)
        finally:
            app.dependency_overrides.clear()

    t_wrong_email = _sync_token_userinfo_transport(
        sub="google-sub-other",
        email="other@example.com",
        email_verified=True,
        nonce=nonce_mm,
    )
    with _make_client(session_maker, transport=t_wrong_email) as client:
        try:
            assert client.get(f"/api/v1/auth/oauth/google/callback?code=ok&state={st_mm}").status_code == 401
        finally:
            app.dependency_overrides.clear()

    # 4. Authenticated link with matching verified email -> 200 OK
    with _make_client(session_maker) as client:
        try:
            init_link = client.get(
                "/api/v1/auth/oauth/google?link=true",
                headers={"Authorization": f"Bearer {bob_token}"},
            ).json()["authorization_url"]
            st_link, nonce_link = _extract_state_and_nonce(session_maker, init_link)
        finally:
            app.dependency_overrides.clear()

    t_bob_link = _sync_token_userinfo_transport(
        sub="google-sub-bob-real",
        email="bob@example.com",
        email_verified=True,
        nonce=nonce_link,
    )
    with _make_client(session_maker, transport=t_bob_link) as client:
        try:
            linked_res = client.get(f"/api/v1/auth/oauth/google/callback?code=ok&state={st_link}")
            assert linked_res.status_code == 200
            assert "access_token" in linked_res.json()
        finally:
            app.dependency_overrides.clear()


def test_open_redirect_prevention_production_https_and_popup_postmessage(session_maker, monkeypatch):
    # 1. Untrusted frontend_origin blocked with 400
    with _make_client(session_maker) as client:
        try:
            evil = client.get("/api/v1/auth/oauth/google?frontend_origin=https://evil.attacker.example")
            assert evil.status_code == 400
            assert "untrusted" in evil.json()["detail"].lower()

            # Trusted CORS origin succeeds and callback returns scoped postMessage HTML
            trusted_url = client.get(
                "/api/v1/auth/oauth/google?frontend_origin=http://localhost:5173"
            ).json()["authorization_url"]
            state, nonce = _extract_state_and_nonce(session_maker, trusted_url)
        finally:
            app.dependency_overrides.clear()

    t_popup = _sync_token_userinfo_transport(
        sub="google-sub-popup",
        email="popup@example.com",
        email_verified=True,
        nonce=nonce,
    )
    with _make_client(session_maker, transport=t_popup) as client:
        try:
            cb_html = client.get(f"/api/v1/auth/oauth/google/callback?code=ok&state={state}")
            assert cb_html.status_code == 200
            assert "text/html" in cb_html.headers["content-type"]
            assert '"http://localhost:5173"' in cb_html.text
            assert "edgemind:oauth-callback" in cb_html.text
            assert "window.opener.postMessage(payload, targetOrigin)" in cb_html.text
        finally:
            app.dependency_overrides.clear()

    # 2. Production requires HTTPS redirect URI
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("OAUTH_GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/oauth/google/callback")
    get_settings.cache_clear()
    with _make_client(session_maker) as client:
        try:
            prod_http = client.get("/api/v1/auth/oauth/google")
            assert prod_http.status_code == 503
            assert "https" in prod_http.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()
