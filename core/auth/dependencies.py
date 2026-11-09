"""
FastAPI Security & Authentication Dependencies.

Provides:
- OAuth2 Bearer token extraction
- JWT access token validation (signature, expiry, claims, issuer, audience)
- User existence and active status verification
- Role-based authorization guard (USER vs. ADMIN)
- Optional user dependency for backward-compatible anonymous endpoints
"""

from typing import Optional
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.security import decode_jwt_token
from core.auth.service import AuthService
from core.database.connection import get_db
from core.database.models import User

# Standard OAuth2 scheme (enforces Authorization: Bearer <token>)
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=True,
)

# Optional scheme for endpoints supporting both anonymous and authenticated usage
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


def get_auth_service(db: Optional[AsyncSession] = Depends(get_db)) -> AuthService:
    """Dependency providing an active AuthService instance."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence is not configured or currently unreachable.",
        )
    return AuthService(db)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """
    Validate incoming Bearer JWT access token and return the associated User entity.
    Never trusts client-supplied user IDs in query params or bodies.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_jwt_token(token, expected_type="access")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {err}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise credentials_exception

    try:
        user_uuid = uuid.UUID(sub)
    except (ValueError, TypeError):
        raise credentials_exception

    user = await auth_service.get_user_by_id(user_uuid)
    if not user:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the authenticated user account is in an active status."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account.",
        )
    return current_user


async def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Optional[AsyncSession] = Depends(get_db),
) -> Optional[User]:
    """
    Optional authentication dependency for backward-compatible endpoints.
    If no token is supplied, returns None without raising an error.
    If a valid token is supplied, resolves the User.
    If a malformed or expired token is supplied, raises 401.
    """
    if not token or db is None:
        return None

    auth_service = AuthService(db)
    try:
        payload = decode_jwt_token(token, expected_type="access")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        return None

    try:
        user_uuid = uuid.UUID(sub)
    except (ValueError, TypeError):
        return None

    user = await auth_service.get_user_by_id(user_uuid)
    if user and user.is_active:
        return user
    return None


def require_role(required_role: str):
    """
    Role-based authorization guard factory.
    Verifies that the authenticated user possesses the specified role.
    """
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires '{required_role}' privileges.",
            )
        return current_user

    return role_checker

