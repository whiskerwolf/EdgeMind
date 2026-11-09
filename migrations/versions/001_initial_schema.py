"""Initial migration: Create projects, problems, and analysis_sessions tables.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-09 13:25:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Projects Table
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("technology_stack", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_name"), "projects", ["name"], unique=False)
    op.create_index(op.f("ix_projects_status"), "projects", ["status"], unique=False)
    op.create_index(op.f("ix_projects_created_at"), "projects", ["created_at"], unique=False)

    # 2. Problems Table
    op.create_table(
        "problems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("problem_slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("difficulty", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problems")),
        sa.UniqueConstraint("platform", "problem_slug", name="uq_problems_platform_problem_slug"),
    )
    op.create_index(op.f("ix_problems_platform"), "problems", ["platform"], unique=False)
    op.create_index(op.f("ix_problems_problem_slug"), "problems", ["problem_slug"], unique=False)
    op.create_index(op.f("ix_problems_created_at"), "problems", ["created_at"], unique=False)

    # 3. Analysis Sessions Table
    op.create_table(
        "analysis_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("problem_id", sa.Uuid(), nullable=True),
        sa.Column("analysis_mode", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("analysis_status", sa.String(length=32), nullable=False),
        sa.Column("gaps_detected", sa.Integer(), nullable=False),
        sa.Column("candidates_generated", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name=op.f("fk_analysis_sessions_problem_id_problems"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_analysis_sessions_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_sessions")),
    )
    op.create_index(op.f("ix_analysis_sessions_created_at"), "analysis_sessions", ["created_at"], unique=False)
    op.create_index(op.f("ix_analysis_sessions_problem_id"), "analysis_sessions", ["problem_id"], unique=False)
    op.create_index(op.f("ix_analysis_sessions_project_id"), "analysis_sessions", ["project_id"], unique=False)
    op.create_index(op.f("ix_analysis_sessions_analysis_status"), "analysis_sessions", ["analysis_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_sessions_analysis_status"), table_name="analysis_sessions")
    op.drop_index(op.f("ix_analysis_sessions_project_id"), table_name="analysis_sessions")
    op.drop_index(op.f("ix_analysis_sessions_problem_id"), table_name="analysis_sessions")
    op.drop_index(op.f("ix_analysis_sessions_created_at"), table_name="analysis_sessions")
    op.drop_table("analysis_sessions")

    op.drop_index(op.f("ix_problems_created_at"), table_name="problems")
    op.drop_index(op.f("ix_problems_problem_slug"), table_name="problems")
    op.drop_index(op.f("ix_problems_platform"), table_name="problems")
    op.drop_table("problems")

    op.drop_index(op.f("ix_projects_created_at"), table_name="projects")
    op.drop_index(op.f("ix_projects_status"), table_name="projects")
    op.drop_index(op.f("ix_projects_name"), table_name="projects")
    op.drop_table("projects")

