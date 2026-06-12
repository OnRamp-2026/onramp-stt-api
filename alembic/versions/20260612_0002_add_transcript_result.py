"""add merged transcript result

Revision ID: 20260612_0002
Revises: 20260611_0001
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260612_0002"
down_revision: str | Sequence[str] | None = "20260611_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'transcript_completed' AFTER 'merging'")
    op.add_column("transcription_jobs", sa.Column("result_object_key", sa.Text(), nullable=True))
    op.add_column("transcription_jobs", sa.Column("merged_text", sa.Text(), nullable=True))
    op.add_column(
        "transcription_jobs",
        sa.Column("merged_segments_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transcription_jobs", "merged_segments_json")
    op.drop_column("transcription_jobs", "merged_text")
    op.drop_column("transcription_jobs", "result_object_key")
