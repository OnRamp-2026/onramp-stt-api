from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.correction.service import (
    CorrectionService,
    serialize_corrected_segments,
    serialize_correction_logs,
    serialize_review_candidates,
)
from app.db.models import CorrectedTranscript, EventOutbox, JobStatus, SttCorrectionLog, TranscriptionJob, utcnow
from app.queue.constants import COMPLETED_EVENT_TYPE, CORRECTION_WORKER_GROUP, STT_COMPLETED_STREAM
from app.queue.events import StreamEnvelope, TranscriptCompleted, TranscriptionCompleted
from app.queue.inbox import is_processed, mark_processed
from app.services.job_state import ensure_job_transition
from app.storage.base import ObjectStorage

logger = structlog.get_logger(__name__)


class CorrectionWorkerService:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        *,
        correction_service: CorrectionService | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.storage = storage
        self.correction_service = correction_service or CorrectionService(settings)

    async def process(self, envelope: StreamEnvelope) -> None:
        payload = TranscriptCompleted.model_validate(envelope.payload)
        if await self._already_processed(envelope.event_id):
            return

        async with self.session_factory() as session, session.begin():
            job = await session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == payload.transcription_id).with_for_update()
            )
            if job is None:
                raise ValueError("Transcription job not found for correction.")
            if job.status == JobStatus.correction_completed:
                mark_processed(session, CORRECTION_WORKER_GROUP, envelope.event_id, str(job.id))
                return
            if job.status == JobStatus.transcript_completed:
                ensure_job_transition(job.status, JobStatus.correcting)
                job.status = JobStatus.correcting

        result = await self._build_result(payload.transcription_id)
        corrected_object_key = result_object_key(payload.tenant_id, payload.transcription_id)
        await self._upload_corrected_result(payload, result, corrected_object_key)

        async with self.session_factory() as session, session.begin():
            if await is_processed(session, CORRECTION_WORKER_GROUP, envelope.event_id):
                return
            job = await session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == payload.transcription_id).with_for_update()
            )
            if job is None:
                raise RuntimeError("Transcription job disappeared before correction save.")

            existing = await session.scalar(
                select(CorrectedTranscript).where(
                    CorrectedTranscript.transcription_id == payload.transcription_id,
                    CorrectedTranscript.dictionary_version == result.dictionary_version,
                )
            )
            corrected_transcript = existing
            if corrected_transcript is None:
                corrected_transcript = CorrectedTranscript(
                    tenant_id=job.tenant_id,
                    transcription_id=job.id,
                    raw_text_sha256=result.raw_text_sha256,
                    corrected_text=result.corrected_text,
                    corrected_segments_json=serialize_corrected_segments(result.corrected_segments),
                    corrected_text_sha256=result.corrected_text_sha256,
                    dictionary_version=result.dictionary_version,
                    result_object_key=corrected_object_key,
                    review_candidates_json=serialize_review_candidates(result.review_candidates),
                    prompt_version=result.prompt_version,
                    llm_applied=result.llm_applied,
                )
                session.add(corrected_transcript)
                await session.flush()
                for log in result.correction_logs:
                    session.add(
                        SttCorrectionLog(
                            corrected_transcript_id=corrected_transcript.id,
                            segment_index=log.segment_index,
                            start_time_sec=log.start_time_sec,
                            end_time_sec=log.end_time_sec,
                            term_id=log.term_id,
                            replace_policy=log.replace_policy,
                            original_text=log.original_text,
                            corrected_text=log.corrected_text,
                            context_evidence=log.context_evidence,
                            decision=log.decision,
                        )
                    )

            if job.status != JobStatus.correction_completed:
                if job.status != JobStatus.correcting:
                    ensure_job_transition(job.status, JobStatus.correcting)
                    job.status = JobStatus.correcting
                ensure_job_transition(job.status, JobStatus.correction_completed)
                job.status = JobStatus.correction_completed
            job.completed_at = utcnow()

            session.add(
                EventOutbox(
                    id=f"evt_{uuid.uuid4().hex}",
                    aggregate_type="transcription",
                    aggregate_id=str(job.id),
                    event_type=COMPLETED_EVENT_TYPE,
                    stream_name=STT_COMPLETED_STREAM,
                    payload_json=TranscriptionCompleted(
                        transcription_id=job.id,
                        tenant_id=job.tenant_id,
                        raw_text_sha256=result.raw_text_sha256,
                        corrected_text_sha256=result.corrected_text_sha256,
                        dictionary_version=result.dictionary_version,
                        result_object_key=corrected_transcript.result_object_key or corrected_object_key,
                        completed_at=job.completed_at,
                    ).model_dump(mode="json"),
                )
            )
            mark_processed(session, CORRECTION_WORKER_GROUP, envelope.event_id, str(corrected_transcript.id))
        await logger.ainfo(
            "transcription_correction_completed",
            transcription_id=str(payload.transcription_id),
            dictionary_version=result.dictionary_version,
        )

    async def _already_processed(self, event_id: str) -> bool:
        async with self.session_factory() as session:
            return await is_processed(session, CORRECTION_WORKER_GROUP, event_id)

    async def _build_result(self, transcription_id: uuid.UUID):
        async with self.session_factory() as session:
            job = await session.get(TranscriptionJob, transcription_id)
            if job is None or job.merged_text is None or not job.merged_segments_json:
                raise RuntimeError("Merged transcript is not ready for correction.")
            return self.correction_service.correct(job.merged_text, job.merged_segments_json)

    async def _upload_corrected_result(self, payload: TranscriptCompleted, result, object_key: str) -> None:
        body = {
            "schema_version": "1.0",
            "transcription_id": str(payload.transcription_id),
            "tenant_id": payload.tenant_id,
            "dictionary_version": result.dictionary_version,
            "raw_text_sha256": result.raw_text_sha256,
            "corrected_text_sha256": result.corrected_text_sha256,
            "corrected_text": result.corrected_text,
            "corrected_segments": serialize_corrected_segments(result.corrected_segments),
            "correction_logs": serialize_correction_logs(result.correction_logs),
            "review_candidates": serialize_review_candidates(result.review_candidates),
            "prompt_version": result.prompt_version,
            "llm_applied": result.llm_applied,
        }
        with tempfile.TemporaryDirectory(prefix=f"onramp-correction-{payload.transcription_id}-") as temp_dir:
            path = Path(temp_dir) / "corrected-transcript.json"
            path.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            await self.storage.upload(path, object_key, content_type="application/json")


def result_object_key(tenant_id: str, transcription_id: uuid.UUID) -> str:
    return f"tenants/{tenant_id}/transcriptions/{transcription_id}/result/corrected-transcript.json"
