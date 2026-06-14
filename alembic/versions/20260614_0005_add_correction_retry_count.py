"""add correction retry count

Revision ID: 20260614_0005
Revises: 20260612_0004
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260614_0005"
down_revision: str | Sequence[str] | None = "20260612_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transcription_jobs",
        sa.Column("correction_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("transcription_jobs", "correction_retry_count")
