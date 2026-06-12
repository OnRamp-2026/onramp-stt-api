from __future__ import annotations

import asyncio
import os
import socket

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.postgres import get_session_factory
from app.queue.constants import CORRECTION_WORKER_GROUP, STT_TRANSCRIPT_COMPLETED_STREAM
from app.queue.consumer import read_new_or_reclaim_pending
from app.queue.events import decode_envelope
from app.queue.redis import bootstrap_consumer_groups, get_redis
from app.services.correction_worker import CorrectionWorkerService
from app.storage.factory import get_storage

logger = structlog.get_logger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis = get_redis()
    await bootstrap_consumer_groups(redis)
    consumer = f"correction-{socket.gethostname()}-{os.getpid()}"
    service = CorrectionWorkerService(settings, get_session_factory(), get_storage())

    while True:
        messages = await read_new_or_reclaim_pending(
            redis,
            stream=STT_TRANSCRIPT_COMPLETED_STREAM,
            group=CORRECTION_WORKER_GROUP,
            consumer=consumer,
            count=1,
            block_ms=settings.redis_stream_block_ms,
            reclaim_idle_ms=settings.redis_pending_reclaim_idle_ms,
        )
        for _, entries in messages:
            for message_id, fields in entries:
                try:
                    await service.process(decode_envelope(fields))
                except Exception:
                    await logger.aexception("correction_event_failed", message_id=message_id)
                    continue
                await redis.xack(STT_TRANSCRIPT_COMPLETED_STREAM, CORRECTION_WORKER_GROUP, message_id)


if __name__ == "__main__":
    asyncio.run(run())
