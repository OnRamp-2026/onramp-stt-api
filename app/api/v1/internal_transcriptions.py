from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ChunkStatus,
    CorrectedTranscript,
    JobStatus,
    SttCorrectionLog,
    TranscriptionChunk,
    TranscriptionJob,
)
from app.db.postgres import session_scope

router = APIRouter(prefix="/internal/transcriptions", tags=["internal-transcriptions"])
SessionDependency = Annotated[AsyncSession, Depends(session_scope)]


class ChunkStatusResponse(BaseModel):
    chunk_index: int
    status: ChunkStatus
    retry_count: int
    recognized_text: str | None
    error_code: str | None


class TranscriptionStatusResponse(BaseModel):
    transcription_id: UUID
    tenant_id: str
    status: JobStatus
    provider: str
    total_chunks: int
    completed_chunks: int
    failed_chunks: int
    audio_duration_sec: float | None
    result_available: bool
    chunks: list[ChunkStatusResponse]


class TranscriptSegmentResponse(BaseModel):
    start_time_sec: float
    end_time_sec: float
    text: str
    speaker: str | None = None
    confidence: float | None = None


class TranscriptBodyResponse(BaseModel):
    text_sha256: str
    text: str
    segments: list[TranscriptSegmentResponse]


class CorrectedTranscriptBodyResponse(TranscriptBodyResponse):
    correction_count: int
    review_candidate_count: int


class TranscriptionResultResponse(BaseModel):
    schema_version: str = "1.0"
    transcription_id: UUID
    tenant_id: str
    provider: str
    audio_duration_sec: float | None
    dictionary_version: str
    raw: TranscriptBodyResponse
    corrected: CorrectedTranscriptBodyResponse


@router.get("/{transcription_id}", response_model=TranscriptionStatusResponse)
async def get_transcription_status(
    transcription_id: UUID,
    session: SessionDependency,
) -> TranscriptionStatusResponse:
    job = await session.get(TranscriptionJob, transcription_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Transcription not found.")
    chunks = list(
        await session.scalars(
            select(TranscriptionChunk)
            .where(TranscriptionChunk.transcription_id == transcription_id)
            .order_by(TranscriptionChunk.chunk_index)
        )
    )
    return TranscriptionStatusResponse(
        transcription_id=job.id,
        tenant_id=job.tenant_id,
        status=job.status,
        provider=job.provider,
        total_chunks=job.total_chunks,
        completed_chunks=job.completed_chunks,
        failed_chunks=job.failed_chunks,
        audio_duration_sec=job.audio_duration_sec,
        result_available=job.status == JobStatus.correction_completed,
        chunks=[
            ChunkStatusResponse(
                chunk_index=chunk.chunk_index,
                status=chunk.status,
                retry_count=chunk.retry_count,
                recognized_text=chunk.recognized_text,
                error_code=chunk.error_code,
            )
            for chunk in chunks
        ],
    )


@router.get("/{transcription_id}/result", response_model=TranscriptionResultResponse)
async def get_transcription_result(
    transcription_id: UUID,
    session: SessionDependency,
) -> TranscriptionResultResponse:
    job = await session.get(TranscriptionJob, transcription_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Transcription not found.")
    corrected = await session.scalar(
        select(CorrectedTranscript)
        .where(CorrectedTranscript.transcription_id == transcription_id)
        .order_by(CorrectedTranscript.created_at.desc())
    )
    correction_count = (
        await session.scalar(
            select(func.count(SttCorrectionLog.id)).where(SttCorrectionLog.corrected_transcript_id == corrected.id)
        )
        if corrected is not None
        else 0
    )
    if job.status != JobStatus.correction_completed or job.merged_text is None or corrected is None:
        raise HTTPException(status_code=409, detail="Transcription result is not ready.")
    return TranscriptionResultResponse(
        transcription_id=job.id,
        tenant_id=job.tenant_id,
        provider=job.provider,
        audio_duration_sec=job.audio_duration_sec,
        dictionary_version=corrected.dictionary_version,
        raw=TranscriptBodyResponse(
            text_sha256=_sha256(job.merged_text),
            text=job.merged_text,
            segments=[TranscriptSegmentResponse.model_validate(segment) for segment in (job.merged_segments_json or [])],
        ),
        corrected=CorrectedTranscriptBodyResponse(
            text_sha256=corrected.corrected_text_sha256,
            text=corrected.corrected_text,
            segments=[TranscriptSegmentResponse.model_validate(segment) for segment in corrected.corrected_segments_json],
            correction_count=int(correction_count or 0),
            review_candidate_count=len(corrected.review_candidates_json or []),
        ),
    )


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
