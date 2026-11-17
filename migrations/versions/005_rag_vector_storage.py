"""RAG Vector Storage migration: Create knowledge_documents and knowledge_chunks.

Provides vector storage for RAG pipeline with tenant isolation,
SHA-256 fingerprints, and dialect-aware vector/JSON fallback.

Revision ID: 005_rag_vector_storage
Revises: 004_postgresql_jsonb_report_store
Create Date: 2026-11-17 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_IMPORTABLE = True
except ImportError:
    PGVECTOR_IMPORTABLE = False
    Vector = None  # type: ignore

# revision identifiers, used by Alembic.
revision: str = "005_rag_vector_storage"
down_revision: Union[str, None] = "004_postgresql_jsonb_report_store"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 0. Check and enable pgvector extension if PostgreSQL is active and extension is available
    has_pgvector = False
    if is_postgres:
        conn = bind.connection
        res = conn.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).scalar()
        if res:
            op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))
            has_pgvector = True

    # 1. Create knowledge_documents table
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_uri", sa.String(length=1024), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "doc_metadata",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("is_global", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_knowledge_documents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_knowledge_documents_project_id_projects"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_documents_content_hash"),
        "knowledge_documents",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_documents_tenant_scope",
        "knowledge_documents",
        ["user_id", "project_id", "is_global"],
        unique=False,
    )

    # 2. Determine embedding column type
    if is_postgres and has_pgvector and PGVECTOR_IMPORTABLE and Vector is not None:
        embedding_col_type = Vector(1536)
    else:
        embedding_col_type = sa.JSON().with_variant(
            Vector(1536) if (PGVECTOR_IMPORTABLE and Vector is not None) else sa.JSON(),
            "postgresql",
        )

    # 3. Create knowledge_chunks table
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("vector_dim", sa.Integer(), nullable=True),
        sa.Column("embedding", embedding_col_type, nullable=True),
        sa.Column(
            "chunk_metadata",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("is_global", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_knowledge_chunks_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_knowledge_chunks_project_id_projects"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_content_hash"),
        "knowledge_chunks",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_chunks_tenant_scope",
        "knowledge_chunks",
        ["user_id", "project_id", "is_global"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_chunks_doc_chunk",
        "knowledge_chunks",
        ["document_id", "chunk_index"],
        unique=False,
    )

    # 4. Create HNSW vector index for cosine similarity if pgvector is active
    if is_postgres and has_pgvector:
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw "
                "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw;"))

    op.drop_index("ix_knowledge_chunks_doc_chunk", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_tenant_scope", table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_content_hash"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")

    op.drop_index("ix_knowledge_documents_tenant_scope", table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_content_hash"), table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
