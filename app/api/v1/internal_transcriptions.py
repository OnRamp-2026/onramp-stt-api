from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChunkStatus, JobStatus, TranscriptionChunk, TranscriptionJob
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


class TranscriptionResultResponse(BaseModel):
    schema_version: str = "1.0"
    transcription_id: UUID
    tenant_id: str
    provider: str
    audio_duration_sec: float | None
    text: str
    segments: list[TranscriptSegmentResponse]


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
        result_available=job.merged_text is not None,
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
    if job.status != JobStatus.transcript_completed or job.merged_text is None:
        raise HTTPException(status_code=409, detail="Transcription result is not ready.")
    return TranscriptionResultResponse(
        transcription_id=job.id,
        tenant_id=job.tenant_id,
        provider=job.provider,
        audio_duration_sec=job.audio_duration_sec,
        text=job.merged_text,
        segments=[TranscriptSegmentResponse.model_validate(segment) for segment in (job.merged_segments_json or [])],
    )
