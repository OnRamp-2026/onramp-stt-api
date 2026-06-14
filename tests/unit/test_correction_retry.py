from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.exceptions import StorageError
from app.db.base import Base
from app.db.models import EventInbox, EventOutbox, JobStatus, TranscriptionJob
from app.queue.constants import CORRECTION_WORKER_GROUP, STT_DLQ_STREAM, STT_PROGRESS_STREAM
from app.queue.events import StreamEnvelope
from app.services.correction_worker import CorrectionWorkerService


class FakeStorage:
    pass


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def create_job(session_factory: async_sessionmaker[AsyncSession]) -> TranscriptionJob:
    job = TranscriptionJob(
        id=uuid4(),
        tenant_id="tenant-a",
        status=JobStatus.correcting,
        source_object_key="source",
        source_filename="meeting.m4a",
        source_content_type="audio/mp4",
        source_size_bytes=1024,
        total_chunks=1,
        completed_chunks=1,
    )
    async with session_factory() as session:
        session.add(job)
        await session.commit()
    return job


def envelope_for(job: TranscriptionJob) -> StreamEnvelope:
    return StreamEnvelope(
        event_id="evt-correction",
        event_type="transcription.transcript.completed",
        payload={
            "transcription_id": str(job.id),
            "tenant_id": job.tenant_id,
            "result_object_key": "result/transcript.json",
        },
    )


@pytest.mark.asyncio
async def test_retryable_correction_error_remains_pending_before_limit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    job = await create_job(session_factory)
    service = CorrectionWorkerService(
        Settings(stt_max_retry_count=2),
        session_factory,
        FakeStorage(),  # type: ignore[arg-type]
    )

    should_ack = await service.record_failure(envelope_for(job), StorageError("storage unavailable"))

    async with session_factory() as session:
        persisted = await session.get(TranscriptionJob, job.id)
        outbox = list(await session.scalars(select(EventOutbox)))
        inbox = list(await session.scalars(select(EventInbox)))

    assert should_ack is False
    assert persisted is not None
    assert persisted.status == JobStatus.correcting
    assert persisted.correction_retry_count == 1
    assert outbox == []
    assert inbox == []


@pytest.mark.asyncio
async def test_retryable_correction_error_moves_to_dlq_after_limit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    job = await create_job(session_factory)
    service = CorrectionWorkerService(
        Settings(stt_max_retry_count=1),
        session_factory,
        FakeStorage(),  # type: ignore[arg-type]
    )
    envelope = envelope_for(job)

    assert await service.record_failure(envelope, StorageError("first failure")) is False
    should_ack = await service.record_failure(envelope, StorageError("second failure"))

    async with session_factory() as session:
        persisted = await session.get(TranscriptionJob, job.id)
        outbox = list(await session.scalars(select(EventOutbox)))
        inbox = await session.get(EventInbox, (CORRECTION_WORKER_GROUP, envelope.event_id))

    assert should_ack is True
    assert persisted is not None
    assert persisted.status == JobStatus.failed
    assert persisted.correction_retry_count == 2
    assert {event.stream_name for event in outbox} == {STT_PROGRESS_STREAM, STT_DLQ_STREAM}
    assert inbox is not None


@pytest.mark.asyncio
async def test_non_retryable_correction_error_fails_immediately(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    job = await create_job(session_factory)
    service = CorrectionWorkerService(
        Settings(stt_max_retry_count=3),
        session_factory,
        FakeStorage(),  # type: ignore[arg-type]
    )

    should_ack = await service.record_failure(envelope_for(job), ValueError("invalid dictionary schema"))

    async with session_factory() as session:
        persisted = await session.get(TranscriptionJob, job.id)

    assert should_ack is True
    assert persisted is not None
    assert persisted.status == JobStatus.failed
    assert persisted.correction_retry_count == 1
