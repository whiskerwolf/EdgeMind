"""
User SQLAlchemy 2.0 ORM Model.

Represents an authenticated user entity supporting multi-tenant resource ownership
and role-based authorization (USER / ADMIN).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base, TimestampMixin, utc_now

ALLOWED_ROLES = {"user", "admin"}


class User(Base, TimestampMixin):
    """User account entity with Argon2 password hashing and role assignments."""

    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint(
            "role IN ('user', 'admin')",
            name="ck_users_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        sa.String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default="user",
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Relationships
    projects: Mapped[List["Project"]] = relationship(
        "Project",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    analysis_sessions: Mapped[List["AnalysisSession"]] = relationship(
        "AnalysisSession",
        back_populates="user",
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to safe dictionary representation, permanently omitting password_hash."""
        return {
            "id": str(self.id),
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' role='{self.role}' active={self.is_active}>"
