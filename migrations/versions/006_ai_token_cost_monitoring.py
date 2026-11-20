"""AI Token Usage and API Cost Monitoring Migration.

Creates the ai_token_usages ledger table with tenant isolation,
user/project attribution, and SQLite/PostgreSQL compatibility.

Revision ID: 006_ai_token_cost_monitoring
Revises: 005_rag_vector_storage
Create Date: 2026-11-18 21:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006_ai_token_cost_monitoring"
down_revision: Union[str, None] = "005_rag_vector_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create ai_token_usages table
    op.create_table(
        "ai_token_usages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="openai"),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=20, scale=12), nullable=True),
        sa.Column("pricing_version", sa.String(length=32), nullable=True),
        sa.Column("usage_source", sa.String(length=32), nullable=False, server_default="ACTUAL_PROVIDER"),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["analysis_sessions.id"],
            name="fk_ai_token_usages_session_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_token_usages_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_ai_token_usages_project_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. Create performance & tenant-isolation indexes
    op.create_index("ix_ai_token_usages_session_id", "ai_token_usages", ["session_id"], unique=False)
    op.create_index("ix_ai_token_usages_user_id", "ai_token_usages", ["user_id"], unique=False)
    op.create_index("ix_ai_token_usages_project_id", "ai_token_usages", ["project_id"], unique=False)
    op.create_index("ix_ai_token_usages_model", "ai_token_usages", ["model"], unique=False)
    op.create_index("ix_ai_token_usages_usage_source", "ai_token_usages", ["usage_source"], unique=False)
    op.create_index(
        "ix_ai_token_usages_user_created",
        "ai_token_usages",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_token_usages_project_created",
        "ai_token_usages",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_ai_token_usages_provider_request_id",
        "ai_token_usages",
        ["provider", "request_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_ai_token_usages_provider_request_id", table_name="ai_token_usages")
    op.drop_index("ix_ai_token_usages_project_created", table_name="ai_token_usages")
    op.drop_index("ix_ai_token_usages_user_created", table_name="ai_token_usages")
    op.drop_index("ix_ai_token_usages_usage_source", table_name="ai_token_usages")
    op.drop_index("ix_ai_token_usages_model", table_name="ai_token_usages")
    op.drop_index("ix_ai_token_usages_project_id", table_name="ai_token_usages")
    op.drop_index("ix_ai_token_usages_user_id", table_name="ai_token_usages")
    op.drop_index("ix_ai_token_usages_session_id", table_name="ai_token_usages")
    op.drop_table("ai_token_usages")
