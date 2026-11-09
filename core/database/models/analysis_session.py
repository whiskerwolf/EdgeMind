"""
SQLAlchemy 2.0 AnalysisSession Model.
"""

from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base, TimestampMixin


class AnalysisSession(Base, TimestampMixin):
    """
    AnalysisSession entity storing metadata and high-level metrics for an EdgeMind analysis.
    Complex reports and candidate input payloads will reside in MongoDB in future phases.
    """
    __tablename__ = "analysis_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    problem_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    analysis_mode: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="BASELINE_DRIVEN",
    )
    language: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="python",
    )
    analysis_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="SUCCESS",
        index=True,
    )
    gaps_detected: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    candidates_generated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    duration_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    # Relationships
    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        back_populates="analysis_sessions",
    )
    problem: Mapped[Optional["Problem"]] = relationship(
        "Problem",
        back_populates="analysis_sessions",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a clean dictionary."""
        return {
            "id": str(self.id),
            "project_id": str(self.project_id) if self.project_id else None,
            "problem_id": str(self.problem_id) if self.problem_id else None,
            "analysis_mode": self.analysis_mode,
            "language": self.language,
            "analysis_status": self.analysis_status,
            "gaps_detected": self.gaps_detected,
            "candidates_generated": self.candidates_generated,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

