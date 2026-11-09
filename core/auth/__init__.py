"""
EdgeMind Authentication & Multi-Tenancy Package.
"""

from core.auth.dependencies import (
    get_auth_service,
    get_current_active_user,
    get_current_user,
    get_optional_current_user,
    require_role,
)
from core.auth.router import auth_router, users_router
from core.auth.schemas import (
    MessageResponse,
    RefreshRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from core.auth.security import (
    PasswordPolicyError,
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    hash_password,
    hash_token,
    validate_password_policy,
    verify_password,
)
from core.auth.service import AuthService

__all__ = [
    "auth_router",
    "users_router",
    "AuthService",
    "get_current_user",
    "get_current_active_user",
    "get_optional_current_user",
    "require_role",
    "get_auth_service",
    "hash_password",
    "verify_password",
    "hash_token",
    "validate_password_policy",
    "create_access_token",
    "create_refresh_token",
    "decode_jwt_token",
    "PasswordPolicyError",
    "UserRegister",
    "UserLogin",
    "TokenResponse",
    "RefreshRequest",
    "UserResponse",
    "UserUpdate",
    "MessageResponse",
]

