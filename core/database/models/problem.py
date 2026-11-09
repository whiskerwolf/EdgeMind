"""
SQLAlchemy 2.0 Problem Model.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base, TimestampMixin


class Problem(Base, TimestampMixin):
    """
    Problem entity representing an algorithmic problem (e.g. from LeetCode).
    Has a composite unique constraint on (platform, problem_slug).
    """
    __tablename__ = "problems"
    __table_args__ = (
        UniqueConstraint("platform", "problem_slug", name="uq_problems_platform_problem_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    platform: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="leetcode",
        index=True,
    )
    problem_slug: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    difficulty: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )

    # Relationships
    analysis_sessions: Mapped[List["AnalysisSession"]] = relationship(
        "AnalysisSession",
        back_populates="problem",
        passive_deletes=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a clean dictionary."""
        return {
            "id": str(self.id),
            "platform": self.platform,
            "problem_slug": self.problem_slug,
            "title": self.title,
            "difficulty": self.difficulty,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

