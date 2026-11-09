"""
EdgeMind Authentication Security Layer.

Handles:
- Argon2 password hashing and verification via pwdlib
- Password complexity validation
- Signed JWT access and refresh token creation and decoding via PyJWT
- SHA-256 hashing for non-reversible refresh token database indexing
"""

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Dict, Optional, Tuple
import uuid

import jwt
from pwdlib import PasswordHash

from core.config import get_settings

# Configure Argon2 password hasher
_password_hasher = PasswordHash.recommended()

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class PasswordPolicyError(ValueError):
    """Raised when a candidate password violates complexity requirements."""
    pass


def validate_password_policy(password: str) -> None:
    """
    Validate password complexity requirements:
    - Between 8 and 128 characters
    - At least one uppercase ASCII letter
    - At least one lowercase ASCII letter
    - At least one decimal digit
    - At least one special/punctuation character
    """
    if not isinstance(password, str):
        raise PasswordPolicyError("Password must be a string.")

    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
        )

    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyError(
            f"Password must not exceed {PASSWORD_MAX_LENGTH} characters."
        )

    if not re.search(r"[A-Z]", password):
        raise PasswordPolicyError("Password must contain at least one uppercase letter (A-Z).")

    if not re.search(r"[a-z]", password):
        raise PasswordPolicyError("Password must contain at least one lowercase letter (a-z).")

    if not re.search(r"[0-9]", password):
        raise PasswordPolicyError("Password must contain at least one digit (0-9).")

    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\/`~]', password):
        raise PasswordPolicyError(
            "Password must contain at least one special character (!@#$%^&*(), etc.)."
        )


def hash_password(password: str) -> str:
    """Hash plaintext password using Argon2."""
    validate_password_policy(password)
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against stored Argon2 hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _password_hasher.verify(plain_password, hashed_password)
    except Exception:
        return False


def hash_token(raw_token: str) -> str:
    """
    Produce a non-reversible SHA-256 digest of a refresh token.
    Used to lookup and store session states without persisting raw token strings.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: uuid.UUID,
    role: str = "user",
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate a cryptographically signed HS256 access token with ~15 minute lifetime.
    Contains user UUID, role, type claim, issuer, audience, and expiration.
    """
    settings = get_settings()
    secret = settings.get_jwt_secret_key()

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: uuid.UUID,
    expires_delta: Optional[timedelta] = None,
) -> Tuple[str, str, datetime]:
    """
    Generate a signed HS256 refresh token with ~7 day lifetime and unique JTI.
    Returns: (raw_jwt_token, jti, expire_datetime)
    """
    settings = get_settings()
    secret = settings.get_jwt_secret_key()

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": jti,
    }
    raw_token = jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)
    return raw_token, jti, expire


def decode_jwt_token(raw_token: str, expected_type: str = "access") -> Dict[str, Any]:
    """
    Decode and strictly validate a JWT token:
    - Signature validity using configured secret key
    - Expiration (exp)
    - Issuer (iss)
    - Audience (aud)
    - Token type matching expected_type ('access' or 'refresh')
    """
    settings = get_settings()
    secret = settings.get_jwt_secret_key()

    try:
        payload = jwt.decode(
            raw_token,
            secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iss", "aud", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError:
        raise
    except jwt.InvalidTokenError:
        raise

    token_type = payload.get("type")
    if token_type != expected_type:
        raise jwt.InvalidTokenError(
            f"Invalid token type: expected '{expected_type}', got '{token_type}'."
        )

    return payload

