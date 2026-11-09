"""
SQLAlchemy 2.0 Project Model.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from core.database.base import Base, TimestampMixin, utc_now


class Project(Base, TimestampMixin):
    """
    Project entity representing a codebase or practice collection under test intelligence.
    Supports multi-tenant ownership via owner_user_id.
    """
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_projects_owner_user_id_users"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    language: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        default="python",
    )
    technology_stack: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Relationships
    owner: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="projects",
    )
    analysis_sessions: Mapped[List["AnalysisSession"]] = relationship(
        "AnalysisSession",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a clean dictionary."""
        return {
            "id": str(self.id),
            "owner_user_id": str(self.owner_user_id) if self.owner_user_id else None,
            "name": self.name,
            "description": self.description,
            "language": self.language,
            "technology_stack": self.technology_stack,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

