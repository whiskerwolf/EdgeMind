"""
SQLAlchemy 2.0 KnowledgeChunk Model for EdgeMind RAG.

Stores text chunks, content fingerprints, embedding vectors,
and tenant ownership scoping for vector similarity search.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from core.database.base import Base, utc_now

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    Vector = None  # type: ignore

if TYPE_CHECKING:
    from core.database.models.knowledge_document import KnowledgeDocument
    from core.database.models.project import Project
    from core.database.models.user import User


def get_embedding_column_type(dimensions: int = 1536):
    """
    Return vector column type:
    Uses pgvector Vector on PostgreSQL if available, otherwise falls back to JSON.
    """
    if PGVECTOR_AVAILABLE and Vector is not None:
        return JSON().with_variant(Vector(dimensions), "postgresql")
    return JSON()


class KnowledgeChunk(Base):
    """
    KnowledgeChunk entity representing a vector-indexed segment of a KnowledgeDocument.
    """
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE", name="fk_knowledge_chunks_document_id"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    embedding_model: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    vector_dim: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        get_embedding_column_type(1536),
        nullable=True,
    )
    chunk_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_knowledge_chunks_user_id"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_knowledge_chunks_project_id"),
        nullable=True,
        index=True,
    )
    is_global: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument",
        back_populates="chunks",
    )

    __table_args__ = (
        Index("ix_knowledge_chunks_tenant_scope", "user_id", "project_id", "is_global"),
        Index("ix_knowledge_chunks_doc_chunk", "document_id", "chunk_index"),
    )
