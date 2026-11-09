"""Phase 4 migration: Add report_storage_status to analysis_sessions table.

Revision ID: 003_report_storage_status
Revises: 002_auth_and_ownership
Create Date: 2026-11-09 17:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_report_storage_status"
down_revision: Union[str, None] = "002_auth_and_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "report_storage_status",
                sa.String(length=32),
                server_default="NOT_CONFIGURED",
                nullable=False,
            )
        )
        batch_op.create_index(
            op.f("ix_analysis_sessions_report_storage_status"),
            ["report_storage_status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("analysis_sessions") as batch_op:
        batch_op.drop_index(op.f("ix_analysis_sessions_report_storage_status"))
        batch_op.drop_column("report_storage_status")
