"""
Authentication & User Profiles REST API Routers.

Endpoints:
- POST /api/v1/auth/register (201 Created / 409 Conflict)
- POST /api/v1/auth/login (200 OK / 401 Unauthorized / 403 Forbidden)
- POST /api/v1/auth/refresh (200 OK / 401 Unauthorized / 403 Forbidden)
- POST /api/v1/auth/logout (200 OK)
- GET /api/v1/users/me (200 OK)
- PATCH /api/v1/users/me (200 OK)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import (
    get_auth_service,
    get_current_active_user,
    get_optional_current_user,
)
from core.auth.oauth import (
    GoogleOAuthService,
    InvalidOAuthStateError,
    OAuthAccountConflictError,
    OAuthConfigurationError,
    OAuthProviderError,
    OAuthSecurityError,
    render_oauth_popup_html,
)
from core.auth.schemas import (
    MessageResponse,
    OAuthAuthorizationResponse,
    RefreshRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from core.auth.security import PasswordPolicyError
from core.auth.service import (
    AuthService,
    DuplicateEmailError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidSessionTokenError,
    TokenReuseDetectedError,
)
from core.config import get_settings
from core.database.connection import get_db
from core.database.models import User
from core.schemas import ErrorResponse

# Routers
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["Users"])


# -----------------------------------------------------------------------------
# Authentication Endpoints
# -----------------------------------------------------------------------------

@auth_router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"model": UserResponse, "description": "User account created successfully"},
        409: {"model": ErrorResponse, "description": "Email address already registered"},
        422: {"model": ErrorResponse, "description": "Password policy or format validation error"},
        503: {"model": ErrorResponse, "description": "Database persistence unavailable"},
    },
)
async def register(
    payload: UserRegister,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Register a new user account with role='user'.
    Enforces password complexity policy and rejects duplicate emails.
    """
    try:
        user = await auth_service.register_user(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        )
        return user.to_dict()
    except DuplicateEmailError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        )
    except PasswordPolicyError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        )


@auth_router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": TokenResponse, "description": "Authentication successful, tokens issued"},
        401: {"model": ErrorResponse, "description": "Invalid email or password"},
        403: {"model": ErrorResponse, "description": "Account is inactive"},
        503: {"model": ErrorResponse, "description": "Database persistence unavailable"},
    },
)
async def login(
    payload: UserLogin,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Authenticate user credentials and issue an access and refresh token pair.
    Uses generic error responses to prevent user email enumeration.
    """
    try:
        user = await auth_service.authenticate_user(
            email=payload.email,
            password=payload.password,
        )
        access_token, raw_refresh, expires_in = await auth_service.create_user_tokens(user)
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=expires_in,
        )
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InactiveAccountError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        )


@auth_router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": TokenResponse, "description": "Tokens successfully rotated"},
        401: {"model": ErrorResponse, "description": "Invalid, expired, or reused refresh token"},
        403: {"model": ErrorResponse, "description": "Account is inactive"},
        503: {"model": ErrorResponse, "description": "Database persistence unavailable"},
    },
)
async def refresh_tokens(
    payload: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Rotate an existing refresh token:
    - Verifies token validity and signature
    - Detects reuse of previously revoked tokens
    - Issues a new access token and fresh refresh token
    """
    try:
        new_access, new_refresh, expires_in = await auth_service.rotate_refresh_token(
            raw_refresh_token=payload.refresh_token,
        )
        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=expires_in,
        )
    except TokenReuseDetectedError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidSessionTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InactiveAccountError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        )


@auth_router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": MessageResponse, "description": "Successfully logged out and session revoked"},
        401: {"model": ErrorResponse, "description": "Invalid or expired access token"},
        503: {"model": ErrorResponse, "description": "Database persistence unavailable"},
    },
)
async def logout(
    payload: Optional[RefreshRequest] = None,
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Logout the authenticated user.
    If a refresh token is supplied in the request body, revokes that specific session.
    Otherwise, revokes all active sessions for the user.
    """
    if payload and payload.refresh_token:
        await auth_service.revoke_refresh_token(payload.refresh_token)
    else:
        await auth_service.revoke_all_user_sessions(current_user.id)

    return MessageResponse(message="Successfully logged out.")


# -----------------------------------------------------------------------------
# OAuth 2.0 / OIDC Authentication Endpoints (Google)
# -----------------------------------------------------------------------------

def get_google_oauth_service(
    db: Optional[AsyncSession] = Depends(get_db),
) -> GoogleOAuthService:
    """Dependency providing GoogleOAuthService backed by active DB session."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence is not configured or currently unreachable.",
        )
    return GoogleOAuthService(db=db, settings=get_settings())


