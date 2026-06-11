from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class JobStatus(StrEnum):
    queued = "queued"
    preprocessing = "preprocessing"
    transcribing = "transcribing"
    merging = "merging"
    correcting = "correcting"
    correction_completed = "correction_completed"
    failed = "failed"
    cancelled = "cancelled"


class ChunkStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    retry_wait = "retry_wait"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), default=JobStatus.queued)
    provider: Mapped[str] = mapped_column(String(32), default="clova")
    source_object_key: Mapped[str] = mapped_column(Text)
    normalized_object_key: Mapped[str | None] = mapped_column(Text)
    source_filename: Mapped[str] = mapped_column(String(512))
    source_content_type: Mapped[str] = mapped_column(String(128))
    source_size_bytes: Mapped[int] = mapped_column(BigInteger)
    audio_duration_sec: Mapped[float | None] = mapped_column(Float)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    completed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    failed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    chunks: Mapped[list[TranscriptionChunk]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )

    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_transcription_job_tenant_id"),)


class TranscriptionChunk(Base):
    __tablename__ = "transcription_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transcription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcription_jobs.id", ondelete="CASCADE"),
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[ChunkStatus] = mapped_column(Enum(ChunkStatus, name="chunk_status"), default=ChunkStatus.pending)
    chunk_object_key: Mapped[str] = mapped_column(Text)
    chunk_duration_sec: Mapped[float] = mapped_column(Float)
    source_mapping_json: Mapped[list[dict[str, float]]] = mapped_column(JSON)
    provider_job_id: Mapped[str | None] = mapped_column(String(256))
    raw_response_object_key: Mapped[str | None] = mapped_column(Text)
    recognized_text: Mapped[str | None] = mapped_column(Text)
    normalized_segments_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    lease_owner: Mapped[str | None] = mapped_column(String(256))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    job: Mapped[TranscriptionJob] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("transcription_id", "chunk_index", name="uq_transcription_chunk_index"),
        Index("ix_transcription_chunks_retry", "status", "next_retry_at"),
    )


class EventOutbox(Base):
    __tablename__ = "event_outbox"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    stream_name: Mapped[str] = mapped_column(String(128))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventInbox(Base):
    __tablename__ = "event_inbox"

    consumer_group: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    result_reference: Mapped[str | None] = mapped_column(Text)
