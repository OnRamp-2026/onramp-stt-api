"""add correction result tables

Revision ID: 20260612_0004
Revises: 20260612_0003
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260612_0004"
down_revision: str | Sequence[str] | None = "20260612_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corrected_transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("transcription_id", sa.Uuid(), nullable=False),
        sa.Column("raw_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=False),
        sa.Column("corrected_segments_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("corrected_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("dictionary_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_object_key", sa.Text(), nullable=True),
        sa.Column("review_candidates_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("llm_applied", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transcription_id"], ["transcription_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "transcription_id", "dictionary_version", name="uq_corrected_transcript_version"),
    )
    op.create_index("ix_corrected_transcripts_tenant_id", "corrected_transcripts", ["tenant_id"])
    op.create_index("ix_corrected_transcripts_transcription_id", "corrected_transcripts", ["transcription_id"])
    op.create_index("ix_corrected_transcripts_dictionary_version", "corrected_transcripts", ["dictionary_version"])

    op.create_table(
        "stt_correction_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corrected_transcript_id", sa.Uuid(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_time_sec", sa.Float(), nullable=False),
        sa.Column("end_time_sec", sa.Float(), nullable=False),
        sa.Column("term_id", sa.String(length=64), nullable=False),
        sa.Column("replace_policy", sa.String(length=32), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=False),
        sa.Column("context_evidence", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["corrected_transcript_id"], ["corrected_transcripts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stt_correction_logs_corrected_transcript_id", "stt_correction_logs", ["corrected_transcript_id"])


def downgrade() -> None:
    op.drop_index("ix_stt_correction_logs_corrected_transcript_id", table_name="stt_correction_logs")
    op.drop_table("stt_correction_logs")
    op.drop_index("ix_corrected_transcripts_dictionary_version", table_name="corrected_transcripts")
    op.drop_index("ix_corrected_transcripts_transcription_id", table_name="corrected_transcripts")
    op.drop_index("ix_corrected_transcripts_tenant_id", table_name="corrected_transcripts")
    op.drop_table("corrected_transcripts")
