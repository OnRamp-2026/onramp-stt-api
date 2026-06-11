from __future__ import annotations

import argparse
import asyncio
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Any, cast

from app.queue.constants import STT_REQUEST_STREAM
from app.queue.events import StreamEnvelope, TranscriptionRequested, encode_envelope
from app.queue.redis import close_redis, get_redis
from app.storage.factory import get_storage

logger = logging.getLogger(__name__)


async def enqueue(audio_path: Path, tenant_id: str, transcription_id: uuid.UUID) -> None:
    audio_path = audio_path.expanduser().resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    object_key = f"tenants/{tenant_id}/transcriptions/{transcription_id}/source/{audio_path.name}"
    content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    await get_storage().upload(audio_path, object_key, content_type=content_type)

    request = TranscriptionRequested(
        transcription_id=transcription_id,
        tenant_id=tenant_id,
        source_object_key=object_key,
        source_filename=audio_path.name,
        source_content_type=content_type,
        source_size_bytes=audio_path.stat().st_size,
    )
    envelope = StreamEnvelope(
        event_id=f"evt_{uuid.uuid4().hex}",
        event_type="transcription.requested",
        payload=request.model_dump(mode="json"),
    )
    redis = get_redis()
    try:
        await redis.xadd(
            STT_REQUEST_STREAM,
            cast(dict[Any, Any], encode_envelope(envelope)),
        )
    finally:
        await close_redis()

    logger.info("Enqueued transcription_id=%s", transcription_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload an audio file and enqueue a local STT request.")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--tenant-id", default="local")
    parser.add_argument("--transcription-id", type=uuid.UUID, default=uuid.uuid4())
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    asyncio.run(enqueue(args.audio, args.tenant_id, args.transcription_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
