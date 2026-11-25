# EdgeMind Google OAuth 2.0 / OIDC Authentication Guide

## Architecture Overview

EdgeMind integrates **Google OAuth 2.0 Authorization Code Flow** (with **PKCE `S256`** and **OIDC `nonce`** verification) directly into its existing authentication, JWT issuance, multi-tenancy, and RBAC system rather than maintaining a separate authorization stack:

- **Configuration**: [`core/config.py`](file:///C:/Users/DELL/Projects/EdgeMind/core/config.py)
- **Database Models & Migration**: `OAuthAccount` and `OAuthState` in [`core/database/models/oauth_account.py`](file:///C:/Users/DELL/Projects/EdgeMind/core/database/models/oauth_account.py) and [`migrations/versions/009_oauth_accounts.py`](file:///C:/Users/DELL/Projects/EdgeMind/migrations/versions/009_oauth_accounts.py)
- **OAuth Service**: [`core/auth/oauth.py`](file:///C:/Users/DELL/Projects/EdgeMind/core/auth/oauth.py) (`GoogleOAuthService`)
- **API Endpoints**: [`core/auth/router.py`](file:///C:/Users/DELL/Projects/EdgeMind/core/auth/router.py)
- **Frontend UI Integration**: `HistoryAuthCard` & `AnalysisContext` (`loginWithGoogle`) in [`web/src/components/history/HistoryAuthCard.tsx`](file:///C:/Users/DELL/Projects/EdgeMind/web/src/components/history/HistoryAuthCard.tsx)

Once Google identity verification succeeds, EdgeMind issues standard EdgeMind `TokenResponse` credentials (`access_token` + rotating `refresh_token`) bound to the user's `User.role` and tenant UUID. Google provider access/refresh tokens are never stored in EdgeMind's database or returned to clients.

---

## Authorization Code Flow

1. **Initiation (`GET /api/v1/auth/oauth/google`)**:
   - Validates `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`, and `OAUTH_GOOGLE_REDIRECT_URI` (returns `503 Service Unavailable` cleanly when unconfigured without affecting email/password JWT login).
   - Generates a 256-bit random `state` token, stores its SHA-256 digest (`state_hash`), PKCE `code_verifier`, OIDC `nonce`, expiration timestamp (`OAUTH_STATE_TTL_SECONDS`, default 600s), and optional `link_user_id` / CORS-validated `redirect_origin` in `oauth_states`.
   - Returns `{ "provider": "google", "authorization_url": "...", "expires_in": 600 }` (or HTTP `302` when `redirect=true`).
2. **Callback (`GET /api/v1/auth/oauth/google/callback`)**:
   - Atomically consumes the single-use `state` record (`consumed_at = now` committed before proceeding, preventing replay).
   - Rejects missing, unknown, expired, or previously consumed states with `400 Bad Request`.
   - Exchanges the authorization `code` + `code_verifier` at `https://oauth2.googleapis.com/token`.
   - Verifies OIDC `id_token` claims (`iss`, `aud`, `exp`, `nonce`, `sub`) when returned and fetches profile metadata from `https://openidconnect.googleapis.com/v1/userinfo`, enforcing `email_verified === true` and matching `sub`.
   - Authenticates or provisions the EdgeMind user and issues EdgeMind JWT credentials.

---

## Environment Configuration & Redirect URIs

```env
OAUTH_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
OAUTH_GOOGLE_CLIENT_SECRET=your-client-secret
# Local development:
OAUTH_GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/v1/auth/oauth/google/callback
# Production (HTTPS required):
# OAUTH_GOOGLE_REDIRECT_URI=https://edgemind.example.com/api/v1/auth/oauth/google/callback
```

### Google Cloud Console Setup
1. Create an OAuth 2.0 Web Application client in Google Cloud Console.
2. Add the exact `OAUTH_GOOGLE_REDIRECT_URI` to **Authorized redirect URIs**.
3. If using the React dashboard sign-in button, register the frontend origin (`http://localhost:5173` in dev or `https://edgemind.example.com` in production) in `CORS_ORIGINS` so `frontend_origin` validation permits popup `postMessage` delivery.

---

## Production HTTPS & Security Protections

- **Production HTTPS Enforcement**: When `ENVIRONMENT=production`, non-HTTPS callback redirect URIs are rejected with `503 Service Unavailable` (`validate_oauth_redirect_uri`).
- **One-Time CSRF State & Replay Protection**: Plaintext `state` tokens are never persisted; SHA-256 digests are consumed atomically via `UPDATE ... WHERE consumed_at IS NULL`.
- **Open Redirect Prevention**: `frontend_origin` is validated against `Settings.cors_origins`, and popup `postMessage` uses the exact validated origin (never wildcard `"*"`).
- **Account Linking & Anti-Takeover**:
  - Returning users match on immutable `(provider="google", provider_subject=sub)` — never mutable email alone.
  - Unverified Google emails (`email_verified !== true`) are rejected (`401 Unauthorized`).
  - Unauthenticated OAuth logins whose email collides with an existing password account are rejected (`409 Conflict`) instead of silently merging accounts.
  - Explicit linking (`GET /api/v1/auth/oauth/google?link=true`) requires a valid Bearer JWT and verifies that the authenticated EdgeMind email matches the verified Google email.
  - Newly provisioned OAuth users always receive `role="user"` (never auto-admin); inactive users (`is_active=False`) are rejected with `403 Forbidden`.
- **Secret Redaction**: `OAUTH_GOOGLE_CLIENT_SECRET` is registered in `Settings.sanitize_error(...)` and masked alongside any upstream Google `access_token` on HTTP errors.

---

## Known Limitations

- Google is the currently supported OAuth 2.0 provider.
- Automatic migration assumes Alembic revision `009_oauth_accounts` (`oauth_accounts` and `oauth_states` tables) has been applied via `alembic upgrade head`.
- Automated tests mock Google's `/token` and `/userinfo` HTTP endpoints via `httpx.MockTransport` without requiring live Google Cloud credentials; OIDC ID token validation cross-checks claims against `/userinfo` over TLS rather than fetching Google JWKS offline.
