from uuid import uuid4

from app.queue.events import StreamEnvelope, TranscriptionRequested, decode_envelope, encode_envelope


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
