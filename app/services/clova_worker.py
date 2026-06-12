from __future__ import annotations

import json
import random
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.db.models import (
    ChunkStatus,
    EventOutbox,
    JobStatus,
    TranscriptionChunk,
    TranscriptionJob,
    utcnow,
)
from app.queue.constants import CLOVA_WORKER_GROUP, STT_CHUNK_STREAM, STT_DLQ_STREAM
from app.queue.events import ChunkRequested, StreamEnvelope
from app.queue.inbox import is_processed, mark_processed
from app.storage.base import ObjectStorage
from app.stt.merger import merge_chunk_segments, render_plain_text
from app.stt.providers.base import ProviderResult, STTProvider

logger = structlog.get_logger(__name__)


class ClovaChunkService:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        provider: STTProvider,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.storage = storage
        self.provider = provider

    async def process(self, envelope: StreamEnvelope, worker_id: str) -> None:
        request = ChunkRequested.model_validate(envelope.payload)
        chunk = await self._claim(request, envelope.event_id, worker_id)
        if chunk is None:
            return

        with tempfile.TemporaryDirectory(prefix=f"onramp-clova-{request.transcription_id}-") as temp_dir:
            audio_path = Path(temp_dir) / f"chunk_{request.chunk_index:04d}.wav"
            try:
                await self.storage.download(request.chunk_object_key, audio_path)
                result = await self.provider.transcribe(audio_path)
                raw_path = Path(temp_dir) / "raw.json"
                raw_path.write_text(
                    json.dumps(result.raw_response, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
                raw_key = (
                    f"tenants/{request.tenant_id}/transcriptions/{request.transcription_id}"
                    f"/provider-raw/{request.chunk_index:04d}.json"
                )
                await self.storage.upload(raw_path, raw_key, content_type="application/json")
            except ProviderError as exc:
                await self._record_failure(request, envelope, exc)
                return
            except Exception as exc:
                await self._record_failure(
                    request,
                    envelope,
                    ProviderError(
                        f"Chunk processing failed before provider completion: {type(exc).__name__}",
                        retryable=True,
                    ),
                )
                return

            await self._record_success(request, envelope.event_id, raw_key, result)

    async def _claim(
        self,
        request: ChunkRequested,
        event_id: str,
        worker_id: str,
    ) -> TranscriptionChunk | None:
        claimed_at = utcnow()
        async with self.session_factory() as session, session.begin():
            if await is_processed(session, CLOVA_WORKER_GROUP, event_id):
                return None
            chunk = await session.scalar(
                select(TranscriptionChunk)
                .where(
                    TranscriptionChunk.transcription_id == request.transcription_id,
                    TranscriptionChunk.chunk_index == request.chunk_index,
                )
                .with_for_update()
            )
            if chunk is None:
                raise ValueError("Chunk event does not match a stored chunk.")
            if chunk.chunk_object_key != request.chunk_object_key:
                raise ValueError("Chunk event object key mismatch.")
            if chunk.status == ChunkStatus.completed:
                mark_processed(session, CLOVA_WORKER_GROUP, event_id, str(chunk.id))
                return None
            if not can_claim_chunk(chunk.status, chunk.lease_expires_at, claimed_at):
                raise ValueError(f"Chunk cannot be claimed from status {chunk.status.value}.")
            chunk.status = ChunkStatus.processing
            chunk.error_code = None
            chunk.error_message = None
            chunk.lease_owner = worker_id
            chunk.lease_expires_at = claimed_at + timedelta(seconds=self.settings.clova_chunk_lease_sec)
            return chunk

    async def _record_success(
        self,
        request: ChunkRequested,
        event_id: str,
        raw_key: str,
        result: ProviderResult,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            chunk = await session.scalar(
                select(TranscriptionChunk)
                .where(
                    TranscriptionChunk.transcription_id == request.transcription_id,
                    TranscriptionChunk.chunk_index == request.chunk_index,
                )
                .with_for_update()
            )
            job = await session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == request.transcription_id).with_for_update()
            )
            if chunk is None or job is None:
                raise RuntimeError("STT chunk or job disappeared while saving the provider result.")
            if chunk.status == ChunkStatus.completed:
                mark_processed(session, CLOVA_WORKER_GROUP, event_id, str(chunk.id))
                return

            chunk.status = ChunkStatus.completed
            chunk.provider_job_id = result.provider_job_id
            chunk.raw_response_object_key = raw_key
            chunk.recognized_text = result.full_text
            chunk.normalized_segments_json = [asdict(segment) for segment in result.segments]
            chunk.next_retry_at = None
            chunk.lease_owner = None
            chunk.lease_expires_at = None
            job.completed_chunks += 1
            if job.completed_chunks == job.total_chunks:
                job.status = JobStatus.merging
                await session.flush()
                await self._merge_transcription(session, job)
            mark_processed(session, CLOVA_WORKER_GROUP, event_id, str(chunk.id))

        await logger.ainfo(
            "clova_chunk_completed",
            transcription_id=str(request.transcription_id),
            chunk_index=request.chunk_index,
        )

    async def _record_failure(
        self,
        request: ChunkRequested,
        envelope: StreamEnvelope,
        error: ProviderError,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            chunk = await session.scalar(
                select(TranscriptionChunk)
                .where(
                    TranscriptionChunk.transcription_id == request.transcription_id,
                    TranscriptionChunk.chunk_index == request.chunk_index,
                )
                .with_for_update()
            )
            job = await session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == request.transcription_id).with_for_update()
            )
            if chunk is None or job is None:
                raise RuntimeError("STT chunk or job disappeared while recording an error.")

            chunk.retry_count += 1
            chunk.error_code = error.code
            chunk.error_message = str(error)[:2000]
            chunk.lease_owner = None
            chunk.lease_expires_at = None
            can_retry = error.retryable and chunk.retry_count <= self.settings.clova_max_retry_count
            if can_retry:
                delay = min(
                    self.settings.clova_backoff_max_sec,
                    self.settings.clova_backoff_base_sec * (2 ** (chunk.retry_count - 1)),
                )
                delay += random.uniform(0, min(1.0, delay * 0.1))
                available_at = utcnow() + timedelta(seconds=delay)
                chunk.status = ChunkStatus.retry_wait
                chunk.next_retry_at = available_at
                session.add(
                    EventOutbox(
                        id=f"evt_{uuid.uuid4().hex}",
                        aggregate_type="transcription_chunk",
                        aggregate_id=f"{request.transcription_id}:{request.chunk_index}",
                        event_type="transcription.chunk.requested",
                        stream_name=STT_CHUNK_STREAM,
                        payload_json=request.model_dump(mode="json"),
                        available_at=available_at,
                    )
                )
            else:
                chunk.status = ChunkStatus.failed
                job.failed_chunks += 1
                job.status = JobStatus.failed
                job.error_code = error.code
                job.error_message = f"Chunk {request.chunk_index}: {error}"[:2000]
                session.add(
                    EventOutbox(
                        id=f"evt_{uuid.uuid4().hex}",
                        aggregate_type="transcription_chunk",
                        aggregate_id=f"{request.transcription_id}:{request.chunk_index}",
                        event_type="transcription.chunk.failed",
                        stream_name=STT_DLQ_STREAM,
                        payload_json={
                            **request.model_dump(mode="json"),
                            "retry_count": chunk.retry_count,
                            "error_code": error.code,
                        },
                    )
                )
            mark_processed(session, CLOVA_WORKER_GROUP, envelope.event_id, str(chunk.id))

    async def _merge_transcription(
        self,
        session: AsyncSession,
        job: TranscriptionJob,
    ) -> None:
        chunks = list(
            await session.scalars(
                select(TranscriptionChunk)
                .where(TranscriptionChunk.transcription_id == job.id)
                .order_by(TranscriptionChunk.chunk_index)
            )
        )
        if len(chunks) != job.total_chunks or any(chunk.status != ChunkStatus.completed for chunk in chunks):
            raise RuntimeError("Cannot merge a transcription with incomplete chunks.")

        merged_segments = merge_chunk_segments(
            [
                (
                    chunk.source_mapping_json,
                    chunk.normalized_segments_json or [],
                )
                for chunk in chunks
            ]
        )
        merged_text = render_plain_text(merged_segments)
        segment_payload = [asdict(segment) for segment in merged_segments]
        payload = {
            "schema_version": "1.0",
            "transcription_id": str(job.id),
            "tenant_id": job.tenant_id,
            "provider": job.provider,
            "audio_duration_sec": job.audio_duration_sec,
            "text": merged_text,
            "segments": segment_payload,
        }
        result_key = f"tenants/{job.tenant_id}/transcriptions/{job.id}/result/transcript.json"
        with tempfile.TemporaryDirectory(prefix=f"onramp-merge-{job.id}-") as temp_dir:
            result_path = Path(temp_dir) / "transcript.json"
            result_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            await self.storage.upload(result_path, result_key, content_type="application/json")

        job.result_object_key = result_key
        job.merged_text = merged_text
        job.merged_segments_json = segment_payload
        job.status = JobStatus.transcript_completed
        job.completed_at = utcnow()


def can_claim_chunk(
    status: ChunkStatus,
    lease_expires_at: datetime | None,
    claimed_at: datetime,
) -> bool:
    if status in {ChunkStatus.pending, ChunkStatus.retry_wait}:
        return True
    return status == ChunkStatus.processing and (lease_expires_at is None or lease_expires_at <= claimed_at)
