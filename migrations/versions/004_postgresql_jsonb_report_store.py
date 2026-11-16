"""PostgreSQL JSONB Report Store migration: Create analysis_reports table.

Stores complete EdgeMind analysis report documents using PostgreSQL native JSONB
with GIN indexing, replacing MongoDB as the document store.

Revision ID: 004_postgresql_jsonb_report_store
Revises: 003_report_storage_status
Create Date: 2026-11-15 22:50:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_postgresql_jsonb_report_store"
down_revision: Union[str, None] = "003_report_storage_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Widen alembic_version.version_num column to 64 chars if needed to accommodate revision identifier
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);"))

    # 1. Create analysis_reports table
    op.create_table(
        "analysis_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("problem_id", sa.Uuid(), nullable=True),
        sa.Column("problem_slug", sa.String(length=255), nullable=True),
        sa.Column(
            "report_data",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=32), server_default="1.0.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_reports")),
        sa.ForeignKeyConstraint(
            ["analysis_session_id"],
            ["analysis_sessions.id"],
            name=op.f("fk_analysis_reports_analysis_session_id_analysis_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_analysis_reports_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_analysis_reports_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["problems.id"],
            name=op.f("fk_analysis_reports_problem_id_problems"),
            ondelete="SET NULL",
        ),
    )

    # 2. Indexes for relational lookups and pagination
    op.create_index(
        op.f("ix_analysis_reports_analysis_session_id"),
        "analysis_reports",
        ["analysis_session_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_analysis_reports_user_id"),
        "analysis_reports",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_reports_project_id"),
        "analysis_reports",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_reports_problem_id"),
        "analysis_reports",
        ["problem_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_reports_problem_slug"),
        "analysis_reports",
        ["problem_slug"],
        unique=False,
    )
    op.create_index(
        "ix_analysis_reports_user_id_created_at",
        "analysis_reports",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_reports_created_at"),
        "analysis_reports",
        ["created_at"],
        unique=False,
    )

    # 3. Native PostgreSQL GIN index on report_data for high-performance JSONB querying
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_analysis_reports_report_data_gin",
            "analysis_reports",
            ["report_data"],
            postgresql_using="gin",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "ix_analysis_reports_report_data_gin",
            table_name="analysis_reports",
            postgresql_using="gin",
        )

    op.drop_index(op.f("ix_analysis_reports_created_at"), table_name="analysis_reports")
    op.drop_index("ix_analysis_reports_user_id_created_at", table_name="analysis_reports")
    op.drop_index(op.f("ix_analysis_reports_problem_slug"), table_name="analysis_reports")
    op.drop_index(op.f("ix_analysis_reports_problem_id"), table_name="analysis_reports")
    op.drop_index(op.f("ix_analysis_reports_project_id"), table_name="analysis_reports")
    op.drop_index(op.f("ix_analysis_reports_user_id"), table_name="analysis_reports")
    op.drop_index(op.f("ix_analysis_reports_analysis_session_id"), table_name="analysis_reports")
    op.drop_table("analysis_reports")
