"""add progress tracking columns

Revision ID: 20260612_0003
Revises: 20260612_0002
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260612_0003"
down_revision: str | Sequence[str] | None = "20260612_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transcription_jobs",
        sa.Column("last_progress_ratio", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "transcription_jobs",
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transcription_jobs", "last_progress_at")
    op.drop_column("transcription_jobs", "last_progress_ratio")
