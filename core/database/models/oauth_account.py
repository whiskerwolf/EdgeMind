"""
SQLAlchemy 2.0 OAuth Account & Single-Use State Models.

Stores:
- `OAuthAccount`: verified external OIDC subject bindings linked to EdgeMind `User` rows.
  Provider access/refresh tokens are intentionally NOT stored.
- `OAuthState`: cryptographically hashed, expiring, single-use CSRF & PKCE state records.
"""

from datetime import datetime
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base, TimestampMixin, utc_now


class OAuthAccount(Base, TimestampMixin):
    """Links an EdgeMind User to an external OAuth/OIDC provider subject."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        sa.UniqueConstraint("provider", "provider_subject", name="uq_oauth_provider_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_oauth_accounts_user_id"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        index=True,
    )
    provider_subject: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    provider_email: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    email_verified: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="oauth_accounts")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "provider": self.provider,
            "email_verified": self.email_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OAuthState(Base, TimestampMixin):
    """Single-use, expiring server-side OAuth CSRF + PKCE + OIDC nonce record."""

    __tablename__ = "oauth_states"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    state_hash: Mapped[str] = mapped_column(
        sa.String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
    )
    nonce: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
    )
    code_verifier: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
    )
    link_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_oauth_states_link_user_id"),
        nullable=True,
    )
    redirect_origin: Mapped[Optional[str]] = mapped_column(
        sa.String(512),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
