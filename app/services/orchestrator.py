from __future__ import annotations

import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import EventOutbox, JobStatus, TranscriptionChunk, TranscriptionJob, utcnow
from app.queue.constants import ORCHESTRATOR_GROUP, STT_CHUNK_STREAM
from app.queue.events import ChunkRequested, StreamEnvelope, TranscriptionRequested
from app.queue.inbox import is_processed, mark_processed
from app.storage.base import ObjectStorage
from app.stt.audio_converter import AudioConverter
from app.stt.vad import VadChunk, VadChunker

logger = structlog.get_logger(__name__)


class OrchestratorService:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.storage = storage
        self.converter = AudioConverter(settings)
        self.vad = VadChunker(settings)

    async def process(self, envelope: StreamEnvelope) -> None:
        request = TranscriptionRequested.model_validate(envelope.payload)
        if await self._already_processed(envelope.event_id):
            return

        await self._ensure_job(request)
        try:
            await self._preprocess(request, envelope.event_id)
        except Exception as exc:
            await self._mark_failed(request.transcription_id, exc)
            raise

    async def _already_processed(self, event_id: str) -> bool:
        async with self.session_factory() as session:
            return await is_processed(session, ORCHESTRATOR_GROUP, event_id)

    async def _ensure_job(self, request: TranscriptionRequested) -> None:
        async with self.session_factory() as session, session.begin():
            existing = await session.get(TranscriptionJob, request.transcription_id)
            if existing is not None:
                if existing.tenant_id != request.tenant_id or existing.source_object_key != request.source_object_key:
                    raise ValueError("Transcription event does not match the existing job.")
                return
            session.add(
                TranscriptionJob(
                    id=request.transcription_id,
                    tenant_id=request.tenant_id,
                    status=JobStatus.preprocessing,
                    source_object_key=request.source_object_key,
                    source_filename=request.source_filename or Path(request.source_object_key).name,
                    source_content_type=request.source_content_type,
                    source_size_bytes=request.source_size_bytes,
                    started_at=utcnow(),
                )
            )

    async def _preprocess(self, request: TranscriptionRequested, event_id: str) -> None:
        with tempfile.TemporaryDirectory(prefix=f"onramp-stt-{request.transcription_id}-") as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / (request.source_filename or Path(request.source_object_key).name)
            normalized = workspace / "source.wav"
            chunk_dir = workspace / "chunks"

            await self.storage.download(request.source_object_key, source)
            metadata = await self.converter.probe(source)
            await self.converter.convert_to_pcm_wav(source, normalized)
            chunks = self.vad.split(normalized, chunk_dir)

            prefix = f"tenants/{request.tenant_id}/transcriptions/{request.transcription_id}"
            normalized_key = f"{prefix}/normalized/source.wav"
            await self.storage.upload(normalized, normalized_key, content_type="audio/wav")

            uploaded_chunks: list[tuple[VadChunk, str]] = []
            for chunk in chunks:
                chunk_key = f"{prefix}/chunks/{chunk.index:04d}.wav"
                await self.storage.upload(chunk.path, chunk_key, content_type="audio/wav")
                uploaded_chunks.append((chunk, chunk_key))

        async with self.session_factory() as session, session.begin():
            job = await session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == request.transcription_id).with_for_update()
            )
            if job is None:
                raise RuntimeError("Transcription job disappeared during preprocessing.")
            if await is_processed(session, ORCHESTRATOR_GROUP, event_id):
                return
            if job.total_chunks:
                mark_processed(session, ORCHESTRATOR_GROUP, event_id, str(job.id))
                return

            job.status = JobStatus.transcribing
            job.normalized_object_key = normalized_key
            job.audio_duration_sec = metadata.duration_sec
            job.source_size_bytes = metadata.size_bytes
            job.total_chunks = len(uploaded_chunks)

            for chunk, chunk_key in uploaded_chunks:
                chunk_row = TranscriptionChunk(
                    transcription_id=job.id,
                    chunk_index=chunk.index,
                    chunk_object_key=chunk_key,
                    chunk_duration_sec=chunk.duration_sec,
                    source_mapping_json=[asdict(mapping) for mapping in chunk.source_mappings],
                )
                session.add(chunk_row)
                payload = ChunkRequested(
                    transcription_id=job.id,
                    tenant_id=job.tenant_id,
                    chunk_index=chunk.index,
                    chunk_object_key=chunk_key,
                )
                session.add(
                    EventOutbox(
                        id=f"evt_{uuid.uuid4().hex}",
                        aggregate_type="transcription_chunk",
                        aggregate_id=f"{job.id}:{chunk.index}",
                        event_type="transcription.chunk.requested",
                        stream_name=STT_CHUNK_STREAM,
                        payload_json=payload.model_dump(mode="json"),
                    )
                )
            mark_processed(session, ORCHESTRATOR_GROUP, event_id, str(job.id))

        await logger.ainfo(
            "transcription_preprocessed",
            transcription_id=str(request.transcription_id),
            total_chunks=len(uploaded_chunks),
        )

    async def _mark_failed(self, transcription_id: uuid.UUID, exc: Exception) -> None:
        async with self.session_factory() as session, session.begin():
            job = await session.get(TranscriptionJob, transcription_id)
            if job is None:
                return
            job.status = JobStatus.failed
            job.error_code = getattr(exc, "code", type(exc).__name__)
            job.error_message = str(exc)[:2000]