@auth_router.get(
    "/oauth/google",
    response_model=OAuthAuthorizationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": OAuthAuthorizationResponse, "description": "Google OAuth authorization URL"},
        302: {"description": "Redirect to Google OAuth authorization endpoint when redirect=true"},
        400: {"model": ErrorResponse, "description": "Invalid frontend origin parameter"},
        401: {"model": ErrorResponse, "description": "Authentication required when link=true"},
        503: {"model": ErrorResponse, "description": "Google OAuth not configured or database unavailable"},
    },
)
async def google_oauth_authorize(
    redirect: bool = Query(default=False, description="When true, responds with HTTP 302 redirect"),
    link: bool = Query(default=False, description="When true, links Google identity to authenticated user"),
    frontend_origin: Optional[str] = Query(
        default=None,
        description="Optional CORS-allowed frontend origin for postMessage popup callback",
    ),
    current_user: Optional[User] = Depends(get_optional_current_user),
    oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
):
    """
    Initiate Google OAuth 2.0 Authorization Code flow with PKCE and single-use CSRF state.
    """
    if link and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to link a Google account.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        auth_url, expires_in = await oauth_service.create_authorization_url(
            link_user=current_user if link else None,
            frontend_origin=frontend_origin,
        )
    except OAuthConfigurationError as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err))
    except OAuthSecurityError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    if redirect:
        return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)

    return OAuthAuthorizationResponse(
        provider="google",
        authorization_url=auth_url,
        expires_in=expires_in,
    )


@auth_router.get(
    "/oauth/google/callback",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": TokenResponse, "description": "Authenticated via Google OAuth; EdgeMind JWT pair issued"},
        400: {"model": ErrorResponse, "description": "Invalid, expired, replayed state, or missing code"},
        401: {"model": ErrorResponse, "description": "Unverified email or failed OIDC verification"},
        403: {"model": ErrorResponse, "description": "Account is inactive"},
        409: {"model": ErrorResponse, "description": "Account linking conflict"},
        502: {"model": ErrorResponse, "description": "Google OAuth upstream exchange failure"},
        503: {"model": ErrorResponse, "description": "Google OAuth not configured or database unavailable"},
    },
)
async def google_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
    oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
):
    """
    Handle Google OAuth 2.0 callback: validate single-use state, exchange code,
    verify Google OIDC identity and email verification, and issue EdgeMind JWT credentials.
    """
    try:
        access_token, refresh_token, expires_in, redirect_origin, user = (
            await oauth_service.handle_callback(
                code=code,
                state=state,
                error=error,
                error_description=error_description,
            )
        )
    except OAuthConfigurationError as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err))
    except InvalidOAuthStateError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except OAuthSecurityError as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err))
    except InactiveAccountError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except OAuthAccountConflictError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except OAuthProviderError as err:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err))

    if redirect_origin:
        html_body = render_oauth_popup_html(
            target_origin=redirect_origin,
            event_payload={
                "type": "edgemind:oauth-callback",
                "tokens": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "bearer",
                    "expires_in": expires_in,
                },
                "email": user.email,
            },
        )
        return HTMLResponse(content=html_body, status_code=status.HTTP_200_OK)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


# -----------------------------------------------------------------------------
# User Profile Endpoints
# -----------------------------------------------------------------------------

@users_router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": UserResponse, "description": "Current user profile"},
        401: {"model": ErrorResponse, "description": "Unauthenticated or invalid token"},
        403: {"model": ErrorResponse, "description": "Account is inactive"},
    },
)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
):
    """Retrieve the authenticated user's own profile. Password hashes are never exposed."""
    return current_user.to_dict()


@users_router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": UserResponse, "description": "User profile updated"},
        400: {"model": ErrorResponse, "description": "Current password incorrect or validation error"},
        401: {"model": ErrorResponse, "description": "Unauthenticated"},
        422: {"model": ErrorResponse, "description": "New password policy error"},
    },
)
async def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Update user profile attributes (full_name, password).
    Users cannot modify their own role, account privileges, or email address.
    """
    try:
        updated_user = await auth_service.update_user_profile(
            user=current_user,
            full_name=payload.full_name,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
        return updated_user.to_dict()
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except PasswordPolicyError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        )

