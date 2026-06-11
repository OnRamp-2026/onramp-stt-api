from uuid import uuid4

from app.queue.events import StreamEnvelope, TranscriptionRequested


def test_transcription_request_accepts_minimal_contract() -> None:
    request = TranscriptionRequested(
        transcription_id=uuid4(),
        tenant_id="tenant-a",
        source_object_key="tenants/tenant-a/transcriptions/id/source/meeting.m4a",
    )
    envelope = StreamEnvelope(
        event_id="evt-1",
        event_type="transcription.requested",
        payload=request.model_dump(mode="json"),
    )

    parsed = TranscriptionRequested.model_validate(envelope.payload)

    assert parsed.source_filename is None
    assert parsed.source_size_bytes == 0
