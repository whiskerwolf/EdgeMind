"""
EdgeMind OAuth 2.0 / OpenID Connect Integration Service (Google Provider).

Implements Authorization Code Flow + PKCE (S256) + OIDC nonce verification with:
- Cryptographically random single-use CSRF state persisted as SHA-256 hash
- Strict redirect URI & post-login origin validation (open redirect & HTTPS checks)
- Verified email enforcement (`email_verified is True`)
- Identity binding via immutable provider `sub` claim (never stores provider tokens)
- Sanitized provider error handling via Settings.sanitize_error
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import logging
import secrets
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode, urlparse
import uuid

import httpx
import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.security import hash_password, hash_token
from core.auth.service import AuthError, AuthService, InactiveAccountError
from core.config import Settings, get_settings
from core.database.models import OAuthAccount, OAuthState, User
from core.sanitization import redact_secrets

logger = logging.getLogger("edgemind.auth.oauth")

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_VALID_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class OAuthError(AuthError):
    """Base exception for OAuth authentication failures."""


class OAuthConfigurationError(OAuthError):
    """Raised when Google OAuth credentials or secure redirect URI are missing/invalid."""


class OAuthSecurityError(OAuthError):
    """Raised on open redirect, HTTPS policy, or identity verification violations."""


class InvalidOAuthStateError(OAuthError):
    """Raised when OAuth state is missing, expired, invalid, or replayed."""


class OAuthProviderError(OAuthError):
    """Raised when the upstream OAuth provider returns an error or invalid payload."""


class OAuthAccountConflictError(OAuthError):
    """Raised when unauthenticated OAuth attempts to claim an existing password account."""


@dataclass(frozen=True)
class VerifiedOAuthIdentity:
    """Normalized, verified identity extracted from Google OIDC."""

    provider: str
    subject: str
    email: str
    email_verified: bool
    full_name: str


def _normalize_origin(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise OAuthSecurityError("Invalid origin URL format.")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def validate_oauth_redirect_uri(redirect_uri: str, environment: str) -> str:
    """
    Validate the registered Google OAuth callback redirect URI.
    Production strictly requires HTTPS; development/testing permits HTTPS or loopback HTTP.
    """
    if not redirect_uri or not redirect_uri.strip():
        raise OAuthConfigurationError("OAUTH_GOOGLE_REDIRECT_URI is not configured.")

    cleaned = redirect_uri.strip()
    parsed = urlparse(cleaned)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()

    if parsed.fragment:
        raise OAuthConfigurationError("OAuth redirect URI must not contain URL fragments.")
    if scheme not in ("https", "http") or not host:
        raise OAuthConfigurationError("OAuth redirect URI must be a valid HTTP(S) URL.")

    if environment.strip().lower() == "production":
        if scheme != "https":
            raise OAuthConfigurationError(
                "OAuth redirect URI must use HTTPS in production environments."
            )
    elif scheme == "http" and host not in _LOOPBACK_HOSTS:
        raise OAuthConfigurationError(
            "Non-HTTPS OAuth redirect URIs are only allowed for localhost/127.0.0.1 in development."
        )

    return cleaned


def validate_frontend_origin(origin: Optional[str], settings: Settings) -> Optional[str]:
    """
    Strictly validate an optional post-OAuth frontend target origin against
    configured `settings.cors_origins` to prevent open redirects / token leakage.
    """
    if origin is None or not origin.strip():
        return None

    candidate = _normalize_origin(origin)
    allowed_origins = set()
    for configured in settings.cors_origins:
        try:
            allowed_origins.add(_normalize_origin(configured))
        except OAuthSecurityError:
            continue

    if candidate not in allowed_origins:
        raise OAuthSecurityError(
            f"Untrusted frontend origin '{candidate}' is not permitted by CORS configuration."
        )
    return candidate


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _generate_unusable_random_password() -> str:
    """Generate a high-entropy password meeting complexity rules for OAuth-provisioned users."""
    return f"Oa#{secrets.token_urlsafe(24)}9zA!"


def _sanitize_oauth_message(message: str, settings: Settings, extra_secrets: Tuple[str, ...] = ()) -> str:
    custom = [s for s in extra_secrets if s and len(s) >= 6]
    cleaned = redact_secrets(message or "", custom_secrets=custom)
    return settings.sanitize_error(cleaned)


class GoogleOAuthService:
    """Handles Google OAuth 2.0 Authorization Code flow and EdgeMind user authentication."""

    def __init__(
        self,
        db: AsyncSession,
        settings: Optional[Settings] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.transport = transport

    def _require_config(self) -> Tuple[str, str, str]:
        client_id = (self.settings.oauth_google_client_id or "").strip()
        client_secret = (self.settings.oauth_google_client_secret or "").strip()
        redirect_uri = (self.settings.oauth_google_redirect_uri or "").strip()

        if not client_id or not client_secret or not redirect_uri:
            raise OAuthConfigurationError(
                "Google OAuth is not configured. Set OAUTH_GOOGLE_CLIENT_ID, "
                "OAUTH_GOOGLE_CLIENT_SECRET, and OAUTH_GOOGLE_REDIRECT_URI."
            )

        validated_redirect = validate_oauth_redirect_uri(redirect_uri, self.settings.environment)
        return client_id, client_secret, validated_redirect

    async def create_authorization_url(
        self,
        link_user: Optional[User] = None,
        frontend_origin: Optional[str] = None,
    ) -> Tuple[str, int]:
        """
        Generate a Google OAuth 2.0 authorization URL backed by a single-use server state
        with PKCE (S256) and OIDC nonce.
        """
        client_id, _, redirect_uri = self._require_config()
        validated_origin = validate_frontend_origin(frontend_origin, self.settings)

        raw_state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(24)
        ttl = self.settings.oauth_state_ttl_seconds
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)

        state_row = OAuthState(
            state_hash=hash_token(raw_state),
            provider="google",
            nonce=nonce,
            code_verifier=code_verifier,
            link_user_id=link_user.id if link_user is not None else None,
            redirect_origin=validated_origin,
            expires_at=expires_at,
        )
        self.db.add(state_row)
        await self.db.flush()

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": raw_state,
            "nonce": nonce,
            "code_challenge": _pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}", ttl

    async def _consume_state(self, raw_state: Optional[str]) -> OAuthState:
        """
        Atomically validate and consume a single-use OAuth state record.
        Commits consumption even on expired/error paths so states can never be replayed.
        """
        if not raw_state or not raw_state.strip():
            raise InvalidOAuthStateError("Missing OAuth state parameter.")

        digest = hash_token(raw_state.strip())
        stmt = select(OAuthState).where(
            OAuthState.state_hash == digest,
            OAuthState.provider == "google",
        )
        res = await self.db.execute(stmt)
        record = res.scalar_one_or_none()
        if record is None:
            raise InvalidOAuthStateError("Invalid OAuth state parameter.")

        if record.consumed_at is not None:
            raise InvalidOAuthStateError("OAuth state has already been consumed.")

        now = datetime.now(timezone.utc)
        upd = (
            update(OAuthState)
            .where(OAuthState.id == record.id, OAuthState.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        upd_res = await self.db.execute(upd)
        await self.db.commit()
        if (upd_res.rowcount or 0) == 0:
            raise InvalidOAuthStateError("OAuth state has already been consumed.")

        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise InvalidOAuthStateError("OAuth state has expired.")

        return record

    async def _exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> Dict[str, Any]:
        payload = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, transport=self.transport) as client:
                response = await client.post(
                    GOOGLE_TOKEN_ENDPOINT,
                    data=payload,
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            sanitized = _sanitize_oauth_message(str(exc), self.settings, (client_secret,))
            logger.warning("Google OAuth token exchange HTTP error: %s", sanitized)
            raise OAuthProviderError("Failed to communicate with Google OAuth token endpoint.")

        if response.status_code != 200:
            sanitized = _sanitize_oauth_message(response.text, self.settings, (client_secret,))
            logger.warning(
                "Google OAuth token exchange rejected status=%s detail=%s",
                response.status_code,
                sanitized,
            )
            raise OAuthProviderError("Google authorization code exchange failed or code was invalid.")

        try:
            data = response.json()
        except Exception:
            raise OAuthProviderError("Google token endpoint returned malformed JSON.")

        if not isinstance(data, dict):
            raise OAuthProviderError("Google token response must be a JSON object.")

        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise OAuthProviderError("Google token response missing valid access_token.")

        return data

    def _validate_id_token_claims(
        self,
        id_token: str,
        expected_client_id: str,
        expected_nonce: str,
    ) -> Dict[str, Any]:
        """Validate standard OIDC claims (iss, aud, exp, nonce, sub) inside an ID token."""
        try:
            claims = jwt.decode(
                id_token,
                options={
                    "verify_signature": False,
                    "verify_exp": True,
                    "verify_aud": False,
                },
            )
        except jwt.ExpiredSignatureError:
            raise OAuthSecurityError("Google ID token has expired.")
        except jwt.InvalidTokenError:
            raise OAuthSecurityError("Malformed Google ID token payload.")

        if claims.get("iss") not in GOOGLE_VALID_ISSUERS:
            raise OAuthSecurityError("Unexpected OIDC issuer in Google ID token.")

        aud = claims.get("aud")
        if isinstance(aud, list):
            aud_ok = expected_client_id in aud
        else:
            aud_ok = aud == expected_client_id
        if not aud_ok:
            raise OAuthSecurityError("Google ID token audience mismatch.")

        if claims.get("nonce") != expected_nonce:
            raise OAuthSecurityError("Google ID token nonce mismatch.")

        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            raise OAuthSecurityError("Google ID token missing subject identifier.")

        return claims

    async def _fetch_verified_identity(
        self,
        token_data: Dict[str, Any],
        client_id: str,
        expected_nonce: str,
        client_secret: str,
    ) -> VerifiedOAuthIdentity:
        """
        Retrieve identity from TLS-authenticated Google UserInfo and cross-validate
        against any returned OIDC ID token claims and `email_verified=True`.
        """
        access_token = str(token_data["access_token"]).strip()
        raw_id_token = token_data.get("id_token")
        id_claims: Optional[Dict[str, Any]] = None

        if raw_id_token is not None:
            if not isinstance(raw_id_token, str) or not raw_id_token.strip():
                raise OAuthProviderError("Malformed id_token in provider response.")
            id_claims = self._validate_id_token_claims(raw_id_token, client_id, expected_nonce)

        try:
            async with httpx.AsyncClient(timeout=15.0, transport=self.transport) as client:
                resp = await client.get(
                    GOOGLE_USERINFO_ENDPOINT,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            sanitized = _sanitize_oauth_message(str(exc), self.settings, (client_secret, access_token))
            logger.warning("Google OAuth userinfo HTTP error: %s", sanitized)
            raise OAuthProviderError("Failed to retrieve verified Google profile information.")

        if resp.status_code != 200:
            sanitized = _sanitize_oauth_message(resp.text, self.settings, (client_secret, access_token))
            logger.warning("Google OAuth userinfo rejected status=%s detail=%s", resp.status_code, sanitized)
            raise OAuthProviderError("Google user identity verification failed.")

        try:
            info = resp.json()
        except Exception:
            raise OAuthProviderError("Google userinfo endpoint returned malformed JSON.")

        if not isinstance(info, dict):
            raise OAuthProviderError("Google userinfo payload must be a JSON object.")

        sub = info.get("sub")
        email = info.get("email")
        email_verified = info.get("email_verified")

        if not isinstance(sub, str) or not sub.strip():
            raise OAuthProviderError("Google profile missing subject identifier.")
        if id_claims is not None and id_claims["sub"] != sub:
            raise OAuthSecurityError("OIDC ID token subject does not match UserInfo subject.")

        if not isinstance(email, str) or "@" not in email:
            raise OAuthProviderError("Google profile missing valid email address.")
        if email_verified is not True:
            raise OAuthSecurityError(
                "Google account email must be verified before authenticating with EdgeMind."
            )

        normalized_email = email.strip().lower()
        full_name = str(info.get("name") or "").strip() or normalized_email.split("@")[0]

        return VerifiedOAuthIdentity(
            provider="google",
            subject=sub.strip(),
            email=normalized_email,
            email_verified=True,
            full_name=full_name[:255],
        )

    async def _resolve_and_authenticate_user(
        self,
        identity: VerifiedOAuthIdentity,
        link_user_id: Optional[uuid.UUID],
    ) -> User:
        """
        Map a verified Google identity to an EdgeMind User account safely:
        - Existing linked OAuthAccount -> login mapped user (respecting is_active & role).
        - Unlinked + explicit link_user_id -> require active owner & matching email before linking.
        - Unlinked + no link_user_id + email collision -> reject (prevent account takeover).
        - Unlinked + new email -> register User(role='user') and create OAuthAccount binding.
        """
        auth_service = AuthService(self.db)

        stmt = select(OAuthAccount).where(
            OAuthAccount.provider == identity.provider,
            OAuthAccount.provider_subject == identity.subject,
        )
        res = await self.db.execute(stmt)
        existing_link = res.scalar_one_or_none()

        if existing_link is not None:
            if link_user_id is not None and existing_link.user_id != link_user_id:
                raise OAuthAccountConflictError(
                    "This Google identity is already linked to a different EdgeMind account."
                )
            user = await auth_service.get_user_by_id(existing_link.user_id)
            if user is None:
                raise OAuthSecurityError("Linked user account could not be resolved.")
            if not user.is_active:
                raise InactiveAccountError("Account is inactive or disabled.")
            existing_link.provider_email = identity.email
            existing_link.email_verified = True
            await self.db.flush()
            return user

        if link_user_id is not None:
            target_user = await auth_service.get_user_by_id(link_user_id)
            if target_user is None:
                raise OAuthSecurityError("Target account for OAuth linking no longer exists.")
            if not target_user.is_active:
                raise InactiveAccountError("Account is inactive or disabled.")
            if target_user.email.strip().lower() != identity.email:
                raise OAuthSecurityError(
                    "Authenticated EdgeMind account email must match the verified Google email to link."
                )
            link_check = await self.db.execute(
                select(OAuthAccount).where(
                    OAuthAccount.user_id == target_user.id,
                    OAuthAccount.provider == identity.provider,
                )
            )
            if link_check.scalar_one_or_none() is not None:
                raise OAuthAccountConflictError("A Google account is already linked to this EdgeMind user.")
            self.db.add(
                OAuthAccount(
                    user_id=target_user.id,
                    provider=identity.provider,
                    provider_subject=identity.subject,
                    provider_email=identity.email,
                    email_verified=True,
                )
            )
            await self.db.flush()
            return target_user

        # Unauthenticated login with unlinked Google identity: never hijack existing password user
        collision = await auth_service.get_user_by_email(identity.email)
        if collision is not None:
            raise OAuthAccountConflictError(
                "An EdgeMind account with this email already exists. "
                "Sign in with your existing credentials before linking Google authentication."
            )

        new_user = User(
            email=identity.email,
            password_hash=hash_password(_generate_unusable_random_password()),
            full_name=identity.full_name,
            role="user",
            is_active=True,
        )
        self.db.add(new_user)
        await self.db.flush()

        self.db.add(
            OAuthAccount(
                user_id=new_user.id,
                provider=identity.provider,
                provider_subject=identity.subject,
                provider_email=identity.email,
                email_verified=True,
            )
        )
        await self.db.flush()
        return new_user

    async def handle_callback(
        self,
        code: Optional[str],
        state: Optional[str],
        error: Optional[str] = None,
        error_description: Optional[str] = None,
    ) -> Tuple[str, str, int, Optional[str], User]:
        """
        Complete Google OAuth callback verification and issue EdgeMind JWT credentials.

        Returns:
            (access_token, refresh_token, expires_in_seconds, redirect_origin, user)
        """
        client_id, client_secret, redirect_uri = self._require_config()

        # Consume single-use state first whenever supplied, even on provider error callbacks
        stored_state = await self._consume_state(state)

        if error:
            safe_desc = _sanitize_oauth_message(
                error_description or error,
                self.settings,
                (client_secret,),
            )
            raise OAuthProviderError(f"Google OAuth authorization declined or failed: {safe_desc}")

        if not code or not code.strip():
            raise OAuthProviderError("Missing authorization code in Google OAuth callback.")

        token_data = await self._exchange_code(
            code=code.strip(),
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code_verifier=stored_state.code_verifier,
        )

        identity = await self._fetch_verified_identity(
            token_data=token_data,
            client_id=client_id,
            expected_nonce=stored_state.nonce,
            client_secret=client_secret,
        )

        user = await self._resolve_and_authenticate_user(
            identity=identity,
            link_user_id=stored_state.link_user_id,
        )

        auth_service = AuthService(self.db)
        access_token, raw_refresh, expires_in = await auth_service.create_user_tokens(user)
        return access_token, raw_refresh, expires_in, stored_state.redirect_origin, user


def render_oauth_popup_html(
    target_origin: str,
    event_payload: Dict[str, Any],
) -> str:
    """
    Render a minimal HTML response delivering OAuth completion or error via `window.opener.postMessage`
    strictly to the pre-validated `target_origin` (never using wildcard `*`).
    """
    safe_origin_json = json.dumps(target_origin)
    safe_payload_json = json.dumps(event_payload).replace("<", "\\u003c").replace(">", "\\u003e")
    status_label = html.escape(
        "Authentication succeeded. You may close this window."
        if event_payload.get("type") == "edgemind:oauth-callback"
        else "Authentication could not be completed. You may close this window."
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>EdgeMind Authentication</title></head>"
        "<body style='font-family:system-ui,sans-serif;background:#0b1020;color:#e5e7eb;"
        "display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
        f"<p>{status_label}</p>"
        "<script>"
        "(() => {"
        f"  const targetOrigin = {safe_origin_json};"
        f"  const payload = {safe_payload_json};"
        "  if (window.opener && !window.opener.closed) {"
        "    window.opener.postMessage(payload, targetOrigin);"
        "  }"
        "  window.close();"
        "})();"
        "</script></body></html>"
    )
