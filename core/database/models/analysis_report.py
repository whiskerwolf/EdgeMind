"""
SQLAlchemy 2.0 AnalysisReport Model.

Stores full test intelligence reports, synthesized edge-case candidates,
coverage gaps, and parsed constraints using PostgreSQL JSONB (with SQLite JSON fallback).
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from core.database.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from core.database.models.analysis_session import AnalysisSession
    from core.database.models.problem import Problem
    from core.database.models.project import Project
    from core.database.models.user import User


class AnalysisReport(Base, TimestampMixin):
    """
    AnalysisReport entity storing the complete structured analysis report document.
    Employs native PostgreSQL JSONB with GIN indexing for high-performance querying,
    and falls back to standard JSON on SQLite for portable in-memory unit testing.
    """
    __tablename__ = "analysis_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_sessions.id", ondelete="CASCADE", name="fk_analysis_reports_session_id"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_analysis_reports_user_id"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_analysis_reports_project_id"),
        nullable=True,
        index=True,
    )
    problem_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL", name="fk_analysis_reports_problem_id"),
        nullable=True,
        index=True,
    )
    problem_slug: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    report_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="1.0.0",
        server_default="1.0.0",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Relationships
    session: Mapped["AnalysisSession"] = relationship(
        "AnalysisSession",
        back_populates="report",
    )
    user: Mapped[Optional["User"]] = relationship(
        "User",
        lazy="selectin",
    )
    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        lazy="selectin",
    )
    problem: Mapped[Optional["Problem"]] = relationship(
        "Problem",
        lazy="selectin",
    )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to standardized dictionary adhering to schema_version 1.0.0.
        Merges canonical identifiers and timestamps into the JSONB payload.
        """
        payload = dict(self.report_data) if self.report_data else {}
        payload["id"] = str(self.id)
        payload["analysis_session_id"] = str(self.analysis_session_id)
        payload["user_id"] = str(self.user_id) if self.user_id else None
        payload["project_id"] = str(self.project_id) if self.project_id else None
        payload["problem_id"] = str(self.problem_id) if self.problem_id else None
        payload["problem_slug"] = self.problem_slug or payload.get("problem_slug")
        payload["schema_version"] = self.schema_version or "1.0.0"
        payload["created_at"] = self.created_at.isoformat() if self.created_at else None
        payload["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return payload
