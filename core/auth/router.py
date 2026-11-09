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

from fastapi import APIRouter, Depends, HTTPException, status

from core.auth.dependencies import (
    get_auth_service,
    get_current_active_user,
)
from core.auth.schemas import (
    MessageResponse,
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

