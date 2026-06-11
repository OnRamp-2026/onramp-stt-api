from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StreamEnvelope(BaseModel):
    event_id: str
    event_type: str
    schema_version: Literal["1.0"] = "1.0"
    payload: dict[str, Any]


class TranscriptionRequested(BaseModel):
    transcription_id: UUID
    tenant_id: str = Field(min_length=1, max_length=128)
    source_object_key: str = Field(min_length=1)
    source_etag: str | None = None
    source_filename: str | None = Field(default=None, max_length=512)
    source_content_type: str = Field(default="application/octet-stream", min_length=1, max_length=128)
    source_size_bytes: int = Field(default=0, ge=0)
    requested_at: datetime | None = None


class ChunkRequested(BaseModel):
    transcription_id: UUID
    tenant_id: str
    chunk_index: int = Field(ge=0)
    chunk_object_key: str


def encode_envelope(envelope: StreamEnvelope) -> dict[str, str]:
    return {
        "event_id": envelope.event_id,
        "event_type": envelope.event_type,
        "schema_version": envelope.schema_version,
        "payload": json.dumps(envelope.payload, ensure_ascii=False, separators=(",", ":")),
    }


def decode_envelope(fields: dict[str, str]) -> StreamEnvelope:
    return StreamEnvelope(
        event_id=fields["event_id"],
        event_type=fields["event_type"],
        schema_version=fields.get("schema_version", "1.0"),
        payload=json.loads(fields["payload"]),
    )
