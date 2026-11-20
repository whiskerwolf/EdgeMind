"""
SQLAlchemy 2.0 AiTokenUsage Model.

Provides token usage accounting and API cost ledger with tenant isolation,
user/project attribution, and SQLite fallback compatibility.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, TYPE_CHECKING
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from core.database.models.analysis_session import AnalysisSession
    from core.database.models.project import Project
    from core.database.models.user import User


class AiTokenUsage(Base, TimestampMixin):
    """
    Ledger record for an individual LLM API invocation or agent reasoning step.
    Tracks token counts, estimated USD costs, pricing versions, and tenant attribution.
    """
    __tablename__ = "ai_token_usages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_sessions.id", ondelete="CASCADE", name="fk_ai_token_usages_session_id"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_ai_token_usages_user_id"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_ai_token_usages_project_id"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="openai",
    )
    model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    estimated_cost_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 12, asdecimal=True),
        nullable=True,
    )
    pricing_version: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    usage_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ACTUAL_PROVIDER",
        index=True,
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )

    # Relationships
    session: Mapped[Optional["AnalysisSession"]] = relationship(
        "AnalysisSession",
        foreign_keys=[session_id],
    )
    user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[user_id],
    )
    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        foreign_keys=[project_id],
    )

    __table_args__ = (
        Index("ix_ai_token_usages_user_created", "user_id", "created_at"),
        Index("ix_ai_token_usages_project_created", "project_id", "created_at"),
        Index("uq_ai_token_usages_provider_request_id", "provider", "request_id", unique=True),
    )
