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
    chunks: list[ChunkStatusResponse]


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
