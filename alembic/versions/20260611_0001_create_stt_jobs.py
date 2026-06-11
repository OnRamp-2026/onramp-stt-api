"""create STT job tables

Revision ID: 20260611_0001
Revises:
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260611_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

job_status = sa.Enum(
    "queued",
    "preprocessing",
    "transcribing",
    "merging",
    "correcting",
    "correction_completed",
    "failed",
    "cancelled",
    name="job_status",
)
chunk_status = sa.Enum(
    "pending",
    "processing",
    "retry_wait",
    "completed",
    "failed",
    "cancelled",
    name="chunk_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    job_status.create(bind, checkfirst=True)
    chunk_status.create(bind, checkfirst=True)

    op.create_table(
        "transcription_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("source_object_key", sa.Text(), nullable=False),
        sa.Column("normalized_object_key", sa.Text(), nullable=True),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("source_content_type", sa.String(length=128), nullable=False),
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("audio_duration_sec", sa.Float(), nullable=True),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("completed_chunks", sa.Integer(), nullable=False),
        sa.Column("failed_chunks", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_transcription_job_tenant_id"),
    )
    op.create_index("ix_transcription_jobs_tenant_id", "transcription_jobs", ["tenant_id"])

    op.create_table(
        "transcription_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transcription_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("status", chunk_status, nullable=False),
        sa.Column("chunk_object_key", sa.Text(), nullable=False),
        sa.Column("chunk_duration_sec", sa.Float(), nullable=False),
        sa.Column("source_mapping_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_job_id", sa.String(length=256), nullable=True),
        sa.Column("raw_response_object_key", sa.Text(), nullable=True),
        sa.Column("recognized_text", sa.Text(), nullable=True),
        sa.Column("normalized_segments_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(length=256), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transcription_id"], ["transcription_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transcription_id", "chunk_index", name="uq_transcription_chunk_index"),
    )
    op.create_index("ix_transcription_chunks_transcription_id", "transcription_chunks", ["transcription_id"])
    op.create_index("ix_transcription_chunks_retry", "transcription_chunks", ["status", "next_retry_at"])

    op.create_table(
        "event_outbox",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("stream_name", sa.String(length=128), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publish_attempts", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_outbox_aggregate_id", "event_outbox", ["aggregate_id"])
    op.create_index("ix_event_outbox_available_at", "event_outbox", ["available_at"])

    op.create_table(
        "event_inbox",
        sa.Column("consumer_group", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_reference", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("consumer_group", "event_id"),
    )


def downgrade() -> None:
    op.drop_table("event_inbox")
    op.drop_index("ix_event_outbox_available_at", table_name="event_outbox")
    op.drop_index("ix_event_outbox_aggregate_id", table_name="event_outbox")
    op.drop_table("event_outbox")
    op.drop_index("ix_transcription_chunks_retry", table_name="transcription_chunks")
    op.drop_index("ix_transcription_chunks_transcription_id", table_name="transcription_chunks")
    op.drop_table("transcription_chunks")
    op.drop_index("ix_transcription_jobs_tenant_id", table_name="transcription_jobs")
    op.drop_table("transcription_jobs")
    chunk_status.drop(op.get_bind(), checkfirst=True)
    job_status.drop(op.get_bind(), checkfirst=True)
