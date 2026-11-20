"""Add 384-dimensional embedding column and HNSW index for local Ollama RAG.

Revision ID: 007_rag_384_local_embeddings
Revises: 006_ai_token_cost_monitoring
Create Date: 2026-11-20 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_IMPORTABLE = True
except ImportError:
    PGVECTOR_IMPORTABLE = False
    Vector = None  # type: ignore

# revision identifiers, used by Alembic.
revision: str = "007_rag_384_local_embeddings"
down_revision: Union[str, None] = "006_ai_token_cost_monitoring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    has_pgvector = False
    if is_postgres:
        res = bind.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).scalar()
        if res:
            has_pgvector = True

    if is_postgres and has_pgvector and PGVECTOR_IMPORTABLE and Vector is not None:
        embedding_384_col_type = Vector(384)
    else:
        embedding_384_col_type = sa.JSON().with_variant(
            Vector(384) if (PGVECTOR_IMPORTABLE and Vector is not None) else sa.JSON(),
            "postgresql",
        )

    # Add embedding_384 column to knowledge_chunks using batch operations for SQLite compatibility
    with op.batch_alter_table("knowledge_chunks") as batch_op:
        batch_op.add_column(sa.Column("embedding_384", embedding_384_col_type, nullable=True))

    # Create HNSW index for 384-dimensional vector cosine distance on PostgreSQL
    if is_postgres and has_pgvector:
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_384_hnsw "
                "ON knowledge_chunks USING hnsw (embedding_384 vector_cosine_ops);"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_384_hnsw;"))

    with op.batch_alter_table("knowledge_chunks") as batch_op:
        batch_op.drop_column("embedding_384")
