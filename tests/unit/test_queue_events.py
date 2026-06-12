from datetime import UTC, datetime
from uuid import uuid4

from app.queue.events import (
    ProgressUpdated,
    StreamEnvelope,
    TranscriptCompleted,
    TranscriptionRequested,
    decode_envelope,
    encode_envelope,
)


def test_stream_envelope_round_trip() -> None:
    payload = TranscriptionRequested(
        transcription_id=uuid4(),
        tenant_id="tenant-a",
        source_object_key="tenants/tenant-a/source/meeting.m4a",
        source_filename="meeting.m4a",
        source_content_type="audio/mp4",
        source_size_bytes=100,
    )
    envelope = StreamEnvelope(
        event_id="evt-1",
        event_type="transcription.requested",
        payload=payload.model_dump(mode="json"),
    )

    decoded = decode_envelope(encode_envelope(envelope))

    assert decoded == envelope


def test_progress_updated_round_trip() -> None:
    payload = ProgressUpdated(
        transcription_id=uuid4(),
        tenant_id="tenant-a",
        status="transcribing",
        completed_chunks=31,
        total_chunks=64,
        failed_chunks=0,
        progress_ratio=31 / 64,
        occurred_at=datetime.now(UTC),
    )
    envelope = StreamEnvelope(
        event_id="evt-3",
        event_type="transcription.progressed",
        payload=payload.model_dump(mode="json"),
    )

    decoded = decode_envelope(encode_envelope(envelope))

    assert decoded == envelope


def test_transcript_completed_round_trip() -> None:
    payload = TranscriptCompleted(
        transcription_id=uuid4(),
        tenant_id="tenant-a",
        result_object_key="tenants/tenant-a/transcriptions/abc/result/transcript.json",
    )
    envelope = StreamEnvelope(
        event_id="evt-2",
        event_type="transcription.transcript.completed",
        payload=payload.model_dump(mode="json"),
    )

    decoded = decode_envelope(encode_envelope(envelope))

    assert decoded == envelope
