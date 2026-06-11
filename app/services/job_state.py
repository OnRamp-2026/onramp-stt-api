from app.db.models import ChunkStatus, JobStatus

JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.queued: {JobStatus.preprocessing, JobStatus.cancelled, JobStatus.failed},
    JobStatus.preprocessing: {JobStatus.transcribing, JobStatus.cancelled, JobStatus.failed},
    JobStatus.transcribing: {JobStatus.merging, JobStatus.cancelled, JobStatus.failed},
    JobStatus.merging: {JobStatus.correcting, JobStatus.failed},
    JobStatus.correcting: {JobStatus.correction_completed, JobStatus.failed},
    JobStatus.correction_completed: set(),
    JobStatus.failed: {JobStatus.queued},
    JobStatus.cancelled: set(),
}

CHUNK_TRANSITIONS: dict[ChunkStatus, set[ChunkStatus]] = {
    ChunkStatus.pending: {ChunkStatus.processing, ChunkStatus.cancelled},
    ChunkStatus.processing: {
        ChunkStatus.completed,
        ChunkStatus.retry_wait,
        ChunkStatus.failed,
        ChunkStatus.cancelled,
    },
    ChunkStatus.retry_wait: {ChunkStatus.pending, ChunkStatus.cancelled, ChunkStatus.failed},
    ChunkStatus.completed: set(),
    ChunkStatus.failed: {ChunkStatus.pending},
    ChunkStatus.cancelled: set(),
}


def ensure_job_transition(current: JobStatus, target: JobStatus) -> None:
    if target not in JOB_TRANSITIONS[current]:
        raise ValueError(f"Invalid job status transition: {current.value} -> {target.value}")


def ensure_chunk_transition(current: ChunkStatus, target: ChunkStatus) -> None:
    if target not in CHUNK_TRANSITIONS[current]:
        raise ValueError(f"Invalid chunk status transition: {current.value} -> {target.value}")
