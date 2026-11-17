"""
SQLAlchemy 2.0 KnowledgeDocument Model for EdgeMind RAG.

Stores root knowledge documents, source metadata, fingerprints,
and tenant ownership scoping.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from core.database.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from core.database.models.knowledge_chunk import KnowledgeChunk
    from core.database.models.project import Project
    from core.database.models.user import User


class KnowledgeDocument(Base, TimestampMixin):
    """
    KnowledgeDocument entity representing an indexed reference source.
    """
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    source_uri: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    doc_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_knowledge_docs_user_id"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_knowledge_docs_project_id"),
        nullable=True,
        index=True,
    )
    is_global: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    # Relationships
    chunks: Mapped[List["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index",
    )

    __table_args__ = (
        Index("ix_knowledge_documents_tenant_scope", "user_id", "project_id", "is_global"),
    )
