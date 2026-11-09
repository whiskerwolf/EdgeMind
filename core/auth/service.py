"""
EdgeMind Authentication Service.

Orchestrates user management, credential verification, session issuance,
refresh token rotation with reuse detection, and administrator bootstrap.
"""

from datetime import datetime, timezone
import logging
from typing import Optional, Tuple
import uuid

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    hash_password,
    hash_token,
    verify_password,
)
from core.config import get_settings
from core.database.base import utc_now
from core.database.models import RefreshToken, User

logger = logging.getLogger("edgemind.auth")


class AuthError(Exception):
    """Base exception for authentication failures."""
    pass


class DuplicateEmailError(AuthError):
    """Raised when registering an email that already exists."""
    pass


class InvalidCredentialsError(AuthError):
    """Raised on invalid login or password mismatch."""
    pass


class InactiveAccountError(AuthError):
    """Raised when attempting authentication on a deactivated account."""
    pass


class InvalidSessionTokenError(AuthError):
    """Raised when a refresh token is invalid, expired, or malformed."""
    pass


class TokenReuseDetectedError(AuthError):
    """Security alert: Raised when an already-revoked refresh token is re-submitted."""
    pass


class AuthService:
    """Authentication and session management services."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Fetch user by normalized email address."""
        normalized = email.strip().lower()
        stmt = select(User).where(User.email == normalized)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Fetch user by UUID."""
        stmt = select(User).where(User.id == user_id)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def register_user(
        self,
        email: str,
        password: str,
        full_name: str,
    ) -> User:
        """
        Register a new user account with role='user'.
        Public registration permanently defaults to role='user'.
        """
        normalized_email = email.strip().lower()
        existing = await self.get_user_by_email(normalized_email)
        if existing:
            raise DuplicateEmailError(f"An account with email '{normalized_email}' already exists.")

        hashed_password = hash_password(password)
        user = User(
            email=normalized_email,
            password_hash=hashed_password,
            full_name=full_name.strip(),
            role="user",
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def authenticate_user(self, email: str, password: str) -> User:
        """
        Authenticate user credentials.
        Returns generic InvalidCredentialsError to prevent email enumeration.
        """
        user = await self.get_user_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid email or password.")

        if not user.is_active:
            raise InactiveAccountError("Account is inactive or disabled.")

        return user

    async def create_user_tokens(self, user: User) -> Tuple[str, str, int]:
        """
        Issue a new signed access token and persisted refresh token pair.
        Returns: (access_token, raw_refresh_token, expires_in_seconds)
        """
        settings = get_settings()
        access_token = create_access_token(user.id, role=user.role)
        raw_refresh, jti, expires_at = create_refresh_token(user.id)

        token_digest = hash_token(raw_refresh)
        session_record = RefreshToken(
            user_id=user.id,
            token_hash=token_digest,
            jti=jti,
            expires_at=expires_at,
            is_revoked=False,
        )
        self.db.add(session_record)
        await self.db.flush()

        expires_in = settings.jwt_access_token_expire_minutes * 60
        return access_token, raw_refresh, expires_in

    async def rotate_refresh_token(self, raw_refresh_token: str) -> Tuple[str, str, int]:
        """
        Rotate an active refresh token:
        1. Decode and validate JWT structure, type, and expiration.
        2. Query non-reversible hash in database.
        3. Detect reuse: if previously revoked, revoke all sessions for that user!
        4. Invalidate old token and issue fresh access + refresh token pair.
        """
        try:
            payload = decode_jwt_token(raw_refresh_token, expected_type="refresh")
        except jwt.ExpiredSignatureError:
            raise InvalidSessionTokenError("Refresh token has expired.")
        except jwt.InvalidTokenError as err:
            raise InvalidSessionTokenError(f"Invalid refresh token: {err}")

        token_digest = hash_token(raw_refresh_token)
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_digest)
        res = await self.db.execute(stmt)
        session_record = res.scalar_one_or_none()

        if not session_record:
            raise InvalidSessionTokenError("Refresh token session was not found or has been revoked.")

        # REUSE DETECTION: If token is already marked revoked, potential token theft occurred!
        if session_record.is_revoked:
            user_id = session_record.user_id
            logger.warning(
                f"SECURITY ALERT: Reused revoked refresh token detected for user {user_id}! "
                f"Revoking all active sessions for this account."
            )
            # Invalidate all active sessions for this user as a security safeguard
            await self.revoke_all_user_sessions(user_id)
            await self.db.commit()
            raise TokenReuseDetectedError(
                "Revoked refresh token reuse detected. All sessions have been terminated for security."
            )

        now = datetime.now(timezone.utc)
        expires_at = session_record.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < now:
            session_record.is_revoked = True
            session_record.revoked_at = now
            await self.db.flush()
            raise InvalidSessionTokenError("Refresh token has expired.")

        # Verify associated user account
        user = await self.get_user_by_id(session_record.user_id)
        if not user or not user.is_active:
            session_record.is_revoked = True
            session_record.revoked_at = now
            await self.db.flush()
            raise InactiveAccountError("Account associated with this session is inactive.")

        # Mark current session as revoked
        session_record.is_revoked = True
        session_record.revoked_at = now

        # Issue successor refresh token
        settings = get_settings()
        new_access_token = create_access_token(user.id, role=user.role)
        new_raw_refresh, new_jti, new_expires = create_refresh_token(user.id)
        new_token_digest = hash_token(new_raw_refresh)

        new_session = RefreshToken(
            user_id=user.id,
            token_hash=new_token_digest,
            jti=new_jti,
            expires_at=new_expires,
            is_revoked=False,
        )
        self.db.add(new_session)
        await self.db.flush()

        session_record.replaced_by = new_session.id
        await self.db.flush()

        expires_in = settings.jwt_access_token_expire_minutes * 60
        return new_access_token, new_raw_refresh, expires_in

    async def revoke_refresh_token(self, raw_refresh_token: str) -> bool:
        """Revoke a specific refresh token upon logout."""
        token_digest = hash_token(raw_refresh_token)
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_digest)
        res = await self.db.execute(stmt)
        session_record = res.scalar_one_or_none()
        if session_record and not session_record.is_revoked:
            session_record.is_revoked = True
            session_record.revoked_at = datetime.now(timezone.utc)
            await self.db.flush()
            return True
        return False

    async def revoke_all_user_sessions(self, user_id: uuid.UUID) -> int:
        """Revoke all active refresh sessions for a specific user."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))
            .values(is_revoked=True, revoked_at=datetime.now(timezone.utc))
        )
        res = await self.db.execute(stmt)
        await self.db.flush()
        return res.rowcount

    async def update_user_profile(
        self,
        user: User,
        full_name: Optional[str] = None,
        current_password: Optional[str] = None,
        new_password: Optional[str] = None,
    ) -> User:
        """
        Update user profile attributes.
        Privileges and roles remain strictly immutable through profile endpoints.
        """
        if new_password is not None:
            if not current_password:
                raise InvalidCredentialsError("Current password must be provided to set a new password.")
            if not verify_password(current_password, user.password_hash):
                raise InvalidCredentialsError("Current password does not match.")
            user.password_hash = hash_password(new_password)

        if full_name is not None and full_name.strip():
            user.full_name = full_name.strip()

        user.updated_at = utc_now()
        await self.db.flush()
        return user

    async def bootstrap_admin(self) -> Optional[User]:
        """
        Safe administrator bootstrap mechanism.
        Checks if any admin exists. If not, and environment configuration
        supplies ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD, creates an admin.
        Never exposes an unauthenticated endpoint to create administrators.
        """
        settings = get_settings()
        email = settings.admin_bootstrap_email
        password = settings.admin_bootstrap_password

        if not email or not password:
            return None

        # Check if an administrator already exists
        stmt = select(User).where(User.role == "admin").limit(1)
        res = await self.db.execute(stmt)
        if res.scalar_one_or_none() is not None:
            return None

        normalized_email = email.strip().lower()
        existing = await self.get_user_by_email(normalized_email)
        if existing:
            existing.role = "admin"
            await self.db.flush()
            logger.info(f"Promoted existing account '{normalized_email}' to administrator.")
            return existing

        hashed_pw = hash_password(password)
        admin = User(
            email=normalized_email,
            password_hash=hashed_pw,
            full_name="EdgeMind Administrator",
            role="admin",
            is_active=True,
        )
        self.db.add(admin)
        await self.db.flush()
        logger.info(f"Successfully bootstrapped initial administrator account: {normalized_email}")
        return admin
