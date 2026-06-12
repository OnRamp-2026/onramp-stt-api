import pytest

from app.db.models import ChunkStatus, JobStatus
from app.services.job_state import ensure_chunk_transition, ensure_job_transition


def test_job_status_allows_normal_pipeline_transition() -> None:
    ensure_job_transition(JobStatus.queued, JobStatus.preprocessing)
    ensure_job_transition(JobStatus.preprocessing, JobStatus.transcribing)
    ensure_job_transition(JobStatus.merging, JobStatus.transcript_completed)


def test_job_status_rejects_skipping_preprocessing() -> None:
    with pytest.raises(ValueError, match="queued -> transcribing"):
        ensure_job_transition(JobStatus.queued, JobStatus.transcribing)


def test_completed_chunk_cannot_be_reprocessed() -> None:
    with pytest.raises(ValueError, match="completed -> processing"):
        ensure_chunk_transition(ChunkStatus.completed, ChunkStatus.processing)
