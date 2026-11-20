"""Fix knowledge_documents updated_at column nullability and default.

Revision ID: 008_fix_knowledge_documents_updated_at
Revises: 007_rag_384_local_embeddings
Create Date: 2026-11-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_fix_knowledge_documents_updated_at"
down_revision: Union[str, None] = "007_rag_384_local_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Make updated_at nullable with server default now() / CURRENT_TIMESTAMP
    with op.batch_alter_table("knowledge_documents") as batch_op:
        if is_postgres:
            batch_op.alter_column(
                "updated_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            )
        else:
            batch_op.alter_column(
                "updated_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Backfill any null updated_at values before restoring NOT NULL
    if is_postgres:
        op.execute(sa.text("UPDATE knowledge_documents SET updated_at = now() WHERE updated_at IS NULL;"))
    else:
        op.execute(sa.text("UPDATE knowledge_documents SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL;"))

    with op.batch_alter_table("knowledge_documents") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
